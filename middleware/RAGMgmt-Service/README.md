# RAGMgmt-Service (middleware)

Second FastAPI service, paired with `DataMgmt-Service`. Owns the RAG management surfaces — pattern catalog, chunking, embedding, retrieval, and generation — that drive the **RAG Management** section of the admin portal and the **Generate** screen of the customer portal.

## Layout

Same layered structure as `DataMgmt-Service`:

```
RAGMgmt-Service/
  api/        FastAPI route handlers (thin); depend only on service interfaces
  service/    Business logic; expose interfaces; concrete impls injected
  dao/        Data access; interfaces + per-backend implementations
  common/     Shared DTOs, settings, return codes, OTel setup, tracing decorator
  migrations/ Liquibase-style SQL changelogs per target DB
  main.py     FastAPI app factory, lifespan, router registration
  pyproject.toml
  run-local.sh
```

## Owned tables (in `rag_app`)

- `rag_patterns` — catalog of Project A's RAG patterns (Hybrid+Rerank, Parent-Child Chunking, Self-RAG, Output Guardrails). Migrations under `migrations/rag_app/`. Filename versions start at `V001__` per service; the migration runner key includes the full file path so DataMgmt-Service's `V001` and RAGMgmt-Service's `V001` coexist without collision.

## Endpoints (planned)

| Method | Path | Status | Purpose |
|---|---|---|---|
| GET | `/health` | live | Liveness probe |
| GET | `/patterns` | next slice | List the four Project A RAG patterns |
| POST | `/chunk` | future | Chunking surface (parent-child) |
| POST | `/retrieve` | future | Hybrid retrieval + rerank |
| POST | `/generate` | future | Self-RAG faithfulness loop + guardrails |

## Running

```sh
./../../DevOps/Local/docker-all-up.sh           # Postgres + Airflow (shared infra)
./run-local.sh                                  # → http://localhost:8002/docs
```

Default port is `8002` (DataMgmt-Service uses `8001`).
