-- 색인(sync)과 임베딩(embed)을 나눈다. sync 는 청크를 넣고 고치기만 하고, 본문이나 글
-- 제목이 바뀐 청크의 임베딩은 비운다. embed 가 빈 청크를 채운다. 벡터와 그 모델은 함께
-- 비거나 함께 찬다.
ALTER TABLE search.chunks
    ALTER COLUMN embedding DROP NOT NULL,
    ALTER COLUMN embed_model_id DROP NOT NULL,
    ADD CONSTRAINT chunks_embedding_with_model
        CHECK ((embedding IS NULL) = (embed_model_id IS NULL));
