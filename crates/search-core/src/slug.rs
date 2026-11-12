//! 블로그(Astro)가 제목에 붙이는 id 를 그대로 다시 만든다. 규칙은 github-slugger 와 같고,
//! 한 글 안에서 같은 슬러그가 다시 나오면 `-1`, `-2` 를 붙인다.

use std::collections::HashMap;

use crate::slug_table::REMOVED_RANGES;

fn removed(c: char) -> bool {
    let code = c as u32;
    let index = REMOVED_RANGES.partition_point(|&(start, _)| start <= code);
    0 < index && code <= REMOVED_RANGES[index - 1].1
}

/// 제목 하나의 슬러그. 중복 번호는 붙이지 않는다.
pub fn slugify(value: &str) -> String {
    let lowercase = value.to_lowercase();
    lowercase
        .chars()
        .filter(|&c| !removed(c))
        .map(|c| if c == ' ' { '-' } else { c })
        .collect()
}

/// 중복 번호를 세는 슬러거. 글 하나마다 새로 만든다.
#[derive(Default)]
pub struct Slugger {
    /// 슬러그 → 지금까지 붙인 마지막 번호
    occurrences: HashMap<String, u32>,
}

impl Slugger {
    pub fn new() -> Self {
        Self::default()
    }

    /// 같은 글에서 이미 나온 슬러그면 번호를 붙인다.
    pub fn slug(&mut self, value: &str) -> String {
        let original = slugify(value);

        if !self.occurrences.contains_key(&original) {
            self.occurrences.insert(original.clone(), 0);
            return original;
        }

        loop {
            let count = self
                .occurrences
                .get_mut(&original)
                .expect("original 은 첫 등장 때 0 으로 들어갔다");
            *count += 1;
            let candidate = format!("{original}-{count}");

            if !self.occurrences.contains_key(&candidate) {
                self.occurrences.insert(candidate.clone(), 0);
                return candidate;
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::{Slugger, removed, slugify};
    use crate::slug_table::REMOVED_RANGES;

    fn slug_all(values: &[&str]) -> Vec<String> {
        let mut slugger = Slugger::new();
        values.iter().map(|v| slugger.slug(v)).collect()
    }

    // 기대값은 블로그 빌드 결과(dist)에서 옮겼다
    #[test]
    fn matches_github_slugger() {
        let cases = [
            ("① 런타임에서만 드러나는 것", "-런타임에서만-드러나는-것"),
            (".NET 10에 없는 API", "net-10에-없는-api"),
            (
                "C# Delegate/event와 R3 Subject의 선택 기준",
                "c-delegateevent와-r3-subject의-선택-기준",
            ),
        ];
        for (input, expected) in cases {
            assert_eq!(slugify(input), expected, "입력: {input:?}");
        }
    }

    #[test]
    fn matches_python_reference() {
        let cases = [
            ("Hello  World", "hello--world"),
            ("A—B 그리고 C", "ab-그리고-c"),
            ("탭\t문자", "탭문자"),
            // 끝 시그마: 단어 끝의 Σ 는 ς 가 된다
            ("ΣΑΣ 끝", "σας-끝"),
            // İ 는 i + 결합 점(U+0307) 두 글자가 된다
            ("İstanbul", "i\u{307}stanbul"),
            ("🚀 출시 노트", "-출시-노트"),
            ("  앞뒤 공백  ", "--앞뒤-공백--"),
            ("Ⅻ 로마 숫자", "ⅻ-로마-숫자"),
            ("ＡＢＣ 전각", "ａｂｃ-전각"),
            ("x_y-z.1", "x_y-z1"),
        ];
        for (input, expected) in cases {
            assert_eq!(slugify(input), expected, "입력: {input:?}");
        }
    }

    #[test]
    fn repeats_get_numbers() {
        assert_eq!(
            slug_all(&["예시", "예시", "예시-1", "예시"]),
            ["예시", "예시-1", "예시-1-1", "예시-2"]
        );
    }

    #[test]
    fn repeats_skip_taken_numbers() {
        assert_eq!(
            slug_all(&["a", "a-1", "a", "a"]),
            ["a", "a-1", "a-2", "a-3"]
        );
    }

    // 기호만 있는 제목은 빈 슬러그가 되고, 빈 슬러그도 중복 번호를 받는다
    #[test]
    fn empty_slugs_are_numbered_too() {
        assert_eq!(slug_all(&["", "", "?"]), ["", "-1", "-2"]);
    }

    #[test]
    fn each_slugger_starts_fresh() {
        let mut first = Slugger::new();
        first.slug("예시");
        let mut second = Slugger::new();
        assert_eq!(second.slug("예시"), "예시");
    }

    #[test]
    fn table_is_sorted_and_disjoint() {
        assert_eq!(REMOVED_RANGES.len(), 736);
        for (start, end) in REMOVED_RANGES {
            assert!(start <= end, "{start:X}..{end:X}");
        }
        for pair in REMOVED_RANGES.windows(2) {
            assert!(
                pair[0].1 < pair[1].0,
                "{:X?} 와 {:X?} 의 순서가 틀렸거나 겹친다",
                pair[0],
                pair[1]
            );
        }
    }

    #[test]
    fn removed_at_range_edges() {
        assert!(removed('\u{0}'));
        assert!(removed('\u{1F}'));
        assert!(!removed(' ')); // 공백은 지우지 않고 '-' 로 바뀐다
        assert!(removed('!'));
        assert!(!removed('-'));
        assert!(!removed('_'));
        assert!(!removed('a'));
        assert!(!removed('가'));
        assert!(removed('\u{10FFFF}'));

        // 모든 구간의 양 끝은 지워지고, 끝 바로 다음 글자는 (다음 구간이 붙어 있지 않으면) 남는다
        for (i, &(start, end)) in REMOVED_RANGES.iter().enumerate() {
            for code in [start, end] {
                if let Some(c) = char::from_u32(code) {
                    assert!(removed(c), "U+{code:04X} 는 지워져야 한다");
                }
            }
            let next_start = REMOVED_RANGES.get(i + 1).map(|r| r.0);
            if next_start != Some(end + 1)
                && let Some(c) = char::from_u32(end + 1)
            {
                assert!(!removed(c), "U+{:04X} 는 남아야 한다", end + 1);
            }
        }
    }
}
