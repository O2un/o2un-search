-- 검색어 캐시 정리(단위 3c). 색인 워크플로가 쓰기 계정으로 보존 기간이 지난 행을 지운다.
-- 읽기 계정은 006 의 함수로만 캐시에 닿으므로 그대로 둔다.
-- DELETE 의 WHERE 가 created_at 을 읽으므로 SELECT 도 함께 준다.
GRANT SELECT, DELETE ON search.query_embeddings TO search_writer;
