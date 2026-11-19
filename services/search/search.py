"""검색 한 번의 흐름: 검색어 임베딩(캐시 → 공급자, 대기 상한) → 키워드·벡터 후보 → RRF → 글 단위."""

from __future__ import annotations

import logging
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Protocol

from indexer import core
from indexer.query_cache import QueryCache, embed_query
from indexer.sync import META_CHUNK_SUFFIX

from ranking import fuse, group_by_post, snippet
from store import ChunkRow

log = logging.getLogger("search")

_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="embed")

# 단어가 이만큼 이하인 검색어는 키워드에 걸린 글이 있으면 벡터로만 들어온 글을 뺀다.
# "공포" 같은 한 단어는 임베딩 거리로 관련 글과 무관한 글이 갈리지 않는다(관련 글 0.31~0.38,
# 무관한 글 0.375~). 키워드 적중이 없으면 벡터 결과가 유일한 단서라 그대로 둔다.
SHORT_QUERY_WORDS = 1


class Candidates(Protocol):
    def keyword(self, words: list[list[str]], section: str | None) -> list[str]: ...

    def vector(self, vector: list[float], model_id: int, section: str | None) -> list[str]: ...

    def chunks(self, chunk_ids: list[str]) -> dict[str, ChunkRow]: ...

    def descriptions(self, post_ids: list[str]) -> dict[str, str]: ...


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


# 토크나이저가 토큰을 만드는 구간과 같다: 한글 음절, ASCII 영문·숫자.
_RUN = re.compile(r"[가-힣]+|[A-Za-z0-9]+")
_HANGUL_RUN = re.compile(r"[가-힣]{3,}")


def query_words(query: str) -> list[tuple[str, list[str]]]:
    """검색어를 단어로 나눈다. (어간, 토큰) 목록이고 어간이 같은 단어는 한 번만 둔다.

    한글 세 음절 이상은 끝 음절을 뗀다. 조사·어미("렌더링이", "까맣게", "만들기")가 단어마다
    달라 그대로 두면 글에 쓰인 꼴과 맞지 않는다. 어간은 결과 강조에도 쓴다.
    """
    words: list[tuple[str, list[str]]] = []
    seen: set[str] = set()
    for run in _RUN.findall(unicodedata.normalize("NFC", query)):
        stem = run[:-1] if _HANGUL_RUN.fullmatch(run) else run
        tokens = core.tokenize(stem)
        if tokens and stem.lower() not in seen:
            seen.add(stem.lower())
            words.append((stem, tokens))
    return words


@dataclass(frozen=True)
class Result:
    mode: str  # "hybrid" | "keyword"
    results: list[dict]
    terms: list[str]  # 결과에서 강조할 검색어 어간


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
    words = query_words(query)
    terms = [stem for stem, _ in words]
    keyword = store.keyword([tokens for _, tokens in words], section) if words else []
    embedded = _query_vector(cache, provider, query)
    vector = store.vector(embedded[0], embedded[1], section) if embedded else []

    scores = fuse(keyword, vector)
    rows = store.chunks(list(scores))
    # 후보를 뽑은 뒤 색인이 지운 청크는 빼고 묶는다.
    scores = {cid: score for cid, score in scores.items() if cid in rows}
    # 벡터 후보는 검색어와 상관없이 늘 상위 청크를 채우므로, 순위만으로는 검색어가 실제로
    # 글에 들어 있는지 알 수 없다. 호출하는 쪽이 보일 글을 거를 수 있게 키워드 적중을 따로 싣는다.
    keyword_posts = {rows[cid].post_id for cid in keyword if cid in rows}
    if len(words) <= SHORT_QUERY_WORDS and keyword_posts:
        scores = {cid: score for cid, score in scores.items() if rows[cid].post_id in keyword_posts}
    hits = group_by_post(scores, {cid: row.post_id for cid, row in rows.items()}, limit)
    meta_posts = [hit.post_id for hit in hits if hit.chunk_id.endswith(META_CHUNK_SUFFIX)]
    descriptions = store.descriptions(meta_posts) if meta_posts else {}
    results = [
        {
            "post_id": hit.post_id,
            "title": rows[hit.chunk_id].title,
            "href": rows[hit.chunk_id].href,
            "best": _best(rows[hit.chunk_id], terms, descriptions),
            "keyword": hit.post_id in keyword_posts,
            "score": round(hit.score, 6),
        }
        for hit in hits
    ]
    return Result("hybrid" if embedded else "keyword", results, terms)


def _best(row: ChunkRow, terms: list[str], descriptions: dict[str, str]) -> dict:
    """대표 절. 글 정보 청크(3f)는 프론트매터 단어를 모은 줄이라 그대로 보이지 않고, 글 설명을
    미리보기로 쓴다. 절 이름은 비워 도입부처럼 글 맨 위로 보낸다."""
    if row.chunk_id.endswith(META_CHUNK_SUFFIX):
        return {"anchor": "", "heading_path": "", "snippet": snippet(descriptions.get(row.post_id, ""))}
    return {"anchor": row.anchor, "heading_path": row.heading_path, "snippet": snippet(row.body, terms)}
