from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _BaseDTO(BaseModel):
    model_config = ConfigDict(extra="ignore")


class ListRagPatternsReqDTO(_BaseDTO):
    """No filters in v1; returns every active pattern."""


class ListRagPatternsRespDTO(_BaseDTO):
    """Payload lives in respCtxData.patterns per the project DTO convention."""

    respCtxData: dict[str, Any] = Field(default_factory=dict)


class ChunkTextReqDTO(_BaseDTO):
    """Request DTO for parent-child chunking. Defaults match the Project A bar from
    the Excel (child ~256 tokens; parent at section/paragraph granularity)."""

    text: str = Field(..., min_length=1)
    parent_size_chars: int = Field(default=1500, ge=128, le=8192)
    child_size_chars: int = Field(default=256, ge=64, le=2048)


class ChunkTextRespDTO(_BaseDTO):
    """Returns parents and children separately with id linkage so callers can index
    them without duplicating parent text per child."""

    respCtxData: dict[str, Any] = Field(default_factory=dict)


class HybridRetrieveReqDTO(_BaseDTO):
    """Request DTO for hybrid retrieval (BM25 + dense + RRF fusion)."""

    query: str = Field(..., min_length=1)
    dataset_name: str | None = None
    top_k: int = Field(default=5, ge=1, le=50)
    top_k_per_leg: int = Field(default=50, ge=5, le=500)
    rrf_k: int = Field(default=60, ge=1, le=1000)


class HybridRetrieveRespDTO(_BaseDTO):
    """Returns ranked hits in respCtxData.hits with diagnostic metadata for both
    retrieval legs and the fused output."""

    respCtxData: dict[str, Any] = Field(default_factory=dict)
