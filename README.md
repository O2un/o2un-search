# o2un-search

Hybrid search and grounded Q&A services for the [o2un devlog](https://o2un.vercel.app).

Work in progress.

- `indexer/` — chunks published posts, syncs them to Postgres, and fills embeddings. Runs from the blog repo through the reusable workflow `.github/workflows/indexer.yml`.
- `crates/search-core/` — Rust port of the chunker and tokenizer (PyO3), built into a wheel by `.github/workflows/core-wheel.yml`. Output matches the Python implementation on every published post (`indexer compare-core`). The indexer picks one with `INDEXER_CORE` (`python` | `rust`); CI still runs the Python one.

## Benchmark

Chunking and tokenizing all published posts (38 posts, 251 chunks), median of 50 rounds, called from Python:

| Implementation | Median per round |
| --- | --- |
| Python | 30.3 ms |
| Rust (release build) | 9.6 ms |

Rust is 3.1–3.2× faster. Measured 2026-11-17 on an Intel Core i9-14900K, Windows 11, Python 3.12.10, rustc 1.99.1. Method and both runs: [`crates/search-core/BENCH.md`](crates/search-core/BENCH.md).
