import time

import pytest

import search
from ranking import fuse, group_by_post, snippet
from store import ChunkRow


def test_fuse_adds_reciprocal_ranks() -> None:
    scores = fuse(["a", "b"], ["b", "c"], k=60)
    assert scores["a"] == pytest.approx(1 / 61)
    assert scores["b"] == pytest.approx(1 / 62 + 1 / 61)
    assert scores["c"] == pytest.approx(1 / 62)


def test_group_by_post_keeps_best_chunk_per_post() -> None:
    scores = {"p1#a": 0.5, "p1#b": 0.9, "p2#a": 0.7}
    post_of = {"p1#a": "p1", "p1#b": "p1", "p2#a": "p2"}
    hits = group_by_post(scores, post_of, limit=10)
    assert [(h.post_id, h.chunk_id) for h in hits] == [("p1", "p1#b"), ("p2", "p2#a")]
    assert len(group_by_post(scores, post_of, limit=1)) == 1


def test_snippet_drops_heading_and_cuts() -> None:
    assert snippet("## 제목\n\n본문   첫 줄\n둘째 줄") == "본문 첫 줄 둘째 줄"
    assert snippet("가" * 200, limit=10) == "가" * 10 + "…"


class FakeStore:
    def __init__(self, rows: list[ChunkRow], keyword: list[str], vector: list[str]) -> None:
        self.rows = {row.chunk_id: row for row in rows}
        self._keyword = keyword
        self._vector = vector
        self.vector_calls = 0

    def keyword(self, tokens, section):
        return [c for c in self._keyword if section is None or self.rows[c].href.startswith(f"/{section}/")]

    def vector(self, vector, model_id, section):
        self.vector_calls += 1
        return [c for c in self._vector if section is None or self.rows[c].href.startswith(f"/{section}/")]

    def chunks(self, chunk_ids):
        return {c: self.rows[c] for c in chunk_ids if c in self.rows}


class MemoryCache:
    def __init__(self) -> None:
        self.rows: dict = {}

    def model_id(self, name):
        return 1

    def get(self, key, model_id):
        return self.rows.get((key, model_id))

    def put(self, key, model_id, vector):
        self.rows.setdefault((key, model_id), vector)


class Provider:
    model_id = "fake/model"

    def __init__(self, fail: Exception | None = None, delay: float = 0.0) -> None:
        self.fail = fail
        self.delay = delay
        self.calls = 0

    def embed_query(self, query):
        self.calls += 1
        time.sleep(self.delay)
        if self.fail:
            raise self.fail
        return [1.0, 0.0]


def row(chunk_id: str, post_id: str, href: str) -> ChunkRow:
    return ChunkRow(chunk_id, post_id, f"글 {post_id}", href, chunk_id.split("#")[-1], "절", "## 절\n본문")


ROWS = [
    row("dev/a#x", "dev/a", "/dev/a/"),
    row("dev/a#y", "dev/a", "/dev/a/"),
    row("life/b#z", "life/b", "/life/b/"),
]


def test_hybrid_groups_by_post_and_uses_cache() -> None:
    store = FakeStore(ROWS, keyword=["dev/a#x"], vector=["life/b#z", "dev/a#y"])
    cache, provider = MemoryCache(), Provider()
    first = search.run(store, cache, provider, "검색어", None, 10)
    assert first.mode == "hybrid"
    # dev/a 는 키워드 1위(x)와 벡터 2위(y) 중 높은 쪽, life/b 는 벡터 1위. 동점은 청크 id 순.
    assert [r["post_id"] for r in first.results] == ["dev/a", "life/b"]
    assert first.results[0]["best"]["anchor"] == "x"
    # dev/a 는 키워드 후보에 걸렸고, life/b 는 벡터 후보로만 들어왔다.
    assert [r["keyword"] for r in first.results] == [True, False]
    search.run(store, cache, provider, "  검색어 ", None, 10)
    assert provider.calls == 1


def test_section_filters_posts() -> None:
    store = FakeStore(ROWS, keyword=["dev/a#x", "life/b#z"], vector=["life/b#z"])
    result = search.run(store, MemoryCache(), Provider(), "검색어", "dev", 10)
    assert [r["post_id"] for r in result.results] == ["dev/a"]


def test_provider_failure_degrades_to_keyword() -> None:
    store = FakeStore(ROWS, keyword=["dev/a#x"], vector=["life/b#z"])
    result = search.run(store, MemoryCache(), Provider(fail=RuntimeError("429")), "검색어", None, 10)
    assert result.mode == "keyword"
    assert [r["post_id"] for r in result.results] == ["dev/a"]
    assert store.vector_calls == 0


def test_deadline_degrades_without_waiting() -> None:
    store = FakeStore(ROWS, keyword=["dev/a#x"], vector=["life/b#z"])
    slow = search.DeadlineProvider(Provider(delay=1.0), seconds=0.05)
    started = time.perf_counter()
    result = search.run(store, MemoryCache(), slow, "검색어", None, 10)
    assert result.mode == "keyword"
    assert time.perf_counter() - started < 0.5


def test_no_provider_is_keyword() -> None:
    store = FakeStore(ROWS, keyword=["dev/a#x"], vector=[])
    assert search.run(store, MemoryCache(), None, "검색어", None, 10).mode == "keyword"
