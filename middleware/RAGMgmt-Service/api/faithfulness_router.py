from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from common.dtos import CheckFaithfulnessReqDTO, CheckFaithfulnessRespDTO
from common.return_codes import RC_OK
from common.tracing import traced
from service.faithfulness_service import IFaithfulnessService

router = APIRouter(prefix="/faithfulness", tags=["faithfulness"])


def get_faithfulness_service(request: Request) -> IFaithfulnessService:
    return request.app.state.faithfulness_service


@router.post(
    "/check",
    response_model=CheckFaithfulnessRespDTO,
    summary="Score a draft against its citations (Self-RAG)",
    description=(
        "Self-RAG faithfulness scoring per the Project A pattern. Splits the text "
        "into sentences (skipping markdown structure), measures token overlap with "
        "the union of citation snippets, and reports per-sentence + overall scores. "
        "`passed` is True iff overall score ≥ overall_threshold. The stub scorer is "
        "deterministic; a Bedrock Claude Haiku critic replaces it later. Payload "
        "lives under `respCtxData` per the project DTO convention."
    ),
)
@traced("faithfulness.api.check")
async def check_faithfulness_handler(
    req: Annotated[CheckFaithfulnessReqDTO, Body(...)],
    svc: Annotated[IFaithfulnessService, Depends(get_faithfulness_service)],
) -> CheckFaithfulnessRespDTO:
    resp = CheckFaithfulnessRespDTO()
    rc = await svc.check_text(req, resp)
    if rc != RC_OK:
        raise HTTPException(status_code=500, detail="faithfulness check failed")
    return resp
