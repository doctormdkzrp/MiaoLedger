"""认证：账号 + 6 位密码 → 设备 token。所有接口按 token 里的用户过滤数据。"""
import hashlib
import hmac
import os
import secrets
from datetime import datetime

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import Device, User

PBKDF2_ROUNDS = 120_000

ROLE_ADMIN = "admin"
ROLE_USER = "user"


def hash_pin(pin: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(8)
    dk = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt.encode(), PBKDF2_ROUNDS)
    return f"pbkdf2${salt}${dk.hex()}"


def verify_pin(pin: str, stored: str) -> bool:
    try:
        _, salt, _ = stored.split("$", 2)
    except ValueError:
        return False
    return hmac.compare_digest(hash_pin(pin, salt), stored)


def issue_token(db: Session, user: User, device_name: str) -> str:
    token = secrets.token_urlsafe(32)
    db.add(Device(user_id=user.id, name=device_name[:64], token=token))
    db.commit()
    return token


def current_user(
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
) -> User:
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="缺少 token")
    token = authorization[7:].strip()
    dev = db.scalar(select(Device).where(Device.token == token))
    if dev is None:
        raise HTTPException(status_code=401, detail="token 无效，请重新登录")
    dev.last_seen = datetime.now()
    db.commit()
    user = db.get(User, dev.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    """管理台接口的守卫：不是管理员一律 403（不带任何"你是谁"的细节）。"""
    if (getattr(user, "role", "") or ROLE_USER) != ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


def revoke_token(db: Session, user_id: int, token: str) -> bool:
    """登出时吊销一台设备的 token；返回是否真的删到了。"""
    if not token:
        return False
    dev = db.scalar(select(Device).where(Device.user_id == user_id, Device.token == token))
    if dev is None:
        return False
    db.delete(dev)
    db.commit()
    return True


def revoke_all_tokens(db: Session, user_id: int) -> int:
    """踢掉某个用户的所有设备（重置密码时用）；返回吊销数量。"""
    rows = db.scalars(select(Device).where(Device.user_id == user_id)).all()
    for dev in rows:
        db.delete(dev)
    return len(rows)


def promote_admin(db: Session, username: str) -> bool:
    """把指定账号提为管理员；账号不存在时返回 False（不报错）。"""
    username = (username or "").strip()
    if not username:
        return False
    user = db.scalar(select(User).where(User.username == username))
    if user is None:
        return False
    user.role = ROLE_ADMIN
    db.commit()
    return True


def promote_from_env(db: Session) -> bool:
    """启动引导：ADMIN_USERNAME 指定的账号存在就提为 admin。"""
    return promote_admin(db, os.getenv("ADMIN_USERNAME", ""))


def invite_code() -> str:
    """注册邀请码；空字符串表示不校验（开放注册）。"""
    return os.getenv("INVITE_CODE", "").strip()
