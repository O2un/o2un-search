"""두 청커·토크나이저 구현의 속도를 공개 글 전체로 잰다.

한 바퀴는 공개 글 전체를 `chunk` 하고 각 청크 본문을 `tokenize` 하는 것이다. 글은 미리 읽어
두므로 파일 읽기는 시간에 들어가지 않는다. Rust 시간에는 Python 경계를 넘는 비용(문자열 복사,
튜플과 `Chunk` 생성)이 들어간다. indexer 가 실제로 받는 속도가 이것이다.

시간에 따른 흔들림이 한쪽에만 몰리지 않게 바퀴마다 두 구현을 번갈아 돌리고, 재기 전에 한
바퀴씩 버린다(정규식 컴파일 같은 첫 호출 비용).
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path

from .core import Core
from .corpus import is_published, iter_posts

Source = tuple[str, str, str]


@dataclass
class Timing:
    name: str
    seconds: list[float] = field(default_factory=list)

    @property
    def median(self) -> float:
        return statistics.median(self.seconds)


@dataclass
class Result:
    posts: int
    chunks: int
    repeat: int
    timings: list[Timing]


def load_sources(blog_root: Path) -> list[Source]:
    return [
        (post.read(), post.post_id, post.ext)
        for post in iter_posts(blog_root)
        if is_published(post)
    ]


def one_round(core: Core, sources: list[Source]) -> tuple[float, int]:
    chunks = 0
    start = time.perf_counter()
    for source, post_id, ext in sources:
        for item in core.chunk(source, post_id, ext):
            core.tokenize(item.body)
            chunks += 1
    return time.perf_counter() - start, chunks


def run(sources: list[Source], cores: list[Core], repeat: int) -> Result:
    timings = [Timing(core.name) for core in cores]
    chunks = 0
    for core in cores:
        _, chunks = one_round(core, sources)
    for _ in range(repeat):
        for core, timing in zip(cores, timings):
            seconds, _ = one_round(core, sources)
            timing.seconds.append(seconds)
    return Result(posts=len(sources), chunks=chunks, repeat=repeat, timings=timings)
