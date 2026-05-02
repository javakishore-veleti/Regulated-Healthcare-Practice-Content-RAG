from psycopg_pool import AsyncConnectionPool

from common.settings import Settings


async def build_pool(settings: Settings) -> AsyncConnectionPool:
    """Pool for the rag_app DB (patterns, future state)."""
    return await _build_pool_for(settings, settings.db_conninfo)


async def build_vectors_pool(settings: Settings) -> AsyncConnectionPool:
    """Separate pool for the rag_vectors DB (pgvector embeddings + retrieval)."""
    return await _build_pool_for(settings, settings.rag_vectors_db_conninfo)


async def _build_pool_for(settings: Settings, conninfo: str) -> AsyncConnectionPool:
    pool = AsyncConnectionPool(
        conninfo=conninfo,
        min_size=settings.db_pool_min_size,
        max_size=settings.db_pool_max_size,
        open=False,
    )
    await pool.open()
    return pool
