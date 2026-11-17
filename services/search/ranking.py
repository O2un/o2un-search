"""두 후보 목록을 역순위 융합(RRF)으로 합치고 글 단위로 묶는다. DB 를 모르는 순수 함수다."""

from __future__ import annotations

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


def snippet(body: str, limit: int = SNIPPET_CHARS) -> str:
    """청크 본문 앞부분. 맨 앞의 제목 줄은 `heading_path` 와 겹치므로 뺀다."""
    lines = body.splitlines()
    while lines and (lines[0].lstrip().startswith("#") or not lines[0].strip()):
        lines.pop(0)
    text = " ".join(" ".join(lines).split())
    return text if len(text) <= limit else text[:limit].rstrip() + "…"
