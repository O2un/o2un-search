# o2un-search

Hybrid search and grounded Q&A services for the [o2un devlog](https://o2un.vercel.app).

Work in progress.

- `indexer/` — chunks published posts, syncs them to Postgres, and fills embeddings. Runs from the blog repo through the reusable workflow `.github/workflows/indexer.yml`.
- `crates/search-core/` — Rust core (PyO3), built into a wheel by `.github/workflows/core-wheel.yml`. Currently a skeleton.
