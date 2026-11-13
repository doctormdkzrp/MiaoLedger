"""0.6.0 账号能力测试：改密码 / 清空账单 / 删分类 / AI 记忆展示。

- 跑在独立临时 SQLite 上（test_account_tmp.db），整轮结束删掉库文件。
- 绝不真实请求大模型：只 stubbing 不了的地方一律不碰网络（_build_prompt 是纯函数）。

运行：python -m pytest -q server/tests/test_account_api.py
"""
import os
import sys

import pytest

# 用独立临时库，避免和 test_api.py / 别人的库打架；pytest 结束时删掉。
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_account_tmp.db")
os.environ.setdefault("INVITE_CODE", "testcode")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402

TMP_DB = "test_account_tmp.db"


@pytest.fixture(scope="module")
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c
    engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def _cleanup_test_db():
    yield
    engine.dispose()
    for path in (TMP_DB, TMP_DB + "-journal", TMP_DB + "-wal", TMP_DB + "-shm"):
        try:
            os.remove(path)
        except OSError:
            pass


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


def login(c, username: str, pin: str, device: str = "second-phone"):
    return c.post(
        "/api/v1/auth/login",
        json={"username": username, "pin": pin, "device_name": device},
    )


def meta(c, token: str) -> dict:
    r = c.get("/api/v1/meta", headers=h(token))
    assert r.status_code == 200, r.text
    return r.json()


def push_one(c, token: str, uuid: str, cents: int = 1000, cat_id=None) -> None:
    r = c.post(
        "/api/v1/txns",
        headers=h(token),
        json={
            "txns": [
                {
                    "client_uuid": uuid,
                    "cat_id": cat_id,
                    "kind": "out",
                    "amount_cents": cents,
                    "occurred_at": "2026-11-12T12:00:00",
                    "note": "测试",
                    "source": "manual",
                }
            ]
        },
    )
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------- 改密码
def test_change_pin_success_revokes_other_devices(client):
    token_a = register(client, "pinuser")
    other = login(client, "pinuser", "123456").json()["token"]

    r = client.post("/api/v1/auth/change-pin", headers=h(token_a), json={"old_pin": "123456", "new_pin": "654321"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True and body["revoked_devices"] == 1

    # 当前这台还能用，另一台被踢掉
    assert client.get("/api/v1/me", headers=h(token_a)).status_code == 200
    assert client.get("/api/v1/me", headers=h(other)).status_code == 401

    # 旧密码登不上，新密码能登
    assert login(client, "pinuser", "123456").status_code == 401
    assert login(client, "pinuser", "654321").status_code == 200


def test_change_pin_wrong_old_pin_401(client):
    token = register(client, "pinwrong")
    r = client.post("/api/v1/auth/change-pin", headers=h(token), json={"old_pin": "000000", "new_pin": "111111"})
    assert r.status_code == 401
    assert r.json()["detail"] == "现在的密码不对"


def test_change_pin_bad_new_format_422(client):
    token = register(client, "pinformat")
    for bad in ("12345", "1234567", "abcdef", "12 345", ""):
        r = client.post("/api/v1/auth/change-pin", headers=h(token), json={"old_pin": "123456", "new_pin": bad})
        assert r.status_code == 422, (bad, r.text)
        assert r.json()["detail"] == "新密码要正好 6 位数字"


def test_change_pin_same_as_old_422(client):
    token = register(client, "pinsame")
    r = client.post("/api/v1/auth/change-pin", headers=h(token), json={"old_pin": "123456", "new_pin": "123456"})
    assert r.status_code == 422
    assert r.json()["detail"] == "新密码和现在的密码一样"


def test_change_pin_requires_token(client):
    r = client.post("/api/v1/auth/change-pin", json={"old_pin": "123456", "new_pin": "654321"})
    assert r.status_code == 401


# ---------------------------------------------------------------- 清空账单
def test_wipe_txns_soft_deletes_all(client):
    token = register(client, "wipeuser")
    push_one(client, token, "wipe-uuid-0001", 1200)
    push_one(client, token, "wipe-uuid-0002", 3400)
    assert len(client.get("/api/v1/txns", headers=h(token), params={"include_deleted": False}).json()) == 2

    r = client.delete("/api/v1/txns/all", headers=h(token))
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "deleted": 2}

    # 可见账单为空；再同步一次 pull 也只拿到软删后的记录
    assert client.get("/api/v1/txns", headers=h(token), params={"include_deleted": False}).json() == []
    pulled = client.get("/api/v1/txns", headers=h(token), params={"include_deleted": True}).json()
    assert len(pulled) == 2 and all(item["deleted"] for item in pulled)
    assert client.get("/api/v1/me", headers=h(token)).json()["txns"] == 0

    # 再清一次：已经没了就是 0，不报错
    assert client.delete("/api/v1/txns/all", headers=h(token)).json() == {"ok": True, "deleted": 0}


def test_wipe_txns_does_not_touch_other_user(client):
    keep = register(client, "wipekeep")
    other = register(client, "wipeother")
    push_one(client, keep, "keep-uuid-0001", 800)
    push_one(client, other, "other-uuid-0001", 900)

    assert client.delete("/api/v1/txns/all", headers=h(keep)).json()["deleted"] == 1
    left = client.get("/api/v1/txns", headers=h(other), params={"include_deleted": False}).json()
    assert len(left) == 1 and left[0]["client_uuid"] == "other-uuid-0001"


def test_wipe_txns_requires_token(client):
    assert client.delete("/api/v1/txns/all").status_code == 401


# ---------------------------------------------------------------- 删分类
def test_delete_category_soft_deletes(client):
    token = register(client, "catuser")
    m = meta(client, token)
    target = next(c for c in m["categories"] if c["name"] == "烟酒")

    r = client.delete(f"/api/v1/categories/{target['id']}", headers=h(token))
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True}

    names = [c["name"] for c in meta(client, token)["categories"]]
    assert "烟酒" not in names

    # 已有账单引用的分类也允许删：历史账单保留原 id
    push_one(client, token, "cat-uuid-0001", 2500, cat_id=target["id"])
    r = client.delete(f"/api/v1/categories/{target['id']}", headers=h(token))
    assert r.status_code == 404  # 已经删过，再删就是 404


def test_delete_category_unknown_404(client):
    token = register(client, "catmiss")
    r = client.delete("/api/v1/categories/999999", headers=h(token))
    assert r.status_code == 404
    assert r.json()["detail"] == "没有这个分类"


def test_delete_category_other_user_404(client):
    owner = register(client, "catowner")
    intruder = register(client, "catintruder")
    target = next(c for c in meta(client, owner)["categories"] if c["name"] == "医疗")

    r = client.delete(f"/api/v1/categories/{target['id']}", headers=h(intruder))
    assert r.status_code == 404
    assert r.json()["detail"] == "没有这个分类"
    # 没被误删
    assert "医疗" in [c["name"] for c in meta(client, owner)["categories"]]


def test_delete_category_requires_token(client):
    assert client.delete("/api/v1/categories/1").status_code == 401


# ---------------------------------------------------------------- AI 记忆展示
def _learn_ai_research(client, token: str) -> None:
    """走真实反馈链路：说 Open Code → 新建「AI 研究」，让这个账号有一条规矩 + 画像。"""
    r = client.post(
        "/api/v1/ai/feedback",
        headers=h(token),
        json={
            "text": "Open Code 的 Go 订阅 67.24",
            "parsed": {"kind": "out"},
            "final": {"kind": "out"},
            "new_category": {"name": "AI 研究", "kind": "out", "icon": "🤖"},
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["learned"]


def _feedback_times(client, token: str, times: int) -> None:
    """再补几条无关反馈，把 feedback_count 推到 10 的倍数（画像这时才刷新）。"""
    for i in range(times):
        r = client.post(
            "/api/v1/ai/feedback",
            headers=h(token),
            json={"text": f"午饭 {20 + i}", "parsed": {"kind": "out"}, "final": {"kind": "out"}},
        )
        assert r.status_code == 200, r.text


def test_ai_memory_returns_real_prompt_and_rules(client, monkeypatch):
    # 就算环境里有 key，也绝不能出现在返回的提示词里；也不许真去请求大模型。
    import app.learning as learning

    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-abcdef123456SECRET")
    monkeypatch.setattr(learning, "_call_profile_model", lambda _prompt: None)  # 只走退化拼接

    token = register(client, "memuser")
    _learn_ai_research(client, token)
    _feedback_times(client, token, 9)  # 凑满 10 条：画像由规则退化拼接生成

    r = client.get("/api/v1/ai/memory", headers=h(token))
    assert r.status_code == 200, r.text
    body = r.json()

    assert set(body) >= {"prompt", "how", "hints", "rules", "stats"}
    assert body["how"] and "规矩" in body["how"]

    prompt = body["prompt"]
    assert prompt and len(prompt) <= 4000  # 契约：截断到 4000 字符（含截断说明）
    assert "家庭记账助手" in prompt            # 确实是 _build_prompt 的产物
    assert "AI 研究" in prompt                 # 分类行 + 规矩注入进去了
    assert "open code" in prompt.lower()       # 该用户学到的规则进了提示词
    assert "sk-abcdef123456SECRET" not in prompt  # key 不外泄

    assert body["hints"] and "AI 研究" in body["hints"]
    assert body["stats"]["rules"] == len(body["rules"]) >= 1
    assert body["stats"]["feedback_count"] == 10
    assert body["stats"]["version"] >= 1

    rule = body["rules"][0]
    assert set(rule) >= {"id", "kind", "pattern", "target_name", "weight", "hits", "updated_at"}
    assert rule["pattern"] == "open code" and rule["target_name"] == "AI 研究"
    assert rule["kind"] == "category"


def test_ai_memory_is_per_user(client):
    a = register(client, "mema")
    b = register(client, "memb")
    _learn_ai_research(client, a)

    body_b = client.get("/api/v1/ai/memory", headers=h(b)).json()
    assert body_b["rules"] == []
    assert "open code" not in body_b["prompt"].lower()
    assert body_b["hints"] == ""
    assert body_b["stats"]["rules"] == 0

    body_a = client.get("/api/v1/ai/memory", headers=h(a)).json()
    assert body_a["rules"] and body_a["rules"][0]["pattern"] == "open code"


def test_ai_memory_hides_secret_looking_text(client, monkeypatch):
    """提示词里被塞了 key 形态的文本时也要打码。"""
    import app.ai as ai_mod

    token = register(client, "memmask")
    _learn_ai_research(client, token)

    real_build = ai_mod._build_prompt

    def leaky_build(*args, **kwargs):
        messages = real_build(*args, **kwargs)
        messages[0]["content"] += "\n调试：api_key=sk-live-9f8e7d6c5b4a"
        return messages

    monkeypatch.setattr(ai_mod, "_build_prompt", leaky_build)

    body = client.get("/api/v1/ai/memory", headers=h(token)).json()
    assert "sk-live-9f8e7d6c5b4a" not in body["prompt"]
    assert "***" in body["prompt"]


def test_ai_memory_prompt_truncated_to_limit():
    """提示词超长要截断（App 里那一段是等宽滚动的，不能无限长）。"""
    from app.ai_api import MEMORY_PROMPT_LIMIT, _mask_prompt

    out = _mask_prompt("字" * 9000)
    assert len(out) <= MEMORY_PROMPT_LIMIT
    assert out.endswith("已截断）")


def test_ai_memory_requires_token(client):
    assert client.get("/api/v1/ai/memory").status_code == 401
