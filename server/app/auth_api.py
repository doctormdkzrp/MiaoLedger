"""注册 / 登录 / 登出 / 账号名查重。

设计：
- 账号在 App 内注册；邀请码（INVITE_CODE）为空时开放注册，非空时必须一致。
- 管理员能力放在 /api/v1/admin（admin_api.py），这里只处理账号自己的事。
- 错误信息一律中文人话，客户端直接把 detail 显示给用户。
- 登录/注册都签发设备 token；登出会真吊销当前设备 token（不是前端假装退出）。
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import current_user, hash_pin, invite_code, issue_token, revoke_token, verify_pin
from .common import seed_user
from .db import get_db
from .models import Device, User
from .schemas import ChangePinIn, LoginIn, RegisterIn, TokenOut

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{2,20}$")
# 注册密码固定 6 位数字（手机上是数字键盘）；登录放宽到 4–32 位兼容老账号。
PIN_RE = re.compile(r"^\d{6}$")

USERNAME_HINT = "账号名只能用 2–20 位英文字母、数字或下划线"
PIN_HINT = "密码要 6 位数字"
CODE_HINT = "邀请码不对，请向管理员索取"
TAKEN_HINT = "这个账号名已经有人用了，换一个"
OLD_PIN_HINT = "现在的密码不对"
NEW_PIN_HINT = "新密码要正好 6 位数字"
SAME_PIN_HINT = "新密码和现在的密码一样"


@router.get("/check-username")
def check_username(username: str = "", db: Session = Depends(get_db)) -> dict:
    """注册第二步用：边输边查账号名能不能用。永远 200，用 available 表达结果。"""
    username = username.strip()
    if not USERNAME_RE.match(username):
        return {"available": False, "reason": USERNAME_HINT}
    exists = db.scalar(select(User).where(User.username == username)) is not None
    if exists:
        return {"available": False, "reason": TAKEN_HINT}
    return {"available": True, "reason": ""}


@router.post("/register", response_model=TokenOut)
def register(body: RegisterIn, db: Session = Depends(get_db)) -> TokenOut:
    expected = invite_code()
    if expected and (body.invite_code or "").strip() != expected:
        raise HTTPException(status_code=403, detail=CODE_HINT)

    username = body.username.strip()
    if not USERNAME_RE.match(username):
        raise HTTPException(status_code=422, detail=USERNAME_HINT)
    if not PIN_RE.match(body.pin):
        raise HTTPException(status_code=422, detail=PIN_HINT)

    name = (body.display_name or "").strip() or username
    if len(name) > 20:
        raise HTTPException(status_code=422, detail="昵称最多 20 个字")
    if db.scalar(select(User).where(User.username == username)):
        raise HTTPException(status_code=409, detail=TAKEN_HINT)

    user = User(username=username, display_name=name, pin_hash=hash_pin(body.pin), role="user")
    db.add(user)
    try:
        db.commit()
    except IntegrityError:  # 并发注册同名，唯一索引兜底
        db.rollback()
        raise HTTPException(status_code=409, detail=TAKEN_HINT)
    db.refresh(user)

    seed_user(db, user)
    token = issue_token(db, user, body.device_name or "android")
    return TokenOut(
        token=token, username=user.username, display_name=user.display_name, role=user.role or "user"
    )


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)) -> TokenOut:
    user = db.scalar(select(User).where(User.username == body.username.strip()))
    if user is None or not verify_pin(body.pin, user.pin_hash):
        raise HTTPException(status_code=401, detail="账号或密码不对")
    token = issue_token(db, user, body.device_name or "android")
    return TokenOut(
        token=token, username=user.username, display_name=user.display_name, role=user.role or "user"
    )


@router.post("/change-pin")
def change_pin(
    body: ChangePinIn,
    authorization: str = Header(default=""),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    """改 6 位数字密码。

    改完把其它设备的 token 全删掉（换手机/丢手机时能一脚踢开），当前这台保持登录。
    """
    if not verify_pin(body.old_pin or "", user.pin_hash):
        raise HTTPException(status_code=401, detail=OLD_PIN_HINT)
    if not PIN_RE.match(body.new_pin or ""):
        raise HTTPException(status_code=422, detail=NEW_PIN_HINT)
    if body.new_pin == body.old_pin:
        raise HTTPException(status_code=422, detail=SAME_PIN_HINT)

    token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
    user.pin_hash = hash_pin(body.new_pin)
    others = db.scalars(select(Device).where(Device.user_id == user.id, Device.token != token)).all()
    for dev in others:
        db.delete(dev)
    db.commit()
    return {"ok": True, "revoked_devices": len(others)}


@router.post("/logout")
def logout(
    authorization: str = Header(default=""),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    """吊销当前这台设备的 token：退出后旧 token 立刻不可用。"""
    token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
    revoked = revoke_token(db, user.id, token) if token else False
    return {"ok": True, "revoked": revoked}
