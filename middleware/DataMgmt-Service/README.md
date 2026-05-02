# DataMgmt-Service (middleware)

FastAPI service that owns dataset cataloging, endpoint configuration, and ingest orchestration for the Regulated Healthcare RAG stack. This is the service that the admin portal's **Administration → Data Management → Initial DataSet** screen drives.

## Layout

```
DataMgmt-Service/
  api/                FastAPI route handlers (thin); depend only on service interfaces
  service/            Business logic; expose interfaces (Protocol); concrete impls injected
  dao/                Data access; expose interfaces; concrete impls per backend (Postgres now)
  common/             Shared DTOs, settings, return codes, OTel setup, tracing decorator
  migrations/         Liquibase-style SQL changelogs per target DB
  main.py             FastAPI app factory, lifespan, router registration
  pyproject.toml      uv-managed Python deps
  run-local.sh        Host-run dev script (uv sync + uvicorn --reload)
```

## Owned tables (in the `rag_app` Postgres database)

- `endpoints` — environment-agnostic data movement destinations (`localhost`, `aws_s3`, `azure_blob`, `gcp_gcs`, `pgvector`, `aws_opensearch`, `localhost_opensearch`, …).
- `system_datasets` — catalog of datasets the RAG stack ingests (slug-form `dataset_name` + `dataset_type`).
- `system_datasets_ingest` — per-run history of a dataset ingest to a specific endpoint.

## Endpoints (HTTP)

| Method | Path         | Description |
|--------|--------------|-------------|
| GET    | `/health`    | Liveness probe |
| GET    | `/endpoints` | List all active rows from `endpoints` |
| GET    | `/datasets`  | List all rows from `system_datasets` |
| GET    | `/docs`      | Swagger UI (auto-generated from Pydantic models) |
| GET    | `/openapi.json` | OpenAPI schema |

All payloads follow the project DTO convention: the response body is a `*RespDTO` with the actual data under `respCtxData`.

## Running locally

```sh
# 1. Bring up Postgres + apply migrations
./../../DevOps/Local/docker-all-up.sh

# 2. Start the service on host
./run-local.sh
# → http://localhost:8001/docs
```

`run-local.sh` uses [uv](https://docs.astral.sh/uv/) to manage the venv. The service runs on the host (not containerized) because no cached Python image is available; adding one would violate the no-extra-pulls rule.

## Migrations

SQL changelogs live under `migrations/<db_name>/V###__<description>.sql` and are picked up automatically by `DevOps/Local/Postgres/run-migrations.sh`, which `DevOps/Local/docker-all-up.sh` invokes after Postgres is healthy. The runner sorts lexically per database and tracks applied migrations (filename + sha256) in a `_schema_migrations` table inside each target DB.
