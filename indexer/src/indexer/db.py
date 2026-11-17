"""search 스키마 마이그레이션과 DB 계정 관리. 모두 DB 소유자 연결(SEARCH_OWNER_URL)로 돈다.

마이그레이션 기록은 `search.schema_migrations` 에 둔다. 블로그 레포의 러너는
`public.schema_migrations` 를 쓰므로 서로 섞이지 않는다. 파일 하나를 트랜잭션 하나로 통째로
실행해서 `DO $$ ... $$` 블록도 쓸 수 있다.
"""

from __future__ import annotations

import secrets
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

import psycopg
from psycopg import errors, sql

MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"

ROLES = {"search_writer": "SEARCH_WRITER_URL", "search_reader": "SEARCH_READER_URL"}

# 계정마다 읽혀야 하는 테이블과 거부돼야 하는 테이블. 읽기 계정(검색 서비스)은 테이블에 직접
# 닿지 않고 search 스키마 함수(마이그레이션 006)만 부른다.
_COMMENTS = ("public.comments", "public.comment_authors")
_SEARCH_TABLES = ("search.posts", "search.chunks", "search.embed_models", "search.query_embeddings")
READABLE = {
    "search_writer": ("search.posts", "search.chunks", "search.embed_models"),
    "search_reader": (),
}
DENIED = {
    "search_writer": _COMMENTS,
    "search_reader": _COMMENTS + _SEARCH_TABLES,
}
# 읽기 계정이 부를 수 있어야 하는 함수. 쓰는 함수(put_query_embedding)는 트랜잭션을 되돌려 시험한다.
CALLABLE = {
    "search_writer": (),
    "search_reader": (
        "SELECT search.embed_model_id('none')",
        "SELECT search.cached_query_embedding('none', 0::smallint)",
        "SELECT count(*) FROM search.keyword_candidates(ARRAY['검색'], NULL, 1)",
        "SELECT count(*) FROM search.vector_candidates(array_fill(0, ARRAY[768])::vector, 0::smallint, NULL, 1)",
        "SELECT count(*) FROM search.chunks_by_id(ARRAY[]::text[])",
        "SELECT search.put_query_embedding('grant-check',"
        " search.embed_model_id('gemini/gemini-embedding-2'), array_fill(0, ARRAY[768])::vector)",
    ),
}


def migrate(owner_url: str) -> list[str]:
    applied_now: list[str] = []
    with psycopg.connect(owner_url) as conn:
        with conn.transaction():
            conn.execute("CREATE SCHEMA IF NOT EXISTS search")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS search.schema_migrations ("
                " name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
            )
        applied = {row[0] for row in conn.execute("SELECT name FROM search.schema_migrations")}
        for path in sorted(MIGRATIONS.glob("*.sql")):
            if path.name in applied:
                continue
            with conn.transaction():
                conn.execute(path.read_text(encoding="utf-8"))
                conn.execute("INSERT INTO search.schema_migrations (name) VALUES (%s)", (path.name,))
            applied_now.append(path.name)
    return applied_now


def role_url(owner_url: str, role: str, password: str) -> str:
    parts = urlsplit(owner_url)
    host = parts.netloc.rsplit("@", 1)[-1]
    netloc = f"{quote(role, safe='')}:{quote(password, safe='')}@{host}"
    return urlunsplit(parts._replace(netloc=netloc))


def open_login(owner_url: str, role: str) -> str:
    """계정에 새 비밀번호를 정해 로그인을 열고, 그 계정의 연결 문자열을 돌려준다."""
    if role not in ROLES:
        raise SystemExit(f"계정은 {sorted(ROLES)} 중 하나입니다.")
    password = secrets.token_urlsafe(32)
    with psycopg.connect(owner_url) as conn:
        conn.execute(
            sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(
                sql.Identifier(role), sql.Literal(password)
            )
        )
    return role_url(owner_url, role, password)


def check_grants(url: str, role: str) -> list[tuple[str, bool, str]]:
    """(질의, 기대대로인지, 결과) 목록."""
    results: list[tuple[str, bool, str]] = []
    with psycopg.connect(url) as conn:
        for table in READABLE[role]:
            with conn.transaction(force_rollback=True):
                try:
                    count = conn.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.SQL(table))).fetchone()
                    results.append((f"SELECT {table}", True, f"{count[0] if count else 0}행"))
                except errors.Error as error:
                    results.append((f"SELECT {table}", False, type(error).__name__))
        for table in DENIED[role]:
            with conn.transaction(force_rollback=True):
                try:
                    conn.execute(sql.SQL("SELECT 1 FROM {} LIMIT 1").format(sql.SQL(table)))
                    results.append((f"SELECT {table}", False, "읽혔다"))
                except errors.InsufficientPrivilege:
                    results.append((f"SELECT {table}", True, "권한 없음으로 거부"))
        for call in CALLABLE[role]:
            with conn.transaction(force_rollback=True):
                try:
                    conn.execute(call)
                    results.append((call, True, "실행됨"))
                except errors.Error as error:
                    results.append((call, False, type(error).__name__))
    return results
