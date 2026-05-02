from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from common.dtos import ChunkTextReqDTO, ChunkTextRespDTO
from common.return_codes import RC_OK
from common.tracing import traced
from service.chunking_service import IChunkingService

router = APIRouter(prefix="/chunk", tags=["chunking"])


def get_chunking_service(request: Request) -> IChunkingService:
    return request.app.state.chunking_service


@router.post(
    "",
    response_model=ChunkTextRespDTO,
    summary="Parent-child chunk a block of text",
    description=(
        "Implements the parent-child chunking pattern from Project A. Parents are "
        "paragraph-aligned slices ≤ `parent_size_chars`; children are length-bounded "
        "slices of their parent ≤ `child_size_chars`, broken on whitespace. Children "
        "are returned with `parent_id` linkage and `char_offset_in_parent` so the "
        "parent text can be reconstructed verbatim. Payload lives under "
        "`respCtxData` per the project DTO convention."
    ),
)
@traced("chunking.api.parent_child")
async def parent_child_chunk_handler(
    req: Annotated[ChunkTextReqDTO, Body(...)],
    svc: Annotated[IChunkingService, Depends(get_chunking_service)],
) -> ChunkTextRespDTO:
    resp = ChunkTextRespDTO()
    rc = await svc.parent_child_chunk(req, resp)
    if rc != RC_OK:
        raise HTTPException(status_code=400, detail="failed to chunk text")
    return resp
