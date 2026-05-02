from typing import Protocol

from psycopg_pool import AsyncConnectionPool

from common.dtos import (
    IngestDataSetReqDTO,
    IngestDataSetRespDTO,
    ListIngestRunsReqDTO,
    ListIngestRunsRespDTO,
)
from common.return_codes import RC_OK
from common.tracing import traced


class IIngestDao(Protocol):
    async def find_latest_success_for_ingest(
        self, req: IngestDataSetReqDTO, resp: IngestDataSetRespDTO
    ) -> int: ...

    async def create_run_for_ingest(
        self, req: IngestDataSetReqDTO, resp: IngestDataSetRespDTO
    ) -> int: ...

    async def mark_status_for_ingest(
        self, req: IngestDataSetReqDTO, resp: IngestDataSetRespDTO
    ) -> int: ...

    async def list_runs(
        self, req: ListIngestRunsReqDTO, resp: ListIngestRunsRespDTO
    ) -> int: ...


class PostgresIngestDao:
    def __init__(self, pool: AsyncConnectionPool) -> None:
        self._pool = pool

    @traced("ingest.dao.find_latest_success")
    async def find_latest_success_for_ingest(
        self, req: IngestDataSetReqDTO, resp: IngestDataSetRespDTO
    ) -> int:
        ctx = resp.respCtxData
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT id, last_ingest_dt
                    FROM system_datasets_ingest
                    WHERE system_dataset_id = %s
                      AND endpoint_id = %s
                      AND ingest_status = 'success'
                    ORDER BY last_ingest_dt DESC NULLS LAST, id DESC
                    LIMIT 1
                    """,
                    (ctx["dataset_id"], ctx["endpoint_id"]),
                )
                row = await cur.fetchone()

        if row is None:
            ctx["latest_success_id"] = None
            ctx["latest_success_dt"] = None
        else:
            ctx["latest_success_id"] = row[0]
            ctx["latest_success_dt"] = row[1].isoformat() if row[1] else None
        return RC_OK

    @traced("ingest.dao.create_run")
    async def create_run_for_ingest(
        self, req: IngestDataSetReqDTO, resp: IngestDataSetRespDTO
    ) -> int:
        ctx = resp.respCtxData
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO system_datasets_ingest
                        (system_dataset_id, endpoint_id, ingest_status, configs_json)
                    VALUES (%s, %s, %s, %s::jsonb)
                    RETURNING id, ingest_start_dt
                    """,
                    (
                        ctx["dataset_id"],
                        ctx["endpoint_id"],
                        ctx["ingest_status"],
                        ctx.get("configs_json_text", "{}"),
                    ),
                )
                row = await cur.fetchone()
                await conn.commit()

        ctx["ingest_id"] = row[0]
        ctx["ingest_start_dt"] = row[1].isoformat() if row[1] else None
        return RC_OK

    @traced("ingest.dao.mark_status")
    async def mark_status_for_ingest(
        self, req: IngestDataSetReqDTO, resp: IngestDataSetRespDTO
    ) -> int:
        ctx = resp.respCtxData
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE system_datasets_ingest
                    SET ingest_status  = %s,
                        ingest_end_dt  = NOW(),
                        last_ingest_dt = NOW(),
                        error_text     = %s,
                        updated_dt     = NOW()
                    WHERE id = %s
                    RETURNING ingest_end_dt
                    """,
                    (
                        ctx["ingest_status"],
                        ctx.get("error_text"),
                        ctx["ingest_id"],
                    ),
                )
                row = await cur.fetchone()
                await conn.commit()

        ctx["ingest_end_dt"] = row[0].isoformat() if row and row[0] else None
        return RC_OK

    @traced("ingest.dao.list_runs")
    async def list_runs(
        self, req: ListIngestRunsReqDTO, resp: ListIngestRunsRespDTO
    ) -> int:
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT
                        sdi.id,
                        sdi.system_dataset_id,
                        sd.dataset_name,
                        sd.dataset_type,
                        sdi.endpoint_id,
                        e.endpoint_name,
                        e.location_type,
                        sdi.ingest_status,
                        sdi.ingest_start_dt,
                        sdi.ingest_end_dt,
                        sdi.last_ingest_dt,
                        sdi.error_text,
                        sdi.configs_json
                    FROM system_datasets_ingest sdi
                    JOIN system_datasets sd ON sd.id = sdi.system_dataset_id
                    JOIN endpoints        e  ON e.id  = sdi.endpoint_id
                    WHERE (%(dataset_name)s::text  IS NULL OR sd.dataset_name  = %(dataset_name)s::text)
                      AND (%(endpoint_name)s::text IS NULL OR e.endpoint_name  = %(endpoint_name)s::text)
                    ORDER BY sdi.ingest_start_dt DESC, sdi.id DESC
                    LIMIT %(limit)s OFFSET %(offset)s
                    """,
                    {
                        "dataset_name": req.dataset_name,
                        "endpoint_name": req.endpoint_name,
                        "limit": req.limit,
                        "offset": req.offset,
                    },
                )
                rows = await cur.fetchall()

        runs = [
            {
                "id": r[0],
                "system_dataset_id": r[1],
                "dataset_name": r[2],
                "dataset_type": r[3],
                "endpoint_id": r[4],
                "endpoint_name": r[5],
                "location_type": r[6],
                "ingest_status": r[7],
                "ingest_start_dt": r[8].isoformat() if r[8] else None,
                "ingest_end_dt": r[9].isoformat() if r[9] else None,
                "last_ingest_dt": r[10].isoformat() if r[10] else None,
                "error_text": r[11],
                "configs_json": r[12],
            }
            for r in rows
        ]
        resp.respCtxData["ingest_runs"] = runs
        resp.respCtxData["count"] = len(runs)
        resp.respCtxData["limit"] = req.limit
        resp.respCtxData["offset"] = req.offset
        resp.respCtxData["filters"] = {
            "dataset_name": req.dataset_name,
            "endpoint_name": req.endpoint_name,
        }
        return RC_OK
