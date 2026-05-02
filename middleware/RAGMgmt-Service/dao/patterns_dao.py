from typing import Protocol

from psycopg_pool import AsyncConnectionPool

from common.dtos import ListRagPatternsReqDTO, ListRagPatternsRespDTO
from common.return_codes import RC_OK
from common.tracing import traced


class IRagPatternsDao(Protocol):
    async def fetch_active(
        self, req: ListRagPatternsReqDTO, resp: ListRagPatternsRespDTO
    ) -> int: ...


class PostgresRagPatternsDao:
    def __init__(self, pool: AsyncConnectionPool) -> None:
        self._pool = pool

    @traced("patterns.dao.fetch_active")
    async def fetch_active(
        self, req: ListRagPatternsReqDTO, resp: ListRagPatternsRespDTO
    ) -> int:
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT id, pattern_key, display_name, summary, excel_source,
                           is_active, created_dt, updated_dt
                    FROM rag_patterns
                    WHERE is_active = TRUE
                    ORDER BY id
                    """
                )
                rows = await cur.fetchall()

        resp.respCtxData["patterns"] = [
            {
                "id": r[0],
                "pattern_key": r[1],
                "display_name": r[2],
                "summary": r[3],
                "excel_source": r[4],
                "is_active": r[5],
                "created_dt": r[6].isoformat() if r[6] else None,
                "updated_dt": r[7].isoformat() if r[7] else None,
            }
            for r in rows
        ]
        return RC_OK
