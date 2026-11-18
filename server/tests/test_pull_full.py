"""WO-01 下行恢复：GET /api/v1/txns 的整库分页拉取（full=1）。

职责边界：
- 不带 full 的老调用必须还是裸列表（老客户端和老用例都靠这个）。
- 带 full=1 才返回 {"items","next_cursor","total"}，软删的笔也要回来并带 deleted=true。
- 游标是 updated_at + client_uuid 复合的，翻页期间不重不漏。

跑在独立临时 SQLite 上（test_pull_tmp.db），整轮结束由 conftest 删掉。
"""
from datetime import datetime, timedelta

import os
import sys

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_pull_tmp.db")
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


def register(client, name):
    r = client.post(
        "/api/v1/auth/register",
        json={"username": name, "pin": "123456", "invite_code": "testcode", "display_name": name},
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


def meta(client, token):
    return client.get("/api/v1/meta", headers=h(token)).json()


def push(client, token, uuid, cents=1000, note="", occurred_at=None):
    m = meta(client, token)
    body = {
        "txns": [
            {
                "client_uuid": uuid,
                "book_id": m["books"][0]["id"],
                "cat_id": m["categories"][0]["id"],
                "account_id": m["accounts"][0]["id"],
                "kind": "out",
                "amount_cents": cents,
                "occurred_at": occurred_at or "2026-11-05T12:30:00",
                "note": note,
            }
        ]
    }
    r = client.post("/api/v1/txns", json=body, headers=h(token))
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------- 老行为不许变
def test_without_full_still_returns_bare_list(client):
    """老客户端不带 full：拿到的还是裸列表，一个字段都不多。"""
    token = register(client, "pull_legacy")
    push(client, token, "legacy-uuid-0001", 1000)
    push(client, token, "legacy-uuid-0002", 2000)

    r = client.get("/api/v1/txns", headers=h(token))
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, list), "不带 full 必须仍返回裸列表"
    assert len(data) == 2
    assert {x["client_uuid"] for x in data} == {"legacy-uuid-0001", "legacy-uuid-0002"}

    # include_deleted=False 的老语义照旧
    visible = client.get("/api/v1/txns", headers=h(token), params={"include_deleted": False}).json()
    assert len(visible) == 2


def test_full_returns_paged_object(client):
    token = register(client, "pull_full_shape")
    push(client, token, "shape-uuid-0001", 1000)

    r = client.get("/api/v1/txns", headers=h(token), params={"full": 1})
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, dict)
    assert set(data) == {"items", "next_cursor", "total"}
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["next_cursor"] is None  # 一页就拉完了
    assert data["items"][0]["client_uuid"] == "shape-uuid-0001"


# ---------------------------------------------------------------- 分页不重不漏
def test_pagination_no_duplicate_no_missing(client):
    """5 笔、每页 2 笔：翻完必须恰好 5 笔，不重不漏，最后一页 next_cursor 为空。"""
    token = register(client, "pull_paging")
    uuids = [f"page-uuid-{i:04d}" for i in range(5)]
    for i, u in enumerate(uuids):
        push(client, token, u, 100 * (i + 1))

    seen = []
    cursor = None
    pages = 0
    while True:
        params = {"full": 1, "limit": 2}
        if cursor:
            params["cursor"] = cursor
        r = client.get("/api/v1/txns", headers=h(token), params=params)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["total"] == 5  # 每页都报同一个总数，客户端才能显示进度
        seen.extend(x["client_uuid"] for x in data["items"])
        pages += 1
        cursor = data["next_cursor"]
        if not cursor:
            break
        assert pages < 10, "游标没往前走，翻页死循环了"

    assert pages == 3
    assert len(seen) == 5
    assert len(set(seen)) == 5, f"翻页出现重复：{seen}"
    assert set(seen) == set(uuids)


def test_cursor_is_opaque_and_order_is_stable(client):
    """游标是不透明字符串（base64），且按 updated_at+client_uuid 稳定排序。"""
    token = register(client, "pull_cursor")
    for i in range(3):
        push(client, token, f"cur-uuid-{i:04d}", 1000 + i)

    first = client.get("/api/v1/txns", headers=h(token), params={"full": 1, "limit": 2}).json()
    assert isinstance(first["next_cursor"], str)
    assert "|" not in first["next_cursor"], "游标不能把内部格式露给客户端"

    second = client.get(
        "/api/v1/txns", headers=h(token), params={"full": 1, "limit": 2, "cursor": first["next_cursor"]}
    ).json()
    # 两页拼起来必须严格按 (updated_at, client_uuid) 升序
    keys = [(x["updated_at"], x["client_uuid"]) for x in first["items"] + second["items"]]
    assert keys == sorted(keys)


def test_bad_cursor_is_422(client):
    token = register(client, "pull_badcursor")
    r = client.get("/api/v1/txns", headers=h(token), params={"full": 1, "cursor": "这不是游标"})
    assert r.status_code == 422


def test_full_limit_capped_at_1000(client):
    token = register(client, "pull_limit")
    assert client.get("/api/v1/txns", headers=h(token), params={"full": 1, "limit": 1000}).status_code == 200
    assert client.get("/api/v1/txns", headers=h(token), params={"full": 1, "limit": 1001}).status_code == 422


# ---------------------------------------------------------------- 软删要回来
def test_soft_deleted_rows_come_back_with_flag(client):
    """软删的笔必须回来并带 deleted=true，客户端才有依据删本地行。"""
    token = register(client, "pull_deleted")
    push(client, token, "del-uuid-0001", 1000)
    push(client, token, "del-uuid-0002", 2000)
    assert client.delete("/api/v1/txns/del-uuid-0001", headers=h(token)).status_code == 200

    data = client.get("/api/v1/txns", headers=h(token), params={"full": 1}).json()
    assert data["total"] == 2, "软删的笔也算在总数里"
    by_uuid = {x["client_uuid"]: x for x in data["items"]}
    assert by_uuid["del-uuid-0001"]["deleted"] is True
    assert by_uuid["del-uuid-0002"]["deleted"] is False

    # 老参数 include_deleted=False 时不该看到软删的
    visible = client.get(
        "/api/v1/txns", headers=h(token), params={"full": 1, "include_deleted": False}
    ).json()
    assert visible["total"] == 1
    assert [x["client_uuid"] for x in visible["items"]] == ["del-uuid-0002"]


# ---------------------------------------------------------------- 隔离与 since
def test_full_only_sees_own_rows(client):
    """别人的账不能出现在 total 和 items 里。"""
    mine = register(client, "pull_mine")
    other = register(client, "pull_other")
    push(client, mine, "mine-uuid-0001", 1000)
    push(client, other, "other-uuid-0001", 2000)
    push(client, other, "other-uuid-0002", 3000)

    data = client.get("/api/v1/txns", headers=h(token := mine), params={"full": 1}).json()
    assert data["total"] == 1
    assert [x["client_uuid"] for x in data["items"]] == ["mine-uuid-0001"]


def test_since_still_works_with_full(client):
    """since 是增量同步在用的参数，加了 full 也不能改变它的含义。"""
    token = register(client, "pull_since")
    push(client, token, "since-uuid-0001", 1000)

    future = (datetime.now() + timedelta(days=1)).isoformat(timespec="seconds")
    data = client.get("/api/v1/txns", headers=h(token), params={"full": 1, "since": future}).json()
    assert data["total"] == 0 and data["items"] == []

    past = (datetime.now() - timedelta(days=1)).isoformat(timespec="seconds")
    data = client.get("/api/v1/txns", headers=h(token), params={"full": 1, "since": past}).json()
    assert data["total"] == 1
