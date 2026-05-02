-- Seed admin-curated source URLs for the four non-regulator-guidelines Project A
-- datasets. These point at dataset-documentation / landing pages rather than the
-- multi-GB corpora themselves; full-corpus ingestion is per-dataset-specific
-- (HuggingFace `datasets`, NCBI E-utilities, Kaggle API, Common Crawl WARC) and
-- lands in follow-up slices. Source: 1_Project_A_Healthcare_Content rows 49-52.

WITH ds AS (
    SELECT id, dataset_name FROM system_datasets
    WHERE dataset_name IN (
        'NCBI_PubMed',
        'PMC_Open_Access_Subset',
        'Kaggle_Medical_Transcriptions',
        'Common_Crawl_Allied_Health'
    )
)
INSERT INTO dataset_source_urls (system_dataset_id, url, label, is_active, position, notes)
SELECT ds.id, v.url, v.label, v.is_active, v.position, v.notes
FROM ds
JOIN (VALUES
    -- NCBI_PubMed
    (
        'NCBI_PubMed',
        'https://huggingface.co/datasets/ncbi/pubmed',
        'HuggingFace: ncbi/pubmed dataset card',
        TRUE,
        10,
        'Primary documentation for the PubMed corpus on HuggingFace. Real ~6 GB MSK-filtered ingest is a separate slice using the HF datasets library.'
    ),
    (
        'NCBI_PubMed',
        'https://pubmed.ncbi.nlm.nih.gov/about/',
        'NCBI: About PubMed',
        TRUE,
        20,
        'NCBI''s authoritative description of PubMed coverage, indexing policies, and licensing.'
    ),

    -- PMC_Open_Access_Subset
    (
        'PMC_Open_Access_Subset',
        'https://pmc.ncbi.nlm.nih.gov/about/',
        'NCBI: About PubMed Central',
        TRUE,
        10,
        'PMC overview + licensing scope. Real ~5 GB OA sample ingest comes via PMC OAI-PMH or pre-built tarballs.'
    ),
    (
        'PMC_Open_Access_Subset',
        'https://www.ncbi.nlm.nih.gov/pmc/tools/openftlist/',
        'NCBI: PMC Open Access full-text list',
        TRUE,
        20,
        'The canonical index of PMC Open Access full-text articles.'
    ),

    -- Kaggle_Medical_Transcriptions
    (
        'Kaggle_Medical_Transcriptions',
        'https://www.kaggle.com/datasets/tboyle10/medicaltranscriptions',
        'Kaggle: tboyle10 / medicaltranscriptions',
        TRUE,
        10,
        'Public landing page (no auth needed). Pulling the actual ~1 GB CSV requires KAGGLE_USERNAME/KAGGLE_KEY auth and explicit T&C accept; that path is opt-in via a future slice.'
    ),

    -- Common_Crawl_Allied_Health
    (
        'Common_Crawl_Allied_Health',
        'https://commoncrawl.org/get-started',
        'Common Crawl: Get started',
        TRUE,
        10,
        'Common Crawl''s onboarding doc — explains the WARC archive structure and access patterns.'
    ),
    (
        'Common_Crawl_Allied_Health',
        'https://commoncrawl.org/the-data/',
        'Common Crawl: The data',
        TRUE,
        20,
        'Index of Common Crawl monthly archives. The allied-health-domain filter is a downstream slice.'
    )
) AS v(dataset_name, url, label, is_active, position, notes)
ON ds.dataset_name = v.dataset_name
ON CONFLICT (system_dataset_id, url) DO NOTHING;
