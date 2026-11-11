-- 검색어 임베딩 캐시. 같은 검색어가 다시 오면 공급자를 부르지 않는다.
-- 방문자 검색어 원문은 저장하지 않는다. 키는 정규화한 검색어의 SHA-256 이다.
-- 검색 서비스는 읽기 계정으로 돌므로, 읽기 계정이 이 테이블에만 넣을 수 있다.
-- 보존 기간과 정리 방식은 단위 3 에서 정한다.
CREATE TABLE search.query_embeddings (
    query_hash      text        NOT NULL,
    embed_model_id  smallint    NOT NULL REFERENCES search.embed_models (id),
    embedding       vector(768) NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (query_hash, embed_model_id)
);

GRANT SELECT, INSERT ON search.query_embeddings TO search_reader;

-- 제목 줄만 있는 청크는 임베딩하지 않는다(embed.has_content). 이미 임베딩된 것도 비운다.
UPDATE search.chunks
SET embedding = NULL, embed_model_id = NULL
WHERE position(chr(10) IN body) = 0 AND ltrim(body) LIKE '#%';
