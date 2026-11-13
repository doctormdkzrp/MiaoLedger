"""端到端接口测试：跑在临时 SQLite 上，不碰真库。

运行：  python -m pytest -q
"""
import io
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


@pytest.fixture(scope="module")
def token(client):
    r = client.post(
        "/api/v1/auth/register",
        json={"username": "demo", "pin": "123456", "invite_code": "testcode", "display_name": "演示账号"},
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


def h(token):
    return {"Authorization": f"Bearer {token}"}


def test_health(client):
    assert client.get("/health").json()["ok"] is True


def test_wrong_invite_code(client):
    r = client.post("/api/v1/auth/register", json={"username": "x", "pin": "123456", "invite_code": "bad"})
    assert r.status_code == 403


def test_login_and_me(client, token):
    r = client.post("/api/v1/auth/login", json={"username": "demo", "pin": "123456"})
    assert r.status_code == 200
    me = client.get("/api/v1/me", headers=h(token)).json()
    assert me["username"] == "demo"
    assert me["role"] == "user"
    assert me["books"] == 1 and me["accounts"] == 4 and me["categories"] == 15


def test_meta_seeded(client, token):
    m = client.get("/api/v1/meta", headers=h(token)).json()
    assert [b["name"] for b in m["books"]] == ["日常账本"]
    assert {"餐饮", "育儿", "赡养"} <= {c["name"] for c in m["categories"]}
    assert {"微信", "支付宝", "建行", "现金"} <= {a["name"] for a in m["accounts"]}


def test_push_idempotent(client, token):
    m = client.get("/api/v1/meta", headers=h(token)).json()
    book = m["books"][0]["id"]
    cat = next(c["id"] for c in m["categories"] if c["name"] == "餐饮")
    acct = next(a["id"] for a in m["accounts"] if a["name"] == "微信")
    body = {
        "txns": [
            {
                "client_uuid": "uuid-aaaa-0001",
                "book_id": book,
                "cat_id": cat,
                "account_id": acct,
                "kind": "out",
                "amount_cents": 6800,
                "occurred_at": "2026-11-05T12:30:00",
                "note": "和同事吃饭 AA",
            }
        ]
    }
    r1 = client.post("/api/v1/txns", json=body, headers=h(token)).json()
    assert r1["created"] == 1
    r2 = client.post("/api/v1/txns", json=body, headers=h(token)).json()
    assert r2["created"] == 0 and r2["updated"] == 1

    rows = client.get("/api/v1/txns", headers=h(token)).json()
    assert len([x for x in rows if x["client_uuid"] == "uuid-aaaa-0001"]) == 1
    assert rows[0]["amount_cents"] == 6800


def test_patch_txn(client, token):
    """PATCH 只改传上来的字段，其余保持原值。"""
    r = client.patch(
        "/api/v1/txns/uuid-aaaa-0001",
        json={"amount_cents": 7500, "note": "改成 75"},
        headers=h(token),
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["amount_cents"] == 7500
    assert d["note"] == "改成 75"
    assert d["kind"] == "out"  # 没传的字段不变
    assert d["client_uuid"] == "uuid-aaaa-0001"

    assert client.patch("/api/v1/txns/no-such-uuid", json={"note": "x"}, headers=h(token)).status_code == 404
    assert client.patch("/api/v1/txns/uuid-aaaa-0001", json={"kind": "bad"}, headers=h(token)).status_code == 422

    # 改回去，后面的统计断言依赖 6800
    back = client.patch(
        "/api/v1/txns/uuid-aaaa-0001", json={"amount_cents": 6800, "note": "和同事吃饭 AA"}, headers=h(token)
    )
    assert back.json()["amount_cents"] == 6800


def test_isolation_between_users(client, token):
    r = client.post(
        "/api/v1/auth/register",
        json={"username": "test_1", "pin": "654321", "invite_code": "testcode", "display_name": "测试账号"},
    )
    assert r.status_code == 200
    token2 = r.json()["token"]
    rows2 = client.get("/api/v1/txns", headers=h(token2)).json()
    assert rows2 == []  # 另一个账号看不到 demo 的账


def test_summary_and_export(client, token):
    s = client.get("/api/v1/summary", params={"month": "2026-11"}, headers=h(token)).json()
    assert s["out_cents"] == 6800
    assert s["by_category"][0]["name"] == "餐饮"

    csv_text = client.get(
        "/api/v1/export.csv", params={"from": "2026-11-01", "to": "2026-11-30"}, headers=h(token)
    ).text
    assert csv_text.splitlines()[0].lstrip("\ufeff") == "时间,金额,收支,分类,资产账户,账本,货币,备注"
    assert "餐饮" in csv_text and "和同事吃饭 AA" in csv_text


def test_import_csv(client, token):
    csv_bytes = (
        "\ufeff时间,金额,收支,分类,资产账户,账本,货币,备注\n"
        "2026-08-31 19:27:56,33,支出,餐饮,不计入账户,默认账本,人民币,晚餐消费\n"
        "2026-08-31 12:24:36,18.8,支出,餐饮,不计入账户,默认账本,人民币,午餐\n"
        "2026-08-30 09:00:00,12800,收入,工资,建行,默认账本,人民币,发工资\n"
    ).encode("utf-8")
    r = client.post(
        "/api/v1/import/csv",
        files={"file": ("ledger.csv", io.BytesIO(csv_bytes), "text/csv")},
        headers=h(token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["imported"] == 3

    # 再导一次不能重复
    r2 = client.post(
        "/api/v1/import/csv",
        files={"file": ("ledger.csv", io.BytesIO(csv_bytes), "text/csv")},
        headers=h(token),
    )
    assert r2.json()["imported"] == 0 and r2.json()["skipped"] == 3

    s = client.get("/api/v1/summary", params={"month": "2026-08"}, headers=h(token)).json()
    assert s["out_cents"] == 5180
    assert s["in_cents"] == 1280000


def test_import_csv_dedupes_duplicate_rows(client, token):
    """同一个文件里有两行一模一样（同时间/同金额/同备注），第二行也要跳过，不能撞唯一索引 500。"""
    csv_bytes = (
        "\ufeff时间,金额,收支,分类,资产账户,账本,货币,备注\n"
        "2026-07-02 08:00:00,12,支出,餐饮,现金,默认账本,人民币,同一条\n"
        "2026-07-02 08:00:00,12,支出,餐饮,现金,默认账本,人民币,同一条\n"
        "2026-07-02 09:00:00,15,支出,餐饮,现金,默认账本,人民币,另一条\n"
    ).encode("utf-8")
    r = client.post(
        "/api/v1/import/csv",
        files={"file": ("dupe.csv", io.BytesIO(csv_bytes), "text/csv")},
        headers=h(token),
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"imported": 2, "skipped": 1}


def test_asr_without_key_returns_503(client, token, monkeypatch):
    """没配 VOLC_API_KEY 时 /asr 必须明确 503，而不是 400/502 或 500。"""
    monkeypatch.delenv("VOLC_API_KEY", raising=False)
    wav = b"RIFF" + b"\x00" * 4096
    r = client.post(
        "/api/v1/asr",
        files={"file": ("voice.wav", io.BytesIO(wav), "audio/wav")},
        headers=h(token),
    )
    assert r.status_code == 503, r.text
    assert "语音识别" in r.json()["detail"]


def test_ai_parse_fallback_rules(client, token, monkeypatch):
    """没有 API key 时走本地规则，也要能抠出金额/分类/账户。"""
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    r = client.post(
        "/api/v1/ai/parse",
        json={"text": "昨天中午跟同事吃饭 AA 68，用微信", "now": "2026-11-06T21:00:00"},
        headers=h(token),
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["amount_cents"] == 6800
    assert d["cat_name"] == "餐饮"
    assert d["account_name"] == "微信"
    assert d["occurred_at"].startswith("2026-11-05T12:00")
    assert d["raw"]["engine"] == "rules"


def test_ai_parse_needs_when_no_amount(client, token, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    d = client.post("/api/v1/ai/parse", json={"text": "买了点水果"}, headers=h(token)).json()
    assert "amount" in d["needs"]
    assert d["confidence"] <= 0.5
