from datetime import datetime, timezone
from pathlib import Path

from common.dtos import IngestDataSetReqDTO, IngestDataSetRespDTO
from common.return_codes import RC_OK, RC_VALIDATION_ERROR
from common.tracing import traced


class LocalhostStorageHandler:
    """Handler for endpoints with location_type='localhost'.

    The actual download is stubbed in this slice — a marker file is written so the
    cache-hit short-circuit can be exercised end-to-end. A real fetcher (Airflow DAG)
    replaces `execute_ingest` later without changing the surface.
    """

    @traced("ingest.localhost.is_destination_populated")
    async def is_destination_populated(
        self, req: IngestDataSetReqDTO, resp: IngestDataSetRespDTO
    ) -> int:
        rc = self._compute_destination_path(req, resp)
        if rc != RC_OK:
            return rc

        target = Path(resp.respCtxData["destination_path"])
        populated = target.is_dir() and any(target.iterdir())
        resp.respCtxData["destination_populated"] = populated
        return RC_OK

    @traced("ingest.localhost.execute_ingest")
    async def execute_ingest(
        self, req: IngestDataSetReqDTO, resp: IngestDataSetRespDTO
    ) -> int:
        rc = self._compute_destination_path(req, resp)
        if rc != RC_OK:
            return rc

        target = Path(resp.respCtxData["destination_path"])
        target.mkdir(parents=True, exist_ok=True)

        marker = target / "INGESTED_AT.txt"
        marker.write_text(
            f"stub ingest of {req.dataset_name} via {req.endpoint_name} "
            f"at {datetime.now(timezone.utc).isoformat()}\n"
        )
        resp.respCtxData["files_written"] = [str(marker)]
        return RC_OK

    @staticmethod
    def _compute_destination_path(
        req: IngestDataSetReqDTO, resp: IngestDataSetRespDTO
    ) -> int:
        cfg = resp.respCtxData.get("location_config") or {}
        base_under_home = cfg.get("base_path_under_home")
        latest_dirname = cfg.get("latest_ingest_dirname", "Latest_Ingest")

        if not base_under_home:
            resp.respCtxData["error_text"] = (
                "endpoint location_config missing 'base_path_under_home'"
            )
            return RC_VALIDATION_ERROR

        path = Path.home() / base_under_home / req.dataset_name / latest_dirname
        resp.respCtxData["destination_path"] = str(path)
        return RC_OK
