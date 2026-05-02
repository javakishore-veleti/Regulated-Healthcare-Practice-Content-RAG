-- Lexical retrieval leg for the hybrid search pattern. Postgres' ts_rank_cd over a
-- tsvector approximates BM25 well enough for v1; a real BM25 implementation can swap
-- in later via a future migration without changing the API surface.
--
-- Generated column keeps child_text_tsv in sync with child_text automatically — no
-- triggers, no application-side logic. GIN index makes @@ matches and ranking fast.

ALTER TABLE child_chunk_embeddings
    ADD COLUMN child_text_tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('english', child_text)) STORED;

CREATE INDEX idx_child_chunk_text_tsv
    ON child_chunk_embeddings
    USING GIN (child_text_tsv);

COMMENT ON COLUMN child_chunk_embeddings.child_text_tsv IS 'Generated tsvector over child_text (english config). Used by the lexical leg of the hybrid search pattern via @@ + ts_rank_cd.';
