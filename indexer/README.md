# indexer

블로그 글을 절 단위 청크로 자르고 검색용 토큰을 만든다. 순수 Python 기준 구현이며, 단위 2의
Rust 구현이 `tests/samples/expected/` 의 출력과 바이트 단위로 같아야 한다.

```
chunk(post_source, post_id, ext) -> list[Chunk]   # src/indexer/chunker.py
tokenize(text) -> list[str]                        # src/indexer/tokenizer.py
```

규칙은 각 모듈 머리 주석에 있다.

## 명령

```
uv run pytest                                       # 샘플 fixture 대조
uv run indexer check-anchors --blog <블로그 레포>    # 실제 글 경계 대조
uv run python scripts/update_fixtures.py            # 규칙을 바꾼 뒤 fixture 갱신
```

`check-anchors` 는 블로그 레포에서 먼저 `npm run build` 를 돌려 둔 `dist/client` 를 읽는다.
공개 글마다 청크 앵커 목록이 글 HTML 의 절 제목 id 목록과 같아야 통과한다.

fixture 는 경계 사례를 담은 샘플 글로만 만든다. 실제 블로그 글은 이 레포에 복제하지 않는다.

## 색인 (1b)

`search` 스키마(Neon Postgres, pgvector)에 글·청크·임베딩을 저장한다. 처음 한 번:

```
cp .env.example .env                                # SEARCH_OWNER_URL, GEMINI_API_KEY 를 채운다
uv run indexer db migrate                           # search 스키마, 테이블, 계정 2개
uv run indexer db login search_writer               # 비밀번호를 정해 .env 에 연결 문자열을 쓴다
uv run indexer db login search_reader
uv run indexer db check-grants                      # 두 계정이 댓글 테이블을 못 읽는지 확인
```

색인은 두 단계다. `sync` 는 블로그를 빌드한 뒤 돌리고, 글 주소와 제목은 빌드의
`search-index.json` 에서 읽는다. `embed` 는 DB 만 본다.

```
uv run indexer sync --blog <블로그 레포>    # 글·청크·토큰을 맞춘다. 바뀐 청크의 임베딩은 비운다
uv run indexer embed                        # 임베딩이 빈 청크와 다른 모델로 만든 청크를 채운다
```

둘 다 `--dry-run` 으로 바꿀 수만 볼 수 있다. `sync` 는 실행마다 공개 글 전체를 다시 자르고
DB 와 비교한다. `embed` 가 호출 한도로 멈추면 처리한 데까지 저장되고 종료 코드 1로 끝난다.
남은 청크는 빈 채로 남아 다음 실행이 이어 간다.

- 제목 줄만 있는 청크(`## 참고 자료`처럼 각주를 빼면 비는 절)는 임베딩하지 않는다.
- 무료 한도는 입력(청크) 개수로 센다. 실제 API 로 검증할 때는 `embed --limit 1` 처럼 개수를 묶는다.
- 검색어 임베딩은 `query_cache.embed_query` 를 거친다. 같은 검색어는 공급자를 다시 부르지 않고,
  키는 검색어 원문이 아니라 해시다.
- 검색어 캐시는 만든 지 30일이 지나면 `uv run indexer cache prune` 이 지운다. 색인 워크플로가
  매 실행 끝에 돌린다.
