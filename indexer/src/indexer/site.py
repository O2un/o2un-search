"""블로그 빌드 결과에서 글 주소, 제목, 글 머리 정보를 읽는다.

블로그는 섹션마다 `/{섹션}/search-index.json` 을 내보내고, 공개 글마다 `id`·`href`·`title`·
`description`·`searchText` 가 들어 있다. 주소 규칙(폴더 → 섹션)을 이 레포에 복제하지 않으려고
이 값을 그대로 쓴다. `searchText` 는 블로그가 프론트매터에서 검색할 만한 필드(제목, 설명, 태그,
`keywords`, 장르 등)를 모은 한 줄이다. 어떤 필드를 넣을지는 블로그(`src/lib/blog.ts`)가 정한다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class SitePost:
    href: str
    title: str
    description: str = ""


@dataclass
class SiteIndex:
    posts: dict[str, SitePost] = field(default_factory=dict)
    search_texts: dict[str, str] = field(default_factory=dict)


def load_site_index(dist: Path) -> SiteIndex:
    index = SiteIndex()
    files = sorted(dist.glob("*/search-index.json"))
    if not files:
        raise SystemExit(f"{dist} 에 search-index.json 이 없습니다. 블로그에서 npm run build 를 먼저 돌리세요.")
    for path in files:
        for item in json.loads(path.read_text(encoding="utf-8")):
            index.posts[item["id"]] = SitePost(
                href=item["href"],
                title=item["title"],
                description=" ".join((item.get("description") or "").split()),
            )
            index.search_texts[item["id"]] = item["searchText"]
    return index
