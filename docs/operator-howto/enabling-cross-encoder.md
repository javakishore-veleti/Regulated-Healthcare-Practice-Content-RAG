# Enabling the cross-encoder reranker

The README names cross-encoder rerank as the third stage of Hybrid+Rerank. The default `RAG_RERANKER_BACKEND=token_overlap` is a pure-stdlib approximation; the real cross-encoder (default `cross-encoder/ms-marco-MiniLM-L-6-v2`) gives meaningfully better rerank quality on retrieval-heavy queries.

## When to use this

- Retrieval quality matters for your use case (you've seen wrong-domain hits in `respCtxData.citations`).
- You're willing to take the cold-load cost: ~2 GB transitive deps + ~90 MB model download on first use.
- You have GPU or fast CPU available; per-call latency adds ~50–200 ms even after the model is loaded.

## Prerequisites

- Conda venv at `$HOME/runtime_data/python_venvs/RHPContent-RAG` (the standard project venv).
- Outbound internet on first run for the model download (cached afterward).
- A few GB of disk for `~/.cache/huggingface/`.

## Steps

### 1. Install the optional dep

```sh
cd middleware/RAGMgmt-Service
pip install '.[cross-encoder-rerank]'
```

This adds `sentence-transformers>=2.2`, which transitively pulls torch. Expect a multi-minute install on first run with pip caching cold.

### 2. Set the env vars

In `middleware/RAGMgmt-Service/.env`:

```sh
RAG_RERANKER_BACKEND=cross_encoder
RAG_RERANKER_ALPHA=0.5      # blend weight: 1.0=pure RRF, 0.0=pure cross-encoder
# RAG_CROSS_ENCODER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2   # default
```

Lower `alpha` if you trust the cross-encoder more than the upstream RRF score; higher if RRF is doing the right thing already and you only want the cross-encoder as a tie-breaker.

### 3. Restart the service

```sh
npm run services:stop
npm run services:start
tail -f /tmp/rhc-rag-logs/ragmgmt.log
```

Look for:

```
INFO ... main: Using CrossEncoderReranker (model=cross-encoder/ms-marco-MiniLM-L-6-v2, alpha=0.50) — first rerank call will pay model-load latency.
```

The model itself loads on the FIRST `/retrieve` or `/generate` call, not at startup — so the first request after a service restart is slower (one-time ~3–5 s).

### 4. Verify

```sh
curl -X POST http://localhost:8002/retrieve \
  -H 'Content-Type: application/json' \
  -d '{"query":"AHPRA testimonials in telehealth advertising","top_k":3}' \
  | jq '.respCtxData.reranker, .respCtxData.hits[].rerank_score'
```

Reranker should report `"cross_encoder"`. Each hit gets a `rerank_score` (the alpha-blended score) and a `rerank_ce_score` (the raw cross-encoder logit / sigmoid output).

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Service log: `sentence-transformers not installed; falling back to token_overlap` | Optional dep missing | `pip install '.[cross-encoder-rerank]'` from the service directory |
| First `/retrieve` call hangs for ~30 s, then succeeds | Model download in progress | Normal on first call. Subsequent calls are fast. |
| Service log: `produces dim=N but the configured / pgvector column expects dim=M` | You picked a model with a different output dim | Either pick a 384-dim model OR run a schema migration to ALTER the `embedding` column dim AND re-embed the corpus. The cross-encoder doesn't write to pgvector, but its model dim still has to match the existing column for the alignment check to pass — the safer option is to keep the default model. |

## Tuning

Three knobs affect rerank behavior:

- `RAG_RERANKER_ALPHA` — RRF weight in the blend. Most-tuned knob.
- `top_k_per_leg` (request-time) — how many candidates each retrieval leg pulls before fusion+rerank. Higher → cross-encoder has more candidates to rerank. Default 50.
- `rrf_k` (request-time) — softening constant for RRF. Lower → fusion trusts the per-leg ranks more. Default 60.

Empirically: try `alpha=0.5` first, then sweep to 0.3 and 0.7 and pick the better feel.

## Falling back

To revert without un-installing the dep:

```sh
RAG_RERANKER_BACKEND=token_overlap
```

Restart the service. No code changes.

## Related

- [`middleware/RAGMgmt-Service/service/rerank/cross_encoder_reranker.py`](../../middleware/RAGMgmt-Service/service/rerank/cross_encoder_reranker.py)
- [`middleware/RAGMgmt-Service/service/rerank/factory.py`](../../middleware/RAGMgmt-Service/service/rerank/factory.py)
