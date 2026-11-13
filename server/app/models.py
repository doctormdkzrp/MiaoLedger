"""数据模型：一人一套数据，所有业务表都挂在 user_id 下。"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(32), default="")
    pin_hash: Mapped[str] = mapped_column(String(200))
    # admin / user；老库没有这一列时由 db.ensure_schema 补上（默认 user）
    role: Mapped[str] = mapped_column(String(16), default="user", server_default="user")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Device(Base):
    """一台手机一个 token，退出登录即失效。"""

    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(64), default="")
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_seen: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Book(Base):
    __tablename__ = "books"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_book_user_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(32))
    icon: Mapped[str] = mapped_column(String(8), default="🏠")
    sort: Mapped[int] = mapped_column(Integer, default=0)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_account_user_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(32))
    kind: Mapped[str] = mapped_column(String(16), default="virtual")  # cash/card/credit/virtual
    balance0_cents: Mapped[int] = mapped_column(Integer, default=0)  # 期初余额（分）
    sort: Mapped[int] = mapped_column(Integer, default=0)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("user_id", "name", "parent_id", name="uq_cat_user_name_parent"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(32))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(8), default="out")  # out/in
    icon: Mapped[str] = mapped_column(String(8), default="🏷")
    sort: Mapped[int] = mapped_column(Integer, default=0)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class UserAiProfile(Base):
    """每人一份 AI 画像：把最近的归类纠错压成几行提示，解析时喂给模型。

    一个用户最多一行（user_id 唯一）；老库没有这张表时由 init_db 的 create_all 自动补建。
    """

    __tablename__ = "user_ai_profile"
    __table_args__ = (UniqueConstraint("user_id", name="uq_ai_profile_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    hints: Mapped[str] = mapped_column(String(600), default="")  # 画像正文，业务上限 500 字
    version: Mapped[int] = mapped_column(Integer, default=0)
    feedback_count: Mapped[int] = mapped_column(Integer, default=0)  # 用于「每 10 条压一次」
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class LearnedRule(Base):
    """学到的规则：关键词 → 分类/账户/账本。weight 越大越可信，hits 记录命中次数。"""

    __tablename__ = "learned_rule"
    __table_args__ = (UniqueConstraint("user_id", "kind", "pattern", name="uq_rule_user_kind_pattern"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # category / account / book
    pattern: Mapped[str] = mapped_column(String(64))  # 规范化后的关键词（小写、去空白）
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_name: Mapped[str] = mapped_column(String(32), default="")
    weight: Mapped[int] = mapped_column(Integer, default=1)  # >=2 时解析直接定类
    hits: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(16), default="feedback")  # feedback / new_category
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class Txn(Base):
    """账单。金额存"分"；client_uuid 由手机生成，保证重复上传不重复记账。"""

    __tablename__ = "txns"
    __table_args__ = (
        UniqueConstraint("user_id", "client_uuid", name="uq_txn_user_uuid"),
        Index("ix_txn_user_time", "user_id", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    client_uuid: Mapped[str] = mapped_column(String(40))
    book_id: Mapped[int | None] = mapped_column(ForeignKey("books.id"), nullable=True)
    cat_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(8), default="out")  # out/in/transfer
    amount_cents: Mapped[int] = mapped_column(Integer)
    occurred_at: Mapped[datetime] = mapped_column(DateTime)
    note: Mapped[str] = mapped_column(String(200), default="")
    source: Mapped[str] = mapped_column(String(16), default="manual")  # manual/voice/ai/import
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
