"""검색어 한글 어절에서 끝에 붙은 조사·어미만 뗀다(portfolio-search 3g 단계 2).

형태소 분석기(Kiwi)로 어절을 나눈 뒤, 끝에서부터 조사(J*)·어미(E*)·접미사(XS*)·보조 용언(VX)·
서술격 조사(VCP)를 떼고 남은 앞부분을 원문 그대로 돌려준다. 형태소의 사전 꼴이 아니라 원문 위치로
자른다. 색인은 글 원문의 2-gram 이라 "까매졌다"는 사전 꼴 "까맣"이 아니라 "까매"로 찾아야 한다.

- "렌더링이" → "렌더링", "정리하는" → "정리", "추천해줘" → "추천", "까매졌다" → "까매"
- 형태소로 나누지 않는다. "방탈출"을 "방" + "탈출"로 나누면 한 음절 "방"은 토큰이 없다
- 뗀 결과가 한 음절이면 어절 그대로 쓴다("검은" → "검은"). 남는 게 없으면 None("에서")

색인(글 본문)은 2-gram 그대로이고, 분석기는 검색 서비스에만 있다.
"""

from __future__ import annotations

from functools import cache

from kiwipiepy import Kiwi

_FUNCTIONAL_PREFIXES = ("J", "E", "XS")
_FUNCTIONAL_TAGS = frozenset({"VX", "VCP"})


@cache
def _kiwi() -> Kiwi:
    return Kiwi()


def load() -> None:
    """모델을 미리 불러온다. 첫 검색어가 불러오는 시간을 기다리지 않게 서비스 시작 때 부른다."""
    _kiwi().tokenize("준비")


def _functional(tag: str) -> bool:
    return tag.startswith(_FUNCTIONAL_PREFIXES) or tag in _FUNCTIONAL_TAGS


def stem(eojeol: str) -> str | None:
    """한글 음절만으로 된 어절 하나. 조사·어미를 뗀 앞부분, 남는 게 없으면 None."""
    morphemes = _kiwi().tokenize(eojeol)
    while morphemes and _functional(morphemes[-1].tag):
        morphemes.pop()
    if not morphemes:
        return None
    end = max(m.start + m.len for m in morphemes)
    return eojeol[:end] if end > 1 else eojeol
