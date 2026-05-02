from typing import Protocol

from common.dtos import IngestDataSetReqDTO, IngestDataSetRespDTO


class IDagTrigger(Protocol):
    """Triggers an external workflow (currently Airflow) for an ingest run.

    Reads dataset/endpoint context from `resp.respCtxData` (populated upstream by the
    DAOs), composes a workflow conf payload, kicks off the run, and waits until the
    workflow reaches a terminal state. Populates additional keys in `resp.respCtxData`
    (workflow_run_id, workflow_state, destination_path).
    """

    async def trigger_and_wait(
        self, req: IngestDataSetReqDTO, resp: IngestDataSetRespDTO
    ) -> int: ...
