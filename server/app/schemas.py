"""请求/响应模型。金额一律用"分"（整数）在接口里传输，字段名带 _cents。"""
from datetime import datetime

from pydantic import AliasChoices, BaseModel, Field


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=32)
    pin: str = Field(min_length=4, max_length=32)
    device_name: str = "android"


class RegisterIn(LoginIn):
    # 邀请码：契约字段名 invite_code，同时兼容旧客户端发来的 code。
    invite_code: str = Field(default="", validation_alias=AliasChoices("invite_code", "code"))
    display_name: str = ""


class TokenOut(BaseModel):
    token: str
    username: str
    display_name: str
    role: str = "user"


class MeOut(BaseModel):
    username: str
    display_name: str
    role: str = "user"
    books: int
    accounts: int
    categories: int
    txns: int


class BookIn(BaseModel):
    name: str = Field(min_length=1, max_length=32)
    icon: str = "🏠"
    sort: int = 0


class AccountIn(BaseModel):
    name: str = Field(min_length=1, max_length=32)
    kind: str = "virtual"
    balance0_cents: int = 0
    sort: int = 0


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=32)
    parent_id: int | None = None
    kind: str = "out"
    icon: str = "🏷"
    sort: int = 0


class TxnIn(BaseModel):
    client_uuid: str = Field(min_length=8, max_length=40)
    book_id: int | None = None
    cat_id: int | None = None
    account_id: int | None = None
    kind: str = "out"
    amount_cents: int
    occurred_at: datetime
    note: str = ""
    source: str = "manual"
    deleted: bool = False


class TxnPatchIn(BaseModel):
    """部分更新：只改传上来的字段，其余保持原值。"""

    book_id: int | None = None
    cat_id: int | None = None
    account_id: int | None = None
    kind: str | None = None
    amount_cents: int | None = None
    occurred_at: datetime | None = None
    note: str | None = None


class TxnOut(TxnIn):
    id: int
    updated_at: datetime


class PushIn(BaseModel):
    txns: list[TxnIn]


class PushOut(BaseModel):
    accepted: int
    created: int
    updated: int
    server_time: datetime


class AiTargets(BaseModel):
    """AI 反馈里「解析结果 / 用户最终结果」的定位字段，只认 ID。"""
    kind: str | None = None
    cat_id: int | None = None
    account_id: int | None = None
    book_id: int | None = None


class NewCategoryIn(BaseModel):
    """用户采纳「新建分类」建议时带上来的新分类。"""
    name: str = Field(min_length=1, max_length=32)
    kind: str = "out"
    icon: str = "🏷"


class FeedbackIn(BaseModel):
    text: str = Field(min_length=1, max_length=300)
    note: str | None = None
    parsed: AiTargets | None = None
    final: AiTargets | None = None
    new_category: NewCategoryIn | None = None


class ChangePinIn(BaseModel):
    """改密码。不在这里做长度/格式校验：错误提示要由端点原样返回中文文案给 App。"""
    old_pin: str = ""
    new_pin: str = ""


class ParseIn(BaseModel):
    text: str = Field(min_length=1, max_length=300)
    book_id: int | None = None
    now: datetime | None = None


class ParseOut(BaseModel):
    ok: bool
    kind: str = "out"
    amount_cents: int | None = None
    cat_id: int | None = None
    cat_name: str | None = None
    account_id: int | None = None
    account_name: str | None = None
    book_id: int | None = None
    book_name: str | None = None
    occurred_at: datetime | None = None
    note: str = ""
    confidence: float = 0.0
    raw: dict | None = None
    needs: list[str] = []  # 需要用户确认的字段
    # 新商户建议：{name, kind, icon}；确实拿不准又有新词时才给，App 弹「要新建这个分类吗」
    suggest_category: dict | None = None


class AiProfileIn(BaseModel):
    """手动改 AI 提示词。长度在端点里检查，为的是给中文提示（422 文案）。"""
    hints: str = ""


class AdminUserIn(BaseModel):
    username: str = ""
    pin: str = ""
    display_name: str = ""
    role: str = "user"


class AdminUserPatchIn(BaseModel):
    username: str | None = None
    display_name: str | None = None
    pin: str | None = None
    role: str | None = None


class AdminTxnIn(BaseModel):
    """管理台单笔新建：client_uuid 由服务端生成，所以不从这里收。"""
    book_id: int | None = None
    cat_id: int | None = None
    account_id: int | None = None
    kind: str = "out"
    amount_cents: int = 0
    occurred_at: datetime | None = None
    note: str = ""
    source: str = "manual"
