"""검색 서비스의 DB 조회. 읽기 계정(SEARCH_READER_URL)으로 `search` 스키마 함수만 부른다.

함수 정의는 indexer/migrations/006_search_functions.sql 에 있다. 서비스는 테이블 구조를 모른다.
"""

from __future__ import annotations

from dataclasses import dataclass

from indexer.query_cache import vector_literal

# 출발값. 바꾸면 단위 5 기준선도 다시 잡는다.
CANDIDATES = 50


@dataclass(frozen=True)
class ChunkRow:
    chunk_id: str
    post_id: str
    title: str
    href: str
    anchor: str
    heading_path: str
    body: str


class Store:
    def __init__(self, conn) -> None:  # psycopg.Connection, autocommit
        self._conn = conn

    def keyword(self, tokens: list[str], section: str | None) -> list[str]:
        rows = self._conn.execute(
            "SELECT chunk_id FROM search.keyword_candidates(%s::text[], %s, %s)",
            (tokens, section, CANDIDATES),
        ).fetchall()
        return [row[0] for row in rows]

    def vector(self, vector: list[float], model_id: int, section: str | None) -> list[str]:
        rows = self._conn.execute(
            "SELECT chunk_id FROM search.vector_candidates(%s::vector, %s::smallint, %s, %s)",
            (vector_literal(vector), model_id, section, CANDIDATES),
        ).fetchall()
        return [row[0] for row in rows]

    def chunks(self, chunk_ids: list[str]) -> dict[str, ChunkRow]:
        rows = self._conn.execute(
            "SELECT * FROM search.chunks_by_id(%s::text[])", (chunk_ids,)
        ).fetchall()
        return {row[0]: ChunkRow(*row) for row in rows}
