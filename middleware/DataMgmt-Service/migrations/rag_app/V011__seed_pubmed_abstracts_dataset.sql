-- PubMed Abstracts dataset — distinct from `NCBI_PubMed`, which only fetches
-- the PubMed about / catalog pages. This dataset's fetcher
-- (`pubmed_abstracts_efetch`) runs the canonical NCBI search→fetch flow:
-- esearch returns PMIDs for a curated query, efetch pulls each PMID's
-- abstract XML, so the chunker has real allied-health abstracts to index.
--
-- Operators curate the search URLs through the admin portal:
--   POST /datasets/NCBI_PubMed_Abstracts/source-urls
-- Each curated URL is an esearch URL of the form:
--   https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi
--      ?db=pubmed&term=<terms>&retmax=<N>
-- The handler caps PMIDs per query at RHC_PUBMED_MAX_PMIDS (default 10) to
-- keep ingest runs bounded.

INSERT INTO system_datasets (dataset_name, dataset_type) VALUES
    ('NCBI_PubMed_Abstracts', 'pubmed_abstracts')
ON CONFLICT (dataset_name) DO NOTHING;

-- Two starter search URLs covering common allied-health practice areas. They
-- run live against PubMed and return real review-paper PMIDs; the handler
-- then efetches each abstract. Replace / supplement via the admin portal once
-- a target search-term list is settled.
WITH ds AS (
    SELECT id FROM system_datasets WHERE dataset_name = 'NCBI_PubMed_Abstracts'
)
INSERT INTO dataset_source_urls (system_dataset_id, url, label, is_active, position, notes)
SELECT
    ds.id,
    v.url,
    v.label,
    v.is_active,
    v.position,
    v.notes
FROM ds, (VALUES
    (
        'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=physiotherapy+systematic+review&retmax=5',
        'PubMed esearch — physiotherapy systematic reviews (top 5)',
        TRUE,
        10,
        'Smoke-grade allied-health search. Replace with a curated, scope-narrowed query for production.'
    ),
    (
        'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=occupational+therapy+evidence+based+practice&retmax=5',
        'PubMed esearch — occupational therapy evidence-based practice (top 5)',
        TRUE,
        20,
        'Smoke-grade allied-health search. Replace with a curated, scope-narrowed query for production.'
    )
) AS v(url, label, is_active, position, notes)
ON CONFLICT (system_dataset_id, url) DO NOTHING;
