"""自然语言提问（WO-05）：模型只翻译条件，数字由服务端 SQL 算。

测试绝不真打 DeepSeek：所有模型出场都 monkeypatch 掉。
重点验三件事：
1. 数字必须是 SQL 算出来的，和统计页一致；
2. 模型瞎编的分类/账本/字段一律进不来，SQL 只认白名单；
3. 不像问账的话不硬答、空结果不编。

运行：python -m pytest -q server/tests/test_ask.py
"""
import os
import sys

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_ask_tmp.db")
os.environ.setdefault("INVITE_CODE", "testcode")
os.environ.pop("ADMIN_USERNAME", None)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

from app import ask as ask_mod  # noqa: E402
from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c
    engine.dispose()


@pytest.fixture(autouse=True)
def no_model(monkeypatch):
    """默认没有模型：走本地翻译 + 模板回答。单个用例自己覆盖这两个钩子。"""
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(ask_mod, "_call_model_json", lambda _prompt: None)
    monkeypatch.setattr(ask_mod, "_call_model_text", lambda _prompt: None)


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
    r = c.get("/api/v1/meta", headers=h(token))
    assert r.status_code == 200, r.text
    return r.json()


def cat_id(c, token: str, name: str) -> int:
    for row in meta(c, token)["categories"]:
        if row["name"] == name:
            return row["id"]
    raise AssertionError(f"没找到分类 {name}")


def push(c, token: str, uuid: str, cents: int, cat: int | None, when: str, note: str = "", kind: str = "out"):
    book = meta(c, token)["books"][0]["id"]
    r = c.post(
        "/api/v1/txns",
        headers=h(token),
        json={
            "txns": [
                {
                    "client_uuid": uuid,
                    "book_id": book,
                    "cat_id": cat,
                    "kind": kind,
                    "amount_cents": cents,
                    "occurred_at": when,
                    "note": note,
                }
            ]
        },
    )
    assert r.status_code == 200, r.text


@pytest.fixture(scope="module")
def shop(client) -> dict:
    """一个有账的账号：11 月餐饮 3 笔、交通 1 笔，10 月餐饮 1 笔。"""
    token = register(client, "asker")
    food = cat_id(client, token, "餐饮")
    traffic = cat_id(client, token, "交通")
    push(client, token, "ask-food-0001", 2500, food, "2026-11-03T12:00:00", "午饭")
    push(client, token, "ask-food-0002", 3800, food, "2026-11-10T19:00:00", "火锅")
    push(client, token, "ask-food-0003", 1200, food, "2026-11-20T08:00:00", "包子")
    push(client, token, "ask-traf-0001", 3000, traffic, "2026-11-05T09:00:00", "打车")
    push(client, token, "ask-food-0004", 5000, food, "2026-10-15T12:00:00", "上月的饭")
    return {"token": token, "food": food, "traffic": traffic}


NOW = {"now": "2026-11-18T20:00:00"}


# ---------------------------------------------------------------- 数字必须和统计页一致
def test_sum_matches_summary_page(client, shop):
    """"这个月买吃的花了多少" → 数字必须和 /summary 里餐饮那一格分不差。"""
    stats = client.get("/api/v1/summary", headers=h(shop["token"]), params={"month": "2026-11"}).json()
    expect = next(r["cents"] for r in stats["by_category"] if r["name"] == "餐饮")
    assert expect == 2500 + 3800 + 1200  # 3 笔，不含上个月那 5000

    r = client.post("/api/v1/ask", headers=h(shop["token"]), json={"text": "这个月买吃的花了多少", **NOW})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["data"]["total_cents"] == expect
    assert body["data"]["count"] == 3
    assert body["query"]["metric"] == "sum"
    assert body["query"]["categories"] == ["餐饮"]
    assert body["query"]["date_from"] == "2026-11-01"
    assert "75.00" in body["answer"], body["answer"]


def test_answer_only_uses_numbers_from_result_table(client, shop):
    """回答里的钱数只能是结果表里那一个（75.00 元），不许模型自己算同比环比。"""
    r = client.post("/api/v1/ask", headers=h(shop["token"]), json={"text": "这个月买吃的花了多少", **NOW})
    answer = r.json()["answer"]
    assert "75.00" in answer, answer
    assert "上个月" not in answer, "模板兜底不该自己算环比"
    assert "比" not in answer or "笔" in answer, answer


def test_last_month_range_is_correct(client, shop):
    r = client.post("/api/v1/ask", headers=h(shop["token"]), json={"text": "上个月一共花了多少", **NOW})
    body = r.json()
    assert body["query"]["date_from"] == "2026-10-01"
    assert body["query"]["date_to"] == "2026-10-31"
    assert body["data"]["total_cents"] == 5000


def test_count_metric(client, shop):
    r = client.post("/api/v1/ask", headers=h(shop["token"]), json={"text": "这个月一共记了几笔", **NOW})
    body = r.json()
    assert body["query"]["metric"] == "count"
    assert body["data"]["count"] == 4


def test_group_by_category(client, shop):
    r = client.post("/api/v1/ask", headers=h(shop["token"]), json={"text": "这个月按分类各花了多少", **NOW})
    body = r.json()
    assert body["query"]["group_by"] == ["category"]
    names = {row["name"]: row["cents"] for row in body["data"]["rows"]}
    assert names["餐饮"] == 7500
    assert names["交通"] == 3000


def test_empty_range_says_no_records(client, shop):
    r = client.post("/api/v1/ask", headers=h(shop["token"]), json={"text": "去年这个月花了多少", **NOW})
    body = r.json()
    assert body["data"]["total_cents"] == 0
    assert body["answer"] == "这个范围里没有记录。"


# ---------------------------------------------------------------- 白名单：模型的输出不可信
def test_model_plan_is_sanitized(client, shop, monkeypatch):
    """模型给的分类/账本/字段只要不在白名单里就丢掉，不许进 SQL。"""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy")
    monkeypatch.setattr(
        ask_mod,
        "_call_model_json",
        lambda _prompt: {
            "metric": "sum",
            "date_from": "2026-11-01",
            "date_to": "2026-11-30",
            "categories": ["餐饮", "别人家的分类"],  # 第二个不存在
            "books": ["日常账本", "不存在的账本"],
            "keyword": "",
            "group_by": ["category"],
            "order": "desc",
            "limit": 50,
            "sql": "DROP TABLE txns",  # 多余字段必须被忽略
        },
    )
    r = client.post("/api/v1/ask", headers=h(shop["token"]), json={"text": "这个月买吃的花了多少", **NOW})
    body = r.json()
    assert body["query"]["categories"] == ["餐饮"]
    assert body["query"]["books"] == ["日常账本"]
    assert "sql" not in body["query"]
    assert body["data"]["total_cents"] == 7500
    # 表和功能都还在
    assert client.get("/api/v1/summary", headers=h(shop["token"]), params={"month": "2026-11"}).status_code == 200


def test_model_bad_enum_and_dates_fall_back(client, shop, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy")
    monkeypatch.setattr(
        ask_mod,
        "_call_model_json",
        lambda _prompt: {
            "metric": "delete",  # 非法枚举
            "date_from": "昨天",  # 非法日期
            "date_to": 12345,  # 非法类型
            "group_by": ["cookie"],  # 非法维度
            "order": "random",
            "limit": 99999,  # 超上限
        },
    )
    r = client.post("/api/v1/ask", headers=h(shop["token"]), json={"text": "这个月花了多少", **NOW})
    body = r.json()
    q = body["query"]
    assert q["metric"] == "sum"
    assert q["group_by"] == []
    assert q["order"] == "desc"
    assert q["limit"] == 200, "limit 上限 200"
    assert q["date_from"] == "2026-11-01" and q["date_to"] == "2026-11-18"


def test_model_date_reversed_is_swapped(client, shop, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy")
    monkeypatch.setattr(
        ask_mod,
        "_call_model_json",
        lambda _prompt: {"metric": "count", "date_from": "2026-11-30", "date_to": "2026-11-01"},
    )
    r = client.post("/api/v1/ask", headers=h(shop["token"]), json={"text": "这个月几笔", **NOW})
    q = r.json()["query"]
    assert q["date_from"] == "2026-11-01" and q["date_to"] == "2026-11-30"


def test_keyword_is_parameterized(client, shop):
    """keyword 里有引号也只能当字符串，不能拼进 SQL。"""
    r = client.post("/api/v1/ask", headers=h(shop["token"]), json={"text": "哪笔是火锅", **NOW})
    assert r.status_code == 200
    # 直接打模型计划，塞一个带引号的关键词，验证不报错且查得到
    r = client.post(
        "/api/v1/ask",
        headers=h(shop["token"]),
        json={"text": "备注里有火锅的花了多少", **NOW},
    )
    assert r.status_code == 200, r.text


def test_keyword_filter_matches(client, shop, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy")
    monkeypatch.setattr(
        ask_mod,
        "_call_model_json",
        lambda _prompt: {"metric": "sum", "date_from": "2026-11-01", "date_to": "2026-11-30", "keyword": "火锅"},
    )
    r = client.post("/api/v1/ask", headers=h(shop["token"]), json={"text": "火锅花了多少", **NOW})
    assert r.json()["data"]["total_cents"] == 3800


def test_quoted_keyword_does_not_break_sql(client, shop, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy")
    monkeypatch.setattr(
        ask_mod,
        "_call_model_json",
        lambda _prompt: {
            "metric": "sum",
            "date_from": "2026-11-01",
            "date_to": "2026-11-30",
            "keyword": "'; DROP TABLE txns; --",
        },
    )
    r = client.post("/api/v1/ask", headers=h(shop["token"]), json={"text": "x", **NOW})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["total_cents"] == 0
    assert client.get("/api/v1/summary", headers=h(shop["token"]), params={"month": "2026-11"}).status_code == 200


def test_only_own_txns_are_counted(client, shop):
    """别人的账不进结果：越权等于不存在。"""
    other = register(client, "other_asker")
    food = cat_id(client, other, "餐饮")
    push(client, other, "other-food-0001", 99999, food, "2026-11-06T12:00:00", "别人的饭")

    r = client.post("/api/v1/ask", headers=h(shop["token"]), json={"text": "这个月买吃的花了多少", **NOW})
    assert r.json()["data"]["total_cents"] == 7500, "不该把别人的账算进来"

    r2 = client.post("/api/v1/ask", headers=h(other), json={"text": "这个月买吃的花了多少", **NOW})
    assert r2.json()["data"]["total_cents"] == 99999


def test_model_category_from_another_user_is_dropped(client, shop, monkeypatch):
    """模型给了别人账号才有的分类名 → 当作不存在（不是 500，也不是查出别人的账）。"""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy")
    monkeypatch.setattr(
        ask_mod,
        "_call_model_json",
        lambda _prompt: {
            "metric": "sum",
            "date_from": "2026-11-01",
            "date_to": "2026-11-30",
            "categories": ["只有别人有"],
        },
    )
    r = client.post("/api/v1/ask", headers=h(shop["token"]), json={"text": "那个分类花了多少", **NOW})
    body = r.json()
    assert body["query"]["categories"] == []
    assert body["data"]["total_cents"] == 7500 + 3000


# ---------------------------------------------------------------- 不像问账的
def test_out_of_scope_question_does_not_invent(client, shop):
    r = client.post("/api/v1/ask", headers=h(shop["token"]), json={"text": "今天天气怎么样", **NOW})
    body = r.json()
    assert body["answer"] == "我只能查你的账，别的答不了。"
    assert body["data"]["total_cents"] == 0
    assert body["query"] == {}


def test_model_says_out_of_scope(client, shop, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy")
    monkeypatch.setattr(ask_mod, "_call_model_json", lambda _prompt: {"in_scope": False})
    r = client.post("/api/v1/ask", headers=h(shop["token"]), json={"text": "帮我写首诗", **NOW})
    assert r.json()["answer"] == "我只能查你的账，别的答不了。"


def test_empty_text_is_422(client, shop):
    r = client.post("/api/v1/ask", headers=h(shop["token"]), json={"text": ""})
    assert r.status_code == 422


def test_requires_token(client):
    r = client.post("/api/v1/ask", json={"text": "这个月花了多少"})
    assert r.status_code == 401


# ---------------------------------------------------------------- 记账不误触提问
def test_record_phrase_still_goes_to_parse(client, shop, monkeypatch):
    """"帮我记一笔午饭 25" → /ai/parse 的 raw.intent 是 record，金额 > 0，客户端该走记账。"""
    from app import ai as ai_mod

    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    r = client.post("/api/v1/ai/parse", headers=h(shop["token"]), json={"text": "帮我记一笔午饭 25"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["amount_cents"] == 2500
    assert body["raw"]["intent"] == "record"
    assert body["cat_name"] == "餐饮"


def test_query_phrase_is_flagged_by_parse(client, shop, monkeypatch):
    """问句 → /ai/parse 的 raw.intent=query 且 amount_cents=0，客户端据此转去 /ask。"""
    from app import ai as ai_mod

    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy")
    monkeypatch.setattr(
        ai_mod,
        "_call_model",
        lambda *a, **kw: {"intent": "query", "kind": "out", "amount": 0, "note": "问账"},
    )
    r = client.post("/api/v1/ai/parse", headers=h(shop["token"]), json={"text": "这个月买吃的花了多少"})
    body = r.json()
    assert body["raw"]["intent"] == "query"
    assert body["amount_cents"] == 0
