"""공개 글 전체를 청크로 잘라 색인과 맞춘다. 임베딩은 하지 않는다(`embed.py`).

실행할 때마다 전체를 다시 자르고 DB 와 비교한다. 실행이 멱등이라 중간에 실패하거나 신호를
놓쳐도 다음 실행이 상태를 맞춘다.

- 글(search.posts): 새 글은 넣고, 제목·주소·설명이 바뀐 글은 고치고, 빠진 글은 지운다.
  글을 지우면 그 글의 청크도 함께 지워진다.
- 청크: 새 청크는 넣고, 본문 해시나 임베딩 입력 해시(`embed_hash`)가 바뀐 청크는 고치고, 남은
  글 안에서 사라진 절은 지운다. 짧은 절의 임베딩 입력은 이웃 절 본문을 담으므로(`embed.py`),
  이웃 절만 바뀌어도 짧은 절이 고칠 대상이 된다.
- 글마다 "글 정보" 청크(`{post_id}#~meta`)를 하나 더 둔다. 본문은 블로그가 만든 `searchText` 다.
  키워드로만 찾고 임베딩하지 않는다(`embed_hash` 가 빈다). 프론트매터 단어를 모은 줄은 뜻이 흐려
  여러 검색어에 두루 가깝게 잡히기 때문이다. 청커가 만드는 청크가 아니므로 Rust 구현과
  `compare-core` 대조에는 들지 않는다. 앵커가 비어 글 맨 위로 간다.
- 임베딩을 비우는 경우: 고친 청크, 글 제목이 바뀐 글의 청크. 글 제목은 임베딩
  입력의 `title:` 에 들어가기 때문이다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from .chunker import Chunk, content_hash
from .core import chunk, tokenize
from .corpus import is_published, iter_posts
from .embed import contexts, embed_hash
from .site import SitePost, load_site_index

# 청커의 청크 id 는 `{post_id}#{anchor}` 꼴이고 앵커는 `~` 를 만들지 않는다.
META_CHUNK_SUFFIX = "#~meta"
META_HEADING = "글 정보"


@dataclass(frozen=True)
class Row:
    chunk_id: str
    post_id: str
    anchor: str
    heading_path: str
    body: str
    tokens: tuple[str, ...]
    content_hash: str
    context_chunk_id: str | None
    embed_hash: str


@dataclass
class State:
    posts: dict[str, SitePost] = field(default_factory=dict)
    # chunk_id → (content_hash, context_chunk_id, embed_hash)
    chunks: dict[str, tuple[str, str | None, str]] = field(default_factory=dict)


class Store(Protocol):
    def load(self) -> State: ...

    def delete_posts(self, post_ids: list[str]) -> None: ...

    def delete_chunks(self, chunk_ids: list[str]) -> None: ...

    def upsert_posts(self, posts: dict[str, SitePost]) -> None: ...

    def upsert_chunks(self, rows: list[Row]) -> None:
        """넣거나 고친다. 고친 청크의 임베딩은 비운다."""
        ...

    def clear_embeddings(self, post_ids: list[str]) -> None: ...


@dataclass
class Plan:
    upsert_posts: dict[str, SitePost] = field(default_factory=dict)
    delete_posts: list[str] = field(default_factory=list)
    retitled: list[str] = field(default_factory=list)
    upsert_chunks: list[Row] = field(default_factory=list)
    delete_chunks: list[str] = field(default_factory=list)
    unchanged: int = 0


@dataclass
class Summary:
    posts: int = 0
    chunks: int = 0
    posts_updated: int = 0
    posts_deleted: int = 0
    chunks_updated: int = 0
    chunks_deleted: int = 0
    unchanged: int = 0

    def lines(self) -> list[str]:
        return [
            f"글 {self.posts}편, 청크 {self.chunks}개",
            f"글 추가·갱신 {self.posts_updated}편, 글 삭제 {self.posts_deleted}편",
            f"청크 추가·갱신 {self.chunks_updated}개, 청크 삭제 {self.chunks_deleted}개, "
            f"변경 없음 {self.unchanged}개",
        ]


def _post_rows(post_id: str, chunks: list[Chunk], search_text: str) -> list[Row]:
    neighbours = contexts([item.body for item in chunks])
    rows = []
    for item, neighbour in zip(chunks, neighbours, strict=True):
        context = None if neighbour is None else chunks[neighbour]
        rows.append(
            Row(
                chunk_id=item.chunk_id,
                post_id=post_id,
                anchor=item.anchor,
                heading_path=item.heading_path,
                body=item.body,
                tokens=tuple(tokenize(item.body)),
                content_hash=item.content_hash,
                context_chunk_id=None if context is None else context.chunk_id,
                embed_hash=embed_hash(item.body, None if context is None else context.body),
            )
        )
    if search_text.strip():
        rows.append(
            Row(
                chunk_id=f"{post_id}{META_CHUNK_SUFFIX}",
                post_id=post_id,
                anchor="",
                heading_path=META_HEADING,
                body=search_text,
                tokens=tuple(tokenize(search_text)),
                content_hash=content_hash(META_HEADING, search_text),
                context_chunk_id=None,
                embed_hash="",  # 키워드로만 찾는다
            )
        )
    return rows


def desired(blog: Path, dist: Path) -> tuple[dict[str, SitePost], list[Row]]:
    site = load_site_index(dist)
    published = [post for post in iter_posts(blog) if is_published(post)]

    source_ids = {post.post_id for post in published}
    if source_ids != set(site.posts):
        missing = sorted(source_ids - set(site.posts))
        extra = sorted(set(site.posts) - source_ids)
        raise SystemExit(
            "블로그 소스와 빌드 결과의 공개 글 목록이 다릅니다. 블로그에서 npm run build 를 다시 돌리세요.\n"
            f"  빌드에 없음: {missing}\n  소스에 없음: {extra}"
        )

    rows = [
        row
        for post in published
        for row in _post_rows(
            post.post_id, chunk(post.read(), post.post_id, post.ext), site.search_texts[post.post_id]
        )
    ]
    return {post_id: site.posts[post_id] for post_id in sorted(source_ids)}, rows


def make_plan(posts: dict[str, SitePost], rows: list[Row], state: State) -> Plan:
    plan = Plan()
    plan.upsert_posts = {
        post_id: post for post_id, post in posts.items() if state.posts.get(post_id) != post
    }
    plan.delete_posts = sorted(post_id for post_id in state.posts if post_id not in posts)
    plan.retitled = sorted(
        post_id
        for post_id, post in posts.items()
        if post_id in state.posts and state.posts[post_id].title != post.title
    )
    for row in rows:
        if state.chunks.get(row.chunk_id) == (row.content_hash, row.context_chunk_id, row.embed_hash):
            plan.unchanged += 1
        else:
            plan.upsert_chunks.append(row)
    wanted = {row.chunk_id for row in rows}
    plan.delete_chunks = sorted(
        chunk_id
        for chunk_id in state.chunks
        if chunk_id not in wanted and chunk_id.split("#", 1)[0] in posts
    )
    return plan


def run(blog: Path, dist: Path, store: Store, dry_run: bool = False) -> Summary:
    posts, rows = desired(blog, dist)
    plan = make_plan(posts, rows, store.load())
    summary = Summary(
        posts=len(posts),
        chunks=len(rows),
        posts_updated=len(plan.upsert_posts),
        posts_deleted=len(plan.delete_posts),
        chunks_updated=len(plan.upsert_chunks),
        chunks_deleted=len(plan.delete_chunks),
        unchanged=plan.unchanged,
    )
    if dry_run:
        return summary

    # 청크가 글을 외래 키로 가리키므로, 글을 먼저 맞춘 뒤 청크를 넣는다.
    if plan.delete_posts:
        store.delete_posts(plan.delete_posts)
    if plan.delete_chunks:
        store.delete_chunks(plan.delete_chunks)
    if plan.upsert_posts:
        store.upsert_posts(plan.upsert_posts)
    if plan.retitled:
        store.clear_embeddings(plan.retitled)
    if plan.upsert_chunks:
        store.upsert_chunks(plan.upsert_chunks)
    return summary
