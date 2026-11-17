"""청커·토크나이저 구현을 고른다.

환경 변수 `INDEXER_CORE`(`python` | `rust`, 기본 `python`)로 정한다. `rust` 인데 Rust 확장
모듈(`o2un_search_core`)이 없으면 Python 으로 넘어가지 않고 ImportError 를 낸다.

Python 구현(`chunker.py`·`tokenizer.py`)이 기준이다. 규칙을 바꿀 때는 Python 을 먼저 고친다.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from typing import Literal

from . import chunker, tokenizer
from .chunker import Chunk

Ext = Literal["md", "mdx"]
NAMES = ("python", "rust")


@dataclass(frozen=True)
class Core:
    name: str
    chunk: Callable[[str, str, Ext], list[Chunk]]
    tokenize: Callable[[str], list[str]]


def _rust() -> Core:
    import o2un_search_core as rust

    def chunk(post_source: str, post_id: str, ext: Ext) -> list[Chunk]:
        return [Chunk(*item) for item in rust.chunk(post_source, post_id, ext)]

    return Core("rust", chunk, rust.tokenize)


def load(name: str) -> Core:
    if name == "python":
        return Core("python", chunker.chunk, tokenizer.tokenize)
    if name == "rust":
        return _rust()
    raise ValueError(f"INDEXER_CORE 는 python 또는 rust: {name!r}")


# cli 가 .env 를 읽은 뒤에 고르도록 첫 호출 때 정한다.
@cache
def selected() -> Core:
    return load(os.environ.get("INDEXER_CORE") or "python")


def chunk(post_source: str, post_id: str, ext: Ext) -> list[Chunk]:
    return selected().chunk(post_source, post_id, ext)


def tokenize(text: str) -> list[str]:
    return selected().tokenize(text)
