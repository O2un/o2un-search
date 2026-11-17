from dataclasses import replace
from pathlib import Path

import pytest

from indexer.compare import compare_post
from indexer.core import Core, load
from indexer.corpus import Post

SOURCE = "도입부\n\n## 첫 절\n검색 엔진\n\n## 둘째 절\nRust 코어\n"


def test_unknown_core_is_rejected() -> None:
    with pytest.raises(ValueError):
        load("go")


@pytest.fixture
def post(tmp_path: Path) -> Post:
    path = tmp_path / "post.md"
    path.write_text(SOURCE, encoding="utf-8")
    return Post(post_id="post", path=path, ext="md", draft=False)


def test_same_core_has_no_difference(post: Post) -> None:
    python = load("python")
    assert compare_post(post, python, python) == (3, None)


def test_reports_first_differing_field(post: Post) -> None:
    python = load("python")

    def chunk(source: str, post_id: str, ext: str):
        items = python.chunk(source, post_id, ext)
        items[1] = replace(items[1], body="다른 본문")
        items[2] = replace(items[2], anchor="다른-앵커")
        return items

    _, difference = compare_post(post, python, Core("other", chunk, python.tokenize))
    assert difference is not None
    assert difference.startswith("청크 1 (post#첫-절) body")


def test_reports_token_difference(post: Post) -> None:
    python = load("python")
    other = Core("other", python.chunk, lambda text: python.tokenize(text)[:-1])
    _, difference = compare_post(post, python, other)
    assert difference is not None
    assert "tokens" in difference


def test_reports_missing_chunks(post: Post) -> None:
    python = load("python")
    other = Core("other", lambda *args: python.chunk(*args)[:2], python.tokenize)
    _, difference = compare_post(post, python, other)
    assert difference == "청크 수 python 3개, other 2개"
