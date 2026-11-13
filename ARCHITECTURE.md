# 架构说明

系统分为三个组件，职责边界明确：手机端负责记账与查看，服务端负责存储与计算，管理台负责维护数据。

```
┌─────────────────────┐        ┌──────────────────────┐        ┌─────────────────┐
│  Android (Compose)  │  HTTP  │  FastAPI + SQLAlchemy │  SQL   │  PostgreSQL /   │
│  本地 SQLite 为主库  │ ─────► │  /api/v1/*            │ ─────► │  SQLite         │
└─────────────────────┘        └──────────────────────┘        └─────────────────┘
         ▲                              ▲
         │ 后台同步                      │ /api/v1/admin/*
         │                              │
         └──────────────────────  ┌─────┴──────────────┐
                                  │  Vue 管理台 (admin) │
                                  └────────────────────┘
```

## 客户端（`android/`）

- Kotlin + Jetpack Compose，单 Activity（`MainActivity`）。依赖中包含 `navigation-compose`，当前页面切换由手写状态机完成，未使用 Hilt 与 Room。
- 本地优先：`data/Models.kt` 中的 `LocalDb`（`SQLiteOpenHelper`）是记账操作的写入方，断网时可继续记账。`data/Api.kt` 负责与服务端对账，账单以 `client_uuid` 作为幂等键，重复上传不会重复入账。
- 后台同步：`data/Backup.kt` 使用 `WorkManager` 定时补传，周期为 6 小时。记完一笔后延迟 30 秒触发一次单次任务，App 启动时立即尝试一次，失败不做提示。
- 一句话记账：`ui/Asr.kt` 负责录音与上传（可选功能）。文本提交服务端 `/ai/parse`，解析为 `{kind, amount_cents, category, occurred_at, note}`。本地规则引擎先给出兜底结果，模型不可用时使用该结果。
- 账目提问由客户端本地作答，服务端不参与计算。
- 主题、颜色与字号集中在 `ui/Theme.kt`，通用组件（二级页、列表行、金额输入）在 `ui/Common.kt`。

## 服务端（`server/`）

| 文件 | 职责 |
|---|---|
| `app/main.py` | 业务路由：账本 / 账户 / 分类 / 账单 / 汇总 / CSV 导入导出，以及 `/health` |
| `app/auth_api.py` | 注册、登录、改密码、登出（Bearer device token） |
| `app/auth.py` | 口令哈希与校验、token 签发、当前用户解析、角色常量 |
| `app/ai_api.py` | AI 解析、反馈学习、规则、用户提示词 |
| `app/ai.py` | 规则引擎兜底与提示词组装 |
| `app/learning.py` | 将改类记录沉淀为规则，供后续解析引用 |
| `app/asr.py` | 语音转写（可选，未配置 Key 时返回 503） |
| `app/models.py` | SQLAlchemy 模型：`User` / `Device` / `Book` / `Account` / `Category` / `Txn` / `LearnedRule` / `UserAiProfile` |
| `app/schemas.py` | Pydantic 出入参 |
| `app/common.py` | 默认账本、账户、分类，CSV 八列口径与导入导出辅助函数 |
| `app/db.py` | 数据库连接、建表与老库补列 |
| `app/cli.py` | 命令行工具：`users` / `add-user` / `reset-pin` / `promote` |
| `app/admin_api.py` | 管理台接口（`/api/v1/admin/*`），仅 `role=admin` 可访问 |

以下为设计层面的固定约定：

- 数据按账号严格隔离：所有查询强制 `user_id = 当前 token 的用户`，越权一律返回 404，不区分「不存在」与「无权访问」。
- 软删除：分类、账本、账单均以 `deleted` 字段置位，不做物理删除，以便多端增量同步收到删除事件。
- AI 为可选功能：未配置任何 Key 时，`app/ai.py` 的规则引擎（中文数字、关键词最长匹配、相对日期）仍可将「午饭 25 块微信」解析为一条账单；配置 `DEEPSEEK_API_KEY` 后调用模型。
- 提示词由用户维护：每个账号有一份不超过 500 字的自定义提示词（`UserAiProfile.hints`），参与解析提示词拼接，可在管理台修改。

## 管理台（`admin/`）

Vue 3 + Vite + Element Plus，构建产物为静态文件，由 nginx 托管，`/api` 反向代理到 `api:8000`。生产环境同源，无需配置 CORS。

- 普通用户登录后可查看与修改自己的账本、账单、提示词、密码，导入导出 CSV。
- `role=admin` 额外具备「用户管理」：创建账号、重置用户名与密码、修改角色、代管任意账号的账单与提示词。
- 前端只控制菜单显隐，权限判定在服务端完成。

## 部署（默认 Docker）

根目录 `docker-compose.yml` 启动三个服务：`db`（postgres:16）、`api`（uvicorn）、`admin`（nginx）。数据保存在 `db_data` 卷中，升级镜像不丢数据。

仅使用接口、不启动管理台时执行 `docker compose up -d db api`，手机端的服务器地址填写 `http://<主机局域网 IP>:8000`。

## 刻意的设计选择

- 不提供共享账本：每个账号各自记账、互不可见，共享账本会显著增加权限模型的复杂度。管理员经管理台代管数据属例外情形。
- 不提供云同步服务：项目为自部署形态，不运营托管服务，数据保存在部署者自行管理的服务器上。
- Android 不打包任何 API Key：所有密钥只从服务端环境变量读取，APK 内不含凭据。
