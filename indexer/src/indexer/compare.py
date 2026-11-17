"""두 청커·토크나이저 구현이 공개 글 전체에서 같은 결과를 내는지 대조한다.

글마다 청크 목록과 각 청크 본문의 토큰을 비교하고, 처음 어긋난 곳 하나만 남긴다.
차이에는 글 원문 조각이 찍히므로 블로그 레포(비공개 로그)에서만 돌린다.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path

from .chunker import Chunk
from .core import Core
from .corpus import Post, is_published, iter_posts


def _first_difference(
    base: list[Chunk], other: list[Chunk], base_core: Core, other_core: Core
) -> str | None:
    for index, (a, b) in enumerate(zip(base, other)):
        for f in fields(Chunk):
            left, right = getattr(a, f.name), getattr(b, f.name)
            if left != right:
                return (
                    f"청크 {index} ({a.chunk_id}) {f.name}\n"
                    f"  {base_core.name}: {left!r}\n  {other_core.name}: {right!r}"
                )
        left, right = base_core.tokenize(a.body), other_core.tokenize(b.body)
        if left != right:
            return (
                f"청크 {index} ({a.chunk_id}) tokens\n"
                f"  {base_core.name}: {left!r}\n  {other_core.name}: {right!r}"
            )
    if len(base) != len(other):
        return f"청크 수 {base_core.name} {len(base)}개, {other_core.name} {len(other)}개"
    return None


def compare_post(post: Post, base: Core, other: Core) -> tuple[int, str | None]:
    """청크 수(기준 구현)와 첫 차이를 돌려준다. 같으면 차이는 None."""
    source = post.read()
    expected = base.chunk(source, post.post_id, post.ext)
    actual = other.chunk(source, post.post_id, post.ext)
    return len(expected), _first_difference(expected, actual, base, other)


@dataclass
class Report:
    posts: int = 0
    chunks: int = 0
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def run(blog_root: Path, base: Core, other: Core) -> Report:
    report = Report()
    for post in iter_posts(blog_root):
        if not is_published(post):
            continue
        count, difference = compare_post(post, base, other)
        report.posts += 1
        report.chunks += count
        if difference is not None:
            report.problems.append(f"{post.post_id}: {difference}")
    return report
