//! 검색 색인용 청커·토크나이저. Python 확장 모듈로 빌드한다.

pub mod slug;
mod slug_table;
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
