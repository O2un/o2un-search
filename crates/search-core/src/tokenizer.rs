//! 검색용 토크나이저. 글 본문과 검색어를 같은 함수로 자른다.
//!
//! 규칙
//! - 입력을 NFC 로 정규화한다.
//! - 개발 용어 사전(`dev_terms::TERMS`)의 용어는 토큰 하나가 된다. ASCII 대소문자는 가리지 않고
//!   토큰은 사전의 소문자 꼴이다.
//!   - 앞 글자가 ASCII 영문·숫자가 아닌 자리에서만 맞춘다. `System.NET` 의 `.NET` 은 용어가 아니다.
//!   - 여러 용어가 맞으면 가장 긴 것을 쓴다. `ASP.NET` 은 `asp.net` 하나다.
//!   - 영문·숫자로 끝나는 용어는 뒤 글자가 ASCII 영문·숫자가 아니어야 한다. 기호로 끝나는 용어는
//!     뒤를 보지 않는다. `C++26` 은 `c++`, `26` 이다.
//! - 한글 음절(U+AC00..=U+D7A3)이 이어진 구간은 음절 2-gram 으로 자른다. 한 음절짜리 구간은 버린다.
//! - ASCII 영문·숫자가 이어진 구간은 소문자 단어 하나가 된다. 한 글자 단어는 버린다.
//! - 그 밖의 문자(기호, 공백, 한글 자모, 다른 문자 체계)는 모두 구분자다.
//! - 출력은 나온 순서 그대로이고 중복을 지우지 않는다.

use unicode_normalization::UnicodeNormalization;

use crate::dev_terms::TERMS;

#[derive(Clone, Copy, PartialEq, Eq)]
enum Kind {
    Hangul,
    Word,
    Separator,
}

fn is_hangul(c: char) -> bool {
    matches!(c, '가'..='힣')
}

fn is_ascii_alnum(c: char) -> bool {
    c.is_ascii_alphanumeric()
}

fn kind_of(c: char) -> Kind {
    match c {
        c if is_hangul(c) => Kind::Hangul,
        c if is_ascii_alnum(c) => Kind::Word,
        _ => Kind::Separator,
    }
}

/// `start` 자리에서 맞는 사전 용어. `TERMS` 는 긴 것부터 적혀 있다.
fn term_at(chars: &[char], start: usize) -> Option<&'static str> {
    if start > 0 && is_ascii_alnum(chars[start - 1]) {
        return None;
    }
    TERMS.iter().copied().find(|term| {
        let end = start + term.len();
        let Some(piece) = chars.get(start..end) else {
            return false;
        };
        let same = piece
            .iter()
            .zip(term.chars())
            .all(|(&c, t)| c.is_ascii() && c.to_ascii_lowercase() == t);
        let ends_in_word = term.chars().last().is_some_and(is_ascii_alnum);
        let glued = chars.get(end).is_some_and(|&c| is_ascii_alnum(c));
        same && false == (ends_in_word && glued)
    })
}

fn flush(kind: Kind, run: &mut Vec<char>, tokens: &mut Vec<String>) {
    match kind {
        Kind::Hangul => {
            tokens.extend(run.windows(2).map(|w| format!("{}{}", w[0], w[1])));
        }
        Kind::Word if run.len() > 1 => {
            tokens.push(run.iter().map(|c| c.to_ascii_lowercase()).collect());
        }
        Kind::Word | Kind::Separator => {}
    }
    run.clear();
}

pub fn tokenize(text: &str) -> Vec<String> {
    let chars: Vec<char> = text.nfc().collect();
    let mut tokens = Vec::new();
    let mut run = Vec::new();
    let mut run_kind = Kind::Separator;

    let mut at = 0;
    while at < chars.len() {
        if let Some(term) = term_at(&chars, at) {
            flush(run_kind, &mut run, &mut tokens);
            run_kind = Kind::Separator;
            tokens.push(term.to_string());
            // 용어는 ASCII 라 바이트 수가 글자 수다.
            at += term.len();
            continue;
        }
        let kind = kind_of(chars[at]);
        if kind != run_kind {
            flush(run_kind, &mut run, &mut tokens);
            run_kind = kind;
        }
        if matches!(kind, Kind::Hangul | Kind::Word) {
            run.push(chars[at]);
        }
        at += 1;
    }
    flush(run_kind, &mut run, &mut tokens);

    tokens
}

#[cfg(test)]
mod tests {
    use super::tokenize;

    const CASES: &[(&str, &[&str])] = &[
        ("검색어", &["검색", "색어"]),
        ("락", &[]),
        ("Rust로 다시", &["rust", "다시"]),
        ("C#에서는 GPT-4", &["c#", "에서", "서는", "gpt"]),
        ("Unity6 2026년", &["unity6", "2026"]),
        ("ㅋㅋ 日本語 café", &["caf"]),
        ("  ", &[]),
        ("가나 가나", &["가나", "가나"]),
        // 자모로 풀린(NFD) "가나". 눈으로 구분되지 않아 이스케이프로 적었다
        ("\u{1100}\u{1161}\u{1102}\u{1161}", &["가나"]),
        // 개발 용어 사전
        (
            "C++26과 C# 그리고 F#",
            &["c++", "26", "c#", "그리", "리고", "f#"],
        ),
        (
            "ASP.NET과 .NET, System.NET",
            &["asp.net", ".net", "system", "net"],
        ),
        ("Node.js나 node.jsx", &["node.js", "node", "jsx"]),
        ("Objective-C로", &["objective-c"]),
        ("abc++ x#", &["abc"]),
        ("유니티C#", &["유니", "니티", "c#"]),
        // 한 글자 영문·숫자는 버린다
        ("C 스타일, 유니티 6, A/B", &["스타", "타일", "유니", "니티"]),
        ("R3 v2", &["r3", "v2"]),
        // ASCII 만 맞춘다: 전각 Ｃ 는 용어가 아니고 기호 뒤라 단어도 아니다
        ("\u{FF23}#", &[]),
    ];

    #[test]
    fn matches_python_cases() {
        for (text, expected) in CASES {
            assert_eq!(tokenize(text), *expected, "입력: {text:?}");
        }
    }
}
