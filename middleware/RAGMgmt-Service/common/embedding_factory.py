"""Embedder selection factory — picks one IEmbedder per
`Settings.rag_embedder_backend`. Mirrors the drafter / reranker factories:
pulled out so the dispatch is unit-testable, never raises, falls back to
StubEmbedder when an opt-in backend is misconfigured.

Backends:
  * `stub`                — StubEmbedder (default; no deps, hash-based).
  * `sentence_transformer`— SentenceTransformerEmbedder (requires
                            `[real-embedder]` extra; falls back to stub when
                            the dep or model name is missing).

NOTE: this factory only swaps the QUERY-side embedder. The DAG-side embedder
in `embed_via_pgvector.py` lives in a separate Python process (Airflow); to
fully switch backends, that handler needs the same model swap AND the corpus
needs to be re-embedded. A query embedded with sentence_transformer against
a corpus embedded with stub will produce meaningless similarity scores.
"""

from __future__ import annotations

import logging

from common.embedding import EMBED_DIM, IEmbedder, StubEmbedder

LOGGER = logging.getLogger(__name__)


def build_embedder(settings) -> IEmbedder:
    backend = (settings.rag_embedder_backend or "stub").lower()

    if backend == "stub":
        LOGGER.info("Using StubEmbedder (hash-based, dim=%d)", EMBED_DIM)
        return StubEmbedder()

    if backend == "sentence_transformer":
        return _build_sentence_transformer_or_fallback(settings)

    LOGGER.warning(
        "Unknown RAG_EMBEDDER_BACKEND=%r — falling back to stub", backend,
    )
    return StubEmbedder()


def _build_sentence_transformer_or_fallback(settings) -> IEmbedder:
    model_name = settings.rag_embedder_model
    if not model_name:
        LOGGER.warning(
            "RAG_EMBEDDER_BACKEND=sentence_transformer but RAG_EMBEDDER_MODEL "
            "is unset; falling back to stub."
        )
        return StubEmbedder()

    try:
        from common.sentence_transformer_embedder import SentenceTransformerEmbedder
        # Probe the heavy dep once at factory time — clear single failure point.
        import sentence_transformers  # type: ignore[import-not-found] # noqa: F401
    except ImportError as exc:
        LOGGER.warning(
            "RAG_EMBEDDER_BACKEND=sentence_transformer but sentence-transformers "
            "not installed (%s); install with `pip install '.[real-embedder]'`. "
            "Falling back to stub.",
            exc,
        )
        return StubEmbedder()

    LOGGER.info(
        "Using SentenceTransformerEmbedder (model=%s, dim=%d) — "
        "first embed call will pay model-load latency.",
        model_name, EMBED_DIM,
    )
    return SentenceTransformerEmbedder(
        model_name=model_name,
        expected_dim=EMBED_DIM,
    )
