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


def test_snippet_moves_to_first_term() -> None:
    body = "앞 " * 150 + "공포 연출이 좋았다"
    cut = snippet(body, ["공포"])
    assert cut.startswith("…") and "공포 연출이 좋았다" in cut
    # 앞부분에 있으면 그대로 앞에서 시작한다.
    assert snippet("공포 연출 " + "뒤 " * 100, ["공포"]).startswith("공포")
    assert snippet("URP 전환", ["urp"]).startswith("URP")


def test_query_words_strips_endings_and_dedupes() -> None:
    words = search.query_words("유니티 렌더링이 까맣게 나오는 이유 C# 유니티")
    assert [stem for stem, _ in words] == ["유니", "렌더링", "까맣", "나오", "이유", "C#"]
    assert words[1][1] == ["렌더", "더링"]
    assert words[5][1] == ["c#"]
    # 한 음절, 한 글자 영문·숫자는 토큰이 없어 단어가 되지 않는다.
    assert search.query_words("뭐 ? C 6") == []


def test_query_words_keeps_dev_terms_whole() -> None:
    words = search.query_words("C++26 ASP.NET System.NET node.jsx")
    assert words == [
        ("C++", ["c++"]),
        ("26", ["26"]),
        ("ASP.NET", ["asp.net"]),
        ("System", ["system"]),
        ("NET", ["net"]),
        ("node", ["node"]),
        ("jsx", ["jsx"]),
    ]
    # 같은 용어를 대소문자만 달리 쓰면 한 번만 둔다.
    assert search.query_words("c# C#") == [("c#", ["c#"])]


class FakeStore:
    def __init__(self, rows: list[ChunkRow], keyword: list[str], vector: list[str]) -> None:
        self.rows = {row.chunk_id: row for row in rows}
        self._keyword = keyword
        self._vector = vector
        self.vector_calls = 0
        self.post_descriptions: dict[str, str] = {}
        self.description_calls: list[list[str]] = []

    def keyword(self, words, section):
        return [c for c in self._keyword if section is None or self.rows[c].href.startswith(f"/{section}/")]

    def vector(self, vector, model_id, section):
        self.vector_calls += 1
        return [c for c in self._vector if section is None or self.rows[c].href.startswith(f"/{section}/")]

    def chunks(self, chunk_ids):
        return {c: self.rows[c] for c in chunk_ids if c in self.rows}

    def descriptions(self, post_ids):
        self.description_calls.append(list(post_ids))
        return {p: self.post_descriptions[p] for p in post_ids if p in self.post_descriptions}


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
    first = search.run(store, cache, provider, "검색어 예시", None, 10)
    assert first.mode == "hybrid"
    # dev/a 는 키워드 1위(x)와 벡터 2위(y) 중 높은 쪽, life/b 는 벡터 1위. 동점은 청크 id 순.
    assert [r["post_id"] for r in first.results] == ["dev/a", "life/b"]
    assert first.results[0]["best"]["anchor"] == "x"
    # dev/a 는 키워드 후보에 걸렸고, life/b 는 벡터 후보로만 들어왔다.
    assert [r["keyword"] for r in first.results] == [True, False]
    search.run(store, cache, provider, "  검색어  예시 ", None, 10)
    assert provider.calls == 1


def test_meta_chunk_shows_description_only() -> None:
    meta = ChunkRow("life/b#~meta", "life/b", "글 life/b", "/life/b/", "", "글 정보", "글 life/b 취미 공포 life/b")
    store = FakeStore([*ROWS, meta], keyword=["life/b#~meta"], vector=[])
    store.post_descriptions = {"life/b": "글 설명이다."}
    result = search.run(store, MemoryCache(), None, "공포", None, 10)
    assert result.results[0]["best"] == {"anchor": "", "heading_path": "", "snippet": "글 설명이다."}
    assert result.results[0]["keyword"] is True
    assert store.description_calls == [["life/b"]]


def test_no_meta_hit_skips_descriptions() -> None:
    store = FakeStore(ROWS, keyword=["dev/a#x"], vector=[])
    search.run(store, MemoryCache(), None, "검색어", None, 10)
    assert store.description_calls == []


def test_one_word_query_drops_vector_only_posts() -> None:
    store = FakeStore(ROWS, keyword=["dev/a#x"], vector=["life/b#z", "dev/a#y"])
    result = search.run(store, MemoryCache(), Provider(), "공포", None, 10)
    assert result.mode == "hybrid"
    assert [r["post_id"] for r in result.results] == ["dev/a"]
    # 키워드에 걸린 글의 다른 청크는 벡터 순위로 대표 절이 될 수 있다.
    assert result.results[0]["best"]["anchor"] == "x"


def test_one_word_query_keeps_vector_without_keyword_hit() -> None:
    store = FakeStore(ROWS, keyword=[], vector=["life/b#z"])
    result = search.run(store, MemoryCache(), Provider(), "호러", None, 10)
    assert [(r["post_id"], r["keyword"]) for r in result.results] == [("life/b", False)]


def test_two_word_query_keeps_vector_only_posts() -> None:
    store = FakeStore(ROWS, keyword=["dev/a#x"], vector=["life/b#z"])
    result = search.run(store, MemoryCache(), Provider(), "공포 테마", None, 10)
    assert [r["post_id"] for r in result.results] == ["dev/a", "life/b"]


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
