-- endpoints: environment-agnostic data movement destinations.
-- One row per concrete destination (a localhost path, an S3 bucket+prefix, an OpenSearch index, etc.).
-- Business logic dispatches on location_type; new destinations are added by inserting rows + adding one handler.

CREATE TABLE endpoints (
    id                    BIGSERIAL PRIMARY KEY,
    endpoint_name         VARCHAR(200) NOT NULL UNIQUE,
    category              VARCHAR(100) NOT NULL,
    location_type         VARCHAR(100) NOT NULL,
    location_config_json  JSONB        NOT NULL DEFAULT '{}'::jsonb,
    is_active             BOOLEAN      NOT NULL DEFAULT TRUE,
    created_dt            TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_dt            TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_endpoints_category_location_type ON endpoints (category, location_type);
CREATE INDEX idx_endpoints_is_active              ON endpoints (is_active);

COMMENT ON COLUMN endpoints.category             IS 'High-level grouping: initial_dataset, vector_store, audit_index, ...';
COMMENT ON COLUMN endpoints.location_type        IS 'Concrete destination kind (localhost, aws_s3, azure_blob, gcp_gcs, pgvector, aws_opensearch, localhost_opensearch, ...).';
COMMENT ON COLUMN endpoints.location_config_json IS 'Per-endpoint config (paths, bucket names, regions, credential references). Credentials themselves come from .env locally and cloud secret manager when deployed.';
