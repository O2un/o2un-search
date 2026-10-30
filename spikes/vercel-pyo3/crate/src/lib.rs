//! Vercel Python 함수에서 PyO3 확장이 로드되는지만 확인하는 시험용 크레이트.

use pyo3::prelude::*;

#[pyfunction]
fn greet() -> &'static str {
    "hello from rust"
}

#[pymodule]
fn hello_native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(greet, m)?)?;
    Ok(())
}
