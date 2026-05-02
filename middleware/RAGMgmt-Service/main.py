from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from api import (
    chunking_router,
    faithfulness_router,
    generation_router,
    guardrails_router,
    patterns_router,
    retrieval_router,
)
from common.db import build_pool, build_vectors_pool
from common.otel import init_otel
from common.settings import get_settings
from dao.patterns_dao import PostgresRagPatternsDao
from dao.retrieval_dao import PostgresRetrievalDao
from service.chunking_service import ChunkingService
from service.drafters.anthropic_drafter import AnthropicDrafter
from service.drafters.drafter import IDrafter
from service.drafters.stub_drafter import StubDrafter
from service.faithfulness_service import FaithfulnessService
from service.generation_service import GenerationService
from service.guardrails.guardrails_service import GuardrailsService
from service.patterns_service import RagPatternsService
from service.rerank.reranker import (
    IdentityReranker,
    IReranker,
    TokenOverlapReranker,
)
from service.retrieval_service import RetrievalService

import logging

LOGGER = logging.getLogger(__name__)


def _build_reranker(settings) -> IReranker:
    """Pick a reranker per `RAG_RERANKER_BACKEND`. Defaults to token_overlap.

    Adding a real cross-encoder backend means: implement IReranker, instantiate
    here under a new branch, and add the dep to pyproject extras (gated so the
    base image stays small).
    """
    backend = (settings.rag_reranker_backend or "token_overlap").lower()
    if backend == "identity":
        LOGGER.info("Using IdentityReranker (passthrough truncation)")
        return IdentityReranker()
    if backend == "token_overlap":
        LOGGER.info(
            "Using TokenOverlapReranker (alpha=%.2f)", settings.rag_reranker_alpha
        )
        return TokenOverlapReranker(alpha=settings.rag_reranker_alpha)
    LOGGER.warning(
        "Unknown RAG_RERANKER_BACKEND=%r — falling back to token_overlap", backend
    )
    return TokenOverlapReranker(alpha=settings.rag_reranker_alpha)


def _build_drafter(settings) -> IDrafter:
    """Pick a drafter per `LLM_DRAFTER`. `auto` uses Anthropic when the key is set.

    `ANTHROPIC_API_KEY` is already resolved at Settings load time — literal
    values pass through; `aws-sm://...`, `azure-kv://...`, `gcp-sm://...`
    references are resolved against the appropriate cloud secret manager.
    See common/secrets.py and the field_validator on Settings.
    """
    mode = (settings.llm_drafter or "auto").lower()
    api_key = settings.anthropic_api_key
    if mode in ("anthropic", "auto") and api_key:
        LOGGER.info("Using AnthropicDrafter with model=%s", settings.anthropic_model)
        return AnthropicDrafter(
            api_key=api_key,
            model=settings.anthropic_model,
            max_tokens=settings.anthropic_max_tokens,
        )
    if mode == "anthropic":
        LOGGER.warning(
            "LLM_DRAFTER=anthropic but ANTHROPIC_API_KEY is unset / unresolved; "
            "falling back to stub."
        )
    LOGGER.info("Using StubDrafter (deterministic, no LLM call)")
    return StubDrafter()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    init_otel(settings)

    pool = await build_pool(settings)
    vectors_pool = await build_vectors_pool(settings)
    app.state.pool = pool
    app.state.vectors_pool = vectors_pool

    patterns_dao = PostgresRagPatternsDao(pool)
    retrieval_dao = PostgresRetrievalDao(vectors_pool)

    reranker = _build_reranker(settings)
    retrieval_service = RetrievalService(retrieval_dao, reranker=reranker)
    guardrails_policy_path = Path(__file__).parent / "service" / "guardrails" / "policy.yaml"
    guardrails_service = GuardrailsService(policy_path=guardrails_policy_path)
    faithfulness_service = FaithfulnessService()
    drafter = _build_drafter(settings)

    app.state.patterns_service = RagPatternsService(patterns_dao)
    app.state.chunking_service = ChunkingService()
    app.state.retrieval_service = retrieval_service
    app.state.guardrails_service = guardrails_service
    app.state.faithfulness_service = faithfulness_service
    app.state.generation_service = GenerationService(
        retrieval_service=retrieval_service,
        drafter=drafter,
        guardrails_service=guardrails_service,
        faithfulness_service=faithfulness_service,
        max_regenerate_attempts=settings.max_regenerate_attempts,
    )

    try:
        yield
    finally:
        await pool.close()
        await vectors_pool.close()


app = FastAPI(
    title="RAGMgmt-Service",
    version="0.1.0",
    description=(
        "RAG management for the Regulated Healthcare RAG stack: pattern catalog, "
        "chunking, embedding, retrieval, generation. Owns the four Project A patterns "
        "from the Excel (Hybrid+Rerank, Parent-Child, Self-RAG, Output Guardrails)."
    ),
    lifespan=lifespan,
)

FastAPIInstrumentor.instrument_app(app)

app.include_router(patterns_router.router)
app.include_router(chunking_router.router)
app.include_router(retrieval_router.router)
app.include_router(generation_router.router)
app.include_router(guardrails_router.router)
app.include_router(faithfulness_router.router)


@app.get("/health", tags=["health"], summary="Liveness probe")
async def health() -> dict[str, str]:
    return {"status": "ok"}
