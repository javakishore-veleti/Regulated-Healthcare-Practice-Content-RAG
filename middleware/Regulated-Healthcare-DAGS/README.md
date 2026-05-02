# Regulated-Healthcare-DAGS

Airflow DAGs for the Project A ingest and downstream RAG workflows. This is the canonical DAG folder per CLAUDE.md and is mounted read-only at `/opt/airflow/dags` by `DevOps/Local/Airflow/docker-compose.yml`.

## Conventions

- **Functional / contextual names**, not generic technical labels. Examples: `regulated_healthcare_dataset_ingest`, `ahpra_advertising_rules_fetch`, `practice_voice_corpus_refresh`. Avoid `etl_pipeline`, `dag_001`, `daily_job`.
- **Modular, not monolithic.** Each concern (fetch / clean / chunk / embed / load) is its own DAG (or TaskGroup), so a stage can be re-run / replaced / observed independently.
- **Endpoint-driven destinations.** Every DAG that writes data must read `dag_run.conf['location_type']` and `dag_run.conf['location_config']` and dispatch accordingly. Adding a new destination type adds a new handler, not branches in every DAG.

## DAGs

| File | DAG ID | Purpose |
|---|---|---|
| `regulated_healthcare_dataset_ingest.py` | `regulated_healthcare_dataset_ingest` | Orchestrator. Dispatches by `location_type` (destination) and `dataset_type` (fetcher). |

## Per-dataset-type handlers (`handlers/`)

The `handlers/` directory holds plain Python modules that the orchestrator imports and calls — they are excluded from Airflow's DAG scan via `.airflowignore` so they never appear in the DAG list. Add a new handler module + a branch case in `dispatch_by_dataset_type` to support a new `dataset_type`.

| File | Bound `dataset_type` | Purpose |
|---|---|---|
| `handlers/ahpra_advertising_rules_fetch.py` | `regulator_guidelines` | Polite HTTP fetch of a configured URL list into `Latest_Ingest/raw/`. Default URL list is a single Wikipedia article on AHPRA while the source-URL admin UI is being built; replace with curated AHPRA / FTC / GMC URLs in a follow-up slice. |
