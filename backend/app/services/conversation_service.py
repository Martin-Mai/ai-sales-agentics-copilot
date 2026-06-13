from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.conversation_repository import ConversationRepository
from app.schemas.conversation import (
    ConversationCreate,
    ConversationResponse,
    ConversationUpdate,
    MessageResponse,
)
from app.services.session_cache import SessionCacheProvider, session_cache


class ConversationService:
    def __init__(
        self,
        repository: ConversationRepository | None = None,
        cache: SessionCacheProvider | None = None,
    ) -> None:
        self.repository = repository or ConversationRepository()
        self.cache = cache or session_cache

    async def create_conversation(
        self,
        session: AsyncSession,
        payload: ConversationCreate,
    ) -> ConversationResponse:
        conversation = await self.repository.create(
            session,
            user_id=payload.user_id,
            title=payload.title,
        )
        return ConversationResponse.model_validate(conversation)

    async def list_user_conversations(
        self,
        session: AsyncSession,
        user_id: str,
    ) -> list[ConversationResponse]:
        conversations = await self.repository.list_active_by_user(session, user_id)
        return [
            ConversationResponse.model_validate(conversation)
            for conversation in conversations
        ]

    async def update_conversation_title(
        self,
        session: AsyncSession,
        conversation_id: str,
        payload: ConversationUpdate,
    ) -> ConversationResponse:
        conversation = await self._get_active_conversation(session, conversation_id)
        updated = await self.repository.update_title(
            session,
            conversation,
            payload.title,
        )
        await self.cache.invalidate_conversation(conversation_id)
        return ConversationResponse.model_validate(updated)

    async def delete_conversation(
        self,
        session: AsyncSession,
        conversation_id: str,
    ) -> None:
        conversation = await self._get_active_conversation(session, conversation_id)
        await self.repository.soft_delete(session, conversation)
        await self.cache.invalidate_conversation(conversation_id)

    async def get_conversation_messages(
        self,
        session: AsyncSession,
        conversation_id: str,
    ) -> list[MessageResponse]:
        await self._get_active_conversation(session, conversation_id)

        cached = await self.cache.get_recent_messages(conversation_id)
        if cached is not None:
            return cached

        messages = await self.repository.list_messages(session, conversation_id)
        result = [MessageResponse.model_validate(message) for message in messages]
        await self.cache.set_recent_messages(conversation_id, result)
        return result

    async def _get_active_conversation(
        self,
        session: AsyncSession,
        conversation_id: str,
    ):
        conversation = await self.repository.get_by_id_any(session, conversation_id)
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
        return conversation


conversation_service = ConversationService()
