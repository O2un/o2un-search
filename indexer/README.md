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
