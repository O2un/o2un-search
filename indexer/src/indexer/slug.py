"""블로그가 제목에 붙이는 id 를 그대로 다시 만든다.

블로그(Astro)는 github-slugger 로 제목 id 를 만든다. 한 글 안에서 같은 슬러그가 다시 나오면
`-1`, `-2` 를 붙인다. 청크 앵커가 이 id 와 바이트 단위로 같아야 검색 결과가 절로 바로 이어진다.
"""

from __future__ import annotations

from bisect import bisect_right

from ._slug_table import REMOVED_RANGES

_STARTS = [start for start, _ in REMOVED_RANGES]


def _removed(char: str) -> bool:
    code = ord(char)
    index = bisect_right(_STARTS, code) - 1
    return index >= 0 and code <= REMOVED_RANGES[index][1]


def slugify(value: str) -> str:
    """github-slugger 의 `slug()`. 중복 번호는 붙이지 않는다."""
    lowered = value.lower()
    return "".join(char for char in lowered if not _removed(char)).replace(" ", "-")


class Slugger:
    """github-slugger 의 `BananaSlug`. 글 하나마다 새로 만든다."""

    def __init__(self) -> None:
        self._occurrences: dict[str, int] = {}

    def slug(self, value: str) -> str:
        result = slugify(value)
        original = result
        while result in self._occurrences:
            self._occurrences[original] += 1
            result = f"{original}-{self._occurrences[original]}"
        self._occurrences[result] = 0
        return result
