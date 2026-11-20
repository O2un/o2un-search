"""두 후보 목록을 역순위 융합(RRF)으로 합치고 글 단위로 묶는다. DB 를 모르는 순수 함수다."""

from __future__ import annotations

import re
from dataclasses import dataclass

# 출발값. 바꾸면 단위 5 기준선도 다시 잡는다.
RRF_K = 60

SNIPPET_CHARS = 160


@dataclass(frozen=True)
class PostHit:
    post_id: str
    chunk_id: str  # 이 글에서 점수가 가장 높은 청크
    score: float


def fuse(*rankings: list[str], k: int = RRF_K) -> dict[str, float]:
    """청크 id 목록(순위 순)들을 받아 청크마다 Σ 1 / (k + 순위). 순위는 1부터다."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return scores


def group_by_post(scores: dict[str, float], post_of: dict[str, str], limit: int) -> list[PostHit]:
    """글 점수 = 그 글 청크의 최고 점수. 동점은 청크 id 순으로 고정한다."""
    best: dict[str, PostHit] = {}
    for chunk_id, score in sorted(scores.items(), key=lambda item: (-item[1], item[0])):
        post_id = post_of[chunk_id]
        if post_id not in best:
            best[post_id] = PostHit(post_id, chunk_id, score)
    return list(best.values())[:limit]


# 검색어가 본문 중간에 있으면 그 앞을 이만큼만 남기고 자른다.
SNIPPET_LEAD = 30

_ASCII_WORD = re.compile(r"[a-z0-9]")


def _find(lowered: str, term: str) -> int:
    """검색어가 처음 나오는 곳. 블로그의 강조와 같이, 영문·숫자로 시작하는 검색어는 앞 글자가,
    영문·숫자로 끝나는 검색어는 뒤 글자가 영문·숫자가 아닐 때만 센다("go"가 "google"에 걸리지 않게).
    한글 검색어는 어디든 센다."""
    if _ASCII_WORD.match(term[0]) is None and _ASCII_WORD.match(term[-1]) is None:
        return lowered.find(term)
    pattern = re.escape(term)
    if _ASCII_WORD.match(term[0]):
        pattern = r"(?<![a-z0-9])" + pattern
    if _ASCII_WORD.match(term[-1]):
        pattern += r"(?![a-z0-9])"
    found = re.search(pattern, lowered)
    return -1 if found is None else found.start()


def snippet(body: str, terms: list[str] = (), limit: int = SNIPPET_CHARS) -> str:
    """청크 본문에서 검색어가 처음 나오는 곳 근처. 없으면 앞부분.

    맨 앞의 제목 줄은 `heading_path` 와 겹치므로 뺀다.
    """
    lines = body.splitlines()
    while lines and (lines[0].lstrip().startswith("#") or not lines[0].strip()):
        lines.pop(0)
    text = " ".join(" ".join(lines).split())
    lowered = text.lower()
    found = [i for i in (_find(lowered, term.lower()) for term in terms if term) if i >= 0]
    first = min(found, default=0)
    start = 0
    # 앞부분에서 검색어가 보이면 그대로 둔다.
    if first > limit - SNIPPET_LEAD:
        start = first - SNIPPET_LEAD
        # 단어 중간에서 자르지 않도록 가까운 앞쪽 공백까지 당긴다.
        space = text.rfind(" ", 0, start)
        if space >= 0 and start - space < 15:
            start = space + 1
    head = "…" if start > 0 else ""
    rest = text[start:]
    return head + (rest if len(rest) <= limit else rest[:limit].rstrip() + "…")
