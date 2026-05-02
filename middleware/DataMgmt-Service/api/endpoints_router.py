from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from common.dtos import ListEndpointsReqDTO, ListEndpointsRespDTO
from common.return_codes import RC_OK
from common.tracing import traced
from service.endpoints_service import IEndpointsService

router = APIRouter(prefix="/endpoints", tags=["endpoints"])


def get_endpoints_service(request: Request) -> IEndpointsService:
    return request.app.state.endpoints_service


@router.get(
    "",
    response_model=ListEndpointsRespDTO,
    summary="List all active endpoints",
    description=(
        "Returns every active row from the `endpoints` table. The payload lives under "
        "`respCtxData.endpoints` per the project's DTO convention."
    ),
)
@traced("endpoints.api.list")
async def list_endpoints_handler(
    svc: Annotated[IEndpointsService, Depends(get_endpoints_service)],
) -> ListEndpointsRespDTO:
    req = ListEndpointsReqDTO()
    resp = ListEndpointsRespDTO()
    rc = await svc.list_active(req, resp)
    if rc != RC_OK:
        raise HTTPException(status_code=500, detail="failed to list endpoints")
    return resp
