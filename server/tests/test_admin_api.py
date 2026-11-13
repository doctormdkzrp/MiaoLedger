"""管理台接口测试：权限、建号改名、重置密码、批量看账改账、AI 画像、CSV。

全部跑在临时 SQLite 上，不碰真库、不请求大模型。

运行：python -m pytest -q server/tests/test_admin_api.py
"""
import io
import os
import sys

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_admin_tmp.db")
os.environ.setdefault("INVITE_CODE", "testcode")
os.environ.pop("ADMIN_USERNAME", None)  # 别让宿主环境的引导配置干扰测试

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import inspect, text  # noqa: E402

from app.auth import promote_admin  # noqa: E402
from app.db import Base, SessionLocal, ensure_schema, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c
    engine.dispose()


def h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def register(c, username: str, pin: str = "123456", device: str = "android") -> str:
    r = c.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "pin": pin,
            "invite_code": "testcode",
            "display_name": username,
            "device_name": device,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


def register_or_login(c, username: str, pin: str = "123456", device: str = "test") -> str:
    r = c.post("/api/v1/auth/register", json={"username": username, "pin": pin, "invite_code": "testcode"})
    if r.status_code == 409:
        r = c.post("/api/v1/auth/login", json={"username": username, "pin": pin, "device_name": device})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin(client) -> dict:
    """造一个管理员：先普通注册，再走 promote（等价于 ADMIN_USERNAME / CLI promote）。"""
    token = register_or_login(client, "admin_root")
    with SessionLocal() as db:
        assert promote_admin(db, "admin_root") is True
    me = client.get("/api/v1/me", headers=h(token)).json()
    assert me["role"] == "admin"
    return {"token": token, "id": me.get("id")}


def admin_id(client, token: str) -> int:
    users = client.get("/api/v1/admin/users", headers=h(token)).json()
    return next(u["id"] for u in users if u["username"] == "admin_root")


# ---------------------------------------------------------------- 权限
def test_non_admin_gets_403(client):
    token = register_or_login(client, "plain_user")
    assert client.get("/api/v1/admin/users", headers=h(token)).status_code == 403
    r = client.post(
        "/api/v1/admin/users",
        json={"username": "hacker", "pin": "123456", "role": "admin"},
        headers=h(token),
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "需要管理员权限"
    assert client.get("/api/v1/admin/users").status_code == 401


# ---------------------------------------------------------------- 用户列表 / 建号 / 改名
def test_list_users(client, admin):
    users = client.get("/api/v1/admin/users", headers=h(admin["token"])).json()
    assert users
    row = next(u for u in users if u["username"] == "plain_user")
    assert set(row) >= {"id", "username", "display_name", "role", "created_at", "txns", "books"}
    assert row["role"] == "user" and row["books"] == 1


def test_create_user_seeds_defaults(client, admin):
    r = client.post(
        "/api/v1/admin/users",
        json={"username": "staff_01", "pin": "123456", "display_name": "员工一号", "role": "user"},
        headers=h(admin["token"]),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["username"] == "staff_01" and body["role"] == "user"
    assert body["books"] == 1  # 建号自动初始化默认账本

    m = client.get(f"/api/v1/admin/users/{body['id']}/meta", headers=h(admin["token"])).json()
    assert [b["name"] for b in m["books"]] == ["日常账本"]
    assert len(m["accounts"]) == 4 and len(m["categories"]) == 15

    # 重名 / 密码格式
    dup = client.post(
        "/api/v1/admin/users",
        json={"username": "staff_01", "pin": "123456"},
        headers=h(admin["token"]),
    )
    assert dup.status_code == 409
    bad = client.post(
        "/api/v1/admin/users",
        json={"username": "staff_bad", "pin": "12345"},
        headers=h(admin["token"]),
    )
    assert bad.status_code == 422 and "6 位" in bad.json()["detail"]


def test_create_user_requires_admin(client):
    token = register_or_login(client, "plain_user")
    r = client.post("/api/v1/admin/users", json={"username": "x2", "pin": "123456"}, headers=h(token))
    assert r.status_code == 403


def test_rename_conflict_409_and_success(client, admin):
    users = client.get("/api/v1/admin/users", headers=h(admin["token"])).json()
    target = next(u for u in users if u["username"] == "staff_01")

    conflict = client.patch(
        f"/api/v1/admin/users/{target['id']}", json={"username": "admin_root"}, headers=h(admin["token"])
    )
    assert conflict.status_code == 409

    ok = client.patch(
        f"/api/v1/admin/users/{target['id']}",
        json={"username": "staff_02", "display_name": "员工二号"},
        headers=h(admin["token"]),
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["username"] == "staff_02" and ok.json()["display_name"] == "员工二号"

    # 新用户名能登录，旧的不行
    assert client.post("/api/v1/auth/login", json={"username": "staff_02", "pin": "123456"}).status_code == 200
    assert client.post("/api/v1/auth/login", json={"username": "staff_01", "pin": "123456"}).status_code == 401


def test_reset_pin_revokes_all_devices(client, admin):
    users = client.get("/api/v1/admin/users", headers=h(admin["token"])).json()
    target = next(u for u in users if u["username"] == "staff_02")

    phone = client.post("/api/v1/auth/login", json={"username": "staff_02", "pin": "123456"}).json()["token"]
    tablet = client.post("/api/v1/auth/login", json={"username": "staff_02", "pin": "123456"}).json()["token"]
    assert client.get("/api/v1/me", headers=h(phone)).status_code == 200

    r = client.patch(
        f"/api/v1/admin/users/{target['id']}", json={"pin": "222222"}, headers=h(admin["token"])
    )
    assert r.status_code == 200, r.text
    assert r.json()["revoked_devices"] >= 2

    # 旧 token 全失效，旧密码登不上，新密码可以
    assert client.get("/api/v1/me", headers=h(phone)).status_code == 401
    assert client.get("/api/v1/me", headers=h(tablet)).status_code == 401
    assert client.post("/api/v1/auth/login", json={"username": "staff_02", "pin": "123456"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"username": "staff_02", "pin": "222222"}).status_code == 200


def test_last_admin_cannot_be_demoted(client, admin):
    users = client.get("/api/v1/admin/users", headers=h(admin["token"])).json()
    admins = [u for u in users if u["role"] == "admin"]
    assert len(admins) == 1  # 本模块只造了一个管理员

    r = client.patch(
        f"/api/v1/admin/users/{admins[0]['id']}", json={"role": "user"}, headers=h(admin["token"])
    )
    assert r.status_code == 422
    assert r.json()["detail"] == "至少要保留一个管理员"

    # 再提一个管理员之后就能降了；降完再升回来，保持后续用例的主动权
    promoted = client.post(
        "/api/v1/admin/users",
        json={"username": "admin_two", "pin": "123456", "role": "admin"},
        headers=h(admin["token"]),
    )
    assert promoted.status_code == 200
    second_id = promoted.json()["id"]
    first_id = admins[0]["id"]

    assert (
        client.patch(f"/api/v1/admin/users/{second_id}", json={"role": "user"}, headers=h(admin["token"])).status_code
        == 200
    )
    assert client.patch(f"/api/v1/admin/users/{second_id}", json={"role": "admin"}, headers=h(admin["token"])).status_code == 200
    assert client.patch(f"/api/v1/admin/users/{first_id}", json={"role": "admin"}, headers=h(admin["token"])).status_code == 200


# ---------------------------------------------------------------- 代用户看账 / 改账
def test_admin_txn_crud(client, admin):
    created = client.post(
        "/api/v1/admin/users",
        json={"username": "txn_user", "pin": "123456", "display_name": "记账用户"},
        headers=h(admin["token"]),
    ).json()
    uid = created["id"]
    m = client.get(f"/api/v1/admin/users/{uid}/meta", headers=h(admin["token"])).json()
    cat = next(c["id"] for c in m["categories"] if c["name"] == "餐饮")

    row = client.post(
        f"/api/v1/admin/users/{uid}/txns",
        json={"kind": "out", "amount_cents": 3200, "cat_id": cat, "note": "管理台代记一笔"},
        headers=h(admin["token"]),
    )
    assert row.status_code == 200, row.text
    txn = row.json()
    assert txn["amount_cents"] == 3200 and txn["client_uuid"]  # 服务端生成 uuid
    assert txn["book_id"]  # 没传就落到默认账本

    listing = client.get(f"/api/v1/admin/users/{uid}/txns", headers=h(admin["token"])).json()
    assert listing["total"] == 1 and len(listing["items"]) == 1

    patched = client.patch(
        f"/api/v1/admin/users/{uid}/txns/{txn['client_uuid']}",
        json={"amount_cents": 4500, "note": "改过了"},
        headers=h(admin["token"]),
    )
    assert patched.status_code == 200 and patched.json()["amount_cents"] == 4500

    bad = client.patch(
        f"/api/v1/admin/users/{uid}/txns/no-such-uuid", json={"note": "x"}, headers=h(admin["token"])
    )
    assert bad.status_code == 404

    assert (
        client.delete(
            f"/api/v1/admin/users/{uid}/txns/{txn['client_uuid']}", headers=h(admin["token"])
        ).status_code
        == 200
    )
    after = client.get(f"/api/v1/admin/users/{uid}/txns", headers=h(admin["token"])).json()
    assert after["total"] == 0


def test_admin_user_txns_date_filter(client, admin):
    users = client.get("/api/v1/admin/users", headers=h(admin["token"])).json()
    uid = next(u["id"] for u in users if u["username"] == "txn_user")
    r = client.get(
        f"/api/v1/admin/users/{uid}/txns",
        params={"from": "2026-01-01", "to": "2026-01-31", "limit": 10, "offset": 0},
        headers=h(admin["token"]),
    )
    assert r.status_code == 200
    assert r.json()["total"] == 0

    # to 是「含当天」：1 月 31 日 23:30 的账，查 to=2026-01-31 必须能查到
    late = client.post(
        f"/api/v1/admin/users/{uid}/txns",
        json={
            "kind": "out",
            "amount_cents": 900,
            "occurred_at": "2026-01-31T23:30:00",
            "note": "月末最后一笔",
        },
        headers=h(admin["token"]),
    )
    assert late.status_code == 200, late.text
    same_day = client.get(
        f"/api/v1/admin/users/{uid}/txns",
        params={"from": "2026-01-31", "to": "2026-01-31"},
        headers=h(admin["token"]),
    ).json()
    assert same_day["total"] == 1 and same_day["items"][0]["note"] == "月末最后一笔"

    # 换成 1 月 30 日就查不到
    prior_day = client.get(
        f"/api/v1/admin/users/{uid}/txns",
        params={"from": "2026-01-30", "to": "2026-01-30"},
        headers=h(admin["token"]),
    ).json()
    assert prior_day["total"] == 0

    bad = client.get(
        f"/api/v1/admin/users/{uid}/txns", params={"from": "2026/01/01"}, headers=h(admin["token"])
    )
    assert bad.status_code == 422  # 日期格式由 Query pattern 拦下


# ---------------------------------------------------------------- AI 画像
def test_admin_ai_profile_get_and_put(client, admin):
    users = client.get("/api/v1/admin/users", headers=h(admin["token"])).json()
    uid = next(u["id"] for u in users if u["username"] == "txn_user")

    before = client.get(f"/api/v1/admin/users/{uid}/ai-profile", headers=h(admin["token"])).json()
    assert before["hints"] == "" and before["version"] == 0

    put = client.put(
        f"/api/v1/admin/users/{uid}/ai-profile",
        json={"hints": "外卖一律餐饮\n打车归交通"},
        headers=h(admin["token"]),
    )
    assert put.status_code == 200, put.text
    assert put.json()["version"] == before["version"] + 1

    after = client.get(f"/api/v1/admin/users/{uid}/ai-profile", headers=h(admin["token"])).json()
    assert after["hints"] == "外卖一律餐饮\n打车归交通"

    too_long = client.put(
        f"/api/v1/admin/users/{uid}/ai-profile", json={"hints": "字" * 501}, headers=h(admin["token"])
    )
    assert too_long.status_code == 422 and "500" in too_long.json()["detail"]


def test_self_ai_profile_put(client):
    token = register_or_login(client, "profile_self")
    r = client.put("/api/v1/ai/profile", json={"hints": "咖啡归餐饮"}, headers=h(token))
    assert r.status_code == 200, r.text
    assert r.json()["hints"] == "咖啡归餐饮" and r.json()["version"] == 1
    assert client.put("/api/v1/ai/profile", json={"hints": "字" * 501}, headers=h(token)).status_code == 422


# ---------------------------------------------------------------- CSV 导入 / 导出
def test_admin_csv_import_and_export(client, admin):
    users = client.get("/api/v1/admin/users", headers=h(admin["token"])).json()
    uid = next(u["id"] for u in users if u["username"] == "txn_user")

    csv_bytes = (
        "\ufeff时间,金额,收支,分类,资产账户,账本,货币,备注\n"
        "2026-09-01 12:00:00,25.5,支出,餐饮,微信,日常账本,人民币,午饭\n"
        "2026-09-02 09:00:00,8000,收入,工资,建行,日常账本,人民币,发薪\n"
    ).encode("utf-8")
    r = client.post(
        f"/api/v1/admin/users/{uid}/import/csv",
        files={"file": ("ledger.csv", io.BytesIO(csv_bytes), "text/csv")},
        headers=h(admin["token"]),
    )
    assert r.status_code == 200, r.text
    assert r.json()["imported"] == 2

    out = client.get(
        f"/api/v1/admin/users/{uid}/export.csv",
        params={"from": "2026-09-01", "to": "2026-09-30"},
        headers=h(admin["token"]),
    )
    assert out.status_code == 200
    text_body = out.text
    assert text_body.splitlines()[0].lstrip("\ufeff") == "时间,金额,收支,分类,资产账户,账本,货币,备注"
    assert "午饭" in text_body and "25.5" in text_body

    # 非管理员不能导别人的账
    plain = register_or_login(client, "plain_user")
    assert (
        client.get(
            f"/api/v1/admin/users/{uid}/export.csv",
            params={"from": "2026-09-01", "to": "2026-09-30"},
            headers=h(plain),
        ).status_code
        == 403
    )


# ---------------------------------------------------------------- 越权 / 不存在
def test_unknown_user_404(client, admin):
    for path in ("/meta", "/txns", "/ai-profile"):
        assert client.get(f"/api/v1/admin/users/999999{path}", headers=h(admin["token"])).status_code == 404
    r = client.patch("/api/v1/admin/users/999999", json={"display_name": "x"}, headers=h(admin["token"]))
    assert r.status_code == 404
    assert r.json()["detail"] == "没有这个用户"


def test_admin_endpoints_require_token(client):
    assert client.get("/api/v1/admin/users").status_code == 401


# ---------------------------------------------------------------- 老库补列
def test_ensure_schema_adds_role_column(tmp_path):
    """老库（users 表没有 role 列）启动时要能自动补列，且可重入。"""
    from sqlalchemy import create_engine

    db_file = tmp_path / "legacy.db"
    legacy = create_engine(f"sqlite:///{db_file}")
    with legacy.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE users ("
                "id INTEGER PRIMARY KEY, username VARCHAR(32) UNIQUE, display_name VARCHAR(32), "
                "pin_hash VARCHAR(200), created_at DATETIME)"
            )
        )
        conn.execute(text("INSERT INTO users (username, pin_hash) VALUES ('old', 'x')"))

    assert "role" not in {c["name"] for c in inspect(legacy).get_columns("users")}
    applied = ensure_schema(legacy)
    assert applied == ["ALTER TABLE users ADD COLUMN role VARCHAR(16) NOT NULL DEFAULT 'user'"]
    assert "role" in {c["name"] for c in inspect(legacy).get_columns("users")}

    with legacy.begin() as conn:
        assert conn.execute(text("SELECT role FROM users WHERE username='old'")).scalar() == "user"

    # 再跑一次不重复 ALTER（可重入）
    assert ensure_schema(legacy) == []
    legacy.dispose()

    # 临时库文件由 pytest 的 tmp_path 自动回收
    assert db_file.exists()
