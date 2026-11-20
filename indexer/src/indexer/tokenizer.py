"""검색용 토크나이저. 글 본문과 검색어를 같은 함수로 자른다.

규칙
- 입력을 NFC 로 정규화한다.
- 개발 용어 사전(`_dev_terms.TERMS`)의 용어는 토큰 하나가 된다. 대소문자는 가리지 않고 토큰은
  사전의 소문자 꼴이다.
  - 앞 글자가 ASCII 영문·숫자가 아닌 자리에서만 맞춘다. `System.NET` 의 `.NET` 은 용어가 아니다.
  - 여러 용어가 맞으면 가장 긴 것을 쓴다. `ASP.NET` 은 `asp.net` 하나다.
  - 영문·숫자로 끝나는 용어는 뒤 글자가 ASCII 영문·숫자가 아니어야 한다. 기호로 끝나는 용어는
    뒤를 보지 않는다. `C++26` 은 `c++`, `26` 이다.
- 한글 음절(U+AC00..U+D7A3)이 이어진 구간은 음절 2-gram 으로 자른다. 한 음절짜리 구간은 버린다.
- ASCII 영문·숫자가 이어진 구간은 소문자 단어 하나가 된다. 한 글자 단어는 버린다.
- 그 밖의 문자(기호, 공백, 한글 자모, 다른 문자 체계)는 모두 구분자다.
- 출력은 나온 순서 그대로이고 중복을 지우지 않는다.
"""

from __future__ import annotations

import unicodedata

from ._dev_terms import TERMS

_HANGUL_FIRST = 0xAC00
_HANGUL_LAST = 0xD7A3

# 긴 용어부터 맞춘다.
_TERMS_LONGEST_FIRST = sorted(TERMS, key=lambda term: (-len(term), term))
_FIRST_CHARS = frozenset(term[0] for term in TERMS)


def _is_hangul(char: str) -> bool:
    return _HANGUL_FIRST <= ord(char) <= _HANGUL_LAST


def _is_ascii_alnum(char: str) -> bool:
    return char.isascii() and char.isalnum()


def _term_at(text: str, start: int) -> str | None:
    if text[start].lower() not in _FIRST_CHARS:
        return None
    if start > 0 and _is_ascii_alnum(text[start - 1]):
        return None
    for term in _TERMS_LONGEST_FIRST:
        end = start + len(term)
        piece = text[start:end]
        # ASCII 만 맞춘다. 유니코드 소문자 변환(켈빈 기호 → k 등)은 쓰지 않는다.
        if not piece.isascii() or piece.lower() != term:
            continue
        if _is_ascii_alnum(term[-1]) and end < len(text) and _is_ascii_alnum(text[end]):
            continue
        return term
    return None


def tokenize(text: str) -> list[str]:
    text = unicodedata.normalize("NFC", text)
    tokens: list[str] = []
    run: list[str] = []
    run_kind = ""  # "hangul" | "word" | ""

    def flush() -> None:
        if run_kind == "hangul":
            tokens.extend(run[i] + run[i + 1] for i in range(len(run) - 1))
        elif run_kind == "word" and len(run) > 1:
            tokens.append("".join(run).lower())
        run.clear()

    at = 0
    while at < len(text):
        term = _term_at(text, at)
        if term is not None:
            flush()
            run_kind = ""
            tokens.append(term)
            at += len(term)
            continue
        char = text[at]
        kind = "hangul" if _is_hangul(char) else "word" if _is_ascii_alnum(char) else ""
        if kind != run_kind:
            flush()
            run_kind = kind
        if kind:
            run.append(char)
        at += 1
    flush()
    return tokens
