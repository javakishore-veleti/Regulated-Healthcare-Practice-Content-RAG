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
from common.embedding_factory import build_embedder
from common.langfuse_client import LangfuseClient
from common.otel import init_otel
from common.settings import get_settings
from dao.patterns_dao import PostgresRagPatternsDao
from dao.retrieval_dao_factory import build_retrieval_dao
from service.chunking_service import ChunkingService
from service.drafters.factory import build_drafter
from service.faithfulness_service import FaithfulnessService
from service.generation_service import GenerationService
from service.guardrails.factory import build_guardrails_service
from service.patterns_service import RagPatternsService
from service.rerank.factory import build_reranker
from service.retrieval_service import RetrievalService

import logging

LOGGER = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    init_otel(settings)

    pool = await build_pool(settings)
    vectors_pool = await build_vectors_pool(settings)
    app.state.pool = pool
    app.state.vectors_pool = vectors_pool

    app.state.langfuse_client = LangfuseClient(
        host=settings.langfuse_host,
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        environment=settings.langfuse_environment,
    )

    patterns_dao = PostgresRagPatternsDao(pool)
    retrieval_dao = build_retrieval_dao(settings, vectors_pool)

    reranker = build_reranker(settings)
    embedder = build_embedder(settings)
    retrieval_service = RetrievalService(
        retrieval_dao, reranker=reranker, embedder=embedder,
    )
    guardrails_policy_path = Path(__file__).parent / "service" / "guardrails" / "policy.yaml"
    guardrails_service = build_guardrails_service(settings, guardrails_policy_path)
    faithfulness_service = FaithfulnessService()
    drafter = build_drafter(settings)

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
        try:
            app.state.langfuse_client.flush()
        except Exception:  # pragma: no cover — shutdown best-effort
            LOGGER.exception("langfuse flush on shutdown failed")
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
