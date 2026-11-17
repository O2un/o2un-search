"""청크 경계를 블로그 빌드 결과와 대조한다.

블로그를 `npm run build` 한 뒤 `dist/client` 의 각 글 HTML 에서
`<section data-heading-level="N">` 바로 아래 `hN` 의 id 를 순서대로 모은다. 공개 글마다 청크
앵커 목록(도입부 제외, 분할된 청크는 한 번만)이 그 목록과 같아야 한다.

글 HTML 은 `dist/client/*/{글 id}/index.html` 에서 찾는다. 섹션 폴더 이름을 블로그 코드에서
옮겨 오지 않으려고 와일드카드를 쓴다. 옛 주소를 넘기는 페이지(`http-equiv="refresh"`)는 뺀다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

from .core import chunk
from .corpus import Post, is_published, iter_posts


class _SectionIds(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: list[str] = []
        self._expect: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "section" and values.get("data-heading-level"):
            self._expect = f"h{values['data-heading-level']}"
            return
        if self._expect is not None:
            if tag == self._expect:
                self.ids.append(values.get("id") or "")
            self._expect = None


def section_ids(html: str) -> list[str]:
    parser = _SectionIds()
    parser.feed(html)
    parser.close()
    return parser.ids


def chunk_anchors(post: Post) -> list[str]:
    anchors: list[str] = []
    for item in chunk(post.read(), post.post_id, post.ext):
        if item.anchor and (not anchors or anchors[-1] != item.anchor):
            anchors.append(item.anchor)
    return anchors


def find_page(dist: Path, post_id: str) -> list[Path]:
    pages = []
    for path in dist.glob(f"*/{post_id}/index.html"):
        head = path.read_text(encoding="utf-8")[:2048]
        if 'http-equiv="refresh"' not in head:
            pages.append(path)
    return pages


@dataclass
class Report:
    checked: int = 0
    drafts: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def check(blog_root: Path, dist: Path | None = None) -> Report:
    dist = dist or blog_root / "dist" / "client"
    report = Report()
    for post in iter_posts(blog_root):
        pages = find_page(dist, post.post_id)
        if not is_published(post):
            report.drafts.append(post.post_id)
            if pages:
                report.problems.append(f"{post.post_id}: 초안인데 빌드 결과에 페이지가 있다 {pages}")
            continue
        report.checked += 1
        if len(pages) != 1:
            report.problems.append(f"{post.post_id}: 글 페이지를 하나로 찾지 못했다 {pages}")
            continue
        expected = section_ids(pages[0].read_text(encoding="utf-8"))
        actual = chunk_anchors(post)
        if actual != expected:
            report.problems.append(
                f"{post.post_id}: 앵커 불일치\n  dist : {expected}\n  chunk: {actual}"
            )
    return report
