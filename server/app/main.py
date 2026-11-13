"""小喵记账 · 服务端 API。

原则：所有业务数据都带 user_id，一律按登录 token 的用户过滤；接口不接受"查别人的账"。
管理台接口（/api/v1/admin/*）额外要求 role=admin。
"""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .admin_api import router as admin_router
from .ai_api import router as ai_router
from .asr import transcribe_wav
from .auth import current_user, promote_from_env
from .auth_api import router as auth_router
from .common import (
    check_amount,
    check_kind,
    export_csv_text,
    find_txn,
    import_csv,
    meta_of,
    seed_user,
    txn_payload,
)
from .db import SessionLocal, get_db, init_db
from .models import Account, Book, Category, Txn, User
from .schemas import AccountIn, BookIn, CategoryIn, MeOut, PushIn, PushOut, TxnOut, TxnPatchIn

APP_VERSION = "1.0.0"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    with SessionLocal() as db:  # 启动引导：ADMIN_USERNAME 指定的账号提为管理员
        promote_from_env(db)
    yield


app = FastAPI(title="小喵记账 API", version=APP_VERSION, lifespan=lifespan)

# 管理台默认同源反代，无需额外配置；只有前后端分域部署时才配 CORS_ORIGINS
_cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# APK 下载：容器里挂 /apk 目录（只读），手机直接打开 /apk/xxx.apk 就能装
_apk_dir = os.getenv("APK_DIR", "/apk")
if os.path.isdir(_apk_dir):
    from fastapi.staticfiles import StaticFiles

    app.mount("/apk", StaticFiles(directory=_apk_dir), name="apk")

# 账号注册/登录/登出/查重
app.include_router(auth_router)
# AI 解析 / 反馈学习 / 规则 / 画像（按账号隔离）
app.include_router(ai_router)
# 管理台：用户管理 + 代用户操作账本/账单/画像/导入导出（要求 role=admin）
app.include_router(admin_router)


@app.get("/health")
def health() -> dict:
    return {"ok": True, "time": datetime.now().isoformat(timespec="seconds"), "version": APP_VERSION}


# ---------------------------------------------------------------- 认证
# 注册 / 登录 / 登出 / 账号名查重已迁到 app/auth_api.py（APIRouter，见上方 include_router）。


def _meta(db: Session, user: User) -> dict:
    """历史名字保留：元数据查询（实现见 common.meta_of）。"""
    return meta_of(db, user)


@app.get("/api/v1/me", response_model=MeOut)
def me(user: User = Depends(current_user), db: Session = Depends(get_db)) -> MeOut:
    def cnt(model):
        return db.scalar(
            select(func.count()).select_from(model).where(model.user_id == user.id, model.deleted.is_(False))
        )

    return MeOut(
        username=user.username,
        display_name=user.display_name,
        role=user.role or "user",
        books=cnt(Book),
        accounts=cnt(Account),
        categories=cnt(Category),
        txns=db.scalar(select(func.count()).select_from(Txn).where(Txn.user_id == user.id, Txn.deleted.is_(False))),
    )


# ---------------------------------------------------------------- 元数据（账本/分类/账户）
@app.get("/api/v1/meta")
def meta(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return meta_of(db, user)


@app.post("/api/v1/books")
def add_book(body: BookIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    if db.scalar(select(Book).where(Book.user_id == user.id, Book.name == body.name)):
        raise HTTPException(status_code=409, detail="账本重名了")
    b = Book(user_id=user.id, name=body.name, icon=body.icon, sort=body.sort)
    db.add(b)
    db.commit()
    db.refresh(b)
    return {"id": b.id, "name": b.name}


@app.patch("/api/v1/books/{book_id}")
def edit_book(book_id: int, body: BookIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    b = db.get(Book, book_id)
    if b is None or b.user_id != user.id:
        raise HTTPException(status_code=404, detail="没有这个账本")
    b.name, b.icon, b.sort = body.name, body.icon, body.sort
    db.commit()
    return {"ok": True}


@app.delete("/api/v1/books/{book_id}")
def del_book(book_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    b = db.get(Book, book_id)
    if b is None or b.user_id != user.id:
        raise HTTPException(status_code=404, detail="没有这个账本")
    b.deleted = True
    db.commit()
    return {"ok": True}


@app.post("/api/v1/accounts")
def add_account(body: AccountIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    if db.scalar(select(Account).where(Account.user_id == user.id, Account.name == body.name)):
        raise HTTPException(status_code=409, detail="账户重名了")
    a = Account(user_id=user.id, name=body.name, kind=body.kind, balance0_cents=body.balance0_cents, sort=body.sort)
    db.add(a)
    db.commit()
    db.refresh(a)
    return {"id": a.id, "name": a.name}


@app.post("/api/v1/categories")
def add_category(body: CategoryIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    if db.scalar(
        select(Category).where(
            Category.user_id == user.id, Category.name == body.name, Category.parent_id == body.parent_id
        )
    ):
        raise HTTPException(status_code=409, detail="分类重名了")
    c = Category(
        user_id=user.id, name=body.name, parent_id=body.parent_id, kind=body.kind, icon=body.icon, sort=body.sort
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return {"id": c.id, "name": c.name}


@app.delete("/api/v1/categories/{category_id}")
def del_category(category_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """软删分类。已被账单引用的也允许删——历史账单保留原 id，统计里显示为「其它」。"""
    c = db.get(Category, category_id)
    if c is None or c.user_id != user.id or c.deleted:
        raise HTTPException(status_code=404, detail="没有这个分类")
    c.deleted = True
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- 账单同步
@app.delete("/api/v1/txns/all")
def del_all_txns(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """清空所有账单：只软删，不动账本/分类/账户，也不动 AI 学到的规矩。"""
    rows = db.scalars(select(Txn).where(Txn.user_id == user.id, Txn.deleted.is_(False))).all()
    for row in rows:
        row.deleted = True
    db.commit()
    return {"ok": True, "deleted": len(rows)}


@app.post("/api/v1/txns", response_model=PushOut)
def push_txns(body: PushIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> PushOut:
    created = updated = 0
    for item in body.txns:
        row = find_txn(db, user.id, item.client_uuid)
        if row is None:
            row = Txn(user_id=user.id, client_uuid=item.client_uuid)
            db.add(row)
            created += 1
        else:
            updated += 1
        row.book_id = item.book_id
        row.cat_id = item.cat_id
        row.account_id = item.account_id
        row.kind = item.kind
        row.amount_cents = item.amount_cents
        row.occurred_at = item.occurred_at
        row.note = item.note[:200]
        row.source = item.source
        row.deleted = item.deleted
    db.commit()
    return PushOut(accepted=len(body.txns), created=created, updated=updated, server_time=datetime.now())


@app.get("/api/v1/txns", response_model=list[TxnOut])
def pull_txns(
    since: datetime | None = None,
    book_id: int | None = None,
    include_deleted: bool = True,
    limit: int = Query(default=500, le=2000),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[TxnOut]:
    q = select(Txn).where(Txn.user_id == user.id)
    if since is not None:
        q = q.where(Txn.updated_at >= since)
    if book_id is not None:
        q = q.where(Txn.book_id == book_id)
    if not include_deleted:
        q = q.where(Txn.deleted.is_(False))
    rows = db.scalars(q.order_by(Txn.updated_at.asc()).limit(limit)).all()
    return [TxnOut(**txn_payload(r)) for r in rows]


@app.patch("/api/v1/txns/{client_uuid}", response_model=TxnOut)
def patch_txn(
    client_uuid: str,
    body: TxnPatchIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> TxnOut:
    """部分更新单笔账单：只改传上来的字段，没传的保持原值。"""
    row = find_txn(db, user.id, client_uuid)
    if row is None:
        raise HTTPException(status_code=404, detail="没有这笔账")

    if body.book_id is not None:
        row.book_id = body.book_id
    if body.cat_id is not None:
        row.cat_id = body.cat_id
    if body.account_id is not None:
        row.account_id = body.account_id
    kind = check_kind(body.kind)
    if kind is not None:
        row.kind = kind
    amount = check_amount(body.amount_cents)
    if amount is not None:
        row.amount_cents = amount
    if body.occurred_at is not None:
        row.occurred_at = body.occurred_at
    if body.note is not None:
        row.note = body.note[:200]
    row.updated_at = datetime.now()
    db.commit()
    db.refresh(row)
    return TxnOut(**txn_payload(row))


@app.delete("/api/v1/txns/{client_uuid}")
def del_txn(client_uuid: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    row = find_txn(db, user.id, client_uuid)
    if row is None:
        raise HTTPException(status_code=404, detail="没有这笔账")
    row.deleted = True
    row.updated_at = datetime.now()
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- 统计
@app.get("/api/v1/summary")
def summary(
    month: str = Query(pattern=r"^\d{4}-\d{2}$"),
    book_id: int | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    start = datetime.strptime(month + "-01", "%Y-%m-%d")
    end = datetime(start.year + (start.month == 12), (start.month % 12) + 1, 1)

    q = select(Txn).where(
        Txn.user_id == user.id, Txn.deleted.is_(False), Txn.occurred_at >= start, Txn.occurred_at < end
    )
    if book_id is not None:
        q = q.where(Txn.book_id == book_id)
    rows = db.scalars(q).all()

    out_cents = sum(r.amount_cents for r in rows if r.kind == "out")
    in_cents = sum(r.amount_cents for r in rows if r.kind == "in")

    cat_names = {c.id: c.name for c in db.scalars(select(Category).where(Category.user_id == user.id)).all()}
    by_cat: dict[str, int] = {}
    by_day: dict[str, int] = {}
    for r in rows:
        if r.kind != "out":
            continue
        name = cat_names.get(r.cat_id, "其它")
        by_cat[name] = by_cat.get(name, 0) + r.amount_cents
        key = r.occurred_at.strftime("%Y-%m-%d")
        by_day[key] = by_day.get(key, 0) + r.amount_cents

    return {
        "month": month,
        "out_cents": out_cents,
        "in_cents": in_cents,
        "left_cents": in_cents - out_cents,
        "count": len(rows),
        "by_category": sorted([{"name": k, "cents": v} for k, v in by_cat.items()], key=lambda x: -x["cents"]),
        "by_day": by_day,
    }


# ---------------------------------------------------------------- AI
# 解析 / 反馈学习 / 规则 / 画像已迁到 app/ai_api.py（APIRouter，见上方 include_router）。


@app.post("/api/v1/asr")
async def asr(
    file: UploadFile = File(...),
    user: User = Depends(current_user),
) -> dict:
    """按住说话录的 wav 传上来，走火山引擎识别成文字。"""
    if not os.getenv("VOLC_API_KEY", "").strip():
        raise HTTPException(status_code=503, detail="服务端没配语音识别 Key，语音记账没启用")
    data = await file.read()
    if len(data) < 2000:
        raise HTTPException(status_code=400, detail="录音太短")
    try:
        text = await asyncio.to_thread(transcribe_wav, data)
    except Exception as e:  # 网络/额度/鉴权问题都从这里出去
        raise HTTPException(status_code=502, detail=f"语音识别失败：{type(e).__name__} {e}")
    if not text:
        return {"text": "", "ok": False, "msg": "没听清"}
    return {"text": text, "ok": True}


# ---------------------------------------------------------------- 导入 / 导出（8 列 CSV 口径）
@app.post("/api/v1/import/csv")
async def import_csv_api(
    file: UploadFile = File(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    raw = await file.read()
    return import_csv(db, user, raw)


@app.get("/api/v1/export.csv", response_class=PlainTextResponse)
def export_csv(
    start: str = Query(alias="from", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    end: str = Query(alias="to", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    book_id: int | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> PlainTextResponse:
    return PlainTextResponse(export_csv_text(db, user, start, end, book_id), media_type="text/csv; charset=utf-8")
