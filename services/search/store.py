"""검색 서비스의 DB 조회. 읽기 계정(SEARCH_READER_URL)으로 `search` 스키마 함수만 부른다.

함수 정의는 indexer/migrations/006_search_functions.sql, 008_keyword_cover.sql, 009_embed_context.sql 에 있다. 서비스는 테이블 구조를 모른다.
"""

from __future__ import annotations

from dataclasses import dataclass

from indexer.query_cache import vector_literal

# 출발값. 바꾸면 단위 5 기준선도 다시 잡는다.
CANDIDATES = 50
# 청크 하나가 맞혀야 하는 단어 무게(드문 단어일수록 무겁다)의 비율. 2026-11-18 문장 검색어 6개로 정했다.
KEYWORD_MIN_COVER = 0.5


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

    def keyword(self, words: list[list[str]], section: str | None) -> list[str]:
        """단어마다 토큰 목록. 핵심 단어 무게가 KEYWORD_MIN_COVER 이상 맞은 청크만 온다(마이그레이션 008)."""
        tokens = [token for word in words for token in word]
        word_of = [index for index, word in enumerate(words) for _ in word]
        rows = self._conn.execute(
            "SELECT chunk_id FROM search.keyword_matches(%s::text[], %s::int[], %s, %s, %s::real)",
            (tokens, word_of, section, CANDIDATES, KEYWORD_MIN_COVER),
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

    def descriptions(self, post_ids: list[str]) -> dict[str, str]:
        """글 설명(마이그레이션 009)."""
        rows = self._conn.execute(
            "SELECT * FROM search.post_descriptions(%s::text[])", (post_ids,)
        ).fetchall()
        return {row[0]: row[1] for row in rows}
