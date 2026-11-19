-- 3f: 짧은 절의 임베딩 맥락, 글 설명.
--
-- search.chunks
--   context_chunk_id  짧은 절을 임베딩할 때 본문 뒤에 붙이는 이웃 청크. 짧지 않은 청크는 NULL.
--                     embed 가 이 청크 본문을 붙여 입력을 만든다(embed 는 청크 순서를 모른다).
--   embed_hash        임베딩 입력(본문 + 이웃 본문)의 해시. '' 이면 임베딩하지 않는 청크다
--                     (제목뿐인 절, 키워드로만 찾는 "글 정보" 청크). 이웃 절만 바뀌어도 이 값이
--                     바뀌므로, sync 가 본문 해시와 함께 비교해 그 청크의 임베딩을 비운다.
-- search.posts
--   description       글 설명. 검색 결과에서 "글 정보" 청크가 대표일 때 미리보기로 쓴다.
--
-- 기본값은 이 열들을 모르는 이전 indexer 가 색인 워크플로에서 돌 때를 위한 것이다. 그때 들어간
-- 행은 다음 sync 가 값이 다르다고 보고 고친다.
ALTER TABLE search.chunks
    ADD COLUMN context_chunk_id text,
    ADD COLUMN embed_hash text NOT NULL DEFAULT '';

ALTER TABLE search.posts
    ADD COLUMN description text NOT NULL DEFAULT '';

-- 결과에 붙일 글 설명. chunks_by_id 의 반환 꼴을 바꾸면 배포된 서비스가 깨지므로 따로 둔다.
CREATE FUNCTION search.post_descriptions(p_ids text[])
RETURNS TABLE (post_id text, description text)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
    SELECT p.post_id, p.description
    FROM search.posts p
    WHERE p.post_id = ANY(p_ids)
$$;

REVOKE ALL ON FUNCTION search.post_descriptions(text[]) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION search.post_descriptions(text[]) TO search_reader;
