"""一句话记账：优先大模型结构化抽取，失败时退到本地规则解析（保证离线/断网也能用）。

设计要点：
- 模型只负责「懂人话」，映射到用户的分类/账户 ID 由服务端做，避免模型编 ID。
- 输出字段缺了就进 needs，让前端标黄提示用户确认，绝不悄悄猜。
- 本地规则不是主力，只在没有 API key 或接口超时时兜底。
- 这个账号学到的规则（learning.py）权重够就直接定类；不够的只作为 few-shot 注入模型，
  规则和画像都按 user_id 取，不同账号互不影响。
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta

import httpx

from . import learning

DEEPSEEK_BASE = os.getenv("DEEPSEEK_BASE_URL") or os.getenv("DEEPSEEK_BASE") or "https://api.deepseek.com"
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL") or "deepseek-chat"

# 建议新建分类时，这些「人/泛称」不适合拿来当分类名。
_SUGGEST_BLOCK = {"爱人", "配偶", "孩子", "儿子", "女儿", "家用", "转账", "红包", "工资"}

CAT_KEYWORDS = [
    ("餐饮", ["吃", "饭", "餐", "外卖", "早饭", "午饭", "晚饭", "夜宵", "烧烤", "火锅", "咖啡", "奶茶", "面", "包子"]),
    ("交通", ["打车", "地铁", "公交", "高铁", "火车", "机票", "出租车", "滴滴", "车费"]),
    ("汽车", ["加油", "充电", "停车费", "停车", "洗车", "保养", "高速", "过路", "油费"]),
    ("购物", ["买", "超市", "淘宝", "京东", "拼多多", "商超", "衣服", "鞋"]),
    ("烟酒", ["包烟", "香烟", "烟", "酒", "白酒", "啤酒"]),
    ("育儿", ["尿裤", "奶粉", "孩子", "幼儿园", "学费", "玩具", "疫苗", "宝宝"]),
    ("赡养", ["爸妈", "妈", "爸", "老人", "爷爷", "奶奶", "赡养", "给父母"]),
    ("医疗", ["药店", "买药", "药", "医院", "挂号", "体检", "看病", "牙"]),
    ("居家", ["房租", "水电", "燃气", "物业", "宽带", "话费", "家具"]),
    ("旅行", ["旅行", "酒店", "露营", "门票", "民宿", "景区"]),
    ("人情", ["红包", "随礼", "份子", "送礼"]),
]

# 收入类分类单独一张表：金额进账时只在这几类里找，别把「工资」归到「其它」。
INCOME_CAT_KEYWORDS = [
    ("工资", ["工资", "薪水", "发薪"]),
    ("奖金", ["奖金", "年终奖"]),
    ("其它收入", ["报销", "退款", "退钱", "收到", "进账", "红包收了", "利息"]),
]

# 给模型的分类说明（只用来消除歧义，不让它自己编分类）。关键词越具体越管用。
CAT_HINTS = {
    "餐饮": "吃饭、早饭午饭晚饭、外卖、奶茶咖啡、聚餐",
    "交通": "打车、地铁公交、火车机票",
    "汽车": "加油、充电、停车费、洗车、保养、高速过路费",
    "购物": "超市买菜、网购、买衣服日用品",
    "烟酒": "香烟、白酒啤酒",
    "育儿": "奶粉纸尿裤、幼儿园学费、玩具、疫苗",
    "赡养": "给爸妈/爷爷奶奶的钱和东西",
    "医疗": "药店买药、看病挂号、体检",
    "居家": "水电燃气物业、话费宽带、房租、家具",
    "旅行": "酒店民宿、门票、露营、出门旅游",
    "人情": "随礼份子、红包、送礼",
    "其它": "确实归不进上面的",
}


ACCOUNT_KEYWORDS = [
    ("微信", ["微信", "wx"]),
    ("支付宝", ["支付宝", "余额宝", "花呗"]),
    ("建行", ["建行", "银行卡", "卡里", "刷卡"]),
    ("现金", ["现金", "钱包", "现钱"]),
]

INCOME_KEYWORDS = ["工资", "奖金", "收入", "报销", "退款", "退钱", "收到", "进账", "红包收了"]


_CN_DIGIT = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
             "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_CN_UNIT = {"十": 10, "百": 100, "千": 1000}
_CN_SEQ = re.compile(r"[零〇一二两三四五六七八九十百千万]{2,12}")


def _cn_to_int(s: str) -> int:
    """中文数字转整数：「两千」→2000、「一百二」→102（口语尾数不追，够记账用）。"""
    total = section = number = 0
    for ch in s:
        if ch in _CN_DIGIT:
            number = _CN_DIGIT[ch]
        elif ch in _CN_UNIT:
            unit = _CN_UNIT[ch]
            section += (number or 1) * unit
            number = 0
        elif ch == "万":
            total += (section + number) * 10000
            section = number = 0
    return total + section + number


def _cn_amount(text: str) -> float | None:
    """「给我妈转两千」这类中文数字金额；带「元/块/钱」的优先。"""
    fallback = None
    for m in _CN_SEQ.finditer(text):
        val = _cn_to_int(m.group(0))
        if val <= 0:
            continue
        tail = text[m.end(): m.end() + 1]
        if tail in ("元", "块", "钱", "毛"):
            return float(val)
        if fallback is None and val >= 10:
            fallback = float(val)
    return fallback


def _best_hit(text: str, table) -> str | None:
    """在关键词表里找命中项，关键词越长越具体（「酒店」优先于「酒」）。"""
    best_len = 0
    best = None
    for name, kws in table:
        for k in kws:
            if k in text and len(k) > best_len:
                best_len = len(k)
                best = name
    return best


def _fallback(text: str, now: datetime) -> dict:
    """本地规则：抠金额、判收支、猜分类/账户、认相对日期。"""
    t = text.strip()
    amount = None
    for m in re.finditer(r"(\d+(?:\.\d{1,2})?)", t):
        tail = t[m.end(): m.end() + 2]
        if any(k in tail for k in ("元", "块", "毛", "￥", "¥")) or amount is None:
            amount = float(m.group(1))
            if any(k in tail for k in ("元", "块", "毛", "￥", "¥")):
                break
    cents = int(round(amount * 100)) if amount is not None else None
    if cents is None:  # 口语里的中文数字：「转两千」「花了三百」
        cn = _cn_amount(t)
        if cn is not None:
            cents = int(round(cn * 100))

    kind = "in" if any(k in t for k in INCOME_KEYWORDS) else "out"

    day = now
    if "前天" in t:
        day = now - timedelta(days=2)
    elif "昨天" in t:
        day = now - timedelta(days=1)
    hour = 12 if "中午" in t else 8 if "早上" in t or "早晨" in t else 20 if "晚上" in t else now.hour
    day = day.replace(hour=hour, minute=0, second=0, microsecond=0)

    # 命中多个分类时选「命中的关键词最长」的那个：「酒店」比「酒」具体、「停车」比「车」具体。
    cat = _best_hit(t, INCOME_CAT_KEYWORDS if kind == "in" else CAT_KEYWORDS)
    acct = _best_hit(t.lower(), ACCOUNT_KEYWORDS)

    return {
        "kind": kind,
        "amount_cents": cents,
        "category": cat,
        "account": acct,
        "occurred_at": day.isoformat(),
        "note": t[:80],
        "confidence": 0.55 if cents else 0.2,
        "engine": "rules",
    }


def _rule_value(rule, name: str, default=None):
    """规则既可能是 ORM 对象，也可能是评测脚本里的 dict。"""
    if isinstance(rule, dict):
        return rule.get(name, default)
    return getattr(rule, name, default)


def _normalize_suggestion(value, kind: str) -> dict | None:
    """把模型给的 suggest_category 规整成 {name, kind, icon}；不合格就丢掉。"""
    name = ""
    icon = "🏷"
    value_kind = kind
    if isinstance(value, dict):
        name = str(value.get("name") or "").strip()
        icon = str(value.get("icon") or "🏷")[:8]
        if str(value.get("kind") or "") in ("in", "out"):
            value_kind = str(value["kind"])
    elif isinstance(value, str):
        name = value.strip()
    if len(name) < 2:
        return None
    if re.search(r"[\u4e00-\u9fff]", name):
        name = name[:8]  # 中文分类名不超过 8 个字
    else:
        name = name[:16]
    return {"name": name, "kind": value_kind, "icon": icon}


def _build_prompt(
    text: str,
    now: datetime,
    cats: list[dict],
    accts: list[dict],
    *,
    hints: str = "",
    rules=None,
) -> list[dict]:
    cat_lines = "、".join(
        f"{c['name']}（{CAT_HINTS.get(c['name'], '')}）" if CAT_HINTS.get(c["name"]) else c["name"]
        for c in cats
        if not c.get("parent_id")
    ) or "餐饮、交通、汽车、购物、育儿"
    acct_lines = "、".join(a["name"] for a in accts) or "微信、支付宝、建行、现金"
    sys = (
        "你是家庭记账助手。把用户一句口语转成一条账单，只输出 JSON，不要解释、不要代码块。\n"
        "字段：kind(out=支出/in=收入)、amount(元，数字)、category(必须从给定分类里选，选不到就 null)、"
        "account(必须从给定账户里选，选不到就 null)、occurred_at(ISO8601，无年份按当前年)、"
        "note(不超过40字的简短备注)、confidence(0~1 你对自己判断的把握)、"
        'suggest_category(对象或 null；只有分类完全对不上、又像是一个新商户/新服务时才给 '
        '{"name":"中文名(不超过8个字)","kind":"out"}，否则给 null)。\n'
        f"今天的日期时间是 {now.strftime('%Y-%m-%d %H:%M %A')}。\n"
        f"可选分类（括号里是这个分类管什么）：{cat_lines}。\n"
        f"可选账户：{acct_lines}。\n"
        "规则：说『AA』『一起』按用户实际支付金额记；没提金额就 amount 给 null；"
        "没提账户就 account 给 null（不要瞎猜）；分类按括号里的说明对号入座，拿不准就 null。"
    )
    few_shots = learning.rules_for_prompt(rules, limit=8) if rules else []
    if few_shots:
        sys += "\n这个用户以前把相近的说法归到这些分类（优先照做）：\n" + "\n".join(
            f"- {p['pattern']} → {p['target_name']}" for p in few_shots
        )
    if hints:
        sys += f"\n这个用户的记账习惯（优先遵守）：\n{hints[:500]}"
    return [
        {"role": "system", "content": sys},
        {"role": "user", "content": text},
    ]


def _call_model(
    text: str,
    now: datetime,
    cats: list[dict],
    accts: list[dict],
    *,
    hints: str = "",
    rules=None,
) -> dict | None:
    key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not key:
        return None
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": _build_prompt(text, now, cats, accts, hints=hints, rules=rules),
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    try:
        with httpx.Client(timeout=15) as c:
            r = c.post(
                f"{DEEPSEEK_BASE}/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload,
            )
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
        data = json.loads(content)
        data["engine"] = DEEPSEEK_MODEL
        return data
    except Exception:  # 网络/额度/格式问题一律退规则，不把错误抛给用户
        return None


def parse_text(
    text: str,
    now: datetime,
    cats: list[dict],
    accts: list[dict],
    default_book_id: int | None = None,
    default_account: dict | None = None,
    *,
    rules=None,
    profile_hints: str = "",
    books: list[dict] | None = None,
) -> dict:
    """返回可直接入库的结构 + needs 列表（前端据此标黄让用户改）。

    rules/profile_hints 只来自当前登录账号（调用方负责按 user_id 取），
    权重 >=2 的规则直接定类，其余作为 few-shot 注入模型。
    """
    learned_hits = learning.direct_for_kinds(text, rules) if rules else {}
    if learned_hits:
        # 规则已经能定类，不必再花钱问模型；金额/日期仍用本地规则抠。
        raw = _fallback(text, now)
        engine = "learned"
    else:
        raw = _call_model(text, now, cats, accts, hints=profile_hints, rules=rules)
        engine = "model"
        if raw is None:
            raw = _fallback(text, now)
            engine = "rules"

    amount = raw.get("amount")
    cents = None
    if isinstance(amount, (int, float)):
        cents = int(round(float(amount) * 100))
    elif isinstance(amount, str) and re.match(r"^\d+(\.\d+)?$", amount.strip()):
        cents = int(round(float(amount) * 100))
    elif raw.get("amount_cents"):
        cents = int(raw["amount_cents"])

    kind = "in" if str(raw.get("kind", "out")).lower() in ("in", "income", "收入") else "out"

    def match(name: str | None, items: list[dict]) -> dict | None:
        if not name:
            return None
        name = str(name).strip()
        for it in items:
            if it["name"] == name:
                return it
        for it in items:
            if name in it["name"] or it["name"] in name:
                return it
        return None

    cat = match(raw.get("category"), cats)
    acct = match(raw.get("account"), accts)
    filled_default_acct = False
    if acct is None and default_account is not None:
        acct = default_account  # 没提账户就按上次用的那个，但仍标出来让用户看一眼
        filled_default_acct = True
    if cat is None and raw.get("category"):
        # 模型给了分类名但用户没有这个分类 → 退回关键词再猜一次
        hit = next((n for n, kws in CAT_KEYWORDS if any(k in str(raw["category"]) for k in kws)), None)
        cat = match(hit, cats) if hit else None

    book_id = default_book_id
    learned_rule: str | None = None
    learned_target: str | None = None

    # 学到的规则覆盖模型/规则结果（只覆盖它自己那个维度）
    if "category" in learned_hits:
        rule, pat = learned_hits["category"]
        tid = _rule_value(rule, "target_id")
        tname = str(_rule_value(rule, "target_name", "") or "")
        hit_cat = next((c for c in cats if c["id"] == tid), None) or match(tname, cats)
        if hit_cat is not None:
            cat = hit_cat
            learned_rule, learned_target = pat, hit_cat["name"]
    if "account" in learned_hits:
        rule, pat = learned_hits["account"]
        tid = _rule_value(rule, "target_id")
        tname = str(_rule_value(rule, "target_name", "") or "")
        hit_acct = next((a for a in accts if a["id"] == tid), None) or match(tname, accts)
        if hit_acct is not None:
            acct = hit_acct
            filled_default_acct = False
            if learned_rule is None:
                learned_rule, learned_target = pat, hit_acct["name"]
    if "book" in learned_hits and books:
        rule, _pat = learned_hits["book"]
        tid = _rule_value(rule, "target_id")
        tname = str(_rule_value(rule, "target_name", "") or "")
        hit_book = next((b for b in books if b["id"] == tid), None) or match(tname, books)
        if hit_book is not None:
            book_id = hit_book["id"]

    occurred = now
    ts = raw.get("occurred_at")
    if ts:
        try:
            occurred = datetime.fromisoformat(str(ts).replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            occurred = now

    needs = []
    if cents is None:
        needs.append("amount")
    if cat is None:
        needs.append("category")
    if filled_default_acct:
        needs.append("account")  # 填的是默认账户，让用户确认一下

    conf = float(raw.get("confidence") or 0)
    if engine == "rules":
        conf = min(conf, 0.6)
    if engine == "learned":
        conf = max(conf, 0.92)  # 学到的规则直接定类，给高一点的把握
    if needs:
        conf = min(conf, 0.5)

    # 新分类建议：只有在确实没归上类、又像新商户时才给
    suggest = None
    if cat is None:
        suggest = _normalize_suggestion(raw.get("suggest_category"), kind)
        if suggest is None and engine != "learned":
            for pat, _score in learning.extract_patterns(text)[:3]:
                name = learning.suggest_name(pat)
                if len(name) < 2 or name in _SUGGEST_BLOCK:
                    continue
                if any(c["name"] == name for c in cats):  # 已经有同名分类就不重复建议
                    continue
                suggest = {"name": name, "kind": kind, "icon": "🏷"}
                break

    return {
        "kind": kind,
        "amount_cents": cents,
        "cat_id": cat["id"] if cat else None,
        "cat_name": cat["name"] if cat else None,
        "account_id": acct["id"] if acct else None,
        "account_name": acct["name"] if acct else None,
        "book_id": book_id,
        # App 0.5.0 仍读 book_name（账本名直接显示，不再本地查表），缺了会让账本名空白
        "book_name": next((b["name"] for b in (books or []) if b["id"] == book_id), None),
        "occurred_at": occurred,
        "note": (raw.get("note") or text)[:80],
        "confidence": round(conf, 2),
        "engine": engine,
        "learned_rule": learned_rule,
        "learned_target": learned_target,
        "suggest_category": suggest,
        "needs": needs,
    }
