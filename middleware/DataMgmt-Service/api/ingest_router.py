from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request

from common.dtos import (
    IngestDataSetReqDTO,
    IngestDataSetRespDTO,
    ListIngestRunsReqDTO,
    ListIngestRunsRespDTO,
)
from common.return_codes import RC_NOT_FOUND, RC_OK
from common.tracing import traced
from service.ingest_service import IIngestService

router = APIRouter(prefix="/ingest", tags=["ingest"])


def get_ingest_service(request: Request) -> IIngestService:
    return request.app.state.ingest_service


@router.post(
    "",
    response_model=IngestDataSetRespDTO,
    summary="Trigger an ingest run for a dataset against a specific endpoint",
    description=(
        "Looks up the dataset and endpoint by name, applies the localhost cache-hit "
        "short-circuit when applicable, otherwise records an in_progress row in "
        "`system_datasets_ingest`, dispatches to the storage handler for the endpoint's "
        "`location_type`, and updates the row to `success` / `failure` / "
        "`skipped_cache_hit`. The full state lives in `respCtxData`."
    ),
)
@traced("ingest.api.start")
async def start_ingest_handler(
    req: Annotated[IngestDataSetReqDTO, Body(...)],
    svc: Annotated[IIngestService, Depends(get_ingest_service)],
) -> IngestDataSetRespDTO:
    resp = IngestDataSetRespDTO()
    rc = await svc.start_ingest(req, resp)
    if rc == RC_NOT_FOUND:
        raise HTTPException(
            status_code=404, detail=resp.respCtxData.get("error", "not found")
        )
    if rc != RC_OK:
        raise HTTPException(
            status_code=400,
            detail=resp.respCtxData.get("error_text", "ingest failed to start"),
        )
    return resp


@router.get(
    "/runs",
    response_model=ListIngestRunsRespDTO,
    summary="List ingest run history with optional filters",
    description=(
        "Joined view over `system_datasets_ingest`, `system_datasets`, and `endpoints`. "
        "Filter by `dataset_name` and/or `endpoint_name`; results are paginated via "
        "`limit` and `offset` and ordered by `ingest_start_dt DESC`. Payload lives "
        "under `respCtxData.ingest_runs` per the project's DTO convention."
    ),
)
@traced("ingest.api.list_runs")
async def list_ingest_runs_handler(
    req: Annotated[ListIngestRunsReqDTO, Query()],
    svc: Annotated[IIngestService, Depends(get_ingest_service)],
) -> ListIngestRunsRespDTO:
    resp = ListIngestRunsRespDTO()
    rc = await svc.list_runs(req, resp)
    if rc != RC_OK:
        raise HTTPException(
            status_code=500,
            detail=resp.respCtxData.get("error_text", "failed to list ingest runs"),
        )
    return resp
