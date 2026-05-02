from contextlib import asynccontextmanager

from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from api import chunking_router, patterns_router
from common.db import build_pool
from common.otel import init_otel
from common.settings import get_settings
from dao.patterns_dao import PostgresRagPatternsDao
from service.chunking_service import ChunkingService
from service.patterns_service import RagPatternsService


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    init_otel(settings)

    pool = await build_pool(settings)
    app.state.pool = pool

    patterns_dao = PostgresRagPatternsDao(pool)
    app.state.patterns_service = RagPatternsService(patterns_dao)
    app.state.chunking_service = ChunkingService()

    try:
        yield
    finally:
        await pool.close()


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


@app.get("/health", tags=["health"], summary="Liveness probe")
async def health() -> dict[str, str]:
    return {"status": "ok"}
