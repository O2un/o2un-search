"""임베딩 공급자 인터페이스. 색인과 검색은 이것만 알고, 공급자 이름으로 분기하지 않는다."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol

# 차원은 모델과 무관하게 고정이다. search.chunks.embedding 이 vector(768) 이라,
# 바꾸려면 마이그레이션이 먼저다.
EMBED_DIM = 768


@dataclass(frozen=True)
class EmbeddingDocument:
    title: str
    text: str


class RateLimited(Exception):
    """공급자가 호출 한도로 거절했고, 기다렸다 다시 시도해도 풀리지 않았다."""


class EmbeddingProvider(Protocol):
    model_id: str

    def embed_documents(self, documents: list[EmbeddingDocument]) -> list[list[float]]: ...

    def embed_query(self, query: str) -> list[float]: ...


def make_provider() -> EmbeddingProvider:
    """공급자는 여기서만 만든다."""
    name = os.environ.get("EMBEDDING_PROVIDER", "gemini")
    if name == "gemini":
        from .gemini import GeminiEmbedding

        from . import env

        return GeminiEmbedding(api_key=env.require("GEMINI_API_KEY"), dim=EMBED_DIM)
    raise SystemExit(f"알 수 없는 EMBEDDING_PROVIDER: {name}")
