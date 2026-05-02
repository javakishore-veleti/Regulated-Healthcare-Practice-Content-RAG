from typing import Protocol

from common.dtos import ListRagPatternsReqDTO, ListRagPatternsRespDTO
from common.tracing import traced
from dao.patterns_dao import IRagPatternsDao


class IRagPatternsService(Protocol):
    async def list_active(
        self, req: ListRagPatternsReqDTO, resp: ListRagPatternsRespDTO
    ) -> int: ...


class RagPatternsService:
    def __init__(self, patterns_dao: IRagPatternsDao) -> None:
        self._patterns_dao = patterns_dao

    @traced("patterns.list_active")
    async def list_active(
        self, req: ListRagPatternsReqDTO, resp: ListRagPatternsRespDTO
    ) -> int:
        return await self._patterns_dao.fetch_active(req, resp)
