"""Embedders for the retrieval leg of the hybrid search pattern.

The default `StubEmbedder` mirrors `embed_via_pgvector.py`'s `_stub_embed` so an
embedded query lands in the same vector space as the corpus. The duplication is
intentional: the DAG handler runs in the Airflow container and this module runs
in the FastAPI process — they don't share imports.

A real embedder (e.g. `sentence-transformers/all-MiniLM-L6-v2` — same 384-dim
output as the stub, semantic instead of hash) plugs in via the `IEmbedder`
Protocol; see `sentence_transformer_embedder.py`. Selection is driven by
`RAG_EMBEDDER_BACKEND` through the factory in `embedding_factory.py`.

WARNING: switching backends invalidates the existing pgvector index — the
operator must re-embed the corpus through the DAG before query-side switches
work meaningfully. The DAG-side `_stub_embed` is a separate file that needs
the same swap; keeping them aligned is an operator concern today.
"""

from __future__ import annotations

import hashlib
import math
from typing import Protocol

from common.otel_genai import (
    OP_EMBEDDING,
    SYSTEM_RHC_STUB,
    set_gen_ai_request,
    set_gen_ai_response,
)

EMBED_DIM = 384


class IEmbedder(Protocol):
    """Stable across StubEmbedder and SentenceTransformerEmbedder."""

    name: str
    dim: int

    def embed(self, text: str) -> list[float]: ...


def stub_embed(text: str, dim: int = EMBED_DIM) -> list[float]:
    """Standalone fn — kept for the DAG-side handler's cross-process copy and
    for direct use in tests. Identical math to `StubEmbedder.embed`."""
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


class StubEmbedder:
    """Hash-based embedder. Deterministic, no deps, useful as a smoke-grade
    default and as the reference IEmbedder implementation. Not semantically
    meaningful — for real retrieval quality use SentenceTransformerEmbedder."""

    name = "stub_sha256_dim384"
    dim = EMBED_DIM

    def embed(self, text: str) -> list[float]:
        # OTel GenAI semconv — even the stub gets attributes so dashboards
        # work uniformly across embedder modes.
        set_gen_ai_request(
            system=SYSTEM_RHC_STUB,
            operation=OP_EMBEDDING,
            model=self.name,
        )
        v = stub_embed(text)
        set_gen_ai_response(
            model=self.name,
            input_tokens=len(text.split()),
        )
        return v
