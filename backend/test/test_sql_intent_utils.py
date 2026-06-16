"""SQL 意图后处理单元测试。"""

from datetime import date

from app.agent.sql_intent_utils import (
    build_analysis_time_scope,
    build_no_data_message,
    build_year_clarification_message,
    describe_filter_criteria,
    extract_date_filters,
    has_no_matching_orders,
    infer_group_by_from_query,
    merge_date_filters,
    requires_sql_first,
    requires_year_clarification,
)


def test_extract_date_filters_full_year_month():
    assert extract_date_filters("2025年8月份哪个区域销售额最低？") == [
        {"column": "order_date", "operator": "year", "value": 2025},
        {"column": "order_date", "operator": "month", "value": 8},
    ]


def test_extract_date_filters_short_year():
    assert extract_date_filters("25年8月渠道占比") == [
        {"column": "order_date", "operator": "year", "value": 2025},
        {"column": "order_date", "operator": "month", "value": 8},
    ]


def test_extract_date_filters_month_only():
    assert extract_date_filters("9月份哪个区域销售额最低？") == [
        {"column": "order_date", "operator": "month", "value": 9},
    ]


def test_merge_date_filters_overrides_wrong_llm_year():
    llm_filters = [
        {"column": "order_date", "operator": "year", "value": 2024},
        {"column": "order_date", "operator": "month", "value": 8},
        {"column": "region", "operator": "==", "value": "华东"},
    ]
    merged = merge_date_filters("2025年8月份哪个区域销售额最低？", llm_filters)
    assert merged == [
        {"column": "region", "operator": "==", "value": "华东"},
        {"column": "order_date", "operator": "year", "value": 2025},
        {"column": "order_date", "operator": "month", "value": 8},
    ]


def test_build_analysis_time_scope_full_dataset():
    scope = build_analysis_time_scope(
        "各区域销售额对比",
        [],
        date(2025, 1, 1),
        date(2025, 12, 31),
    )
    assert "用户未指定分析时间" in scope
    assert "2025-01-01 至 2025-12-31" in scope


def test_build_analysis_time_scope_with_year_month():
    scope = build_analysis_time_scope(
        "2025年8月份哪个区域最低",
        [
            {"column": "order_date", "operator": "year", "value": 2025},
            {"column": "order_date", "operator": "month", "value": 8},
        ],
        date(2025, 8, 1),
        date(2025, 8, 31),
    )
    assert "2025年8月" in scope
    assert "2025-08-01 至 2025-08-31" in scope


def test_requires_year_clarification_when_month_without_year():
    assert requires_year_clarification("9月份哪个区域销售额最低？") is True
    assert requires_year_clarification("2025年9月份哪个区域销售额最低？") is False
    assert requires_year_clarification("各区域销售额对比") is False


def test_build_year_clarification_message():
    msg = build_year_clarification_message("9月份哪个区域销售额最低？")
    assert "9 月" in msg
    assert "年份" in msg
    assert "9月份" in msg


def test_describe_filter_criteria_year_month():
    desc = describe_filter_criteria(
        [
            {"column": "order_date", "operator": "year", "value": 2028},
            {"column": "order_date", "operator": "month", "value": 9},
        ]
    )
    assert desc == "2028年9月"


def test_has_no_matching_orders():
    assert has_no_matching_orders([{"column": "region", "operator": "==", "value": "华东"}], None, None)
    assert not has_no_matching_orders([], None, None)
    assert not has_no_matching_orders(
        [{"column": "region", "operator": "==", "value": "华东"}],
        date(2025, 1, 1),
        date(2025, 12, 31),
    )


def test_build_no_data_message():
    msg = build_no_data_message(
        [
            {"column": "order_date", "operator": "year", "value": 2028},
            {"column": "order_date", "operator": "month", "value": 9},
        ],
        date(2025, 1, 1),
        date(2025, 12, 31),
    )
    assert "2028年9月" in msg
    assert "无匹配订单" in msg
    assert "2025-01-01 至 2025-12-31" in msg


def test_merge_date_filters_strips_llm_year_when_user_omits_year():
    llm_filters = [
        {"column": "order_date", "operator": "year", "value": 2024},
        {"column": "order_date", "operator": "month", "value": 9},
    ]
    merged = merge_date_filters("9月份哪个区域销售额最低？", llm_filters)
    assert merged == [{"column": "order_date", "operator": "month", "value": 9}]


def test_merge_date_filters_respects_user_specified_year():
    llm_filters = [
        {"column": "order_date", "operator": "year", "value": 2025},
        {"column": "order_date", "operator": "month", "value": 8},
    ]
    merged = merge_date_filters("2024年8月份各区域销售额", llm_filters)
    assert merged == [
        {"column": "order_date", "operator": "year", "value": 2024},
        {"column": "order_date", "operator": "month", "value": 8},
    ]


def test_infer_group_by_region():
    assert infer_group_by_from_query("2025年8月份哪个区域销售额最低？", None) == "region"
    assert infer_group_by_from_query("各区域对比", "channel") == "channel"


def test_requires_sql_first_when_sales_and_satisfaction():
    assert requires_sql_first("2025年数码配件在11-12月销售很好，用户满意吗？") is True
    assert requires_sql_first("2025年华东区销售表现如何？用户主要反馈什么？") is True
    assert requires_sql_first("用户对产品质量有哪些差评？") is False
    assert requires_sql_first("2025年各区域销售额对比") is False
