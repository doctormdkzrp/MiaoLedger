"""AI 学习闭环测试：绝不真实请求大模型（一律 monkeypatch），跑在临时 SQLite 上。

运行：  python -m pytest -q server/tests/test_ai_learning.py
"""
import os
import sys

import pytest

# 用自己的临时库，避免和 test_api.py / 其他人的库打架；pytest 结束时删掉。
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_ai_tmp.db")
os.environ.setdefault("INVITE_CODE", "testcode")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

import app.ai as ai_mod  # noqa: E402
import app.learning as learning  # noqa: E402
from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c
    engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def _cleanup_test_db():
    """整轮测试结束后删掉临时库（test_api.py 共用这个库）。"""
    yield
    engine.dispose()
    for path in ("test_ai_tmp.db",):
        try:
            os.remove(path)
        except OSError:
            pass


def h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def register(c, username: str, pin: str = "123456") -> str:
    r = c.post(
        "/api/v1/auth/register",
        json={"username": username, "pin": pin, "invite_code": "testcode", "display_name": username},
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


def meta(c, token: str) -> dict:
    return c.get("/api/v1/meta", headers=h(token)).json()


def cat_id(m: dict, name: str) -> int:
    return next(c["id"] for c in m["categories"] if c["name"] == name)


def acct_id(m: dict, name: str) -> int:
    return next(a["id"] for a in m["accounts"] if a["name"] == name)


def parse(c, token: str, text: str, now: str = "2026-11-12T12:00:00") -> dict:
    r = c.post("/api/v1/ai/parse", json={"text": text, "now": now}, headers=h(token))
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------- 解析 + 新分类建议


def test_parse_no_key_suggests_new_category(client, monkeypatch):
    """没有 API key 时走本地规则，拿不准的新商户给 suggest_category。"""
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    token = register(client, "ai_new")
    d = parse(client, token, "Open Code 的 Go 订阅 67.24")
    assert d["amount_cents"] == 6724
    assert d["cat_name"] is None  # 本地规则归不进任何分类
    assert d["suggest_category"] == {"name": "Open Code", "kind": "out", "icon": "🏷"}
    assert "category" in d["needs"]
    assert d["raw"]["engine"] == "rules"


def test_parse_uses_model_result_when_available(client, monkeypatch):
    """模型路径：只把结构化结果映射到本地分类/账户，不真实发请求。"""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy-key")

    def fake_model(text, now, cats, accts, *, hints="", rules=None):
        return {
            "kind": "out",
            "amount": 88.5,
            "category": "餐饮",
            "account": "微信",
            "occurred_at": "2026-11-12T12:00:00",
            "note": "和同事吃饭",
            "confidence": 0.9,
        }

    monkeypatch.setattr(ai_mod, "_call_model", fake_model)
    token = register(client, "ai_model")
    d = parse(client, token, "跟同事吃饭 88.5 微信")
    assert d["raw"]["engine"] == "model"
    assert d["amount_cents"] == 8850
    assert d["cat_name"] == "餐饮"
    assert d["account_name"] == "微信"


# ---------------------------------------------------------------- 验收主路径


def test_new_category_then_learned_across_brands(client, monkeypatch):
    """说 Open Code → 新建「AI 研究」→ 说 Commander Code 自动归 AI 研究。"""
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    token = register(client, "ai_family")
    m = meta(client, token)

    first = parse(client, token, "Open Code 的 Go 订阅 67.24")
    assert first["cat_id"] is None and first["suggest_category"]["name"] == "Open Code"

    r = client.post(
        "/api/v1/ai/feedback",
        json={
            "text": "Open Code 的 Go 订阅 67.24",
            "parsed": {"cat_id": first["cat_id"], "account_id": first["account_id"]},
            "final": {},
            "new_category": {"name": "AI 研究", "kind": "out", "icon": "🤖"},
        },
        headers=h(token),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    learned = body["learned"]
    assert learned and learned[0]["kind"] == "category"
    assert learned[0]["pattern"] == "open code"
    assert learned[0]["target_name"] == "AI 研究"

    # 新分类已经建出来（App 的 meta 里能看到）
    m2 = meta(client, token)
    assert "AI 研究" in {c["name"] for c in m2["categories"]}

    # 换个牌子（Commander Code / OpenCode）也要认出来，且不再问模型
    second = parse(client, token, "Commander Code GOAT 订阅 67")
    assert second["cat_name"] == "AI 研究"
    assert second["raw"]["engine"] == "learned"
    assert second["raw"]["learned_rule"] == "open code"
    assert second["amount_cents"] == 6700

    third = parse(client, token, "OpenCode 充值 100")
    assert third["cat_name"] == "AI 研究"

    rules = client.get("/api/v1/ai/rules", headers=h(token)).json()["rules"]
    assert len(rules) == 1
    assert rules[0]["weight"] == 2 and rules[0]["hits"] == 1


def test_correction_learns_after_second_hit(client, monkeypatch):
    """普通纠错 weight 从 1 开始：一次只做提示，两次才直接定类。"""
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    token = register(client, "ai_correct")
    m = meta(client, token)
    other = cat_id(m, "其它")
    food = cat_id(m, "餐饮")

    def feedback(parsed_cat, final_cat):
        r = client.post(
            "/api/v1/ai/feedback",
            json={
                "text": "美发店理发 28",
                "parsed": {"cat_id": parsed_cat},
                "final": {"cat_id": final_cat},
            },
            headers=h(token),
        )
        assert r.status_code == 200, r.text
        return r.json()

    body = feedback(other, food)
    assert body["learned"][0]["weight"] == 1
    # weight=1 不直接定类（本地规则仍归不进拉面）
    assert parse(client, token, "美发店理发 30")["cat_name"] is None

    body = feedback(other, food)
    assert body["learned"][0]["weight"] == 2
    learned = parse(client, token, "美发店理发 30")
    assert learned["cat_name"] == "餐饮"
    assert learned["raw"]["learned_rule"] == "美发店理发"


def test_account_correction_learns(client, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    token = register(client, "ai_acct")
    m = meta(client, token)
    wx = acct_id(m, "微信")
    alipay = acct_id(m, "支付宝")
    for _ in range(2):
        r = client.post(
            "/api/v1/ai/feedback",
            json={
                "text": "Open Code 订阅 100",
                "parsed": {"account_id": wx},
                "final": {"account_id": alipay},
            },
            headers=h(token),
        )
        assert r.status_code == 200, r.text
    d = parse(client, token, "Open Code 订阅 120")
    assert d["account_name"] == "支付宝"


# ---------------------------------------------------------------- 画像


def test_profile_compressed_every_ten_feedback(client, monkeypatch):
    """每累计 10 条反馈压一次画像（模型用固定文本替代，不真请求）。"""
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    token = register(client, "ai_profile")
    m = meta(client, token)
    food = cat_id(m, "餐饮")
    calls = []

    def fake_profile(prompt):
        calls.append(prompt)
        return "AI 工具订阅都归 AI 研究\n吃饭一律归餐饮"

    monkeypatch.setattr(learning, "_call_profile_model", fake_profile)
    for i in range(10):
        r = client.post(
            "/api/v1/ai/feedback",
            json={
                "text": f"美发店理发 {i + 1}",
                "parsed": {"cat_id": cat_id(m, "其它")},
                "final": {"cat_id": food},
            },
            headers=h(token),
        )
        assert r.status_code == 200, r.text
        if i < 9:
            assert calls == []  # 不满 10 条不调模型

    assert len(calls) == 1
    p = client.get("/api/v1/ai/profile", headers=h(token)).json()
    assert p["feedback_count"] == 10
    assert p["version"] == 1
    assert "AI 研究" in p["hints"] and "餐饮" in p["hints"]


def test_profile_falls_back_when_model_fails(client, monkeypatch):
    """画像模型失败/没 key 时退化为拼接文本，反馈接口绝不 500。"""
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    token = register(client, "ai_fallback")
    m = meta(client, token)
    monkeypatch.setattr(learning, "_call_profile_model", lambda prompt: None)
    for i in range(10):
        r = client.post(
            "/api/v1/ai/feedback",
            json={
                "text": f"美发店理发 {i + 1}",
                "parsed": {"cat_id": cat_id(m, "其它")},
                "final": {"cat_id": cat_id(m, "餐饮")},
            },
            headers=h(token),
        )
        assert r.status_code == 200, r.text
    p = client.get("/api/v1/ai/profile", headers=h(token)).json()
    assert "→ 餐饮" in p["hints"]
    assert p["version"] == 1


# ---------------------------------------------------------------- 隔离 / 越权


def test_rules_and_profile_isolated_between_accounts(client, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    first = register(client, "ai_owner")
    second = register(client, "ai_other")

    for _ in range(2):
        client.post(
            "/api/v1/ai/feedback",
            json={
                "text": "Open Code 的 Go 订阅 67.24",
                "parsed": {"cat_id": None},
                "final": {},
                "new_category": {"name": "AI 研究", "kind": "out", "icon": "🤖"},
            },
            headers=h(first),
        )

    h_rules = client.get("/api/v1/ai/rules", headers=h(first)).json()["rules"]
    assert h_rules
    assert client.get("/api/v1/ai/rules", headers=h(second)).json()["rules"] == []

    # 另一个账号说同样的话，不会被别人的规则影响
    d = parse(client, second, "Commander Code GOAT 订阅 67")
    assert d["cat_name"] != "AI 研究"
    assert "learned_rule" not in (d["raw"] or {})

    # 看别人的画像：空
    wp = client.get("/api/v1/ai/profile", headers=h(second)).json()
    assert wp["hints"] == "" and wp["version"] == 0

    # 越权删规则 → 404
    rid = h_rules[0]["id"]
    assert client.delete(f"/api/v1/ai/rules/{rid}", headers=h(second)).status_code == 404
    assert client.delete("/api/v1/ai/rules/999999", headers=h(first)).status_code == 404
    # 本人的规则还在，删自己的可以
    assert client.delete(f"/api/v1/ai/rules/{rid}", headers=h(first)).status_code == 200
    assert client.get("/api/v1/ai/rules", headers=h(first)).json()["rules"] == []
    assert parse(client, first, "Commander Code GOAT 订阅 67")["cat_name"] is None


def test_ai_endpoints_require_token(client):
    for method, path in (
        ("post", "/api/v1/ai/parse"),
        ("post", "/api/v1/ai/feedback"),
        ("get", "/api/v1/ai/rules"),
        ("get", "/api/v1/ai/profile"),
    ):
        r = getattr(client, method)(path, json={"text": "x"}) if method == "post" else getattr(client, method)(path)
        assert r.status_code == 401
    assert client.delete("/api/v1/ai/rules/1").status_code == 401


# ---------------------------------------------------------------- 提示词注入


def test_profile_and_rules_injected_into_prompt(client, monkeypatch):
    """解析时把该账号的画像和规则注入提示词（用假模型截获参数，不真请求）。"""
    token = register(client, "ai_prompt")
    m = meta(client, token)
    learned_ok = []

    def fake_model(text, now, cats, accts, *, hints="", rules=None):
        learned_ok.append({"hints": hints, "rules": list(rules or [])})
        return None

    monkeypatch.setattr(ai_mod, "_call_model", fake_model)

    # 先造一条 weight=2 的规则和一段画像
    for _ in range(2):
        client.post(
            "/api/v1/ai/feedback",
            json={
                "text": "Open Code 订阅 100",
                "parsed": {"cat_id": None},
                "final": {},
                "new_category": {"name": "AI 研究", "kind": "out", "icon": "🤖"},
            },
            headers=h(token),
        )
    monkeypatch.setattr(learning, "_call_profile_model", lambda prompt: "AI 工具订阅归 AI 研究")
    for i in range(10):
        client.post(
            "/api/v1/ai/feedback",
            json={
                "text": f"买菜 {i + 1}",
                "parsed": {"cat_id": cat_id(m, "其它")},
                "final": {"cat_id": cat_id(m, "餐饮")},
            },
            headers=h(token),
        )

    parse(client, token, "买了个水杯 59")  # 不命中 weight>=2 规则，会走模型
    assert learned_ok
    assert "AI 研究" in learned_ok[-1]["hints"]
    pats = {r.pattern for r in learned_ok[-1]["rules"]}
    assert "open code" in pats

