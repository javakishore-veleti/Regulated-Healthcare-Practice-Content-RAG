-- system_datasets: catalog of datasets the RAG stack ingests.
-- dataset_name is the slug used both as the FK target and as the on-disk folder name
-- under $HOME/runtime_data/RAG_Projects/Regulated-Healthcare-RAG/DataSets/<dataset_name>/Latest_Ingest/
-- so it must contain only [A-Za-z0-9_].

CREATE TABLE system_datasets (
    id            BIGSERIAL PRIMARY KEY,
    dataset_name  VARCHAR(200) NOT NULL UNIQUE,
    dataset_type  VARCHAR(100) NOT NULL,
    created_dt    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_dt    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_system_datasets_dataset_name_slug
        CHECK (dataset_name ~ '^[A-Za-z0-9_]+$')
);

CREATE INDEX idx_system_datasets_dataset_type ON system_datasets (dataset_type);

COMMENT ON COLUMN system_datasets.dataset_name IS 'Slug; [A-Za-z0-9_] only. Must match the on-disk folder name for any localhost endpoint and is the canonical identifier in admin-portal labels.';
COMMENT ON COLUMN system_datasets.dataset_type IS 'Coarse type, e.g., regulator_guidelines, pubmed, pmc, medical_transcriptions, common_crawl.';
