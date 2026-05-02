# Adding a new dataset (curated URLs)

The catalog ships with seven datasets across three corpora. This guide walks through adding an eighth.

There are two scopes of "new dataset":

- **(A) Same dataset_type as an existing one** — e.g. another regulator's URL list. No code change; just rows in the `dataset_source_urls` admin table.
- **(B) New dataset_type with custom fetch logic** — e.g. a different OAI-PMH or RSS source. Needs a handler module and a registry entry.

This guide covers (A) end-to-end and points at the (B) extension points.

## Prerequisites

- Local stack up (`npm run stack:up`).
- Admin portal at http://localhost:4200.

---

## Scope A — same dataset_type

### 1. Pick a corpus and dataset_type

Look at `middleware/RAGMgmt-Service/common/corpus_types.py` — the existing dataset_names → corpus_type map. Reuse a `dataset_type` (regulator_guidelines, pubmed_abstracts, pmc_fulltext, etc.) so the existing fetcher handles it.

Naming rule per `CLAUDE.md`: dataset_name stays in `[A-Za-z0-9_]` (the localhost storage handler builds a path slug from it).

### 2. Insert the dataset row

Two paths.

**(2a) Migration (preferred for production-curated datasets):**

Add `middleware/DataMgmt-Service/migrations/rag_app/V0NN__seed_<your_dataset>.sql`:

```sql
INSERT INTO system_datasets (dataset_name, dataset_type) VALUES
    ('US_FTC_Health_Claim_Bulletins', 'regulator_guidelines')
ON CONFLICT (dataset_name) DO NOTHING;

WITH ds AS (
    SELECT id FROM system_datasets WHERE dataset_name = 'US_FTC_Health_Claim_Bulletins'
)
INSERT INTO dataset_source_urls (system_dataset_id, url, label, is_active, position, notes)
SELECT
    ds.id, v.url, v.label, v.is_active, v.position, v.notes
FROM ds, (VALUES
    (
        'https://www.ftc.gov/business-guidance/blog/category/health-products-claims',
        'FTC: Health Products Claims blog',
        TRUE,
        10,
        'Quarterly enforcement updates from the FTC bureau handling health-product advertising claims.'
    )
) AS v(url, label, is_active, position, notes)
ON CONFLICT (system_dataset_id, url) DO NOTHING;
```

Re-run migrations:

```sh
DevOps/Local/Postgres/run-migrations.sh
```

**(2b) Admin portal (for one-off curation):**

- Administration → Data Management → Source URLs → select the existing dataset that already has the type you want
- Click **Add URL**, enter URL + label + notes
- Toggle active

This adds rows to `dataset_source_urls` only. It doesn't create a new `system_datasets` row — for a brand-new dataset_name, use (2a).

### 3. Update the corpus taxonomy (Python + both portals)

Three places must stay aligned with the seeded `system_datasets`:

```python
# middleware/RAGMgmt-Service/common/corpus_types.py
DATASET_NAME_TO_CORPUS_TYPE: dict[str, str] = {
    ...
    "US_FTC_Health_Claim_Bulletins": REGULATOR,    # ← new entry
    ...
}
```

```ts
// portals/admin/src/app/core/corpus-types.ts
const DATASET_NAME_TO_CORPUS_TYPE: Record<string, CorpusType> = {
  ...
  US_FTC_Health_Claim_Bulletins: 'regulator',     // ← new entry
  ...
};

// portals/customer/src/app/core/corpus-types.ts — same entry
```

The Python-side test `test_seeded_datasets_present` will fail if you forget the Python entry. The two TypeScript copies aren't covered by automated tests (yet) — verify by clicking around the Initial DataSet + Catalog screens and seeing the expected chip color.

### 4. Trigger an ingest run

Admin portal → Initial DataSet → tab for the new dataset → pick endpoint → Run ingest.

Or from CLI:

```sh
curl -X POST http://localhost:8001/ingest \
  -H 'Content-Type: application/json' \
  -d '{
    "dataset_name": "US_FTC_Health_Claim_Bulletins",
    "endpoint_name": "localhost_initial_dataset_default"
  }'
```

The ingest DAG runs the registered fetcher for the dataset_type, chunks via RAGMgmt-Service `/chunk`, and embeds into `child_chunk_embeddings`.

### 5. Verify

- Admin portal → **Initial DataSet** → your dataset should now have a status row showing "success".
- Customer portal → **Catalog** → the dataset card with the right corpus chip should appear.
- Customer portal → **Generate** → call /generate with a topic the new corpus would cover. `respCtxData.retrieval_meta.corpora_present` should include the corpus your dataset belongs to.

---

## Scope B — new dataset_type

Two extra steps on top of Scope A:

### B1. Write a handler

Add `middleware/Regulated-Healthcare-DAGS/handlers/<your>_fetch.py`. Two existing patterns:

- **URL-list fetcher** — see `pmc_open_access_fetch.py` or `ahpra_advertising_rules_fetch.py`. Thin wrapper over `_url_list_fetcher.fetch_url_list(...)`. Free retries, polite spacing, manifest output. Use this for any "GET a list of URLs and save raw bytes" source.
- **Search-then-fetch** — see `pubmed_abstracts_efetch_fetch.py`. Two-phase: a curated search URL returns a list of IDs, then per-ID GETs return content. Use this for E-utilities-shaped sources.

### B2. Register the dataset_type

In `middleware/Regulated-Healthcare-DAGS/regulated_healthcare_dataset_ingest.py`:

```python
_FETCHER_REGISTRY: dict[str, tuple[str, str]] = {
    ...
    "your_new_type": ("your_fetch.py", "fetch_function_name"),
}
```

Then steps 1–5 of Scope A apply.

## Related

- [`middleware/Regulated-Healthcare-DAGS/regulated_healthcare_dataset_ingest.py`](../../middleware/Regulated-Healthcare-DAGS/regulated_healthcare_dataset_ingest.py) — the orchestrator + handler registry
- [`middleware/Regulated-Healthcare-DAGS/handlers/_url_list_fetcher.py`](../../middleware/Regulated-Healthcare-DAGS/handlers/_url_list_fetcher.py) — shared retry / rate-limit / manifest helper
- [`middleware/RAGMgmt-Service/common/corpus_types.py`](../../middleware/RAGMgmt-Service/common/corpus_types.py) — backend taxonomy source of truth
