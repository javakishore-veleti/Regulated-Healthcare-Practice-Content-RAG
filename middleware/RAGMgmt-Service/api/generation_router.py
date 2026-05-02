from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from common.dtos import GenerateGroundedDraftReqDTO, GenerateGroundedDraftRespDTO
from common.langfuse_client import LangfuseClient
from common.return_codes import RC_OK
from common.tracing import traced
from service.generation_service import IGenerationService

router = APIRouter(prefix="/generate", tags=["generation"])


def get_generation_service(request: Request) -> IGenerationService:
    return request.app.state.generation_service


def get_langfuse_client(request: Request) -> LangfuseClient:
    return request.app.state.langfuse_client


@router.post(
    "",
    response_model=GenerateGroundedDraftRespDTO,
    summary="Compose a compliance-grounded draft from retrieved corpus passages",
    description=(
        "Runs three-corpora-balanced hybrid retrieval (regulator + clinical "
        "evidence + practice voice) and composes a draft with numbered citations "
        "linking back to source rows. Faithfulness scoring + output guardrails "
        "run on the resulting draft before it returns. Each call also emits a "
        "single Langfuse trace (when configured) capturing topic, corpora "
        "coverage, faithfulness verdict, and guardrails verdict — the README's "
        "primary observability commitment. Payload lives under `respCtxData`."
    ),
)
@traced("generation.api.grounded_draft")
async def generate_grounded_draft_handler(
    req: Annotated[GenerateGroundedDraftReqDTO, Body(...)],
    svc: Annotated[IGenerationService, Depends(get_generation_service)],
    langfuse: Annotated[LangfuseClient, Depends(get_langfuse_client)],
) -> GenerateGroundedDraftRespDTO:
    resp = GenerateGroundedDraftRespDTO()
    rc = await svc.generate_grounded_draft(req, resp)
    if rc != RC_OK:
        raise HTTPException(status_code=500, detail="generation failed")

    # Single observability touchpoint: ship the whole composed trace from
    # respCtxData (which already carries retrieval_meta, faithfulness, guardrails,
    # draft_markdown). Disabled when Langfuse SDK isn't installed or host is unset.
    langfuse.emit_generation_trace(
        topic=req.topic,
        retrieval_mode=resp.respCtxData.get("retrieval_mode") or "three_corpora",
        resp_ctx=resp.respCtxData,
    )
    return resp
