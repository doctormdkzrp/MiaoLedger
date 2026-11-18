"""新设备批准 + 登录失败锁定（WO-03）。

覆盖：
- 老客户端不带设备头 → 照老逻辑放行（不能一上线把旧客户端全废掉）
- 新手机带没见过的设备指纹 → 403 DEVICE_PENDING，且不建活凭据
- 管理员批了 → 同一台手机再登录能进
- 管理员停用 → 那台手机的 token 立刻失效，再登录是 403 DEVICE_REVOKED
- 升级兼容：老库里 device_uuid 为空、status=approved 的记录会被第一台带指纹的手机接管
- 连错 5 次密码 → 429 锁 10 分钟，锁内正确密码也进不去，别的账号不受影响

全部跑在临时 SQLite 上，不碰真库。

运行：python -m pytest -q server/tests/test_devices.py
"""
import os
import sys

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_devices_tmp.db")
os.environ.setdefault("INVITE_CODE", "testcode")
os.environ.pop("ADMIN_USERNAME", None)  # 别让宿主环境的引导配置干扰测试

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.auth import LOGIN_LOCK, promote_admin  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Device  # noqa: E402


@pytest.fixture(scope="module")
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_lock():
    """锁定计数是模块级单例，用例之间必须清干净，否则互相污染。"""
    LOGIN_LOCK.reset()
    yield
    LOGIN_LOCK.reset()


def h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def dev_headers(device_uuid: str, name: str = "POCO X3") -> dict:
    return {"X-Device-Id": device_uuid, "X-Device-Name": name}


def register(c, username: str, pin: str = "123456", device_uuid: str | None = None) -> str:
    r = c.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "pin": pin,
            "invite_code": "testcode",
            "display_name": username,
        },
        headers=dev_headers(device_uuid) if device_uuid else {},
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


def login(c, username: str, pin: str = "123456", device_uuid: str | None = None):
    return c.post(
        "/api/v1/auth/login",
        json={"username": username, "pin": pin},
        headers=dev_headers(device_uuid) if device_uuid else {},
    )


def devices_of(c, admin_token: str, user_id: int) -> list[dict]:
    r = c.get(f"/api/v1/admin/users/{user_id}/devices", headers=h(admin_token))
    assert r.status_code == 200, r.text
    return r.json()["items"]


def user_id_of(c, admin_token: str, username: str) -> int:
    rows = c.get("/api/v1/admin/users", headers=h(admin_token)).json()
    for row in rows:
        if row["username"] == username:
            return row["id"]
    raise AssertionError(f"没找到账号 {username}")


@pytest.fixture(scope="module")
def admin_token(client) -> str:
    token = register(client, "dev_admin", device_uuid="admin-phone-0001")
    with SessionLocal() as db:
        assert promote_admin(db, "dev_admin") is True
    return token


# ---------------------------------------------------------------- 兼容性：不带设备头
def test_login_without_device_header_still_works(client):
    """老客户端不带 X-Device-Id：照老逻辑放行，并留一条 approved 记录。"""
    register(client, "legacy_a", device_uuid=None)
    r = login(client, "legacy_a", device_uuid=None)
    assert r.status_code == 200, r.text
    assert r.json()["token"]
    with SessionLocal() as db:
        rows = db.scalars(
            select(Device).where(Device.device_uuid == "", Device.status == "approved")
        ).all()
    assert rows, "不带指纹的登录应该留一条 approved 记录"


# ---------------------------------------------------------------- 新设备：pending → 批准
def test_new_device_is_pending_then_approved(client, admin_token):
    uid = "iPhone-15-pro-max-aaaa"
    register(client, "newbie", device_uuid=uid)  # 注册那台直接批（过了邀请码）
    user_id = user_id_of(client, admin_token, "newbie")

    # 换一台没见过的手机登录
    r = login(client, "newbie", device_uuid="second-phone-bbbb")
    assert r.status_code == 403, r.text
    body = r.json()
    assert body["code"] == "DEVICE_PENDING"
    assert body["detail"] == "这台设备还没被批准"

    items = devices_of(client, admin_token, user_id)
    pending = [d for d in items if d["status"] == "pending"]
    assert len(pending) == 1
    assert pending[0]["device_id"] == "second-phone-bbbb"
    assert pending[0]["token_alive"] is False, "没批的设备不该有活凭据"
    assert pending[0]["name"] == "POCO X3"

    # 待批期间反复点登录：一直是 403，不会被当成撞密码锁住账号
    for _ in range(6):
        again = login(client, "newbie", device_uuid="second-phone-bbbb")
        assert again.status_code == 403
        assert again.json()["code"] == "DEVICE_PENDING"

    # 管理员批了就能进
    device_id = pending[0]["id"]
    ok = client.post(
        f"/api/v1/admin/users/{user_id}/devices/{device_id}/approve", headers=h(admin_token)
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["device"]["status"] == "approved"

    r = login(client, "newbie", device_uuid="second-phone-bbbb")
    assert r.status_code == 200, r.text
    assert r.json()["token"]


def test_pending_device_list_puts_pending_first(client, admin_token):
    register(client, "listorder", device_uuid="listorder-phone-1")
    user_id = user_id_of(client, admin_token, "listorder")
    login(client, "listorder", device_uuid="listorder-phone-2")  # → pending
    data = client.get(f"/api/v1/admin/users/{user_id}/devices", headers=h(admin_token)).json()
    assert data["total"] == 2
    assert data["pending"] == 1
    assert data["items"][0]["status"] == "pending", "待批的要排最前面，管理员一眼能看到"


# ---------------------------------------------------------------- 停用
def test_revoked_device_loses_token_and_cannot_login(client, admin_token):
    uid = "revoke-phone-0001"
    token = register(client, "revokee", device_uuid=uid)
    user_id = user_id_of(client, admin_token, "revokee")
    assert client.get("/api/v1/me", headers=h(token)).status_code == 200

    items = devices_of(client, admin_token, user_id)
    target = [d for d in items if d["device_id"] == uid][0]
    r = client.post(f"/api/v1/admin/users/{user_id}/devices/{target['id']}/revoke", headers=h(admin_token))
    assert r.status_code == 200, r.text
    assert r.json()["device"]["status"] == "revoked"

    assert client.get("/api/v1/me", headers=h(token)).status_code == 401, "停用的设备手里的 token 要立刻失效"

    r = login(client, "revokee", device_uuid=uid)
    assert r.status_code == 403, r.text
    assert r.json()["code"] == "DEVICE_REVOKED"
    assert r.json()["detail"] == "这台设备已经被停用了"


def test_unknown_device_id_is_404(client, admin_token):
    user_id = user_id_of(client, admin_token, "revokee")
    r = client.post(f"/api/v1/admin/users/{user_id}/devices/999999/approve", headers=h(admin_token))
    assert r.status_code == 404
    assert r.json()["detail"] == "没有这台设备"


def test_devices_requires_admin(client):
    token = register(client, "plainuser", device_uuid="plain-phone-0001")
    with SessionLocal() as db:
        uid = db.scalar(select(Device.user_id).where(Device.device_uuid == "plain-phone-0001"))
    r = client.get(f"/api/v1/admin/users/{uid}/devices", headers=h(token))
    assert r.status_code == 403
    assert r.json()["detail"] == "需要管理员权限"


# ---------------------------------------------------------------- 升级兼容
def test_legacy_device_record_is_taken_over_once(client):
    """老库补列后设备记录 device_uuid 为空、status=approved。

    第一台带指纹的手机应该接管这条记录直接通过，老用户升级不会被自己的新规则锁在外面；
    接管后第二条新手机再登录就必须等批准。
    """
    register(client, "upgrader", device_uuid=None)  # 模拟升级前那台手机
    with SessionLocal() as db:
        legacy = db.scalars(select(Device).where(Device.name == "android")).all()
        assert legacy, "注册时没带设备头应该留一条老式记录"
        legacy_ids = {d.id for d in legacy}

    r = login(client, "upgrader", device_uuid="upgraded-phone-0001")
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        taken = db.scalar(select(Device).where(Device.device_uuid == "upgraded-phone-0001"))
        assert taken is not None
        assert taken.id in legacy_ids, "应该接管老记录，而不是新建一条"
        assert taken.status == "approved"

    # 第二条没批过的手机照样卡住
    r = login(client, "upgrader", device_uuid="upgraded-phone-0002")
    assert r.status_code == 403
    assert r.json()["code"] == "DEVICE_PENDING"


def test_legacy_backfill_sets_approved():
    """补列时 status 默认 approved：即使某条记录 status 是空的，回填也把它置 approved。"""
    from app.db import backfill_legacy_devices, ensure_schema

    ensure_schema(engine)
    with SessionLocal() as db:
        dev = db.scalar(select(Device).order_by(Device.id))
        dev.status = ""
        db.commit()
        dev_id = dev.id

    backfill_legacy_devices(engine)

    with SessionLocal() as db:
        assert db.get(Device, dev_id).status == "approved"


# ---------------------------------------------------------------- 登录失败锁定
def test_five_wrong_pins_lock_the_account(client):
    register(client, "lockme", pin="111111", device_uuid="lock-phone-0001")

    for i in range(5):
        r = login(client, "lockme", pin="999999", device_uuid="lock-phone-0001")
        assert r.status_code == 401, f"第 {i + 1} 次错密码应该还是 401"

    r = login(client, "lockme", pin="999999", device_uuid="lock-phone-0001")
    assert r.status_code == 429, r.text
    assert r.json()["detail"] == "密码错太多次，10 分钟后再试"
    assert int(r.headers["Retry-After"]) > 0

    # 锁里连正确密码都不行（不然锁就没意义了）
    r = login(client, "lockme", pin="111111", device_uuid="lock-phone-0001")
    assert r.status_code == 429


def test_lock_does_not_affect_other_accounts(client):
    register(client, "victim", pin="222222", device_uuid="victim-phone-0001")
    register(client, "bystander", pin="333333", device_uuid="bystander-phone-0001")
    for _ in range(5):
        login(client, "victim", pin="000000")
    assert login(client, "victim", pin="222222").status_code == 429
    assert login(client, "bystander", pin="333333").status_code == 200, "别人不该被连坐"


def test_successful_login_resets_the_counter(client):
    register(client, "forgetful", pin="444444", device_uuid="forgetful-phone-0001")
    for _ in range(4):
        assert login(client, "forgetful", pin="000000").status_code == 401
    # 第 5 次输对：计数清零，不该被锁
    assert login(client, "forgetful", pin="444444").status_code == 200
    for _ in range(4):
        assert login(client, "forgetful", pin="000000").status_code == 401
    assert login(client, "forgetful", pin="444444").status_code == 200, "成功本该把连错次数清零"


def test_unknown_username_also_counts(client):
    """账号不存在也计数：不然攻击者能从「有没有被锁」反推出账号存不存在。"""
    for _ in range(5):
        assert login(client, "nobody_here", pin="000000").status_code == 401
    r = login(client, "nobody_here", pin="000000")
    assert r.status_code == 429
