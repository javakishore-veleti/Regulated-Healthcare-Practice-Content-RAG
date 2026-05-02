-- PMC Open Access full-text dataset — distinct from `PMC_Open_Access_Subset`,
-- which only fetches the catalog / about pages. This dataset's fetcher
-- (`pmc_full_text_efetch`) pulls actual article XML via NCBI E-utilities efetch
-- so the chunker has real allied-health corpus content to index.
--
-- Operators curate the real PMCID list through the admin portal (dataset_source_urls
-- → POST /datasets/PMC_Open_Access_FullText/source-urls). Each entry is the full
-- efetch URL form:
--     https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pmc&id=<NUMERIC_PMCID>&rettype=full&retmode=xml
-- The handler's fallback pulls a single stable NCBI documentation page so the
-- pipeline can be smoke-tested without committing to a guessed PMCID list.

INSERT INTO system_datasets (dataset_name, dataset_type) VALUES
    ('PMC_Open_Access_FullText', 'pmc_fulltext')
ON CONFLICT (dataset_name) DO NOTHING;

-- One smoke source URL: NCBI's own E-utilities documentation page (HTML, very
-- stable). Replace / supplement via the admin portal with real curated efetch
-- URLs once a target PMCID list is settled.
WITH ds AS (
    SELECT id FROM system_datasets WHERE dataset_name = 'PMC_Open_Access_FullText'
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
        'https://www.ncbi.nlm.nih.gov/books/NBK25500/',
        'NCBI E-utilities Help (smoke source)',
        TRUE,
        10,
        'Stable NCBI page documenting the efetch API. Replace via the admin portal with real curated efetch URLs of the form https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pmc&id=<PMCID>&rettype=full&retmode=xml.'
    )
) AS v(url, label, is_active, position, notes)
ON CONFLICT (system_dataset_id, url) DO NOTHING;
