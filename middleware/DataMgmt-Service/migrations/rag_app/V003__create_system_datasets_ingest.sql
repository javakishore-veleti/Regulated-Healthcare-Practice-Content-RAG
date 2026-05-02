-- system_datasets_ingest: per-run history of a dataset ingest to a specific endpoint.
-- Replaces a free-form "ingested location" string with an FK to endpoints.
-- ingest_status enumerates: pending | in_progress | success | failure | skipped_cache_hit.

CREATE TABLE system_datasets_ingest (
    id                 BIGSERIAL PRIMARY KEY,
    system_dataset_id  BIGINT       NOT NULL REFERENCES system_datasets(id) ON DELETE CASCADE,
    endpoint_id        BIGINT       NOT NULL REFERENCES endpoints(id),
    ingest_start_dt    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    ingest_end_dt      TIMESTAMPTZ,
    ingest_status      VARCHAR(40)  NOT NULL DEFAULT 'pending',
    last_ingest_dt     TIMESTAMPTZ,
    configs_json       JSONB        NOT NULL DEFAULT '{}'::jsonb,
    error_text         TEXT,
    created_dt         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_dt         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_sdi_ingest_status
        CHECK (ingest_status IN ('pending', 'in_progress', 'success', 'failure', 'skipped_cache_hit'))
);

CREATE INDEX idx_sdi_dataset_endpoint ON system_datasets_ingest (system_dataset_id, endpoint_id);
CREATE INDEX idx_sdi_status            ON system_datasets_ingest (ingest_status);
CREATE INDEX idx_sdi_last_ingest_dt    ON system_datasets_ingest (last_ingest_dt DESC);

COMMENT ON COLUMN system_datasets_ingest.endpoint_id     IS 'FK to endpoints — the run-time destination chosen for this ingest (localhost / S3 / Azure Blob / GCS / ...).';
COMMENT ON COLUMN system_datasets_ingest.configs_json    IS 'Per-run overrides and metadata (e.g., AWS credential profile name used). Does NOT store secrets.';
COMMENT ON COLUMN system_datasets_ingest.ingest_status   IS 'pending | in_progress | success | failure | skipped_cache_hit (localhost cache-hit short-circuit).';
