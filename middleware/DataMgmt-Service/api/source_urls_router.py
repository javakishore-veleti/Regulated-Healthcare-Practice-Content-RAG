from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Request

from common.dtos import (
    AddSourceUrlBodyDTO,
    AddSourceUrlReqDTO,
    AddSourceUrlRespDTO,
    DeleteSourceUrlReqDTO,
    DeleteSourceUrlRespDTO,
    ListSourceUrlsReqDTO,
    ListSourceUrlsRespDTO,
    UpdateSourceUrlBodyDTO,
    UpdateSourceUrlReqDTO,
    UpdateSourceUrlRespDTO,
)
from common.return_codes import RC_NOT_FOUND, RC_OK, RC_VALIDATION_ERROR
from common.tracing import traced
from service.source_urls_service import ISourceUrlsService

router = APIRouter(tags=["source-urls"])


def get_source_urls_service(request: Request) -> ISourceUrlsService:
    return request.app.state.source_urls_service


def _http_for_rc(rc: int, resp_ctx: dict) -> int:
    if rc == RC_NOT_FOUND:
        return 404
    if rc == RC_VALIDATION_ERROR:
        return 400
    return 500


@router.get(
    "/datasets/{dataset_name}/source-urls",
    response_model=ListSourceUrlsRespDTO,
    summary="List curated source URLs for a dataset",
    description=(
        "Returns admin-curated `dataset_source_urls` rows for the dataset, ordered by "
        "(`position` ASC, `id` ASC). The regulator-guidelines fetcher reads the same "
        "list at DAG run time. Payload lives under `respCtxData.source_urls`."
    ),
)
@traced("source_urls.api.list")
async def list_source_urls_handler(
    dataset_name: Annotated[str, Path(...)],
    only_active: Annotated[bool, Query()] = False,
    svc: ISourceUrlsService = Depends(get_source_urls_service),
) -> ListSourceUrlsRespDTO:
    req = ListSourceUrlsReqDTO(dataset_name=dataset_name, only_active=only_active)
    resp = ListSourceUrlsRespDTO()
    rc = await svc.list_for_dataset(req, resp)
    if rc != RC_OK:
        raise HTTPException(
            status_code=_http_for_rc(rc, resp.respCtxData),
            detail=resp.respCtxData.get("error", "failed to list source urls"),
        )
    return resp


@router.post(
    "/datasets/{dataset_name}/source-urls",
    response_model=AddSourceUrlRespDTO,
    summary="Add a curated source URL to a dataset",
)
@traced("source_urls.api.add")
async def add_source_url_handler(
    dataset_name: Annotated[str, Path(...)],
    body: Annotated[AddSourceUrlBodyDTO, Body(...)],
    svc: ISourceUrlsService = Depends(get_source_urls_service),
) -> AddSourceUrlRespDTO:
    req = AddSourceUrlReqDTO(
        dataset_name=dataset_name,
        url=body.url,
        label=body.label,
        is_active=body.is_active,
        position=body.position,
        notes=body.notes,
    )
    resp = AddSourceUrlRespDTO()
    rc = await svc.add(req, resp)
    if rc != RC_OK:
        raise HTTPException(
            status_code=_http_for_rc(rc, resp.respCtxData),
            detail=resp.respCtxData.get("error", "failed to add source url"),
        )
    return resp


@router.patch(
    "/source-urls/{id}",
    response_model=UpdateSourceUrlRespDTO,
    summary="Update a source URL (toggle active, reorder, re-label, edit notes)",
)
@traced("source_urls.api.update")
async def update_source_url_handler(
    id: Annotated[int, Path(...)],
    body: Annotated[UpdateSourceUrlBodyDTO, Body(...)],
    svc: ISourceUrlsService = Depends(get_source_urls_service),
) -> UpdateSourceUrlRespDTO:
    req = UpdateSourceUrlReqDTO(
        id=id,
        is_active=body.is_active,
        position=body.position,
        label=body.label,
        notes=body.notes,
    )
    resp = UpdateSourceUrlRespDTO()
    rc = await svc.update(req, resp)
    if rc != RC_OK:
        raise HTTPException(
            status_code=_http_for_rc(rc, resp.respCtxData),
            detail=resp.respCtxData.get("error", "failed to update source url"),
        )
    return resp


@router.delete(
    "/source-urls/{id}",
    response_model=DeleteSourceUrlRespDTO,
    summary="Delete a source URL",
)
@traced("source_urls.api.delete")
async def delete_source_url_handler(
    id: Annotated[int, Path(...)],
    svc: ISourceUrlsService = Depends(get_source_urls_service),
) -> DeleteSourceUrlRespDTO:
    req = DeleteSourceUrlReqDTO(id=id)
    resp = DeleteSourceUrlRespDTO()
    rc = await svc.delete(req, resp)
    if rc != RC_OK:
        raise HTTPException(
            status_code=_http_for_rc(rc, resp.respCtxData),
            detail=resp.respCtxData.get("error", "failed to delete source url"),
        )
    return resp
