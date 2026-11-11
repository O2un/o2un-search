from indexer.query_cache import embed_query, query_hash


class FakeProvider:
    def __init__(self, model_id: str = "fake/model") -> None:
        self.model_id = model_id
        self.queries: list[str] = []

    def embed_documents(self, documents):  # pragma: no cover - 쓰지 않는다
        raise AssertionError

    def embed_query(self, query: str) -> list[float]:
        self.queries.append(query)
        return [float(len(self.queries)), 0.0, 0.0]


class MemoryCache:
    def __init__(self, models: dict[str, int]) -> None:
        self.models = models
        self.rows: dict[tuple[str, int], list[float]] = {}

    def model_id(self, name: str) -> int | None:
        return self.models.get(name)

    def get(self, key: str, model_id: int) -> list[float] | None:
        return self.rows.get((key, model_id))

    def put(self, key: str, model_id: int, vector: list[float]) -> None:
        self.rows.setdefault((key, model_id), vector)


def test_same_query_calls_provider_once() -> None:
    cache = MemoryCache({"fake/model": 1})
    provider = FakeProvider()
    first, hit1 = embed_query(cache, provider, "LINQ 지연 실행")
    second, hit2 = embed_query(cache, provider, "  LINQ   지연 실행 ")
    assert (hit1, hit2) == (False, True)
    assert first == second
    assert provider.queries == ["LINQ 지연 실행"]


def test_cache_does_not_store_query_text() -> None:
    cache = MemoryCache({"fake/model": 1})
    embed_query(cache, FakeProvider(), "비밀번호 재설정")
    (key, _), = cache.rows
    assert key == query_hash("비밀번호 재설정")
    assert "비밀번호" not in key


def test_other_model_does_not_reuse_vector() -> None:
    cache = MemoryCache({"fake/model": 1, "fake/other": 2})
    embed_query(cache, FakeProvider(), "검색어")
    other = FakeProvider("fake/other")
    _, hit = embed_query(cache, other, "검색어")
    assert hit is False
    assert other.queries == ["검색어"]


def test_unregistered_model_skips_cache() -> None:
    cache = MemoryCache({})
    provider = FakeProvider()
    embed_query(cache, provider, "검색어")
    embed_query(cache, provider, "검색어")
    assert len(provider.queries) == 2
    assert cache.rows == {}
