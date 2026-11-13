# 小喵记账 · 管理台

小喵记账的 Web 管理台，纯前端静态站点。

页面数据全部来自服务端 `/api/v1` 接口，不含 mock 数据。

## 技术选型

| 项 | 选择 | 说明 |
| --- | --- | --- |
| 框架 | Vue 3.5 + `<script setup>` + TypeScript | 单文件组件，组合式 API |
| 构建 | Vite 7 | 构建目标 es2019，`element-plus` 与其余依赖分包 |
| 路由 | vue-router 4（hash 模式） | 静态托管时不依赖后端 rewrite |
| 状态 | Pinia | 仅登录态一个 store |
| UI | Element Plus 2.11 | 表格、表单、弹窗组件，中文文案完整 |
| 请求 | axios 封装（`src/utils/http.ts`） | 统一注入 Bearer，统一解析后端 `detail` 中文错误 |

## 目录结构

```
admin/
├─ src/
│  ├─ api/          接口层，按后端模块拆分（auth / meta / txns / summary / ai / io / admin）
│  ├─ components/   MiaoLogo.vue：品牌标识
│  ├─ layouts/      MainLayout.vue：左侧菜单 + 顶栏（昵称、角色、退出）
│  ├─ router/       路由表与登录/角色守卫
│  ├─ stores/       Pinia（当前用户与 token）
│  ├─ styles/       全局样式与主题变量
│  ├─ utils/        http 封装、登录态存储、金额/时间格式化
│  └─ views/        页面（Login / Books / Txns / ImportExport / AiProfile / Account / NotFound / admin/Users + admin/UserDetail）
├─ public/          静态资源（favicon）
├─ Dockerfile       多阶段构建：node 构建 → nginx 托管
├─ nginx.conf       静态托管 + /api 反代到 api:8000
├─ .env.example     环境变量样例
└─ vite.config.ts   别名、dev 代理、分包
```

## 页面

| 路由 | 页面 | 说明 |
| --- | --- | --- |
| `/login` | 登录 | 账号 + 6 位数字密码，token 存 localStorage |
| `/books` | 我的账本 | 账本增改删（`/meta`、`/books`），账户与分类只读展示 |
| `/txns` | 我的账单 | 月度汇总卡片（`/summary`）+ 明细（`/txns`），可改可删 |
| `/io` | 导入导出 | 8 列 CSV 导出（带 token 拉 blob）与导入 |
| `/ai` | 我的 AI 提示词 | `/ai/profile` 读写，500 字上限 + 字数统计 + 版本/反馈信息 |
| `/account` | 我的账号 | 资料展示 + 改密码（`/auth/change-pin`） |
| `/admin/users` | 用户管理 | 仅 `role=admin` 可见：建号、改昵称/角色/重置密码；详情抽屉里查看账单分页、代记/改/删账、改 AI 提示词、导入导出 |

非管理员登录后侧边栏不显示「用户管理」，直接访问地址会被守卫重定向到「我的账本」。

## 三种运行方式

### 1. 本地开发

```bash
cd admin
pnpm install
cp .env.example .env.local   # Windows: copy .env.example .env.local
pnpm dev
```

开发服务器默认监听 `http://127.0.0.1:8848`，`/api` 由 vite 代理到 `http://127.0.0.1:8000`。修改 `VITE_PROXY_TARGET` 可指向其他后端。

### 2. 本地构建与预览

```bash
cd admin
pnpm install
pnpm build      # 产物在 dist/
pnpm preview    # 预览构建产物
```

类型检查单独执行 `pnpm typecheck`（`vue-tsc --noEmit --skipLibCheck`），项目未配置 lint 脚本。

### 3. Docker

管理台镜像内部的 nginx 将 `/api` 反向代理到主机名 `api:8000`，因此容器运行时需要有一个可达的 `api` 主机名。常规做法是随 compose 一起启动，`/api` 由 compose 中的 `api` 服务承接：

```bash
# 在仓库根目录
docker compose up -d --build
# 管理台默认 http://localhost:8080
```

单独构建镜像用 `docker build -t miao-ledger-admin .`。以 `docker run` 启动时须把 `api` 指向一个真实可访问的服务端地址，仅将 `api` 指向容器自身会导致接口不可用。

## 环境变量

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `VITE_API_BASE_URL` | `/api` | 接口基地址，业务路径以 `/v1/` 开头 |
| `VITE_PROXY_TARGET` | `http://127.0.0.1:8000` | 仅开发服务器使用的代理目标 |
| `VITE_PUBLIC_PATH` | `/` | 静态资源基础路径 |
| `VITE_PORT` | `8848` | 开发服务器端口 |

生产环境只需要 `VITE_API_BASE_URL=/api`，转发由 nginx 完成。

## 注意事项

- 前端不保存密码，只保存后端下发的 device token（localStorage：`miao-token`、`miao-user`）。
- 错误提示直接显示后端返回的中文 `detail`。只有会话失效的 `401`（缺少 token / token 无效 / 用户不存在）才清除登录态并跳转登录页；登录与改密码处的 `401` 仅提示文案。
- 品牌色为淡蓝 `#5aa9f0`（与手机端一致），主题变量集中在 `src/styles/index.css` 的 `:root`。
- 导出 CSV 用 axios 拉取 blob 再触发下载，浏览器直接打开链接不会带 Authorization 头。
- 容器内 nginx 监听 80，宿主机端口由 compose 的 `ADMIN_PORT`（默认 8080）映射。
