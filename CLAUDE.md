# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Git commit authorship

Do **not** add Claude as a co-author on commits in this repo. Omit the `Co-Authored-By: Claude ...` trailer entirely. Commits should be authored solely under the user's GitHub identity: **javakishore-veleti** (`javakishore@gmail.com`).

## Repository status

This repo is **scoped to a single project**: `1_Project_A_Healthcare_Content` from `../RAG_Mastery_Projects.xlsx`. Other Project worksheets in that workbook (B/C/D/E/F/G) are explicitly **out of scope** — do not pull datasets, patterns, or design language from those tabs even if they look reusable.

This repo is currently a **stub** — only `README.md`, `LICENSE`, and a Python-oriented `.gitignore` exist. There is no source code, package manifest, build system, or test suite yet. When asked to implement something, expect to be scaffolding from scratch (Python tooling implied by `.gitignore`: covers pip, uv, poetry, pdm, pytest, ruff, mypy, Streamlit, Marimo, Jupyter — none are committed to yet).

Do not invent commands, directory layouts, or modules that aren't in the repo. If a task assumes infrastructure that doesn't exist, surface that and confirm before generating it.

## Project intent (from README)

The system generates SEO/marketing content for allied-health practices in **regulated jurisdictions** — primarily AU (AHPRA advertising rules) and US (FTC health-claim rules). Regulators in these jurisdictions forbid testimonials, misleading therapeutic claims, and unverified efficacy statements, so a plain LLM is unsafe: it can produce a regulatory breach in the first paragraph.

Every generated draft must be grounded in three corpora:
1. The regulator's published advertising rules.
2. The practice's own voice corpus (tone/brand reference).
3. Open-access clinical evidence.

Every claim in output must map to a retrievable, citable source, with a guardrail layer that blocks banned phrases and forbidden-claim patterns. **Compliance is the load-bearing requirement** — when trading off retrieval recall vs. faithfulness/guardrails, prefer the latter.

## Planned RAG patterns (per README)

These are the design commitments to honor when implementing retrieval/generation:

- **Hybrid search + cross-encoder rerank** — combine lexical (e.g., BM25) and dense retrieval, then rerank.
- **Parent-child chunking** — retrieve on small child chunks, generate against larger parent chunks for context.
- **Self-RAG faithfulness loop** — generated drafts are checked for grounding against retrieved evidence and regenerated if unfaithful.
- **Output guardrails** — banned-phrase / forbidden-claim detection runs on the final output, not just upstream.

## Observability commitments (per README)

- **Primary:** Langfuse (self-hosted OSS) — captures prompt/completion, retrieved-chunk metadata, and per-turn faithfulness scores. Instrumentation that drops chunk metadata or faithfulness scores defeats the point.
- **Secondary:** OpenTelemetry GenAI semantic conventions over OTLP (Grafana Tempo / Honeycomb compatible).

## Airflow DAGs — location and naming

- **Location:** all DAG files live under `middleware/Regulated-Healthcare-DAGS/`. Do not put DAGs under `DevOps/`, under the FastAPI service code, or anywhere else.
- **Naming — prefer functional/contextual domain names over technical names.** A DAG name should read like the business outcome it produces, not like a generic pipeline label. Use this as the default and only fall back to a technical name when the DAG genuinely is a system-level concern.
  - **Prefer:** `ahpra_advertising_rules_ingest`, `practice_voice_corpus_refresh`, `clinical_evidence_open_access_pull`, `forbidden_claims_lexicon_sync`, `faithfulness_score_backfill`
  - **Avoid:** `etl_pipeline`, `data_loader`, `dag_001`, `ingest_v2`, `daily_job`
  - **Acceptable technical names** (system concerns where a domain name would be misleading): things like `metadata_db_vacuum`, `airflow_log_rotate`.
- The same rule applies to **RAG component names** in general — services, modules, classes, and endpoints should reflect their healthcare-RAG function (e.g., `RegulatorRulesRetriever`, `PracticeVoiceReranker`) rather than generic technical labels (`Service1`, `RetrieverImpl`, `Helper`). Match the project's domain language as much as possible.
- **Modular, not monolithic.** Do not write one giant DAG that fetches → cleans → chunks → embeds → loads. Split each concern into its own DAG (or a TaskGroup / sub-DAG) so individual stages can be re-run, replaced, and observed in isolation. A new dataset in the Excel should mostly mean *configuring* existing DAGs, not copy-pasting a new monolith.

## Endpoints — environment-agnostic data movement

The codebase must **not** branch on "local vs cloud" anywhere in business logic. Every data movement (download, upload, persist, audit-log) is parameterized by an **endpoint** row in the DB. "Local" is just one `location_type` among many, not a default.

**`endpoints` table (DB schema):**
- `id` (PK)
- `category` — high-level grouping. First known value: `initial_dataset`. Other categories will appear later (e.g., `vector_store`, `audit_index`).
- `location_type` — concrete destination kind. The set will grow to ~25+ types over time. Initial set includes at minimum: `localhost`, `aws_s3`, `azure_blob`, `gcp_gcs`, `pgvector`, `aws_opensearch`, `localhost_opensearch`. Add new types by inserting rows + adding one new handler implementation, not by editing every DAG/endpoint.
- `location_config_json` — per-endpoint config (paths, bucket names, regions, credential references). Credentials themselves are NOT stored here — they resolve from `.env` locally and from the cloud-native secret manager when deployed.
- standard audit columns

**API contract:** ingest / movement endpoints accept an `endpoint` reference (id or name) on the request. The service layer looks it up and dispatches by `location_type` through a single dispatch table. `system_datasets_ingest` references `endpoints` via FK — the ingested-location info is the endpoint row, not a free-form string column.

**`localhost` endpoint specifics** (one of many `location_type`s, not a default):
- Path: `$HOME/runtime_data/RAG_Projects/Regulated-Healthcare-RAG/DataSets/<DataSetSlug>/Latest_Ingest/`. Slug = `[A-Za-z0-9_]` only, must match `system_datasets.dataset_name` (e.g., `AHPRA Advertising Rules (AU)` → `AHPRA_Advertising_Rules_AU`).
- `Latest_Ingest/` holds the most recent ingest's artifacts; do not invent a historical-version sibling convention without asking.
- Idempotency: when an ingest run targets a `localhost` endpoint and `Latest_Ingest/` is already populated with a successful prior ingest (per `system_datasets_ingest`), short-circuit and return success without re-downloading. The check belongs in the ingest entry-point (FastAPI handler / first DAG task), not deep inside fetchers. This rule is `localhost`-only — do not generalize to other `location_type`s without asking. A force-refresh override is anticipated but not implemented until requested.

## Middleware architecture (FastAPI services)

Every middleware service follows the same layered structure:

```
middleware/<service-name>/
  api/        # FastAPI route handlers (thin); depend on service interfaces only
  service/    # Business logic; expose interfaces (Protocol / abc); concrete impls injected
  dao/        # Data access; expose interfaces; concrete impls per backend (Postgres, OpenSearch, ...)
  common/     # Shared constants and utils used by api/, service/, and dao/
```

Strict rules:
- `api/` depends only on `service/` interfaces — never imports DAOs or DB drivers.
- `service/` depends only on `dao/` interfaces — never imports DB drivers.
- `dao/` is the only layer that touches a DB driver. Multiple DAO implementations are normal (e.g., `PostgresPracticeVoiceDao`, `OpenSearchPracticeVoiceDao`); selection is by config / endpoint, not by code edits in `service/`.
- **OpenAPI / Swagger:** every API exposes `/docs` and `/openapi.json`. Document request/response with Pydantic models — no implicit `Any`.
- **OpenTelemetry spans:** every API handler, every service method, and every DAO method is wrapped in a span. Span names use the project's domain language (e.g., `regulator_rules.ingest`, `practice_voice.search`), not generic technical names.
- **Jaeger integration:** OTLP traces are exported from FastAPI services. In the local-dev stack, the receiver is the Jaeger service in `DevOps/Local/Observability/Jaeger/`.
- **OpenSearch audit log — feature-toggled.** When toggle `OPENSEARCH_AUDIT_ENABLED=true`, every long-lived workflow (especially ingestion) writes a **single denormalized record at completion** containing both start and end metadata (workflow id, dataset, endpoint id, start_dt, end_dt, status, error). Do not write a start-only record and a separate end record. The OpenSearch instance is itself resolved via an `endpoints` row of category `audit_index` so the same code targets localhost OpenSearch, AWS OpenSearch, or any compatible alternative.

### DTO pattern (api ↔ service ↔ dao)

Every method across `api/`, `service/`, and `dao/` follows a strict DTO contract — never loose positional/keyword arguments:

- **One `ReqDTO` in, one `RespDTO` out-param, an `int` return code.** Method signatures look like:
  ```python
  def ingest_dataset(req: IngestDataSetReqDTO, resp: IngestDataSetRespDTO) -> int: ...
  ```
  The integer return is a status/return code (e.g., `RC_OK = 0`, non-zero for known error categories). The actual payload to be sent back to the API caller is populated into `resp`, not returned.
- **Naming:** DTOs are **contextual, not generic** — `IngestDataSetReqDTO` / `IngestDataSetRespDTO`, `SearchPracticeVoiceReqDTO` / `SearchPracticeVoiceRespDTO`. Never `RequestDTO`, `BaseRequest`, `Req`, etc.
- **`RespDTO.respCtxData: dict[str, Any]`** is the canonical place where the response payload lives. The api layer serializes `resp.respCtxData` (or the whole `RespDTO`, with `respCtxData` as the body) when returning to the HTTP caller. Service and DAO layers populate `respCtxData` directly — they do not return parallel data structures alongside it.
- **Pydantic** for the DTO classes so OpenAPI/Swagger schemas are auto-generated correctly. `respCtxData` is typed (`dict[str, Any]` or a more specific schema when feasible) — never untyped.
- **No bypass:** even one-arg methods take their `ReqDTO` (containing that one field). This keeps every layer's signature shape uniform and makes adding fields a non-breaking change.

## Database schema management

Use a **Liquibase-style migration** approach (Liquibase itself or a Python equivalent — confirm at implementation time). Migration changelogs live in version control alongside the relevant middleware service. **Migrations run automatically as part of `DevOps/Local/docker-all-up.sh`** so any fresh local checkout produces a fully migrated DB without manual steps.

## Local stack lifecycle

`DevOps/Local/docker-all-down.sh` **removes named volumes by default** so a `down` followed by `up` produces a clean DB. This is destructive — pass `--keep-volumes` when data preservation is needed.

## Deployment target

README mentions an **AWS Architecture** section (currently empty). Assume AWS as the deployment target when making infra-shaped decisions, but confirm specifics with the user — nothing is committed yet. **Do not bake "local" assumptions into business logic** (Airflow executor choice, file paths, storage SDKs, OpenSearch hostnames, etc.) — those are environment concerns and belong behind the endpoint abstraction or behind environment-specific config, never hard-coded.

## Deployment portability (k8s on AWS / Azure / GCP and other containerized targets)

Every artifact in this repo must run unchanged in any of: AWS EKS, Azure AKS, GCP GKE, or another containerized target. The same image / build, just with different config. Hard rules:

- **No hardcoded host URLs anywhere in code.** All external service URLs (FastAPI base, Airflow API, Airflow UI, OpenSearch, vector DBs, …) come from env vars (Python services), `pydantic-settings`, or Angular environment files / runtime-config endpoints (`/api/config`). The string `localhost` is acceptable **only** as a `location_type` value in the endpoint abstraction or as a dev-time default that an env var overrides.
- **Filesystem paths are not portable across environments.** The `localhost` `location_type` is dev-mode by design; production deploys ingest into cloud-native endpoints (`aws_s3`, `azure_blob`, `gcp_gcs`, etc.). If a `localhost` endpoint is needed in k8s for some reason, it must be backed by a PersistentVolume mounted at the resolved path; never assume the pod's writable filesystem is durable.
- **Credentials never live in image or repo.** `.env` is for local dev only; in cloud k8s, secrets come from AWS Secrets Manager / Azure Key Vault / GCP Secret Manager, mounted as env vars or projected files. Code reads via the same `pydantic-settings` interface either way.
- **Run as non-root.** Container images already do (`AIRFLOW_UID=50000`, FastAPI inherits the base image's non-root user); do not regress.
- **Health endpoints are k8s-shaped.** Every service exposes `/health` (already in DataMgmt-Service) returning a small JSON payload — readiness / liveness probes hit it. Don't put expensive checks in liveness.
- **The admin portal is a static SPA.** It is served by an ingress / CDN in production, not by `ng serve`. Any URL the portal needs (API base, Airflow UI base, …) comes from a runtime config; do not hardcode.
- **DAGs must be content-addressed by file path import**, not by Python package import on `sys.path`, since the Airflow image's task subprocess does not get arbitrary paths added (the existing `regulated_healthcare_dataset_ingest.py` uses `importlib.util.spec_from_file_location`; follow that pattern when adding new handlers).
- **Stateless services scale horizontally.** No in-process caches that diverge across replicas. Use the DB or a shared cache.
- **Configuration discovery order** (in services): explicit env var → mounted secret file → cloud secret manager (resolved by an SDK) → safe local default. Never the other way around.
