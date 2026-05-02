"""Embedding handler — reads chunked/*.json, embeds each child, and upserts
to `rag_vectors.child_chunk_embeddings`.

Embedder selection (env-driven, mirrors RAGMgmt-Service's query-side
`embedding_factory.py`):

  RHC_DAG_EMBEDDER=stub          (default)
                                  Hash-based, deterministic, dim 384, no deps.
                                  Smoke-grade only — not semantically meaningful.

  RHC_DAG_EMBEDDER=aws_bedrock   Excel Project A AWS row "Embedding".
                                  Calls Bedrock InvokeModel (Titan Embed v2 or
                                  Cohere Embed v4). Required env:
                                    BEDROCK_EMBEDDING_MODEL_ID, BEDROCK_REGION.
                                  Required extra: `pip install boto3` in the
                                  Airflow environment that runs this handler.

The QUERY-side embedder lives in middleware/RAGMgmt-Service. Both sides MUST
use the same embedder family + model id, otherwise the corpus and queries
land in different vector spaces and similarity scores are meaningless.

The vector column dim (set in the rag_vectors V001 migration) is 384.
Changing it requires an ALTER + corpus re-embed migration. Titan Embed v2's
`dimensions` request parameter lets us pin a real-model output to 384 so
the column doesn't need to change for AWS deploys.

Gracefully no-ops when `RHC_VECTORS_DB_DSN` is unset.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras

LOGGER = logging.getLogger(__name__)

EMBED_DIM = 384

# Embedder selection. Reads at module-level so each DAG run picks up the
# current env. Default `stub` keeps the local-dev path zero-dep.
_EMBEDDER_BACKEND = (os.environ.get("RHC_DAG_EMBEDDER") or "stub").lower()
_BEDROCK_MODEL_ID = os.environ.get("BEDROCK_EMBEDDING_MODEL_ID") or ""
_BEDROCK_REGION = os.environ.get("BEDROCK_REGION") or "us-east-1"


def _stub_embed(text: str, dim: int = EMBED_DIM) -> list[float]:
    """Stdlib-only deterministic embedder. SHA-256 cascade → uniform-floats → L2-norm.
    Mirrors `RAGMgmt-Service/common/embedding.py::stub_embed` exactly so corpus
    rows and query embeddings land in the same vector space."""
    floats: list[float] = []
    seed = text.encode("utf-8")
    while len(floats) < dim:
        seed = hashlib.sha256(seed).digest()
        for i in range(8):
            chunk = seed[i * 4 : (i + 1) * 4]
            val = int.from_bytes(chunk, "big") / 0xFFFFFFFF - 0.5
            floats.append(val)
            if len(floats) == dim:
                break
    norm = math.sqrt(sum(f * f for f in floats))
    return [f / norm for f in floats] if norm > 0 else floats


# Singleton boto3 client for the bedrock-runtime, lazily constructed on first
# use. Reused across rows in the same DAG run so we don't re-init the SigV4
# signer on every embedding call.
_bedrock_client = None


def _bedrock_embed(text: str, dim: int = EMBED_DIM) -> list[float]:
    """Call Bedrock InvokeModel for one text. Mirrors the QUERY-side
    `BedrockEmbedder` in RAGMgmt-Service so corpus and query embeddings land
    in the same vector space.

    Required env:
      BEDROCK_EMBEDDING_MODEL_ID  (e.g. amazon.titan-embed-text-v2:0)
      BEDROCK_REGION              (default us-east-1)
      AWS credentials via the standard chain (env / IRSA / SSO).

    Required dep: `boto3` in the Airflow environment that runs this handler.
    """
    global _bedrock_client

    if not _BEDROCK_MODEL_ID:
        raise RuntimeError(
            "RHC_DAG_EMBEDDER=aws_bedrock but BEDROCK_EMBEDDING_MODEL_ID is unset. "
            "Set it to a Bedrock embedding model id (e.g. amazon.titan-embed-text-v2:0)."
        )

    if _bedrock_client is None:
        try:
            import boto3  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "RHC_DAG_EMBEDDER=aws_bedrock but boto3 is not installed in this "
                "Airflow environment. Add boto3 to the worker image or "
                "PYTHONPATH-installed packages."
            ) from exc
        _bedrock_client = boto3.client("bedrock-runtime", region_name=_BEDROCK_REGION)

    if _BEDROCK_MODEL_ID.startswith("amazon.titan-embed"):
        body = {"inputText": text, "dimensions": dim, "normalize": True}
    elif _BEDROCK_MODEL_ID.startswith("cohere.embed"):
        # Corpus side uses search_document; QUERY side uses search_query.
        body = {
            "texts": [text],
            "input_type": "search_document",
            "embedding_types": ["float"],
        }
    else:
        body = {"inputText": text}

    resp = _bedrock_client.invoke_model(
        modelId=_BEDROCK_MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(body),
    )
    payload = json.loads(resp["body"].read())

    if "embedding" in payload:
        vec = payload["embedding"]
    elif "embeddings" in payload:
        embs = payload["embeddings"]
        if isinstance(embs, dict) and "float" in embs:
            vec = embs["float"][0]
        else:
            vec = embs[0]
    else:
        raise RuntimeError(
            f"Bedrock embed response had no recognizable embedding field. "
            f"Keys: {sorted(payload.keys())}"
        )

    if len(vec) != dim:
        raise RuntimeError(
            f"Bedrock model {_BEDROCK_MODEL_ID} returned dim={len(vec)} but the "
            f"pgvector column expects dim={dim}. Pick a model whose output "
            f"matches, or run a schema migration."
        )
    return [float(x) for x in vec]


def _embed(text: str) -> list[float]:
    """Dispatch to the configured embedder backend."""
    if _EMBEDDER_BACKEND == "aws_bedrock":
        return _bedrock_embed(text)
    if _EMBEDDER_BACKEND != "stub":
        LOGGER.warning(
            "Unknown RHC_DAG_EMBEDDER=%r — falling back to stub", _EMBEDDER_BACKEND,
        )
    return _stub_embed(text)


def _vector_literal(embedding: list[float]) -> str:
    """pgvector accepts text-form `[v1,v2,...]` cast via `::vector`. This avoids
    needing the pgvector psycopg adapter as an extra dependency."""
    return "[" + ",".join(f"{x:.6f}" for x in embedding) + "]"


def _embedder_label() -> str:
    """Recorded in the manifest's embedding summary so a downstream operator
    inspecting Latest_Ingest can tell which embedder produced the rows.

    Pairing this with the same label on the QUERY side prevents a silent
    cross-process mismatch where corpus = stub but queries = bedrock."""
    if _EMBEDDER_BACKEND == "aws_bedrock":
        return f"aws_bedrock:{_BEDROCK_MODEL_ID}"
    return "stub_sha256_dim384"


def embed_chunked_pages(resolved: dict[str, Any]) -> dict[str, Any]:
    """Read every `chunked/*.json` under the dataset's Latest_Ingest, embed each
    child, and upsert into `child_chunk_embeddings`. Updates the manifest with an
    `embedding` summary block."""
    dsn = os.environ.get("RHC_VECTORS_DB_DSN") or ""
    target = Path(resolved["destination_path"])
    manifest_path = target / "INGEST_MANIFEST.json"

    if not manifest_path.is_file():
        return {"status": "skipped", "reason": f"manifest not found at {manifest_path}"}

    chunked_dir = target / "chunked"
    if not chunked_dir.is_dir():
        return {"status": "skipped", "reason": "no chunked/ directory; chunking step did not run"}

    if not dsn:
        summary = {
            "status": "skipped",
            "reason": "RHC_VECTORS_DB_DSN not configured in this environment",
        }
        manifest = json.loads(manifest_path.read_text())
        manifest["embedding"] = summary
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        return summary

    manifest = json.loads(manifest_path.read_text())
    dataset_name = resolved["dataset_name"]

    chunk_files = sorted(chunked_dir.glob("*_chunks.json"))
    per_page: list[dict[str, Any]] = []
    total_upserted = 0

    conn = psycopg2.connect(dsn)
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            for chunk_path in chunk_files:
                stem = chunk_path.stem  # e.g. "000_chunks"
                page_index = int(stem.split("_")[0])
                ctx = json.loads(chunk_path.read_text())

                parents_by_id = {p["id"]: p for p in ctx.get("parents", [])}
                children = ctx.get("children", [])
                if not children:
                    per_page.append(
                        {"page_index": page_index, "status": "skipped_no_children"}
                    )
                    continue

                rows = []
                for child in children:
                    parent = parents_by_id.get(child["parent_id"])
                    if parent is None:
                        continue
                    rows.append(
                        (
                            dataset_name,
                            page_index,
                            child["parent_id"],
                            child["id"],
                            parent["text"],
                            child["text"],
                            child["char_offset_in_parent"],
                            _vector_literal(_embed(child["text"])),
                        )
                    )

                psycopg2.extras.execute_values(
                    cur,
                    """
                    INSERT INTO child_chunk_embeddings (
                        dataset_name, page_index, parent_id, child_id,
                        parent_text, child_text, char_offset_in_parent, embedding
                    )
                    VALUES %s
                    ON CONFLICT (dataset_name, page_index, child_id) DO UPDATE SET
                        parent_id             = EXCLUDED.parent_id,
                        parent_text           = EXCLUDED.parent_text,
                        child_text            = EXCLUDED.child_text,
                        char_offset_in_parent = EXCLUDED.char_offset_in_parent,
                        embedding             = EXCLUDED.embedding,
                        ingested_dt           = NOW()
                    """,
                    rows,
                    template=(
                        "(%s,%s,%s,%s,%s,%s,%s,%s::vector)"
                    ),
                )
                upserted = len(rows)
                total_upserted += upserted
                per_page.append(
                    {
                        "page_index": page_index,
                        "status": "success",
                        "upserted": upserted,
                    }
                )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    summary = {
        "status": "ok",
        "embedder": _embedder_label(),
        "embedding_dim": EMBED_DIM,
        "table": "child_chunk_embeddings",
        "pages": per_page,
        "total_rows_upserted": total_upserted,
    }
    manifest["embedding"] = summary
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return summary
