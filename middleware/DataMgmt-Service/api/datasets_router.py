from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from common.dtos import ListDataSetsReqDTO, ListDataSetsRespDTO
from common.return_codes import RC_OK
from common.tracing import traced
from service.datasets_service import IDataSetsService

router = APIRouter(prefix="/datasets", tags=["datasets"])


def get_datasets_service(request: Request) -> IDataSetsService:
    return request.app.state.datasets_service


@router.get(
    "",
    response_model=ListDataSetsRespDTO,
    summary="List all datasets",
    description=(
        "Returns every row from the `system_datasets` catalog. The payload lives under "
        "`respCtxData.datasets` per the project's DTO convention."
    ),
)
@traced("datasets.api.list")
async def list_datasets_handler(
    svc: Annotated[IDataSetsService, Depends(get_datasets_service)],
) -> ListDataSetsRespDTO:
    req = ListDataSetsReqDTO()
    resp = ListDataSetsRespDTO()
    rc = await svc.list_all(req, resp)
    if rc != RC_OK:
        raise HTTPException(status_code=500, detail="failed to list datasets")
    return resp
