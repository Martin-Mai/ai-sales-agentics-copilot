import asyncio
import concurrent.futures
from typing import Any, Dict, List

import chromadb
from sentence_transformers import SentenceTransformer

from app.config import settings

COMMENTS_COLLECTION = "sales_comments"

_chroma_client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
chroma_client = _chroma_client


async def get_comments_collection() -> chromadb.Collection:
    return await asyncio.to_thread(
        _chroma_client.get_or_create_collection,
        name=COMMENTS_COLLECTION,
    )


async def get_memory_collection() -> chromadb.Collection:
    return await asyncio.to_thread(
        _chroma_client.get_or_create_collection,
        name=settings.LONG_TERM_MEMORY_COLLECTION,
    )


class EmbeddingModelSingleton:
    _instance: "EmbeddingModelSingleton | None" = None
    _model: SentenceTransformer | None = None

    def __new__(cls) -> "EmbeddingModelSingleton":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if EmbeddingModelSingleton._model is None:
            EmbeddingModelSingleton._model = SentenceTransformer("BAAI/bge-small-zh-v1.5")

    @property
    def model(self) -> SentenceTransformer:
        if EmbeddingModelSingleton._model is None:
            EmbeddingModelSingleton._model = SentenceTransformer("BAAI/bge-small-zh-v1.5")
        return EmbeddingModelSingleton._model

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        embeddings = await asyncio.to_thread(
            self.model.encode,
            texts,
            normalize_embeddings=True,
        )
        return embeddings.tolist()


embedding_model = EmbeddingModelSingleton()


async def add_comment_to_chroma(
    review_id: str,
    order_id: str,
    comment: str,
    rating: int,
    sentiment: str,
) -> None:
    embeddings = await embedding_model.embed_texts([comment])
    collection = await get_comments_collection()
    metadata: Dict[str, Any] = {
        "order_id": order_id,
        "rating": rating,
        "sentiment": sentiment,
    }
    await asyncio.to_thread(
        collection.add,
        ids=[review_id],
        embeddings=embeddings,
        documents=[comment],
        metadatas=[metadata],
    )
