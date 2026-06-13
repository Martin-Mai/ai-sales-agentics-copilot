"""图表规格构建与消息持久化辅助。"""

import json
import re
from typing import Any, Literal

CHART_MARKER_PREFIX = "<!--chart:"
CHART_MARKER_SUFFIX = "-->"

PIE_MAX_CATEGORIES = 8
TIME_SERIES_GROUP_BY = frozenset({"month", "order_date"})

PIE_CHART_KEYWORDS = ("扇形图", "扇形", "饼图", "pie")
BAR_CHART_KEYWORDS = ("柱状图", "柱形图", "柱状", "柱形", "条形图")
LINE_CHART_KEYWORDS = ("折线图", "折线", "line chart")
TREND_INTENT_KEYWORDS = ("趋势", "走势", "变化", "波动", "增减", "逐月", "每月", "按月", "日度", "daily")


def is_time_series_group_by(group_by: str | None) -> bool:
    return group_by in TIME_SERIES_GROUP_BY


def is_chartable_sql_result(result: Any) -> bool:
    """分组 SQL 结果为 dict 且至少 2 个类别时可绘制图表。"""
    if not isinstance(result, dict) or not result:
        return False
    if len(result) < 2:
        return False
    return all(isinstance(v, (int, float)) for v in result.values())


def _month_sort_key(label: str) -> int:
    match = re.match(r"(\d+)", str(label))
    return int(match.group(1)) if match else 0


def _date_sort_key(label: str) -> str:
    return str(label)


def sql_result_to_data_points(
    result: dict[str, Any],
    *,
    group_by: str | None = None,
) -> list[dict[str, Any]]:
    """将 SQL 分组结果转为前端 chart data 数组。"""
    if group_by == "month":
        items = sorted(result.items(), key=lambda kv: _month_sort_key(kv[0]))
    elif group_by == "order_date":
        items = sorted(result.items(), key=lambda kv: _date_sort_key(kv[0]))
    else:
        items = sorted(result.items(), key=lambda kv: kv[1], reverse=True)

    return [{"label": str(label), "value": float(value)} for label, value in items]


def infer_y_label(user_query: str) -> str:
    if "销量" in user_query or "数量" in user_query:
        return "销量"
    if "销售额" in user_query or "营收" in user_query or "收入" in user_query:
        return "销售额"
    return "数值"


def infer_x_label(group_by: str | None) -> str:
    if group_by == "month":
        return "月份"
    if group_by == "order_date":
        return "日期"
    if group_by == "region":
        return "区域"
    if group_by == "channel":
        return "渠道"
    if group_by == "product_category":
        return "品类"
    return "类别"


def has_trend_intent(user_query: str) -> bool:
    query_lower = user_query.lower()
    return any(kw in user_query for kw in TREND_INTENT_KEYWORDS) or "trend" in query_lower


def parse_user_chart_type_preference(
    user_query: str,
) -> Literal["bar", "pie", "line"] | None:
    query_lower = user_query.lower()
    if any(kw in user_query for kw in LINE_CHART_KEYWORDS) or (
        "line" in query_lower and "在线" not in user_query
    ):
        return "line"
    if any(kw in user_query for kw in PIE_CHART_KEYWORDS) or "pie" in query_lower:
        return "pie"
    if any(kw in user_query for kw in BAR_CHART_KEYWORDS):
        return "bar"
    return None


def resolve_chart_type(
    *,
    user_query: str,
    llm_chart_type: Literal["bar", "pie", "line"],
    category_count: int,
    group_by: str | None = None,
) -> Literal["bar", "pie", "line"]:
    """用户指定 > 时间序列默认折线 > LLM 建议 > 规则降级。"""
    user_pref = parse_user_chart_type_preference(user_query)
    if user_pref:
        chart_type = user_pref
    elif is_time_series_group_by(group_by):
        chart_type = "line"
    else:
        chart_type = llm_chart_type

    if is_time_series_group_by(group_by):
        if chart_type == "pie":
            chart_type = "line"
        if chart_type == "bar" and not user_pref and has_trend_intent(user_query):
            chart_type = "line"

    if chart_type == "line" and not is_time_series_group_by(group_by) and user_pref != "line":
        chart_type = llm_chart_type if llm_chart_type != "line" else "bar"

    if chart_type == "pie" and category_count > PIE_MAX_CATEGORIES:
        return "bar"

    return chart_type


def build_bar_chart_spec(
    *,
    title: str,
    data_points: list[dict[str, Any]],
    x_label: str = "类别",
    y_label: str = "数值",
) -> dict[str, Any]:
    return {
        "type": "bar",
        "title": title,
        "x_label": x_label,
        "y_label": y_label,
        "data": data_points,
    }


def build_pie_chart_spec(
    *,
    title: str,
    data_points: list[dict[str, Any]],
    x_label: str = "类别",
    y_label: str = "数值",
) -> dict[str, Any]:
    return {
        "type": "pie",
        "title": title,
        "x_label": x_label,
        "y_label": y_label,
        "data": data_points,
    }


def build_line_chart_spec(
    *,
    title: str,
    data_points: list[dict[str, Any]],
    x_label: str = "时间",
    y_label: str = "数值",
) -> dict[str, Any]:
    return {
        "type": "line",
        "title": title,
        "x_label": x_label,
        "y_label": y_label,
        "data": data_points,
    }


def build_chart_spec(
    chart_type: Literal["bar", "pie", "line"],
    *,
    title: str,
    data_points: list[dict[str, Any]],
    x_label: str = "类别",
    y_label: str = "数值",
) -> dict[str, Any]:
    if chart_type == "pie":
        return build_pie_chart_spec(
            title=title,
            data_points=data_points,
            x_label=x_label,
            y_label=y_label,
        )
    if chart_type == "line":
        return build_line_chart_spec(
            title=title,
            data_points=data_points,
            x_label=x_label,
            y_label=y_label,
        )
    return build_bar_chart_spec(
        title=title,
        data_points=data_points,
        x_label=x_label,
        y_label=y_label,
    )


def chart_type_label(chart_type: str) -> str:
    if chart_type == "pie":
        return "扇形图"
    if chart_type == "line":
        return "折线图"
    return "柱状图"


def group_by_hint_text(group_by: str | None) -> str:
    if group_by == "month":
        return "month（按月份聚合，适合折线图展示月度趋势）"
    if group_by == "order_date":
        return "order_date（按日期聚合，适合折线图展示日度走势）"
    if group_by:
        return f"{group_by}（分类维度，适合柱状图/扇形图）"
    return "未指定（标量或非分组结果）"


def serialize_assistant_content(chart_spec: dict[str, Any] | None, text: str) -> str:
    if chart_spec:
        payload = json.dumps(chart_spec, ensure_ascii=False)
        return f"{CHART_MARKER_PREFIX}{payload}{CHART_MARKER_SUFFIX}\n{text}"
    return text


def parse_assistant_content(content: str) -> tuple[dict[str, Any] | None, str]:
    pattern = re.compile(
        rf"^{re.escape(CHART_MARKER_PREFIX)}(.+?){re.escape(CHART_MARKER_SUFFIX)}\n?",
        re.DOTALL,
    )
    match = pattern.match(content)
    if not match:
        return None, content
    try:
        chart_spec = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None, content
    return chart_spec, content[match.end() :]
