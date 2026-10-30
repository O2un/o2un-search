"""Vercel Python 함수에서 Rust 확장(hello_native)이 로드되는지 확인하는 시험용 앱."""

import platform

from fastapi import FastAPI

import hello_native

app = FastAPI()


@app.get("/")
def root():
    return {
        "message": hello_native.greet(),
        "machine": platform.machine(),
        "python": platform.python_version(),
    }
