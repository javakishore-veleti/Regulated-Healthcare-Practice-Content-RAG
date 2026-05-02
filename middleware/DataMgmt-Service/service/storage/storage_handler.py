from typing import Protocol

from common.dtos import IngestDataSetReqDTO, IngestDataSetRespDTO


class IStorageHandler(Protocol):
    """One implementation per `endpoints.location_type` (localhost, aws_s3, azure_blob, ...).

    Both methods follow the project DTO contract:
    - read inputs from req and from resp.respCtxData (populated upstream by DAO/service)
    - populate further keys in resp.respCtxData
    - return an int return code (RC_OK on success)
    """

    async def is_destination_populated(
        self, req: IngestDataSetReqDTO, resp: IngestDataSetRespDTO
    ) -> int: ...

    async def execute_ingest(
        self, req: IngestDataSetReqDTO, resp: IngestDataSetRespDTO
    ) -> int: ...
