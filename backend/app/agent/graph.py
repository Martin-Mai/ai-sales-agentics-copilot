"""LangGraph Agent 状态定义与工作流构建。"""

import asyncio
import json
from typing import Any, Literal, Optional

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from typing_extensions import NotRequired, TypedDict

from app.agent.charts import (
    build_bar_chart_spec,
    build_chart_spec,
    build_line_chart_spec,
    chart_type_label,
    group_by_hint_text,
    infer_x_label,
    infer_y_label,
    is_chartable_sql_result,
    is_time_series_group_by,
    resolve_chart_type,
    sql_result_to_data_points,
)
from app.agent.prompts import (
    ALLOWED_AGGREGATIONS,
    ALLOWED_COLUMNS,
    CHART_PLANNER_PROMPT_TEMPLATE,
    INSIGHT_PROMPT_TEMPLATE,
    PLANNER_PROMPT_TEMPLATE,
    SQL_INTENT_PROMPT_TEMPLATE,
)
from app.agent.sql_intent_utils import (
    build_analysis_time_scope,
    build_data_date_range_hint,
    build_no_data_message,
    build_year_clarification_message,
    describe_filter_criteria,
    has_no_matching_orders,
    infer_group_by_from_query,
    merge_date_filters,
    requires_sql_first,
    requires_year_clarification,
)
from app.agent.tools import (
    SQLIntent,
    SQLTool,
    VectorTool,
    fetch_filtered_order_date_range,
    fetch_order_date_range,
    fetch_reviews_for_agent,
)
from app.config import settings
from app.database.mysql_client import AsyncSessionLocal

_client = AsyncOpenAI(
    api_key=settings.llm_api_key,
    base_url=settings.llm_base_url,
)


class AgentState(TypedDict):
    user_query: str
    conversation_id: str
    user_id: str
    messages: list[dict]
    memories: list[str]
    sql_result: Any
    sql_group_by: Optional[str]
    sql_filters: list[dict]
    analysis_time_scope: str
    reviews: list[str]
    reviews_scope: str
    insight: str
    chart_spec: Any
    step_count: int
    error: Optional[str]
    no_data: NotRequired[bool]
    planned_tool: NotRequired[str]


class PlannerOutput(BaseModel):
    tool: Literal["sql_tool", "vector_tool", "insight"] = Field(
        ..., description="下一步调用的工具或直接输出洞察"
    )
    reason: str = Field(..., description="选择该路由的商业逻辑决策原因")


class ChartPlannerOutput(BaseModel):
    chart_type: Literal["bar", "pie", "line"] = Field(
        "bar", description="图表类型：bar 对比，pie 占比，line 趋势"
    )
    title: str = Field(..., description="图表标题")
    x_label: str = Field("类别", description="分类维度标签")
    y_label: str = Field("数值", description="指标标签")


def _get_queue(config: RunnableConfig) -> asyncio.Queue | None:
    return config.get("configurable", {}).get("queue")


async def _emit_event(config: RunnableConfig, event: dict) -> None:
    queue = _get_queue(config)
    if queue is not None:
        await queue.put(event)


def _build_context_section(state: AgentState) -> str:
    parts: list[str] = []
    if state.get("messages"):
        parts.append("## 对话历史（最近几轮）")
        for msg in state["messages"][-settings.MAX_HISTORY_TURNS:]:
            parts.append(f"{msg['role']}: {msg['content']}")
        parts.append("")
    if state.get("memories"):
        parts.append("## 长期记忆")
        for mem in state["memories"]:
            parts.append(f"- {mem}")
        parts.append("")
    return "\n".join(parts)


def _strip_json_markdown(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    if text.startswith("json"):
        text = text[4:].strip()
    return text


def _parse_json_model(content: str, model: type[BaseModel]) -> BaseModel:
    data = json.loads(_strip_json_markdown(content))
    return model.model_validate(data)


async def _json_mode_completion(
    messages: list[dict],
    response_model: type[BaseModel],
    *,
    temperature: float = 0.0,
) -> BaseModel:
    content = ""
    try:
        response = await _client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=temperature,
        )
        content = response.choices[0].message.content or ""
    except Exception:
        response = await _client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            temperature=temperature,
        )
        content = response.choices[0].message.content or ""
    return _parse_json_model(content, response_model)


async def planner_node(state: AgentState, config: RunnableConfig) -> AgentState:
    await _emit_event(config, {"event": "node_start", "node": "planner"})
    state["step_count"] = state.get("step_count", 0) + 1

    context_section = _build_context_section(state)
    prompt = PLANNER_PROMPT_TEMPLATE.format(
        allowed_columns=", ".join(sorted(ALLOWED_COLUMNS)),
        allowed_aggregations=", ".join(sorted(ALLOWED_AGGREGATIONS)),
        context_section=context_section,
        user_query=state["user_query"],
    )

    try:
        output = await _json_mode_completion(
            [{"role": "user", "content": prompt}],
            PlannerOutput,
        )
        state["planned_tool"] = output.tool
        state["error"] = None
        await _emit_event(
            config,
            {"event": "planner_decision", "tool": output.tool, "reason": output.reason},
        )
    except Exception as exc:
        state["planned_tool"] = "insight"
        state["error"] = str(exc)

    return state


async def year_clarify_node(state: AgentState, config: RunnableConfig) -> AgentState:
    await _emit_event(config, {"event": "node_start", "node": "year_clarify"})
    state["step_count"] = state.get("step_count", 0) + 1
    message = build_year_clarification_message(state["user_query"])
    state["insight"] = message
    state["error"] = None
    await _emit_event(config, {"event": "text_chunk", "text": message})
    return state


async def no_data_node(state: AgentState, config: RunnableConfig) -> AgentState:
    await _emit_event(config, {"event": "node_start", "node": "no_data"})
    state["step_count"] = state.get("step_count", 0) + 1
    message = state.get("insight") or "当前查询条件下无匹配订单数据。"
    state["insight"] = message
    state["no_data"] = True
    state["error"] = None
    await _emit_event(config, {"event": "text_chunk", "text": message})
    return state


async def sql_node(state: AgentState, config: RunnableConfig) -> AgentState:
    await _emit_event(config, {"event": "node_start", "node": "sql_tool"})
    state["step_count"] = state.get("step_count", 0) + 1

    try:
        async with AsyncSessionLocal() as session:
            min_date, max_date = await fetch_order_date_range(session)
            data_date_range_hint = build_data_date_range_hint(min_date, max_date)
            intent_prompt = SQL_INTENT_PROMPT_TEMPLATE.format(
                allowed_columns=", ".join(sorted(ALLOWED_COLUMNS)),
                data_date_range_hint=data_date_range_hint,
                user_query=state["user_query"],
            )

            intent = await _json_mode_completion(
                [{"role": "user", "content": intent_prompt}],
                SQLIntent,
            )
            corrected_filters = merge_date_filters(state["user_query"], intent.filters)
            corrected_group_by = infer_group_by_from_query(
                state["user_query"], intent.group_by
            )
            if corrected_filters != intent.filters or corrected_group_by != intent.group_by:
                intent = intent.model_copy(
                    update={"filters": corrected_filters, "group_by": corrected_group_by}
                )

            tool = SQLTool(session)
            result = await tool.run(intent)

            filtered_min, filtered_max = await fetch_filtered_order_date_range(
                session, intent.filters
            )
            if has_no_matching_orders(intent.filters, filtered_min, filtered_max):
                message = build_no_data_message(intent.filters, min_date, max_date)
                state["sql_result"] = None
                state["sql_group_by"] = intent.group_by
                state["sql_filters"] = intent.filters
                state["analysis_time_scope"] = (
                    f"查询条件（{describe_filter_criteria(intent.filters)}）无匹配订单。"
                )
                state["insight"] = message
                state["no_data"] = True
                state["error"] = None
                await _emit_event(config, {"event": "sql_result", "data": None})
                return state

            state["analysis_time_scope"] = build_analysis_time_scope(
                state["user_query"],
                intent.filters,
                filtered_min,
                filtered_max,
            )
        state["sql_result"] = result
        state["sql_group_by"] = intent.group_by
        state["sql_filters"] = intent.filters
        state["no_data"] = False
        state["error"] = None
        await _emit_event(config, {"event": "sql_result", "data": result})
    except Exception as exc:
        state["sql_result"] = None
        state["sql_group_by"] = None
        state["sql_filters"] = []
        state["analysis_time_scope"] = ""
        state["no_data"] = False
        state["error"] = str(exc)

    return state


async def vector_node(state: AgentState, config: RunnableConfig) -> AgentState:
    await _emit_event(config, {"event": "node_start", "node": "vector_tool"})
    state["step_count"] = state.get("step_count", 0) + 1

    try:
        async with AsyncSessionLocal() as session:
            reviews, reviews_scope = await fetch_reviews_for_agent(
                session,
                user_query=state["user_query"],
                sql_filters=state.get("sql_filters") or [],
                has_sql_context=state.get("sql_result") is not None,
                analysis_time_scope=state.get("analysis_time_scope") or "",
                top_k=5,
            )
        state["reviews"] = reviews
        state["reviews_scope"] = reviews_scope
        state["error"] = None
        await _emit_event(config, {"event": "reviews", "data": reviews})
    except Exception as exc:
        state["reviews"] = []
        state["reviews_scope"] = ""
        state["error"] = str(exc)

    return state


async def chart_node(state: AgentState, config: RunnableConfig) -> AgentState:
    await _emit_event(config, {"event": "node_start", "node": "chart_spec"})
    state["step_count"] = state.get("step_count", 0) + 1

    sql_result = state.get("sql_result")
    if not is_chartable_sql_result(sql_result):
        state["chart_spec"] = None
        return state

    group_by = state.get("sql_group_by")
    data_points = sql_result_to_data_points(sql_result, group_by=group_by)
    sql_display = json.dumps(sql_result, ensure_ascii=False, indent=2)

    prompt = CHART_PLANNER_PROMPT_TEMPLATE.format(
        user_query=state["user_query"],
        group_by_hint=group_by_hint_text(group_by),
        sql_result=sql_display,
        category_count=len(data_points),
    )

    try:
        output = await _json_mode_completion(
            [{"role": "user", "content": prompt}],
            ChartPlannerOutput,
        )
        y_label = output.y_label or infer_y_label(state["user_query"])
        default_x_label = output.x_label or infer_x_label(group_by)
        chart_type = resolve_chart_type(
            user_query=state["user_query"],
            llm_chart_type=output.chart_type,
            category_count=len(data_points),
            group_by=group_by,
        )
        spec = build_chart_spec(
            chart_type,
            title=output.title,
            data_points=data_points,
            x_label=default_x_label,
            y_label=y_label,
        )
        state["chart_spec"] = spec
        state["error"] = None
        await _emit_event(config, {"event": "chart_spec", "data": spec})
    except Exception as exc:
        fallback_type = "line" if is_time_series_group_by(group_by) else "bar"
        fallback_builder = build_line_chart_spec if fallback_type == "line" else build_bar_chart_spec
        state["chart_spec"] = fallback_builder(
            title="数据趋势" if fallback_type == "line" else "数据对比",
            data_points=data_points,
            x_label=infer_x_label(group_by),
            y_label=infer_y_label(state["user_query"]),
        )
        state["error"] = str(exc)
        await _emit_event(config, {"event": "chart_spec", "data": state["chart_spec"]})

    return state


async def insight_node(state: AgentState, config: RunnableConfig) -> AgentState:
    await _emit_event(config, {"event": "node_start", "node": "insight"})
    state["step_count"] = state.get("step_count", 0) + 1

    context_section = _build_context_section(state)
    sql_display = state.get("sql_result")
    if isinstance(sql_display, dict):
        sql_display_str = json.dumps(sql_display, ensure_ascii=False, indent=2)
    else:
        sql_display_str = str(sql_display) if sql_display is not None else "无"

    reviews_display = (
        "\n".join(f"- {r}" for r in state.get("reviews", []))
        if state.get("reviews")
        else "无"
    )
    reviews_scope = state.get("reviews_scope") or ""
    reviews_section = reviews_scope + "\n" + reviews_display if reviews_scope else reviews_display

    chart_spec = state.get("chart_spec")
    if chart_spec:
        type_label = chart_type_label(chart_spec.get("type", "bar"))
        chart_section = (
            f"## 已生成图表\n"
            f"类型：{type_label}\n"
            f"标题：{chart_spec.get('title', '数据对比')}\n"
            f"（用户界面已展示{type_label}，文字中可引用「如上所示」）\n"
        )
    else:
        chart_section = ""

    analysis_time_section = state.get("analysis_time_scope") or "未执行 SQL 查询，无分析时间范围。"

    prompt = INSIGHT_PROMPT_TEMPLATE.format(
        user_query=state["user_query"],
        context_section=context_section,
        chart_section=chart_section,
        analysis_time_section=analysis_time_section,
        sql_result=sql_display_str,
        reviews=reviews_section,
    )

    if state.get("error") and not sql_display and not state.get("reviews"):
        state["insight"] = f"处理失败: {state['error']}"
        await _emit_event(config, {"event": "text_chunk", "text": state["insight"]})
        return state

    insight_parts: list[str] = []
    try:
        stream = await _client.chat.completions.create(
            model=settings.llm_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                insight_parts.append(delta)
                await _emit_event(config, {"event": "text_chunk", "text": delta})
        state["insight"] = "".join(insight_parts)
        state["error"] = None
    except Exception as exc:
        state["insight"] = f"处理失败: {exc}"
        state["error"] = str(exc)
        await _emit_event(config, {"event": "text_chunk", "text": state["insight"]})

    return state


def route_after_planner(
    state: AgentState,
) -> Literal["year_clarify", "sql_tool", "vector_tool", "insight"]:
    if requires_year_clarification(state["user_query"]):
        return "year_clarify"
    if requires_sql_first(state["user_query"]):
        return "sql_tool"
    tool = state.get("planned_tool", "insight")
    if tool == "sql_tool":
        return "sql_tool"
    if tool == "vector_tool":
        return "vector_tool"
    return "insight"


def route_after_sql(
    state: AgentState,
) -> Literal["no_data", "vector_tool", "chart_spec", "insight"]:
    if state.get("no_data"):
        return "no_data"
    # SQL 查询后始终补充用户评论，供洞察报告「用户心声解读」使用
    if not state.get("reviews"):
        return "vector_tool"
    if is_chartable_sql_result(state.get("sql_result")):
        return "chart_spec"
    return "insight"


def route_after_vector(state: AgentState) -> Literal["chart_spec", "insight"]:
    if is_chartable_sql_result(state.get("sql_result")):
        return "chart_spec"
    return "insight"


def build_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("planner", planner_node)
    workflow.add_node("year_clarify", year_clarify_node)
    workflow.add_node("no_data", no_data_node)
    workflow.add_node("sql_tool", sql_node)
    workflow.add_node("vector_tool", vector_node)
    workflow.add_node("chart_spec", chart_node)
    workflow.add_node("insight", insight_node)

    workflow.set_entry_point("planner")
    workflow.add_conditional_edges(
        "planner",
        route_after_planner,
        {
            "year_clarify": "year_clarify",
            "sql_tool": "sql_tool",
            "vector_tool": "vector_tool",
            "insight": "insight",
        },
    )
    workflow.add_edge("year_clarify", END)
    workflow.add_edge("no_data", END)
    workflow.add_conditional_edges(
        "sql_tool",
        route_after_sql,
        {
            "no_data": "no_data",
            "vector_tool": "vector_tool",
            "chart_spec": "chart_spec",
            "insight": "insight",
        },
    )
    workflow.add_conditional_edges(
        "vector_tool",
        route_after_vector,
        {"chart_spec": "chart_spec", "insight": "insight"},
    )
    workflow.add_edge("chart_spec", "insight")
    workflow.add_edge("insight", END)

    return workflow.compile()


agent_graph = build_graph()
