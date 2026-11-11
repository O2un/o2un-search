"""검색용 토크나이저. 글 본문과 검색어를 같은 함수로 자른다.

규칙
- 입력을 NFC 로 정규화한다.
- 한글 음절(U+AC00..U+D7A3)이 이어진 구간은 음절 2-gram 으로 자른다. 한 음절짜리 구간은 버린다.
- ASCII 영문·숫자가 이어진 구간은 소문자 단어 하나가 된다.
- 그 밖의 문자(기호, 공백, 한글 자모, 다른 문자 체계)는 모두 구분자다.
- 출력은 나온 순서 그대로이고 중복을 지우지 않는다.
"""

from __future__ import annotations

import unicodedata

_HANGUL_FIRST = 0xAC00
_HANGUL_LAST = 0xD7A3


def _is_hangul(char: str) -> bool:
    return _HANGUL_FIRST <= ord(char) <= _HANGUL_LAST


def _is_ascii_alnum(char: str) -> bool:
    return char.isascii() and char.isalnum()


def tokenize(text: str) -> list[str]:
    text = unicodedata.normalize("NFC", text)
    tokens: list[str] = []
    run: list[str] = []
    run_kind = ""  # "hangul" | "word" | ""

    def flush() -> None:
        if run_kind == "hangul":
            tokens.extend(run[i] + run[i + 1] for i in range(len(run) - 1))
        elif run_kind == "word":
            tokens.append("".join(run).lower())
        run.clear()

    for char in text:
        kind = "hangul" if _is_hangul(char) else "word" if _is_ascii_alnum(char) else ""
        if kind != run_kind:
            flush()
            run_kind = kind
        if kind:
            run.append(char)
    flush()
    return tokens
