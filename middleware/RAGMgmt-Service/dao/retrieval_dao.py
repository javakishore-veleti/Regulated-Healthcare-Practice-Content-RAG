from typing import Protocol

from psycopg_pool import AsyncConnectionPool

from common.embedding import vector_literal
from common.tracing import traced


class IRetrievalDao(Protocol):
    """Backend-agnostic interface for the two hybrid retrieval legs.

    `query_vector` is a plain list of floats (typically from `IEmbedder.embed`);
    each backend formats it into its own native shape — pgvector text-form
    literal for Postgres, raw float array for OpenSearch's k-NN clause.
    """

    async def lexical_search(
        self, query: str, top_k: int, dataset_names: list[str] | None
    ) -> list[dict]: ...

    async def dense_search(
        self,
        query_vector: list[float],
        top_k: int,
        dataset_names: list[str] | None,
    ) -> list[dict]: ...


class PostgresRetrievalDao:
    """pgvector-backed DAO. Lexical leg uses Postgres ts_rank_cd over the
    `child_text_tsv` generated column (BM25-shaped); dense leg uses pgvector's
    cosine distance operator. Both return rows shaped identically so the service
    can fuse them with RRF.

    `dataset_names`: None ⇒ no dataset filter (search the whole corpus); a list
    restricts the search via `dataset_name = ANY(...)`. The list-shape lets the
    three-corpora retrieval flow scope each leg to one corpus's dataset set
    without a separate code path.
    """

    def __init__(self, vectors_pool: AsyncConnectionPool) -> None:
        self._pool = vectors_pool

    @traced("retrieval.dao.postgres.lexical_search")
    async def lexical_search(
        self, query: str, top_k: int, dataset_names: list[str] | None
    ) -> list[dict]:
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT id, dataset_name, page_index, parent_id, child_id,
                           parent_text, child_text, char_offset_in_parent,
                           parent_heading, section_id,
                           ts_rank_cd(child_text_tsv, plainto_tsquery('english', %(q)s)) AS leg_score
                    FROM child_chunk_embeddings
                    WHERE child_text_tsv @@ plainto_tsquery('english', %(q)s)
                      AND (%(ds)s::text[] IS NULL OR dataset_name = ANY(%(ds)s::text[]))
                    ORDER BY leg_score DESC
                    LIMIT %(k)s
                    """,
                    {"q": query, "ds": dataset_names, "k": top_k},
                )
                rows = await cur.fetchall()
        return [_row_to_hit(r, leg="lexical") for r in rows]

    @traced("retrieval.dao.postgres.dense_search")
    async def dense_search(
        self,
        query_vector: list[float],
        top_k: int,
        dataset_names: list[str] | None,
    ) -> list[dict]:
        # pgvector wants the text-form literal; format it once here so the
        # service layer (and any future DAO implementations) stay agnostic.
        qv_literal = vector_literal(query_vector)
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT id, dataset_name, page_index, parent_id, child_id,
                           parent_text, child_text, char_offset_in_parent,
                           parent_heading, section_id,
                           1 - (embedding <=> %(qv)s::vector) AS leg_score
                    FROM child_chunk_embeddings
                    WHERE (%(ds)s::text[] IS NULL OR dataset_name = ANY(%(ds)s::text[]))
                    ORDER BY embedding <=> %(qv)s::vector
                    LIMIT %(k)s
                    """,
                    {
                        "qv": qv_literal,
                        "ds": dataset_names,
                        "k": top_k,
                    },
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
        "parent_heading": row[8],
        "section_id": row[9],
        "leg_score": float(row[10]) if row[10] is not None else 0.0,
        "leg": leg,
    }
