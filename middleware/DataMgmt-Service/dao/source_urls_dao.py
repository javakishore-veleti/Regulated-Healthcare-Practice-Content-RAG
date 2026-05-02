from typing import Protocol

from psycopg_pool import AsyncConnectionPool

from common.dtos import (
    AddSourceUrlReqDTO,
    AddSourceUrlRespDTO,
    DeleteSourceUrlReqDTO,
    DeleteSourceUrlRespDTO,
    ListSourceUrlsReqDTO,
    ListSourceUrlsRespDTO,
    UpdateSourceUrlReqDTO,
    UpdateSourceUrlRespDTO,
)
from common.return_codes import RC_NOT_FOUND, RC_OK, RC_VALIDATION_ERROR
from common.tracing import traced


class ISourceUrlsDao(Protocol):
    async def list_for_dataset(
        self, req: ListSourceUrlsReqDTO, resp: ListSourceUrlsRespDTO
    ) -> int: ...

    async def add(self, req: AddSourceUrlReqDTO, resp: AddSourceUrlRespDTO) -> int: ...

    async def update(
        self, req: UpdateSourceUrlReqDTO, resp: UpdateSourceUrlRespDTO
    ) -> int: ...

    async def delete(
        self, req: DeleteSourceUrlReqDTO, resp: DeleteSourceUrlRespDTO
    ) -> int: ...


class PostgresSourceUrlsDao:
    def __init__(self, pool: AsyncConnectionPool) -> None:
        self._pool = pool

    @traced("source_urls.dao.list_for_dataset")
    async def list_for_dataset(
        self, req: ListSourceUrlsReqDTO, resp: ListSourceUrlsRespDTO
    ) -> int:
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT su.id, su.system_dataset_id, sd.dataset_name, su.url,
                           su.label, su.is_active, su.position, su.notes,
                           su.created_dt, su.updated_dt
                    FROM dataset_source_urls su
                    JOIN system_datasets sd ON sd.id = su.system_dataset_id
                    WHERE sd.dataset_name = %(name)s
                      AND (NOT %(only_active)s OR su.is_active = TRUE)
                    ORDER BY su.position ASC, su.id ASC
                    """,
                    {"name": req.dataset_name, "only_active": req.only_active},
                )
                rows = await cur.fetchall()

        resp.respCtxData["source_urls"] = [_row_to_dict(r) for r in rows]
        resp.respCtxData["dataset_name"] = req.dataset_name
        resp.respCtxData["count"] = len(rows)
        return RC_OK

    @traced("source_urls.dao.add")
    async def add(self, req: AddSourceUrlReqDTO, resp: AddSourceUrlRespDTO) -> int:
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT id FROM system_datasets WHERE dataset_name = %s",
                    (req.dataset_name,),
                )
                row = await cur.fetchone()
                if row is None:
                    resp.respCtxData["error"] = f"dataset not found: {req.dataset_name}"
                    return RC_NOT_FOUND
                dataset_id = row[0]

                try:
                    await cur.execute(
                        """
                        INSERT INTO dataset_source_urls
                            (system_dataset_id, url, label, is_active, position, notes)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        RETURNING id, system_dataset_id, url, label, is_active,
                                  position, notes, created_dt, updated_dt
                        """,
                        (
                            dataset_id,
                            req.url.strip(),
                            req.label,
                            req.is_active,
                            req.position,
                            req.notes,
                        ),
                    )
                except Exception as exc:  # noqa: BLE001
                    msg = str(exc).lower()
                    if "unique" in msg or "duplicate key" in msg:
                        resp.respCtxData["error"] = (
                            f"url already exists for dataset {req.dataset_name}"
                        )
                        return RC_VALIDATION_ERROR
                    if "chk_dataset_source_urls" in msg or "check constraint" in msg:
                        resp.respCtxData["error"] = (
                            "url must start with http:// or https://"
                        )
                        return RC_VALIDATION_ERROR
                    raise
                row = await cur.fetchone()
                await conn.commit()

        ins = _row_minimal_to_dict(row, dataset_name=req.dataset_name)
        resp.respCtxData["source_url"] = ins
        return RC_OK

    @traced("source_urls.dao.update")
    async def update(
        self, req: UpdateSourceUrlReqDTO, resp: UpdateSourceUrlRespDTO
    ) -> int:
        sets: list[str] = []
        params: list = []
        if req.is_active is not None:
            sets.append("is_active = %s")
            params.append(req.is_active)
        if req.position is not None:
            sets.append("position = %s")
            params.append(req.position)
        if req.label is not None:
            sets.append("label = %s")
            params.append(req.label)
        if req.notes is not None:
            sets.append("notes = %s")
            params.append(req.notes)

        if not sets:
            resp.respCtxData["error"] = "no fields supplied"
            return RC_VALIDATION_ERROR

        sets.append("updated_dt = NOW()")
        params.append(req.id)

        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"""
                    UPDATE dataset_source_urls
                    SET {", ".join(sets)}
                    WHERE id = %s
                    RETURNING id, system_dataset_id, url, label, is_active,
                              position, notes, created_dt, updated_dt
                    """,
                    params,
                )
                row = await cur.fetchone()
                await conn.commit()

        if row is None:
            resp.respCtxData["error"] = f"source url id={req.id} not found"
            return RC_NOT_FOUND
        resp.respCtxData["source_url"] = _row_minimal_to_dict(row)
        return RC_OK

    @traced("source_urls.dao.delete")
    async def delete(
        self, req: DeleteSourceUrlReqDTO, resp: DeleteSourceUrlRespDTO
    ) -> int:
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM dataset_source_urls WHERE id = %s RETURNING id",
                    (req.id,),
                )
                row = await cur.fetchone()
                await conn.commit()

        if row is None:
            resp.respCtxData["error"] = f"source url id={req.id} not found"
            return RC_NOT_FOUND
        resp.respCtxData["deleted_id"] = row[0]
        return RC_OK


def _row_to_dict(row) -> dict:
    return {
        "id": row[0],
        "system_dataset_id": row[1],
        "dataset_name": row[2],
        "url": row[3],
        "label": row[4],
        "is_active": row[5],
        "position": row[6],
        "notes": row[7],
        "created_dt": row[8].isoformat() if row[8] else None,
        "updated_dt": row[9].isoformat() if row[9] else None,
    }


def _row_minimal_to_dict(row, dataset_name: str | None = None) -> dict:
    """Shape returned by INSERT/UPDATE RETURNING (no joined dataset_name)."""
    return {
        "id": row[0],
        "system_dataset_id": row[1],
        "dataset_name": dataset_name,
        "url": row[2],
        "label": row[3],
        "is_active": row[4],
        "position": row[5],
        "notes": row[6],
        "created_dt": row[7].isoformat() if row[7] else None,
        "updated_dt": row[8].isoformat() if row[8] else None,
    }
