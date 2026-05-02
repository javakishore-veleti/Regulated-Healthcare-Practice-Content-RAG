from typing import Protocol

from common.dtos import ListEndpointsReqDTO, ListEndpointsRespDTO
from common.tracing import traced
from dao.endpoints_dao import IEndpointsDao


class IEndpointsService(Protocol):
    async def list_active(
        self, req: ListEndpointsReqDTO, resp: ListEndpointsRespDTO
    ) -> int: ...


class EndpointsService:
    def __init__(self, endpoints_dao: IEndpointsDao) -> None:
        self._endpoints_dao = endpoints_dao

    @traced("endpoints.list_active")
    async def list_active(
        self, req: ListEndpointsReqDTO, resp: ListEndpointsRespDTO
    ) -> int:
        return await self._endpoints_dao.fetch_active(req, resp)
