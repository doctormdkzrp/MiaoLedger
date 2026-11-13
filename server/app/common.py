"""跨路由复用的小工具：默认数据初始化、元数据、CSV 导入导出、账单序列化。

放在单独模块里是为了让 main.py / ai_api.py / admin_api.py 都能用，
又不至于互相 import 成环。
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta
from hashlib import sha1

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Account, Book, Category, Txn, User

DEFAULT_BOOKS = [("日常账本", "🏠")]
DEFAULT_ACCOUNTS = [("微信", "virtual"), ("支付宝", "virtual"), ("建行", "card"), ("现金", "cash")]
DEFAULT_CATS = {
    "out": ["餐饮", "交通", "汽车", "购物", "烟酒", "育儿", "赡养", "医疗", "居家", "旅行", "人情", "其它"],
    "in": ["工资", "奖金", "其它收入"],
}

# 导入导出统一 8 列口径（列顺序即契约，CSV 首行固定）
CSV_HEADER = ["时间", "金额", "收支", "分类", "资产账户", "账本", "货币", "备注"]

TXN_KINDS = ("out", "in", "transfer")


# ---------------------------------------------------------------- 初始化 / 元数据
def seed_user(db: Session, user: User) -> None:
    """新账号的默认账本 / 账户 / 分类（注册与管理台建号共用这一份）。"""
    for i, (name, icon) in enumerate(DEFAULT_BOOKS):
        db.add(Book(user_id=user.id, name=name, icon=icon, sort=i))
    for i, (name, kind) in enumerate(DEFAULT_ACCOUNTS):
        db.add(Account(user_id=user.id, name=name, kind=kind, sort=i))
    for kind, names in DEFAULT_CATS.items():
        for i, name in enumerate(names):
            db.add(Category(user_id=user.id, name=name, kind=kind, sort=i))
    db.commit()


def meta_of(db: Session, user: User) -> dict:
    """该用户的账本 / 分类 / 账户（软删的不返回）。"""
    books = db.scalars(
        select(Book).where(Book.user_id == user.id, Book.deleted.is_(False)).order_by(Book.sort, Book.id)
    ).all()
    cats = db.scalars(
        select(Category)
        .where(Category.user_id == user.id, Category.deleted.is_(False))
        .order_by(Category.sort, Category.id)
    ).all()
    accts = db.scalars(
        select(Account)
        .where(Account.user_id == user.id, Account.deleted.is_(False))
        .order_by(Account.sort, Account.id)
    ).all()
    return {
        "books": [{"id": b.id, "name": b.name, "icon": b.icon, "sort": b.sort} for b in books],
        "categories": [
            {"id": c.id, "name": c.name, "parent_id": c.parent_id, "kind": c.kind, "icon": c.icon, "sort": c.sort}
            for c in cats
        ],
        "accounts": [
            {"id": a.id, "name": a.name, "kind": a.kind, "balance0_cents": a.balance0_cents, "sort": a.sort}
            for a in accts
        ],
    }


# ---------------------------------------------------------------- 账单
def txn_payload(row: Txn) -> dict:
    """账单 → 接口输出（与 schemas.TxnOut 字段一致）。"""
    return {
        "id": row.id,
        "client_uuid": row.client_uuid,
        "book_id": row.book_id,
        "cat_id": row.cat_id,
        "account_id": row.account_id,
        "kind": row.kind,
        "amount_cents": row.amount_cents,
        "occurred_at": row.occurred_at,
        "note": row.note,
        "source": row.source,
        "deleted": row.deleted,
        "updated_at": row.updated_at,
    }


def find_txn(db: Session, user_id: int, client_uuid: str) -> Txn | None:
    return db.scalar(select(Txn).where(Txn.user_id == user_id, Txn.client_uuid == client_uuid))


def check_kind(kind: str | None) -> str | None:
    """校验收支类型；None 原样返回（表示这次不改）。"""
    if kind is None:
        return None
    kind = str(kind).strip()
    if kind not in TXN_KINDS:
        raise HTTPException(status_code=422, detail="收支类型只能是 out（支出）/ in（收入）/ transfer（转账）")
    return kind


def check_amount(amount_cents: int | None) -> int | None:
    if amount_cents is None:
        return None
    if amount_cents < 0:
        raise HTTPException(status_code=422, detail="金额不能是负数")
    return int(amount_cents)


# ---------------------------------------------------------------- CSV 导入
def decode_csv(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise HTTPException(status_code=400, detail="文件编码认不出来，试试 UTF-8 或 GBK")


def import_csv(db: Session, user: User, raw: bytes) -> dict:
    """导入 8 列 CSV：账本/分类/账户按名字自动补齐，重复行跳过。"""
    text = decode_csv(raw)
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "时间" not in reader.fieldnames:
        raise HTTPException(status_code=400, detail="不是支持的 CSV 格式（缺「时间」这一列）")

    m = meta_of(db, user)
    books = {b["name"]: b["id"] for b in m["books"]}
    cats = {c["name"]: c["id"] for c in m["categories"]}
    accts = {a["name"]: a["id"] for a in m["accounts"]}

    def ensure_book(name: str) -> int:
        name = (name or "默认账本").strip()
        if name not in books:
            b = Book(user_id=user.id, name=name)
            db.add(b)
            db.flush()
            books[name] = b.id
        return books[name]

    def ensure_cat(name: str, kind: str) -> int:
        name = (name or "其它").strip()
        if name not in cats:
            c = Category(user_id=user.id, name=name, kind=kind)
            db.add(c)
            db.flush()
            cats[name] = c.id
        return cats[name]

    def ensure_acct(name: str) -> int:
        name = (name or "现金").strip()
        if name not in accts:
            a = Account(user_id=user.id, name=name)
            db.add(a)
            db.flush()
            accts[name] = a.id
        return accts[name]

    imported = skipped = 0
    seen: set[str] = set()  # 同一个文件里出现两行完全一样的账，第二行也要跳过
    for row in reader:
        try:
            amount = float(str(row["金额"]).replace(",", "") or 0)
            when = datetime.strptime(row["时间"].strip(), "%Y-%m-%d %H:%M:%S")
        except Exception:
            skipped += 1
            continue
        kind = "in" if "收入" == (row.get("收支") or "").strip() else "out"
        book_id = ensure_book(row.get("账本", ""))
        cat_id = ensure_cat(row.get("分类", ""), kind)
        acct_id = ensure_acct(row.get("资产账户", ""))
        uuid = sha1(f"{user.id}|{row['时间']}|{row.get('金额')}|{row.get('备注', '')}".encode()).hexdigest()[:32]
        if uuid in seen or db.scalar(select(Txn).where(Txn.user_id == user.id, Txn.client_uuid == uuid)):
            skipped += 1
            continue
        seen.add(uuid)
        db.add(
            Txn(
                user_id=user.id,
                client_uuid=uuid,
                book_id=book_id,
                cat_id=cat_id,
                account_id=acct_id,
                kind=kind,
                amount_cents=int(round(abs(amount) * 100)),
                occurred_at=when,
                note=(row.get("备注") or "")[:200],
                source="import",
            )
        )
        imported += 1
    db.commit()
    return {"imported": imported, "skipped": skipped}


# ---------------------------------------------------------------- CSV 导出
def export_csv_text(db: Session, user: User, start: str, end: str, book_id: int | None = None) -> str:
    """按日期区间导出 8 列 CSV（UTF-8 BOM，Excel 直接双击不乱码）。"""
    t0 = datetime.strptime(start, "%Y-%m-%d")
    t1 = datetime.strptime(end, "%Y-%m-%d") + timedelta(days=1)
    q = select(Txn).where(
        Txn.user_id == user.id, Txn.deleted.is_(False), Txn.occurred_at >= t0, Txn.occurred_at < t1
    )
    if book_id is not None:
        q = q.where(Txn.book_id == book_id)
    rows = db.scalars(q.order_by(Txn.occurred_at)).all()

    m = meta_of(db, user)
    book_names = {b["id"]: b["name"] for b in m["books"]}
    cat_names = {c["id"]: c["name"] for c in m["categories"]}
    acct_names = {a["id"]: a["name"] for a in m["accounts"]}

    buf = io.StringIO()
    buf.write("\ufeff")
    w = csv.writer(buf)
    w.writerow(CSV_HEADER)
    for r in rows:
        w.writerow(
            [
                r.occurred_at.strftime("%Y-%m-%d %H:%M:%S"),
                f"{r.amount_cents / 100:.2f}".rstrip("0").rstrip("."),
                {"out": "支出", "in": "收入", "transfer": "转账"}.get(r.kind, "支出"),
                cat_names.get(r.cat_id, "其它"),
                acct_names.get(r.account_id, "不计入账户"),
                book_names.get(r.book_id, "默认账本"),
                "人民币",
                r.note,
            ]
        )
    return buf.getvalue()
