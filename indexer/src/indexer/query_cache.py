"""검색어 임베딩 캐시. 검색 서비스(단위 3)가 검색어를 임베딩할 때 거친다.

키는 정규화(NFC, 앞뒤 공백 제거, 연속 공백 하나로)한 검색어의 SHA-256 과 모델이다.
방문자 검색어 원문은 저장하지 않는다.
"""

from __future__ import annotations

import hashlib
import unicodedata
from typing import Protocol

from .embedding import EmbeddingProvider


def query_hash(query: str) -> str:
    normalized = " ".join(unicodedata.normalize("NFC", query).split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class QueryCache(Protocol):
    def model_id(self, name: str) -> int | None: ...

    def get(self, key: str, model_id: int) -> list[float] | None: ...

    def put(self, key: str, model_id: int, vector: list[float]) -> None: ...


def embed_query(cache: QueryCache, provider: EmbeddingProvider, query: str) -> tuple[list[float], bool]:
    """(벡터, 캐시 적중 여부). 모델이 아직 등록되지 않았으면 캐시 없이 임베딩한다."""
    model_id = cache.model_id(provider.model_id)
    key = query_hash(query)
    if model_id is not None:
        cached = cache.get(key, model_id)
        if cached is not None:
            return cached, True
    vector = provider.embed_query(query)
    if model_id is not None:
        cache.put(key, model_id, vector)
    return vector, False


class PgQueryCache:
    """검색 서비스의 연결을 그대로 쓴다. 넣은 행이 남도록 연결은 autocommit 이어야 한다."""

    def __init__(self, conn) -> None:  # psycopg.Connection
        self._conn = conn

    def model_id(self, name: str) -> int | None:
        row = self._conn.execute("SELECT id FROM search.embed_models WHERE name = %s", (name,)).fetchone()
        return row[0] if row else None

    def get(self, key: str, model_id: int) -> list[float] | None:
        row = self._conn.execute(
            "SELECT embedding::text FROM search.query_embeddings"
            " WHERE query_hash = %s AND embed_model_id = %s",
            (key, model_id),
        ).fetchone()
        return [float(v) for v in row[0].strip("[]").split(",")] if row else None

    def put(self, key: str, model_id: int, vector: list[float]) -> None:
        self._conn.execute(
            "INSERT INTO search.query_embeddings (query_hash, embed_model_id, embedding)"
            " VALUES (%s, %s, %s::vector) ON CONFLICT DO NOTHING",
            (key, model_id, "[" + ",".join(repr(float(v)) for v in vector) + "]"),
        )
