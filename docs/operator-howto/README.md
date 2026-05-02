# Operator how-to guides

Short, focused recipes for common operator tasks. Each guide walks through a single configuration change end-to-end — assumes the local stack is already up via `npm run stack:up`.

| Guide | When you'd use it |
|---|---|
| [Switching to Bedrock for drafting](./switching-to-bedrock.md) | Production deploy on AWS; you want Claude served via Bedrock instead of the direct Anthropic API. |
| [AWS OpenSearch Serverless retrieval](./aws-opensearch-retrieval.md) | Project A Excel Task 7 — flip retrieval to AOSS hybrid k-NN + BM25 instead of pgvector. |
| [Enabling the cross-encoder reranker](./enabling-cross-encoder.md) | Retrieval quality matters; you're willing to take the ~2 GB model dep cost. |
| [Enabling the real embedder](./enabling-real-embedder.md) | You want semantic embeddings instead of the SHA-256 stub — improves dense retrieval quality. |
| [Enabling Langfuse observability](./enabling-langfuse.md) | You want per-call traces of retrieval + generation + faithfulness for review. |
| [Adding a new dataset (curated URLs)](./adding-a-new-dataset.md) | A new corpus URL list or PubMed search needs to land in the catalog without a code change. |

All guides assume:
- The conda venv is provisioned (`npm run venv:install`).
- The local stack is up (`npm run stack:up`).
- You're working from the repo root.
