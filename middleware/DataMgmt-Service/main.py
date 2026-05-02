from contextlib import asynccontextmanager

from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from api import datasets_router, endpoints_router
from common.db import build_pool
from common.otel import init_otel
from common.settings import get_settings
from dao.datasets_dao import PostgresDataSetsDao
from dao.endpoints_dao import PostgresEndpointsDao
from service.datasets_service import DataSetsService
from service.endpoints_service import EndpointsService


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    init_otel(settings)

    pool = await build_pool(settings)
    app.state.pool = pool

    endpoints_dao = PostgresEndpointsDao(pool)
    datasets_dao = PostgresDataSetsDao(pool)
    app.state.endpoints_service = EndpointsService(endpoints_dao)
    app.state.datasets_service = DataSetsService(datasets_dao)

    try:
        yield
    finally:
        await pool.close()


app = FastAPI(
    title="DataMgmt-Service",
    version="0.1.0",
    description=(
        "Dataset cataloging, endpoint configuration, and ingest orchestration for the "
        "Regulated Healthcare RAG stack."
    ),
    lifespan=lifespan,
)

FastAPIInstrumentor.instrument_app(app)

app.include_router(endpoints_router.router)
app.include_router(datasets_router.router)


@app.get("/health", tags=["health"], summary="Liveness probe")
async def health() -> dict[str, str]:
    return {"status": "ok"}
