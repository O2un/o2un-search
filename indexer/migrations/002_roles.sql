-- 색인용 쓰기 계정과 검색 서비스용 읽기 계정. 둘 다 search 스키마에만 권한이 있다.
-- 이 레포는 공개라 비밀번호를 여기에 두지 않는다. 계정은 로그인할 수 없는 상태로 만들고,
-- `indexer db login <계정>` 이 비밀번호를 정해 로그인을 연다.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'search_writer') THEN
        CREATE ROLE search_writer NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'search_reader') THEN
        CREATE ROLE search_reader NOLOGIN;
    END IF;
END
$$;

GRANT USAGE ON SCHEMA search TO search_writer, search_reader;
GRANT SELECT, INSERT, UPDATE, DELETE ON search.chunks TO search_writer;
GRANT SELECT ON search.chunks TO search_reader;
