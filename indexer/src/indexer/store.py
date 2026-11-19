"""search 스키마를 읽고 쓰는 Postgres 저장소. sync 와 embed 가 같이 쓴다."""

from __future__ import annotations

import psycopg

from .embed import Pending
from .site import SitePost
from .sync import Row, State


def _vector(values: list[float]) -> str:
    return "[" + ",".join(repr(float(value)) for value in values) + "]"


class PgStore:
    def __init__(self, url: str) -> None:
        self._conn = psycopg.connect(url, autocommit=False)

    def close(self) -> None:
        self._conn.close()

    # sync

    def load(self) -> State:
        with self._conn.cursor() as cur:
            cur.execute("SELECT post_id, href, title, description FROM search.posts")
            posts = {row[0]: SitePost(*row[1:]) for row in cur.fetchall()}
            cur.execute("SELECT chunk_id, content_hash, context_chunk_id, embed_hash FROM search.chunks")
            chunks = {row[0]: tuple(row[1:]) for row in cur.fetchall()}
        self._conn.commit()
        return State(posts=posts, chunks=chunks)

    def delete_posts(self, post_ids: list[str]) -> None:
        with self._conn.transaction(), self._conn.cursor() as cur:
            cur.execute("DELETE FROM search.posts WHERE post_id = ANY(%s)", (post_ids,))

    def delete_chunks(self, chunk_ids: list[str]) -> None:
        with self._conn.transaction(), self._conn.cursor() as cur:
            cur.execute("DELETE FROM search.chunks WHERE chunk_id = ANY(%s)", (chunk_ids,))

    def upsert_posts(self, posts: dict[str, SitePost]) -> None:
        with self._conn.transaction(), self._conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO search.posts (post_id, title, href, description) VALUES (%s, %s, %s, %s)"
                " ON CONFLICT (post_id) DO UPDATE SET title = EXCLUDED.title, href = EXCLUDED.href,"
                " description = EXCLUDED.description",
                [(post_id, post.title, post.href, post.description) for post_id, post in posts.items()],
            )

    def clear_embeddings(self, post_ids: list[str]) -> None:
        with self._conn.transaction(), self._conn.cursor() as cur:
            cur.execute(
                "UPDATE search.chunks SET embedding = NULL, embed_model_id = NULL"
                " WHERE post_id = ANY(%s)",
                (post_ids,),
            )

    def upsert_chunks(self, rows: list[Row]) -> None:
        with self._conn.transaction(), self._conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO search.chunks (
                    chunk_id, post_id, anchor, heading_path, body, tokens, content_hash,
                    context_chunk_id, embed_hash, indexed_at
                ) VALUES (%s, %s, %s, %s, %s, to_tsvector('simple', %s), %s, %s, %s, now())
                ON CONFLICT (chunk_id) DO UPDATE SET
                    post_id = EXCLUDED.post_id,
                    anchor = EXCLUDED.anchor,
                    heading_path = EXCLUDED.heading_path,
                    body = EXCLUDED.body,
                    tokens = EXCLUDED.tokens,
                    content_hash = EXCLUDED.content_hash,
                    context_chunk_id = EXCLUDED.context_chunk_id,
                    embed_hash = EXCLUDED.embed_hash,
                    indexed_at = EXCLUDED.indexed_at,
                    embedding = NULL,
                    embed_model_id = NULL
                """,
                [
                    (
                        row.chunk_id,
                        row.post_id,
                        row.anchor,
                        row.heading_path,
                        row.body,
                        " ".join(row.tokens),
                        row.content_hash,
                        row.context_chunk_id,
                        row.embed_hash,
                    )
                    for row in rows
                ],
            )

    # embed

    def model_id(self, name: str) -> int:
        with self._conn.transaction(), self._conn.cursor() as cur:
            cur.execute(
                "INSERT INTO search.embed_models (name) VALUES (%s) ON CONFLICT (name) DO NOTHING",
                (name,),
            )
            cur.execute("SELECT id FROM search.embed_models WHERE name = %s", (name,))
            row = cur.fetchone()
        assert row is not None
        return row[0]

    def pending(self, model_id: int) -> list[Pending]:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT c.chunk_id, p.title, c.heading_path, c.body, n.body, c.embed_hash <> ''"
                " FROM search.chunks c JOIN search.posts p USING (post_id)"
                " LEFT JOIN search.chunks n ON n.chunk_id = c.context_chunk_id"
                " WHERE c.embed_model_id IS DISTINCT FROM %s"
                " ORDER BY c.chunk_id",
                (model_id,),
            )
            rows = [Pending(*row) for row in cur.fetchall()]
        self._conn.commit()
        return rows

    def set_embeddings(self, chunk_ids: list[str], vectors: list[list[float]], model_id: int) -> None:
        with self._conn.transaction(), self._conn.cursor() as cur:
            cur.executemany(
                "UPDATE search.chunks SET embedding = %s::vector, embed_model_id = %s"
                " WHERE chunk_id = %s",
                [
                    (_vector(vector), model_id, chunk_id)
                    for chunk_id, vector in zip(chunk_ids, vectors, strict=True)
                ],
            )

    # cache

    def prune_query_cache(self, days: int) -> int:
        """만든 지 days 일이 지난 검색어 캐시 행을 지우고 지운 수를 돌려준다."""
        with self._conn.transaction(), self._conn.cursor() as cur:
            cur.execute(
                "DELETE FROM search.query_embeddings WHERE created_at < now() - make_interval(days => %s)",
                (days,),
            )
            return cur.rowcount
