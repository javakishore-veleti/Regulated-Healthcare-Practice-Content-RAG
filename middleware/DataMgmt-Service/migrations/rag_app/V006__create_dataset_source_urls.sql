-- dataset_source_urls: per-dataset, admin-managed source URL list.
-- The AHPRA / regulator-guidelines fetcher reads active URLs for a dataset from
-- this table at DAG run time, replacing the hardcoded default in handler code.
-- Also lets admins curate (add/disable/reorder) URLs without code changes.

CREATE TABLE dataset_source_urls (
    id                BIGSERIAL    PRIMARY KEY,
    system_dataset_id BIGINT       NOT NULL REFERENCES system_datasets(id) ON DELETE CASCADE,
    url               TEXT         NOT NULL,
    label             VARCHAR(300),
    is_active         BOOLEAN      NOT NULL DEFAULT TRUE,
    position          INT          NOT NULL DEFAULT 0,
    notes             TEXT,
    created_dt        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_dt        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_dataset_source_urls_dataset_url UNIQUE (system_dataset_id, url),
    CONSTRAINT chk_dataset_source_urls_url_nonempty CHECK (length(trim(url)) > 0),
    CONSTRAINT chk_dataset_source_urls_url_scheme CHECK (url ~* '^https?://')
);

CREATE INDEX idx_dataset_source_urls_dataset
    ON dataset_source_urls (system_dataset_id, is_active, position);

COMMENT ON COLUMN dataset_source_urls.position
    IS 'Stable display + fetch order. The AHPRA fetcher reads active rows ORDER BY position, id ASC.';
COMMENT ON COLUMN dataset_source_urls.label
    IS 'Human-friendly title for the URL (e.g., "AHPRA Advertising Hub"). Optional.';
