"""pytest 全局设置与收尾。

1) 配置固定：测试模块里用 `os.environ.setdefault(...)` 设邀请码，键已存在时不生效。
   CI 会显式传 `INVITE_CODE: ""`，那样「错的邀请码要 403」的用例会退化成 422。
   所以这里先**强制**钉住测试配置，不跟随外部环境。
2) 收尾清理：把测试过程中产生的临时 SQLite 文件全部删掉，避免留半成品。
"""
import glob
import os

import pytest

# 必须在任何 app 模块被导入之前设置（conftest 先于测试模块加载）。
os.environ["INVITE_CODE"] = "testcode"

_HERE = os.path.dirname(os.path.abspath(__file__))
_PATTERNS = ("test_*.db", "test_*.db-journal", "test_*.db-wal", "test_*.db-shm")


@pytest.fixture(scope="session", autouse=True)
def _cleanup_test_databases():
    yield

    # 先放掉连接，Windows 上文件被占用时 os.remove 会失败
    try:
        from app.db import engine

        engine.dispose()
    except Exception:  # 测试没导到 app 也无所谓，继续清理
        pass

    for pattern in _PATTERNS:
        for path in glob.glob(os.path.join(_HERE, "..", pattern)):
            try:
                os.remove(path)
            except OSError:
                pass
