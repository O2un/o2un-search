"""검색 한 번의 흐름: 검색어 임베딩(캐시 → 공급자, 대기 상한) → 키워드·벡터 후보 → RRF → 글 단위."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Protocol

from indexer import core
from indexer.query_cache import QueryCache, embed_query

from ranking import fuse, group_by_post, snippet
from store import ChunkRow

log = logging.getLogger("search")

_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="embed")


class Candidates(Protocol):
    def keyword(self, tokens: list[str], section: str | None) -> list[str]: ...

    def vector(self, vector: list[float], model_id: int, section: str | None) -> list[str]: ...

    def chunks(self, chunk_ids: list[str]) -> dict[str, ChunkRow]: ...


class DeadlineProvider:
    """공급자 호출을 `seconds` 까지만 기다린다. 넘기면 TimeoutError 이고 호출은 뒤에서 끝난다."""

    def __init__(self, inner, seconds: float) -> None:
        self._inner = inner
        self._seconds = seconds
        self.model_id = inner.model_id

    def embed_documents(self, documents):  # 검색 경로는 쓰지 않는다
        raise NotImplementedError

    def embed_query(self, query: str) -> list[float]:
        return _pool.submit(self._inner.embed_query, query).result(timeout=self._seconds)


@dataclass(frozen=True)
class Result:
    mode: str  # "hybrid" | "keyword"
    results: list[dict]


def _query_vector(cache: QueryCache, provider, query: str) -> tuple[list[float], int] | None:
    """(벡터, 모델 id). 얻지 못하면 None 이고 사유는 로그에만 남긴다."""
    if provider is None:
        return None
    model_id = cache.model_id(provider.model_id)
    if model_id is None:
        log.error("embed model not registered: %s", provider.model_id)
        return None
    try:
        vector, hit = embed_query(cache, provider, query)
    except Exception as error:  # 한도, 시간 초과, 키 오류 모두 키워드로 강등한다
        log.error("query embedding failed: %s: %s", type(error).__name__, error)
        return None
    log.info("query embedding: %s", "cache" if hit else "provider")
    return vector, model_id


def run(store: Candidates, cache: QueryCache, provider, query: str, section: str | None, limit: int) -> Result:
    keyword = store.keyword(core.tokenize(query), section)
    embedded = _query_vector(cache, provider, query)
    vector = store.vector(embedded[0], embedded[1], section) if embedded else []

    scores = fuse(keyword, vector)
    rows = store.chunks(list(scores))
    # 후보를 뽑은 뒤 색인이 지운 청크는 빼고 묶는다.
    scores = {cid: score for cid, score in scores.items() if cid in rows}
    hits = group_by_post(scores, {cid: row.post_id for cid, row in rows.items()}, limit)
    results = [
        {
            "post_id": hit.post_id,
            "title": rows[hit.chunk_id].title,
            "href": rows[hit.chunk_id].href,
            "best": {
                "anchor": rows[hit.chunk_id].anchor,
                "heading_path": rows[hit.chunk_id].heading_path,
                "snippet": snippet(rows[hit.chunk_id].body),
            },
            "score": round(hit.score, 6),
        }
        for hit in hits
    ]
    return Result("hybrid" if embedded else "keyword", results)
