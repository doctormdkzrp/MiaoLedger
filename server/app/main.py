"""小喵记账 · 服务端 API。

原则：所有业务数据都带 user_id，一律按登录 token 的用户过滤；接口不接受"查别人的账"。
管理台接口（/api/v1/admin/*）额外要求 role=admin。
"""
from __future__ import annotations

import asyncio
import base64
import os
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .admin_api import router as admin_router
from .ai_api import router as ai_router
from .asr import transcribe_wav
from .ask import router as ask_router
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
from .guard import GuardMiddleware
from .landing import render as render_landing
from .models import Account, Book, Category, Txn, User
from .schemas import AccountIn, BookIn, CategoryIn, MeOut, PushIn, PushOut, TxnOut, TxnPatchIn

APP_VERSION = "1.1.7"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    with SessionLocal() as db:  # 启动引导：ADMIN_USERNAME 指定的账号提为管理员
        promote_from_env(db)
    yield


# 生产环境默认不暴露 API 文档（/docs、/redoc、/openapi.json）——
# 那三页等于把整张接口地图（含 /admin/*）送给扫描器。要临时看文档就设 ENABLE_DOCS=1。
_DOCS = os.getenv("ENABLE_DOCS", "0") == "1"
app = FastAPI(
    title="小喵记账 API",
    version=APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs" if _DOCS else None,
    redoc_url="/redoc" if _DOCS else None,
    openapi_url="/openapi.json" if _DOCS else None,
)

# 轻量防护：单 IP 限流 + 请求体上限（见 app/guard.py）
app.add_middleware(GuardMiddleware)

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
# 自然语言提问：模型只翻译条件，数字由服务端 SQL 算
app.include_router(ask_router)
# 管理台：用户管理 + 代用户操作账本/账单/画像/导入导出（要求 role=admin）
app.include_router(admin_router)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def landing() -> str:
    """首页落地页：给家里人看的，放最新 APK 的下载入口。

    不放任何接口细节；APK 名字取 /apk 目录里最新的那个，换包不用改代码。
    """
    return render_landing()


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


def _cursor_time(db: Session, expr):
    """把 updated_at 统一裁到「秒」再比。

    SQLite 的 updated_at 是文本：建表默认值（CURRENT_TIMESTAMP）写的是
    `2026-11-18 11:46:04`，而代码里赋值 datetime.now() 写的是
    `2026-11-18 11:46:04.123456`。两种形态直接比会漏（同一行跟自己的游标判不相等），
    所以两边都裁到秒；秒内并列的由 client_uuid 定先后，翻页仍然不重不漏。
    """
    if db.get_bind().dialect.name == "sqlite":
        return func.strftime("%Y-%m-%d %H:%M:%S", expr)
    return func.to_char(func.date_trunc("second", expr), "YYYY-MM-DD HH24:MI:SS")


def _encode_cursor(row: Txn) -> str:
    """把「updated_at（秒）+ client_uuid」编成一个不透明游标，客户端只管原样带回来。"""
    ts = row.updated_at or datetime.min
    raw = f"{ts.strftime('%Y-%m-%d %H:%M:%S')}|{row.client_uuid}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> tuple[str, str]:
    """游标解不开就是客户端乱传，直接 422，不猜。"""
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        ts_text, _, uuid = raw.partition("|")
        datetime.strptime(ts_text, "%Y-%m-%d %H:%M:%S")
        return ts_text, uuid
    except Exception:
        raise HTTPException(status_code=422, detail="cursor 不对，从头拉一遍")


@app.get("/api/v1/txns")
def pull_txns(
    since: datetime | None = None,
    book_id: int | None = None,
    include_deleted: bool = True,
    limit: int = Query(default=500, le=2000),
    full: int = 0,
    cursor: str | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """拉账单。

    老客户端（不带 full）还是拿到裸列表，语义跟以前一模一样；
    `full=1` 走整库分页拉取，返回 {"items":[...],"next_cursor":"...","total":N}，
    软删的笔也会带 deleted=true 一起回来，客户端据此删本地行。
    """
    if full and limit > 1000:
        raise HTTPException(status_code=422, detail="单次最多拉 1000 笔")

    ts_key = _cursor_time(db, Txn.updated_at)
    conds = [Txn.user_id == user.id]
    if since is not None:
        conds.append(Txn.updated_at >= since)
    if book_id is not None:
        conds.append(Txn.book_id == book_id)
    if not include_deleted:
        conds.append(Txn.deleted.is_(False))

    # total 是「这次要拉的总笔数」，翻页时每页都保持同一个值，
    # 客户端才能显示「正在恢复 120/500」。
    total = db.scalar(select(func.count()).select_from(Txn).where(*conds))

    # 翻页锚点用「秒级 updated_at + client_uuid」复合：同一秒内被改的几笔也有确定的先后。
    if full and cursor:
        c_ts, c_uuid = _decode_cursor(cursor)
        conds.append(or_(ts_key > c_ts, (ts_key == c_ts) & (Txn.client_uuid > c_uuid)))

    q = select(Txn).where(*conds)
    rows = db.scalars(q.order_by(ts_key.asc(), Txn.client_uuid.asc()).limit(limit)).all()

    if not full:
        return [TxnOut(**txn_payload(r)) for r in rows]

    items = [TxnOut(**txn_payload(r)) for r in rows]
    next_cursor = _encode_cursor(rows[-1]) if len(rows) == limit and rows else None
    return {"items": items, "next_cursor": next_cursor, "total": total}


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
