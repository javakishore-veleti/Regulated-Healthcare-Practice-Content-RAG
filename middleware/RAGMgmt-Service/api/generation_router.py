from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from common.dtos import GenerateGroundedDraftReqDTO, GenerateGroundedDraftRespDTO
from common.return_codes import RC_OK
from common.tracing import traced
from service.generation_service import IGenerationService

router = APIRouter(prefix="/generate", tags=["generation"])


def get_generation_service(request: Request) -> IGenerationService:
    return request.app.state.generation_service


@router.post(
    "",
    response_model=GenerateGroundedDraftRespDTO,
    summary="Compose a compliance-grounded draft from retrieved corpus passages",
    description=(
        "Runs hybrid retrieval against the indexed corpus and composes a draft "
        "with numbered citations linking to source rows in "
        "`child_chunk_embeddings`. Today's implementation is a deterministic "
        "stub that emits retrieved children verbatim — no paraphrasing — to "
        "guarantee every claim maps to a citable source. A real LLM drafter "
        "(per the Excel: Bedrock Claude Opus 4.7) and the Self-RAG / guardrail "
        "layers replace this in follow-up slices. Payload lives under "
        "`respCtxData` per the project DTO convention."
    ),
)
@traced("generation.api.grounded_draft")
async def generate_grounded_draft_handler(
    req: Annotated[GenerateGroundedDraftReqDTO, Body(...)],
    svc: Annotated[IGenerationService, Depends(get_generation_service)],
) -> GenerateGroundedDraftRespDTO:
    resp = GenerateGroundedDraftRespDTO()
    rc = await svc.generate_grounded_draft(req, resp)
    if rc != RC_OK:
        raise HTTPException(status_code=500, detail="generation failed")
    return resp
