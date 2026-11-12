//! 검색용 토크나이저. 글 본문과 검색어를 같은 함수로 자른다.
//!
//! 규칙
//! - 입력을 NFC 로 정규화한다.
//! - 한글 음절(U+AC00..=U+D7A3)이 이어진 구간은 음절 2-gram 으로 자른다. 한 음절짜리 구간은 버린다.
//! - ASCII 영문·숫자가 이어진 구간은 소문자 단어 하나가 된다.
//! - 그 밖의 문자(기호, 공백, 한글 자모, 다른 문자 체계)는 모두 구분자다.
//! - 출력은 나온 순서 그대로이고 중복을 지우지 않는다.

use unicode_normalization::UnicodeNormalization;

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

fn push_tokens(group: &[(Kind, char)], tokens: &mut Vec<String>) {
    // chunk_by 가 만드는 그룹은 비어 있지 않다
    let kind = group[0].0;

    match kind {
        Kind::Hangul => {
            tokens.extend(group.windows(2).map(|w| format!("{}{}", w[0].1, w[1].1)));
        }
        Kind::Word => {
            let word: String = group.iter().map(|&(_, c)| c.to_ascii_lowercase()).collect();
            tokens.push(word);
        }
        Kind::Separator => {}
    }
}

pub fn tokenize(text: &str) -> Vec<String> {
    let tagged: Vec<(Kind, char)> = text.nfc().map(|c| (kind_of(c), c)).collect();
    let mut tokens = Vec::new();

    tagged
        .chunk_by(|a, b| a.0 == b.0)
        .for_each(|group| push_tokens(group, &mut tokens));

    tokens
}

#[cfg(test)]
mod tests {
    use super::tokenize;

    const CASES: &[(&str, &[&str])] = &[
        ("검색어", &["검색", "색어"]),
        ("락", &[]),
        ("Rust로 다시", &["rust", "다시"]),
        ("C#에서는 GPT-4", &["c", "에서", "서는", "gpt", "4"]),
        ("Unity6 2026년", &["unity6", "2026"]),
        ("ㅋㅋ 日本語 café", &["caf"]),
        ("  ", &[]),
        ("가나 가나", &["가나", "가나"]),
        // 자모로 풀린(NFD) "가나". 눈으로 구분되지 않아 이스케이프로 적었다
        ("\u{1100}\u{1161}\u{1102}\u{1161}", &["가나"]),
    ];

    #[test]
    fn matches_python_cases() {
        for (text, expected) in CASES {
            assert_eq!(tokenize(text), *expected, "입력: {text:?}");
        }
    }
}
