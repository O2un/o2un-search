"""검색 서비스의 DB 조회. 읽기 계정(SEARCH_READER_URL)으로 돈다."""

from __future__ import annotations

from dataclasses import dataclass

# 출발값. 바꾸면 단위 5 기준선도 다시 잡는다.
CANDIDATES = 50

# HNSW 기본 ef_search(40)는 후보 수보다 작아 벡터 후보가 40개에서 잘린다.
EF_SEARCH = 100


@dataclass(frozen=True)
class ChunkRow:
    chunk_id: str
    post_id: str
    title: str
    href: str
    anchor: str
    heading_path: str
    body: str


def tsquery(tokens: list[str]) -> str | None:
    """토큰을 OR 로 묶는다. 토큰은 소문자 영숫자나 한글 2-gram 이라 따옴표만 감싸면 된다."""
    unique = list(dict.fromkeys(tokens))
    return " | ".join(f"'{token}'" for token in unique) if unique else None


def section_prefix(section: str | None) -> str | None:
    """`posts.href` 의 LIKE 패턴. section 은 호출하는 쪽이 영숫자·하이픈으로 검사해 둔다."""
    return f"/{section}/%" if section else None


class Store:
    def __init__(self, conn) -> None:  # psycopg.Connection, autocommit
        self._conn = conn
        conn.execute(f"SET hnsw.ef_search = {EF_SEARCH}")

    def keyword(self, tokens: list[str], section: str | None) -> list[str]:
        query = tsquery(tokens)
        if query is None:
            return []
        rows = self._conn.execute(
            "SELECT c.chunk_id"
            " FROM search.chunks c JOIN search.posts p USING (post_id),"
            "      to_tsquery('simple', %(q)s) q"
            " WHERE c.tokens @@ q AND (%(prefix)s::text IS NULL OR p.href LIKE %(prefix)s)"
            " ORDER BY ts_rank_cd(c.tokens, q) DESC, c.chunk_id"
            " LIMIT %(n)s",
            {"q": query, "prefix": section_prefix(section), "n": CANDIDATES},
        ).fetchall()
        return [row[0] for row in rows]

    def vector(self, vector: list[float], model_id: int, section: str | None) -> list[str]:
        """임베딩이 빈 청크와 다른 모델로 임베딩된 청크는 후보에 들지 않는다."""
        rows = self._conn.execute(
            "SELECT c.chunk_id"
            " FROM search.chunks c JOIN search.posts p USING (post_id)"
            " WHERE c.embed_model_id = %(model)s"
            "   AND (%(prefix)s::text IS NULL OR p.href LIKE %(prefix)s)"
            " ORDER BY c.embedding <=> %(v)s::vector"
            " LIMIT %(n)s",
            {
                "v": "[" + ",".join(repr(float(x)) for x in vector) + "]",
                "model": model_id,
                "prefix": section_prefix(section),
                "n": CANDIDATES,
            },
        ).fetchall()
        return [row[0] for row in rows]

    def chunks(self, chunk_ids: list[str]) -> dict[str, ChunkRow]:
        rows = self._conn.execute(
            "SELECT c.chunk_id, c.post_id, p.title, p.href, c.anchor, c.heading_path, c.body"
            " FROM search.chunks c JOIN search.posts p USING (post_id)"
            " WHERE c.chunk_id = ANY(%s)",
            (chunk_ids,),
        ).fetchall()
        return {row[0]: ChunkRow(*row) for row in rows}
