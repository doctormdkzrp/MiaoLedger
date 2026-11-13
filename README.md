# 小喵记账

一个自部署的家庭记账系统。

[![CI][ci-badge]][ci-link]
[![Release][release-badge]][release-link]
[![License][license-badge]][license-link]

<p align="center">
  <img src="docs/images/logo.svg" width="96" alt="小喵记账">
</p>

仓库包含三个可独立运行的组件：

- `android/` —— Android 客户端（Kotlin + Jetpack Compose）。账本主库为手机本地 SQLite。
- `server/` —— 服务端（FastAPI + SQLAlchemy）。负责多端同步、汇总统计与 AI 解析。
- `admin/` —— Web 管理台（Vue 3 + Element Plus）。构建为静态文件，由 nginx 托管。

客户端以本地数据库为写入起点：记账先落本地，联网后按 `client_uuid` 幂等补传。服务端是同步与备份的落点，不作为账本的唯一副本。

---

## 界面

手机端为淡蓝色主配色，底部四个 Tab：

| Tab | 内容 |
|---|---|
| 明细 | 本月支出、收入、结余，账本切换，逐笔流水 |
| 统计 | 支出构成环形图、支出排行、月度对比、按日支出日历 |
| AI | 记账助手：一句话记账与账目提问，入口可查看学到的规则 |
| 我的 | 账号、备份状态、分类配置、账单导出、版本号 |

中间为加号按钮，点击进入手动记账，长按进入语音记账。

管理台为左侧菜单式网页，含我的账本、我的账单、导入导出、我的 AI 提示词、我的账号；管理员账号额外显示用户管理。

## 环境要求

| 用途 | 要求 |
|---|---|
| 跑服务端 | Python 3.12+、pip |
| 跑管理台 | Node.js 20.19+ 或 22.13+（见 `admin/package.json` 的 `engines`）、pnpm 10+ |
| 编译 Android | JDK 17+（CI 使用 21）、Android SDK（compileSdk 36）、Gradle 8.14.3（仓库自带 wrapper） |
| 部署 | Docker 与 Docker Compose v2 |

仅部署、不开发时只需要 Docker。

## 快速开始（Docker）

```bash
git clone https://github.com/doctormdkzrp/MiaoLedger.git
cd MiaoLedger
cp .env.example .env
docker compose up -d
```

启动前须编辑 `.env`，把 `POSTGRES_PASSWORD` 设为自定的强口令；留空会导致 compose 拒绝启动。Windows 下复制文件用 `Copy-Item .env.example .env`。

启动后的地址：

| 服务 | 地址 |
|---|---|
| 管理台 | <http://localhost:8080> |
| 接口文档 | <http://localhost:8000/docs> |
| 健康检查 | <http://localhost:8000/health> |

手机端在欢迎页「高级设置」里的「服务器地址」填写 `http://<主机局域网 IP>:8000`。

## 账号与管理员

账号名限 2–20 位英文字母、数字或下划线，密码为 6 位数字。

首次使用须先创建账号。默认 `INVITE_CODE` 为空，允许开放注册；设置该变量后，注册须填写正确的邀请码，否则返回 403。

管理台的「用户管理」要求账号具备 `role=admin`。提升管理员有两种方式，任选一种。

方式一：编辑 `.env` 中已存在的 `ADMIN_USERNAME=` 行，填入用户名，再重建容器。`restart` 不会重新读取 `.env`，`up -d` 检测到环境变量变更后会重建容器：

```bash
docker compose up -d api
```

方式二：在运行中的容器里直接提升：

```bash
docker compose exec api python -m app.cli promote <用户名>
```

尚无账号时可先用命令行创建，再提升为管理员：

```bash
docker compose exec api python -m app.cli add-user admin 123456 管理员
docker compose exec api python -m app.cli promote admin
```

命令行工具支持 `users`、`add-user <账号> <密码> [显示名]`、`reset-pin <账号> <新密码>`、`promote <账号>` 四个子命令。

## 本地运行服务端

```bash
cd server
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Windows 下激活虚拟环境用 `.venv\Scripts\activate`。

不配置任何 Key 时，服务端使用默认 SQLite 与内置规则引擎。健康检查：

```bash
curl http://localhost:8000/health
```

返回内容形如 `{"ok":true,"time":"2026-11-13T09:30:00","version":"1.0.0"}`，`version` 与 `server/app/main.py` 的 `APP_VERSION` 一致。

运行测试：

```bash
cd server
python -m pytest -q
```

## 运行管理台

```bash
cd admin
pnpm install
pnpm dev
```

开发服务器监听 `http://localhost:8848`，`/api` 由 vite 代理到 `http://127.0.0.1:8000`。

生产构建执行 `pnpm build`，产物在 `admin/dist/`。

## 编译 Android

```bash
cd android
./gradlew assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

产物在 `app/build/outputs/apk/debug/app-debug.apk`。Windows 下把 `./gradlew` 换成 `gradlew.bat`。

仓库不含签名密钥，debug 包使用本机生成的调试签名。构建 release 包须自备 keystore，并新增 release 的 `signingConfig` 挂到 release buildType。现有 `android/app/build.gradle.kts` 的 `signingConfigs` 只有 `debug` 一项。

不在本地搭建 Android 工具链时，可使用 CI 产物：推送到 `main`、提交拉取请求或手动触发工作流时都会构建 debug APK，在 Actions 页面下载 `miaoledger-debug-apk` 安装。

## 配置说明

服务端通过环境变量配置。本地运行时由 shell 提供，Docker 部署时来自根目录 `.env`。

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./data/miaoledger.db` | 数据库连接串。生产建议使用 PostgreSQL：`postgresql+psycopg://user:pass@db:5432/miaoledger` |
| `INVITE_CODE` | 空 | 注册邀请码。留空表示允许任何人注册；设置后注册须填写正确值，否则返回 403 |
| `ADMIN_USERNAME` | 空 | 启动时将该用户名提升为 `admin` |
| `DEEPSEEK_API_KEY` | 空 | 大模型 Key。留空时仅使用内置规则引擎解析 |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | 兼容 OpenAI 协议的端点 |
| `DEEPSEEK_MODEL` | `deepseek-chat` | 模型名 |
| `VOLC_API_KEY` | 空 | 火山引擎语音识别 Key。留空时 `/api/v1/asr` 返回 503，客户端提示语音功能未启用 |
| `VOLC_RESOURCE_ID` | `volc.seedasr.sauc.duration` | 语音识别资源 ID |
| `CORS_ORIGINS` | 空 | 逗号分隔的允许来源。管理台由 nginx 同源反代，通常无需配置 |
| `APK_DIR` | `/apk` | 该目录存在时以只读静态文件方式挂载到 `/apk`，用于分发 APK |
| `TZ` | `Asia/Shanghai` | 容器时区，影响服务端记录的时间戳。服务端代码不直接读取该变量 |

Docker 部署的 `api` 服务只透传其中九项：`DATABASE_URL`、`INVITE_CODE`、`ADMIN_USERNAME`、`DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL`、`VOLC_API_KEY`、`VOLC_RESOURCE_ID`、`TZ`。

`CORS_ORIGINS` 与 `APK_DIR` 需自行加到 `docker-compose.yml` 的 `api.environment` 才会生效。`DATABASE_URL` 由 `POSTGRES_USER`、`POSTGRES_PASSWORD`、`POSTGRES_DB` 在 compose 中强制拼装，直接改该变量无效。

Docker 部署另使用 `POSTGRES_USER`、`POSTGRES_PASSWORD`、`POSTGRES_DB`、`API_PORT`（默认 8000）、`ADMIN_PORT`（默认 8080）。

管理台读取四个变量：

| 变量 | 默认值 | 生效时机 | 说明 |
|---|---|---|---|
| `VITE_API_BASE_URL` | `/api` | 构建时 | 接口前缀，替换进产物 |
| `VITE_PUBLIC_PATH` | `/` | 构建时 | 静态资源基础路径 |
| `VITE_PORT` | `8848` | 仅开发时 | 开发服务器端口 |
| `VITE_PROXY_TARGET` | `http://127.0.0.1:8000` | 仅开发时 | `/api` 的代理目标 |

样例见 [admin/.env.example](admin/.env.example) 与 `admin/.env.development`。

## 功能

### 手机端

- 一句话记账：文字或语音输入后自动判定收支方向、金额、分类与日期。识别结果可逐项修改，修改记录会沉淀为学到的规则，供后续解析参考。
- 账目提问：可就本月支出、分类构成、月度对比等提问。作答在客户端本地完成，服务端不参与。
- 本地优先：账本存储于手机 SQLite，离线可用；联网后自动补传，同一 `client_uuid` 重复上传不会重复入账。
- 多账本可在客户端新建。
- 资产账户与分类在注册时预置：账户四个（微信、支付宝、建行、现金），分类 15 个。分类可在「我的 → 分类配置」中增删。
- 资产账户当前版本不提供新增入口。
- 导出 CSV，固定 8 列：时间、金额、收支、分类、资产账户、账本、货币、备注。导入通过管理台或服务端接口完成。

### 管理台

- 查看与修改自己的账本、账单、AI 提示词、密码。
- 导入导出 CSV。
- 管理员额外具备：创建账号、重置用户名与密码、修改角色、代管任意账号的账单与提示词、单独导出指定账号的数据。

### 数据隔离

每个账号只能访问自身 `user_id` 名下的数据，所有查询强制按当前 token 的用户过滤。越权访问一律返回 404，不区分「不存在」与「无权访问」。

系统不提供共享账本。多个账号各自独立记账，互不可见；仅管理员经管理台代管的情形例外。

## 接口

完整接口文档在服务端启动后通过 `/docs` 查看（FastAPI 自带 Swagger）。常用接口：

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/auth/register` | 注册，返回 device token |
| POST | `/api/v1/auth/login` | 登录 |
| POST | `/api/v1/txns` | 批量上传账单（幂等） |
| GET | `/api/v1/txns?since=2026-11-01T00:00:00` | 拉取增量，`since` 为 ISO 时间串 |
| GET | `/api/v1/summary?month=YYYY-MM` | 月度汇总 |
| POST | `/api/v1/ai/parse` | 一句话解析为结构化账单 |
| GET/PUT | `/api/v1/ai/profile` | 读写当前账号的 AI 提示词 |
| POST | `/api/v1/import/csv` | 导入 CSV |
| GET | `/api/v1/export.csv?from=YYYY-MM-DD&to=YYYY-MM-DD` | 导出 CSV |
| GET | `/api/v1/admin/users` | 用户列表（仅 admin） |

## 项目结构

```
android/        Android App（Kotlin + Jetpack Compose）
server/         服务端（FastAPI + SQLAlchemy）
admin/          管理台（Vue 3 + Element Plus + Vite）
docs/images/    README 使用的 logo（界面截图不入库）
docker-compose.yml
```

细节见 [ARCHITECTURE.md](ARCHITECTURE.md)。

## 参与开发

见 [CONTRIBUTING.md](CONTRIBUTING.md)。缺陷与功能建议通过 Issue 模板提交，安全问题的报告方式见 [SECURITY.md](SECURITY.md)，社区行为约定见 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。

## 版本变更

见 [CHANGELOG.md](CHANGELOG.md)。

## 开源协议

本项目采用 [MIT](LICENSE) 协议。

第三方依赖多为 MIT、Apache-2.0、BSD-3-Clause 等宽松协议，均允许商用、修改与闭源分发，须保留版权声明。`psycopg`（PostgreSQL 驱动）为 LGPL-3.0，以依赖形式调用，不影响本项目自身的协议选择。

[ci-badge]: https://github.com/doctormdkzrp/MiaoLedger/actions/workflows/ci.yml/badge.svg
[ci-link]: https://github.com/doctormdkzrp/MiaoLedger/actions/workflows/ci.yml
[release-badge]: https://img.shields.io/github/v/release/doctormdkzrp/MiaoLedger
[release-link]: https://github.com/doctormdkzrp/MiaoLedger/releases
[license-badge]: https://img.shields.io/badge/license-MIT-blue.svg
[license-link]: LICENSE