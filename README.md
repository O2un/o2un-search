# o2un-search

[o2un 데브로그](https://o2un.vercel.app)의 하이브리드 검색과 근거 기반 질의응답 서비스.

작업 중이다.

- `indexer/` — 공개 글을 청크로 잘라 Postgres와 맞추고 임베딩을 채운다. 블로그 레포가 재사용 워크플로 `.github/workflows/indexer.yml`로 실행한다.
- `crates/search-core/` — 청커·토크나이저의 Rust 구현(PyO3). `.github/workflows/core-wheel.yml`이 wheel로 빌드한다. 공개 글 전체에서 Python 구현과 출력이 같다(`indexer compare-core`). indexer는 `INDEXER_CORE`(`python` | `rust`)로 구현을 고르고, CI는 아직 Python 구현으로 돈다.

## 벤치마크

공개 글 전체(38편, 청크 251개)를 청크로 자르고 토큰화하는 한 바퀴를 Python에서 불러 50바퀴 잰 중앙값이다.

| 구현 | 한 바퀴 중앙값 |
| --- | --- |
| Python | 30.3 ms |
| Rust (release 빌드) | 9.6 ms |

Rust가 3.1~3.2배 빠르다. 2026-11-17, Intel Core i9-14900K, Windows 11, Python 3.12.10, rustc 1.99.1에서 쟀다. 재는 방법과 두 번의 측정값은 [`crates/search-core/BENCH.md`](crates/search-core/BENCH.md)에 있다.
