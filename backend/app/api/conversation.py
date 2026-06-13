from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.conversation import (
    ConversationCreate,
    ConversationResponse,
    ConversationUpdate,
    MessageResponse,
)
from app.services.conversation_service import conversation_service

router = APIRouter(prefix="/conversations")


@router.post(
    "",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    payload: ConversationCreate,
    session: AsyncSession = Depends(get_db),
) -> ConversationResponse:
    return await conversation_service.create_conversation(session, payload)


@router.get("/user/{user_id}", response_model=list[ConversationResponse])
async def list_user_conversations(
    user_id: str,
    session: AsyncSession = Depends(get_db),
) -> list[ConversationResponse]:
    return await conversation_service.list_user_conversations(session, user_id)


@router.put("/{conversation_id}", response_model=ConversationResponse)
async def update_conversation_title(
    conversation_id: str,
    payload: ConversationUpdate,
    session: AsyncSession = Depends(get_db),
) -> ConversationResponse:
    return await conversation_service.update_conversation_title(
        session,
        conversation_id,
        payload,
    )


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: str,
    session: AsyncSession = Depends(get_db),
) -> None:
    await conversation_service.delete_conversation(session, conversation_id)


@router.get("/{conversation_id}/messages", response_model=list[MessageResponse])
async def get_conversation_messages(
    conversation_id: str,
    session: AsyncSession = Depends(get_db),
) -> list[MessageResponse]:
    return await conversation_service.get_conversation_messages(
        session,
        conversation_id,
    )
