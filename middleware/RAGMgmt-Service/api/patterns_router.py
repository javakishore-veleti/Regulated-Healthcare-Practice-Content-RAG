from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from common.dtos import ListRagPatternsReqDTO, ListRagPatternsRespDTO
from common.return_codes import RC_OK
from common.tracing import traced
from service.patterns_service import IRagPatternsService

router = APIRouter(prefix="/patterns", tags=["patterns"])


def get_patterns_service(request: Request) -> IRagPatternsService:
    return request.app.state.patterns_service


@router.get(
    "",
    response_model=ListRagPatternsRespDTO,
    summary="List the active RAG patterns",
    description=(
        "Returns every active row from `rag_patterns` (the four Project A patterns "
        "from the Excel: Hybrid+Rerank, Parent-Child, Self-RAG, Output Guardrails). "
        "Payload lives under `respCtxData.patterns` per the project DTO convention."
    ),
)
@traced("patterns.api.list")
async def list_patterns_handler(
    svc: Annotated[IRagPatternsService, Depends(get_patterns_service)],
) -> ListRagPatternsRespDTO:
    req = ListRagPatternsReqDTO()
    resp = ListRagPatternsRespDTO()
    rc = await svc.list_active(req, resp)
    if rc != RC_OK:
        raise HTTPException(status_code=500, detail="failed to list patterns")
    return resp
