# Design diagrams

Multi-tab `architecture-diagrams.drawio` covering every load-bearing piece of the system.

## How to view

- **Web (no install)** — open https://app.diagrams.net/, then File → Open from device → pick `architecture-diagrams.drawio`. Tabs appear along the bottom.
- **VS Code** — install the *Draw.io Integration* extension; double-click the file in the explorer.
- **Desktop app** — the cross-platform draw.io desktop app at https://github.com/jgraph/drawio-desktop opens it directly.

## Tabs

| # | Tab | What it covers |
|---|---|---|
| 1 | **System (Local Dev)** | The full local stack — Angular portals, FastAPI services, Postgres + pgvector, Airflow, optional Langfuse. Path-routed `/api/*` proxy. The shape an operator sees on `npm run stack:up`. |
| 2 | **Three-corpora retrieval** | `POST /retrieve/three-corpora` — query fans out across regulator + clinical evidence + practice voice; each runs hybrid (BM25 + dense) with RRF fusion + reranker; merged response with `corpora_present` / `corpora_missing`. |
| 3 | **Generation pipeline** | `POST /generate` end-to-end: three-corpora retrieval → reranker → drafter → faithfulness scorer → regenerate loop → guardrails → response, with Langfuse trace fan-out. The Self-RAG decision diamond is explicit. |
| 4 | **AWS Production** | Excel Project A AWS architecture row mapping. ALB → ECS Fargate (DataMgmt + RAGMgmt) → Bedrock + AOSS + RDS + S3 + Langfuse-on-ECS. Each cell pairs with the Excel's named service. |
| 5 | **Ingestion DAG** | `regulated_healthcare_dataset_ingest` task graph + dispatch tables: `_FETCHER_REGISTRY` (dataset_type → handler) and `RHC_DAG_VECTOR_STORE` (corpus index target). |
| 6 | **Plugin / Factory architecture** | Every load-bearing Protocol (`IDrafter`, `IEmbedder`, `IReranker`, `IRetrievalDao`, `IGuardrailsService`) and its concrete implementations, color-coded by dep type. The `rag_iface --cloud` preset that flips them all together. |

## Editing

The file is plain XML — round-trips cleanly through git. PRs that add/move shapes show meaningful diffs. To reshape:

1. Open in any of the viewers above.
2. Edit shapes / arrows / colors.
3. File → Save (web app prompts to download the updated XML; replace this file in-tree).
4. Commit. The diff is line-oriented because each shape is a separate `<mxCell>`.

## Color conventions

| Color | Meaning |
|---|---|
| Cyan blue (`#dae8fc`) | Frontend / API entrypoint |
| Green (`#d5e8d4`) | FastAPI service / pure-stdlib component |
| Yellow (`#fff2cc`) | Storage / data store |
| Orange (`#ffe6cc`) | Workflow / orchestration |
| Purple (`#e1d5e7`) | LLM provider (Anthropic) |
| AWS orange (`#FF9900`) | AWS managed service |
| AWS green (`#3F8624`) | AWS data / model service |
| AWS purple (`#7F2BC4`) | AWS observability / security |
| Pink dashed (`#f8cecc`) | Optional / opt-in component |
| Dark teal (`#08434a`) | Interface / Protocol header |
