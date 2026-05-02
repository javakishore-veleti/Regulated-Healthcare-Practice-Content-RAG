"""AWS OpenSearch Serverless retrieval DAO — RAG_Mastery_Projects.xlsx Project A
Task 7: 'Embed corpus on AWS into OpenSearch with hybrid mapping'.

Implements the same `IRetrievalDao` contract as `PostgresRetrievalDao` so the
service layer doesn't know which backend it's hitting. Operators flip
`RAG_RETRIEVAL_BACKEND=aws_opensearch_serverless` and the rest of the
generation pipeline (chunking, faithfulness, guardrails, drafter) stays
unchanged.

Auth: SigV4 via boto3's standard AWS chain (env vars, ~/.aws/credentials,
IRSA / Pod Identity in EKS, SSO). The Lambda / ECS / EKS workload that hosts
this service needs `aoss:APIAccessAll` on the target collection.

Index mapping expected (created by the operator's Terraform / IaC, not by
this DAO):

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

Optional dep — install via `pip install '.[opensearch]'`. The factory falls
back to the Postgres DAO when boto3 / opensearch-py / endpoint is missing.
"""

from __future__ import annotations

import logging
from typing import Any

from common.tracing import traced

LOGGER = logging.getLogger(__name__)


class OpenSearchRetrievalDao:
    """Hybrid retrieval against an AWS OpenSearch Serverless collection.

    Lexical leg = OpenSearch `match` query on `child_text` (BM25 default).
    Dense leg   = OpenSearch `knn` query on `embedding`.

    Both legs return hits in the SAME shape PostgresRetrievalDao returns, so
    `_rrf_fuse` in retrieval_service can fuse without branching on backend.
    """

    def __init__(self, endpoint: str, index: str, region: str) -> None:
        if not endpoint:
            raise ValueError(
                "OpenSearchRetrievalDao requires AWS_OPENSEARCH_ENDPOINT — "
                "the AOSS collection's endpoint URL "
                "(e.g. https://<id>.<region>.aoss.amazonaws.com)."
            )
        if not index:
            raise ValueError(
                "OpenSearchRetrievalDao requires AWS_OPENSEARCH_INDEX."
            )
        # Lazy imports — keeps the heavy dep (opensearch-py + botocore signing)
        # out of the import chain when this DAO isn't selected.
        import boto3  # type: ignore[import-not-found]
        from opensearchpy import (  # type: ignore[import-not-found]
            AWSV4SignerAuth,
            OpenSearch,
            RequestsHttpConnection,
        )

        credentials = boto3.Session().get_credentials()
        self._client = OpenSearch(
            hosts=[endpoint.replace("https://", "").rstrip("/")],
            http_auth=AWSV4SignerAuth(credentials, region, "aoss"),
            use_ssl=True,
            verify_certs=True,
            connection_class=RequestsHttpConnection,
            pool_maxsize=20,
        )
        self._index = index
        self._region = region
        LOGGER.info(
            "OpenSearchRetrievalDao initialized (endpoint=%s, index=%s, region=%s)",
            endpoint, index, region,
        )

    @traced("retrieval.dao.opensearch.lexical_search")
    async def lexical_search(
        self, query: str, top_k: int, dataset_names: list[str] | None
    ) -> list[dict]:
        body: dict[str, Any] = {
            "size": top_k,
            "query": _bool_with_filter(
                must=[{"match": {"child_text": {"query": query}}}],
                dataset_names=dataset_names,
            ),
        }
        # opensearchpy is sync — wrap in to_thread so we don't block the loop.
        import asyncio
        resp = await asyncio.to_thread(
            self._client.search, index=self._index, body=body
        )
        return [_hit_to_row(h, leg="lexical") for h in resp["hits"]["hits"]]

    @traced("retrieval.dao.opensearch.dense_search")
    async def dense_search(
        self,
        query_vector: list[float],
        top_k: int,
        dataset_names: list[str] | None,
    ) -> list[dict]:
        # Hybrid-friendly k-NN: the must clause does the actual k-NN; the
        # filter clause restricts to dataset_names. Both `knn` and the
        # filter sit inside `bool` so we get both ANN AND the dataset cut.
        knn_clause = {"knn": {"embedding": {"vector": query_vector, "k": top_k}}}
        body: dict[str, Any] = {
            "size": top_k,
            "query": _bool_with_filter(
                must=[knn_clause],
                dataset_names=dataset_names,
            ),
        }
        import asyncio
        resp = await asyncio.to_thread(
            self._client.search, index=self._index, body=body
        )
        return [_hit_to_row(h, leg="dense") for h in resp["hits"]["hits"]]


def _bool_with_filter(
    *, must: list[dict], dataset_names: list[str] | None
) -> dict:
    """Wrap `must` in a bool query and add an optional dataset_name filter."""
    bool_clause: dict[str, Any] = {"must": must}
    if dataset_names:
        bool_clause["filter"] = [{"terms": {"dataset_name": dataset_names}}]
    return {"bool": bool_clause}


def _hit_to_row(hit: dict, leg: str) -> dict:
    """Map an OpenSearch hit to the same row dict PostgresRetrievalDao returns
    so retrieval_service can fuse without branching on backend."""
    src = hit.get("_source") or {}
    return {
        "id": hit.get("_id"),
        "dataset_name": src.get("dataset_name"),
        "page_index": src.get("page_index"),
        "parent_id": src.get("parent_id"),
        "child_id": src.get("child_id"),
        "parent_text": src.get("parent_text") or "",
        "child_text": src.get("child_text") or "",
        "char_offset_in_parent": src.get("char_offset_in_parent") or 0,
        "leg_score": float(hit.get("_score") or 0.0),
        "leg": leg,
    }
