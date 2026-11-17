# 벤치마크

Python 구현(`indexer/src/indexer/chunker.py`·`tokenizer.py`)과 Rust 구현(이 크레이트)의 속도. 공개 글 전체 기준으로 Rust가 3.1~3.2배 빠르다.

## 2026-11-17

| 구현 | 중앙값 (1차) | 중앙값 (2차) |
| --- | --- | --- |
| Python | 30.38 ms | 30.29 ms |
| Rust | 9.64 ms | 9.62 ms |
| 배수 | 3.2배 | 3.1배 |

| 항목 | 값 |
| --- | --- |
| 기기 | Intel Core i9-14900K, RAM 64GB |
| OS | Windows 11 Pro 10.0.26200 |
| Python | 3.12.10 |
| Rust | rustc 1.99.1, maturin 1.16.0, release 빌드 |
| 글·청크 | 공개 글 38편, 청크 251개 |
| 반복 | 50바퀴, 두 번 실행 |

한 바퀴 전체가 Python으로도 30ms 남짓이다. 같은 기기에서 블로그 `npm run build`가 8초쯤 걸리므로, CI 색인 한 번에서 청크·토큰화가 차지하는 몫은 두 구현 모두 작다.

## 재는 법

```
# crates/search-core 에서. release 빌드로 설치한다
VIRTUAL_ENV=../../indexer/.venv uvx maturin develop --uv --release

uv run --project ../../indexer indexer bench-core --blog <블로그 레포 경로> --repeat 50
```

- 한 바퀴: 공개 글 전체를 `chunk` 하고, 나온 청크마다 본문을 `tokenize`
- 글은 미리 읽어 둔다. 파일 읽기는 시간에 들어가지 않는다
- Rust 시간은 Python에서 부른 시간이다. 문자열 복사, 튜플과 `Chunk` 생성처럼 경계를 넘는 비용이 들어간다. indexer가 실제로 받는 속도라 이 값을 기준으로 삼는다
- 바퀴마다 두 구현을 번갈아 돌리고, 재기 전에 한 바퀴씩 버린다
- `--release` 없이 설치한 debug 빌드로 재면 안 된다. 위 기기에서 debug 빌드는 Rust 49.70 ms, Python 31.82 ms(20바퀴)로 Rust가 더 느렸다
