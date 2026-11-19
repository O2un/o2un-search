"""임베딩이 빈 청크를 채운다. 블로그 레포 없이 DB 만 본다.

채울 대상: 임베딩이 비어 있는 청크(새 청크, sync 가 비운 청크), 지금 공급자와 다른 모델로
만든 청크. `embed_hash` 가 빈 청크는 건너뛴다. 제목 줄만 있는 청크(각주를 빼고 나면 비는
`## 참고 자료` 같은 절)와, 키워드로만 찾는 글 정보 청크(`sync.py`)다. 키워드 검색과 앵커에는
그대로 남는다.

한두 문장짜리 절은 뜻이 흐려 어떤 검색어와도 가깝게 잡히므로, 자기 본문 뒤에 이웃 절 본문을
붙여 임베딩한다(`contexts`). 이웃은 sync 가 정해 `context_chunk_id` 에 두고, embed 는 그 본문을
DB 에서 붙인다. 청크와 앵커는 그대로다.

호출 한도로 멈추면 처리한 데까지 저장되고, 남은 청크는 빈 채로 남아 다음 실행이 이어 간다.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol

from .chunker import HEADING_PATH_SEPARATOR
from .embedding import EmbeddingDocument, EmbeddingProvider, RateLimited

BATCH_SIZE = 20

# 제목 줄을 뺀 본문이 이 문자 수보다 짧은 청크는 이웃 절과 함께 임베딩한다.
SHORT_CHUNK_CHARS = 100
CONTEXT_SEPARATOR = "\n\n"


def embed_input(body: str, context: str | None) -> str:
    """공급자에 보내는 본문: 청크 본문, 이웃이 있으면 그 뒤에 이웃 본문."""
    return body if context is None else body + CONTEXT_SEPARATOR + context


def embed_hash(body: str, context: str | None) -> str:
    """임베딩 입력의 해시. 임베딩할 내용이 없으면(제목뿐인 청크) ''."""
    if not has_content(body):
        return ""
    return hashlib.sha256(embed_input(body, context).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Pending:
    chunk_id: str
    post_title: str
    heading_path: str
    body: str
    context: str | None  # 이웃 청크 본문(짧은 절만)
    embeddable: bool  # embed_hash 가 비지 않았다

    def document(self) -> EmbeddingDocument:
        title = self.post_title
        if self.heading_path:
            title = f"{title}{HEADING_PATH_SEPARATOR}{self.heading_path}"
        return EmbeddingDocument(title=title, text=embed_input(self.body, self.context))


def _content(body: str) -> str:
    """제목 줄을 뺀 본문."""
    first, _, rest = body.partition("\n")
    return rest if first.lstrip().startswith("#") else body


def has_content(body: str) -> bool:
    """제목 줄 하나뿐인 청크가 아니면 참이다."""
    return bool(_content(body).strip())


def content_length(body: str) -> int:
    """제목 줄을 빼고 공백을 하나로 접은 문자 수."""
    return len(" ".join(_content(body).split()))


def contexts(bodies: list[str]) -> list[int | None]:
    """글 하나의 청크 본문(문서 순서)에서 청크마다 함께 임베딩할 이웃 청크의 번호를 정한다.

    짧은 청크(`SHORT_CHUNK_CHARS` 미만)는 앞 절, 앞 절이 없으면(도입부, 도입부 없는 글의 첫 절)
    다음 절이다. 이웃을 고를 때 제목뿐인 청크는 건너뛴다. 나머지 청크는 None.
    """
    out: list[int | None] = []
    for index, body in enumerate(bodies):
        if not has_content(body) or content_length(body) >= SHORT_CHUNK_CHARS:
            out.append(None)
            continue
        before = [i for i in range(index) if has_content(bodies[i])]
        after = [i for i in range(index + 1, len(bodies)) if has_content(bodies[i])]
        out.append(before[-1] if before else after[0] if after else None)
    return out


class Store(Protocol):
    def model_id(self, name: str) -> int: ...

    def pending(self, model_id: int) -> list[Pending]: ...

    def set_embeddings(self, chunk_ids: list[str], vectors: list[list[float]], model_id: int) -> None: ...


@dataclass
class Summary:
    pending: int = 0
    skipped: int = 0
    embedded: int = 0
    requests: int = 0
    rate_limited: bool = False

    def lines(self) -> list[str]:
        out = [
            f"채울 청크 {self.pending}개 (제목뿐인 청크·글 정보 청크 {self.skipped}개 제외), "
            f"임베딩 {self.embedded}개 (요청 {self.requests}회)"
        ]
        if self.rate_limited:
            out.append(
                f"호출 한도로 중단: 남은 {self.pending - self.embedded}개는 다음 실행이 이어 간다"
            )
        return out


def run(
    store: Store, provider: EmbeddingProvider, dry_run: bool = False, limit: int | None = None
) -> Summary:
    """limit 를 주면 이번 실행에서 그 개수까지만 임베딩한다. 나머지는 빈 채로 남는다."""
    model_id = store.model_id(provider.model_id)
    candidates = store.pending(model_id)
    pending = [item for item in candidates if item.embeddable]
    summary = Summary(pending=len(pending), skipped=len(candidates) - len(pending))
    if limit is not None:
        pending = pending[:limit]
    if dry_run:
        return summary
    for start in range(0, len(pending), BATCH_SIZE):
        batch = pending[start : start + BATCH_SIZE]
        try:
            vectors = provider.embed_documents([item.document() for item in batch])
        except RateLimited:
            summary.rate_limited = True
            break
        summary.requests += 1
        store.set_embeddings([item.chunk_id for item in batch], vectors, model_id)
        summary.embedded += len(batch)
    return summary
