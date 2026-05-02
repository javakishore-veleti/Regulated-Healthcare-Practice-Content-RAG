from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from common.dtos import IngestDataSetReqDTO, IngestDataSetRespDTO
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
