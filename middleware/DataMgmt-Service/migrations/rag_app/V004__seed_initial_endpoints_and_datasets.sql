-- Seed: bootstrap endpoints and the Project A dataset catalog.
-- Sourced from 1_Project_A_Healthcare_Content worksheet of RAG_Mastery_Projects.xlsx.
-- Additional endpoints/datasets are added later via the admin portal or future migrations.

-- 1. Default localhost endpoint for initial dataset downloads.
--    base_path_under_home is resolved by the handler as expanduser("~") + "/" + base_path_under_home,
--    so the actual on-disk root is $HOME/runtime_data/RAG_Projects/Regulated-Healthcare-RAG/DataSets/.
INSERT INTO endpoints (endpoint_name, category, location_type, location_config_json)
VALUES (
    'localhost_initial_dataset_default',
    'initial_dataset',
    'localhost',
    '{
        "base_path_under_home": "runtime_data/RAG_Projects/Regulated-Healthcare-RAG/DataSets",
        "latest_ingest_dirname": "Latest_Ingest"
    }'::jsonb
);

-- 2. Project A dataset catalog (5 datasets per the Excel worksheet).
INSERT INTO system_datasets (dataset_name, dataset_type) VALUES
    ('Public_Regulator_Guidelines',   'regulator_guidelines'),
    ('NCBI_PubMed',                   'pubmed'),
    ('PMC_Open_Access_Subset',        'pmc'),
    ('Kaggle_Medical_Transcriptions', 'medical_transcriptions'),
    ('Common_Crawl_Allied_Health',    'common_crawl');
