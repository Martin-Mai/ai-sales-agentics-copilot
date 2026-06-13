from abc import ABC, abstractmethod

from app.schemas.conversation import MessageResponse


class SessionCacheProvider(ABC):
    """近期会话消息缓存抽象层，后续可替换为 Redis 实现。"""

    @abstractmethod
    async def get_recent_messages(
        self, conversation_id: str
    ) -> list[MessageResponse] | None:
        """返回缓存的消息列表；未命中时返回 None。"""

    @abstractmethod
    async def set_recent_messages(
        self,
        conversation_id: str,
        messages: list[MessageResponse],
    ) -> None:
        """写入近期消息缓存。"""

    @abstractmethod
    async def invalidate_conversation(self, conversation_id: str) -> None:
        """会话变更时清除对应缓存。"""


class InMemorySessionCache(SessionCacheProvider):
    """内存占位实现，便于本地开发与后续 Redis 迁移。"""

    def __init__(self) -> None:
        self._store: dict[str, list[MessageResponse]] = {}

    async def get_recent_messages(
        self, conversation_id: str
    ) -> list[MessageResponse] | None:
        return self._store.get(conversation_id)

    async def set_recent_messages(
        self,
        conversation_id: str,
        messages: list[MessageResponse],
    ) -> None:
        self._store[conversation_id] = messages

    async def invalidate_conversation(self, conversation_id: str) -> None:
        self._store.pop(conversation_id, None)


session_cache: SessionCacheProvider = InMemorySessionCache()
