"""认证接口测试：注册校验 / 查重 / 登录 / 登出吊销 / 隔离。

跑：python -m pytest -q
"""
import os
import sys

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_ledger.db")
os.environ.setdefault("INVITE_CODE", "testcode")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c


def h(token):
    return {"Authorization": f"Bearer {token}"}


def test_check_username_free_and_bad_format(client):
    assert client.get("/api/v1/auth/check-username", params={"username": "alice"}).json()["available"] is True
    bad = client.get("/api/v1/auth/check-username", params={"username": "a b"}).json()
    assert bad["available"] is False and "账号名" in bad["reason"]


def test_register_rejects_bad_input(client):
    # 邀请码优先校验：错的邀请码不会泄露账号名格式问题的细节
    r = client.post("/api/v1/auth/register", json={"username": "a", "pin": "123456", "invite_code": "wrong"})
    assert r.status_code == 403 and "邀请码" in r.json()["detail"]

    r = client.post("/api/v1/auth/register", json={"username": "a", "pin": "123456", "invite_code": "testcode"})
    assert r.status_code == 422 and "账号名" in r.json()["detail"]

    r = client.post("/api/v1/auth/register", json={"username": "alice", "pin": "12345", "invite_code": "testcode"})
    assert r.status_code == 422 and "6 位" in r.json()["detail"]

    r = client.post(
        "/api/v1/auth/register",
        json={"username": "alice", "pin": "123456", "invite_code": "testcode", "display_name": "名" * 21},
    )
    assert r.status_code == 422 and "昵称" in r.json()["detail"]


def test_register_and_duplicate(client):
    r = client.post(
        "/api/v1/auth/register",
        json={"username": "alice", "pin": "123456", "invite_code": "testcode", "display_name": "Alice"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token"] and body["username"] == "alice" and body["display_name"] == "Alice"
    assert body["role"] == "user"

    assert client.get("/api/v1/auth/check-username", params={"username": "alice"}).json()["available"] is False

    r2 = client.post(
        "/api/v1/auth/register",
        json={"username": "alice", "pin": "123456", "invite_code": "testcode"},
    )
    assert r2.status_code == 409


def test_register_accepts_legacy_code_field(client):
    """旧客户端把邀请码放在 code 字段里，仍然要能注册。"""
    r = client.post(
        "/api/v1/auth/register",
        json={"username": "legacy", "pin": "123456", "code": "testcode", "display_name": "旧版客户端"},
    )
    assert r.status_code == 200, r.text


def test_login(client):
    assert client.post("/api/v1/auth/login", json={"username": "alice", "pin": "000000"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"username": "nobody", "pin": "123456"}).status_code == 401

    r = client.post("/api/v1/auth/login", json={"username": "alice", "pin": "123456"})
    assert r.status_code == 200 and r.json()["token"]


def test_logout_revokes_current_device(client):
    token = client.post(
        "/api/v1/auth/register",
        json={"username": "bob", "pin": "123456", "invite_code": "testcode", "display_name": "Bob"},
    ).json()["token"]
    assert client.get("/api/v1/me", headers=h(token)).status_code == 200

    r = client.post("/api/v1/auth/logout", headers=h(token))
    assert r.status_code == 200 and r.json()["ok"] is True

    # 旧 token 立刻失效
    assert client.get("/api/v1/me", headers=h(token)).status_code == 401


def test_other_device_unaffected_by_logout(client):
    t1 = client.post("/api/v1/auth/login", json={"username": "alice", "pin": "123456"}).json()["token"]
    t2 = client.post("/api/v1/auth/login", json={"username": "alice", "pin": "123456"}).json()["token"]
    client.post("/api/v1/auth/logout", headers=h(t1))
    assert client.get("/api/v1/me", headers=h(t1)).status_code == 401
    assert client.get("/api/v1/me", headers=h(t2)).status_code == 200  # 另一台设备还能用
