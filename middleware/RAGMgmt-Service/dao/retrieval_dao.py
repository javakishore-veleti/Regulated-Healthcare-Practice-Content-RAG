from typing import Protocol

from psycopg_pool import AsyncConnectionPool

from common.tracing import traced


class IRetrievalDao(Protocol):
    async def lexical_search(
        self, query: str, top_k: int, dataset_name: str | None
    ) -> list[dict]: ...

    async def dense_search(
        self, query_vector_literal: str, top_k: int, dataset_name: str | None
    ) -> list[dict]: ...


class PostgresRetrievalDao:
    """Reads from the rag_vectors DB. Lexical leg uses Postgres ts_rank_cd over the
    `child_text_tsv` generated column (BM25-shaped); dense leg uses pgvector's
    cosine distance operator. Both return rows shaped identically so the service
    can fuse them with RRF."""

    def __init__(self, vectors_pool: AsyncConnectionPool) -> None:
        self._pool = vectors_pool

    @traced("retrieval.dao.lexical_search")
    async def lexical_search(
        self, query: str, top_k: int, dataset_name: str | None
    ) -> list[dict]:
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT id, dataset_name, page_index, parent_id, child_id,
                           parent_text, child_text, char_offset_in_parent,
                           ts_rank_cd(child_text_tsv, plainto_tsquery('english', %(q)s)) AS leg_score
                    FROM child_chunk_embeddings
                    WHERE child_text_tsv @@ plainto_tsquery('english', %(q)s)
                      AND (%(ds)s::text IS NULL OR dataset_name = %(ds)s::text)
                    ORDER BY leg_score DESC
                    LIMIT %(k)s
                    """,
                    {"q": query, "ds": dataset_name, "k": top_k},
                )
                rows = await cur.fetchall()
        return [_row_to_hit(r, leg="lexical") for r in rows]

    @traced("retrieval.dao.dense_search")
    async def dense_search(
        self, query_vector_literal: str, top_k: int, dataset_name: str | None
    ) -> list[dict]:
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT id, dataset_name, page_index, parent_id, child_id,
                           parent_text, child_text, char_offset_in_parent,
                           1 - (embedding <=> %(qv)s::vector) AS leg_score
                    FROM child_chunk_embeddings
                    WHERE (%(ds)s::text IS NULL OR dataset_name = %(ds)s::text)
                    ORDER BY embedding <=> %(qv)s::vector
                    LIMIT %(k)s
                    """,
                    {"qv": query_vector_literal, "ds": dataset_name, "k": top_k},
                )
                rows = await cur.fetchall()
        return [_row_to_hit(r, leg="dense") for r in rows]


def _row_to_hit(row, leg: str) -> dict:
    return {
        "id": row[0],
        "dataset_name": row[1],
        "page_index": row[2],
        "parent_id": row[3],
        "child_id": row[4],
        "parent_text": row[5],
        "child_text": row[6],
        "char_offset_in_parent": row[7],
        "leg_score": float(row[8]) if row[8] is not None else 0.0,
        "leg": leg,
    }
