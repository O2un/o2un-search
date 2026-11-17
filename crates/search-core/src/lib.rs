//! 검색 색인용 청커·토크나이저. Python 확장 모듈로 빌드한다.

pub mod chunker;
pub mod slug;
mod slug_table;
pub mod tokenizer;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

use crate::chunker::Ext;

/// `chunk` 가 Python 에 돌려주는 튜플 하나.
/// 순서: chunk_id, post_id, anchor, heading_path, body, content_hash. indexer 가 `Chunk(*t)` 로 감싼다.
type ChunkTuple = (String, String, String, String, String, String);

#[pyfunction]
fn tokenize(text: &str) -> Vec<String> {
    tokenizer::tokenize(text)
}

#[pyfunction]
fn chunk(post_source: &str, post_id: &str, ext: &str) -> PyResult<Vec<ChunkTuple>> {
    let parsed = ext
        .parse::<Ext>()
        .map_err(|_| PyValueError::new_err(format!("ext 는 md 또는 mdx: {ext:?}")))?;

    Ok(chunker::chunk(post_source, post_id, parsed)
        .into_iter()
        .map(|c| {
            (
                c.chunk_id,
                c.post_id,
                c.anchor,
                c.heading_path,
                c.body,
                c.content_hash,
            )
        })
        .collect())
}

#[pymodule]
fn o2un_search_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(tokenize, m)?)?;
    m.add_function(wrap_pyfunction!(chunk, m)?)?;
    Ok(())
}
