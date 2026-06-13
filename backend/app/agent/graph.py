"""LangGraph Agent 状态定义与工作流构建。"""

import asyncio
import json
from typing import Any, Literal, Optional

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from typing_extensions import NotRequired, TypedDict

from app.agent.prompts import (
    ALLOWED_AGGREGATIONS,
    ALLOWED_COLUMNS,
    INSIGHT_PROMPT_TEMPLATE,
    PLANNER_PROMPT_TEMPLATE,
    SQL_INTENT_PROMPT_TEMPLATE,
)
from app.agent.tools import SQLIntent, SQLTool, VectorQuery, VectorTool
from app.config import settings
from app.database.mysql_client import AsyncSessionLocal

REVIEW_KEYWORDS = ("评价", "评论", "反馈", "用户说", "看法", "为什么", "原因", "舆情", "口碑", "满意度")

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
    reviews: list[str]
    insight: str
    step_count: int
    error: Optional[str]
    planned_tool: NotRequired[str]


class PlannerOutput(BaseModel):
    tool: Literal["sql_tool", "vector_tool", "insight"] = Field(
        ..., description="下一步调用的工具或直接输出洞察"
    )
    reason: str = Field(..., description="选择该路由的商业逻辑决策原因")


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


async def sql_node(state: AgentState, config: RunnableConfig) -> AgentState:
    await _emit_event(config, {"event": "node_start", "node": "sql_tool"})
    state["step_count"] = state.get("step_count", 0) + 1

    intent_prompt = SQL_INTENT_PROMPT_TEMPLATE.format(
        allowed_columns=", ".join(sorted(ALLOWED_COLUMNS)),
        user_query=state["user_query"],
    )

    try:
        intent = await _json_mode_completion(
            [{"role": "user", "content": intent_prompt}],
            SQLIntent,
        )
        async with AsyncSessionLocal() as session:
            tool = SQLTool(session)
            result = await tool.run(intent)
        state["sql_result"] = result
        state["error"] = None
        await _emit_event(config, {"event": "sql_result", "data": result})
    except Exception as exc:
        state["sql_result"] = None
        state["error"] = str(exc)

    return state


async def vector_node(state: AgentState, config: RunnableConfig) -> AgentState:
    await _emit_event(config, {"event": "node_start", "node": "vector_tool"})
    state["step_count"] = state.get("step_count", 0) + 1

    try:
        tool = VectorTool()
        query = VectorQuery(query=state["user_query"], top_k=5)
        reviews = await tool.run(query)
        state["reviews"] = reviews
        state["error"] = None
        await _emit_event(config, {"event": "reviews", "data": reviews})
    except Exception as exc:
        state["reviews"] = []
        state["error"] = str(exc)

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

    prompt = INSIGHT_PROMPT_TEMPLATE.format(
        user_query=state["user_query"],
        context_section=context_section,
        sql_result=sql_display_str,
        reviews=reviews_display,
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


def route_after_planner(state: AgentState) -> Literal["sql_tool", "vector_tool", "insight"]:
    tool = state.get("planned_tool", "insight")
    if tool == "sql_tool":
        return "sql_tool"
    if tool == "vector_tool":
        return "vector_tool"
    return "insight"


def route_after_sql(state: AgentState) -> Literal["vector_tool", "insight"]:
    query = state["user_query"]
    if any(kw in query for kw in REVIEW_KEYWORDS) and not state.get("reviews"):
        return "vector_tool"
    return "insight"


def build_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("planner", planner_node)
    workflow.add_node("sql_tool", sql_node)
    workflow.add_node("vector_tool", vector_node)
    workflow.add_node("insight", insight_node)

    workflow.set_entry_point("planner")
    workflow.add_conditional_edges(
        "planner",
        route_after_planner,
        {"sql_tool": "sql_tool", "vector_tool": "vector_tool", "insight": "insight"},
    )
    workflow.add_conditional_edges(
        "sql_tool",
        route_after_sql,
        {"vector_tool": "vector_tool", "insight": "insight"},
    )
    workflow.add_edge("vector_tool", "insight")
    workflow.add_edge("insight", END)

    return workflow.compile()


agent_graph = build_graph()
