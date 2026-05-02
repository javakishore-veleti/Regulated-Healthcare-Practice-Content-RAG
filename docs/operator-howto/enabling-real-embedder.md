# Enabling the real embedder

The default `RAG_EMBEDDER_BACKEND=stub` uses a SHA-256 hash cascade. It's deterministic and dep-free but **not semantically meaningful** — two paragraphs about completely different things can score similarly. The real embedder (default `sentence-transformers/all-MiniLM-L6-v2`) gives real semantic embeddings.

## When to use this

- Dense retrieval quality matters (BM25 alone misses semantic paraphrases).
- You're willing to take the dep cost: ~2 GB transitive (shared with the cross-encoder reranker if you have that installed too).
- You can afford to **re-embed the entire corpus** — switching the query embedder without re-embedding the corpus produces meaningless cosine similarity.

⚠ **Critical: this is a two-side switch.** The query embedder lives in RAGMgmt-Service; the corpus embedder lives in the Airflow DAG handler `embed_via_pgvector.py`. Both must use the same model AND the corpus must be re-ingested before the switch takes effect.

## Prerequisites

- Conda venv provisioned with the optional dep.
- The `child_chunk_embeddings` table is set to dim=384 (the default model's output dim — same as the stub, so no migration needed).
- All datasets you care about can be re-ingested (the existing corpus will be stale).

## Steps

### 1. Install the optional dep

```sh
cd middleware/RAGMgmt-Service
pip install '.[real-embedder]'
```

(`real-embedder` and `cross-encoder-rerank` share the same `sentence-transformers` dep — installing one effectively installs the other's heavy parts. You can install both with `pip install '.[real-embedder,cross-encoder-rerank]'`.)

### 2. Update the DAG-side embedder

Edit `middleware/Regulated-Healthcare-DAGS/handlers/embed_via_pgvector.py` to call `sentence_transformers` instead of the inline `_stub_embed`. The function signature stays the same — the chunker writes to `child_chunk_embeddings` via `<vector>::vector` literal, dim 384, normalized. Match `RAGMgmt-Service/common/sentence_transformer_embedder.py`'s call shape exactly: `model.encode(text, normalize_embeddings=True, convert_to_numpy=True)`.

> This step is operator-side because the DAG handler runs in the Airflow container and shouldn't share Python imports with RAGMgmt-Service. The duplication is intentional per `CLAUDE.md`. A future "shared embedder library" published as a Python package would close this gap; for now it's a documented manual step.

### 3. Set the RAGMgmt env vars

In `middleware/RAGMgmt-Service/.env`:

```sh
RAG_EMBEDDER_BACKEND=sentence_transformer
# RAG_EMBEDDER_MODEL=sentence-transformers/all-MiniLM-L6-v2   # default
```

### 4. Truncate the existing embeddings table

Existing embeddings are stale (stub-derived) — they won't match the new query embeddings.

```sh
docker exec -it rhc-postgres psql -U rhc_admin -d rag_vectors \
  -c "TRUNCATE child_chunk_embeddings;"
```

The seed-practice-voice script that runs on `docker-all-up.sh` re-populates the practice-voice corpus, but its `_stub_embed` ALSO needs the same model swap (or its rows produced by the seed will mismatch query embeddings). For practice voice specifically, re-run the seed script after editing it.

### 5. Re-ingest each dataset

From the admin portal: **Administration → Data Management → Initial DataSet** → for each dataset, pick an endpoint and click Run ingest with **Force refresh** ticked. The DAG fetches → chunks → embeds with the new embedder → upserts.

For the practice-voice sample corpus:

```sh
DevOps/Local/Scripts/seed-practice-voice.sh
```

### 6. Restart RAGMgmt and verify

```sh
npm run services:stop
npm run services:start
curl -X POST http://localhost:8002/retrieve \
  -H 'Content-Type: application/json' \
  -d '{"query":"AHPRA testimonials","top_k":3}' \
  | jq '.respCtxData.embedder'
```

Should report `"sentence_transformer"`. The first request after restart pays the model-load cost (~3–5 s); subsequent requests are fast.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Service log: `sentence-transformers not installed; falling back to stub` | Optional dep missing | `pip install '.[real-embedder]'` |
| Service log: `produces dim=N but expects dim=M` | The configured model's output dim differs from the existing pgvector column | Either pick a 384-dim model (default works) OR run a schema migration to ALTER the column AND re-embed |
| Retrieval scores look way off / many zero-similarity hits | Mixed embedders — query side is real but corpus is still stub-embedded | Re-run step 4 + 5 |
| `respCtxData.embedder` reports `stub_sha256_dim384` despite env var set | Dep / model name issue silently fell back | Check the service log for the WARNING immediately after startup |

## Falling back

```sh
RAG_EMBEDDER_BACKEND=stub
```

Restart RAGMgmt. The corpus is still real-embedded (which doesn't match), so re-truncate + re-ingest with the DAG handler reverted to stub if you want consistency.

## Related

- [`middleware/RAGMgmt-Service/common/sentence_transformer_embedder.py`](../../middleware/RAGMgmt-Service/common/sentence_transformer_embedder.py)
- [`middleware/RAGMgmt-Service/common/embedding_factory.py`](../../middleware/RAGMgmt-Service/common/embedding_factory.py)
- [`middleware/Regulated-Healthcare-DAGS/handlers/embed_via_pgvector.py`](../../middleware/Regulated-Healthcare-DAGS/handlers/embed_via_pgvector.py) — the DAG-side counterpart
