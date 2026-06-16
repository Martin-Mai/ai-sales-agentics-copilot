"""SQL 意图后处理：从用户问题中可靠提取日期过滤，修正 LLM 解析偏差。"""

from __future__ import annotations

import re
from datetime import date

_DATE_FILTER_OPS = frozenset({"year", "month", "day", "==", "eq", "!=", "ne", ">", "<", ">=", "<="})
_YEAR_IN_QUERY = re.compile(r"(?:(\d{4})|(\d{2}))年")


def _parse_year_from_match(match: re.Match[str]) -> int:
    return int(match.group(1) or f"20{match.group(2)}")


def user_mentions_year(user_query: str) -> bool:
    return _YEAR_IN_QUERY.search(user_query) is not None


_MONTH_IN_QUERY = re.compile(r"(\d{1,2})\s*月份?")


def extract_mentioned_months(user_query: str) -> list[int]:
    return [int(m.group(1)) for m in _MONTH_IN_QUERY.finditer(user_query)]


def requires_year_clarification(user_query: str) -> bool:
    """用户提到具体月份但未指定年份时，需追问年份。"""
    return bool(extract_mentioned_months(user_query)) and not user_mentions_year(user_query)


_SALES_SIGNAL = re.compile(
    r"销售|销售额|销量|卖得|收入|订单|表现|占比|对比|排名|最高|最低|趋势|走势"
)
_SATISFACTION_SIGNAL = re.compile(
    r"满意|评价|评论|反馈|用户说|怎么说|看法|口碑|差评|好评|投诉"
)


def requires_sql_first(user_query: str) -> bool:
    """问题同时涉及销售指标与用户满意度时，应先查 SQL 再补充评论。"""
    return bool(_SALES_SIGNAL.search(user_query) and _SATISFACTION_SIGNAL.search(user_query))


def build_year_clarification_message(user_query: str) -> str:
    months = extract_mentioned_months(user_query)
    if len(months) == 1:
        month = months[0]
        return (
            f"您提到了 {month} 月，但未指定具体年份。"
            f"请补充完整年份后再查询，例如「{{年份}}{month}月份哪个区域销售额最低」。"
        )
    if months:
        month_text = "、".join(str(m) for m in months)
        return (
            f"您提到了 {month_text} 月，但未指定具体年份。"
            "请补充完整年份后再查询，例如「{年份}9月份哪个区域销售额最低」。"
        )
    return "请提供具体年份，例如「{年份}9月份」，以便准确查询该月数据。"


def extract_date_filters(user_query: str) -> list[dict]:
    """从自然语言问题中提取 order_date 的年/月过滤条件。"""
    filters: list[dict] = []

    year_month = re.search(
        r"(?:(\d{4})|(\d{2}))年\s*(\d{1,2})\s*月",
        user_query,
    )
    if year_month:
        year = _parse_year_from_match(year_month)
        month = int(year_month.group(3))
        filters.append({"column": "order_date", "operator": "year", "value": year})
        filters.append({"column": "order_date", "operator": "month", "value": month})
        return filters

    month_only = _MONTH_IN_QUERY.search(user_query)
    if month_only:
        filters.append(
            {
                "column": "order_date",
                "operator": "month",
                "value": int(month_only.group(1)),
            }
        )

    year_only = _YEAR_IN_QUERY.search(user_query)
    if year_only and not month_only:
        filters.append(
            {
                "column": "order_date",
                "operator": "year",
                "value": _parse_year_from_match(year_only),
            }
        )

    return filters


def _strip_order_date_filters(filters: list[dict]) -> list[dict]:
    return [
        f
        for f in filters
        if not (
            f.get("column") == "order_date"
            and (f.get("operator") or f.get("op")) in _DATE_FILTER_OPS
        )
    ]


def merge_date_filters(user_query: str, llm_filters: list[dict]) -> list[dict]:
    """用问题中解析出的日期条件覆盖 LLM 生成的 order_date 日期过滤。"""
    extracted = extract_date_filters(user_query)
    other_filters = _strip_order_date_filters(llm_filters)

    if extracted:
        return other_filters + extracted

    if not user_mentions_year(user_query):
        return [
            f
            for f in llm_filters
            if not (
                f.get("column") == "order_date"
                and (f.get("operator") or f.get("op")) == "year"
            )
        ]

    return llm_filters


def build_analysis_time_scope(
    user_query: str,
    sql_filters: list[dict],
    min_date: date | None,
    max_date: date | None,
) -> str:
    """生成写入洞察报告的分析时间范围说明。"""
    if min_date is None or max_date is None:
        return "暂无有效订单数据，无法确定分析时间范围。"

    range_text = f"{min_date.isoformat()} 至 {max_date.isoformat()}"
    has_order_date_filter = any(f.get("column") == "order_date" for f in sql_filters)

    year_filter = next(
        (
            f
            for f in sql_filters
            if f.get("column") == "order_date" and (f.get("operator") or f.get("op")) == "year"
        ),
        None,
    )
    month_filter = next(
        (
            f
            for f in sql_filters
            if f.get("column") == "order_date" and (f.get("operator") or f.get("op")) == "month"
        ),
        None,
    )

    if year_filter and month_filter:
        return (
            f"分析时间范围：{year_filter['value']}年{month_filter['value']}月"
            f"（数据实际覆盖 {range_text}）。"
        )
    if year_filter:
        return (
            f"分析时间范围：{year_filter['value']}年"
            f"（数据实际覆盖 {range_text}）。"
        )
    if month_filter:
        return (
            f"分析时间范围：{month_filter['value']}月"
            f"（数据实际覆盖 {range_text}）。"
        )
    if not has_order_date_filter and not extract_date_filters(user_query):
        return (
            f"用户未指定分析时间。本次统计基于数据库全部订单，"
            f"分析时间范围：{range_text}。"
        )
    return f"分析时间范围：{range_text}。"


def describe_filter_criteria(filters: list[dict]) -> str:
    """将 SQL 过滤条件转为可读描述（用于无数据提示）。"""
    year: int | None = None
    month: int | None = None
    day: int | None = None
    parts: list[str] = []

    for f in filters:
        col = f.get("column")
        op = f.get("operator") or f.get("op")
        val = f.get("value")
        if col == "order_date" and op == "year":
            year = int(val)
        elif col == "order_date" and op == "month":
            month = int(val)
        elif col == "order_date" and op == "day":
            day = int(val)
        elif col == "region":
            parts.append(f"区域={val}")
        elif col == "channel":
            parts.append(f"渠道={val}")
        elif col == "product_category":
            parts.append(f"品类={val}")

    period_parts: list[str] = []
    if year is not None:
        period_parts.append(f"{year}年")
    if month is not None:
        period_parts.append(f"{month}月")
    if day is not None:
        period_parts.append(f"{day}日")
    if period_parts:
        parts.insert(0, "".join(period_parts))
    return "、".join(parts) if parts else "指定条件"


def has_no_matching_orders(
    sql_filters: list[dict],
    filtered_min: date | None,
    filtered_max: date | None,
) -> bool:
    """有过滤条件但 MIN/MAX 订单日期均为空，表示无匹配订单。"""
    if not sql_filters:
        return False
    return filtered_min is None and filtered_max is None


def build_no_data_message(
    sql_filters: list[dict],
    db_min: date | None,
    db_max: date | None,
) -> str:
    """生成查询条件无匹配订单时的提示（数据库范围来自实际 MIN/MAX 查询）。"""
    criteria = describe_filter_criteria(sql_filters)
    if db_min is not None and db_max is not None:
        db_range = f"{db_min.isoformat()} 至 {db_max.isoformat()}"
    else:
        db_range = "暂无订单数据"
    return (
        f"您查询的条件（{criteria}）在数据库中无匹配订单。"
        f"当前数据库订单日期覆盖范围为 {db_range}。"
        f"请调整查询时间或条件后重试。"
    )


def build_data_date_range_hint(min_date: date | None, max_date: date | None) -> str:
    if min_date is None or max_date is None:
        return "数据库中暂无订单日期数据。"
    return (
        f"数据库中现有订单日期范围为 {min_date.isoformat()} 至 {max_date.isoformat()}。"
        " year/month 过滤必须依据用户问题中明确提到的年份与月份，勿臆造或使用系统当前年份。"
    )


def infer_group_by_from_query(user_query: str, current: str | None) -> str | None:
    """对「哪个区域/渠道/品类最低/最高」类问题补全 group_by。"""
    if current:
        return current
    if re.search(r"哪个区域|各区域|区域.*(?:最低|最高|最少|最多|对比|排名)", user_query):
        return "region"
    if re.search(r"哪个渠道|各渠道|渠道.*(?:最低|最高|最少|最多|对比|排名|占比)", user_query):
        return "channel"
    if re.search(r"哪个品类|各品类|品类.*(?:最低|最高|最少|最多|对比|排名)", user_query):
        return "product_category"
    return current
