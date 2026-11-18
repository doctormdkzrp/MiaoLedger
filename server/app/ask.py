"""自然语言提问：模型只把问题翻译成查询条件，数字一律由 SQL 算。

为什么这么绕：让模型直接回答「这个月买吃的花了多少」，它会给一个看起来很像、
但其实编出来的数。账目数字错一位，这个功能就是负资产。所以流程是死的：

    问题 → 模型只输出查询条件 JSON（不许写 SQL、不许写数字）
         → 服务端按白名单校验（字段名/枚举/日期格式/分类与账本必须是这个人自己的）
         → 参数化 SQL 聚合出真实数字
         → 把「问题 + 条件 + 结果表」交给模型写一句人话（只许用结果表里的数字）
         → 结果为空就直说没有记录，不编

模型从头到尾碰不到数据库，也拿不到明细行；它两次出场都只是「翻译」。
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import date, datetime, timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .auth import current_user
from .common import meta_of
from .db import get_db
from .models import Book, Category, Txn, User
from .schemas import AskIn, AskOut

router = APIRouter(prefix="/api/v1", tags=["ask"])

DEEPSEEK_BASE = os.getenv("DEEPSEEK_BASE_URL") or os.getenv("DEEPSEEK_BASE") or "https://api.deepseek.com"
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL") or "deepseek-chat"

# 查询条件 schema：服务端只认这几个字段，多一个都不认。
PLAN_FIELDS = (
    "metric",
    "date_from",
    "date_to",
    "categories",
    "books",
    "keyword",
    "group_by",
    "order",
    "limit",
)
METRICS = ("sum", "count", "avg")
GROUP_BYS = ("category", "book", "month", "day")
ORDERS = ("asc", "desc")

ROW_LIMIT_MAX = 200
QUERY_TIMEOUT = 5.0

EMPTY_ANSWER = "这个范围里没有记录。"
SCOPE_ANSWER = "我只能查你的账，别的答不了。"

# 计划里这些字段不允许模型自己定死成任意字符串，统一在下面按白名单裁剪。
_NOISE = re.compile(r"\s+")


# ---------------------------------------------------------------- 模型出场（可 mock）
def _call_model_json(prompt: str) -> dict | None:
    """让模型只回一个 JSON 对象。没有 key / 网络错 / 返回不是对象 → None。"""
    key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not key:
        return None
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "response_format": {"type": "json_object"},
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
        data = json.loads(content)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _call_model_text(prompt: str) -> str | None:
    """让模型写一句话。失败返回 None，由模板兜底（模板只用结果表里的数字）。"""
    key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not key:
        return None
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [{"role": "user", "content": prompt}],
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
            return (r.json()["choices"][0]["message"]["content"] or "").strip() or None
    except Exception:
        return None


# ---------------------------------------------------------------- 第一步：问题 → 条件
def _plan_prompt(text: str, now: datetime, cats: list[str], books: list[str]) -> str:
    return (
        "你是记账系统里的查询翻译器。把用户的问题翻译成查询条件，只输出 JSON，不要解释、不要代码块。\n"
        "严格按这个结构输出，字段不许增删、不许改名字：\n"
        "{\n"
        '  "metric": "sum" 或 "count" 或 "avg",\n'
        '  "date_from": "YYYY-MM-DD",\n'
        '  "date_to": "YYYY-MM-DD",\n'
        '  "categories": ["分类名"],\n'
        '  "books": ["账本名"],\n'
        '  "keyword": "备注里的关键词或空串",\n'
        '  "group_by": ["category" 或 "book" 或 "month" 或 "day"],\n'
        '  "order": "asc" 或 "desc",\n'
        '  "limit": 整数\n'
        "}\n"
        "硬性约束：\n"
        "1. 只输出条件。绝对不要输出 SQL，绝对不要输出任何金额、笔数之类的数字结果。\n"
        "2. categories 只能从下面这份分类清单里挑，books 只能从账本清单里挑；挑不到就给空数组。\n"
        "3. 没说范围就按这个月；说「上个月」「去年这个月」自己换算成具体日期。\n"
        "4. 问「多少 / 花了多少 / 一共」用 sum；问「几笔 / 多少次」用 count；问「平均」用 avg。\n"
        "5. 如果这句话不是在问账目统计（比如问天气、闲聊），直接输出 {\"in_scope\": false}。\n"
        f"今天是 {now.strftime('%Y-%m-%d')}，当前时刻 {now.strftime('%H:%M')}。\n"
        f"分类清单：{'、'.join(cats) or '（无）'}\n"
        f"账本清单：{'、'.join(books) or '（无）'}\n"
        f"用户的问题：{text}"
    )


def _fallback_plan(text: str, now: datetime, cats: list[str]) -> dict | None:
    """没有模型时用的本地翻译：只认日期说法和分类关键词，够答常见问法。

    同样是「只产出条件」，不产出任何数字 —— 数字仍然由 SQL 算。
    """
    t = text.strip()
    if not t:
        return None
    # 先判断是不是在问账：问句里得有点「钱/花/多少/几笔」的意思
    if not any(k in t for k in ("多少", "几笔", "几次", "一共", "总共", "合计", "平均", "花", "支出", "收入", "消费")):
        return None

    today = now.date()
    if "去年这个月" in t or "去年同期" in t:
        first = today.replace(year=today.year - 1, day=1)
    elif "上个月" in t or "上月" in t:
        first = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    elif "这个月" in t or "本月" in t:
        first = today.replace(day=1)
    elif "今天" in t:
        first = today
    elif "昨天" in t:
        first = today - timedelta(days=1)
    elif "今年" in t:
        first = today.replace(month=1, day=1)
    else:
        first = today.replace(day=1)

    if first == today or first == today - timedelta(days=1):
        last = first
    else:
        nxt = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
        last = nxt - timedelta(days=1)

    metric = "count" if ("几笔" in t or "几次" in t or "多少笔" in t) else "avg" if "平均" in t else "sum"

    # 分类：先看有没有直接说到分类名；没有再用口语关键词对，且只取命中最具体的那个
    # （「买吃的」同时命中「购物/买」和「餐饮/吃」，取关键词更长的，别把两类都算上）
    hit_cats = [c for c in cats if c and c in t]
    if not hit_cats:
        from .ai import CAT_KEYWORDS, INCOME_CAT_KEYWORDS  # 复用同一份关键词表，别维护两套

        best_name, best_len = None, 0
        for name, kws in CAT_KEYWORDS + INCOME_CAT_KEYWORDS:
            if name not in cats:
                continue
            for k in kws:
                if k in t and len(k) > best_len:
                    best_name, best_len = name, len(k)
        if best_name:
            hit_cats = [best_name]

    group_by: list[str] = []
    if "按分类" in t or "每个分类" in t or "各类" in t:
        group_by = ["category"]
    elif "按天" in t or "每天" in t:
        group_by = ["day"]
    elif "按月" in t or "每个月" in t:
        group_by = ["month"]

    return {
        "metric": metric,
        "date_from": first.isoformat(),
        "date_to": last.isoformat(),
        "categories": hit_cats,
        "books": [],
        "keyword": "",
        "group_by": group_by,
        "order": "desc",
        "limit": 50,
    }


def _as_date(value, default: date) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return datetime.strptime(str(value).strip()[:10], "%Y-%m-%d").date()
    except Exception:
        return default


def _as_str_list(value) -> list[str]:
    if isinstance(value, str):
        return [v.strip() for v in re.split(r"[,，、\s]+", value) if v.strip()]
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def _sanitize_plan(raw: dict, now: datetime, cats: list[str], books: list[str]) -> dict:
    """白名单校验：字段名、枚举、日期格式、分类/账本必须真实存在。

    任何一项不合格就退回安全默认值，绝不把模型给的字符串直接拼进查询。
    """
    today = now.date()
    metric = str(raw.get("metric") or "sum").strip().lower()
    if metric not in METRICS:
        metric = "sum"

    date_from = _as_date(raw.get("date_from"), today.replace(day=1))
    date_to = _as_date(raw.get("date_to"), today)
    if date_to < date_from:
        date_from, date_to = date_to, date_from

    # 分类/账本只留这个账号真有的名字，其余一律当不存在（越权或模型瞎编都进不来）
    wanted_cats = _as_str_list(raw.get("categories"))
    allowed_cats = [c for c in wanted_cats if c in cats]
    wanted_books = _as_str_list(raw.get("books"))
    allowed_books = [b for b in wanted_books if b in books]

    keyword = _NOISE.sub(" ", str(raw.get("keyword") or "")).strip()[:40]

    group_by = [g for g in _as_str_list(raw.get("group_by")) if g in GROUP_BYS][:2]

    order = str(raw.get("order") or "desc").strip().lower()
    if order not in ORDERS:
        order = "desc"

    try:
        limit = int(raw.get("limit") or 50)
    except Exception:
        limit = 50
    limit = max(1, min(limit, ROW_LIMIT_MAX))

    return {
        "metric": metric,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "categories": allowed_cats,
        "books": allowed_books,
        "keyword": keyword,
        "group_by": group_by,
        "order": order,
        "limit": limit,
        # 模型给了但用户没有的，记下来只用于日志，不进查询
        "_dropped": {
            "categories": [c for c in wanted_cats if c not in cats],
            "books": [b for b in wanted_books if b not in books],
        },
    }


def make_plan(db: Session, user: User, text: str, now: datetime) -> dict | None:
    """把问题翻成查询条件；完全不像在问账就返回 None。"""
    m = meta_of(db, user)
    cats = [c["name"] for c in m["categories"]]
    books = [b["name"] for b in m["books"]]

    raw = _call_model_json(_plan_prompt(text, now, cats, books))
    if raw is not None and raw.get("in_scope") is False:
        return None
    if raw is None:
        raw = _fallback_plan(text, now, cats)
    if raw is None:
        return None
    return _sanitize_plan(raw, now, cats, books)


# ---------------------------------------------------------------- 第二步：条件 → SQL 结果
def run_query(db: Session, user: User, plan: dict) -> dict:
    """参数化查询，只算聚合，不把明细行整批吐出去。"""
    started = time.monotonic()
    date_from = datetime.fromisoformat(plan["date_from"])
    date_to = datetime.fromisoformat(plan["date_to"]) + timedelta(days=1)

    conds = [
        Txn.user_id == user.id,
        Txn.deleted.is_(False),
        Txn.kind == "out",
        Txn.occurred_at >= date_from,
        Txn.occurred_at < date_to,
    ]

    if plan["categories"]:
        cat_ids = db.scalars(
            select(Category.id).where(
                Category.user_id == user.id, Category.name.in_(plan["categories"])
            )
        ).all()
        if not cat_ids:
            return {"total_cents": 0, "count": 0, "rows": [], "elapsed_ms": 0}
        conds.append(Txn.cat_id.in_(list(cat_ids)))

    if plan["books"]:
        book_ids = db.scalars(
            select(Book.id).where(Book.user_id == user.id, Book.name.in_(plan["books"]))
        ).all()
        if not book_ids:
            return {"total_cents": 0, "count": 0, "rows": [], "elapsed_ms": 0}
        conds.append(Txn.book_id.in_(list(book_ids)))

    if plan["keyword"]:
        conds.append(Txn.note.contains(plan["keyword"], autoescape=True))

    group_by = plan["group_by"]
    rows: list[dict] = []
    total_cents = 0
    count = 0

    if not group_by:
        total_cents, count = db.execute(
            select(func.coalesce(func.sum(Txn.amount_cents), 0), func.count()).where(*conds)
        ).one()
    else:
        dim = group_by[0]
        if dim == "category":
            key = Txn.cat_id
            names = {c["id"]: c["name"] for c in meta_of(db, user)["categories"]}
        elif dim == "book":
            key = Txn.book_id
            names = {b["id"]: b["name"] for b in meta_of(db, user)["books"]}
        elif dim == "day":
            key = func.strftime("%Y-%m-%d", Txn.occurred_at)
            names = {}
        else:  # month
            key = func.strftime("%Y-%m", Txn.occurred_at)
            names = {}

        q = (
            select(key, func.coalesce(func.sum(Txn.amount_cents), 0), func.count())
            .where(*conds)
            .group_by(key)
            .limit(plan["limit"])
        )
        raw_rows = db.execute(q).all()
        bucket = []
        for k, cents, n in raw_rows:
            if isinstance(k, str):
                label = k
            else:
                label = names.get(k) or "未分类"
            bucket.append({"name": label, "cents": int(cents or 0), "count": int(n or 0)})
        bucket.sort(key=lambda r: r["cents"], reverse=(plan["order"] == "desc"))
        rows = bucket
        total_cents = sum(r["cents"] for r in rows)
        count = sum(r["count"] for r in rows)

    elapsed_ms = int((time.monotonic() - started) * 1000)
    if (time.monotonic() - started) > QUERY_TIMEOUT:
        raise HTTPException(status_code=503, detail="查得太慢了，把范围说小一点再问")

    return {
        "total_cents": int(total_cents or 0),
        "count": int(count or 0),
        "rows": rows,
        "elapsed_ms": elapsed_ms,
    }


# ---------------------------------------------------------------- 第三步：结果 → 一句话
def _yuan(cents: int) -> str:
    return f"{cents / 100:,.2f}"


def _fallback_answer(plan: dict, data: dict) -> str:
    """没有模型时用模板写：每个数字都来自 data，不推算、不补充。"""
    if not data["total_cents"] and not data["count"]:
        return EMPTY_ANSWER
    span = f"{plan['date_from']} 到 {plan['date_to']}"
    what = "、".join(plan["categories"]) if plan["categories"] else "支出"
    if plan["metric"] == "count":
        return f"{span}，{what}一共 {data['count']} 笔。"
    if plan["metric"] == "avg":
        avg = data["total_cents"] // data["count"] if data["count"] else 0
        return f"{span}，{what}一共 {data['count']} 笔，平均每笔 {_yuan(avg)} 元。"
    if data["rows"]:
        parts = "，".join(f"{r['name']} {_yuan(r['cents'])} 元" for r in data["rows"][:6])
        return f"{span}，{what}一共 {_yuan(data['total_cents'])} 元（{parts}）。"
    return f"{span}，{what}一共 {_yuan(data['total_cents'])} 元。"


def _answer_prompt(text: str, plan: dict, data: dict) -> str:
    table = [
        f"- 合计 {_yuan(data['total_cents'])} 元",
        f"- 笔数 {data['count']}",
    ]
    for r in data["rows"][:20]:
        table.append(f"- {r['name']}：{_yuan(r['cents'])} 元，{r['count']} 笔")
    return (
        "你在替用户查账。下面是一次查询的真实结果表，请用一句中文把结果说清楚。\n"
        "硬性约束：只允许使用结果表中出现的数字，不得推算、不得补充、不得估算比例或同比环比。\n"
        "结果表里没有的数字，一个都不许写。不要提 SQL、不要提查询条件这些技术细节。\n"
        f"用户问的是：{text}\n"
        f"查询范围：{plan['date_from']} 到 {plan['date_to']}"
        + (f"，分类 {'、'.join(plan['categories'])}" if plan["categories"] else "")
        + "\n结果表：\n"
        + "\n".join(table)
    )


def _narrate(text: str, plan: dict, data: dict) -> str:
    if not data["total_cents"] and not data["count"]:
        return EMPTY_ANSWER
    said = _call_model_text(_answer_prompt(text, plan, data))
    if not said:
        return _fallback_answer(plan, data)
    # 模型偶尔会把提示词照抄回来或者带上代码块，清一下再给用户
    said = said.strip().strip("`").strip()
    return said or _fallback_answer(plan, data)


# ---------------------------------------------------------------- 接口
@router.post("/ask", response_model=AskOut)
def ask(body: AskIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> AskOut:
    """问一句账目统计：模型翻译条件 → 服务端算数 → 模型写人话。"""
    now = body.now or datetime.now()
    plan = make_plan(db, user, body.text, now)
    if plan is None:
        return AskOut(answer=SCOPE_ANSWER, query={}, data={"total_cents": 0, "count": 0, "rows": []})

    data = run_query(db, user, plan)
    # 日志留痕：模型输出 → 校验后条件 → SQL 结果，出问题能直接对账
    print(
        "[ask] plan=%s data_total=%s rows=%s dropped=%s"
        % (
            json.dumps({k: plan[k] for k in plan if not k.startswith("_")}, ensure_ascii=False),
            data["total_cents"],
            len(data["rows"]),
            json.dumps(plan.get("_dropped") or {}, ensure_ascii=False),
        )
    )
    answer = _narrate(body.text, plan, data)
    return AskOut(
        answer=answer,
        query={k: plan[k] for k in plan if not k.startswith("_")},
        data={
            "total_cents": data["total_cents"],
            "count": data["count"],
            "rows": data["rows"],
        },
    )
