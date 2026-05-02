# DataMgmt-Service (middleware)

FastAPI service that owns dataset cataloging, endpoint configuration, and ingest orchestration for the Regulated Healthcare RAG stack. This is the service that the admin portal's **Administration → Data Management → Initial DataSet** screen drives.

## Status

This slice ships **only the database schema (migrations)**. The api / service / dao / common code layers are scaffolded in a later slice.

## Owned tables (in the `rag_app` Postgres database)

- `endpoints` — environment-agnostic data movement destinations (`localhost`, `aws_s3`, `azure_blob`, `gcp_gcs`, `pgvector`, `aws_opensearch`, `localhost_opensearch`, …). See CLAUDE.md "Endpoints" section.
- `system_datasets` — catalog of datasets the RAG stack ingests (slug-form `dataset_name` + `dataset_type`).
- `system_datasets_ingest` — per-run history of a dataset ingest to a specific endpoint, including status, timestamps, and config JSON.

## Migrations

Migration changelogs live under `migrations/<db_name>/V###__<description>.sql` and are picked up automatically by `DevOps/Local/Postgres/run-migrations.sh`, which `DevOps/Local/docker-all-up.sh` invokes after Postgres is healthy. No manual migration command is required on a fresh checkout.

Filename convention: `V<seq>__<snake_case_description>.sql`. The runner sorts lexically per database and tracks applied migrations (filename + sha256) in a `_schema_migrations` table inside each target DB.
