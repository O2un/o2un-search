-- 키워드 후보를 엄하게 고른다. 검색어 토큰을 OR 로 묶으면 문장 검색어는 "이유", "만들" 같은
-- 흔한 조각 하나만 맞아도 걸린다.
--
-- 검색 서비스가 검색어를 단어로 나눠 단어마다 토큰을 묶어 보낸다(p_words 가 p_tokens 의 단어 번호).
-- 단어 무게는 그 단어가 든 청크가 드물수록 크다(idf, 하한 0.1). 청크 하나가 맞힌 단어 무게의 합이
-- 전체의 p_min_cover 이상일 때만 후보다. 단어 하나짜리 검색어는 OR 묶음과 같은 결과다.
--
-- 006 의 keyword_candidates 는 이 함수를 부르는 서비스가 배포될 때까지 남겨 둔다.
CREATE FUNCTION search.keyword_matches(
    p_tokens text[], p_words int[], p_section text, p_limit int, p_min_cover real
)
RETURNS TABLE (chunk_id text)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
    WITH words AS (
        SELECT u.w, to_tsquery('simple', string_agg(DISTINCT quote_literal(u.t), ' & ')) AS q
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
        SELECT to_tsquery('simple', string_agg(DISTINCT quote_literal(t), ' | ')) AS tq,
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

REVOKE ALL ON FUNCTION search.keyword_matches(text[], int[], text, int, real) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION search.keyword_matches(text[], int[], text, int, real) TO search_reader;
