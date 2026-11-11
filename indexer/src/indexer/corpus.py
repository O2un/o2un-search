"""블로그 레포에서 색인할 글을 고른다.

글 id 는 블로그 콘텐츠 컬렉션의 `post.id` 와 같아야 한다. Astro glob 로더는 프론트매터에
`slug` 가 있으면 그것을 쓰고, 없으면 `src/content/blog` 기준 상대 경로의 각 조각을
github-slugger 로 접은 뒤 끝의 `/index` 를 뗀다. 블로그는 `draft: true` 와 `_` 로 시작하는
id 를 공개 목록에서 뺀다(`src/lib/blog.ts` 의 `getPublishedBlogPosts`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .slug import slugify

CONTENT_DIR = Path("src/content/blog")

_DRAFT_TRUE = re.compile(r"^draft:[ \t]*(?:true|True|TRUE)[ \t]*(?:#.*)?$", re.MULTILINE)
_SLUG = re.compile(r"^slug:[ \t]*(['\"]?)(.+?)\1[ \t]*$", re.MULTILINE)


@dataclass(frozen=True)
class Post:
    post_id: str
    path: Path
    ext: Literal["md", "mdx"]
    draft: bool

    def read(self) -> str:
        return self.path.read_text(encoding="utf-8")


def _frontmatter(source: str) -> str:
    lines = source.lstrip("﻿").replace("\r\n", "\n").split("\n")
    if not lines or lines[0].rstrip() != "---":
        return ""
    for index in range(1, len(lines)):
        if lines[index].rstrip() == "---":
            return "\n".join(lines[1:index])
    return ""


def post_id_for(relative: Path, source: str) -> str:
    slug = _SLUG.search(_frontmatter(source))
    if slug:
        return slug.group(2)
    segments = [*relative.parent.parts, relative.stem]
    post_id = "/".join(slugify(segment) for segment in segments)
    return post_id.removesuffix("/index")


def iter_posts(blog_root: Path) -> list[Post]:
    content = blog_root / CONTENT_DIR
    posts: list[Post] = []
    for path in sorted(content.rglob("*")):
        if path.suffix not in (".md", ".mdx") or not path.is_file():
            continue
        source = path.read_text(encoding="utf-8")
        posts.append(
            Post(
                post_id=post_id_for(path.relative_to(content), source),
                path=path,
                ext="mdx" if path.suffix == ".mdx" else "md",
                draft=bool(_DRAFT_TRUE.search(_frontmatter(source))),
            )
        )
    return sorted(posts, key=lambda post: post.post_id)


def is_published(post: Post) -> bool:
    return not post.draft and not post.post_id.startswith("_")
