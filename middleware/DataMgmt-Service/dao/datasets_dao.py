from typing import Protocol

from psycopg_pool import AsyncConnectionPool

from common.dtos import ListDataSetsReqDTO, ListDataSetsRespDTO
from common.return_codes import RC_OK
from common.tracing import traced


class IDataSetsDao(Protocol):
    async def fetch_all(
        self, req: ListDataSetsReqDTO, resp: ListDataSetsRespDTO
    ) -> int: ...


class PostgresDataSetsDao:
    def __init__(self, pool: AsyncConnectionPool) -> None:
        self._pool = pool

    @traced("datasets.dao.fetch_all")
    async def fetch_all(
        self, req: ListDataSetsReqDTO, resp: ListDataSetsRespDTO
    ) -> int:
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT id, dataset_name, dataset_type, created_dt, updated_dt
                    FROM system_datasets
                    ORDER BY id
                    """
                )
                rows = await cur.fetchall()

        resp.respCtxData["datasets"] = [
            {
                "id": r[0],
                "dataset_name": r[1],
                "dataset_type": r[2],
                "created_dt": r[3].isoformat() if r[3] else None,
                "updated_dt": r[4].isoformat() if r[4] else None,
            }
            for r in rows
        ]
        return RC_OK
