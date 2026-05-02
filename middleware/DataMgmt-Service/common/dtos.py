from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _BaseDTO(BaseModel):
    model_config = ConfigDict(extra="ignore")


class ListEndpointsReqDTO(_BaseDTO):
    """Request DTO for listing endpoints. v1 takes no filters."""


class ListEndpointsRespDTO(_BaseDTO):
    """Response DTO. The actual API payload lives in respCtxData per project convention."""

    respCtxData: dict[str, Any] = Field(default_factory=dict)


class ListDataSetsReqDTO(_BaseDTO):
    """Request DTO for listing datasets. v1 takes no filters."""


class ListDataSetsRespDTO(_BaseDTO):
    respCtxData: dict[str, Any] = Field(default_factory=dict)


class IngestDataSetReqDTO(_BaseDTO):
    """Request DTO for the ingest workflow. Carries the dataset slug and the endpoint
    name that selects where data lands. force_refresh bypasses the cache short-circuit
    (anticipated; not implemented yet)."""

    dataset_name: str
    endpoint_name: str
    force_refresh: bool = False


class IngestDataSetRespDTO(_BaseDTO):
    """Response DTO for the ingest workflow. State accumulates in respCtxData across the
    DAO/service/handler chain (dataset_id, endpoint_id, location_type, location_config,
    cache_populated, latest_success_id, ingest_id, ingest_status, destination_path,
    ingest_start_dt, ingest_end_dt, message)."""

    respCtxData: dict[str, Any] = Field(default_factory=dict)


class ListIngestRunsReqDTO(_BaseDTO):
    """Filters for listing ingest run history. All filters are optional; omit to scan all."""

    dataset_name: str | None = None
    endpoint_name: str | None = None
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class ListIngestRunsRespDTO(_BaseDTO):
    respCtxData: dict[str, Any] = Field(default_factory=dict)
