from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from api import (
    chunking_router,
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
from service.generation_service import GenerationService
from service.guardrails.guardrails_service import GuardrailsService
from service.patterns_service import RagPatternsService
from service.retrieval_service import RetrievalService


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

    retrieval_service = RetrievalService(retrieval_dao)
    guardrails_policy_path = Path(__file__).parent / "service" / "guardrails" / "policy.yaml"
    guardrails_service = GuardrailsService(policy_path=guardrails_policy_path)

    app.state.patterns_service = RagPatternsService(patterns_dao)
    app.state.chunking_service = ChunkingService()
    app.state.retrieval_service = retrieval_service
    app.state.generation_service = GenerationService(retrieval_service)
    app.state.guardrails_service = guardrails_service

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


@app.get("/health", tags=["health"], summary="Liveness probe")
async def health() -> dict[str, str]:
    return {"status": "ok"}
