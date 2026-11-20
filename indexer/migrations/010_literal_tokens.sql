-- 검색어 토큰을 Postgres 파서에 다시 넣지 않는다(portfolio-search 3g).
--
-- 008 의 keyword_matches 는 토큰마다 to_tsquery('simple', ...) 를 거친다. 파서가 `c++` 를 `c` 로,
-- `.net` 을 `net` 으로, `objective-c` 를 세 어휘로 자르므로 개발 용어 사전의 토큰이 맞지 않는다.
-- 토큰은 토크나이저가 이미 정했으니 따옴표를 붙여 tsquery 로 바로 바꾼다. 색인 쪽도 같은 이유로
-- to_tsvector 대신 tsvector 리터럴로 넣는다(indexer `store.tsvector_literal`).
--
-- 지금까지의 토큰(한글 2-gram, ASCII 영문·숫자)은 파서를 거쳐도 그대로라 이 함수로 바꿔도 결과가
-- 같다. 서명이 같아 배포된 검색 서비스가 그대로 부른다.
CREATE OR REPLACE FUNCTION search.keyword_matches(
    p_tokens text[], p_words int[], p_section text, p_limit int, p_min_cover real
)
RETURNS TABLE (chunk_id text)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
    WITH words AS (
        SELECT u.w, string_agg(DISTINCT quote_literal(u.t), ' & ')::tsquery AS q
        FROM unnest(p_tokens, p_words) AS u(t, w)
        GROUP BY u.w
    ),
    total AS (SELECT count(*)::float8 AS n FROM search.chunks),
    weighted AS (
        SELECT words.q,
               greatest(ln((total.n + 1) / ((SELECT count(*) FROM search.chunks c WHERE c.tokens @@ words.q) + 1)), 0.1) AS idf
        FROM words CROSS JOIN total
    ),
    any_token AS (
        SELECT string_agg(DISTINCT quote_literal(t), ' | ')::tsquery AS tq,
               (SELECT sum(idf) FROM weighted) AS idf_sum
        FROM unnest(p_tokens) AS t
    ),
    scored AS (
        SELECT c.chunk_id,
               ts_rank_cd(c.tokens, a.tq) AS rank,
               (SELECT sum(w.idf) FROM weighted w WHERE c.tokens @@ w.q) / a.idf_sum AS cover
        FROM search.chunks c
        JOIN search.posts p ON p.post_id = c.post_id
        CROSS JOIN any_token a
        WHERE a.tq IS NOT NULL
          AND c.tokens @@ a.tq
          AND (p_section IS NULL OR starts_with(p.href, '/' || p_section || '/'))
    )
    SELECT chunk_id FROM scored
    WHERE cover >= p_min_cover
    ORDER BY cover DESC, rank DESC, chunk_id
    LIMIT p_limit
$$;
