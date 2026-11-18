"""防护层测试：API 文档默认关闭、单 IP 限流、请求体上限。

限流与体积上限都走环境变量，所以这里用 monkeypatch 临时改；conftest.py 里
默认把 RATE_LIMIT_PER_MIN 设成 0，别的测试不受影响。
"""
import os
import sys

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_ledger.db")
os.environ.setdefault("INVITE_CODE", "testcode")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_api_docs_disabled(client):
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404, path


def test_rate_limit_returns_429(client, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "3")
    codes = [client.get("/api/v1/meta").status_code for _ in range(6)]
    assert codes[0] != 429  # 前面的请求要能过去
    assert 429 in codes  # 超了必须被挡


def test_health_is_exempt(client, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "1")
    codes = [client.get("/health").status_code for _ in range(5)]
    assert codes == [200] * 5


def test_big_body_rejected(client, monkeypatch):
    monkeypatch.setenv("MAX_BODY_BYTES", "1000")
    r = client.post(
        "/api/v1/txns",
        content=b"x" * 5000,
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 413
