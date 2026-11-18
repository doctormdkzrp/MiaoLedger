# RUNBOOK · 小喵记账

> 面向「操作者」：出问题时照着做，不需要理解原理。
> 最后一节「全貌」是给半年后的自己看的，链路上谁在哪、数据在哪。

---

## 一、三分钟急救

**先看它还活着没**（任何机器上执行都行）：

```bash
curl -s https://jz.doctormdkzrp.cn/health
```

返回 `{"ok":true,"time":"...","version":"1.1.1"}` 就是活的。返回别的东西按下表处理。

| 你看到的 | 大概是什么 | 一条命令修 |
|---|---|---|
| 没反应 / 超时 | 容器挂了或 Caddy 挂了 | `ssh` 进 ECS 后 `docker restart ledger-api caddy` |
| `502 Bad Gateway` | Caddy 活着，后面 API 没起或刚重启 | `docker ps` 看 `ledger-api` 在不在，不在就 `docker restart ledger-api` |
| `502` 且日志有 `Permission denied` | 数据目录权限被改动（容器内是 uid 10001） | `chown -R 10001:10001 /opt/ledger/data` 再重启 |
| 证书警告 / `NET::ERR_CERT_*` | 证书没续上（Let's Encrypt 偶尔连不通） | `docker restart caddy`，看日志里 `certificate obtained successfully` |
| App 里提示「连不上服务器」 | **先看服务端日志再说**，别急着怀疑网络 | `docker logs -t --since 30m ledger-api` |

**服务在 ECS 上**（`jz.doctormdkzrp.cn` → 39.98.91.134），SSH 只走 Tailscale（公网 22 已关）。
没有 tailnet 时用 Hermes 的中转：`/opt/data/scripts/ecs_run.py "命令"`。

---

## 二、症状 → 先查什么 → 怎么修

### 1. 数据不对（少了账 / 多了账）

```bash
# 看库里到底有多少
docker exec ledger-api python -c "import sqlite3;c=sqlite3.connect('/data/miaoledger.db');print(c.execute('select count(*),sum(amount_cents) from txns').fetchone())"
```

- **App 是主库**，服务端只是备份点。App 里对上、服务端对不上 → 让 App 重新上行（下拉刷新/重登）。
- 反过来服务端有、App 没有 → 用 App 的「整库拉回」（只在新设备或清空本地库后触发）。
- 别手工改库：`client_uuid` 是唯一键，手写的行会在下次同步时被覆盖。

### 2. 登录不上（`403` + 提示设备待批准）

新设备要管理员批。批的办法（服务端命令行）：

```bash
docker exec ledger-api python -m app.cli users                     # 看账号 id
docker exec -it ledger-api python -c "
import sqlite3;c=sqlite3.connect('/data/miaoledger.db')
c.execute(\"update devices set status='approved' where status='pending'\");c.commit()
print('approved', c.total_changes)"
```

（管理台暂时没有设备页面，先用这条命令；有页面后删掉上面这段。）

### 3. 被刷 / 被扫

- 限流在应用内：单 IP 每分钟 120 次，超了 `429`。临时放宽/收紧改环境变量 `RATE_LIMIT_PER_MIN` 后重建容器。
- 想看谁在打：`docker logs --tail 200 ledger-api` 与 Caddy 的 `/opt/ledger/caddy/data/access.log`。
- 被打崩了（CPU 100% / 带宽满）：先把 443 关掉止血 —— 安全组里删掉 443 入方向，或在 Caddy 前面加一条 `@block path` 规则。

### 4. 备份 / 恢复

- 每天 **03:00** 自动跑：SQLite 一致性快照 → `oss://zrp-ledger-backup/daily/`（30 天生命周期，本地留 14 天）。
- 手动补一次：`/opt/ledger/backup.sh`
- **恢复**（把某天的备份换回去）：

```bash
# 1) 先停服务，备份当前库（别覆盖丢证据）
docker stop ledger-api
cp /opt/ledger/data/miaoledger.db /opt/ledger/data/miaoledger.db.bak-$(date +%s)
# 2) 从 OSS 拉回来（ECS 上 ossutil 装在 /root/ossu/ossutil-2.1.1-linux-amd64/ossutil）
O=/root/ossu/ossutil-2.1.1-linux-amd64/ossutil
$O cp oss://zrp-ledger-backup/daily/<文件名>.db /opt/ledger/data/miaoledger.db \
   -e oss-cn-zhangjiakou.aliyuncs.com --region cn-zhangjiakou -c /root/.ossutilconfig2
chown 10001:10001 /opt/ledger/data/miaoledger.db
# 3) 起服务并核对笔数与金额合计
docker start ledger-api
docker exec ledger-api python -c "import sqlite3;c=sqlite3.connect('/data/miaoledger.db');print(c.execute('select count(*),sum(amount_cents) from txns').fetchone())"
```

### 5. 装 App（APK）

手机浏览器直接开：`https://jz.doctormdkzrp.cn/apk/haoli-1.1.0-debug.apk`
新包放 `/opt/ledger/apk/` 即可，不用重启（只读挂载）。

---

## 三、全貌（链路与数据在哪）

```
手机 App（本地 SQLite 是主库）
   │  HTTPS  https://jz.doctormdkzrp.cn
   ▼
Caddy（ECS，443，自动签/续证书，限请求体 12MB）
   │  127.0.0.1:8000
   ▼
ledger-api 容器（FastAPI，非 root uid 10001，单 IP 限流 120/min）
   │
   ├─ /data/miaoledger.db      ← SQLite，唯一的数据文件
   ├─ /apk/*.apk               ← 安装包（只读挂载）
   ├─ 火山 ASR / DeepSeek      ← 语音识别、自然语言提问（外网 API）
   └─ 每天 03:00 dump → OSS 桶 zrp-ledger-backup（30 天）

NAS（家里）: 1.0.1 旧版本仍在跑，作为回滚备份；不再对外
```

**关键路径**

| 东西 | 在哪 |
|---|---|
| 代码 | `github.com/doctormdkzrp/MiaoLedger`（main），构建机是家里 50.10 的 `F:\Git\YYJZ` |
| 镜像 | `ledger-api:<版本>`（NAS 上 build → `docker save` → 传 ECS → `docker load`） |
| 容器 env | `/opt/ledger/ledger.env`（0600，含 INVITE_CODE / ADMIN_USERNAME / DEEPSEEK_* / VOLC_*） |
| 数据库 | `/opt/ledger/data/miaoledger.db` |
| APK | `/opt/ledger/apk/` |
| 备份脚本 | `/opt/ledger/backup.sh` + `/etc/cron.d/ledger-backup` |
| Caddy 配置 | `/opt/ledger/caddy/Caddyfile`；证书在 `/opt/ledger/caddy/data/` |
| 管理台 | 仓库 `admin/`（目前只在 NAS 上有一份 1.0.0，未接 ECS） |

**安全边界（改之前先读）**

- 公网只开 80（主域名站点 + 备案核验）、443（本服务）、1883（MQTT，要密码）；22 只走 Tailscale。
- API 文档（`/docs`、`/openapi.json`）生产默认关闭，要看就临时设 `ENABLE_DOCS=1`。
- 限流/体积上限在 `server/app/guard.py`；`TRUST_PROXY` 只在前面加了 CDN 时才设 1。
- 认证三件套：6 位码 + 新设备需批准 + 连错 5 次锁 10 分钟。
