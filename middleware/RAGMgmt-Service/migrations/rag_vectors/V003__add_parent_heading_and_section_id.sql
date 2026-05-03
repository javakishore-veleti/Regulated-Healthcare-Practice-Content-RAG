-- Excel Project A Task 4 ("Markdown with section IDs") + Task 11
-- ("Prompt template: cite-by-section").
--
-- Adds two NULL-able columns so existing rows survive the migration without
-- a backfill. New rows from the chunker (chunking_service.py) and the DAG
-- embed handlers carry parent_heading + section_id forward through retrieval
-- to the drafter prompt, where they enable cite-by-section formatting like
--   [Public_Regulator_Guidelines#Testimonials]
-- instead of the current `[1]`-only markers.
--
-- Existing pgvector indexes are unaffected — these are scalar columns, not
-- vector. New columns are queryable for analytics ("how many rows per
-- section?") and for filtering retrieval to a specific section_id.

ALTER TABLE child_chunk_embeddings
    ADD COLUMN IF NOT EXISTS parent_heading TEXT,
    ADD COLUMN IF NOT EXISTS section_id     TEXT;

-- Index section_id for fast section-scoped retrieval queries — operators
-- can filter to a specific section in addition to the existing dataset_name
-- filter.
CREATE INDEX IF NOT EXISTS idx_child_chunk_section
    ON child_chunk_embeddings (dataset_name, section_id);

COMMENT ON COLUMN child_chunk_embeddings.parent_heading IS
    'The most-recent markdown heading preceding this chunk in the source. '
    'NULL when the source had no headings or this chunk preceded the first '
    'heading. Surfaced in citations as the section anchor for cite-by-section drafting.';

COMMENT ON COLUMN child_chunk_embeddings.section_id IS
    'Slugified parent_heading suitable for citation anchors '
    '(e.g. "Section_133_of_the_National_Law"). NULL when parent_heading is NULL.';
