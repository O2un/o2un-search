-- 검색 서비스가 DB 에 닿는 길을 함수로 둔다. 서비스는 테이블 구조를 모르고 이 함수들만 부른다.
-- 읽기 계정(search_reader)은 테이블 권한을 거두고 함수 실행 권한만 받는다.
--
-- 함수는 소유자 권한으로 돈다(SECURITY DEFINER). 그래서 search_path 를 고정하고, 테이블은
-- 언제나 스키마를 붙여 부른다. vector 타입과 연산자는 public 스키마의 확장에 있다.
-- 순위를 합치는 방식(RRF)과 글 단위 묶기는 서비스에 둔다. 단위 5 가 평가 세트로 다시 고를 값이다.

-- 키워드 후보: 토큰을 OR 로 묶어 tokens 를 찾고 ts_rank_cd 순. 토큰이 없으면 빈 결과.
CREATE FUNCTION search.keyword_candidates(p_tokens text[], p_section text, p_limit int)
RETURNS TABLE (chunk_id text)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
    WITH q AS (
        SELECT to_tsquery('simple', string_agg(DISTINCT quote_literal(t), ' | ')) AS tq
        FROM unnest(p_tokens) AS t
    )
    SELECT c.chunk_id
    FROM search.chunks c
    JOIN search.posts p ON p.post_id = c.post_id
    CROSS JOIN q
    WHERE q.tq IS NOT NULL
      AND c.tokens @@ q.tq
      AND (p_section IS NULL OR starts_with(p.href, '/' || p_section || '/'))
    ORDER BY ts_rank_cd(c.tokens, q.tq) DESC, c.chunk_id
    LIMIT p_limit
$$;

-- 벡터 후보: 같은 모델로 임베딩된 청크만, 코사인 거리 순. 임베딩이 빈 청크는 들지 않는다.
-- HNSW 기본 ef_search(40)는 후보 수(50)보다 작아 함수 안에서 올린다. 함수 정의의 SET 절로는
-- Neon 소유자 계정이 이 값을 걸 수 없어서, 실행할 때 트랜잭션 범위로 건다.
CREATE FUNCTION search.vector_candidates(p_embedding vector, p_model smallint, p_section text, p_limit int)
RETURNS TABLE (chunk_id text)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    PERFORM set_config('hnsw.ef_search', '100', true);
    RETURN QUERY
        SELECT c.chunk_id
        FROM search.chunks c
        JOIN search.posts p ON p.post_id = c.post_id
        WHERE c.embed_model_id = p_model
          AND (p_section IS NULL OR starts_with(p.href, '/' || p_section || '/'))
        ORDER BY c.embedding <=> p_embedding
        LIMIT p_limit;
END
$$;

-- 결과에 붙일 청크와 글 정보.
CREATE FUNCTION search.chunks_by_id(p_ids text[])
RETURNS TABLE (chunk_id text, post_id text, title text, href text, anchor text, heading_path text, body text)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
    SELECT c.chunk_id, c.post_id, p.title, p.href, c.anchor, c.heading_path, c.body
    FROM search.chunks c
    JOIN search.posts p ON p.post_id = c.post_id
    WHERE c.chunk_id = ANY(p_ids)
$$;

-- 검색어 캐시: 모델 id, 조회, 저장.
CREATE FUNCTION search.embed_model_id(p_name text)
RETURNS smallint
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
    SELECT id FROM search.embed_models WHERE name = p_name
$$;

CREATE FUNCTION search.cached_query_embedding(p_hash text, p_model smallint)
RETURNS vector
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
    SELECT embedding FROM search.query_embeddings
    WHERE query_hash = p_hash AND embed_model_id = p_model
$$;

CREATE FUNCTION search.put_query_embedding(p_hash text, p_model smallint, p_embedding vector)
RETURNS void
LANGUAGE sql VOLATILE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
    INSERT INTO search.query_embeddings (query_hash, embed_model_id, embedding)
    VALUES (p_hash, p_model, p_embedding)
    ON CONFLICT DO NOTHING
$$;

-- 함수는 기본으로 PUBLIC 이 실행할 수 있다. 읽기 계정에만 연다.
REVOKE ALL ON FUNCTION
    search.keyword_candidates(text[], text, int),
    search.vector_candidates(vector, smallint, text, int),
    search.chunks_by_id(text[]),
    search.embed_model_id(text),
    search.cached_query_embedding(text, smallint),
    search.put_query_embedding(text, smallint, vector)
FROM PUBLIC;

GRANT EXECUTE ON FUNCTION
    search.keyword_candidates(text[], text, int),
    search.vector_candidates(vector, smallint, text, int),
    search.chunks_by_id(text[]),
    search.embed_model_id(text),
    search.cached_query_embedding(text, smallint),
    search.put_query_embedding(text, smallint, vector)
TO search_reader;

REVOKE ALL ON search.posts, search.chunks, search.embed_models, search.query_embeddings FROM search_reader;
