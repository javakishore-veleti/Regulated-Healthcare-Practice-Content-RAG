-- Expand curated source URLs: more AHPRA advertising guidance, more
-- PubMed esearch URLs covering wider allied-health disciplines.
--
-- Operators using the admin portal can disable / reorder / add to these via
-- /datasets/{name}/source-urls — this migration just makes the out-of-the-box
-- experience cover more practice areas without manual curation.

-- ── More AHPRA / regulator URLs ─────────────────────────────────────────
WITH ds AS (
    SELECT id FROM system_datasets WHERE dataset_name = 'Public_Regulator_Guidelines'
)
INSERT INTO dataset_source_urls (system_dataset_id, url, label, is_active, position, notes)
SELECT
    ds.id, v.url, v.label, v.is_active, v.position, v.notes
FROM ds, (VALUES
    (
        'https://www.ahpra.gov.au/Resources/Advertising-hub/Advertising-resources/Social-media-how-to-meet-your-obligations.aspx',
        'AHPRA: Social media — how to meet your obligations',
        TRUE,
        60,
        'AHPRA''s page specifically on social-media advertising obligations. Verify availability before each ingest run.'
    ),
    (
        'https://www.ahpra.gov.au/Resources/Advertising-hub/Advertising-resources/Testimonials-tool.aspx',
        'AHPRA: Testimonials tool',
        TRUE,
        70,
        'AHPRA testimonials decision-tool page — directly relevant to the most-violated content rule.'
    )
) AS v(url, label, is_active, position, notes)
ON CONFLICT (system_dataset_id, url) DO NOTHING;


-- ── More PubMed esearch URLs (allied-health disciplines) ───────────────
WITH ds AS (
    SELECT id FROM system_datasets WHERE dataset_name = 'NCBI_PubMed_Abstracts'
)
INSERT INTO dataset_source_urls (system_dataset_id, url, label, is_active, position, notes)
SELECT
    ds.id, v.url, v.label, v.is_active, v.position, v.notes
FROM ds, (VALUES
    (
        'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=speech+pathology+systematic+review&retmax=5',
        'PubMed esearch — speech pathology systematic reviews (top 5)',
        TRUE,
        30,
        'Speech pathology / SLT scope — common allied-health discipline beyond physio + OT.'
    ),
    (
        'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=exercise+physiology+chronic+disease&retmax=5',
        'PubMed esearch — exercise physiology + chronic disease (top 5)',
        TRUE,
        40,
        'Accredited exercise physiologist scope — chronic disease management is a high-volume content area.'
    ),
    (
        'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=dietetics+evidence+based+practice&retmax=5',
        'PubMed esearch — dietetics + evidence-based practice (top 5)',
        TRUE,
        50,
        'Dietitian scope — practice voice + evidence often diverge here, useful for compliance testing.'
    ),
    (
        'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=podiatry+diabetic+foot+systematic+review&retmax=5',
        'PubMed esearch — podiatry + diabetic foot reviews (top 5)',
        TRUE,
        60,
        'Podiatrist scope — diabetic foot is a regulator-watched content area.'
    )
) AS v(url, label, is_active, position, notes)
ON CONFLICT (system_dataset_id, url) DO NOTHING;
