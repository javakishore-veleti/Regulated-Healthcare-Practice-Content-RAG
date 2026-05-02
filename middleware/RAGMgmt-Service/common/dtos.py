from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _BaseDTO(BaseModel):
    model_config = ConfigDict(extra="ignore")


class ListRagPatternsReqDTO(_BaseDTO):
    """No filters in v1; returns every active pattern."""


class ListRagPatternsRespDTO(_BaseDTO):
    """Payload lives in respCtxData.patterns per the project DTO convention."""

    respCtxData: dict[str, Any] = Field(default_factory=dict)
