"""按账号隔离的 AI 学习：把用户的归类纠错沉淀成「关键词 → 分类/账户/账本」规则。

两个层次：
1. 规则（LearnedRule）：从一句话里抽出商户/服务名，记住用户把它归到了哪。
   weight >= 2 时解析直接定类（连模型都不用问）；weight = 1 的只作为 few-shot 注入提示词。
2. 画像（UserAiProfile）：每累计 10 条反馈，把最近的纠错压成 <=5 行中文提示，解析时喂给模型。
   模型调用失败就把规则拼成几行，绝不抛错、绝不阻塞记账。

所有数据都挂 user_id；不同账号之间互不可见、互不影响。
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime

import httpx
from sqlalchemy import select

from .models import Account, Book, Category, LearnedRule, UserAiProfile

# 与 ai.py 保持同源；这里单独读环境变量是为了避免 ai <-> learning 循环导入。
DEEPSEEK_BASE = os.getenv("DEEPSEEK_BASE_URL") or os.getenv("DEEPSEEK_BASE") or "https://api.deepseek.com"
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL") or "deepseek-chat"

# 抽关键词时要丢掉的词：动词、时间、金额单位、账户名、泛称。
_STOP_CN = {
    "买", "买了", "买点", "买了个", "吃", "吃了", "喝", "喝了", "付", "付了", "交", "充", "充值",    "花", "花了", "用", "用了", "给", "跟", "和", "帮", "替", "送", "请", "订", "续费", "订阅",
    "扣", "扣了", "退", "报销", "收到", "转", "转了", "领", "记", "记一笔", "记账",
    "的", "了", "吧", "呢", "吗", "啊", "呀", "个", "点", "一下", "一次", "一共", "总共",
    "大概", "左右", "还有", "以及", "然后", "就是", "这个", "那个", "今天", "昨天", "前天",
    "明天", "后天", "上午", "下午", "中午", "晚上", "早上", "早晨", "上周", "这周", "下周",
    "本月", "这个月", "上个月", "月底", "月初", "元", "块", "毛", "钱", "人民币", "现金",
    "微信", "支付宝", "银行卡", "建行", "卡里", "刷卡", "余额宝", "花呗", "账单", "消费",
    "支出", "收入", "记录", "东西", "费用", "服务", "商品", "订单", "红包", "转账", "AA",
    "会员", "年费", "月费", "套餐", "月卡", "年卡",
}
_EN_STOP = {
    "the", "a", "an", "and", "or", "for", "with", "of", "to", "in", "on", "at", "by", "from",
    "my", "our", "is", "was", "are", "it", "this", "that", "me", "i", "we", "you", "he", "she",
    "buy", "bought", "pay", "paid", "use", "used", "yuan", "rmb", "cny", "fee", "order",
}

_CN_RUN = re.compile(r"[\u4e00-\u9fff]+")
_EN_TOKEN = re.compile(r"[a-zA-Z][a-zA-Z0-9+#.\-]*")
_NUM = re.compile(r"\d+(?:\.\d+)?")
# 最长优先，避免「订阅」被「订」抢先切掉。
_STOP_CN_RE = re.compile("|".join(sorted((re.escape(w) for w in _STOP_CN), key=len, reverse=True)))


def _v(rule, name: str, default=None):
    """规则可能是 ORM 对象（线上）或 dict（评测/测试里的轻量规则）。"""
    if isinstance(rule, dict):
        return rule.get(name, default)
    return getattr(rule, name, default)


def normalize(text: str) -> str:
    """小写、去多余空白；规则匹配和存库都用这个形态。"""
    return " ".join((text or "").lower().split())


def _split_cn(run: str) -> list[str]:
    """按停用词把中文片段切开，只留有意义的片段（>=2 字）。

    不用整段替换：切开后「花店买花」还能留下「花店」，而「昨天中午跟同事吃饭」
    只剩「同事」，不会被动词/时间词污染。
    """
    return [seg.strip() for seg in _STOP_CN_RE.split(run) if len(seg.strip()) >= 2]


def extract_patterns(text: str) -> list[tuple[str, float]]:
    """从一句话里抽候选商户词，按「越具体越靠前」返回 [(pattern, score)]。

    中文：连续汉字片段（去掉动词/时间/账户词后）按 2~8 字切。
    英文：按词边界取相邻词组（2~3 个词）和单词，丢掉常见虚词。
    """
    t = _NUM.sub(" ", (text or "").lower())
    cands: list[tuple[str, float]] = []

    for run in _CN_RUN.findall(t):
        for part in _split_cn(run):
            L = len(part)
            if L < 2:
                continue
            if L <= 8:
                cands.append((part, min(0.95, 0.55 + 0.05 * L)))
            else:  # 太长就滑窗截取，最多 8 字
                for i in range(0, L - 7):
                    cands.append((part[i: i + 8], 0.9))

    runs: list[list[str]] = []
    cur: list[str] = []
    prev_end = None
    for m in list(_EN_TOKEN.finditer(t)) + [None]:
        if m is None:
            if cur:
                runs.append(cur)
            break
        w = m.group(0)
        if prev_end is not None:
            gap = t[prev_end: m.start()]
            if gap.strip():  # 中间隔着中文/标点（如「Open Code 的 Go」）就断开
                runs.append(cur)
                cur = []
        prev_end = m.end()
        if w in _EN_STOP or not w.isalpha():
            if cur:
                runs.append(cur)
                cur = []
            continue
        cur.append(w)
    for run in runs:
        if len(run) >= 2:
            for n in (3, 2):
                for i in range(len(run) - n + 1):
                    cands.append((" ".join(run[i: i + n]), 1.0 if n == 3 else 0.95))
        for w in run:
            if len(w) >= 4:  # 太短的词（go/ai）单独学没意义
                cands.append((w, 0.85 if len(w) >= 6 else 0.8))

    # 去重 + 分数降序；同分长的优先（更具体）
    seen: dict[str, float] = {}
    for pat, score in cands:
        pat = normalize(pat)
        if len(pat.replace(" ", "")) < 2 or pat in seen:
            continue
        seen[pat] = score
    return sorted(seen.items(), key=lambda kv: (kv[1], len(kv[0])), reverse=True)


def suggest_name(pattern: str) -> str:
    """候选词 → 建议的新分类名：英文标题化，中文截 8 字。"""
    pat = normalize(pattern)
    if not pat:
        return ""
    if re.fullmatch(r"[a-z0-9 +#.\-]+", pat):
        name = " ".join(w if w in ("+", "#", ".") else w.capitalize() for w in pat.split())
        return name[:16]
    return pat[:8]


def select_patterns(text: str, limit: int = 2) -> list[str]:
    """挑最具体的 1~2 个候选词；被更长候选包含的短词直接丢掉。"""
    out: list[str] = []
    for pat, _score in extract_patterns(text):
        flat = pat.replace(" ", "")
        if any(flat in o.replace(" ", "") for o in out):
            continue
        out.append(pat)
        if len(out) >= limit:
            break
    return out


def match_rules(text: str, rules) -> list:
    """返回命中的规则，最长关键词优先、weight 次之。

    - 整句包含（忽略空格）即命中；
    - 英文短语规则允许「长度 >= 4 的单词」命中：学到 open code 后，
      Commander Code / OpenCode 都能命中；
    """
    t = normalize(text)
    tc = t.replace(" ", "")
    words = set(re.findall(r"[a-z][a-z0-9+#.\-]{1,}", t))
    scored = []
    for r in rules:
        pat = normalize(_v(r, "pattern", "") or "")
        if len(pat.replace(" ", "")) < 2:
            continue
        pc = pat.replace(" ", "")
        if pat in t or (len(pc) >= 3 and pc in tc):
            hit = True
        elif re.fullmatch(r"[a-z0-9 +#.\-]+", pat):
            hit = any(w in words for w in pat.split() if len(w) >= 4)
        else:
            hit = False
        if hit:
            scored.append((len(pc), int(_v(r, "weight", 0) or 0), r))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [r for _, _, r in scored]


def direct_for_kinds(text: str, rules) -> dict:
    """能直接定案的维度：{kind: (rule, pattern)}，只取 weight >= 2 的规则。"""
    strong = [r for r in rules if int(_v(r, "weight", 0) or 0) >= 2]
    out: dict[str, tuple] = {}
    for r in match_rules(text, strong):
        out.setdefault(_v(r, "kind", ""), (r, _v(r, "pattern", "")))
    return out


def rules_for_prompt(rules, limit: int = 8) -> list[dict]:
    """挑最近最可信的规则做成 few-shot。"""
    if not rules:
        return []
    norm = [
        r for r in rules
        if not _v(r, "deleted", False) and normalize(_v(r, "pattern", "") or "")
    ]
    norm.sort(
        key=lambda r: (
            int(_v(r, "weight", 0) or 0),
            int(_v(r, "hits", 0) or 0),
            _v(r, "updated_at", None) or datetime.min,
        ),
        reverse=True,
    )
    return [
        {
            "kind": _v(r, "kind", ""),
            "pattern": _v(r, "pattern", ""),
            "target_name": _v(r, "target_name", ""),
            "target_id": _v(r, "target_id", None),
        }
        for r in norm[:limit]
    ]


# ---------------------------------------------------------------- 画像

def get_profile(db, user_id: int) -> UserAiProfile | None:
    """只读画像；解析接口每次调用不该顺手建行。"""
    return db.scalars(select(UserAiProfile).where(UserAiProfile.user_id == user_id)).first()


def get_or_create_profile(db, user_id: int) -> UserAiProfile:
    p = db.scalars(select(UserAiProfile).where(UserAiProfile.user_id == user_id)).first()
    if p is None:
        p = UserAiProfile(user_id=user_id, hints="", version=0, feedback_count=0)
        db.add(p)
        db.flush()
    return p


def _fallback_hints(rules) -> str:
    """模型不可用时的退化画像：直接拼「关键词 → 目标」。"""
    rows = rules_for_prompt(rules, limit=5)
    return "；".join(f"{r['pattern']} → {r['target_name']}" for r in rows if r["target_name"])


def _call_profile_model(prompt: str) -> str | None:
    """把近期纠错压成画像。没有 key / 网络失败 / 格式不对都返回 None，由调用方退化。"""
    key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not key:
        return None
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你在帮一个家庭记账 App 总结某个用户的归类习惯。根据下面的「说法 → 用户最终归到的类」，"
                    "写不超过 5 行中文短句，每行一条可执行的归类偏好（例如：Open Code、Commander Code 这类"
                    "AI 工具订阅都归「AI 研究」）。只输出偏好本身，不要编号、不要解释、不要标题。"
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
    }
    try:
        with httpx.Client(timeout=10) as c:
            r = c.post(
                f"{DEEPSEEK_BASE}/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload,
            )
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
        return str(content).strip() or None
    except Exception:  # 绝不因为画像失败影响记账
        return None


def refresh_profile(db, user_id: int) -> UserAiProfile:
    """按当前规则重建画像：优先用小模型压缩，失败退化为拼接，最多 5 行。"""
    profile = get_or_create_profile(db, user_id)
    rules = list(
        db.scalars(
            select(LearnedRule).where(LearnedRule.user_id == user_id, LearnedRule.deleted.is_(False))
        )
    )
    if not rules:
        profile.hints = ""
        profile.version = (profile.version or 0) + 1
        profile.updated_at = datetime.now()
        return profile

    rows = rules_for_prompt(rules, limit=12)
    prompt = "\n".join(f"- {r['pattern']} → {r['target_name']}" for r in rows)
    text = _call_profile_model(prompt) or _fallback_hints(rules)
    lines = [ln.strip(" -·\t") for ln in text.splitlines() if ln.strip()]
    profile.hints = "\n".join(lines[:5])[:500]
    profile.version = (profile.version or 0) + 1
    profile.updated_at = datetime.now()
    return profile


def record_feedback(db, user_id: int) -> UserAiProfile:
    """反馈计数 +1；每满 10 条重建一次画像。"""
    profile = get_or_create_profile(db, user_id)
    profile.feedback_count = int(profile.feedback_count or 0) + 1
    if profile.feedback_count % 10 == 0:
        try:
            refresh_profile(db, user_id)
        except Exception:  # 画像只是锦上添花，不能影响反馈接口
            pass
    return profile


# ---------------------------------------------------------------- 规则写入

def load_rules(db, user_id: int, include_deleted: bool = False) -> list[LearnedRule]:
    q = select(LearnedRule).where(LearnedRule.user_id == user_id)
    if not include_deleted:
        q = q.where(LearnedRule.deleted.is_(False))
    return list(db.scalars(q.order_by(LearnedRule.updated_at.desc(), LearnedRule.id.desc())))


def _owned_target(db, user_id: int, kind: str, target_id: int | None) -> tuple[int, str] | None:
    model = {"category": Category, "account": Account, "book": Book}.get(kind)
    if model is None or target_id is None:
        return None
    obj = db.get(model, int(target_id))
    if obj is None or getattr(obj, "user_id", None) != user_id or getattr(obj, "deleted", False):
        return None
    return obj.id, obj.name


def _find_category(db, user_id: int, name: str) -> Category | None:
    return db.scalars(
        select(Category).where(
            Category.user_id == user_id,
            Category.name == name,
            Category.deleted.is_(False),
        )
    ).first()


def upsert_rule(
    db,
    user_id: int,
    kind: str,
    pattern: str,
    target_name: str,
    target_id: int | None = None,
    *,
    source: str = "feedback",
    decisive: bool = False,
) -> LearnedRule:
    """有则 weight+1、hits+1；没有则新建。decisive（新建分类/明确表态）首次 weight=2。"""
    pat = normalize(pattern)
    rule = db.scalars(
        select(LearnedRule).where(
            LearnedRule.user_id == user_id,
            LearnedRule.kind == kind,
            LearnedRule.pattern == pat,
        )
    ).first()
    if rule is None:
        rule = LearnedRule(
            user_id=user_id,
            kind=kind,
            pattern=pat,
            target_id=target_id,
            target_name=target_name,
            weight=2 if decisive else 1,
            hits=1,
            source=source,
            deleted=False,
        )
        db.add(rule)
    else:
        rule.weight = int(rule.weight or 0) + 1
        if decisive:
            rule.weight = max(rule.weight, 2)
        rule.hits = int(rule.hits or 0) + 1
        rule.target_id = target_id
        rule.target_name = target_name
        rule.source = source
        rule.deleted = False
    db.flush()
    return rule


def learn_from_feedback(
    db,
    user,
    text: str,
    parsed: dict | None,
    final: dict | None,
    new_category: dict | None = None,
) -> list[dict]:
    """对比「AI 解析结果」和「用户最终保存的」，把变化的维度学成规则。

    new_category 表示用户采纳了「新建分类」建议：先建分类（或复用同名），
    这是明确表态，规则首次就记 weight=2，下次同类说法不用再问模型。
    """
    parsed = parsed or {}
    final = final or {}
    learned: list[dict] = []

    new_cat = None
    if new_category:
        name = str(new_category.get("name") or "").strip()[:32]
        if len(name) >= 1:
            kind = "in" if str(new_category.get("kind") or "out").lower() in ("in", "收入") else "out"
            icon = str(new_category.get("icon") or "🏷")[:8]
            new_cat = _find_category(db, user.id, name)
            if new_cat is None:
                new_cat = Category(user_id=user.id, name=name, kind=kind, icon=icon, sort=0)
                db.add(new_cat)
                db.flush()

    diffs: list[tuple[str, int | None, bool]] = []  # (kind, final_target_id, decisive)
    if new_cat is not None:
        diffs.append(("category", new_cat.id, True))
    elif final.get("cat_id") and parsed.get("cat_id") != final.get("cat_id"):
        diffs.append(("category", int(final["cat_id"]), False))
    if final.get("account_id") and parsed.get("account_id") != final.get("account_id"):
        diffs.append(("account", int(final["account_id"]), False))
    if final.get("book_id") and parsed.get("book_id") != final.get("book_id"):
        diffs.append(("book", int(final["book_id"]), False))

    patterns = select_patterns(text, limit=2)
    if not patterns:
        return learned

    for kind, target_id, decisive in diffs:
        target = _owned_target(db, user.id, kind, target_id)
        if target is None:
            continue
        tid, tname = target
        for pat in (patterns if kind == "category" else patterns[:1]):
            rule = upsert_rule(
                db,
                user.id,
                kind,
                pat,
                tname,
                tid,
                source="new_category" if decisive else "feedback",
                decisive=decisive,
            )
            learned.append(
                {
                    "kind": kind,
                    "pattern": rule.pattern,
                    "target_name": rule.target_name,
                    "weight": rule.weight,
                }
            )
    return learned
