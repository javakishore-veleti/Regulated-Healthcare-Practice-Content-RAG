# Regulated-Healthcare-DAGS

Airflow DAGs for the Project A ingest and downstream RAG workflows. This is the canonical DAG folder per CLAUDE.md and is mounted read-only at `/opt/airflow/dags` by `DevOps/Local/Airflow/docker-compose.yml`.

## Conventions

- **Functional / contextual names**, not generic technical labels. Examples: `regulated_healthcare_dataset_ingest`, `ahpra_advertising_rules_fetch`, `practice_voice_corpus_refresh`. Avoid `etl_pipeline`, `dag_001`, `daily_job`.
- **Modular, not monolithic.** Each concern (fetch / clean / chunk / embed / load) is its own DAG (or TaskGroup), so a stage can be re-run / replaced / observed independently.
- **Endpoint-driven destinations.** Every DAG that writes data must read `dag_run.conf['location_type']` and `dag_run.conf['location_config']` and dispatch accordingly. Adding a new destination type adds a new handler, not branches in every DAG.

## DAGs

| File | DAG ID | Purpose |
|---|---|---|
| `regulated_healthcare_dataset_ingest.py` | `regulated_healthcare_dataset_ingest` | Generic ingest entry point. Receives dataset/endpoint context via `dag_run.conf`, dispatches by `location_type`. Currently the localhost handler writes a manifest stub; per-dataset fetchers (AHPRA scraper, PubMed download, etc.) replace the stub slice by slice. |
