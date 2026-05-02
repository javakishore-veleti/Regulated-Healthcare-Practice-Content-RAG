-- Seed admin-curated source URLs for the Public_Regulator_Guidelines dataset.
-- Includes the existing Wikipedia AHPRA article (CC-BY-SA, stable, the smoke
-- source we've been using) plus several AHPRA Advertising-hub pages and the
-- FTC's health-claims advisory. URLs marked is_active = true are pulled by
-- the regulator-guidelines fetcher on the next ingest run.
--
-- Operators can add / disable / reorder rows via DataMgmt-Service /source-urls
-- endpoints (admin portal screen, slice s2.3) — no code change required.
-- 4xx/timeouts during fetch are logged per-URL in the manifest; the run as a
-- whole succeeds as long as ≥1 URL responds.

WITH ds AS (
    SELECT id FROM system_datasets WHERE dataset_name = 'Public_Regulator_Guidelines'
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
        'https://en.wikipedia.org/wiki/Australian_Health_Practitioner_Regulation_Agency',
        'Wikipedia: Australian Health Practitioner Regulation Agency',
        TRUE,
        10,
        'CC-BY-SA encyclopedia article. Stable, low-risk smoke source while curating real regulator pages.'
    ),
    (
        'https://www.ahpra.gov.au/Resources/Advertising-hub.aspx',
        'AHPRA: Advertising hub',
        TRUE,
        20,
        'Top-level AHPRA advertising guidance landing page. Verify availability before relying on this for content drafts.'
    ),
    (
        'https://www.ahpra.gov.au/Resources/Advertising-hub/Advertising-guidelines-and-other-guidance.aspx',
        'AHPRA: Advertising guidelines and other guidance',
        TRUE,
        30,
        'AHPRA advertising guidelines + supporting guidance documents. Verify availability.'
    ),
    (
        'https://www.ahpra.gov.au/Resources/Advertising-hub/Advertising-resources.aspx',
        'AHPRA: Advertising resources',
        TRUE,
        40,
        'AHPRA fact sheets and FAQs about advertising.'
    ),
    (
        'https://www.ftc.gov/business-guidance/resources/health-products-compliance-guidance',
        'FTC: Health Products Compliance Guidance',
        TRUE,
        50,
        'US FTC guidance for health product / claim advertising. Relevant for cross-jurisdictional content rules.'
    )
) AS v(url, label, is_active, position, notes)
ON CONFLICT (system_dataset_id, url) DO NOTHING;
