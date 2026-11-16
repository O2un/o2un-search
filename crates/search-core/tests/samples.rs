//! indexer 의 샘플 글 fixture 와 Astro 렌더 앵커에 Rust 청커를 대조한다.

use std::fs;
use std::path::{Path, PathBuf};

use o2un_search_core::chunker::{Chunk, Ext, MAX_CHUNK_CHARS, chunk};
use o2un_search_core::tokenizer::tokenize;
use serde_json::Value;

fn samples_dir() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../../indexer/tests/samples")
}

fn read(path: &Path) -> String {
    fs::read_to_string(path).unwrap_or_else(|e| panic!("{} 을 읽지 못했다: {e}", path.display()))
}

fn sample_names() -> Vec<String> {
    let mut names: Vec<String> = fs::read_dir(samples_dir())
        .expect("샘플 폴더")
        .map(|entry| {
            entry
                .expect("샘플 항목")
                .file_name()
                .into_string()
                .expect("파일 이름")
        })
        .filter(|name| name.ends_with(".md") || name.ends_with(".mdx"))
        .collect();
    names.sort();
    names
}

fn ext_of(value: &str) -> Ext {
    match value {
        "md" => Ext::Md,
        "mdx" => Ext::Mdx,
        other => panic!("알 수 없는 확장자 {other}"),
    }
}

fn text(value: &Value, key: &str) -> String {
    value[key]
        .as_str()
        .unwrap_or_else(|| panic!("{key} 가 문자열이 아니다"))
        .to_string()
}

#[test]
fn every_sample_has_a_fixture() {
    let names = sample_names();
    assert_eq!(names.len(), 7, "샘플 수가 바뀌었다: {names:?}");
    for name in names {
        assert!(
            samples_dir()
                .join("expected")
                .join(format!("{name}.json"))
                .exists(),
            "{name}"
        );
    }
}

#[test]
fn samples_match_fixtures() {
    for name in sample_names() {
        let source = read(&samples_dir().join(&name));
        let expected: Value = serde_json::from_str(&read(
            &samples_dir().join("expected").join(format!("{name}.json")),
        ))
        .expect("fixture JSON");
        let post_id = text(&expected, "post_id");
        let ext = ext_of(&text(&expected, "ext"));
        let expected_chunks = expected["chunks"].as_array().expect("chunks 배열");

        let actual = chunk(&source, &post_id, ext);
        assert_eq!(actual.len(), expected_chunks.len(), "{name}: 청크 수");

        for (i, (got, want)) in actual.iter().zip(expected_chunks).enumerate() {
            let want_chunk = Chunk {
                chunk_id: text(want, "chunk_id"),
                post_id: text(want, "post_id"),
                anchor: text(want, "anchor"),
                heading_path: text(want, "heading_path"),
                body: text(want, "body"),
                content_hash: text(want, "content_hash"),
            };
            assert_eq!(got, &want_chunk, "{name}: {i}번째 청크");

            let want_tokens: Vec<String> = want["tokens"]
                .as_array()
                .expect("tokens 배열")
                .iter()
                .map(|t| t.as_str().expect("토큰").to_string())
                .collect();
            assert_eq!(
                tokenize(&got.body),
                want_tokens,
                "{name}: {i}번째 청크의 토큰"
            );
        }
    }
}

#[test]
fn long_section_splits_under_limit() {
    let source = read(&samples_dir().join("long_section.md"));
    let chunks = chunk(&source, "samples/long_section", Ext::Md);
    let ids: Vec<&str> = chunks
        .iter()
        .filter(|c| c.anchor == "긴-절")
        .map(|c| c.chunk_id.as_str())
        .collect();
    assert!(ids.len() > 1, "긴 절이 나뉘지 않았다");
    let expected: Vec<String> = (1..=ids.len())
        .map(|n| format!("samples/long_section#긴-절#{n}"))
        .collect();
    assert_eq!(ids, expected);
    for c in &chunks {
        assert!(
            c.body.chars().count() <= MAX_CHUNK_CHARS,
            "{} 이 한도를 넘는다",
            c.chunk_id
        );
    }
}

#[test]
fn crlf_and_lf_give_same_chunks() {
    let source = read(&samples_dir().join("nesting.md"));
    assert_eq!(
        chunk(&source.replace('\n', "\r\n"), "x", Ext::Md),
        chunk(&source, "x", Ext::Md)
    );
}

#[test]
fn bom_is_ignored() {
    let source = read(&samples_dir().join("nesting.md"));
    assert_eq!(
        chunk(&format!("\u{feff}{source}"), "x", Ext::Md),
        chunk(&source, "x", Ext::Md)
    );
}

// 블로그 마크다운 파이프라인으로 샘플을 렌더링해 뽑은 절 id. fixture 와 별개의 정답이다.
#[test]
fn anchors_match_astro_render() {
    let expected: Value =
        serde_json::from_str(&read(&samples_dir().join("astro_anchors.json"))).expect("앵커 JSON");
    let expected = expected.as_object().expect("앵커 객체");
    assert!(!expected.is_empty());
    for (name, anchors) in expected {
        let source = read(&samples_dir().join(name));
        let mut actual: Vec<String> = Vec::new();
        for c in chunk(&source, "x", Ext::Md) {
            if !c.anchor.is_empty() && actual.last() != Some(&c.anchor) {
                actual.push(c.anchor);
            }
        }
        let anchors: Vec<String> = anchors
            .as_array()
            .expect("앵커 배열")
            .iter()
            .map(|a| a.as_str().expect("앵커").to_string())
            .collect();
        assert_eq!(actual, anchors, "{name}");
    }
}
