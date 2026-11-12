//! 청커·토크나이저의 Rust 구현 자리. 단위 2가 채운다.
//!
//! 정답지는 `indexer/tests/samples/expected/` 의 fixture 이고, 순수 Python 기준 구현은
//! `indexer/src/indexer/{chunker,tokenizer}.py` 다. 출력이 바이트 단위로 같아야 교체한다.
//! 지금은 wheel 빌드·배포 경로(단위 1c)를 확인하려고 함수 자리만 둔다.

pub mod tokenizer;

use pyo3::exceptions::PyNotImplementedError;
use pyo3::prelude::*;

#[pyfunction]
fn tokenize(_text: &str) -> PyResult<Vec<String>> {
    Err(PyNotImplementedError::new_err("단위 2에서 구현한다"))
}

#[pyfunction]
fn chunk(_post_source: &str, _post_id: &str, _ext: &str) -> PyResult<Vec<Py<PyAny>>> {
    Err(PyNotImplementedError::new_err("단위 2에서 구현한다"))
}

#[pymodule]
fn o2un_search_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(tokenize, m)?)?;
    m.add_function(wrap_pyfunction!(chunk, m)?)?;
    Ok(())
}
