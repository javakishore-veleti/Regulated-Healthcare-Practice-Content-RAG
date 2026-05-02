"""Stub embedder used by the retrieval leg of the hybrid search pattern.

Mirrors `embed_via_pgvector.py`'s `_stub_embed` exactly so that an embedded query
lands in the same vector space as the corpus. Both must move together when a real
model swaps in. The duplication is intentional: the DAG handler runs in the Airflow
container and this module runs in the FastAPI process — they don't share imports.
"""

from __future__ import annotations

import hashlib
import math

EMBED_DIM = 384


def stub_embed(text: str, dim: int = EMBED_DIM) -> list[float]:
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


def vector_literal(embedding: list[float]) -> str:
    """pgvector text-form literal, cast via `::vector` in queries."""
    return "[" + ",".join(f"{x:.6f}" for x in embedding) + "]"
