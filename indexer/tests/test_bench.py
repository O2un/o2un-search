from pathlib import Path

from indexer import bench
from indexer.core import Core, load


def test_load_sources_skips_drafts(tmp_path: Path) -> None:
    content = tmp_path / "src" / "content" / "blog"
    content.mkdir(parents=True)
    (content / "a.md").write_text("## 절\n본문\n", encoding="utf-8")
    (content / "b.mdx").write_text("---\ndraft: true\n---\n본문\n", encoding="utf-8")
    assert bench.load_sources(tmp_path) == [("## 절\n본문\n", "a", "md")]


def test_run_times_every_core_each_round() -> None:
    python = load("python")
    calls: list[str] = []

    def tokenize(text: str) -> list[str]:
        calls.append(text)
        return python.tokenize(text)

    counted = Core("counted", python.chunk, tokenize)
    sources = [("도입부\n\n## 첫 절\n본문\n", "post", "md")]
    result = bench.run(sources, [python, counted], repeat=3)

    assert (result.posts, result.chunks, result.repeat) == (1, 2, 3)
    assert [len(timing.seconds) for timing in result.timings] == [3, 3]
    # 버리는 한 바퀴 + 잰 세 바퀴, 바퀴마다 청크 둘
    assert len(calls) == (1 + 3) * 2
