# 参与开发

## 本地运行

三个组件可分别运行，互不强依赖，App 只需要一个可访问的服务端地址。

```bash
# 1. 服务端（默认 SQLite，不配 Key 也可使用）
cd server
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 2. 管理台（另开终端）
cd admin
pnpm install
pnpm dev                             # http://localhost:8848

# 3. Android（再开终端）
cd android
./gradlew assembleDebug              # Windows: gradlew.bat assembleDebug
```

管理台开发服务器默认监听 8848，端口由 `admin/vite.config.ts` 的 `server.port` 读取 `VITE_PORT` 决定。

## 提交前检查

- 服务端：`cd server && python -m pytest -q` 须全部通过。
- 管理台：`cd admin && pnpm typecheck` 与 `cd admin && pnpm build` 须成功。项目未配置 lint 脚本，`admin/package.json` 的脚本为 `dev`、`build`、`preview`、`typecheck`。
- Android：`cd android && ./gradlew assembleDebug` 须成功，Windows 下写作 `gradlew.bat assembleDebug`。
- 推送后 CI 会分别执行上述构建，四个 job 为服务端测试、Android 构建、管理台构建、镜像构建。

## 代码风格

- 服务端：PEP 8，类型注解写全。错误一律 `HTTPException(status_code=状态码, detail="中文说明")`，前端直接展示 `detail`。
- Android：Kotlin 官方风格。Compose 中颜色与字号统一取自 `ui/Theme.kt`，页面内不写十六进制色值。
- 管理台：使用仓库内的 TypeScript 配置，提交前执行 `pnpm typecheck`。

## 数据模型改动

- 新增表或字段须同时考虑 SQLite 与 PostgreSQL。老库升级在 `app/db.py` 的 `init_db()` 中平滑补列，已部署的实例升级后应能正常启动。
- 软删除：账单、分类、账本以 `deleted` 字段置位，不做物理删除，多端增量同步依赖该字段。

## 提交信息

标题一行说明改了什么，不超过 50 字，不加句号。正文解释为什么改、机制如何、有什么后果。不写「fix bug」「update」这类标题，不写自我评价。

示例：

```
一句话记账支持相对日期解析

原来只识别「昨天」「今天」，现在支持「前天」「上周三」「三天前」，
解析失败时退回当天。补充 6 个单测覆盖上述写法。
```

## 不要提交的内容

`.gitignore` 已覆盖大部分情形，以下仍需注意：

- 任何 Key、token、`.env` 真值。
- 数据库文件、APK、日志、`node_modules/`、构建产物。
- 签名密钥（`*.jks` / `*.keystore`）。
- 部署服务器的真实 IP、域名、内网地址。

## 反馈问题

缺陷与功能建议通过 [.github/ISSUE_TEMPLATE/](.github/ISSUE_TEMPLATE/) 中的模板提交。安全问题的报告方式见 [SECURITY.md](SECURITY.md)。
