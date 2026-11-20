"""검색어 단어를 동의어 묶음으로 넓힌다(portfolio-search 3g 단계 3).

묶음은 `indexer._dev_terms.SYNONYMS` 다. 검색어 단어가 묶음의 한 표기면 묶음의 다른 표기를 같은
단어의 대안으로 붙인다. 키워드 판정(마이그레이션 011)은 대안 중 하나의 토큰을 모두 가진 청크를 맞는
것으로 본다. 색인은 바꾸지 않는다.

- 영문 표기의 토큰은 검색어와 같이 기본 꼴(`word_forms.query_form`)이다. "Shaders"도 `shader` 묶음을 찾는다
- 한글 표기의 토큰은 2-gram 이다. 한글 검색어는 조사·어미를 뗀 어간("유니티로" → "유니티")으로 묶음을 찾는다
- 한글·영문이 섞인 표기(`c샵`)는 검색어에서 알아보기만 하고 대안 토큰은 없다
"""

from __future__ import annotations

import re

from indexer import core
from indexer._dev_terms import SYNONYMS, TERMS
from indexer.word_forms import query_form

_HANGUL = re.compile(r"[가-힣]+")
_LETTERS = re.compile(r"[a-z]+")

_BUNDLE_OF: dict[str, tuple[str, ...]] = {form: bundle for bundle in SYNONYMS for form in bundle}
# 영문만인 표기는 기본 꼴로도 찾는다("shaders" → shader 묶음).
_BUNDLE_OF_BASE: dict[str, tuple[str, ...]] = {
    query_form(form): bundle for bundle in SYNONYMS for form in bundle if _LETTERS.fullmatch(form)
}

# 검색어에서 통째로 알아봐야 하는 섞인 표기. 그대로 두면 `c샵`이 한 글자 `c`와 한 음절 `샵`으로
# 갈려 둘 다 버려진다.
MIXED = tuple(
    sorted(
        (form for form in _BUNDLE_OF if not form.isascii() and _HANGUL.fullmatch(form) is None),
        key=lambda form: (-len(form), form),
    )
)


def bundle(word: str) -> tuple[str, ...] | None:
    """검색어 단어(한글은 어간)가 든 묶음. 없으면 None."""
    key = word.lower()
    found = _BUNDLE_OF.get(key)
    if found is None and _LETTERS.fullmatch(key):
        found = _BUNDLE_OF_BASE.get(query_form(key))
    return found


def form_tokens(form: str) -> list[str]:
    """표기 하나의 검색어 토큰. 섞인 표기는 빈 목록이다."""
    if form in TERMS:
        return [form]
    if _HANGUL.fullmatch(form):
        return core.tokenize(form)
    if form.isascii():
        return [query_form(token) for token in core.tokenize(form)]
    return []
