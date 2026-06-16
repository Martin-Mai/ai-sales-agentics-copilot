"""Agent 图路由逻辑单元测试。"""

from app.agent.graph import route_after_planner, route_after_sql


def test_route_after_planner_year_clarify_when_month_without_year():
    state = {
        "user_query": "9月份哪个区域销售额最低？",
        "planned_tool": "sql_tool",
    }
    assert route_after_planner(state) == "year_clarify"


def test_route_after_planner_proceeds_when_year_provided():
    state = {
        "user_query": "2025年9月份哪个区域销售额最低？",
        "planned_tool": "sql_tool",
    }
    assert route_after_planner(state) == "sql_tool"


def test_route_after_planner_sql_first_when_sales_and_satisfaction():
    state = {
        "user_query": "2025年数码配件在11-12月销售很好，用户满意吗？",
        "planned_tool": "vector_tool",
    }
    assert route_after_planner(state) == "sql_tool"


def test_route_after_planner_respects_vector_only():
    state = {
        "user_query": "用户对产品质量有哪些差评？",
        "planned_tool": "vector_tool",
    }
    assert route_after_planner(state) == "vector_tool"


def test_route_after_sql_goes_to_no_data_when_flagged():
    state = {
        "user_query": "2028年9月份哪个区域销售额最低？",
        "no_data": True,
        "reviews": [],
        "sql_result": None,
    }
    assert route_after_sql(state) == "no_data"


def test_route_after_sql_always_fetches_reviews():
    state = {
        "user_query": "25年八月份渠道的销售额占比",
        "reviews": [],
        "sql_result": {"线上": 100.0, "线下": 200.0},
    }
    assert route_after_sql(state) == "vector_tool"


def test_route_after_sql_skips_vector_when_reviews_exist():
    state = {
        "user_query": "25年八月份渠道的销售额占比",
        "reviews": ["评论1"],
        "sql_result": {"线上": 100.0, "线下": 200.0},
    }
    assert route_after_sql(state) == "chart_spec"


def test_route_after_sql_goes_to_insight_without_chartable_result():
    state = {
        "user_query": "总销售额",
        "reviews": ["评论1"],
        "sql_result": 12345.0,
    }
    assert route_after_sql(state) == "insight"
