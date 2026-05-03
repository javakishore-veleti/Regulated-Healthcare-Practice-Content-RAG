"""rag_iface — Excel Project A Task 13: provider-agnostic public interface.

Re-exports the load-bearing Protocols and `build_*` factories that the rest
of the service uses internally, so external callers / smoke CLIs can
import from `rag_iface` rather than digging into `dao/` or `service/`.

The factories already make every component swappable per env var:

    Drafter          LLM_DRAFTER ∈ {auto, anthropic, bedrock, stub}
    Embedder         RAG_EMBEDDER_BACKEND ∈ {stub, sentence_transformer, aws_bedrock}
    Reranker         RAG_RERANKER_BACKEND ∈ {identity, token_overlap, cross_encoder}
    Retrieval DAO    RAG_RETRIEVAL_BACKEND ∈ {postgres, aws_opensearch_serverless}
    Guardrails       RAG_GUARDRAILS_BACKEND ∈ {regex, bedrock, layered}

A `--cloud aws|local` preset (see `cloud_presets.apply_preset`) flips all
of these together — operators don't need to remember each variable.

PEP 562 lazy attribute resolution: heavy imports (psycopg_pool, opensearchpy,
boto3, sentence-transformers, etc.) are loaded on first access of the
corresponding name, NOT at `import rag_iface` time. This lets the
lightweight `cloud_presets` and CLI `describe` subcommand work from a bare
Python without the full service venv.
"""

from __future__ import annotations

# Light imports only — these have no heavy deps and are cheap to load.
from rag_iface.cloud_presets import (
    AVAILABLE_PRESETS,
    apply_preset,
    describe_preset,
)


__all__ = [
    # Protocols (lazy):
    "IDrafter",
    "IEmbedder",
    "IGuardrailsService",
    "IReranker",
    "IRetrievalDao",
    # Default implementations (lazy):
    "GuardrailsService",
    "IdentityReranker",
    "PostgresRetrievalDao",
    "StubEmbedder",
    "TokenOverlapReranker",
    # Factories (lazy):
    "build_drafter",
    "build_embedder",
    "build_guardrails_service",
    "build_reranker",
    "build_retrieval_dao",
    # Cloud presets (eager):
    "AVAILABLE_PRESETS",
    "apply_preset",
    "describe_preset",
]


# PEP 562 lazy attribute resolution. Maps each lazily-exposed name to the
# (module_path, attribute_name) it resolves to. The module is imported only
# when the name is accessed.
_LAZY_TARGETS: dict[str, tuple[str, str]] = {
    # Protocols + default implementations.
    "IDrafter": ("service.drafters.drafter", "IDrafter"),
    "IEmbedder": ("common.embedding", "IEmbedder"),
    "IGuardrailsService": ("service.guardrails.guardrails_service", "IGuardrailsService"),
    "IReranker": ("service.rerank.reranker", "IReranker"),
    "IRetrievalDao": ("dao.retrieval_dao", "IRetrievalDao"),
    "GuardrailsService": ("service.guardrails.guardrails_service", "GuardrailsService"),
    "IdentityReranker": ("service.rerank.reranker", "IdentityReranker"),
    "PostgresRetrievalDao": ("dao.retrieval_dao", "PostgresRetrievalDao"),
    "StubEmbedder": ("common.embedding", "StubEmbedder"),
    "TokenOverlapReranker": ("service.rerank.reranker", "TokenOverlapReranker"),
    # Factories.
    "build_drafter": ("service.drafters.factory", "build_drafter"),
    "build_embedder": ("common.embedding_factory", "build_embedder"),
    "build_guardrails_service": ("service.guardrails.factory", "build_guardrails_service"),
    "build_reranker": ("service.rerank.factory", "build_reranker"),
    "build_retrieval_dao": ("dao.retrieval_dao_factory", "build_retrieval_dao"),
}


def __getattr__(name: str):
    target = _LAZY_TARGETS.get(name)
    if target is None:
        raise AttributeError(f"module 'rag_iface' has no attribute {name!r}")
    module_path, attr = target
    import importlib
    module = importlib.import_module(module_path)
    value = getattr(module, attr)
    globals()[name] = value  # cache for subsequent accesses
    return value
