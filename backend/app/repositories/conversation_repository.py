from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation, Message


class ConversationRepository:
    async def create(
        self,
        session: AsyncSession,
        *,
        user_id: str,
        title: str,
    ) -> Conversation:
        conversation = Conversation(user_id=user_id, title=title)
        session.add(conversation)
        await session.commit()
        await session.refresh(conversation)
        return conversation

    async def get_by_id(
        self,
        session: AsyncSession,
        conversation_id: str,
        *,
        include_deleted: bool = False,
    ) -> Conversation | None:
        stmt = select(Conversation).where(Conversation.id == conversation_id)
        if not include_deleted:
            stmt = stmt.where(Conversation.is_deleted.is_(False))
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_any(
        self,
        session: AsyncSession,
        conversation_id: str,
    ) -> Conversation | None:
        result = await session.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        return result.scalar_one_or_none()

    async def list_active_by_user(
        self,
        session: AsyncSession,
        user_id: str,
    ) -> list[Conversation]:
        result = await session.execute(
            select(Conversation)
            .where(
                Conversation.user_id == user_id,
                Conversation.is_deleted.is_(False),
            )
            .order_by(Conversation.updated_at.desc())
        )
        return list(result.scalars().all())

    async def update_title(
        self,
        session: AsyncSession,
        conversation: Conversation,
        title: str,
    ) -> Conversation:
        conversation.title = title
        conversation.updated_at = datetime.now()
        await session.commit()
        await session.refresh(conversation)
        return conversation

    async def soft_delete(
        self,
        session: AsyncSession,
        conversation: Conversation,
    ) -> Conversation:
        conversation.is_deleted = True
        conversation.updated_at = datetime.now()
        await session.commit()
        await session.refresh(conversation)
        return conversation

    async def list_messages(
        self,
        session: AsyncSession,
        conversation_id: str,
    ) -> list[Message]:
        result = await session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.timestamp.asc())
        )
        return list(result.scalars().all())

    async def add_message(
        self,
        session: AsyncSession,
        *,
        conversation_id: str,
        role: str,
        content: str,
    ) -> Message:
        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
        )
        session.add(message)
        await session.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(updated_at=datetime.now())
        )
        await session.commit()
        await session.refresh(message)
        return message
