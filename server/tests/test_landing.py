"""首页落地页测试：根路径能开、带 APK 下载入口、不泄露接口细节。"""
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


def test_root_serves_landing_page(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    body = r.text
    assert "小喵记账" in body
    assert "/apk/" in body and ".apk" in body
    # 不把接口地图漏在页面上
    assert "/api/v1/" not in body
