"""영어 낱말의 기본 꼴. 토크나이저가 자른 토큰에 덧붙이는 단계다(portfolio-search 3g 단계 2).

토크나이저(Python·Rust)는 자르기만 하고 이 단계는 Python 한 곳에만 있다. 그래서 Rust 구현과
맞출 필요가 없고 `compare-core` 대상도 아니다.

- 어간: 영문만인 토큰은 Snowball(Porter2) 영어 어간이 다르면 덧붙인다.
  `shaders` → `shaders`, `shader`. `rendering` → `rendering`, `render`.
- 버전: 영문 두 글자 이상 뒤에 숫자가 붙은 토큰은 영문 부분과 그 어간을 덧붙인다.
  `unity6` → `unity6`, `unity`, `uniti`. `x86`, `r3` 처럼 영문이 한 글자면 붙이지 않는다.
- 개발 용어 사전의 용어(`c#`, `node.js`)와 한글·숫자 토큰에는 붙이지 않는다.

색인은 `index_forms` 로 원래 토큰 바로 뒤에 덧붙인다. 검색어는 `query_form` 으로 영문만인 단어를
어간 하나로 바꾼다. 단어 하나의 토큰은 모두 맞아야 하므로 검색어 쪽에는 두 꼴을 함께 넣지 않는다.
"""

from __future__ import annotations

import re
from functools import cache

import snowballstemmer

from ._dev_terms import TERMS

_STEMMER = snowballstemmer.stemmer("english")
_LETTERS = re.compile(r"[a-z]{2,}")
_VERSIONED = re.compile(r"([a-z]{2,})[0-9]+")
_TERMS = frozenset(TERMS)


@cache
def _stem(word: str) -> str:
    stem = _STEMMER.stemWord(word)
    return stem if len(stem) > 1 else word


def _extra_forms(token: str) -> list[str]:
    if token in _TERMS:
        return []
    versioned = _VERSIONED.fullmatch(token)
    if versioned:
        base = versioned.group(1)
        stem = _stem(base)
        return [base] if stem == base else [base, stem]
    if _LETTERS.fullmatch(token):
        stem = _stem(token)
        return [] if stem == token else [stem]
    return []


def index_forms(tokens: list[str]) -> list[str]:
    forms: list[str] = []
    for token in tokens:
        forms.append(token)
        forms.extend(_extra_forms(token))
    return forms


def query_form(token: str) -> str:
    if token not in _TERMS and _LETTERS.fullmatch(token):
        return _stem(token)
    return token
