"""认证：账号 + 6 位密码 → 设备 token。所有接口按 token 里的用户过滤数据。"""
import hashlib
import hmac
import os
import secrets
import threading
from datetime import datetime, timedelta

from fastapi import Depends, Header, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .db import get_db
from .models import Device, User

PBKDF2_ROUNDS = 120_000

ROLE_ADMIN = "admin"
ROLE_USER = "user"

# 设备状态：没见过/没批过的叫 pending，批了叫 approved，被管理员踢掉的叫 revoked。
DEVICE_PENDING = "pending"
DEVICE_APPROVED = "approved"
DEVICE_REVOKED = "revoked"

DEVICE_PENDING_HINT = "这台设备还没被批准"
DEVICE_REVOKED_HINT = "这台设备已经被停用了"
DEVICE_GONE_HINT = "没有这台设备"

# 连着错 5 次密码锁 10 分钟：6 位数字只有 100 万种，不锁的话公网上几小时就能撞穿。
FAIL_LIMIT = 5
LOCK_SECONDS = 600
LOCKED_HINT = "密码错太多次，10 分钟后再试"


class DeviceBlocked(HTTPException):
    """设备没批准 / 被停用：403，响应体顶层带 code，客户端按 code 分流文案。

    形状按工单要求是 {"detail": "...", "code": "DEVICE_PENDING"}，
    所以不能直接借 HTTPException.detail 表达 code（那样会嵌成 detail.detail）。
    """

    def __init__(self, detail: str, code: str) -> None:
        super().__init__(status_code=403, detail=detail)
        self.code = code


class LoginLock:
    """登录失败计数，内存里放着（重启清零，工单明确说可以接受）。

    只算「连续」失败：登录成功就把这个账号的清零。锁到期也清零。
    """

    def __init__(self) -> None:
        self._fails: dict[str, list[datetime]] = {}
        self._until: dict[str, datetime] = {}
        self._guard = threading.Lock()

    def wait_seconds(self, username: str) -> int:
        """还在锁里就返回剩余秒数，否则 0。"""
        with self._guard:
            until = self._until.get(username)
            if until is None:
                return 0
            left = (until - datetime.now()).total_seconds()
            if left <= 0:
                self._until.pop(username, None)
                self._fails.pop(username, None)
                return 0
            return int(left) + 1

    def fail(self, username: str) -> None:
        with self._guard:
            now = datetime.now()
            recent = [t for t in self._fails.get(username, []) if (now - t).total_seconds() <= LOCK_SECONDS]
            recent.append(now)
            if len(recent) >= FAIL_LIMIT:
                self._until[username] = now + timedelta(seconds=LOCK_SECONDS)
                self._fails[username] = []
            else:
                self._fails[username] = recent

    def ok(self, username: str) -> None:
        with self._guard:
            self._fails.pop(username, None)
            self._until.pop(username, None)

    def reset(self) -> None:
        """测试用：清空所有计数。"""
        with self._guard:
            self._fails.clear()
            self._until.clear()


LOGIN_LOCK = LoginLock()


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


def _new_token() -> str:
    return secrets.token_urlsafe(32)


def _dead_token(kind: str) -> str:
    """占位 token：pending / revoked 的设备也有 token 列（NOT NULL + 唯一），
    但没人拿得到它，所以等价于「这台设备现在没有登录凭据」。"""
    return f"{kind}-{secrets.token_hex(24)}"


def issue_token(db: Session, user: User, device_name: str, *, device_uuid: str = "") -> str:
    """注册时直接发一份新设备凭据（注册本身已经过邀请码，不需要再批一次）。"""
    name = (device_name or "android").strip()[:64] or "android"
    token = _new_token()
    now = datetime.now()
    db.add(
        Device(
            user_id=user.id,
            name=name,
            token=token,
            device_uuid=(device_uuid or "").strip()[:64],
            device_name=name,
            status=DEVICE_APPROVED,
            first_seen=now,
            last_seen=now,
        )
    )
    db.commit()
    return token


def find_device(db: Session, user_id: int, device_uuid: str) -> Device | None:
    """按客户端自己生成的设备指纹找记录（老客户端没有指纹，永远找不到）。"""
    device_uuid = (device_uuid or "").strip()
    if not device_uuid:
        return None
    return db.scalar(
        select(Device)
        .where(Device.user_id == user_id, Device.device_uuid == device_uuid)
        .order_by(Device.id.desc())
    )


def device_for_login(db: Session, user: User, device_uuid: str, device_name: str) -> Device:
    """登录时认设备，返回可以发 token 的那一条；不能放行就抛 403。

    - 请求头没带设备指纹（老客户端）：沿用老逻辑放行一次，发一条 approved 记录。
      下一版本会强制带，这里不再加严是怕一上线把旧客户端全废掉。
    - 带了指纹但服务端不认识：先看这个账号有没有「升级前的老记录」可以接管
      （老库补列时 device_uuid 是空的、status 是 approved）。接管过来直接 approved ——
      这一条是为了让已经在用的手机升级后不被自己的新规则锁在外面。
      每条老记录只能被接管一次，所以第二台没批过的新手机照样要管理员批。
    - 认到了：approved 放行、pending/revoked 一律 403，revoked 永远不放（要重新批得走管理台）。
    """
    uuid = (device_uuid or "").strip()[:64]
    name = (device_name or "").strip()[:64] or "android"
    now = datetime.now()

    if not uuid:
        dev = Device(
            user_id=user.id,
            name=name,
            token=_new_token(),
            device_uuid="",
            device_name=name,
            status=DEVICE_APPROVED,
            first_seen=now,
            last_seen=now,
        )
        db.add(dev)
        db.commit()
        db.refresh(dev)
        return dev

    dev = find_device(db, user.id, uuid)
    if dev is not None:
        status = dev.status or DEVICE_APPROVED
        if status == DEVICE_REVOKED:
            raise DeviceBlocked(DEVICE_REVOKED_HINT, "DEVICE_REVOKED")
        if status != DEVICE_APPROVED:
            raise DeviceBlocked(DEVICE_PENDING_HINT, "DEVICE_PENDING")
        dev.last_seen = now
        dev.name = dev.device_name = name
        db.commit()
        return dev

    legacy = db.scalar(
        select(Device)
        .where(
            Device.user_id == user.id,
            or_(Device.device_uuid == "", Device.device_uuid.is_(None)),
            Device.status == DEVICE_APPROVED,
        )
        .order_by(Device.last_seen.desc(), Device.id.desc())
    )
    if legacy is not None:
        legacy.device_uuid = uuid
        legacy.name = legacy.device_name = name
        legacy.last_seen = now
        if legacy.first_seen is None:
            legacy.first_seen = now
        db.commit()
        return legacy

    pending = Device(
        user_id=user.id,
        name=name,
        token=_dead_token("pending"),
        device_uuid=uuid,
        device_name=name,
        status=DEVICE_PENDING,
        first_seen=now,
        last_seen=now,
    )
    db.add(pending)
    db.commit()
    raise DeviceBlocked(DEVICE_PENDING_HINT, "DEVICE_PENDING")


def rotate_token(db: Session, dev: Device) -> str:
    """给已经认过的设备换一张新 token（每次登录都换，旧 token 就失效）。"""
    token = _new_token()
    dev.token = token
    dev.last_seen = datetime.now()
    db.commit()
    return token


def drop_device_tokens(db: Session, user_id: int, keep_token: str = "") -> int:
    """作废某个用户（除 keep_token 以外）的登录凭据，但保留设备记录本身。

    保留记录的原因：设备指纹 + approved 状态得留着，不然这些手机下次登录会被
    当成「没批过的新设备」卡住。改密码踢人只要踢掉凭据就够了。
    """
    rows = db.scalars(select(Device).where(Device.user_id == user_id)).all()
    killed = 0
    for dev in rows:
        if keep_token and dev.token == keep_token:
            continue
        if (dev.status or DEVICE_APPROVED) == DEVICE_REVOKED:
            continue
        if dev.token.startswith(("pending-", "kicked-", "revoked-")):
            continue
        dev.token = _dead_token("kicked")
        killed += 1
    return killed


def revoke_device(db: Session, dev: Device) -> None:
    """管理员踢掉一台设备：状态置 revoked，同时作废它手里的 token。"""
    dev.status = DEVICE_REVOKED
    dev.token = _dead_token("revoked")
    db.commit()


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
    if (dev.status or DEVICE_APPROVED) == DEVICE_REVOKED:
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
    """登出时吊销一台设备的凭据；返回是否真的吊销了。

    设备记录留着（指纹和 approved 状态要保住），只把 token 换成没人拿得到的占位值，
    这样同一台手机再登录不用重新等批准。
    """
    if not token:
        return False
    dev = db.scalar(select(Device).where(Device.user_id == user_id, Device.token == token))
    if dev is None:
        return False
    dev.token = _dead_token("kicked")
    db.commit()
    return True


def revoke_all_tokens(db: Session, user_id: int) -> int:
    """踢掉某个用户的所有设备（重置密码时用）；返回吊销数量。"""
    return drop_device_tokens(db, user_id)


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
