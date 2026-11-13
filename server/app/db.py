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
}


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


def init_db() -> None:
    from . import models  # noqa: F401  确保模型注册

    path = _sqlite_path(DATABASE_URL)
    if path:
        Path(path).expanduser().parent.mkdir(parents=True, exist_ok=True)

    Base.metadata.create_all(bind=engine)
    ensure_schema(engine)
