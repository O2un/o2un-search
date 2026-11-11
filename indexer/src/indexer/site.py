"""블로그 빌드 결과에서 글 주소와 제목을 읽는다.

블로그는 섹션마다 `/{섹션}/search-index.json` 을 내보내고, 공개 글마다 `id`·`href`·`title` 이
들어 있다. 주소 규칙(폴더 → 섹션)을 이 레포에 복제하지 않으려고 이 값을 그대로 쓴다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SitePost:
    href: str
    title: str


def load_site_index(dist: Path) -> dict[str, SitePost]:
    posts: dict[str, SitePost] = {}
    files = sorted(dist.glob("*/search-index.json"))
    if not files:
        raise SystemExit(f"{dist} 에 search-index.json 이 없습니다. 블로그에서 npm run build 를 먼저 돌리세요.")
    for path in files:
        for item in json.loads(path.read_text(encoding="utf-8")):
            posts[item["id"]] = SitePost(href=item["href"], title=item["title"])
    return posts
