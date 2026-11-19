"""首页落地页测试：能开、有下载入口、不泄露个人信息与接口路径。"""
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
    assert "/api/v1/" not in body


def test_landing_has_no_private_info(client):
    body = client.get("/").text
    # 公网页面上不能出现真实姓名，也不能把邀请码印出来
    assert "张汝沛" not in body
    assert "邀请码单独找管理员要" in body
