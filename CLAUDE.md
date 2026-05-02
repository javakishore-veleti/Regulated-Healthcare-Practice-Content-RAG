# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Git commit authorship

Do **not** add Claude as a co-author on commits in this repo. Omit the `Co-Authored-By: Claude ...` trailer entirely. Commits should be authored solely under the user's GitHub identity: **javakishore-veleti** (`javakishore@gmail.com`).

## Repository status

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
- **Reusable storage backend.** Every download/ingest path must go through a single shared storage abstraction that supports four destinations uniformly: **localhost filesystem**, **AWS S3**, **Azure Blob Storage**, **GCP Cloud Storage**. Implement once (e.g., `StorageBackend` interface with `LocalFsBackend`, `S3Backend`, `AzureBlobBackend`, `GcsBackend` implementations) and have every DAG and FastAPI ingest endpoint depend on the interface, not on a specific cloud SDK. The destination is selected per-ingest-run via the `system_datasets_ingest.configs_json` config; credentials follow the Deployment target rules below (`.env` locally, cloud-native key vault when deployed).
- **Localhost path layout (for `LocalFsBackend`):**
  ```
  $HOME/runtime_data/RAG_Projects/Regulated-Healthcare-RAG/DataSets/<DataSetSlug>/Latest_Ingest/
  ```
  - `$HOME` = the OS user's home directory.
  - `<DataSetSlug>` = the dataset's name normalized to contain **no spaces and no special characters** — keep `[A-Za-z0-9_]` only, drop everything else (e.g., `AHPRA Advertising Rules (AU)` → `AHPRA_Advertising_Rules_AU`). The slug must match the value persisted in `system_datasets.dataset_name`, so the same canonical form is shared between DB rows, the storage path, and admin-portal labels.
  - `Latest_Ingest/` always holds the most recent ingest's artifacts. (If historical ingests need to be preserved, decide and document the sibling-folder convention before introducing it — do not invent one silently.)
- **Localhost ingest is idempotent — short-circuit if already downloaded.** When the ingest workflow is invoked with destination = localhost and the dataset's `Latest_Ingest/` is already populated (and the prior ingest succeeded per `system_datasets_ingest`), do **not** re-download. Return success immediately so the RAG side can proceed without waiting on a no-op fetch. The check belongs in the ingest entry-point (FastAPI endpoint and/or first task of the DAG), not pushed down into individual fetchers. This rule is **localhost only** for now — S3 / Azure Blob / GCS destinations have not been specified, so do not generalize the short-circuit to them without asking. A force-refresh path (admin re-trigger that bypasses the cache hit) is anticipated but **not** implemented until the user requests it.

## Deployment target

README mentions an **AWS Architecture** section (currently empty). Assume AWS as the deployment target when making infra-shaped decisions, but confirm specifics with the user — nothing is committed yet.
