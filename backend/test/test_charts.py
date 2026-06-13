"""charts 模块单元测试。"""

from app.agent.charts import (
    build_chart_spec,
    build_line_chart_spec,
    build_pie_chart_spec,
    is_chartable_sql_result,
    is_time_series_group_by,
    parse_assistant_content,
    parse_user_chart_type_preference,
    resolve_chart_type,
    serialize_assistant_content,
    sql_result_to_data_points,
)


def test_is_chartable_sql_result():
    assert is_chartable_sql_result({"华东": 100.0, "华北": 80.0}) is True
    assert is_chartable_sql_result({"华东": 100.0}) is False
    assert is_chartable_sql_result(123) is False
    assert is_chartable_sql_result({}) is False


def test_sql_result_to_data_points_sorted_desc():
    points = sql_result_to_data_points({"华东": 100.0, "华北": 200.0})
    assert points[0]["label"] == "华北"
    assert points[0]["value"] == 200.0


def test_sql_result_to_data_points_month_chronological():
    points = sql_result_to_data_points(
        {"3月": 30.0, "1月": 10.0, "2月": 20.0},
        group_by="month",
    )
    assert [p["label"] for p in points] == ["1月", "2月", "3月"]


def test_sql_result_to_data_points_order_date_chronological():
    points = sql_result_to_data_points(
        {"2024-03-01": 30.0, "2024-01-01": 10.0, "2024-02-01": 20.0},
        group_by="order_date",
    )
    assert points[0]["label"] == "2024-01-01"
    assert points[-1]["label"] == "2024-03-01"


def test_is_time_series_group_by():
    assert is_time_series_group_by("month") is True
    assert is_time_series_group_by("order_date") is True
    assert is_time_series_group_by("region") is False


def test_parse_user_chart_type_preference():
    assert parse_user_chart_type_preference("用饼图展示占比") == "pie"
    assert parse_user_chart_type_preference("各区域销售额对比") is None
    assert parse_user_chart_type_preference("柱状图对比各渠道") == "bar"
    assert parse_user_chart_type_preference("销售额月度趋势折线图") == "line"


def test_resolve_chart_type_time_series_defaults_to_line():
    assert (
        resolve_chart_type(
            user_query="各月销售额趋势",
            llm_chart_type="bar",
            category_count=6,
            group_by="month",
        )
        == "line"
    )


def test_resolve_chart_type_pie_downgrade_when_too_many_categories():
    assert (
        resolve_chart_type(
            user_query="各品类占比",
            llm_chart_type="pie",
            category_count=10,
        )
        == "bar"
    )


def test_resolve_chart_type_user_override():
    assert (
        resolve_chart_type(
            user_query="用扇形图展示各区域对比",
            llm_chart_type="bar",
            category_count=4,
        )
        == "pie"
    )


def test_resolve_chart_type_line_not_for_category_without_user_pref():
    assert (
        resolve_chart_type(
            user_query="各区域销售额",
            llm_chart_type="line",
            category_count=4,
            group_by="region",
        )
        == "bar"
    )


def test_build_line_chart_spec():
    spec = build_line_chart_spec(
        title="各月销售额趋势",
        data_points=[{"label": "1月", "value": 100.0}],
        x_label="月份",
        y_label="销售额",
    )
    assert spec["type"] == "line"


def test_build_chart_spec_routes_by_type():
    points = [{"label": "1月", "value": 100.0}]
    assert build_chart_spec("pie", title="t", data_points=points)["type"] == "pie"
    assert build_chart_spec("bar", title="t", data_points=points)["type"] == "bar"
    assert build_chart_spec("line", title="t", data_points=points)["type"] == "line"


def test_serialize_and_parse_assistant_content():
    spec = {
        "type": "line",
        "title": "各月销售额趋势",
        "x_label": "月份",
        "y_label": "销售额",
        "data": [{"label": "1月", "value": 100.0}],
    }
    text = "报告时间：2024年"
    serialized = serialize_assistant_content(spec, text)
    parsed_spec, parsed_text = parse_assistant_content(serialized)
    assert parsed_spec == spec
    assert parsed_text == text
