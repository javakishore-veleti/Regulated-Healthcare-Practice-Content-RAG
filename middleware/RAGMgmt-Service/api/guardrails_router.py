from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from common.dtos import CheckGuardrailsReqDTO, CheckGuardrailsRespDTO
from common.return_codes import RC_OK
from common.tracing import traced
from service.guardrails.guardrails_service import IGuardrailsService

router = APIRouter(prefix="/guardrails", tags=["guardrails"])


def get_guardrails_service(request: Request) -> IGuardrailsService:
    return request.app.state.guardrails_service


@router.post(
    "/check",
    response_model=CheckGuardrailsRespDTO,
    summary="Scan text for banned-phrase / forbidden-claim violations",
    description=(
        "Output guardrails per the Project A 'Output guardrails' pattern. Runs the "
        "active policy's regex rules over the supplied text and returns every match "
        "with rule id, severity, rationale, and char offsets. `passed` is True iff "
        "no violations were detected at any severity. Payload lives under "
        "`respCtxData` per the project DTO convention."
    ),
)
@traced("guardrails.api.check")
async def check_guardrails_handler(
    req: Annotated[CheckGuardrailsReqDTO, Body(...)],
    svc: Annotated[IGuardrailsService, Depends(get_guardrails_service)],
) -> CheckGuardrailsRespDTO:
    resp = CheckGuardrailsRespDTO()
    rc = await svc.check_text(req, resp)
    if rc != RC_OK:
        raise HTTPException(status_code=500, detail="guardrails check failed")
    return resp
