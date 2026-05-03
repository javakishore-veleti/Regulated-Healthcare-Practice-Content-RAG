-- PubMed MeSH-filtered esearch URLs — Excel Project A Task 5.
--
-- Excel Task 5 names "Pull PubMed MSK subset; filter by MeSH terms" with the
-- ≥1.5M abstracts acceptance bar. The MSK (musculoskeletal) scope was named
-- explicitly in the README and the project's dataset notes.
--
-- The PubMed esearch API supports MeSH-qualified terms via the `[mh]`
-- qualifier — `term=Musculoskeletal+Diseases[mh]` returns ALL articles
-- indexed under that MeSH heading and its descendants (MeSH is hierarchical).
-- This is the load-bearing difference between a free-text physiotherapy
-- search (which returns abstracts where "physiotherapy" appears anywhere)
-- and a MeSH-filtered search (which returns abstracts MEDLINE catalogued as
-- being about that subject).
--
-- The existing `pubmed_abstracts_efetch_fetch.py` handler already supports
-- any esearch URL — this migration just adds the MeSH-qualified ones.
-- Operators tuning for production scale would crank up `retmax` and add
-- pagination via `retstart`; the seeded `retmax=10` is for smoke / first-run.

WITH ds AS (
    SELECT id FROM system_datasets WHERE dataset_name = 'NCBI_PubMed_Abstracts'
)
INSERT INTO dataset_source_urls (system_dataset_id, url, label, is_active, position, notes)
SELECT
    ds.id, v.url, v.label, v.is_active, v.position, v.notes
FROM ds, (VALUES
    -- Top-level MSK MeSH heading — covers all musculoskeletal disease descendants.
    (
        'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=Musculoskeletal+Diseases%5Bmh%5D&retmax=10',
        'PubMed esearch — Musculoskeletal Diseases [mh] (MeSH-filtered, top 10)',
        TRUE,
        100,
        'MeSH-qualified MSK scope — Excel Task 5 acceptance criterion. Crank retmax + add retstart pagination for production scale.'
    ),
    -- Chronic pain — explicitly called out in the project README.
    (
        'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=Chronic+Pain%5Bmh%5D&retmax=10',
        'PubMed esearch — Chronic Pain [mh] (MeSH-filtered, top 10)',
        TRUE,
        110,
        'Chronic pain MeSH heading — relevant to allied-health practice voice scope.'
    ),
    -- Physical therapy modalities — central to allied-health practice.
    (
        'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=Physical+Therapy+Modalities%5Bmh%5D&retmax=10',
        'PubMed esearch — Physical Therapy Modalities [mh] (MeSH-filtered, top 10)',
        TRUE,
        120,
        'Physiotherapy modalities MeSH heading.'
    ),
    -- Manual therapy / spinal manipulation — relevant for chiropractic + osteopathic.
    (
        'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=Musculoskeletal+Manipulations%5Bmh%5D&retmax=10',
        'PubMed esearch — Musculoskeletal Manipulations [mh] (MeSH-filtered, top 10)',
        TRUE,
        130,
        'Manual / spinal manipulation MeSH heading — chiro + osteo allied-health scope.'
    ),
    -- Joint diseases — separate descendant of Musculoskeletal Diseases worth its own search.
    (
        'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=Joint+Diseases%5Bmh%5D&retmax=10',
        'PubMed esearch — Joint Diseases [mh] (MeSH-filtered, top 10)',
        TRUE,
        140,
        'Joint diseases MeSH heading — high-volume content area for podiatry, physio, OT.'
    )
) AS v(url, label, is_active, position, notes)
ON CONFLICT (system_dataset_id, url) DO NOTHING;
