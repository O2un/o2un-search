"""Gemini 임베딩 어댑터 (`gemini-embedding-2`).

- `task_type` 을 받지 않는 모델이라 문서와 검색어를 입력 접두어로 구분한다. 형식은 여기에만 둔다.
- 여러 입력을 한 목록으로 보내면 합쳐진 벡터 하나가 돌아오므로, 입력마다 `Content` 로 감싼다.
- 768 차원처럼 줄인 출력은 공급자가 정규화해서 돌려준다.
- 호출 한도(429)에 걸리면 응답이 알려 준 시간만큼 기다렸다 다시 시도하고, 그래도 막히면
  `RateLimited` 를 낸다. 검색 경로는 `max_attempts=1` 로 기다리지 않는다.
- `timeout_s` 를 주면 HTTP 요청 하나가 그 시간을 넘길 때 실패한다.
"""

from __future__ import annotations

import re
import sys
import time

from google import genai
from google.genai import errors, types

from .embedding import EmbeddingDocument, RateLimited

MODEL = "gemini-embedding-2"
MAX_ATTEMPTS = 4
DEFAULT_WAIT_SECONDS = 30.0
MAX_WAIT_SECONDS = 90.0

_RETRY_DELAY = re.compile(r"'retryDelay':\s*'(\d+(?:\.\d+)?)s'")


def _retry_delay(error: errors.APIError) -> float:
    match = _RETRY_DELAY.search(str(error.details))
    seconds = float(match.group(1)) if match else DEFAULT_WAIT_SECONDS
    return min(seconds + 1, MAX_WAIT_SECONDS)


class GeminiEmbedding:
    model_id = f"gemini/{MODEL}"

    def __init__(
        self, api_key: str, dim: int, *, max_attempts: int = MAX_ATTEMPTS, timeout_s: float | None = None
    ) -> None:
        self.dim = dim
        self.max_attempts = max_attempts
        # HttpOptions.timeout 은 밀리초이고, 0 은 "상한 없음"이라 1 이상으로 둔다.
        http_options = types.HttpOptions(timeout=max(1, int(timeout_s * 1000))) if timeout_s is not None else None
        self._client = genai.Client(api_key=api_key, http_options=http_options)

    def _embed(self, texts: list[str]) -> list[list[float]]:
        contents = [types.Content(parts=[types.Part.from_text(text=text)]) for text in texts]
        config = types.EmbedContentConfig(output_dimensionality=self.dim)
        for attempt in range(1, self.max_attempts + 1):
            try:
                result = self._client.models.embed_content(
                    model=MODEL, contents=contents, config=config
                )
            except errors.APIError as error:
                if error.code != 429:
                    raise
                if attempt == self.max_attempts:
                    raise RateLimited(str(error)) from error
                wait = _retry_delay(error)
                print(f"호출 한도(429): {wait:.0f}초 기다렸다 다시 시도 ({attempt}/{self.max_attempts - 1})", file=sys.stderr)
                time.sleep(wait)
                continue
            vectors = [list(item.values or []) for item in result.embeddings or []]
            if len(vectors) != len(texts) or any(len(v) != self.dim for v in vectors):
                raise RuntimeError(
                    f"임베딩 응답 모양이 다르다: 입력 {len(texts)}개, 벡터 {len(vectors)}개"
                )
            return vectors
        raise AssertionError("unreachable")

    def embed_documents(self, documents: list[EmbeddingDocument]) -> list[list[float]]:
        return self._embed([f"title: {doc.title} | text: {doc.text}" for doc in documents])

    def embed_query(self, query: str) -> list[float]:
        return self._embed([f"task: search result | query: {query}"])[0]
