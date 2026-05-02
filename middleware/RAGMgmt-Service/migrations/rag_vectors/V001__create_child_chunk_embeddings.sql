-- child_chunk_embeddings: pgvector store for parent-child chunked corpus.
-- The vector extension is already installed in this DB by Postgres init.
-- One row per (dataset_name, page_index, child_id). Embedding dim is 384 to match
-- the current stub embedder; a real model can swap in by changing the dim and
-- backfilling — that's a future migration.

CREATE TABLE child_chunk_embeddings (
    id                    BIGSERIAL    PRIMARY KEY,
    dataset_name          VARCHAR(200) NOT NULL,
    page_index            INT          NOT NULL,
    parent_id             VARCHAR(50)  NOT NULL,
    child_id              VARCHAR(80)  NOT NULL,
    parent_text           TEXT         NOT NULL,
    child_text            TEXT         NOT NULL,
    char_offset_in_parent INT          NOT NULL,
    embedding             vector(384)  NOT NULL,
    ingested_dt           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_child_chunk_embeddings_natural_key
        UNIQUE (dataset_name, page_index, child_id)
);

CREATE INDEX idx_child_chunk_dataset ON child_chunk_embeddings (dataset_name);
CREATE INDEX idx_child_chunk_dataset_page ON child_chunk_embeddings (dataset_name, page_index);

-- Cosine similarity index. ivfflat is fine for the small corpora the test rig sees;
-- HNSW or a different `lists` value can replace this in a future migration.
CREATE INDEX idx_child_chunk_embedding_cos
    ON child_chunk_embeddings
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 50);

COMMENT ON COLUMN child_chunk_embeddings.embedding IS 'pgvector embedding of child_text. Dim=384 matches the current stub embedder; a real model swap will be a separate ALTER + backfill migration.';
