"""색인(sync)과 임베딩(embed). 실제 DB·공급자 대신 메모리 저장소와 가짜 공급자로 확인한다."""

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from indexer import embed, sync
from indexer.embed import Pending
from indexer.embedding import EmbeddingDocument, RateLimited
from indexer.site import SitePost
from indexer.sync import Row, State


class FakeProvider:
    def __init__(self, model_id: str = "fake/model", fail_after: int | None = None) -> None:
        self.model_id = model_id
        self.inputs: list[EmbeddingDocument] = []
        self.requests = 0
        self.fail_after = fail_after

    def embed_documents(self, documents: list[EmbeddingDocument]) -> list[list[float]]:
        if self.fail_after is not None and self.requests >= self.fail_after:
            raise RateLimited("limit")
        self.requests += 1
        self.inputs.extend(documents)
        return [[1.0, 0.0, 0.0] for _ in documents]

    def embed_query(self, query: str) -> list[float]:
        return [1.0, 0.0, 0.0]


@dataclass
class StoredChunk:
    row: Row
    model_id: int | None = None


class MemoryStore:
    """search 스키마의 외래 키(청크 → 글, ON DELETE CASCADE)까지 흉내 낸다."""

    def __init__(self) -> None:
        self.posts: dict[str, SitePost] = {}
        self.chunks: dict[str, StoredChunk] = {}
        self.models: dict[str, int] = {}

    def load(self) -> State:
        return State(
            posts=dict(self.posts),
            chunks={
                chunk_id: (c.row.content_hash, c.row.context_chunk_id, c.row.embed_hash)
                for chunk_id, c in self.chunks.items()
            },
            lexemes={chunk_id: frozenset(c.row.tokens) for chunk_id, c in self.chunks.items()},
        )

    def delete_posts(self, post_ids: list[str]) -> None:
        for post_id in post_ids:
            del self.posts[post_id]
        self.chunks = {k: c for k, c in self.chunks.items() if c.row.post_id not in post_ids}

    def delete_chunks(self, chunk_ids: list[str]) -> None:
        for chunk_id in chunk_ids:
            del self.chunks[chunk_id]

    def upsert_posts(self, posts: dict[str, SitePost]) -> None:
        self.posts.update(posts)

    def clear_embeddings(self, post_ids: list[str]) -> None:
        for c in self.chunks.values():
            if c.row.post_id in post_ids:
                c.model_id = None

    def upsert_chunks(self, rows: list[Row]) -> None:
        for row in rows:
            assert row.post_id in self.posts, "외래 키 위반: 글보다 청크가 먼저 들어왔다"
            self.chunks[row.chunk_id] = StoredChunk(row)

    def update_tokens(self, rows: list[Row]) -> None:
        for row in rows:
            self.chunks[row.chunk_id].row = row

    def model_id(self, name: str) -> int:
        return self.models.setdefault(name, len(self.models) + 1)

    def pending(self, model_id: int) -> list[Pending]:
        return [
            Pending(
                chunk_id,
                self.posts[c.row.post_id].title,
                c.row.heading_path,
                c.row.body,
                self.chunks[c.row.context_chunk_id].row.body if c.row.context_chunk_id else None,
                c.row.embed_hash != "",
            )
            for chunk_id, c in sorted(self.chunks.items())
            if c.model_id != model_id
        ]

    def set_embeddings(self, chunk_ids: list[str], vectors: list[list[float]], model_id: int) -> None:
        for chunk_id in chunk_ids:
            self.chunks[chunk_id].model_id = model_id

    def empty(self) -> int:
        return sum(1 for c in self.chunks.values() if c.model_id is None)


class Blog:
    """블로그 레포 소스와 빌드 결과(search-index.json)를 흉내 낸다."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.dist = root / "dist" / "client"
        self.posts: dict[str, dict] = {}

    def write(
        self,
        post_id: str,
        title: str,
        body: str,
        draft: bool = False,
        section: str = "devlog",
        search_text: str = "",
        description: str = "",
    ) -> None:
        path = self.root / "src" / "content" / "blog" / post_id / "index.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"---\ntitle: '{title}'\ndraft: {'true' if draft else 'false'}\n---\n\n{body}\n",
            encoding="utf-8",
        )
        if draft:
            self.posts.pop(post_id, None)
        else:
            self.posts[post_id] = {
                "id": post_id,
                "href": f"/{section}/{post_id}/",
                "title": title,
                "description": description,
                "searchText": search_text,
                "section": section,
            }
        self.build()

    def build(self) -> None:
        if self.dist.exists():
            for path in self.dist.glob("*/search-index.json"):
                path.unlink()
        sections: dict[str, list] = {}
        for item in self.posts.values():
            sections.setdefault(item["section"], []).append(item)
        for section, items in sections.items():
            (self.dist / section).mkdir(parents=True, exist_ok=True)
            (self.dist / section / "search-index.json").write_text(json.dumps(items), encoding="utf-8")


# 짧은 절 규칙(embed.SHORT_CHUNK_CHARS)에 걸리지 않게 절마다 이 문장을 붙인다.
PAD = " 짧은 절로 잡히지 않도록 같은 문장을 길게 이어 적었다." * 4
INTRO_A = f"도입부.{PAD}"
BODY_A = f"{INTRO_A}\n\n## 첫 절\n\n첫 절 본문.{PAD}\n\n## 둘째 절\n\n둘째 절 본문.{PAD}"
BODY_B = f"## 하나\n\n하나 본문.{PAD}\n\n## 둘\n\n둘 본문.{PAD}\n\n## 셋\n\n셋 본문.{PAD}"


@pytest.fixture
def blog(tmp_path: Path) -> Blog:
    blog = Blog(tmp_path)
    blog.write("개발기/a", "글 A", BODY_A)
    blog.write("선택/b", "글 B", BODY_B)
    return blog


@pytest.fixture
def store(blog: Blog) -> MemoryStore:
    """첫 색인과 임베딩까지 마친 상태."""
    store = MemoryStore()
    sync.run(blog.root, blog.dist, store)
    embed.run(store, FakeProvider())
    return store


def _sync(blog: Blog, store: MemoryStore) -> sync.Summary:
    return sync.run(blog.root, blog.dist, store)


# sync


def test_first_sync_leaves_embeddings_empty(blog: Blog) -> None:
    store = MemoryStore()
    summary = _sync(blog, store)
    assert (summary.posts, summary.chunks, summary.chunks_updated) == (2, 6, 6)
    assert store.empty() == 6


def test_second_sync_changes_nothing(blog: Blog, store: MemoryStore) -> None:
    summary = _sync(blog, store)
    assert (summary.posts_updated, summary.chunks_updated, summary.unchanged) == (0, 0, 6)
    assert store.empty() == 0


def test_editing_one_section_empties_only_that_chunk(blog: Blog, store: MemoryStore) -> None:
    blog.write("개발기/a", "글 A", BODY_A.replace("첫 절 본문.", "첫 절 본문을 고쳤다."))
    assert _sync(blog, store).chunks_updated == 1
    assert store.chunks["개발기/a#첫-절"].model_id is None
    assert store.empty() == 1


def test_removed_section_is_deleted(blog: Blog, store: MemoryStore) -> None:
    blog.write("선택/b", "글 B", BODY_B.replace("\n\n## 셋\n\n셋 본문.", ""))
    assert _sync(blog, store).chunks_deleted == 1
    assert "선택/b#셋" not in store.chunks


def test_post_turned_draft_is_deleted(blog: Blog, store: MemoryStore) -> None:
    blog.write("선택/b", "글 B", BODY_B, draft=True)
    assert _sync(blog, store).posts_deleted == 1
    assert "선택/b" not in store.posts
    assert not any(c.row.post_id == "선택/b" for c in store.chunks.values())


def test_title_change_empties_post_embeddings(blog: Blog, store: MemoryStore) -> None:
    blog.write("선택/b", "글 B 새 제목", BODY_B)
    assert _sync(blog, store).posts_updated == 1
    assert store.empty() == 3


def test_moved_section_updates_post_only(blog: Blog, store: MemoryStore) -> None:
    blog.write("선택/b", "글 B", BODY_B, section="notes")
    summary = _sync(blog, store)
    assert (summary.posts_updated, summary.chunks_updated) == (1, 0)
    assert store.posts["선택/b"].href == "/notes/선택/b/"
    assert store.empty() == 0


def test_tokenizer_change_updates_tokens_only(
    blog: Blog, store: MemoryStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = sync.tokenize
    monkeypatch.setattr(sync, "tokenize", lambda text: [*original(text), "새토큰"])
    summary = _sync(blog, store)
    assert (summary.chunks_updated, summary.tokens_updated, summary.unchanged) == (0, 6, 0)
    assert all("새토큰" in c.row.tokens for c in store.chunks.values())
    assert store.empty() == 0
    assert _sync(blog, store).unchanged == 6


def test_stale_build_is_rejected(blog: Blog) -> None:
    blog.posts.pop("선택/b")
    blog.build()
    with pytest.raises(SystemExit):
        _sync(blog, MemoryStore())


def test_sync_dry_run_changes_nothing(blog: Blog) -> None:
    store = MemoryStore()
    summary = sync.run(blog.root, blog.dist, store, dry_run=True)
    assert (summary.chunks_updated, store.chunks, store.posts) == (6, {}, {})


# embed


def test_embed_fills_only_empty_chunks(blog: Blog, store: MemoryStore) -> None:
    blog.write("개발기/a", "글 A", BODY_A.replace("첫 절 본문.", "첫 절 본문을 고쳤다."))
    _sync(blog, store)
    provider = FakeProvider()
    summary = embed.run(store, provider)
    assert (summary.embedded, provider.requests) == (1, 1)
    assert [doc.title for doc in provider.inputs] == ["글 A > 첫 절"]


def test_embed_with_nothing_to_do_calls_nothing(store: MemoryStore) -> None:
    provider = FakeProvider()
    assert (embed.run(store, provider).embedded, provider.requests) == (0, 0)


def test_intro_chunk_uses_post_title(blog: Blog) -> None:
    store = MemoryStore()
    _sync(blog, store)
    provider = FakeProvider()
    embed.run(store, provider)
    assert EmbeddingDocument(title="글 A", text=INTRO_A) in provider.inputs


def test_title_change_embeds_with_new_title(blog: Blog, store: MemoryStore) -> None:
    blog.write("선택/b", "글 B 새 제목", BODY_B)
    _sync(blog, store)
    provider = FakeProvider()
    assert embed.run(store, provider).embedded == 3
    assert {doc.title.split(" > ")[0] for doc in provider.inputs} == {"글 B 새 제목"}


def test_rate_limit_keeps_progress_and_next_run_resumes(blog: Blog, monkeypatch) -> None:
    monkeypatch.setattr(embed, "BATCH_SIZE", 2)
    store = MemoryStore()
    _sync(blog, store)
    stopped = embed.run(store, FakeProvider(fail_after=1))
    assert (stopped.rate_limited, stopped.embedded, store.empty()) == (True, 2, 4)

    resumed = embed.run(store, FakeProvider())
    assert (resumed.rate_limited, resumed.embedded, store.empty()) == (False, 4, 0)


def test_model_change_reembeds_everything(store: MemoryStore) -> None:
    assert embed.run(store, FakeProvider("fake/other")).embedded == 6
    assert set(store.models) == {"fake/model", "fake/other"}


def test_embed_dry_run_changes_nothing(blog: Blog) -> None:
    store = MemoryStore()
    _sync(blog, store)
    provider = FakeProvider()
    assert (embed.run(store, provider, dry_run=True).pending, provider.requests, store.empty()) == (6, 0, 6)


def test_heading_only_chunk_is_skipped(blog: Blog) -> None:
    blog.write("선택/c", "글 C", f"## 본문 절\n\n내용.{PAD}\n\n## 참고 자료\n\n[^1]: 출처")
    store = MemoryStore()
    _sync(blog, store)
    provider = FakeProvider()
    summary = embed.run(store, provider)
    assert (summary.skipped, summary.embedded) == (1, 7)
    assert store.chunks["선택/c#참고-자료"].model_id is None
    assert "선택/c#참고-자료" in store.chunks


def test_limit_embeds_at_most_n(blog: Blog) -> None:
    store = MemoryStore()
    _sync(blog, store)
    assert embed.run(store, FakeProvider(), limit=2).embedded == 2
    assert store.empty() == 4


# 짧은 절 (3f)

SHORT_BODY = f"도입부.\n\n## 긴 절\n\n긴 절 본문.{PAD}\n\n## 짧은 절\n\n두 문장. 짧다.\n\n## 끝 절\n\n끝 절 본문.{PAD}"


def test_content_length_ignores_heading_and_folds_spaces() -> None:
    assert embed.content_length("## 제목\n\n가  나\n다") == len("가 나 다")
    assert embed.content_length("도입부.") == len("도입부.")
    assert embed.content_length("## 참고 자료\n") == 0


def test_short_chunk_embeds_with_previous_section(blog: Blog) -> None:
    blog.write("선택/c", "글 C", SHORT_BODY)
    store = MemoryStore()
    _sync(blog, store)
    assert store.chunks["선택/c#짧은-절"].row.context_chunk_id == "선택/c#긴-절"
    assert store.chunks["선택/c#긴-절"].row.context_chunk_id is None
    provider = FakeProvider()
    embed.run(store, provider)
    docs = {doc.title: doc.text for doc in provider.inputs}
    # 자기 본문 뒤에 이웃 본문을 붙인다
    assert docs["글 C > 짧은 절"] == f"## 짧은 절\n\n두 문장. 짧다.\n\n## 긴 절\n\n긴 절 본문.{PAD}"
    # 앞 절이 없는 도입부는 다음 절을 붙인다
    assert docs["글 C"] == f"도입부.\n\n## 긴 절\n\n긴 절 본문.{PAD}"
    # 긴 절과 청크 본문은 그대로다
    assert docs["글 C > 끝 절"] == f"## 끝 절\n\n끝 절 본문.{PAD}"
    assert store.chunks["선택/c#짧은-절"].row.body == "## 짧은 절\n\n두 문장. 짧다."


def test_short_chunk_skips_heading_only_neighbour() -> None:
    bodies = ["## 본문\n\n" + "가" * 120, "## 참고\n", "## 짧은 절\n\n짧다."]
    assert embed.contexts(bodies) == [None, None, 0]


def test_embed_hash_is_empty_without_content() -> None:
    assert embed.embed_hash("## 참고 자료\n", None) == ""
    assert embed.embed_hash("본문", None) != embed.embed_hash("본문", "이웃")


def test_editing_neighbour_reembeds_short_chunk(blog: Blog) -> None:
    blog.write("선택/c", "글 C", SHORT_BODY)
    store = MemoryStore()
    _sync(blog, store)
    embed.run(store, FakeProvider())

    blog.write("선택/c", "글 C", SHORT_BODY.replace("긴 절 본문.", "긴 절 본문을 고쳤다."))
    assert _sync(blog, store).chunks_updated == 3  # 긴 절, 그 뒤의 짧은 절, 그 앞의 도입부
    assert store.chunks["선택/c#짧은-절"].model_id is None
    assert store.chunks["선택/c#끝-절"].model_id is not None


# 글 정보 청크 (3f)


def test_meta_chunk_is_keyword_only(blog: Blog) -> None:
    blog.write(
        "선택/c",
        "[방탈출] 글 C",
        BODY_B,
        search_text="[방탈출] 글 c 취미 방탈출 공포 선택/c",
        description="글  C 의\n설명.",
    )
    store = MemoryStore()
    _sync(blog, store)
    meta = store.chunks["선택/c#~meta"].row
    assert (meta.anchor, meta.heading_path, meta.embed_hash) == ("", "글 정보", "")
    assert meta.body == "[방탈출] 글 c 취미 방탈출 공포 선택/c"
    assert "공포" in meta.tokens
    # 글 설명은 글(search.posts)에 둔다. 공백은 하나로 접는다
    assert store.posts["선택/c"].description == "글 C 의 설명."

    provider = FakeProvider()
    summary = embed.run(store, provider)
    assert summary.skipped == 1
    assert all(not doc.title.endswith("글 정보") for doc in provider.inputs)
    assert store.chunks["선택/c#~meta"].model_id is None


def test_search_text_change_updates_only_meta_chunk(blog: Blog) -> None:
    blog.write("선택/c", "글 C", BODY_B, search_text="글 c 공포")
    store = MemoryStore()
    _sync(blog, store)
    embed.run(store, FakeProvider())

    blog.write("선택/c", "글 C", BODY_B, search_text="글 c 공포 미스터리")
    assert _sync(blog, store).chunks_updated == 1
    assert store.empty() == 1


def test_description_change_updates_post_only(blog: Blog, store: MemoryStore) -> None:
    blog.write("선택/b", "글 B", BODY_B, description="새 설명")
    summary = _sync(blog, store)
    assert (summary.posts_updated, summary.chunks_updated) == (1, 0)
    assert store.posts["선택/b"].description == "새 설명"
    assert store.empty() == 0


def test_post_without_search_text_has_no_meta_chunk(blog: Blog, store: MemoryStore) -> None:
    assert not any(chunk_id.endswith("#~meta") for chunk_id in store.chunks)
