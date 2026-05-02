# Enabling Langfuse observability

The README's primary observability commitment is Langfuse — per-call traces of retrieval, drafter call, faithfulness, and guardrails for review. The default is no-op; this guide turns it on.

## When to use this

- You want to inspect what the system actually returned for past `/generate` calls.
- A compliance reviewer needs to see prompt/completion + retrieved chunks + faithfulness verdict per draft.
- You're tuning thresholds (`per_sentence_threshold`, `overall_threshold`) and want to compare runs.

## Prerequisites

- A Langfuse instance reachable from the RAGMgmt service. Self-hosted via `docker run langfuse/langfuse:latest` is the lowest-friction option for local dev; cloud Langfuse works too.
- Langfuse public + secret keys (created in your Langfuse project's Settings).

## Steps

### 1. Run Langfuse (self-hosted, local)

```sh
# Quick local Langfuse — see https://langfuse.com/docs/deployment/self-host for production
docker run -d --name langfuse \
  -p 3000:3000 \
  -e DATABASE_URL=postgresql://... \
  -e NEXTAUTH_SECRET=... \
  -e SALT=... \
  langfuse/langfuse:latest
```

Or use Langfuse Cloud (https://cloud.langfuse.com).

### 2. Install the optional dep

```sh
cd middleware/RAGMgmt-Service
pip install '.[langfuse]'
```

This adds `langfuse>=2.0`. The Langfuse client gracefully no-ops when the dep is missing OR when `LANGFUSE_HOST` is unset, so a forgotten install isn't a service-down event.

### 3. Set the env vars

In `middleware/RAGMgmt-Service/.env`:

```sh
LANGFUSE_HOST=http://localhost:3000
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_ENVIRONMENT=local-dev   # tags traces; useful when one Langfuse project receives from multiple deployments
```

`LANGFUSE_SECRET_KEY` accepts cloud-secret-manager references — same form as `ANTHROPIC_API_KEY`:

```sh
LANGFUSE_SECRET_KEY=aws-sm://us-east-1/langfuse-secret
LANGFUSE_SECRET_KEY=azure-kv://my-vault/langfuse-secret
LANGFUSE_SECRET_KEY=gcp-sm://my-project/langfuse-secret
```

### 4. Restart RAGMgmt

```sh
npm run services:stop
npm run services:start
tail -f /tmp/rhc-rag-logs/ragmgmt.log
```

Look for:

```
INFO ... common.langfuse_client: Langfuse enabled (host=http://localhost:3000)
```

### 5. Make a /generate call

```sh
curl -X POST http://localhost:8002/generate \
  -H 'Content-Type: application/json' \
  -d '{"topic":"AHPRA testimonials"}' > /tmp/draft.json
```

Open Langfuse → Traces. You should see a new `generate_grounded_draft` trace with sub-spans for `retrieval` and events for `faithfulness`, `guardrails`, `citations_summary`.

## What gets shipped (and what doesn't)

The Langfuse client is **privacy-by-default** — it forwards aggregate identifiers but not raw content that could leak through observability storage:

- ✅ Topic (the request input)
- ✅ Draft markdown (the request output)
- ✅ Retrieval metadata: corpora present/missing, per-corpus hit counts, reranker / embedder names
- ✅ Faithfulness verdict: score, passed, sentence count, scorer name
- ✅ Guardrails verdict: policy_id, max_severity, **rule_ids** of violations
- ❌ Guardrails matched_text / char offsets — would leak the rejected prompt content
- ❌ Citation snippet content — would forward indexed corpus passages to the trace store
- ✅ Citation aggregate counts: by `corpus_type`, by `dataset_name`

If you need richer trace data for compliance review, edit `common/langfuse_client.py::emit_generation_trace` — the sensitive-redaction policy lives there.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Service log: `Langfuse SDK not installed — observability disabled` | Optional dep missing | `pip install '.[langfuse]'` |
| Service log: `LANGFUSE_HOST is unset — Langfuse observability disabled` | Env var missing | Set it in `.env` |
| Service starts cleanly with `Langfuse enabled` but Traces page is empty | Wrong key pair (mixing public from one project with secret from another), or unreachable host | Test with `curl $LANGFUSE_HOST/api/public/health` from the service host |
| Service log: `Langfuse trace emit failed: …` | Network blip / Langfuse instance restart | Per-call failures are non-fatal — they don't break /generate. The next request retries cleanly. |

## Falling back

```sh
# In .env
LANGFUSE_HOST=
```

Restart. Service runs identically with the SDK still installed but disabled — useful for an A/B comparison.

## Related

- [`middleware/RAGMgmt-Service/common/langfuse_client.py`](../../middleware/RAGMgmt-Service/common/langfuse_client.py)
- [README — Observability commitments](../../README.md#observability-commitments)
