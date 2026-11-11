-- 검색 색인. 청크 하나가 행 하나다. 청크 규칙은 indexer/src/indexer/chunker.py 에 있다.
-- vector 확장은 다른 스키마와 같이 쓰는 데이터베이스 전역 객체라 IF NOT EXISTS 로 둔다.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE search.chunks (
    chunk_id      text        PRIMARY KEY,
    post_id       text        NOT NULL,
    post_title    text        NOT NULL,
    href          text        NOT NULL,
    heading_path  text        NOT NULL,
    body          text        NOT NULL,
    tokens        tsvector    NOT NULL,
    embedding     vector(768) NOT NULL,
    embed_model   text        NOT NULL,
    embed_dim     int         NOT NULL,
    content_hash  text        NOT NULL,
    indexed_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX chunks_post_id_idx ON search.chunks (post_id);
CREATE INDEX chunks_tokens_idx ON search.chunks USING gin (tokens);
CREATE INDEX chunks_embedding_idx ON search.chunks USING hnsw (embedding vector_cosine_ops);
