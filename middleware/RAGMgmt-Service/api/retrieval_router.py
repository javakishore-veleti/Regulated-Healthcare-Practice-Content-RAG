from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from common.dtos import HybridRetrieveReqDTO, HybridRetrieveRespDTO
from common.return_codes import RC_OK
from common.tracing import traced
from service.retrieval_service import IRetrievalService

router = APIRouter(prefix="/retrieve", tags=["retrieval"])


def get_retrieval_service(request: Request) -> IRetrievalService:
    return request.app.state.retrieval_service


@router.post(
    "",
    response_model=HybridRetrieveRespDTO,
    summary="Hybrid retrieval (BM25 + dense + RRF)",
    description=(
        "Implements the Hybrid+Rerank pattern from the Project A Excel: lexical "
        "(Postgres ts_rank_cd / BM25-shaped) and dense (pgvector cosine) legs run "
        "in parallel, fused with Reciprocal Rank Fusion (RRF), then truncated to "
        "`top_k`. The cross-encoder rerank step is a stub for now and will swap in "
        "as a follow-up slice. Payload lives under `respCtxData.hits` per the "
        "project DTO convention."
    ),
)
@traced("retrieval.api.hybrid_search")
async def hybrid_retrieve_handler(
    req: Annotated[HybridRetrieveReqDTO, Body(...)],
    svc: Annotated[IRetrievalService, Depends(get_retrieval_service)],
) -> HybridRetrieveRespDTO:
    resp = HybridRetrieveRespDTO()
    rc = await svc.hybrid_search(req, resp)
    if rc != RC_OK:
        raise HTTPException(status_code=500, detail="hybrid retrieval failed")
    return resp
