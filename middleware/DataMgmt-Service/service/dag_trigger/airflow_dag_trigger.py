import asyncio
import time
from typing import Any

import httpx

from common.dtos import IngestDataSetReqDTO, IngestDataSetRespDTO
from common.return_codes import RC_INTERNAL_ERROR, RC_OK, RC_VALIDATION_ERROR
from common.tracing import traced

# Mapping of `endpoints.location_type` -> Airflow DAG ID. New cloud destinations
# add a new row here AND a corresponding handler block in the DAG; no service-layer
# branching is needed.
LOCATION_TYPE_TO_DAG_ID: dict[str, str] = {
    "localhost": "regulated_healthcare_dataset_ingest",
}

TERMINAL_STATES = {"success", "failed"}


class AirflowDagTrigger:
    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        poll_interval_secs: float,
        timeout_secs: float,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._auth = (username, password)
        self._poll_interval_secs = poll_interval_secs
        self._timeout_secs = timeout_secs

    @traced("ingest.dag_trigger.airflow.trigger_and_wait")
    async def trigger_and_wait(
        self, req: IngestDataSetReqDTO, resp: IngestDataSetRespDTO
    ) -> int:
        ctx = resp.respCtxData
        location_type = ctx.get("location_type")
        dag_id = LOCATION_TYPE_TO_DAG_ID.get(location_type)
        if dag_id is None:
            ctx["error_text"] = (
                f"no Airflow DAG mapped for location_type={location_type!r}"
            )
            return RC_VALIDATION_ERROR

        conf = {
            "dataset_name": req.dataset_name,
            "dataset_type": ctx.get("dataset_type"),
            "endpoint_name": req.endpoint_name,
            "location_type": location_type,
            "location_config": ctx.get("location_config") or {},
            "force_refresh": bool(req.force_refresh),
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            try:
                run_id = await self._create_run(client, dag_id, conf)
            except Exception as exc:  # noqa: BLE001
                ctx["error_text"] = f"failed to create Airflow dag run: {exc!r}"
                return RC_INTERNAL_ERROR

            ctx["workflow_run_id"] = run_id
            ctx["workflow_dag_id"] = dag_id

            try:
                final_state = await self._poll_until_terminal(client, dag_id, run_id)
            except Exception as exc:  # noqa: BLE001
                ctx["error_text"] = f"failed while polling Airflow dag run: {exc!r}"
                return RC_INTERNAL_ERROR

        ctx["workflow_state"] = final_state
        if final_state == "success":
            return RC_OK

        if final_state is None:
            ctx["error_text"] = (
                f"Airflow dag run {run_id} did not reach a terminal state within "
                f"{self._timeout_secs}s"
            )
        else:
            ctx.setdefault(
                "error_text", f"Airflow dag run {run_id} ended in state {final_state!r}"
            )
        return RC_INTERNAL_ERROR

    async def _create_run(
        self, client: httpx.AsyncClient, dag_id: str, conf: dict[str, Any]
    ) -> str:
        url = f"{self._base_url}/api/v1/dags/{dag_id}/dagRuns"
        resp = await client.post(url, auth=self._auth, json={"conf": conf})
        if resp.status_code not in (200, 201):
            raise RuntimeError(
                f"POST {url} -> HTTP {resp.status_code}: {resp.text[:300]}"
            )
        body = resp.json()
        return body["dag_run_id"]

    async def _poll_until_terminal(
        self, client: httpx.AsyncClient, dag_id: str, run_id: str
    ) -> str | None:
        url = f"{self._base_url}/api/v1/dags/{dag_id}/dagRuns/{run_id}"
        deadline = time.monotonic() + self._timeout_secs
        last_state: str | None = None
        while time.monotonic() < deadline:
            await asyncio.sleep(self._poll_interval_secs)
            resp = await client.get(url, auth=self._auth)
            if resp.status_code != 200:
                raise RuntimeError(
                    f"GET {url} -> HTTP {resp.status_code}: {resp.text[:300]}"
                )
            last_state = resp.json().get("state")
            if last_state in TERMINAL_STATES:
                return last_state
        return last_state
