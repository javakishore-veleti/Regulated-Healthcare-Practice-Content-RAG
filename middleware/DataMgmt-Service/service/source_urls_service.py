from typing import Protocol

from common.dtos import (
    AddSourceUrlReqDTO,
    AddSourceUrlRespDTO,
    DeleteSourceUrlReqDTO,
    DeleteSourceUrlRespDTO,
    ListSourceUrlsReqDTO,
    ListSourceUrlsRespDTO,
    UpdateSourceUrlReqDTO,
    UpdateSourceUrlRespDTO,
)
from common.tracing import traced
from dao.source_urls_dao import ISourceUrlsDao


class ISourceUrlsService(Protocol):
    async def list_for_dataset(
        self, req: ListSourceUrlsReqDTO, resp: ListSourceUrlsRespDTO
    ) -> int: ...

    async def add(self, req: AddSourceUrlReqDTO, resp: AddSourceUrlRespDTO) -> int: ...

    async def update(
        self, req: UpdateSourceUrlReqDTO, resp: UpdateSourceUrlRespDTO
    ) -> int: ...

    async def delete(
        self, req: DeleteSourceUrlReqDTO, resp: DeleteSourceUrlRespDTO
    ) -> int: ...


class SourceUrlsService:
    def __init__(self, dao: ISourceUrlsDao) -> None:
        self._dao = dao

    @traced("source_urls.list_for_dataset")
    async def list_for_dataset(
        self, req: ListSourceUrlsReqDTO, resp: ListSourceUrlsRespDTO
    ) -> int:
        return await self._dao.list_for_dataset(req, resp)

    @traced("source_urls.add")
    async def add(self, req: AddSourceUrlReqDTO, resp: AddSourceUrlRespDTO) -> int:
        return await self._dao.add(req, resp)

    @traced("source_urls.update")
    async def update(
        self, req: UpdateSourceUrlReqDTO, resp: UpdateSourceUrlRespDTO
    ) -> int:
        return await self._dao.update(req, resp)

    @traced("source_urls.delete")
    async def delete(
        self, req: DeleteSourceUrlReqDTO, resp: DeleteSourceUrlRespDTO
    ) -> int:
        return await self._dao.delete(req, resp)
