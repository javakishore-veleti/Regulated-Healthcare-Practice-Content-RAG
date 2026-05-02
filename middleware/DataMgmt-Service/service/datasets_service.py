from typing import Protocol

from common.dtos import ListDataSetsReqDTO, ListDataSetsRespDTO
from common.tracing import traced
from dao.datasets_dao import IDataSetsDao


class IDataSetsService(Protocol):
    async def list_all(
        self, req: ListDataSetsReqDTO, resp: ListDataSetsRespDTO
    ) -> int: ...


class DataSetsService:
    def __init__(self, datasets_dao: IDataSetsDao) -> None:
        self._datasets_dao = datasets_dao

    @traced("datasets.list_all")
    async def list_all(
        self, req: ListDataSetsReqDTO, resp: ListDataSetsRespDTO
    ) -> int:
        return await self._datasets_dao.fetch_all(req, resp)
