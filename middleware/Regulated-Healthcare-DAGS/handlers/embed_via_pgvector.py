"""Embedding handler — reads chunked/*.json, embeds each child via a deterministic
stub embedder, and upserts to `rag_vectors.child_chunk_embeddings`.

The stub embedder is a placeholder: hash-based, dim 384, deterministic per-text but
not semantically meaningful. It exists so the pgvector roundtrip can be validated
end-to-end without pulling a model. Swapping in a real embedder later is one
edit-point: replace `_stub_embed`. The vector dim is set in the migration (also 384)
and changing it requires an ALTER + backfill migration.

Gracefully no-ops when `RHC_VECTORS_DB_DSN` is unset so the ingest pipeline still
succeeds in environments without a vector DB configured.
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


def _stub_embed(text: str, dim: int = EMBED_DIM) -> list[float]:
    """Stdlib-only deterministic embedder. SHA-256 cascade → uniform-floats → L2-norm.
    Replace with a real model later; the public signature stays the same."""
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


def _vector_literal(embedding: list[float]) -> str:
    """pgvector accepts text-form `[v1,v2,...]` cast via `::vector`. This avoids
    needing the pgvector psycopg adapter as an extra dependency."""
    return "[" + ",".join(f"{x:.6f}" for x in embedding) + "]"


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
                            _vector_literal(_stub_embed(child["text"])),
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
        "embedder": "stub_sha256_dim384",
        "embedding_dim": EMBED_DIM,
        "table": "child_chunk_embeddings",
        "pages": per_page,
        "total_rows_upserted": total_upserted,
    }
    manifest["embedding"] = summary
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return summary
