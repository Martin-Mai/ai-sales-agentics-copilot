"""
生成销售分析 Agent 测试用 CSV 数据。
运行: python generate_test_data.py
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker

# ── 全局随机种子 ──────────────────────────────────────────────
RANDOM_SEED = 42
random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)
faker = Faker("zh_CN")
faker.seed_instance(RANDOM_SEED)

# ── 常量 ──────────────────────────────────────────────────────
SALES_ROWS = 5000
REVIEW_COVERAGE = 0.70
REGIONS = ["东北", "华北", "华东", "华南", "西北", "西南"]
CATEGORIES = ["美妆护肤", "数码配件", "办公文具", "食品饮料", "家居生活"]
CHANNELS = ["线上", "线下"]
SENTIMENTS = {4: "positive", 5: "positive", 3: "neutral", 2: "negative", 1: "negative"}

DATA_DIR = Path(__file__).resolve().parent / "data"

# 各月份品类权重（体现季节规律）
MONTH_CATEGORY_WEIGHTS: dict[int, dict[str, float]] = {
    m: {
        "美妆护肤": 1.0,
        "数码配件": 1.0,
        "办公文具": 1.0,
        "食品饮料": 1.0,
        "家居生活": 1.0,
    }
    for m in range(1, 13)
}
# 夏季饮料高峰
for m in (6, 7, 8):
    MONTH_CATEGORY_WEIGHTS[m]["食品饮料"] = 3.5
    MONTH_CATEGORY_WEIGHTS[m]["美妆护肤"] = 0.7
# 年末美妆、数码高峰
for m in (11, 12):
    MONTH_CATEGORY_WEIGHTS[m]["美妆护肤"] = 2.8
    MONTH_CATEGORY_WEIGHTS[m]["数码配件"] = 2.5
    MONTH_CATEGORY_WEIGHTS[m]["办公文具"] = 0.8

# 评论模板（按情感分类）
POSITIVE_TEMPLATES = [
    "物流很快，{product}质量超出预期，包装也很精美，会回购。",
    "客服态度很好，{product}用起来很顺手，性价比很高，推荐购买。",
    "收到货很满意，{product}和描述一致，家人都很喜欢。",
    "第二次购买了，{product}品质稳定，发货速度快，值得信赖。",
    "活动价入手很划算，{product}做工精细，使用体验很棒。",
]
NEUTRAL_TEMPLATES = [
    "整体还行，{product}中规中矩，物流正常，没有特别惊喜。",
    "{product}基本符合描述，价格一般，能用但谈不上出色。",
    "收到货后试用了几天，{product}表现平平，不好不坏。",
    "包装完好，{product}质量尚可，和预期差不多。",
    "客服回复及时，{product}一般般，凑合能用吧。",
]
NEGATIVE_TEMPLATES = [
    "等了太久才发货，{product}和图片差距大，不太满意。",
    "{product}用了两天就出问题，联系客服处理也很慢，失望。",
    "包装破损，{product}有明显瑕疵，退货流程太繁琐。",
    "价格不便宜但{product}质量很差，完全不值这个价。",
    "描述夸大其词，实际收到的{product}很廉价，不推荐。",
]

PRODUCT_ALIASES = {
    "美妆护肤": ["面霜", "精华液", "面膜", "口红", "防晒霜", "洁面乳"],
    "数码配件": ["蓝牙耳机", "手机壳", "充电宝", "数据线", "键盘", "鼠标垫"],
    "办公文具": ["签字笔", "笔记本", "文件夹", "订书机", "便利贴", "计算器"],
    "食品饮料": ["坚果礼盒", "咖啡豆", "果汁", "零食大礼包", "茶叶", "矿泉水"],
    "家居生活": ["收纳盒", "床上四件套", "台灯", "衣架", "垃圾桶", "抱枕"],
}


def _weighted_category(month: int) -> str:
    weights = MONTH_CATEGORY_WEIGHTS[month]
    cats = list(weights.keys())
    probs = np.array([weights[c] for c in cats], dtype=float)
    probs /= probs.sum()
    return str(np.random.choice(cats, p=probs))


def _generate_order_dates(n: int) -> list[date]:
    """按月份权重生成订单日期，年末与夏季订单略多。"""
    start = date(2025, 1, 1)
    end = date(2025, 12, 31)
    total_days = (end - start).days + 1

    month_weights = np.ones(12, dtype=float)
    for m in (6, 7, 8):
        month_weights[m - 1] = 1.6
    for m in (11, 12):
        month_weights[m - 1] = 1.8
    month_weights /= month_weights.sum()

    dates: list[date] = []
    for _ in range(n):
        month = int(np.random.choice(range(1, 13), p=month_weights))
        if month == 12:
            day = random.randint(1, 31)
        else:
            next_month = date(2025 if month < 12 else 2026, month + 1 if month < 12 else 1, 1)
            last_day = (next_month - timedelta(days=1)).day
            day = random.randint(1, last_day)
        dates.append(date(2025, month, day))
    return dates


def _generate_revenue(n: int) -> np.ndarray:
    """对数正态分布，多数落在 50~800，极少超过 2000。"""
    raw = np.random.lognormal(mean=5.2, sigma=0.55, size=n)
    revenue = np.clip(raw, 20.0, 5000.0)
    # 压低极端高值出现频率
    high_mask = revenue > 2000
    revenue[high_mask] = 2000 + (revenue[high_mask] - 2000) * 0.15
    return np.round(revenue, 2)


def _generate_sales_data() -> pd.DataFrame:
    order_dates = _generate_order_dates(SALES_ROWS)
    daily_counter: dict[str, int] = {}

    rows = []
    for i in range(SALES_ROWS):
        od = order_dates[i]
        date_key = od.strftime("%Y%m%d")
        daily_counter[date_key] = daily_counter.get(date_key, 0) + 1
        order_id = f"ORD{date_key}{daily_counter[date_key]:04d}"

        customer_id = f"CUST{random.randint(1, 9999):04d}"
        region = random.choice(REGIONS)
        product_category = _weighted_category(od.month)
        revenue = float(_generate_revenue(1)[0])
        quantity = random.randint(1, 10)
        channel = np.random.choice(CHANNELS, p=[0.65, 0.35])

        rows.append(
            {
                "order_id": order_id,
                "customer_id": customer_id,
                "region": region,
                "product_category": product_category,
                "order_date": od.isoformat(),
                "revenue": revenue,
                "quantity": quantity,
                "channel": channel,
            }
        )

    return pd.DataFrame(rows)


def _sample_rating() -> int:
    r = random.random()
    if r < 0.60:
        return random.choice([4, 5])
    if r < 0.80:
        return 3
    return random.choice([1, 2])


def _generate_comment(rating: int, product_category: str) -> str:
    product = random.choice(PRODUCT_ALIASES[product_category])
    if rating >= 4:
        template = random.choice(POSITIVE_TEMPLATES)
    elif rating == 3:
        template = random.choice(NEUTRAL_TEMPLATES)
    else:
        template = random.choice(NEGATIVE_TEMPLATES)
    comment = template.format(product=product)
    # 补充至 20~80 字
    while len(comment) < 20:
        comment += faker.sentence(nb_words=3).rstrip("。") + "。"
    if len(comment) > 80:
        comment = comment[:79] + "。"
    return comment


def _generate_reviews_data(sales_df: pd.DataFrame) -> pd.DataFrame:
    n_reviews = int(round(len(sales_df) * REVIEW_COVERAGE))
    sampled_orders = sales_df.sample(n=n_reviews, random_state=RANDOM_SEED)

    rows = []
    for seq, (_, order) in enumerate(sampled_orders.iterrows(), start=1):
        rating = _sample_rating()
        sentiment = SENTIMENTS[rating]
        comment = _generate_comment(rating, order["product_category"])
        rows.append(
            {
                "review_id": f"REV{seq:010d}",
                "order_id": order["order_id"],
                "rating": rating,
                "comment": comment,
                "sentiment": sentiment,
            }
        )

    return pd.DataFrame(rows)


def _pick_indices(n: int, ratio: float, dataframe: pd.DataFrame) -> list[int]:
    count = max(1, int(round(n * ratio)))
    return random.sample(list(dataframe.index), min(count, len(dataframe)))


def _inject_noise(
    sales_df: pd.DataFrame, reviews_df: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, int]]:
    sales = sales_df.copy()
    reviews = reviews_df.copy()
    noise_records: list[dict] = []
    stats: dict[str, int] = {
        "revenue_nan": 0,
        "revenue_negative": 0,
        "order_date_invalid": 0,
        "comment_empty": 0,
        "rating_invalid": 0,
        "duplicate_rows": 0,
    }

    invalid_dates = ["2025-13-01", "invalid", "2025-02-30", "N/A"]

    for idx in _pick_indices(len(sales), 0.02, sales):
        sales.at[idx, "revenue"] = np.nan
        noise_records.append(
            {"dataset": "sales_data", "identifier": sales.at[idx, "order_id"], "row_index": idx, "noise_type": "revenue_nan"}
        )
        stats["revenue_nan"] += 1

    for idx in _pick_indices(len(sales), 0.01, sales):
        sales.at[idx, "revenue"] = -99.9
        noise_records.append(
            {
                "dataset": "sales_data",
                "identifier": sales.at[idx, "order_id"],
                "row_index": idx,
                "noise_type": "revenue_negative",
            }
        )
        stats["revenue_negative"] += 1

    for idx in _pick_indices(len(sales), 0.01, sales):
        bad_date = random.choice(invalid_dates)
        sales.at[idx, "order_date"] = bad_date
        noise_records.append(
            {
                "dataset": "sales_data",
                "identifier": sales.at[idx, "order_id"],
                "row_index": idx,
                "noise_type": "order_date_invalid",
                "detail": bad_date,
            }
        )
        stats["order_date_invalid"] += 1

    for idx in _pick_indices(len(reviews), 0.02, reviews):
        reviews.at[idx, "comment"] = ""
        noise_records.append(
            {
                "dataset": "reviews_data",
                "identifier": reviews.at[idx, "review_id"],
                "row_index": idx,
                "noise_type": "comment_empty",
            }
        )
        stats["comment_empty"] += 1

    for idx in _pick_indices(len(reviews), 0.01, reviews):
        bad_rating = random.choice([0, 6])
        reviews.at[idx, "rating"] = bad_rating
        noise_records.append(
            {
                "dataset": "reviews_data",
                "identifier": reviews.at[idx, "review_id"],
                "row_index": idx,
                "noise_type": "rating_invalid",
                "detail": bad_rating,
            }
        )
        stats["rating_invalid"] += 1

    dup_count = random.randint(5, 10)
    dup_indices = random.sample(list(sales.index), dup_count)
    duplicates = sales.loc[dup_indices].copy()
    sales = pd.concat([sales, duplicates], ignore_index=True)
    for _, row in duplicates.iterrows():
        noise_records.append(
            {
                "dataset": "sales_data",
                "identifier": row["order_id"],
                "row_index": "appended",
                "noise_type": "duplicate_row",
            }
        )
    stats["duplicate_rows"] = dup_count

    noise_log = pd.DataFrame(noise_records)
    return sales, reviews, noise_log, stats


def _print_summary(sales_df: pd.DataFrame, reviews_df: pd.DataFrame, stats: dict[str, int]) -> None:
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("=" * 50)
    print("测试数据生成完成")
    print("=" * 50)
    print(f"销售订单总行数 : {len(sales_df)}")
    print(f"用户评论总行数 : {len(reviews_df)}")
    print(f"评论覆盖率     : {len(reviews_df) / (len(sales_df) - stats['duplicate_rows']):.1%}")
    print("-" * 50)
    print("噪声注入统计:")
    for key, value in stats.items():
        label = key.replace("_", " ").title()
        print(f"  {label:<22}: {value}")
    print("-" * 50)
    print(f"输出目录: {DATA_DIR.resolve()}")
    print("  - sales_data.csv")
    print("  - reviews_data.csv")
    print("  - noise_log.csv")
    print("=" * 50)


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    sales_df = _generate_sales_data()
    reviews_df = _generate_reviews_data(sales_df)
    sales_df, reviews_df, noise_log, stats = _inject_noise(sales_df, reviews_df)

    sales_df.to_csv(DATA_DIR / "sales_data.csv", index=False, encoding="utf-8-sig")
    reviews_df.to_csv(DATA_DIR / "reviews_data.csv", index=False, encoding="utf-8-sig")
    noise_log.to_csv(DATA_DIR / "noise_log.csv", index=False, encoding="utf-8-sig")

    _print_summary(sales_df, reviews_df, stats)


if __name__ == "__main__":
    main()
