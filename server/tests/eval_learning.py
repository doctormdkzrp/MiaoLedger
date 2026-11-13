"""AI 学习效果评测：30 句口语，比较「学习前 / 逐句纠正后 / 只纠正 3 句后的泛化」。

不请求大模型：全部走本地规则 + 学到的规则（与线上无 key 时同一条路径）。
运行：  python tests/eval_learning.py
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import learning  # noqa: E402
from app.ai import parse_text  # noqa: E402

NOW = datetime(2026, 11, 12, 12, 0, 0)

CATS_BASE = [
    {"id": 1, "name": "餐饮", "parent_id": None},
    {"id": 2, "name": "交通", "parent_id": None},
    {"id": 3, "name": "汽车", "parent_id": None},
    {"id": 4, "name": "购物", "parent_id": None},
    {"id": 5, "name": "烟酒", "parent_id": None},
    {"id": 6, "name": "育儿", "parent_id": None},
    {"id": 7, "name": "赡养", "parent_id": None},
    {"id": 8, "name": "医疗", "parent_id": None},
    {"id": 9, "name": "居家", "parent_id": None},
    {"id": 10, "name": "旅行", "parent_id": None},
    {"id": 11, "name": "人情", "parent_id": None},
    {"id": 12, "name": "其它", "parent_id": None},
    {"id": 13, "name": "工资", "parent_id": None},
    {"id": 14, "name": "奖金", "parent_id": None},
    {"id": 15, "name": "其它收入", "parent_id": None},
]
CATS_LEARNED = CATS_BASE + [{"id": 16, "name": "AI 研究", "parent_id": None}]
ACCTS = [
    {"id": 1, "name": "微信"},
    {"id": 2, "name": "支付宝"},
    {"id": 3, "name": "建行"},
    {"id": 4, "name": "现金"},
]
BOOKS = [{"id": 1, "name": "日常账本"}]

AI_CAT = "AI 研究"

# 30 句日常口语（金额、品牌按普通人的说法来）
CASES = [
    # ---- AI 服务（新分类「AI 研究」，默认 15 类里没有）
    ("Open Code 的 Go 订阅 67.24", AI_CAT),
    ("Commander Code GOAT 订阅 67", AI_CAT),
    ("OpenCode 充值 100", AI_CAT),
    ("火山引擎 120", AI_CAT),
    ("ChatGPT 订阅 20", AI_CAT),
    ("Claude Pro 订阅 140", AI_CAT),
    ("Cursor 订阅 160", AI_CAT),
    ("硅基流动 API 充值 50", AI_CAT),
    ("DeepSeek API 充值 30", AI_CAT),
    ("Kimi 会员 39", AI_CAT),
    # ---- 日常分类
    ("昨天中午跟同事吃饭 AA 68", "餐饮"),
    ("早上打车去单位 23.5", "交通"),
    ("给车加油 410", "汽车"),
    ("超市买菜 86.4", "购物"),
    ("两包烟 45", "烟酒"),
    ("孩子奶粉 268", "育儿"),
    ("给爸妈转 2000", "赡养"),
    ("感冒药 36.8", "医疗"),
    ("交房租 3200", "居家"),
    ("周末酒店 680", "旅行"),
    ("随礼 500", "人情"),
    ("同事聚餐 AA 120", "餐饮"),
    ("地铁充值 100", "交通"),
    ("停车费 15", "汽车"),
    ("网购一双鞋 299", "购物"),
    ("幼儿园学费 1800", "育儿"),
    ("体检 380", "医疗"),
    ("水电费 210", "居家"),
    ("露营装备 560", "旅行"),
    ("买了个水杯 59", "购物"),
]

# 只纠正这 3 句，观察泛化能力（品牌换名/大小写/空格）
SEED_SENTENCES = [
    "Open Code 的 Go 订阅 67.24",
    "火山引擎 120",
    "ChatGPT 订阅 20",
]


def build_rules(sentences: list[str]) -> list[dict]:
    """模拟用户逐句纠正到「AI 研究」：每句抽 1~2 个关键词，weight=2（明确表态）。"""
    rules = []
    for s in sentences:
        for pat in learning.select_patterns(s, limit=2):
            rules.append(
                {
                    "kind": "category",
                    "pattern": pat,
                    "target_name": AI_CAT,
                    "target_id": 16,
                    "weight": 2,
                    "hits": 1,
                    "deleted": False,
                    "updated_at": NOW,
                }
            )
    return rules


def run(cats, rules) -> tuple[int, list[tuple[str, str, str | None]]]:
    bad = []
    ok = 0
    for text, expect in CASES:
        res = parse_text(
            text, NOW, cats, ACCTS, 1, ACCTS[0], rules=rules, profile_hints="", books=BOOKS
        )
        got = res["cat_name"]
        if got == expect:
            ok += 1
        else:
            bad.append((text, expect, got))
    return ok, bad


def report(title: str, ok: int, bad: list, total: int) -> None:
    print(f"\n== {title}：{ok}/{total} = {ok / total * 100:.1f}%")
    for text, expect, got in bad:
        print(f"   ✗ {text}  期望={expect}  实际={got}")


def main() -> int:
    total = len(CASES)
    print(f"评测样本：{total} 句（AI 服务 {sum(1 for _, c in CASES if c == AI_CAT)} 句 + 日常 {total - 10} 句）")

    base_ok, base_bad = run(CATS_BASE, [])
    report("学习前（默认 15 类，无规则）", base_ok, base_bad, total)

    rules_all = build_rules([s for s, cat in CASES if cat == AI_CAT])
    print(f"\n逐句纠正学到的规则：{[(r['pattern'], r['target_name']) for r in rules_all]}")
    all_ok, all_bad = run(CATS_LEARNED, rules_all)
    report("逐句纠正后", all_ok, all_bad, total)

    rules_seed = build_rules(SEED_SENTENCES)
    print(f"\n只纠正 3 句学到的规则：{[(r['pattern'], r['target_name']) for r in rules_seed]}")
    seed_ok, seed_bad = run(CATS_LEARNED, rules_seed)
    report("只纠正 3 句后的泛化", seed_ok, seed_bad, total)

    print("\n== 结论")
    print(f"   学习前 {base_ok / total * 100:.1f}% → 逐句纠正 {all_ok / total * 100:.1f}%"
          f" → 只纠正 3 句 {seed_ok / total * 100:.1f}%")
    if all_ok / total < 0.9:
        print("   ✗ 逐句纠正后仍未到 90%，检查规则提取/匹配")
        return 1
    if all_ok <= base_ok:
        print("   ✗ 学习后没有提升")
        return 1
    print("   ✓ 学习后归类准确率 >= 90% 且明显高于学习前")
    return 0


if __name__ == "__main__":
    sys.exit(main())
