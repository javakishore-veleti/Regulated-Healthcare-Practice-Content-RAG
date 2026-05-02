import json
from typing import Protocol

from common.dtos import IngestDataSetReqDTO, IngestDataSetRespDTO
from common.return_codes import RC_OK, RC_VALIDATION_ERROR
from common.tracing import traced
from dao.datasets_dao import IDataSetsDao
from dao.endpoints_dao import IEndpointsDao
from dao.ingest_dao import IIngestDao
from service.storage.dispatcher import StorageDispatcher

LOCATION_TYPE_LOCALHOST = "localhost"

INGEST_STATUS_IN_PROGRESS = "in_progress"
INGEST_STATUS_SUCCESS = "success"
INGEST_STATUS_FAILURE = "failure"
INGEST_STATUS_SKIPPED_CACHE_HIT = "skipped_cache_hit"


class IIngestService(Protocol):
    async def start_ingest(
        self, req: IngestDataSetReqDTO, resp: IngestDataSetRespDTO
    ) -> int: ...


class IngestService:
    def __init__(
        self,
        datasets_dao: IDataSetsDao,
        endpoints_dao: IEndpointsDao,
        ingest_dao: IIngestDao,
        dispatcher: StorageDispatcher,
    ) -> None:
        self._datasets_dao = datasets_dao
        self._endpoints_dao = endpoints_dao
        self._ingest_dao = ingest_dao
        self._dispatcher = dispatcher

    @traced("ingest.service.start_ingest")
    async def start_ingest(
        self, req: IngestDataSetReqDTO, resp: IngestDataSetRespDTO
    ) -> int:
        ctx = resp.respCtxData

        rc = await self._datasets_dao.fetch_by_name_for_ingest(req, resp)
        if rc != RC_OK:
            return rc

        rc = await self._endpoints_dao.fetch_by_name_for_ingest(req, resp)
        if rc != RC_OK:
            return rc

        if not ctx.get("endpoint_is_active"):
            ctx["error_text"] = f"endpoint {req.endpoint_name!r} is not active"
            return RC_VALIDATION_ERROR

        handler = self._dispatcher.resolve(ctx["location_type"], resp)
        if handler is None:
            return RC_VALIDATION_ERROR

        # Cache-hit short-circuit: localhost only, both DB success row AND
        # populated destination required (per CLAUDE.md endpoint rules).
        if ctx["location_type"] == LOCATION_TYPE_LOCALHOST and not req.force_refresh:
            rc = await self._ingest_dao.find_latest_success_for_ingest(req, resp)
            if rc != RC_OK:
                return rc

            rc = await handler.is_destination_populated(req, resp)
            if rc != RC_OK:
                return rc

            if ctx.get("latest_success_id") and ctx.get("destination_populated"):
                ctx["ingest_status"] = INGEST_STATUS_SKIPPED_CACHE_HIT
                ctx["configs_json_text"] = json.dumps(
                    {
                        "force_refresh": False,
                        "cache_hit_against_run_id": ctx["latest_success_id"],
                    }
                )
                rc = await self._ingest_dao.create_run_for_ingest(req, resp)
                if rc != RC_OK:
                    return rc
                ctx["message"] = "skipped: localhost destination already populated"
                return RC_OK

        # Normal path: create in_progress row, dispatch, mark success/failure.
        ctx["ingest_status"] = INGEST_STATUS_IN_PROGRESS
        ctx["configs_json_text"] = json.dumps({"force_refresh": req.force_refresh})
        rc = await self._ingest_dao.create_run_for_ingest(req, resp)
        if rc != RC_OK:
            return rc

        try:
            handler_rc = await handler.execute_ingest(req, resp)
        except Exception as exc:  # noqa: BLE001
            handler_rc = -1
            ctx["error_text"] = f"handler raised: {exc!r}"

        if handler_rc == RC_OK:
            ctx["ingest_status"] = INGEST_STATUS_SUCCESS
        else:
            ctx["ingest_status"] = INGEST_STATUS_FAILURE
            ctx.setdefault("error_text", f"handler returned rc={handler_rc}")

        rc = await self._ingest_dao.mark_status_for_ingest(req, resp)
        if rc != RC_OK:
            return rc

        ctx["message"] = (
            "ingest completed"
            if ctx["ingest_status"] == INGEST_STATUS_SUCCESS
            else "ingest failed"
        )
        return RC_OK
