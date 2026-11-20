"""검색 API. `POST /search`와 미리 깨우기 `POST /warm`이고, 공유 키 헤더가 맞는 요청만 받는다.

환경 변수
- SEARCH_READER_URL: Neon 읽기 계정 연결 문자열
- GEMINI_API_KEY: 검색어 임베딩
- SEARCH_API_KEY: 공유 키. 블로그 서버만 갖는다. 비어 있으면 모든 요청을 거부한다
- INDEXER_CORE: `rust` (Vercel 설정). 없으면 Python 구현
- SEARCH_EMBED_TIMEOUT_S: 공급자 대기 상한(초), 기본 1.5. 강등 확인용으로 0 을 줄 수 있다

로컬에서는 이 폴더의 `.env` 를 읽는다(이미 설정된 값은 덮어쓰지 않는다).
"""

from __future__ import annotations

import time

_started = time.perf_counter()

import hmac  # noqa: E402
import logging  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
from typing import Literal  # noqa: E402
from urllib.parse import urlsplit  # noqa: E402

import psycopg  # noqa: E402
from fastapi import FastAPI, Header, Request  # noqa: E402
from fastapi.exceptions import RequestValidationError  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from indexer import env as dotenv  # noqa: E402

dotenv.load()

from indexer import core  # noqa: E402
from indexer.embedding import make_provider  # noqa: E402
from indexer.query_cache import PgQueryCache  # noqa: E402

import korean  # noqa: E402
import search  # noqa: E402
from store import Store  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
log = logging.getLogger("search")
# 공급자 SDK 가 요청마다 남기는 HTTP 로그는 끈다. 실패는 search 로그가 남긴다.
logging.getLogger("httpx").setLevel(logging.WARNING)

# 서비스 자체 상한. 블로그가 공개하는 상한(3b)보다 넉넉하게 둔다. 응답에 이 값을 말하지 않는다.
QUERY_MAX_CHARS = 200
LIMIT_DEFAULT = 10
LIMIT_MAX = 20
EMBED_TIMEOUT_S = float(os.environ.get("SEARCH_EMBED_TIMEOUT_S", "1.5"))

_SECTION = re.compile(r"^[a-z0-9-]{1,40}$")


def _provider():
    if not os.environ.get("GEMINI_API_KEY"):
        log.error("GEMINI_API_KEY is not set; keyword only")
        return None
    inner = make_provider(retry=False, timeout_s=max(EMBED_TIMEOUT_S, 0.001) + 1.0)
    return search.DeadlineProvider(inner, EMBED_TIMEOUT_S)


core.selected()  # 토크나이저 구현을 import 때 정해 첫 요청에 얹지 않는다
korean.load()  # 형태소 분석 모델(1초 남짓)도 import 때 불러, 블로그의 /warm 이 기다리게 한다
_PROVIDER = _provider()
_import_ms = round((time.perf_counter() - _started) * 1000)
_first_request = True
log.info(
    "instance start: import %dms, core %s, db %s",
    _import_ms,
    core.selected().name,
    urlsplit(os.environ.get("SEARCH_READER_URL", "")).hostname,
)

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


class SearchRequest(BaseModel):
    query: str
    section: str | None = None
    limit: int | None = None
    # keyword: 공급자를 부르지 않고 키워드 후보만 쓴다. 블로그가 먼저 보일 결과를 받을 때 쓴다.
    mode: Literal["hybrid", "keyword"] = "hybrid"


def _bad_request() -> JSONResponse:
    return JSONResponse({"detail": "bad request"}, status_code=400)


@app.exception_handler(RequestValidationError)
def _validation(_request: Request, error: RequestValidationError) -> JSONResponse:
    # 입력값(검색어)은 로그에 남기지 않는다.
    log.error("invalid request: %s", [(e["loc"], e["type"]) for e in error.errors()])
    return _bad_request()


def _authorized(key: str | None) -> bool:
    expected = os.environ.get("SEARCH_API_KEY", "")
    if not expected:
        log.error("SEARCH_API_KEY is not set; rejecting")
        return False
    return key is not None and hmac.compare_digest(key.encode(), expected.encode())


@app.post("/search")
def search_posts(body: SearchRequest, x_search_key: str | None = Header(default=None)):
    global _first_request
    if not _authorized(x_search_key):
        return JSONResponse({"detail": "unauthorized"}, status_code=401)

    query = body.query.strip()
    limit = LIMIT_DEFAULT if body.limit is None else body.limit
    if not query or len(query) > QUERY_MAX_CHARS:
        log.error("query rejected: %d chars", len(query))
        return _bad_request()
    if not 1 <= limit <= LIMIT_MAX or (body.section is not None and not _SECTION.match(body.section)):
        log.error("params rejected: limit=%r section=%r", body.limit, body.section)
        return _bad_request()

    started = time.perf_counter()
    with psycopg.connect(os.environ["SEARCH_READER_URL"], autocommit=True) as conn:
        provider = _PROVIDER if body.mode == "hybrid" else None
        result = search.run(Store(conn), PgQueryCache(conn), provider, query, body.section, limit)
    took_ms = round((time.perf_counter() - started) * 1000)
    if _first_request:
        log.info("first request on instance: %dms (import %dms)", took_ms, _import_ms)
        _first_request = False
    log.info("search %s (asked %s): %d results, %dms", result.mode, body.mode, len(result.results), took_ms)
    return {"mode": result.mode, "results": result.results, "terms": result.terms}


@app.post("/warm", status_code=204)
def warm(x_search_key: str | None = Header(default=None)):
    """방문자가 검색창을 열면 블로그가 부른다. 인스턴스를 띄우고 쉬고 있던 DB를 깨운다."""
    if not _authorized(x_search_key):
        return JSONResponse({"detail": "unauthorized"}, status_code=401)
    started = time.perf_counter()
    with psycopg.connect(os.environ["SEARCH_READER_URL"], autocommit=True) as conn:
        conn.execute("SELECT 1")
    log.info("warm: db %dms", round((time.perf_counter() - started) * 1000))
    return None
