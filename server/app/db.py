"""数据库连接与会话（SQLite 开发 / PostgreSQL 生产）。"""
import os
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "").strip() or "sqlite:///./data/miaoledger.db"

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, future=True, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _sqlite_path(url: str) -> str | None:
    """从 sqlite:/// 开头的 URL 里取文件路径；内存库返回 None。"""
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        return None
    path = url[len(prefix):]
    if not path or path == ":memory:":
        return None
    return path


# 老库补列：create_all 只建新表，不会给已有表加字段，所以在这里按需 ALTER。
# SQLite / PostgreSQL 语法一致（ADD COLUMN + NOT NULL DEFAULT），可反复执行。
EXTRA_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "users": [("role", "VARCHAR(16) NOT NULL DEFAULT 'user'")],
    # 新设备批准：老库的 devices 没有这几列，补上。status 的 DDL 默认值特意写成
    # approved —— 老设备（本来就在用）加列时直接就是 approved，不会把自己锁在外面；
    # 只有代码里新建的「没见过的设备」才显式写成 pending。
    "devices": [
        ("device_uuid", "VARCHAR(64) NOT NULL DEFAULT ''"),
        ("device_name", "VARCHAR(64) NOT NULL DEFAULT ''"),
        ("status", "VARCHAR(16) NOT NULL DEFAULT 'approved'"),
        ("first_seen", "TIMESTAMP"),
    ],
}

# 兜底：万一某条老记录的 status 是空的（手工改过库、或别的方言补列时没带默认值），
# 一律按 approved 处理，避免升级后自己的手机进不来。
BACKFILL_SQL: list[str] = [
    "UPDATE devices SET status = 'approved' WHERE status IS NULL OR status = ''",
]


def ensure_schema(bind: Engine | None = None) -> list[str]:
    """补齐老库缺的列；返回本次真正执行的 ALTER 语句（便于启动日志/测试断言）。"""
    bind = bind or engine
    applied: list[str] = []
    insp = inspect(bind)
    tables = set(insp.get_table_names())
    for table, columns in EXTRA_COLUMNS.items():
        if table not in tables:
            continue
        existing = {c["name"] for c in insp.get_columns(table)}
        for name, ddl in columns:
            if name in existing:
                continue
            stmt = f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"
            with bind.begin() as conn:
                conn.execute(text(stmt))
            applied.append(stmt)
    return applied


def backfill_legacy_devices(bind: Engine | None = None) -> list[str]:
    """把没有状态的设备（升级前就存在的老设备）一律置为 approved。

    这条必须跟 ensure_schema 一起跑：老手机本来就在用，升级后不能因为新加的
    「新设备要批准」规则被踢出去。
    """
    bind = bind or engine
    applied: list[str] = []
    insp = inspect(bind)
    if "devices" not in set(insp.get_table_names()):
        return applied
    existing = {c["name"] for c in insp.get_columns("devices")}
    if "status" not in existing:
        return applied
    for stmt in BACKFILL_SQL:
        with bind.begin() as conn:
            res = conn.execute(text(stmt))
        if (res.rowcount or 0) > 0:
            applied.append(stmt)
    return applied


def init_db() -> None:
    from . import models  # noqa: F401  确保模型注册

    path = _sqlite_path(DATABASE_URL)
    if path:
        Path(path).expanduser().parent.mkdir(parents=True, exist_ok=True)

    Base.metadata.create_all(bind=engine)
    ensure_schema(engine)
    backfill_legacy_devices(engine)
