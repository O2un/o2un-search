"""블로그 글 원문을 절 단위 청크로 자른다.

절의 경계는 블로그의 `src/lib/rehype-heading-sections.mjs` 가 만드는 `<section>` 과 같다.

- 최상위의 `h2` 는 언제나 절을 연다.
- `hN`(N >= 3) 은 `h(N-1)` 절 안에 있을 때만 절을 연다. 레벨을 건너뛴 제목(`h2` 바로 아래의
  `h4`, 첫 `h2` 앞의 `h3`)은 절을 열지 않고 감싸고 있는 절의 본문이 된다.
- `h1` 은 절을 열지도 닫지도 않는다.
- 콜아웃(`:::note`)과 인용문 안의 제목은 절을 열지 않는다. 다만 블로그가 그 제목에도 id 를
  붙이므로, 중복 번호를 맞추려고 슬러그는 센다.

청크 하나는 절 하나다. 본문은 절의 제목 줄과, 다음 절 제목이 나오기 전까지의 내용이다.
첫 절 앞의 도입부는 앵커 없는 청크가 되고, 비어 있으면 만들지 않는다.

본문에서 버리는 것: 프론트매터, 각주 정의와 각주 표시(`[^n]`), 이미지 문법, `::youtube`·`::x`
디렉티브, `.mdx` 의 `import`·`export` 블록과 한 줄 전체가 JSX 태그인 줄. 코드 블록은 남긴다.

지원하지 않는 문법(블로그 글에 아직 없다): setext 제목, 목록 안 제목, 각주 표시가 든 제목,
HTML 엔티티가 든 제목. 실제 글에 나타나면 경계 대조(`check-anchors`)가 잡는다.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Literal

from .slug import Slugger

# 임베딩 입력 한도는 8,192 토큰이다. 토큰 수는 공급자 토크나이저를 불러야 셀 수 있으므로
# 문자 수로 대신한다. 한국어·코드 모두 토큰 수가 문자 수보다 적어 이 값을 넘지 않는다.
MAX_CHUNK_CHARS = 8192

HEADING_PATH_SEPARATOR = " > "


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    post_id: str
    anchor: str
    heading_path: str
    body: str
    content_hash: str


_FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_ATX = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*$")
_ATX_CLOSING = re.compile(r"(?:^|[ \t]+)#+$")
_BLOCKQUOTE = re.compile(r"^ {0,3}> ?")
_CONTAINER_OPEN = re.compile(r"^ {0,3}(:{3,})[A-Za-z]")
_CONTAINER_CLOSE = re.compile(r"^ {0,3}(:{3,})[ \t]*$")
_FOOTNOTE_DEF = re.compile(r"^ {0,3}\[\^[^\]]+\]:")
_EMBED_DIRECTIVE = re.compile(r"^[ \t]*::(?:youtube|x)(?=[\[{ \t]|$)")
_MDX_ESM = re.compile(r"^(?:import|export)\b")
_MDX_JSX_LINE = re.compile(r"^[ \t]*(?:</?[A-Za-z][^<>]*>[ \t]*)+$")

_IMAGE = re.compile(r'!\[[^\]]*\]\((?:[^()"]|"[^"]*")*\)')
_FOOTNOTE_REF = re.compile(r"\[\^[^\]\s]+\]")
_LINK = re.compile(r'\[([^\]]*)\]\((?:[^()"]|"[^"]*")*\)')
_STRONG = re.compile(r"(\*\*|__)(.+?)\1")
_EM_STAR = re.compile(r"\*(.+?)\*")
_EM_UNDERSCORE = re.compile(r"(?<![A-Za-z0-9])_(.+?)_(?![A-Za-z0-9])")
_STRIKE = re.compile(r"~~(.+?)~~")
_ESCAPE = re.compile(r"\\([!-/:-@\[-`{-~])")
_DOUBLE_DASH = re.compile(r"(?<!-)--(?!-)")
_CODE_SPAN = re.compile(r"(`+)(.+?)\1")


def _strip_frontmatter(lines: list[str]) -> list[str]:
    if not lines or lines[0].rstrip() != "---":
        return lines
    for index in range(1, len(lines)):
        if lines[index].rstrip() == "---":
            return lines[index + 1 :]
    return lines


def _clean_inline(text: str) -> str:
    """본문 줄에서 이미지와 각주 표시를 지운다."""
    return _FOOTNOTE_REF.sub("", _IMAGE.sub("", text))


def _unescaped_text(segment: str) -> str:
    segment = _IMAGE.sub("", segment)
    segment = _FOOTNOTE_REF.sub("", segment)
    segment = _LINK.sub(r"\1", segment)
    segment = _STRONG.sub(r"\2", segment)
    segment = _EM_STAR.sub(r"\1", segment)
    segment = _EM_UNDERSCORE.sub(r"\1", segment)
    segment = _STRIKE.sub(r"\1", segment)
    # 블로그는 smartypants 를 켜 두어 `--` 를 em dash 로 바꾼 뒤 슬러그를 만든다.
    return _DOUBLE_DASH.sub("—", segment)


def _inline_text(segment: str) -> str:
    """역슬래시로 이스케이프한 글자는 문법으로 읽지 않고 글자 그대로 둔다."""
    parts: list[str] = []
    position = 0
    for match in _ESCAPE.finditer(segment):
        parts.append(_unescaped_text(segment[position : match.start()]))
        parts.append(match.group(1))
        position = match.end()
    parts.append(_unescaped_text(segment[position:]))
    return "".join(parts)


def heading_text(raw: str) -> str:
    """ATX 제목 줄의 내용을 화면에 보이는 글자로 바꾼다. 슬러그와 제목 경로에 쓴다."""
    parts: list[str] = []
    position = 0
    for match in _CODE_SPAN.finditer(raw):
        parts.append(_inline_text(raw[position : match.start()]))
        code = match.group(2)
        if len(code) >= 2 and code[0] == " " and code[-1] == " " and code.strip():
            code = code[1:-1]
        parts.append(code)
        position = match.end()
    parts.append(_inline_text(raw[position:]))
    return "".join(parts).strip()


def _parse_atx(line: str) -> tuple[int, str] | None:
    match = _ATX.match(line)
    if not match:
        return None
    content = _ATX_CLOSING.sub("", match.group(2) or "")
    return len(match.group(1)), heading_text(content)


@dataclass
class _Heading:
    level: int
    text: str
    anchor: str
    line: str


def _scan(source: str, ext: str) -> list[str | _Heading]:
    """원문을 본문 줄과 최상위 제목으로 나눈다. 버릴 줄은 여기서 빠진다."""
    lines = source.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff").split("\n")
    lines = _strip_frontmatter(lines)

    slugger = Slugger()
    items: list[str | _Heading] = []
    fence: tuple[str, int] | None = None
    containers: list[int] = []
    in_footnote = False
    in_esm = False

    for line in lines:
        if fence is not None:
            items.append(line)
            stripped = line.strip()
            char, length = fence
            if (
                len(line) - len(line.lstrip(" ")) <= 3
                and stripped
                and set(stripped) == {char}
                and len(stripped) >= length
            ):
                fence = None
            continue

        if in_footnote:
            if not line.strip() or line.startswith(("    ", "\t")):
                continue
            in_footnote = False

        if in_esm:
            if line.strip():
                continue
            in_esm = False

        if _FOOTNOTE_DEF.match(line):
            in_footnote = True
            continue

        fence_match = _FENCE_OPEN.match(line)
        if fence_match and not (fence_match.group(1)[0] == "`" and "`" in fence_match.group(2)):
            marker = fence_match.group(1)
            fence = (marker[0], len(marker))
            items.append(line)
            continue

        if ext == "mdx" and not containers:
            if _MDX_ESM.match(line):
                in_esm = True
                continue
            if _MDX_JSX_LINE.match(line):
                continue

        if _EMBED_DIRECTIVE.match(line):
            continue

        close = _CONTAINER_CLOSE.match(line)
        if close and containers and len(close.group(1)) >= containers[-1]:
            containers.pop()
            items.append(line)
            continue
        open_ = _CONTAINER_OPEN.match(line)
        if open_:
            containers.append(len(open_.group(1)))
            items.append(_clean_inline(line))
            continue

        quoted = line
        depth = 0
        while (match := _BLOCKQUOTE.match(quoted)) is not None:
            quoted = quoted[match.end() :]
            depth += 1

        heading = _parse_atx(quoted)
        if heading is not None:
            level, text = heading
            anchor = slugger.slug(text)
            if depth == 0 and not containers:
                items.append(_Heading(level, text, anchor, _clean_inline(line)))
                continue

        items.append(_clean_inline(line))

    return items


def _normalize(lines: list[str]) -> str:
    out: list[str] = []
    for line in lines:
        line = line.rstrip()
        if not line and (not out or not out[-1]):
            continue
        out.append(line)
    while out and not out[-1]:
        out.pop()
    return "\n".join(out)


def _blocks(body: str) -> list[str]:
    """빈 줄을 경계로 문단을 나눈다. 코드 블록 안의 빈 줄에서는 나누지 않는다."""
    blocks: list[str] = []
    current: list[str] = []
    fence: tuple[str, int] | None = None
    for line in body.split("\n"):
        if fence is None:
            match = _FENCE_OPEN.match(line)
            if match:
                fence = (match.group(1)[0], len(match.group(1)))
            elif not line:
                if current:
                    blocks.append("\n".join(current))
                    current = []
                continue
        else:
            stripped = line.strip()
            if stripped and set(stripped) == {fence[0]} and len(stripped) >= fence[1]:
                fence = None
        current.append(line)
    if current:
        blocks.append("\n".join(current))
    return blocks


def _hard_split(block: str) -> list[str]:
    pieces: list[str] = []
    current = ""
    for line in block.split("\n"):
        while len(line) > MAX_CHUNK_CHARS:
            if current:
                pieces.append(current)
                current = ""
            pieces.append(line[:MAX_CHUNK_CHARS])
            line = line[MAX_CHUNK_CHARS:]
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > MAX_CHUNK_CHARS:
            pieces.append(current)
            current = line
        else:
            current = candidate
    if current:
        pieces.append(current)
    return pieces


def _split(body: str) -> list[str]:
    if len(body) <= MAX_CHUNK_CHARS:
        return [body]
    parts: list[str] = []
    current = ""
    for block in _blocks(body):
        pieces = _hard_split(block) if len(block) > MAX_CHUNK_CHARS else [block]
        for piece in pieces:
            candidate = f"{current}\n\n{piece}" if current else piece
            if len(candidate) > MAX_CHUNK_CHARS:
                parts.append(current)
                current = piece
            else:
                current = candidate
    if current:
        parts.append(current)
    return parts


def content_hash(heading_path: str, body: str) -> str:
    return hashlib.sha256(f"{heading_path}\n{body}".encode("utf-8")).hexdigest()


def chunk(post_source: str, post_id: str, ext: Literal["md", "mdx"]) -> list[Chunk]:
    sections: list[tuple[str, str, list[str]]] = [("", "", [])]
    stack: list[_Heading] = []

    for item in _scan(post_source, ext):
        if isinstance(item, _Heading) and (
            item.level == 2 or (item.level >= 3 and any(h.level == item.level - 1 for h in stack))
        ):
            while stack and stack[-1].level >= item.level:
                stack.pop()
            stack.append(item)
            path = HEADING_PATH_SEPARATOR.join(h.text for h in stack)
            sections.append((item.anchor, path, [item.line]))
        else:
            sections[-1][2].append(item.line if isinstance(item, _Heading) else item)

    chunks: list[Chunk] = []
    for anchor, path, lines in sections:
        body = _normalize(lines)
        if not body:
            continue
        parts = _split(body)
        for number, part in enumerate(parts, start=1):
            chunk_id = f"{post_id}#{anchor}" + (f"#{number}" if len(parts) > 1 else "")
            chunks.append(Chunk(chunk_id, post_id, anchor, path, part, content_hash(path, part)))
    return chunks
