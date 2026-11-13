"""AI 相关接口：解析一句话、接受纠错反馈、查看/删除学到的规则、查看/编辑个人画像。

全部走 Bearer 认证；所有查询都按当前登录用户的 user_id 过滤，越权一律 404
（不告诉对方"存在但不是你的"）。每个账号的规则和画像各自独立，互不可见、互不影响。
"""
from __future__ import annotations

import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from . import learning
from .ai import parse_text
from .auth import current_user
from .common import meta_of
from .db import get_db
from .models import LearnedRule, User
from .schemas import AiProfileIn, FeedbackIn, ParseIn, ParseOut

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])

# 画像正文（手动提示词 / 自动压缩结果）业务上限：500 字
PROFILE_HINTS_LIMIT = 500


def _iso(dt) -> str:
    if not dt:
        return datetime.now().isoformat(timespec="seconds")
    return dt.isoformat(timespec="seconds") if hasattr(dt, "isoformat") else str(dt)


def _profile_payload(profile) -> dict:
    return {
        "hints": profile.hints or "",
        "version": int(profile.version or 0),
        "feedback_count": int(profile.feedback_count or 0),
        "updated_at": _iso(profile.updated_at),
    }


def save_profile_hints(db: Session, user_id: int, hints: str) -> dict:
    """写入提示词（自我接口与管理台共用）：校验 500 字、version+1、返回 GET 同构。"""
    hints = (hints or "").strip()
    if len(hints) > PROFILE_HINTS_LIMIT:
        raise HTTPException(status_code=422, detail=f"提示词最多 {PROFILE_HINTS_LIMIT} 字")
    profile = learning.get_or_create_profile(db, user_id)
    profile.hints = hints
    profile.version = int(profile.version or 0) + 1
    profile.updated_at = datetime.now()
    db.commit()
    db.refresh(profile)
    return _profile_payload(profile)


@router.post("/parse", response_model=ParseOut)
def ai_parse(body: ParseIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> ParseOut:
    """一句话 → 结构化账单。带上这个账号学到的规则和画像，越用越准。"""
    m = meta_of(db, user)
    book_id = body.book_id or (m["books"][0]["id"] if m["books"] else None)
    default_acct = m["accounts"][0] if m["accounts"] else None

    rules = learning.load_rules(db, user.id)
    profile = learning.get_profile(db, user.id)
    res = parse_text(
        body.text,
        body.now or datetime.now(),
        m["categories"],
        m["accounts"],
        book_id,
        default_acct,
        rules=rules,
        profile_hints=(profile.hints or "") if profile else "",
        books=m["books"],
    )

    raw: dict = {"engine": res["engine"]}
    if res.get("learned_rule"):  # App 据此显示「AI 已学会」
        raw["learned_rule"] = res["learned_rule"]
    if res.get("learned_target"):
        raw["learned_target"] = res["learned_target"]

    return ParseOut(
        ok=res["amount_cents"] is not None,
        kind=res["kind"],
        amount_cents=res["amount_cents"],
        cat_id=res["cat_id"],
        cat_name=res["cat_name"],
        account_id=res["account_id"],
        account_name=res["account_name"],
        book_id=res["book_id"],
        book_name=res.get("book_name"),
        occurred_at=res["occurred_at"],
        note=res["note"],
        confidence=res["confidence"],
        raw=raw,
        needs=res["needs"],
        suggest_category=res.get("suggest_category"),
    )


@router.post("/feedback")
def ai_feedback(body: FeedbackIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """用户保存账单后回传「AI 解析的」和「实际保存的」，有差异就学成规则。"""
    parsed = body.parsed.model_dump() if body.parsed else {}
    final = body.final.model_dump() if body.final else {}
    new_cat = body.new_category.model_dump() if body.new_category else None
    learned = learning.learn_from_feedback(db, user, body.text, parsed, final, new_cat)
    learning.record_feedback(db, user.id)
    db.commit()
    return {"ok": True, "learned": learned}


@router.get("/rules")
def ai_rules(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    rows = learning.load_rules(db, user.id)
    return {
        "rules": [
            {
                "id": r.id,
                "kind": r.kind,
                "pattern": r.pattern,
                "target_id": r.target_id,
                "target_name": r.target_name,
                "weight": r.weight,
                "hits": r.hits,
                "source": r.source,
                "updated_at": _iso(r.updated_at),
            }
            for r in rows
        ]
    }


@router.delete("/rules/{rule_id}")
def ai_delete_rule(rule_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    rule = db.get(LearnedRule, rule_id)
    if rule is None or rule.user_id != user.id or rule.deleted:
        raise HTTPException(status_code=404, detail="规则不存在")
    rule.deleted = True
    rule.updated_at = datetime.now()
    db.commit()
    return {"ok": True}


@router.get("/profile")
def ai_profile(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    profile = learning.get_or_create_profile(db, user.id)
    db.commit()
    return _profile_payload(profile)


@router.put("/profile")
def ai_profile_put(
    body: AiProfileIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    """手动修改自己的 AI 提示词（≤500 字）；结构同 GET /ai/profile。"""
    return save_profile_hints(db, user.id, body.hints)


# App 里「它的记忆」页展示用：把 AI 实际拿到的提示词原样给用户看。
MEMORY_PROMPT_LIMIT = 4000
MEMORY_HOW = "先看你教过的规矩，再看商户关键词，最后让它自己判断；认错了你改一次，它就记一条"
# 提示词里不该出现的敏感串（真出现就打码，绝不把 key 漏给 App）
_SECRET_PATTERNS = re.compile(
    r"(sk-[A-Za-z0-9_\-]{6,}|Bearer\s+[A-Za-z0-9._\-]{8,}|api[_-]?key\s*[:=]\s*\S+)", re.IGNORECASE
)


def _mask_prompt(text: str) -> str:
    """脱敏 + 长度截断：App 要展示原文，但 key/token 不能跟着出去。"""
    masked = _SECRET_PATTERNS.sub("***", text)
    if len(masked) > MEMORY_PROMPT_LIMIT:
        tail = "…（后面还有内容，已截断）"
        masked = masked[: MEMORY_PROMPT_LIMIT - len(tail)] + tail
    return masked


def _memory_rules(rows) -> list[dict]:
    """和 GET /ai/rules 同一结构，前端可以复用解析。"""
    return [
        {
            "id": r.id,
            "kind": r.kind,
            "pattern": r.pattern,
            "target_id": r.target_id,
            "target_name": r.target_name,
            "weight": r.weight,
            "hits": r.hits,
            "source": r.source,
            "updated_at": _iso(r.updated_at),
        }
        for r in rows
    ]


@router.get("/memory")
def ai_memory(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """「AI 到底拿到了什么」：提示词原文 + 画像 + 规矩 + 计数。

    提示词不是从别处抄的模板，而是直接调 ai._build_prompt 的真实产物——
    和 /ai/parse 走模型时喂进去的一模一样，用户看到的就是它实际在用的。
    """
    from .ai import _build_prompt  # noqa: PLC0415  延迟导入，避免 ai ↔ ai_api 成环

    m = meta_of(db, user)
    rules = learning.load_rules(db, user.id)
    profile = learning.get_or_create_profile(db, user.id)
    hints = profile.hints or ""
    db.commit()

    messages = _build_prompt(
        "（这里只是展示，不是真实要记的账）",
        datetime.now(),
        m["categories"],
        m["accounts"],
        hints=hints,
        rules=rules,
    )
    # 只展示 system 那段（user 那段是具体那句话，展示提示词时没意义）
    system_text = next((msg["content"] for msg in messages if msg.get("role") == "system"), "")

    return {
        "prompt": _mask_prompt(system_text),
        "how": MEMORY_HOW,
        "hints": hints,
        "rules": _memory_rules(rules),
        "stats": {
            "rules": len(rules),
            "feedback_count": int(profile.feedback_count or 0),
            "version": int(profile.version or 0),
            "updated_at": _iso(profile.updated_at),
        },
    }
