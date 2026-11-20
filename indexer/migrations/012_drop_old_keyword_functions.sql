-- 검색 서비스가 부르지 않는 옛 키워드 함수를 지운다.
--
-- - keyword_candidates (006): 008 의 keyword_matches 로 바뀌었다
-- - keyword_matches (008, 010): 011 의 keyword_matches_alt 로 바뀌었다
--
-- 둘 다 새 함수를 부르는 서비스가 배포될 때까지 남겨 두었고, 그 배포는 끝났다(portfolio-search 3g 단계 3).
DROP FUNCTION search.keyword_candidates(text[], text, int);
DROP FUNCTION search.keyword_matches(text[], int[], text, int, real);
