"""Embedding handler for AWS OpenSearch Serverless — corpus side of the
`RAG_RETRIEVAL_BACKEND=aws_opensearch_serverless` flow on the RAGMgmt query
side. Excel Project A AWS architecture row "Vector store" + Task 7 closer.

Reads `chunked/*.json` (same input as embed_via_pgvector), embeds each child
via the configured embedder backend (`RHC_DAG_EMBEDDER` ∈ {stub, aws_bedrock} —
same dispatch as the pgvector handler), and bulk-indexes into the AOSS index
named by `AWS_OPENSEARCH_INDEX`.

Required env:
  AWS_OPENSEARCH_ENDPOINT       https://<id>.<region>.aoss.amazonaws.com
  AWS_OPENSEARCH_INDEX          rhc-child-chunks (or whatever the operator created)
  AWS_OPENSEARCH_REGION         us-east-1 by default
  AWS credentials               via standard chain (Airflow pod IRSA, env, SSO)

Required deps in the Airflow worker environment:
  opensearch-py
  boto3

Index mapping the handler expects (created out-of-band by the operator's
Terraform / IaC, NOT by this handler — same shape as the QUERY-side
`OpenSearchRetrievalDao`'s docstring):

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

Doc IDs are deterministic — `{dataset_name}::{page_index}::{child_id}` — so
re-runs against the same dataset upsert in place.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
from pathlib import Path
from typing import Any, Iterable

LOGGER = logging.getLogger(__name__)


# Reuse the embedder dispatch that lives in embed_via_pgvector — both stub
# and aws_bedrock backends are defined there. Loading via importlib mirrors
# the rest of the handlers (works regardless of Airflow's sys.path).
_pgvec_path = Path(__file__).parent / "embed_via_pgvector.py"
_pgvec_spec = importlib.util.spec_from_file_location(
    "rhc_handlers.embed_via_pgvector", _pgvec_path
)
assert _pgvec_spec is not None and _pgvec_spec.loader is not None
_pgvec = importlib.util.module_from_spec(_pgvec_spec)
_pgvec_spec.loader.exec_module(_pgvec)

_embed = _pgvec._embed  # dispatch: stub | aws_bedrock
_embedder_label = _pgvec._embedder_label
EMBED_DIM = _pgvec.EMBED_DIM


def _build_opensearch_client():
    """Lazy-import opensearchpy + boto3, build an SigV4-signed client.
    Raises with clear remediation when deps are missing — the corpus state
    matters, so silent fallback to a no-op would be worse than failing loud."""
    try:
        import boto3  # type: ignore[import-not-found]
        from opensearchpy import (  # type: ignore[import-not-found]
            AWSV4SignerAuth,
            OpenSearch,
            RequestsHttpConnection,
        )
    except ImportError as exc:
        raise RuntimeError(
            "embed_via_opensearch requires opensearch-py + boto3 in the Airflow "
            "worker environment. Add them to the worker image's requirements "
            "(e.g. `pip install opensearch-py boto3`)."
        ) from exc

    endpoint = os.environ.get("AWS_OPENSEARCH_ENDPOINT") or ""
    if not endpoint:
        raise RuntimeError(
            "AWS_OPENSEARCH_ENDPOINT is unset. Set it to your AOSS collection's "
            "endpoint URL (e.g. https://<id>.us-east-1.aoss.amazonaws.com)."
        )
    region = os.environ.get("AWS_OPENSEARCH_REGION") or "us-east-1"

    credentials = boto3.Session().get_credentials()
    return OpenSearch(
        hosts=[endpoint.replace("https://", "").rstrip("/")],
        http_auth=AWSV4SignerAuth(credentials, region, "aoss"),
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        pool_maxsize=20,
    )


def _bulk_actions(
    rows: Iterable[dict], index: str
) -> Iterable[dict]:
    """Generate the alternating header/body lines opensearch-py's `bulk` helper
    expects when called via the streaming-bulk API. Each doc gets a deterministic
    _id so re-runs upsert."""
    for r in rows:
        doc_id = f"{r['dataset_name']}::{r['page_index']}::{r['child_id']}"
        yield {
            "_op_type": "index",
            "_index": index,
            "_id": doc_id,
            "_source": r,
        }


def embed_chunked_pages(resolved: dict[str, Any]) -> dict[str, Any]:
    """Read every `chunked/*.json` under the dataset's Latest_Ingest, embed each
    child via the configured embedder, and bulk-index into AOSS. Updates the
    manifest with an `embedding` summary block."""
    target = Path(resolved["destination_path"])
    manifest_path = target / "INGEST_MANIFEST.json"

    if not manifest_path.is_file():
        return {"status": "skipped", "reason": f"manifest not found at {manifest_path}"}

    chunked_dir = target / "chunked"
    if not chunked_dir.is_dir():
        return {"status": "skipped", "reason": "no chunked/ directory; chunking step did not run"}

    index = os.environ.get("AWS_OPENSEARCH_INDEX") or "rhc-child-chunks"
    manifest = json.loads(manifest_path.read_text())
    dataset_name = resolved["dataset_name"]

    chunk_files = sorted(chunked_dir.glob("*_chunks.json"))
    rows: list[dict] = []
    per_page: list[dict[str, Any]] = []

    for chunk_path in chunk_files:
        stem = chunk_path.stem
        page_index = int(stem.split("_")[0])
        ctx = json.loads(chunk_path.read_text())

        parents_by_id = {p["id"]: p for p in ctx.get("parents", [])}
        children = ctx.get("children", [])
        if not children:
            per_page.append(
                {"page_index": page_index, "status": "skipped_no_children"}
            )
            continue

        page_rows = 0
        for child in children:
            parent = parents_by_id.get(child["parent_id"])
            if parent is None:
                continue
            embedding = _embed(child["text"])
            if len(embedding) != EMBED_DIM:
                # Defensive: surface dim mismatch loud rather than silently
                # indexing rows that the AOSS knn_vector field will reject.
                raise RuntimeError(
                    f"embed_via_opensearch: embedder produced dim={len(embedding)} "
                    f"but the configured EMBED_DIM={EMBED_DIM}. Pick an embedder "
                    f"whose output matches the index's knn_vector mapping."
                )
            rows.append(
                {
                    "dataset_name": dataset_name,
                    "page_index": page_index,
                    "parent_id": child["parent_id"],
                    "child_id": child["id"],
                    "parent_text": parent["text"],
                    "child_text": child["text"],
                    "char_offset_in_parent": child["char_offset_in_parent"],
                    "embedding": embedding,
                    # Section anchors (Excel Task 4 + 11). Both null when
                    # the source had no markdown headings.
                    "parent_heading": parent.get("parent_heading"),
                    "section_id": parent.get("section_id"),
                }
            )
            page_rows += 1
        per_page.append(
            {"page_index": page_index, "status": "success", "upserted": page_rows}
        )

    # Build the client + bulk-index in one pass. The lazy build means we don't
    # construct a client when the chunked dir is empty.
    total_upserted = 0
    if rows:
        from opensearchpy.helpers import bulk  # type: ignore[import-not-found]
        client = _build_opensearch_client()
        success, failed = bulk(
            client,
            _bulk_actions(rows, index=index),
            raise_on_error=False,
            stats_only=False,
            chunk_size=500,
        )
        total_upserted = success
        if failed:
            LOGGER.warning(
                "embed_via_opensearch: %d row(s) failed to index (sampling first): %r",
                len(failed) if isinstance(failed, list) else failed,
                (failed[:3] if isinstance(failed, list) else None),
            )

    summary = {
        "status": "ok",
        "embedder": _embedder_label(),
        "embedding_dim": EMBED_DIM,
        "vector_store": "aws_opensearch_serverless",
        "index": index,
        "pages": per_page,
        "total_rows_upserted": total_upserted,
    }
    manifest["embedding"] = summary
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return summary
