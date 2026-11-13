"""管理台接口：查人、建号、改号、代用户看账改账、导入导出、看/改画像。

约定：
- 全部要求 role=admin（require_admin）；普通用户访问一律 403「需要管理员权限」。
- 目标账号不存在一律 404「没有这个用户」，不区分"查无此人"和"不是你的"。
- 错误 detail 全是中文人话，管理台直接把这句话弹给管理员。
"""
from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .ai_api import _profile_payload, save_profile_hints
from .auth import ROLE_ADMIN, ROLE_USER, hash_pin, require_admin, revoke_all_tokens
from .common import (
    check_amount,
    check_kind,
    export_csv_text,
    find_txn,
    import_csv,
    meta_of,
    seed_user,
    txn_payload,
)
from .db import get_db
from .models import Book, Txn, User
from .schemas import AdminTxnIn, AdminUserIn, AdminUserPatchIn, AiProfileIn, TxnOut, TxnPatchIn

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{2,20}$")
PIN_RE = re.compile(r"^\d{6}$")
ROLES = (ROLE_ADMIN, ROLE_USER)


# ---------------------------------------------------------------- 小工具
def _target(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="没有这个用户")
    return user


def _user_payload(db: Session, user: User) -> dict:
    txns = db.scalar(
        select(func.count()).select_from(Txn).where(Txn.user_id == user.id, Txn.deleted.is_(False))
    )
    books = db.scalar(
        select(func.count()).select_from(Book).where(Book.user_id == user.id, Book.deleted.is_(False))
    )
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role or ROLE_USER,
        "created_at": user.created_at,
        "txns": int(txns or 0),
        "books": int(books or 0),
    }


def _check_name(username: str) -> str:
    username = (username or "").strip()
    if not USERNAME_RE.match(username):
        raise HTTPException(status_code=422, detail="账号名只能用 2–20 位英文字母、数字或下划线")
    return username


def _check_pin(pin: str) -> str:
    pin = pin or ""
    if not PIN_RE.match(pin):
        raise HTTPException(status_code=422, detail="密码要 6 位数字")
    return pin


def _check_role(role: str) -> str:
    role = (role or "").strip()
    if role not in ROLES:
        raise HTTPException(status_code=422, detail="角色只能是 admin（管理员）或 user（普通用户）")
    return role


def _admin_count(db: Session) -> int:
    return int(db.scalar(select(func.count()).select_from(User).where(User.role == ROLE_ADMIN)) or 0)


def _day(value: str | None, label: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=422, detail=f"{label}日期格式要是 YYYY-MM-DD")


# ---------------------------------------------------------------- 用户
@router.get("/users")
def list_users(_admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(User).order_by(User.id)).all()
    return [_user_payload(db, u) for u in rows]


@router.post("/users")
def create_user(
    body: AdminUserIn,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """管理台直接开号：自动带默认账本/账户/分类，role 可指定。"""
    username = _check_name(body.username)
    pin = _check_pin(body.pin)
    role = _check_role(body.role or ROLE_USER)
    name = (body.display_name or "").strip() or username
    if len(name) > 20:
        raise HTTPException(status_code=422, detail="昵称最多 20 个字")
    if db.scalar(select(User).where(User.username == username)):
        raise HTTPException(status_code=409, detail="这个账号名已经有人用了，换一个")

    user = User(username=username, display_name=name, pin_hash=hash_pin(pin), role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    seed_user(db, user)
    return _user_payload(db, user)


@router.patch("/users/{user_id}")
def patch_user(
    user_id: int,
    body: AdminUserPatchIn,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """改用户名 / 昵称 / 密码 / 角色。

    - 改用户名：查重，重了 409。
    - 改密码：吊销该用户全部设备 token（代表用户被踢下线，要用新密码重登）。
    - 降级：最后一个管理员不许降级，否则没人能进管理台。
    """
    user = _target(db, user_id)

    if body.username is not None:
        username = _check_name(body.username)
        if username != user.username:
            if db.scalar(select(User).where(User.username == username)):
                raise HTTPException(status_code=409, detail="这个账号名已经有人用了，换一个")
            user.username = username

    if body.display_name is not None:
        name = body.display_name.strip()
        if len(name) > 20:
            raise HTTPException(status_code=422, detail="昵称最多 20 个字")
        user.display_name = name or user.username

    revoked = 0
    if body.pin is not None:
        user.pin_hash = hash_pin(_check_pin(body.pin))
        revoked = revoke_all_tokens(db, user.id)

    if body.role is not None:
        role = _check_role(body.role)
        if (user.role or ROLE_USER) == ROLE_ADMIN and role != ROLE_ADMIN and _admin_count(db) <= 1:
            raise HTTPException(status_code=422, detail="至少要保留一个管理员")
        user.role = role

    db.commit()
    db.refresh(user)
    payload = _user_payload(db, user)
    payload["revoked_devices"] = revoked
    return payload


# ---------------------------------------------------------------- 代用户看数据
@router.get("/users/{user_id}/meta")
def user_meta(user_id: int, _admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    return meta_of(db, _target(db, user_id))


@router.get("/users/{user_id}/txns")
def user_txns(
    user_id: int,
    start: str | None = Query(default=None, alias="from", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    end: str | None = Query(default=None, alias="to", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    book_id: int | None = None,
    include_deleted: bool = False,
    limit: int = Query(default=200, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    user = _target(db, user_id)
    conds = [Txn.user_id == user.id]
    t0 = _day(start, "开始")
    t1 = _day(end, "结束")
    if t0 is not None:
        conds.append(Txn.occurred_at >= t0)
    if t1 is not None:
        # to 含当天：查询条件是 < 次日零点
        conds.append(Txn.occurred_at < t1 + timedelta(days=1))
    if book_id is not None:
        conds.append(Txn.book_id == book_id)
    if not include_deleted:
        conds.append(Txn.deleted.is_(False))

    total = int(db.scalar(select(func.count()).select_from(Txn).where(*conds)) or 0)
    rows = db.scalars(
        select(Txn).where(*conds).order_by(Txn.occurred_at.desc(), Txn.id.desc()).limit(limit).offset(offset)
    ).all()
    return {"total": total, "items": [txn_payload(r) for r in rows]}


@router.post("/users/{user_id}/txns", response_model=TxnOut)
def create_user_txn(
    user_id: int,
    body: AdminTxnIn,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> TxnOut:
    """管理台代记一笔：client_uuid 由服务端生成，手机下次同步会拉到。"""
    user = _target(db, user_id)
    m = meta_of(db, user)
    book_id = body.book_id or (m["books"][0]["id"] if m["books"] else None)
    row = Txn(
        user_id=user.id,
        client_uuid=secrets.token_hex(16),
        book_id=book_id,
        cat_id=body.cat_id,
        account_id=body.account_id,
        kind=check_kind(body.kind) or "out",
        amount_cents=check_amount(body.amount_cents) or 0,
        occurred_at=body.occurred_at or datetime.now(),
        note=(body.note or "")[:200],
        source=body.source or "manual",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return TxnOut(**txn_payload(row))


@router.patch("/users/{user_id}/txns/{client_uuid}", response_model=TxnOut)
def patch_user_txn(
    user_id: int,
    client_uuid: str,
    body: TxnPatchIn,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> TxnOut:
    user = _target(db, user_id)
    row = find_txn(db, user.id, client_uuid)
    if row is None:
        raise HTTPException(status_code=404, detail="没有这笔账")

    if body.book_id is not None:
        row.book_id = body.book_id
    if body.cat_id is not None:
        row.cat_id = body.cat_id
    if body.account_id is not None:
        row.account_id = body.account_id
    kind = check_kind(body.kind)
    if kind is not None:
        row.kind = kind
    amount = check_amount(body.amount_cents)
    if amount is not None:
        row.amount_cents = amount
    if body.occurred_at is not None:
        row.occurred_at = body.occurred_at
    if body.note is not None:
        row.note = body.note[:200]
    row.updated_at = datetime.now()
    db.commit()
    db.refresh(row)
    return TxnOut(**txn_payload(row))


@router.delete("/users/{user_id}/txns/{client_uuid}")
def delete_user_txn(
    user_id: int,
    client_uuid: str,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    user = _target(db, user_id)
    row = find_txn(db, user.id, client_uuid)
    if row is None:
        raise HTTPException(status_code=404, detail="没有这笔账")
    row.deleted = True
    row.updated_at = datetime.now()
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- 代用户 AI 画像 / 导入导出
@router.get("/users/{user_id}/ai-profile")
def user_ai_profile(user_id: int, _admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    from . import learning  # noqa: PLC0415  延迟导入，保持 admin_api 启动轻量

    user = _target(db, user_id)
    profile = learning.get_or_create_profile(db, user.id)
    db.commit()
    return _profile_payload(profile)


@router.put("/users/{user_id}/ai-profile")
def put_user_ai_profile(
    user_id: int,
    body: AiProfileIn,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    user = _target(db, user_id)
    return save_profile_hints(db, user.id, body.hints)


@router.get("/users/{user_id}/export.csv", response_class=PlainTextResponse)
def user_export_csv(
    user_id: int,
    start: str = Query(alias="from", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    end: str = Query(alias="to", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    book_id: int | None = None,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> PlainTextResponse:
    user = _target(db, user_id)
    return PlainTextResponse(
        export_csv_text(db, user, start, end, book_id), media_type="text/csv; charset=utf-8"
    )


@router.post("/users/{user_id}/import/csv")
async def user_import_csv(
    user_id: int,
    file: UploadFile = File(...),
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    user = _target(db, user_id)
    raw = await file.read()
    return import_csv(db, user, raw)
