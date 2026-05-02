from contextlib import asynccontextmanager

from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from api import config_router, datasets_router, endpoints_router, ingest_router
from common.db import build_pool
from common.otel import init_otel
from common.settings import get_settings
from dao.datasets_dao import PostgresDataSetsDao
from dao.endpoints_dao import PostgresEndpointsDao
from dao.ingest_dao import PostgresIngestDao
from service.config_service import ConfigService
from service.dag_trigger.airflow_dag_trigger import AirflowDagTrigger
from service.datasets_service import DataSetsService
from service.endpoints_service import EndpointsService
from service.ingest_service import IngestService
from service.storage.dispatcher import StorageDispatcher
from service.storage.localhost_handler import LocalhostStorageHandler


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    init_otel(settings)

    pool = await build_pool(settings)
    app.state.pool = pool

    endpoints_dao = PostgresEndpointsDao(pool)
    datasets_dao = PostgresDataSetsDao(pool)
    ingest_dao = PostgresIngestDao(pool)

    dispatcher = StorageDispatcher()
    dispatcher.register("localhost", LocalhostStorageHandler())

    dag_trigger = None
    if settings.airflow_base_url:
        dag_trigger = AirflowDagTrigger(
            base_url=settings.airflow_base_url,
            username=settings.airflow_username,
            password=settings.airflow_password,
            poll_interval_secs=settings.airflow_poll_interval_secs,
            timeout_secs=settings.airflow_timeout_secs,
        )

    app.state.endpoints_service = EndpointsService(endpoints_dao)
    app.state.datasets_service = DataSetsService(datasets_dao)
    app.state.config_service = ConfigService(settings)
    app.state.ingest_service = IngestService(
        datasets_dao=datasets_dao,
        endpoints_dao=endpoints_dao,
        ingest_dao=ingest_dao,
        dispatcher=dispatcher,
        dag_trigger=dag_trigger,
    )

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
app.include_router(ingest_router.router)
app.include_router(config_router.router)


@app.get("/health", tags=["health"], summary="Liveness probe")
async def health() -> dict[str, str]:
    return {"status": "ok"}
