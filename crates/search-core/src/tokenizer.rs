//! 검색용 토크나이저. 글 본문과 검색어를 같은 함수로 자른다.
//!
//! 기준 구현: `indexer/src/indexer/tokenizer.py` (48줄). 출력이 바이트 단위로 같아야 한다.
//!
//! 규칙
//! - 입력을 NFC 로 정규화한다.
//! - 한글 음절(U+AC00..=U+D7A3)이 이어진 구간은 음절 2-gram 으로 자른다. 한 음절짜리 구간은 버린다.
//! - ASCII 영문·숫자가 이어진 구간은 소문자 단어 하나가 된다.
//! - 그 밖의 문자(기호, 공백, 한글 자모, 다른 문자 체계)는 모두 구분자다.
//! - 출력은 나온 순서 그대로이고 중복을 지우지 않는다.

use unicode_normalization::UnicodeNormalization; // `text.nfc()` 를 쓰게 해 주는 트레이트

#[derive(Clone, Copy, PartialEq, Eq)]
enum Kind {
    Hangul,
    Word,
    Separator,
}

/// 한글 완성형 음절(U+AC00..=U+D7A3)인가. 원본 `_is_hangul`. 자모는 구분자다.
fn is_hangul(c: char) -> bool {
    matches!(c, '가'..='힣')
}

/// ASCII 영문·숫자인가. 원본 `_is_ascii_alnum`.
fn is_ascii_alnum(c: char) -> bool {
    c.is_ascii_alphanumeric()
}

/// 문자 하나의 구간 종류. 원본 `for char in text:` 안의 `kind = ...` 한 줄.
fn kind_of(c: char) -> Kind {
    match c {
        c if is_hangul(c) => Kind::Hangul,
        c if is_ascii_alnum(c) => Kind::Word,
        _ => Kind::Separator,
    }
}

fn push_tokens(group: &[(Kind, char)], tokens: &mut Vec<String>) {
    // chunk_by로 묶인 그룹은 항상 1개 이상의 원소를 가짐
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
    let mut tokens = Vec::new(); // mut 및 초기화 필수

    // 반환값이 없는 부수 효과(tokens.push)만 수행하므로 for_each 사용
    tagged
        .chunk_by(|a, b| a.0 == b.0)
        .for_each(|group| push_tokens(group, &mut tokens));

    tokens
}

#[cfg(test)]
mod tests {
    use super::tokenize;

    // indexer/tests/test_tokenizer.py 의 사례를 그대로 옮겼다.
    const CASES: &[(&str, &[&str])] = &[
        ("검색어", &["검색", "색어"]),
        ("락", &[]),
        ("Rust로 다시", &["rust", "다시"]),
        ("C#에서는 GPT-4", &["c", "에서", "서는", "gpt", "4"]),
        ("Unity6 2026년", &["unity6", "2026"]),
        ("ㅋㅋ 日本語 café", &["caf"]),
        ("  ", &[]),
        ("가나 가나", &["가나", "가나"]),
        // 자모로 풀린(NFD) "가나". 소스 파일에서 눈으로 구분되지 않아 이스케이프로 적었다
        ("\u{1100}\u{1161}\u{1102}\u{1161}", &["가나"]),
    ];

    #[test]
    fn matches_python_cases() {
        for (text, expected) in CASES {
            assert_eq!(tokenize(text), *expected, "입력: {text:?}");
        }
    }
}
