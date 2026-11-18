#!/usr/bin/env python3
"""记账库搬迁：PostgreSQL -> SQLite（两个容器里都能跑）。

用法（dump 在 NAS 的容器里跑，load 在 ECS 的容器里跑）：
  python mig.py dump /mig/out     # 源：env DATABASE_URL（PG）
  python mig.py load /mig/out     # 目标：env DATABASE_URL（SQLite）

设计：按表把 PG 行读成 JSON（日期转 ISO、bytes 转 b64:），
load 时用目标库反射出来的 Table 做 SQLAlchemy 类型化插入，
日期/布尔交给方言自己格式化（直接塞字符串会让 SQLite 的
'YYYY-MM-DDTHH:MM:SS' 与 'YYYY-MM-DD HH:MM:SS' 混在一起，范围查询会错）。
"""
import base64
import json
import os
import sys
from datetime import date, datetime, time
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import create_engine, inspect, text

# 老库缺列时填什么（反射不到 Python 侧默认值，只能显式给）
MISSING_DEFAULTS = {
    "devices": {"device_uuid": "", "device_name": "", "status": "approved", "first_seen": None},
    "users": {"role": "user"},
}

# 有外键的先后顺序：父表先插
TABLES = [
    "users",
    "books",
    "accounts",
    "categories",
    "user_ai_profile",
    "learned_rule",
    "devices",
    "txns",
]


def enc(v):
    if isinstance(v, (datetime, date, time)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (bytes, bytearray, memoryview)):
        return "b64:" + base64.b64encode(bytes(v)).decode()
    return v


def dec(v, pytype):
    if v is None:
        return None
    if isinstance(v, str) and v.startswith("b64:") and pytype in (bytes, bytearray):
        return base64.b64decode(v[4:])
    if pytype is datetime and isinstance(v, str):
        return datetime.fromisoformat(v)
    if pytype is date and isinstance(v, str):
        return date.fromisoformat(v)
    if pytype is time and isinstance(v, str):
        return time.fromisoformat(v)
    if pytype is bool and not isinstance(v, bool):
        return bool(v)
    return v


def dump(outdir):
    url = os.environ["DATABASE_URL"]
    eng = create_engine(url, future=True)
    os.makedirs(outdir, exist_ok=True)
    insp = inspect(eng)
    have = set(insp.get_table_names())
    with eng.connect() as conn:
        for t in TABLES:
            if t not in have:
                print(f"skip {t} (源库没有)")
                continue
            rows = [dict(r) for r in conn.execute(text(f"SELECT * FROM {t}")).mappings()]
            for r in rows:
                for k, v in list(r.items()):
                    r[k] = enc(v)
            path = os.path.join(outdir, t + ".json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(rows, f, ensure_ascii=False)
            print(f"dump {t}: {len(rows)} rows -> {path}")
    return 0


def load(outdir):
    url = os.environ["DATABASE_URL"]
    eng = create_engine(url, future=True)
    md = sa.MetaData()
    insp = inspect(eng)
    have = set(insp.get_table_names())
    total = {}
    with eng.begin() as conn:
        for t in TABLES:
            path = os.path.join(outdir, t + ".json")
            if not os.path.exists(path):
                print(f"skip {t} (没有文件)")
                continue
            if t not in have:
                print(f"skip {t} (目标库没有这张表)")
                continue
            table = sa.Table(t, md, autoload_with=eng)
            cols = {c.name: c for c in table.columns}
            rows = json.load(open(path, encoding="utf-8"))
            payload = []
            for r in rows:
                item = {}
                for k, v in r.items():
                    if k not in cols:
                        continue
                    try:
                        pytype = cols[k].type.python_type
                    except (NotImplementedError, AttributeError):
                        pytype = str
                    item[k] = dec(v, pytype)
                # 源库老表结构缺列（如 devices.device_uuid 是 1.1.0 才加的）时，
                # 反射出来的列没有 Python 侧默认值，需要显式补 —— SQLite 的建表 DDL
                # 里也没有这些默认值，漏填会直接撞 NOT NULL。
                overrides = MISSING_DEFAULTS.get(t, {})
                for name, c in cols.items():
                    if name in item or c.nullable:
                        continue
                    if name in overrides:
                        item[name] = overrides[name]
                        continue
                    try:
                        pytype = c.type.python_type
                    except (NotImplementedError, AttributeError):
                        pytype = str
                    if pytype is str:
                        item[name] = ""
                    elif pytype is bool:
                        item[name] = False
                    elif pytype is int:
                        item[name] = 0
                    elif pytype is datetime:
                        item[name] = datetime.now()
                payload.append(item)
            # 已存在的 id 先删，保证可重复执行
            ids = [p["id"] for p in payload if "id" in p]
            if ids:
                conn.execute(table.delete().where(table.c.id.in_(ids)))
            if payload:
                conn.execute(table.insert(), payload)
            total[t] = len(payload)
            print(f"load {t}: {len(payload)} rows")
    # 复核
    with eng.connect() as conn:
        for t in TABLES:
            if t in have and os.path.exists(os.path.join(outdir, t + ".json")):
                n = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
                print(f"count {t}: {n}")
        if "txns" in have:
            s = conn.execute(text("SELECT COUNT(*), COALESCE(SUM(amount_cents),0) FROM txns")).fetchone()
            print(f"txns_sum: rows={s[0]} amount_cents={s[1]}")
    return 0


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    outdir = sys.argv[2] if len(sys.argv) > 2 else "/mig"
    if mode == "dump":
        sys.exit(dump(outdir))
    if mode == "load":
        sys.exit(load(outdir))
    print(__doc__)
    sys.exit(2)
