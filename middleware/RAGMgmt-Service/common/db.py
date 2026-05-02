from psycopg_pool import AsyncConnectionPool

from common.settings import Settings


async def build_pool(settings: Settings) -> AsyncConnectionPool:
    pool = AsyncConnectionPool(
        conninfo=settings.db_conninfo,
        min_size=settings.db_pool_min_size,
        max_size=settings.db_pool_max_size,
        open=False,
    )
    await pool.open()
    return pool
