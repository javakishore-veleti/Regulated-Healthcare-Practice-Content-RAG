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
