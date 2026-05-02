# AWS OpenSearch Serverless retrieval backend

Project A's Excel architecture (`RAG_Mastery_Projects.xlsx` → `1_Project_A_Healthcare_Content` → AWS architecture row "Vector store") names **Amazon OpenSearch Serverless** with hybrid k-NN + BM25 as the AWS retrieval target. The default `RAG_RETRIEVAL_BACKEND=postgres` runs pgvector locally; this guide flips RAGMgmt-Service over to OpenSearch Serverless for the AWS deploy.

## When to use this

- Production AWS deploy — OpenSearch Serverless absorbs scaling and replaces the pgvector single-node footprint.
- Excel Task 7 — "Embed corpus on AWS into OpenSearch with hybrid mapping; verify in Langfuse." Recall@10 ≥ 0.8 acceptance criterion.
- You have a populated AOSS collection (the ingest path is operator-side; this guide only covers query-side wiring).

## Prerequisites

- AWS account with OpenSearch Serverless enabled.
- An AOSS collection with the index mapping below (created by your Terraform / Bicep / IaC, not by this DAO).
- AWS credentials reachable via the standard chain (env vars, `~/.aws/credentials`, IRSA in EKS, SSO).
- IAM principal has `aoss:APIAccessAll` on the collection.

## Index mapping

The DAO expects this shape on the AOSS index:

```json
{
  "settings": {"index.knn": true},
  "mappings": {
    "properties": {
      "dataset_name":          {"type": "keyword"},
      "page_index":            {"type": "integer"},
      "parent_id":             {"type": "keyword"},
      "child_id":              {"type": "keyword"},
      "parent_text":           {"type": "text"},
      "child_text":            {"type": "text"},
      "char_offset_in_parent": {"type": "integer"},
      "embedding": {
        "type": "knn_vector",
        "dimension": 384,
        "method": {"name": "hnsw", "engine": "lucene", "space_type": "cosinesimil"}
      }
    }
  }
}
```

Dimension matches the existing pgvector column (384) — no schema migration needed when switching backends with the same embedder.

## Steps

### 1. Install the optional dep

```sh
cd middleware/RAGMgmt-Service
pip install '.[opensearch]'
```

This adds `opensearch-py>=2.4` and `boto3>=1.34`. boto3 is shared with the Bedrock drafter extra so installing both is incremental.

### 2. Set the env vars

In `middleware/RAGMgmt-Service/.env` (or k8s ConfigMap):

```sh
RAG_RETRIEVAL_BACKEND=aws_opensearch_serverless
AWS_OPENSEARCH_ENDPOINT=https://abc123.us-east-1.aoss.amazonaws.com
AWS_OPENSEARCH_INDEX=rhc-child-chunks
AWS_OPENSEARCH_REGION=us-east-1
```

`AWS_OPENSEARCH_ENDPOINT` is required when `RAG_RETRIEVAL_BACKEND=aws_opensearch_serverless` — empty endpoint falls back to Postgres with a clear WARNING in the service log.

### 3. Verify your AWS chain + AOSS access

```sh
aws sts get-caller-identity   # should print your IAM principal
aws opensearchserverless list-collections --region us-east-1
```

Both should succeed. If the second fails with `AccessDenied`, your principal lacks `aoss:ListCollections`; check IAM and the collection's data access policy.

### 4. Restart RAGMgmt

```sh
npm run services:stop
npm run services:start
tail -f /tmp/rhc-rag-logs/ragmgmt.log
```

Look for:

```
INFO ... dao.retrieval_dao_factory: Using OpenSearchRetrievalDao (endpoint=https://abc123..., index=rhc-child-chunks, region=us-east-1)
```

If you instead see `falling back to postgres`, the WARNING immediately above names what's missing (dep not installed, endpoint unset, etc.).

### 5. Test a retrieval

```sh
curl -X POST http://localhost:8002/retrieve \
  -H 'Content-Type: application/json' \
  -d '{"query":"AHPRA testimonial advertising","top_k":5}' \
  | jq '.respCtxData.hits[].dataset_name, .respCtxData.legs'
```

The response shape is identical to the Postgres backend — `respCtxData.hits` carries the same fields (`dataset_name`, `child_id`, `parent_id`, `child_text`, `rrf_score`, `rerank_score`).

## Ingest path (separate)

This guide covers the QUERY side only. To populate the AOSS index, you need an ingest path that:

1. Pulls raw docs (existing DAG: `regulated_healthcare_dataset_ingest`).
2. Chunks via `POST /chunk` (existing).
3. Embeds each child chunk (existing DAG handler: `embed_via_pgvector.py` — needs an OpenSearch sibling).
4. Bulk-indexes into AOSS with the mapping above.

A dedicated DAG handler (`embed_via_opensearch.py`) is the natural follow-up. Until it lands, an operator workflow is:

- Use the existing `embed_via_pgvector` to write to a local pgvector instance.
- Run a one-off bulk migration script that reads from pgvector and writes to AOSS.
- Verify with `aws opensearchserverless` API that the index has the expected document count.

## Falling back

```sh
RAG_RETRIEVAL_BACKEND=postgres
```

Restart. No code changes. Useful for A/B comparisons between pgvector and AOSS.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Service log: `optional deps not installed; falling back to postgres` | `[opensearch]` extra missing | `pip install '.[opensearch]'` |
| Service log: `AWS_OPENSEARCH_ENDPOINT is unset; falling back to postgres` | Env var typo / not loaded | Verify `.env` is in `middleware/RAGMgmt-Service/` and has the var |
| `/retrieve` returns 0 hits | Index not populated, OR the dataset_names filter excludes everything | Check the index has documents; try the query without `dataset_name` to remove the filter |
| `AuthorizationException: AccessDenied` | IAM principal can't read the collection | Add `aoss:APIAccessAll` to the collection's data access policy AND IAM policy |
| Latency > 1s per request | Cold AOSS collection / pre-provisioned OCU starvation | AOSS auto-scales but cold-starts can be slow; pre-warm with a few warm-up queries |

## Related

- [`middleware/RAGMgmt-Service/dao/opensearch_retrieval_dao.py`](../../middleware/RAGMgmt-Service/dao/opensearch_retrieval_dao.py)
- [`middleware/RAGMgmt-Service/dao/retrieval_dao_factory.py`](../../middleware/RAGMgmt-Service/dao/retrieval_dao_factory.py)
- [Excel: `RAG_Mastery_Projects.xlsx` → `1_Project_A_Healthcare_Content` → AWS architecture row `Vector store`]
