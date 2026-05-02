"""Reranker selection factory — picks one IReranker per
`Settings.rag_reranker_backend`. Mirrors the drafters/factory pattern: pulled
out of main.py so the dispatch is unit-testable, never raises, falls back to
TokenOverlapReranker (the pure-stdlib default) when an opt-in backend is
misconfigured.

Backends:
  * `identity`        — IdentityReranker (passthrough truncation; baseline).
  * `token_overlap`   — TokenOverlapReranker (default; pure stdlib).
  * `cross_encoder`   — CrossEncoderReranker (requires `[cross-encoder-rerank]`
                        extra; falls back to token_overlap when missing).
"""

from __future__ import annotations

import logging

from service.rerank.reranker import (
    IdentityReranker,
    IReranker,
    TokenOverlapReranker,
)

LOGGER = logging.getLogger(__name__)


def build_reranker(settings) -> IReranker:
    backend = (settings.rag_reranker_backend or "token_overlap").lower()
    alpha = settings.rag_reranker_alpha

    if backend == "identity":
        LOGGER.info("Using IdentityReranker (passthrough truncation)")
        return IdentityReranker()

    if backend == "cross_encoder":
        return _build_cross_encoder_or_fallback(settings)

    if backend == "token_overlap":
        LOGGER.info("Using TokenOverlapReranker (alpha=%.2f)", alpha)
        return TokenOverlapReranker(alpha=alpha)

    LOGGER.warning(
        "Unknown RAG_RERANKER_BACKEND=%r — falling back to token_overlap", backend,
    )
    return TokenOverlapReranker(alpha=alpha)


def _build_cross_encoder_or_fallback(settings) -> IReranker:
    alpha = settings.rag_reranker_alpha
    model_name = settings.rag_cross_encoder_model

    if not model_name:
        LOGGER.warning(
            "RAG_RERANKER_BACKEND=cross_encoder but RAG_CROSS_ENCODER_MODEL "
            "is unset; falling back to token_overlap."
        )
        return TokenOverlapReranker(alpha=alpha)

    try:
        from service.rerank.cross_encoder_reranker import CrossEncoderReranker
        # Probe sentence_transformers presence here so the failure surfaces
        # in the factory log (one place) rather than in a request handler.
        import sentence_transformers  # type: ignore[import-not-found] # noqa: F401
    except ImportError as exc:
        LOGGER.warning(
            "RAG_RERANKER_BACKEND=cross_encoder but sentence-transformers not "
            "installed (%s); install with `pip install '.[cross-encoder-rerank]'`. "
            "Falling back to token_overlap.",
            exc,
        )
        return TokenOverlapReranker(alpha=alpha)

    LOGGER.info(
        "Using CrossEncoderReranker (model=%s, alpha=%.2f) — "
        "first rerank call will pay model-load latency.",
        model_name, alpha,
    )
    return CrossEncoderReranker(model_name=model_name, alpha=alpha)
