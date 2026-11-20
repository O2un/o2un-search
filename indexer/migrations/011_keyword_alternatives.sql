-- 검색어 단어마다 대안 표기를 받는 키워드 판정(portfolio-search 3g 단계 3, 동의어).
--
-- 010 의 keyword_matches 는 단어 하나 = 토큰 AND 하나다. 동의어 묶음에 든 단어("유니티")는
-- 대안이 여럿이라 단어 하나 = 대안들의 OR, 대안 하나 = 토큰 AND 로 본다.
--   유니티 → ('유니' & '니티') | 'unity'
-- 토큰마다 (단어 번호, 대안 번호)를 함께 받는다. 단어 무게(idf)는 대안을 합친 조건으로 센다.
-- 나머지(덮는 비율, 순위)는 010 과 같다.
--
-- 010 의 keyword_matches 는 새 서비스가 배포될 때까지 옛 서비스가 부르므로 남긴다.
CREATE FUNCTION search.keyword_matches_alt(
    p_tokens text[], p_words int[], p_alts int[], p_section text, p_limit int, p_min_cover real
)
RETURNS TABLE (chunk_id text)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
    WITH alts AS (
        SELECT u.w, u.a, '(' || string_agg(DISTINCT quote_literal(u.t), ' & ') || ')' AS q
        FROM unnest(p_tokens, p_words, p_alts) AS u(t, w, a)
        GROUP BY u.w, u.a
    ),
    words AS (
        SELECT alts.w, string_agg(alts.q, ' | ')::tsquery AS q
        FROM alts
        GROUP BY alts.w
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

REVOKE ALL ON FUNCTION search.keyword_matches_alt(text[], int[], int[], text, int, real) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION search.keyword_matches_alt(text[], int[], int[], text, int, real) TO search_reader;
