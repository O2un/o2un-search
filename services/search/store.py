"""검색 서비스의 DB 조회. 읽기 계정(SEARCH_READER_URL)으로 `search` 스키마 함수만 부른다.

함수 정의는 indexer/migrations/006_search_functions.sql, 009_embed_context.sql, 011_keyword_alternatives.sql 에
있다. 서비스는 테이블 구조를 모른다.
"""

from __future__ import annotations

from dataclasses import dataclass

from indexer.query_cache import vector_literal

# 키워드·벡터 후보를 각각 이만큼 뽑는다. 바꾸면 확인 검색어의 결과를 하나씩 다시 읽고 판정한다.
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

    def keyword(self, words: list[list[list[str]]], section: str | None) -> list[str]:
        """단어마다 대안 목록, 대안마다 토큰 목록. 대안 하나의 토큰이 모두 맞으면 단어가 맞는다.
        핵심 단어 무게가 KEYWORD_MIN_COVER 이상 맞은 청크만 온다(마이그레이션 011)."""
        flat = [
            (token, w, a)
            for w, alternatives in enumerate(words)
            for a, alternative in enumerate(alternatives)
            for token in alternative
        ]
        rows = self._conn.execute(
            "SELECT chunk_id FROM search.keyword_matches_alt("
            "%s::text[], %s::int[], %s::int[], %s, %s, %s::real)",
            (
                [token for token, _, _ in flat],
                [w for _, w, _ in flat],
                [a for _, _, a in flat],
                section,
                CANDIDATES,
                KEYWORD_MIN_COVER,
            ),
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
