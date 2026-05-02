from typing import Protocol

from psycopg_pool import AsyncConnectionPool

from common.dtos import ListEndpointsReqDTO, ListEndpointsRespDTO
from common.return_codes import RC_OK
from common.tracing import traced


class IEndpointsDao(Protocol):
    async def fetch_active(
        self, req: ListEndpointsReqDTO, resp: ListEndpointsRespDTO
    ) -> int: ...


class PostgresEndpointsDao:
    def __init__(self, pool: AsyncConnectionPool) -> None:
        self._pool = pool

    @traced("endpoints.dao.fetch_active")
    async def fetch_active(
        self, req: ListEndpointsReqDTO, resp: ListEndpointsRespDTO
    ) -> int:
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT id, endpoint_name, category, location_type, location_config_json,
                           is_active, created_dt, updated_dt
                    FROM endpoints
                    WHERE is_active = TRUE
                    ORDER BY id
                    """
                )
                rows = await cur.fetchall()

        resp.respCtxData["endpoints"] = [
            {
                "id": r[0],
                "endpoint_name": r[1],
                "category": r[2],
                "location_type": r[3],
                "location_config_json": r[4],
                "is_active": r[5],
                "created_dt": r[6].isoformat() if r[6] else None,
                "updated_dt": r[7].isoformat() if r[7] else None,
            }
            for r in rows
        ]
        return RC_OK
