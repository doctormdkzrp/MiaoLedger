"""一句话记账质量评测：拿真模型跑 20 句日常口语，看正确率。

用途：一期验收标准第 2 条（正确率 ≥ 90%）的定期体检。
用法：  .venv/bin/python -m tests.eval_parse        # 在 server/ 目录下
注：需要环境变量 DEEPSEEK_API_KEY；没有 key 时会自动退到规则引擎（正确率会明显低，属预期）。
"""
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ai import parse_text  # noqa: E402

CATS = [
    {"id": i + 1, "name": n, "parent_id": None}
    for i, n in enumerate(
        ["餐饮", "交通", "汽车", "购物", "烟酒", "育儿", "赡养", "医疗", "居家", "旅行", "人情", "其它", "工资", "奖金", "其它收入"]
    )
]
ACCTS = [{"id": i + 1, "name": n} for i, n in enumerate(["微信", "支付宝", "建行", "现金"])]

NOW = datetime(2026, 11, 6, 21, 0, 0)

CASES = [
    ("早饭12块现金", 1200, "out", "餐饮", "现金"),
    ("昨天中午跟同事吃饭 AA 68，用微信", 6800, "out", "餐饮", "微信"),
    ("打车23", 2300, "out", "交通", "微信"),
    ("给车充电 49 支付宝", 4900, "out", "汽车", "支付宝"),
    ("超市买菜 215 微信", 21500, "out", "购物", "微信"),
    ("买包烟 25", 2500, "out", "烟酒", "微信"),
    ("孩子的纸尿裤 140.6 支付宝", 14060, "out", "育儿", "支付宝"),
    ("给我妈转两千 建行", 200000, "out", "赡养", "建行"),
    ("药店买药 36", 3600, "out", "医疗", "微信"),
    ("交话费 100", 10000, "out", "居家", "微信"),
    ("周末露营花了 150", 15000, "out", "旅行", "微信"),
    ("随礼 500 微信", 50000, "out", "人情", "微信"),
    ("加班打车回家 31.5 微信", 3150, "out", "交通", "微信"),
    ("中午吃面 18", 1800, "out", "餐饮", "微信"),
    ("发工资了 12800 建行", 1280000, "in", "工资", "建行"),
    ("报销下来 320 支付宝", 32000, "in", "其它收入", "支付宝"),
    ("停车费 5 块现金", 500, "out", "汽车", "现金"),
    ("幼儿园交学费 3000 建行", 300000, "out", "育儿", "建行"),
    ("水电费 180", 18000, "out", "居家", "微信"),
    ("前天晚上烧烤 120 微信", 12000, "out", "餐饮", "微信"),
]


def main() -> int:
    ok = 0
    fails = []
    for text, cents, kind, cat, acct in CASES:
        r = parse_text(text, NOW, CATS, ACCTS, default_book_id=1, default_account=ACCTS[0])
        good = r["amount_cents"] == cents and r["kind"] == kind and r["cat_name"] == cat and r["account_name"] == acct
        ok += good
        mark = "✓" if good else "✗"
        extra = "" if good else f"   → 得到 金额={r['amount_cents']} {r['kind']} {r['cat_name']} {r['account_name']}"
        print(f"{mark} {text:34s} 期望 {cents/100:>8.2f} {kind} {cat} {acct}{extra}  [{r['engine']}]")
        if not good:
            fails.append(text)
    print(f"\n正确率 {ok}/{len(CASES)} = {ok / len(CASES) * 100:.0f}%")
    if fails:
        print("错的这些：", "；".join(fails))
    return 0 if ok / len(CASES) >= 0.9 else 1


if __name__ == "__main__":
    raise SystemExit(main())
