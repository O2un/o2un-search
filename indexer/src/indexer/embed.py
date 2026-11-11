"""임베딩이 빈 청크를 채운다. 블로그 레포 없이 DB 만 본다.

채울 대상: 임베딩이 비어 있는 청크(새 청크, sync 가 비운 청크), 지금 공급자와 다른 모델로
만든 청크. 제목 줄만 있는 청크(각주를 빼고 나면 비는 `## 참고 자료` 같은 절)는 임베딩할
내용이 없어 건너뛴다. 키워드 검색과 앵커에는 그대로 남는다.

호출 한도로 멈추면 처리한 데까지 저장되고, 남은 청크는 빈 채로 남아 다음 실행이 이어 간다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .chunker import HEADING_PATH_SEPARATOR
from .embedding import EmbeddingDocument, EmbeddingProvider, RateLimited

BATCH_SIZE = 20


@dataclass(frozen=True)
class Pending:
    chunk_id: str
    post_title: str
    heading_path: str
    body: str

    def document(self) -> EmbeddingDocument:
        title = self.post_title
        if self.heading_path:
            title = f"{title}{HEADING_PATH_SEPARATOR}{self.heading_path}"
        return EmbeddingDocument(title=title, text=self.body)


def has_content(body: str) -> bool:
    """제목 줄 하나뿐인 청크가 아니면 참이다."""
    first, _, rest = body.partition("\n")
    return bool(rest.strip()) or not first.lstrip().startswith("#")


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
            f"채울 청크 {self.pending}개 (제목뿐인 청크 {self.skipped}개 제외), "
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
    pending = [item for item in candidates if has_content(item.body)]
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
