"""Retrieval-DAO selection factory — pick `IRetrievalDao` per
`Settings.rag_retrieval_backend`. Same fall-back pattern as the drafter /
reranker / embedder factories: never raises; falls back to PostgresRetrievalDao
when an opt-in backend is misconfigured.

Backends:
  * `postgres`                  — PostgresRetrievalDao (default).
  * `aws_opensearch_serverless` — OpenSearchRetrievalDao (requires
                                   `[opensearch]` extra + AWS_OPENSEARCH_*
                                   env vars; falls back to postgres when
                                   missing).
"""

from __future__ import annotations

import logging

from dao.retrieval_dao import IRetrievalDao, PostgresRetrievalDao

LOGGER = logging.getLogger(__name__)


def build_retrieval_dao(settings, vectors_pool) -> IRetrievalDao:
    backend = (settings.rag_retrieval_backend or "postgres").lower()

    if backend == "postgres":
        LOGGER.info("Using PostgresRetrievalDao (pgvector + tsvector hybrid)")
        return PostgresRetrievalDao(vectors_pool)

    if backend == "aws_opensearch_serverless":
        return _build_opensearch_or_fallback(settings, vectors_pool)

    LOGGER.warning(
        "Unknown RAG_RETRIEVAL_BACKEND=%r — falling back to postgres", backend,
    )
    return PostgresRetrievalDao(vectors_pool)


def _build_opensearch_or_fallback(settings, vectors_pool) -> IRetrievalDao:
    if not settings.aws_opensearch_endpoint:
        LOGGER.warning(
            "RAG_RETRIEVAL_BACKEND=aws_opensearch_serverless but "
            "AWS_OPENSEARCH_ENDPOINT is unset; falling back to postgres."
        )
        return PostgresRetrievalDao(vectors_pool)

    try:
        from dao.opensearch_retrieval_dao import OpenSearchRetrievalDao
        # Probe the heavy deps once at factory time — single failure point in
        # the log instead of N per-request import errors.
        import boto3  # type: ignore[import-not-found] # noqa: F401
        import opensearchpy  # type: ignore[import-not-found] # noqa: F401
    except ImportError as exc:
        LOGGER.warning(
            "RAG_RETRIEVAL_BACKEND=aws_opensearch_serverless but optional deps "
            "not installed (%s); install with `pip install '.[opensearch]'`. "
            "Falling back to postgres.",
            exc,
        )
        return PostgresRetrievalDao(vectors_pool)

    LOGGER.info(
        "Using OpenSearchRetrievalDao (endpoint=%s, index=%s, region=%s)",
        settings.aws_opensearch_endpoint,
        settings.aws_opensearch_index,
        settings.aws_opensearch_region,
    )
    return OpenSearchRetrievalDao(
        endpoint=settings.aws_opensearch_endpoint,
        index=settings.aws_opensearch_index,
        region=settings.aws_opensearch_region,
    )
