import json
from dataclasses import asdict
from pathlib import Path

import pytest

from indexer import chunk, tokenize
from indexer.chunker import MAX_CHUNK_CHARS

SAMPLES = Path(__file__).parent / "samples"
CASES = sorted(SAMPLES.glob("*.md*"))


@pytest.mark.parametrize("path", CASES, ids=lambda path: path.name)
def test_sample_matches_fixture(path: Path) -> None:
    expected = json.loads((SAMPLES / "expected" / f"{path.name}.json").read_text(encoding="utf-8"))
    chunks = chunk(path.read_text(encoding="utf-8"), expected["post_id"], expected["ext"])
    actual = [{**asdict(item), "tokens": tokenize(item.body)} for item in chunks]
    assert actual == expected["chunks"]


def test_long_section_splits_under_limit() -> None:
    source = (SAMPLES / "long_section.md").read_text(encoding="utf-8")
    chunks = chunk(source, "samples/long_section", "md")
    parts = [item for item in chunks if item.anchor == "긴-절"]
    assert len(parts) > 1
    assert [item.chunk_id for item in parts] == [
        f"samples/long_section#긴-절#{n}" for n in range(1, len(parts) + 1)
    ]
    assert all(len(item.body) <= MAX_CHUNK_CHARS for item in chunks)


def test_crlf_and_lf_give_same_chunks() -> None:
    source = (SAMPLES / "nesting.md").read_text(encoding="utf-8")
    assert chunk(source.replace("\n", "\r\n"), "x", "md") == chunk(source, "x", "md")


# 블로그 마크다운 파이프라인(@astrojs/markdown-remark + 블로그 remark·rehype 플러그인)으로 샘플을
# 렌더링해 `<section data-heading-level>` 아래 제목 id 를 뽑은 값이다. fixture 를 다시 쓰더라도
# 앵커는 이 독립된 값과 맞아야 한다. `.mdx` 샘플은 import 대상이 없어 렌더링하지 못해 빠져 있다.
ASTRO_ANCHORS = json.loads((SAMPLES / "astro_anchors.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", sorted(ASTRO_ANCHORS))
def test_anchors_match_astro_render(name: str) -> None:
    source = (SAMPLES / name).read_text(encoding="utf-8")
    anchors: list[str] = []
    for item in chunk(source, "x", "md"):
        if item.anchor and (not anchors or anchors[-1] != item.anchor):
            anchors.append(item.anchor)
    assert anchors == ASTRO_ANCHORS[name]
