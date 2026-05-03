# Running the eval harness

Excel Project A Task 14 — RAG-triad evaluation against (clinic, topic, expected-citations) golden triples. The harness runs each triple through the live RAG pipeline, scores **faithfulness / context precision / answer relevance**, and writes a self-contained HTML report.

## When to use this

- Pre-merge gate on a refactor that touches retrieval / chunking / drafter prompts.
- Acceptance check before flipping a production deploy to a new embedder or reranker.
- Compliance review — the report pairs with the Langfuse traces the same /generate calls emitted, so a reviewer can drill from a row to the exact trace.

## Acceptance bars (Excel)

| Metric | Threshold |
|---|---|
| Faithfulness | ≥ 0.90 |
| Context precision | ≥ 0.75 |
| Answer relevance | ≥ 0.85 |

The harness exits 0 when every triple passes all three bars; exit 2 if any triple fails. Wire that into CI as a gating check.

## Triple format (JSONL, one per line)

```json
{
  "id": "ahpra_testimonials_01",
  "clinic_profile": "Generic AU allied-health practice",
  "topic": "What does AHPRA say about testimonials in advertising?",
  "expected_citations": ["Public_Regulator_Guidelines#Testimonials"],
  "expected_corpora": ["regulator"],
  "voice_profile": "professional, plain English"
}
```

`expected_citations` accepts two forms:

- `Dataset#Section_id` — exact match on the new section anchors (Excel Tasks 4 + 11).
- `Dataset` — prefix match on dataset_name only. Useful for pre-section-ID corpora.

The starter `eval/golden_triples.jsonl` ships 10 examples covering the regulator + practice-voice scope. Operators add to 200 (the Excel acceptance count) by appending more lines.

## Steps

### 1. Stack up + ingest

```sh
npm run stack:up
# Trigger ingest from the admin portal so child_chunk_embeddings has rows
# the eval can hit. Alternatively curl POST /ingest for each dataset.
```

### 2. Run the harness

```sh
cd middleware/RAGMgmt-Service
python -m eval.cli \
  --triples eval/golden_triples.jsonl \
  --cloud local \
  --output /tmp/rag_eval_report.html \
  --results-jsonl /tmp/rag_eval_results.jsonl
```

For an AWS-deployed stack:

```sh
python -m eval.cli \
  --triples eval/golden_triples.jsonl \
  --cloud aws \
  --output /tmp/rag_eval_report_aws.html
```

(The `--cloud aws` preset flips backends to Bedrock / OpenSearch / layered guardrails per `rag_iface/cloud_presets.py`. AWS_OPENSEARCH_ENDPOINT, BEDROCK_MODEL_ID, etc. must already be set.)

### 3. Read the report

Open `/tmp/rag_eval_report.html`. Top of the report:

- Aggregate scores (mean across all triples) with PASS/FAIL pills against each Excel bar.
- Per-triple pass rate ("ALL PASS / MIXED / ALL FAIL").

Per-row table:

- Faithfulness score (red when < 0.90).
- Context precision (red when < 0.75).
- Answer relevance (red when < 0.85).
- Verdict pill per triple.

The full per-triple result data is in the JSONL output (`--results-jsonl`) — useful for diffing eval runs across drafter / embedder swaps.

## Metric implementations

All three metrics ship as **stdlib heuristics** today:

- **Faithfulness**: re-uses the live `FaithfulnessService` token-overlap scorer the regenerate loop already invokes.
- **Context precision**: of retrieved citations, what fraction match `expected_citations`? Match by exact `Dataset#Section_id` first, then fallback to dataset prefix.
- **Answer relevance**: token overlap between topic tokens and draft tokens, weighted by topic-token coverage (so on-topic drafts that introduce supporting detail aren't penalized like vanilla Jaccard).

The Excel names Ragas as the reference tool — Ragas's LLM-as-judge versions of these metrics are the upgrade path. The harness orchestration (CLI + HTML report) doesn't change; only `eval/metrics.py` swaps. A `[ragas]` extra in `pyproject.toml` is the natural seam for that.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Every faithfulness score is 0 | The corpus is empty or `RHC_VECTORS_DB_DSN` / `AWS_OPENSEARCH_ENDPOINT` mismatches the data | Verify `child_chunk_embeddings` has rows; re-ingest if needed |
| Context precision always 0 even with corpus matches | `expected_citations` use a different format (e.g. `[1]` markers — those aren't anchors) | Fix triples to use `Dataset#Section_id` form |
| Answer relevance low even on obviously on-topic drafts | Heuristic is surface-token overlap; a paraphrased draft scores lower | Acceptable for now; upgrade to Ragas LLM-as-judge for semantic scoring |
| CLI exits 2 every time | One or more triples fail at least one threshold | Open the HTML report — failed metric is highlighted red per row |

## Related

- [`middleware/RAGMgmt-Service/eval/cli.py`](../../middleware/RAGMgmt-Service/eval/cli.py)
- [`middleware/RAGMgmt-Service/eval/metrics.py`](../../middleware/RAGMgmt-Service/eval/metrics.py)
- [`middleware/RAGMgmt-Service/eval/golden_triples.jsonl`](../../middleware/RAGMgmt-Service/eval/golden_triples.jsonl) — starter set
- [Excel: `RAG_Mastery_Projects.xlsx` → `1_Project_A_Healthcare_Content` → Hands-on tasks → Task 14]
