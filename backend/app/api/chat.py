import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.agent.charts import serialize_assistant_content
from app.agent.graph import agent_graph
from app.database import get_db
from app.database.mysql_client import AsyncSessionLocal
from app.repositories.conversation_repository import ConversationRepository
from app.services.session_cache import session_cache

router = APIRouter(prefix="/chat")
_repository = ConversationRepository()


class ChatStreamRequest(BaseModel):
    conversation_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)


async def _validate_conversation(
    session: AsyncSession,
    conversation_id: str,
) -> None:
    conversation = await _repository.get_by_id_any(session, conversation_id)
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"会话 {conversation_id} 不存在",
        )
    if conversation.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=f"会话 {conversation_id} 已被删除",
        )


@router.post("/stream")
async def chat_stream(
    payload: ChatStreamRequest,
    session: AsyncSession = Depends(get_db),
) -> EventSourceResponse:
    await _validate_conversation(session, payload.conversation_id)

    await _repository.add_message(
        session,
        conversation_id=payload.conversation_id,
        role="user",
        content=payload.message,
    )
    await session_cache.invalidate_conversation(payload.conversation_id)

    db_messages = await _repository.list_messages(session, payload.conversation_id)
    history = [
        {"role": m.role, "content": m.content}
        for m in db_messages[:-1]
    ]

    initial_state = {
        "user_query": payload.message,
        "conversation_id": payload.conversation_id,
        "user_id": payload.user_id,
        "messages": history,
        "memories": [],
        "sql_result": None,
        "sql_group_by": None,
        "sql_filters": [],
        "analysis_time_scope": "",
        "reviews": [],
        "reviews_scope": "",
        "insight": "",
        "chart_spec": None,
        "step_count": 0,
        "error": None,
        "no_data": False,
    }

    queue: asyncio.Queue = asyncio.Queue()
    insight_buffer: list[str] = []
    chart_state: dict[str, dict | None] = {"spec": None}

    async def run_agent() -> None:
        try:
            final_state = await agent_graph.ainvoke(
                initial_state,
                {"configurable": {"queue": queue}},
            )
            insight = final_state.get("insight", "")
            if insight and not insight_buffer:
                insight_buffer.append(insight)
            if final_state.get("chart_spec") and not chart_state["spec"]:
                chart_state["spec"] = final_state["chart_spec"]
        except Exception as exc:
            error_msg = f"处理失败: {exc}"
            insight_buffer.clear()
            insight_buffer.append(error_msg)
            await queue.put({"event": "text_chunk", "text": error_msg})
        finally:
            await queue.put(None)

    async def event_generator() -> AsyncGenerator[dict, None]:
        task = asyncio.create_task(run_agent())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                event_type = item.get("event", "message")
                if event_type == "text_chunk":
                    insight_buffer.append(item.get("text", ""))
                elif event_type == "chart_spec" and item.get("data"):
                    chart_state["spec"] = item["data"]
                yield {
                    "event": event_type,
                    "data": json.dumps(item, ensure_ascii=False),
                }
        finally:
            if not task.done():
                task.cancel()

            assistant_content = "".join(insight_buffer).strip()
            if not assistant_content:
                assistant_content = "处理失败: 未生成有效回复"

            persisted_content = serialize_assistant_content(
                chart_state["spec"],
                assistant_content,
            )

            try:
                async with AsyncSessionLocal() as persist_session:
                    await _repository.add_message(
                        persist_session,
                        conversation_id=payload.conversation_id,
                        role="assistant",
                        content=persisted_content,
                    )
                await session_cache.invalidate_conversation(payload.conversation_id)
            except Exception:
                pass

    return EventSourceResponse(event_generator())
