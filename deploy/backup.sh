#!/bin/sh
# 小喵记账：每日 03:00 把 SQLite 库 dump 一份到 OSS（标准存储，30 天生命周期）。
# 由 /etc/cron.d/ledger-backup 调度，root 跑。
set -eu

TS=$(date +%Y%m%d-%H%M)
LOCAL_DIR=/opt/ledger/backup
OUT="$LOCAL_DIR/miaoledger-$TS.db"
OSSUTIL=/root/ossu/ossutil-2.1.1-linux-amd64/ossutil
CFG=/root/.ossutilconfig2
EP=oss-cn-zhangjiakou.aliyuncs.com
REGION=cn-zhangjiakou
BUCKET=zrp-ledger-backup

mkdir -p "$LOCAL_DIR"

# 1) 一致性快照：必须用 sqlite3 的 backup API，直接 cp 正在写的库会拿到半截
docker exec ledger-api python -c "
import sqlite3
src = sqlite3.connect('/data/miaoledger.db')
dst = sqlite3.connect('/data/_backup.db')
src.backup(dst)
dst.close(); src.close()
print('snapshot ok')
"
docker cp ledger-api:/data/_backup.db "$OUT"
docker exec ledger-api sh -c 'rm -f /data/_backup.db' || true
chmod 600 "$OUT"

# 2) 上传（同名对象覆盖，日期在文件名里）
"$OSSUTIL" cp "$OUT" "oss://$BUCKET/daily/" \
    -e "$EP" --region "$REGION" -c "$CFG" >/dev/null

# 3) 本地只留 14 天，OSS 侧靠生命周期 30 天
find "$LOCAL_DIR" -name 'miaoledger-*.db' -mtime +14 -delete

echo "$(date '+%F %T') backup ok $(basename "$OUT") $(wc -c < "$OUT") bytes"
