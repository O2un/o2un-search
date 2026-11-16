//! 블로그 글 원문을 절 단위 청크로 자른다.
//!
//! 절의 경계는 블로그의 `src/lib/rehype-heading-sections.mjs` 가 만드는 `<section>` 과 같다.
//! - 최상위의 `h2` 는 언제나 절을 연다.
//! - `hN`(N >= 3) 은 `h(N-1)` 절 안에 있을 때만 절을 연다. 레벨을 건너뛴 제목은 감싼 절의 본문이 된다.
//! - `h1` 은 절을 열지도 닫지도 않는다.
//! - 콜아웃(`:::note`)과 인용문 안의 제목은 절을 열지 않지만, 슬러그 중복 번호는 센다.
//!
//! 청크 하나는 절 하나다. 본문은 절의 제목 줄과, 다음 절 제목이 나오기 전까지의 내용이다.
//! 첫 절 앞의 도입부는 앵커 없는 청크가 되고, 비어 있으면 만들지 않는다.
//! 본문에서 버리는 것: 프론트매터, 각주 정의와 각주 표시, 이미지, `::youtube`·`::x` 디렉티브,
//! `.mdx` 의 `import`·`export` 블록과 한 줄 전체가 JSX 태그인 줄. 코드 블록은 남긴다.

// TODO(3단계): 이 파일의 todo!() 를 채운다. 기준 구현은 `indexer/src/indexer/chunker.py`(333줄).
// 함수 순서는 원본과 같다. 위에서부터 채우고, 하나 채울 때마다 그 함수의 테스트부터 통과시키면
// 어디서 어긋났는지 바로 보인다:
//   cargo test chunker::tests::heading_text   (함수 이름 일부로 골라 돌릴 수 있다)
// 마지막에 tests/samples.rs(샘플 글 7개 전체 대조)가 통과하면 3단계 끝이다.
//
// 공통 주의
// - 길이는 전부 "문자 수"다. Python `len(s)` 는 코드 포인트 수, Rust `s.len()` 은 바이트 수다.
//   한글은 한 글자가 3바이트라 `len()` 을 쓰면 8,192 한도가 1/3 로 줄어든다. `s.chars().count()` 를 쓴다.
//   문자열을 n 글자에서 자를 때도 바이트 위치가 아니라 문자 경계로 자른다(`char_indices` 를 찾아볼 것).
// - Python `strip()`·`rstrip()` 은 Rust `trim()`·`trim_end()`, `lstrip(" ")` 는 `trim_start_matches(' ')`.
// - 정규식은 원본 패턴을 아래 static 으로 그대로 옮겨 두었다(fancy-regex: 역참조·전후방 탐색 지원).
//   - Python `pat.match(s)` → 패턴이 모두 `^` 로 시작하므로 `RE.captures(s)` / `RE.is_match(s)` 와 같다.
//     fancy-regex 는 이 함수들이 `Result` 를 돌려준다(역추적 한도 초과 때 Err). 여기서는 `.unwrap()` 으로 충분하다.
//   - Python `pat.sub(r"\1", s)` → `RE.replace_all(s, "${1}")`. `$1` 바로 뒤에 글자가 붙으면 그룹 이름으로
//     읽히므로 중괄호를 쓴다. 반환은 `Cow<str>` 이라 `.into_owned()` 나 `.to_string()` 으로 String 을 만든다.

use std::{sync::LazyLock};

use fancy_regex::Regex;
use sha2::{Digest, Sha256};

use crate::slug::Slugger;

/// 청크 본문 한도(문자 수). 임베딩 입력 한도 8,192 토큰을 문자 수로 대신한다.
pub const MAX_CHUNK_CHARS: usize = 8192;

pub const HEADING_PATH_SEPARATOR: &str = " > ";

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Chunk {
    pub chunk_id: String,
    pub post_id: String,
    pub anchor: String,
    pub heading_path: String,
    pub body: String,
    pub content_hash: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Ext {
    Md,
    Mdx,
}

fn re(pattern: &str) -> Regex {
    Regex::new(pattern).expect("정규식 패턴")
}

// 줄 단위 판정
static FENCE_OPEN: LazyLock<Regex> = LazyLock::new(|| re(r"^ {0,3}(`{3,}|~{3,})(.*)$"));
static ATX: LazyLock<Regex> = LazyLock::new(|| re(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*$"));
static ATX_CLOSING: LazyLock<Regex> = LazyLock::new(|| re(r"(?:^|[ \t]+)#+$"));
static BLOCKQUOTE: LazyLock<Regex> = LazyLock::new(|| re(r"^ {0,3}> ?"));
static CONTAINER_OPEN: LazyLock<Regex> = LazyLock::new(|| re(r"^ {0,3}(:{3,})[A-Za-z]"));
static CONTAINER_CLOSE: LazyLock<Regex> = LazyLock::new(|| re(r"^ {0,3}(:{3,})[ \t]*$"));
static FOOTNOTE_DEF: LazyLock<Regex> = LazyLock::new(|| re(r"^ {0,3}\[\^[^\]]+\]:"));
static EMBED_DIRECTIVE: LazyLock<Regex> = LazyLock::new(|| re(r"^[ \t]*::(?:youtube|x)(?=[\[{ \t]|$)"));
static MDX_ESM: LazyLock<Regex> = LazyLock::new(|| re(r"^(?:import|export)\b"));
static MDX_JSX_LINE: LazyLock<Regex> = LazyLock::new(|| re(r"^[ \t]*(?:</?[A-Za-z][^<>]*>[ \t]*)+$"));

// 줄 안의 인라인 문법
static IMAGE: LazyLock<Regex> = LazyLock::new(|| re(r#"!\[[^\]]*\]\((?:[^()"]|"[^"]*")*\)"#));
static FOOTNOTE_REF: LazyLock<Regex> = LazyLock::new(|| re(r"\[\^[^\]\s]+\]"));
static LINK: LazyLock<Regex> = LazyLock::new(|| re(r#"\[([^\]]*)\]\((?:[^()"]|"[^"]*")*\)"#));
static STRONG: LazyLock<Regex> = LazyLock::new(|| re(r"(\*\*|__)(.+?)\1"));
static EM_STAR: LazyLock<Regex> = LazyLock::new(|| re(r"\*(.+?)\*"));
static EM_UNDERSCORE: LazyLock<Regex> = LazyLock::new(|| re(r"(?<![A-Za-z0-9])_(.+?)_(?![A-Za-z0-9])"));
static STRIKE: LazyLock<Regex> = LazyLock::new(|| re(r"~~(.+?)~~"));
static ESCAPE: LazyLock<Regex> = LazyLock::new(|| re(r"\\([!-/:-@\[-`{-~])"));
static DOUBLE_DASH: LazyLock<Regex> = LazyLock::new(|| re(r"(?<!-)--(?!-)"));
static CODE_SPAN: LazyLock<Regex> = LazyLock::new(|| re(r"(`+)(.+?)\1"));

/// 맨 앞의 `---` … `---` 프론트매터를 뗀다. 닫는 줄이 없으면 그대로 둔다.
fn strip_frontmatter<'a>(lines: &'a [&'a str]) -> &'a [&'a str] {
    if false == matches!(lines.first(), Some(l) if l.trim_end() == "---"){
        return lines;
    }

    for index in 1..lines.len(){
        if lines[index].trim_end() == "---" {
            return &lines[index + 1..];
        }
    }

    lines
}

/// 본문 줄에서 이미지와 각주 표시를 지운다.
fn clean_inline(text: &str) -> String {
    FOOTNOTE_REF.replace_all(&IMAGE.replace_all(text, ""), "").to_string()
}

/// 이스케이프가 없는 조각을 보이는 글자로 바꾼다.
fn unescaped_text(segment: &str) -> String {
    let segment = IMAGE.replace_all(segment, "");
    let segment = FOOTNOTE_REF.replace_all(&segment, "");
    let segment = LINK.replace_all(&segment, "$1");
    let segment = STRONG.replace_all(&segment, "$2");
    let segment = EM_STAR.replace_all(&segment, "$1");
    let segment = EM_UNDERSCORE.replace_all(&segment, "$1");
    let segment = STRIKE.replace_all(&segment, "$1");

    DOUBLE_DASH.replace_all(&segment, "\u{2014}").into_owned()
}

/// 역슬래시로 이스케이프한 글자는 문법으로 읽지 않고 글자 그대로 둔다.
fn inline_text(segment: &str) -> String {
    let (mut parts, last_pos) = ESCAPE.captures_iter(segment)
        .fold((Vec::new(),0), |(mut acc, pos), cap_result| {
            let cap = cap_result.expect("정규식 캡처 중 에러가 발생했습니다");
            let m = cap.get(0).unwrap();
            acc.push(unescaped_text(&segment[pos..m.start()]));
            acc.push(cap.get(1).unwrap().as_str().to_string());
            (acc, m.end())
        });

    parts.push(unescaped_text(&segment[last_pos..]));
    parts.join("")
}

/// ATX 제목 줄의 내용을 화면에 보이는 글자로 바꾼다. 슬러그와 제목 경로에 쓴다.
pub fn heading_text(raw: &str) -> String {
    let (mut parts, last_pos) = CODE_SPAN.captures_iter(raw)
        .fold((Vec::new(),0), |(mut acc, pos), cap_result| {
            let cap = cap_result.expect("정규식 캡처 중 에러가 발생했습니다");
            let m = cap.get(0).unwrap();
            acc.push(inline_text(&raw[pos..m.start()]));

            let mut code = cap.get(2).unwrap().as_str();
            if matches!(code.as_bytes(), [b' ', .., b' ']) && false == code.trim().is_empty() {
                code = &code[1..code.len() -1];
            }
            
            acc.push(code.to_string());
            (acc, m.end())
        });

    parts.push(inline_text(&raw[last_pos..]));
    parts.join("").trim().to_string()
}

/// ATX 제목 줄이면 (레벨, 보이는 제목) 을 돌려준다.
fn parse_atx(line: &str) -> Option<(usize, String)> {
    let caps = ATX.captures(line).expect("정규식 캡쳐 에러")?;

    let group = caps.get(2).map_or("", |m| m.as_str());
    let content = ATX_CLOSING.replace_all(group, "");
    let len = caps.get(1).unwrap().as_str().chars().count();

    Some((len, heading_text(&content)))
}

/// 절을 열 수 있는 최상위 제목 줄.
#[derive(Debug, Clone)]
struct Heading {
    level: usize,
    text: String,
    anchor: String,
    /// 본문에 들어갈 원래 줄(clean_inline 을 거친 것)
    line: String,
}

/// scan 이 돌려주는 줄 하나: 본문 줄이거나, 절을 열 수도 있는 최상위 제목.
#[derive(Debug, Clone)]
enum Item {
    Line(String),
    Heading(Heading),
}

/// 원문을 본문 줄과 최상위 제목으로 나눈다. 버릴 줄은 여기서 빠진다.
fn scan(source: &str, ext: Ext) -> Vec<Item> {
    let source = source.replace("\r\n", "\n").replace('\r', "\n");
    let raw: Vec<&str> = source.trim_start_matches('\u{feff}').split('\n').collect();
    let lines = strip_frontmatter(&raw);

    let mut slugger = Slugger::new();
    let mut items: Vec<Item> = Vec::new();
    let mut fence: Option<(char,usize)> = None;
    let mut containers: Vec<usize> = Vec::new();
    let mut in_footnote = false;
    let mut in_esm = false;

    for &line in lines{
        if let Some((char_, length)) = fence {
            items.push(Item::Line(line.to_string()));
            let stripped = line.trim();
            if line.len() - line.trim_start_matches(' ').len() <= 3
                && false == stripped.is_empty()
                && stripped.chars().all(|c| c == char_)
                && length <= stripped.len()
            {
                fence = None;
            }
            continue;
        }

        if in_footnote {
            if line.trim().is_empty() || line.starts_with("    ") || line.starts_with('\t') {
                continue;
            }
            in_footnote = false;
        }

        if in_esm {
            if false == line.trim().is_empty() {
                continue;
            }
            in_esm = false;
        }

        if FOOTNOTE_DEF.is_match(line).unwrap() {
            in_footnote = true;
            continue;
        }

        let fence_match = FENCE_OPEN.captures(line).unwrap();
        if let Some(caps) = fence_match {
            let g1 = caps.get(1).map_or("", |m| m.as_str());
            let g2 = caps.get(2).map_or("", |m| m.as_str());
            if false == (g1.starts_with('`') && g2.contains('`')) {
                let marker_char = g1.chars().next().unwrap();
                fence = Some((marker_char, g1.len()));
                items.push(Item::Line(line.to_string()));
                continue;
            }
        }
        
        if ext == Ext::Mdx && containers.is_empty() {
            if MDX_ESM.is_match(line).unwrap() {
                in_esm = true;
                continue;
            }
            if MDX_JSX_LINE.is_match(line).unwrap() {
                continue;
            }
        }

        if EMBED_DIRECTIVE.is_match(line).unwrap() {
            continue;
        }

        let close = CONTAINER_CLOSE.captures(line).unwrap();
        if let Some(caps) = close {
            let colons = caps.get(1).map_or(0, |m| m.as_str().len());
            if matches!(containers.last(), Some(&last) if last <= colons) {
                containers.pop();
                items.push(Item::Line(line.to_string()));
                continue;
            }
        }

        let open = CONTAINER_OPEN.captures(line).unwrap();
        if let Some(caps) = open {
            containers.push(caps.get(1).map_or(0, |m| m.as_str().len()));
            items.push(Item::Line(clean_inline(line)));
            continue;
        }

        let mut quoted = line;
        let mut depth = 0;
        while let Some(m) = BLOCKQUOTE.find(quoted).unwrap() {
            quoted = &quoted[m.end()..];
            depth +=1;
        }

        let heading = parse_atx(quoted);
        if let Some((level, text)) = heading {
            let anchor = slugger.slug(&text);
            if 0 == depth && containers.is_empty() {
                items.push(Item::Heading(Heading{
                    level, 
                    text, 
                    anchor, 
                    line: clean_inline(line)
                }));
                continue;
            }
        }

        items.push(Item::Line(clean_inline(line)));
    }

    items
}

/// 줄 끝 공백을 떼고, 연속 빈 줄을 하나로, 앞뒤 빈 줄을 없애고 '\n' 으로 잇는다.
fn normalize(lines: &[String]) -> String {
    let mut out: Vec<&str> = Vec::new();
    for line in lines{
        let trimmed= line.trim_end();
        if trimmed.is_empty() && matches!(out.last(), None | Some(&"")) {
            continue;
        }

        out.push(trimmed);
    }

    while matches!(out.last(), Some(&"")) {
        out.pop();
    }
    
    out.join("\n")
}

/// 빈 줄을 경계로 문단을 나눈다. 코드 블록 안의 빈 줄에서는 나누지 않는다.
fn blocks(body: &str) -> Vec<String> {
    let mut blocks= Vec::new();
    let mut current = Vec::new();
    let mut fence: Option<(char, usize)> = None;

    for line in body.split('\n') {
        if fence.is_none() {
            let match_op = FENCE_OPEN.captures(line);
            if let Some(mat) = match_op.unwrap() {
                let matched = mat.get(1).unwrap().as_str();
                fence = Some((matched.chars().next().unwrap(), matched.len()));
            } else if line.is_empty() {
                if false == current.is_empty() {
                    blocks.push(current.join("\n"));
                    current = Vec::new();
                }
                continue;
            }
        } else {
            let stripped = line.trim();
            let f = fence.unwrap();
            if false == stripped.is_empty() && stripped.chars().all(|c| c == f.0) && f.1 <= stripped.chars().count() {
                fence = None;
            }
        }
        current.push(line);
    }
    if false == current.is_empty() {
        blocks.push(current.join("\n"));
    }

    blocks
}

/// 한도를 넘는 문단 하나를 줄 단위로, 줄 하나가 넘으면 문자 단위로 자른다.
fn hard_split(block: &str) -> Vec<String> {
    let mut pieces = vec![];
    let mut current = String::new();
    for line in block.split('\n') {
        let mut line = line;
        while MAX_CHUNK_CHARS < line.chars().count() {
            if false == current.is_empty() {
                pieces.push(current);
                current = String::new()
            }
            let cut_pos = line.char_indices().nth(MAX_CHUNK_CHARS).unwrap().0;
            pieces.push(line[..cut_pos].to_string());
            line = &line[cut_pos..];
        }

        let candidate = if false == current.is_empty(){ format!("{current}\n{line}")} else { line.to_string()};

        if MAX_CHUNK_CHARS < candidate.chars().count() {
            pieces.push(current);
            current = line.to_string();
        }
        else {
            current = candidate;
        }
    }

    if false == current.is_empty() {
        pieces.push(current);
    }

    pieces
}

/// 한도를 넘는 본문을 문단 경계로 나눈다.
fn split(body: &str) -> Vec<String> {
    if body.chars().count() <= MAX_CHUNK_CHARS {
        return vec![body.to_string()];
    }

    let mut parts = vec![];
    let mut current: String = String::new();

    for block in blocks(body) {
        let pieces = if MAX_CHUNK_CHARS < block.chars().count() {hard_split(&block)} else {vec![block]};
        for piece in pieces {
            let candidate = if false == current.is_empty() {format!("{current}\n\n{piece}")} else {piece.clone()};
            if MAX_CHUNK_CHARS < candidate.chars().count() {
                parts.push(current);
                current = piece;
            }
            else {
                current = candidate;
            }
        }
    }

    if false == current.is_empty() {
        parts.push(current);
    }

    parts
}

/// 제목 경로와 본문의 SHA-256 (소문자 16진수). 1b 가 증분 판정에 쓴다.
pub fn content_hash(heading_path: &str, body: &str) -> String {
    hex::encode(Sha256::digest(format!("{heading_path}\n{body}")))
}

/// 글 원문 하나를 청크 목록으로 자른다.
pub fn chunk(post_source: &str, post_id: &str, ext: Ext) -> Vec<Chunk> {
    let mut sections:Vec<(String,String, Vec<String>)> = vec![(String::new(),String::new(), vec![])];
    let mut stack:Vec<Heading> = vec![];

    for item in scan(post_source, ext) {
        match item {
            Item::Heading(heading) => {
                let is_level_two: bool = 2 == heading.level;
                let is_level_three_or_more = 3 <= heading.level;
                let target_level = heading.level - 1;
                let has_parent = stack.iter().any(|h: &Heading| {target_level == h.level});

                if is_level_two || (is_level_three_or_more && has_parent) {
                    while matches!(stack.last(), Some(top) if heading.level <= top.level) {
                        stack.pop();
                    }
                    let heading_line = heading.line.clone();
                    let heading_anchor = heading.anchor.clone();
                    stack.push(heading);

                    let path = stack
                        .iter()
                        .map(|h| h.text.as_str())
                        .collect::<Vec<_>>()
                        .join(HEADING_PATH_SEPARATOR);

                    sections.push((heading_anchor, path, vec![heading_line]));
                } else {
                    let line = heading.line;
                    if let Some(last_section) = sections.last_mut() {
                        last_section.2.push(line);
                    }
                }
            },
            Item::Line(line) =>{
                if let Some(last_section) = sections.last_mut() {
                    last_section.2.push(line);
                }
            }
        }
    }

    sections
        .into_iter()
        .filter_map(|(anchor, path, lines)| {
            let normalized = normalize(&lines);
            if normalized.is_empty() {
                None
            } else {
                Some((anchor, path, normalized))
            }
        })
        .flat_map(|(anchor, path, normalized)| {
            let pieces = split(&normalized);
            let piece_count = pieces.len();

            pieces
                .into_iter()
                .enumerate()
                .map(move |(idx, piece)| {
                    let chunk_id = if piece_count < 2 {
                        format!("{post_id}#{anchor}")
                    } else {
                        let num = idx + 1;
                        format!("{post_id}#{anchor}#{num}")
                    };
                    let content_hash = content_hash(&path, &piece);

                    Chunk {
                        chunk_id: chunk_id,
                        post_id: post_id.to_string(),
                        anchor: anchor.clone(),
                        heading_path: path.clone(),
                        body: piece,
                        content_hash: content_hash,
                    }
                })
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn regexes_compile() {
        let all: [&LazyLock<Regex>; 20] = [
            &FENCE_OPEN,
            &ATX,
            &ATX_CLOSING,
            &BLOCKQUOTE,
            &CONTAINER_OPEN,
            &CONTAINER_CLOSE,
            &FOOTNOTE_DEF,
            &EMBED_DIRECTIVE,
            &MDX_ESM,
            &MDX_JSX_LINE,
            &IMAGE,
            &FOOTNOTE_REF,
            &LINK,
            &STRONG,
            &EM_STAR,
            &EM_UNDERSCORE,
            &STRIKE,
            &ESCAPE,
            &DOUBLE_DASH,
            &CODE_SPAN,
        ];
        for regex in all {
            LazyLock::force(regex);
        }
    }

    #[test]
    fn strip_frontmatter_cases() {
        let cases: [(&[&str], &[&str]); 5] = [
            (&["---", "title: x", "---", "본문"], &["본문"]),
            (&["---", "title: x", "---  ", "본문"], &["본문"]),
            (&["본문", "---", "x", "---"], &["본문", "---", "x", "---"]),
            (&["---", "닫히지 않음"], &["---", "닫히지 않음"]),
            (&[], &[]),
        ];
        for (input, expected) in cases {
            assert_eq!(strip_frontmatter(input), expected, "입력: {input:?}");
        }
    }

    #[test]
    fn clean_inline_cases() {
        let cases = [
            ("앞 ![대체](./a.png \"캡션 (괄호)\") 뒤", "앞  뒤"),
            ("각주[^note] 와 [^2] 둘", "각주 와  둘"),
            ("[^띄어 쓴 각주] 는 남는다", "[^띄어 쓴 각주] 는 남는다"),
            ("이미지 두 개 ![a](x.png)![b](y.png) 끝", "이미지 두 개  끝"),
        ];
        for (input, expected) in cases {
            assert_eq!(clean_inline(input), expected, "입력: {input:?}");
        }
    }

    #[test]
    fn heading_text_cases() {
        let cases = [
            ("평범한 제목", "평범한 제목"),
            (
                "**굵게**와 *기울임*, _밑줄_ 그리고 ~~취소~~",
                "굵게와 기울임, 밑줄 그리고 취소",
            ),
            (
                "snake_case_name 은 기울임이 아니다",
                "snake_case_name 은 기울임이 아니다",
            ),
            (
                "[링크 글자](https://example.com \"제목\") 뒤",
                "링크 글자 뒤",
            ),
            ("![이미지](./a.png) 남는 글자", "남는 글자"),
            ("각주 표시[^1] 지움", "각주 표시 지움"),
            (
                "`코드 **굵게 아님**` 바깥 **굵게**",
                "코드 **굵게 아님** 바깥 굵게",
            ),
            ("`` 백틱 ` 하나 ``", "백틱 ` 하나"),
            ("\\*별표\\* 이스케이프", "*별표* 이스케이프"),
            ("\\[대괄호\\] 와 \\_밑줄\\_", "[대괄호] 와 _밑줄_"),
            ("A -- B --- C", "A — B --- C"),
            ("앞뒤 공백   ", "앞뒤 공백"),
            ("C# 과 .NET", "C# 과 .NET"),
            ("__굵게 밑줄__ 끝", "굵게 밑줄 끝"),
        ];
        for (input, expected) in cases {
            assert_eq!(heading_text(input), expected, "입력: {input:?}");
        }
    }

    #[test]
    fn parse_atx_cases() {
        let cases: [(&str, Option<(usize, &str)>); 13] = [
            ("## 제목", Some((2, "제목"))),
            ("### 닫는 해시 ###", Some((3, "닫는 해시"))),
            ("#### 해시 뒤 #태그", Some((4, "해시 뒤 #태그"))),
            ("   ## 들여쓰기 3칸", Some((2, "들여쓰기 3칸"))),
            ("    ## 들여쓰기 4칸", None),
            ("#해시만붙음", None),
            ("##", Some((2, ""))),
            ("## ", Some((2, ""))),
            ("####### 일곱 개", None),
            ("# h1", Some((1, "h1"))),
            ("##\t탭 구분", Some((2, "탭 구분"))),
            ("## 제목 #", Some((2, "제목"))),
            ("## C#", Some((2, "C#"))),
        ];
        for (input, expected) in cases {
            let expected = expected.map(|(level, text)| (level, text.to_string()));
            assert_eq!(parse_atx(input), expected, "입력: {input:?}");
        }
    }

    /// scan 결과를 비교하기 쉬운 문자열로 바꾼다.
    /// 본문 줄은 `L|줄`, 제목은 `H레벨|앵커|제목|본문에 들어갈 줄`.
    fn render(items: &[Item]) -> Vec<String> {
        items
            .iter()
            .map(|item| match item {
                Item::Line(line) => format!("L|{line}"),
                Item::Heading(h) => format!("H{}|{}|{}|{}", h.level, h.anchor, h.text, h.line),
            })
            .collect()
    }

    fn scan_md(source: &str) -> Vec<String> {
        render(&scan(source, Ext::Md))
    }

    #[test]
    fn scan_frontmatter_and_top_heading() {
        assert_eq!(
            scan_md("---\ntitle: x\n---\n도입\n## 제목\n본문\n"),
            ["L|도입", "H2|제목|제목|## 제목", "L|본문", "L|"]
        );
    }

    #[test]
    fn scan_heading_anchor_uses_visible_text() {
        assert_eq!(
            scan_md("## **굵게** [링크](https://a.b) 제목 ##"),
            ["H2|굵게-링크-제목|굵게 링크 제목|## **굵게** [링크](https://a.b) 제목 ##"]
        );
    }

    #[test]
    fn scan_nested_headings_count_slugs_but_stay_lines() {
        let source = "> ## 같은 제목\n:::note\n## 같은 제목\n:::\n## 같은 제목";
        assert_eq!(
            scan_md(source),
            [
                "L|> ## 같은 제목",
                "L|:::note",
                "L|## 같은 제목",
                "L|:::",
                "H2|같은-제목-2|같은 제목|## 같은 제목",
            ]
        );
    }

    #[test]
    fn scan_container_closes_only_with_enough_colons() {
        let source = "::::note\n:::\n## 안\n::::\n## 밖";
        assert_eq!(
            scan_md(source),
            ["L|::::note", "L|:::", "L|## 안", "L|::::", "H2|밖|밖|## 밖"]
        );
    }

    #[test]
    fn scan_fence_hides_headings() {
        let source = "````\n## 아님\n```\n````\n``` a`b\n## 제목";
        assert_eq!(
            scan_md(source),
            [
                "L|````",
                "L|## 아님",
                "L|```",
                "L|````",
                "L|``` a`b",
                "H2|제목|제목|## 제목",
            ]
        );
    }

    #[test]
    fn scan_drops_footnote_definitions_images_and_embeds() {
        let source = "본문[^1] ![a](x.png)\n\n[^1]: 정의\n    이어짐\n\n다음\n::youtube[영상]{#abc}\n::youtubes 남음";
        assert_eq!(
            scan_md(source),
            ["L|본문 ", "L|", "L|다음", "L|::youtubes 남음"]
        );
    }

    #[test]
    fn scan_mdx_drops_esm_and_jsx_lines() {
        let source = "import A from 'a'\nimport B from 'b'\n\n<Comp />\n본문";
        assert_eq!(render(&scan(source, Ext::Mdx)), ["L|", "L|본문"]);
        assert_eq!(
            scan_md(source),
            ["L|import A from 'a'", "L|import B from 'b'", "L|", "L|<Comp />", "L|본문"]
        );
    }

    #[test]
    fn scan_mdx_keeps_esm_inside_container() {
        let source = ":::note\nimport A from 'a'\n:::";
        assert_eq!(
            render(&scan(source, Ext::Mdx)),
            ["L|:::note", "L|import A from 'a'", "L|:::"]
        );
    }

    #[test]
    fn scan_crlf_and_bom_match_lf() {
        let lf = scan_md("## 제목\n본문\n");
        assert_eq!(scan_md("\u{feff}## 제목\r\n본문\r\n"), lf);
        assert_eq!(scan_md("## 제목\r본문\r"), lf);
    }

    fn owned(lines: &[&str]) -> Vec<String> {
        lines.iter().map(|line| line.to_string()).collect()
    }

    #[test]
    fn normalize_cases() {
        let cases: [(&[&str], &str); 4] = [
            (
                &["", "", "첫 줄  ", "", "", "", "둘째 줄\t", "", ""],
                "첫 줄\n\n둘째 줄",
            ),
            (&["  ", "\t", "x"], "x"),
            (&[], ""),
            (&["", ""], ""),
        ];
        for (input, expected) in cases {
            assert_eq!(normalize(&owned(input)), expected, "입력: {input:?}");
        }
    }

    #[test]
    fn blocks_cases() {
        let cases: [(&str, &[&str]); 3] = [
            ("a\n\nb\n\n\nc", &["a", "b", "c"]),
            ("```\nx\n\ny\n```\n\nz", &["```\nx\n\ny\n```", "z"]),
            ("~~~\n```\n\n~~~\nw", &["~~~\n```\n\n~~~\nw"]),
        ];
        for (input, expected) in cases {
            assert_eq!(blocks(input), expected, "입력: {input:?}");
        }
    }

    fn char_lengths(parts: &[String]) -> Vec<usize> {
        parts.iter().map(|part| part.chars().count()).collect()
    }

    #[test]
    fn split_short_body_is_one_part() {
        assert_eq!(split("짧은 본문"), ["짧은 본문"]);
    }

    #[test]
    fn split_on_paragraphs() {
        let body = ["가".repeat(3000), "나".repeat(3000), "다".repeat(3000)].join("\n\n");
        let parts = split(&body);
        assert_eq!(char_lengths(&parts), [6002, 3000]);
        assert_eq!(parts[1], "다".repeat(3000));
    }

    #[test]
    fn split_keeps_fenced_block_together_until_hard_split() {
        let fenced = format!("```\n{}\n```", vec!["코드".repeat(1000); 5].join("\n\n"));
        assert_eq!(
            char_lengths(&split(&format!("{fenced}\n\n끝"))),
            [8011, 2007]
        );
    }

    #[test]
    fn split_long_line_by_chars() {
        assert_eq!(
            char_lengths(&split(&"라".repeat(20000))),
            [8192, 8192, 3616]
        );
    }

    #[test]
    fn split_long_paragraph_by_lines() {
        let body = vec!["마".repeat(3000); 4].join("\n");
        assert_eq!(char_lengths(&split(&body)), [6001, 6001]);
    }

    #[test]
    fn content_hash_cases() {
        assert_eq!(
            content_hash("", "본문"),
            "1cb36780813a3a29bc0f884daab19b10905d5a9cd336bc7897e5531d9feec290"
        );
        assert_eq!(
            content_hash("A > B", "## B\n\n내용"),
            "951a9db9ed8c660cdf6bc2ffcab21c26a8db0d8a2cadd74a168dc935e3f1e9dc"
        );
    }
}
