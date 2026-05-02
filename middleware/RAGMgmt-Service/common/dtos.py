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


class ThreeCorporaRetrieveReqDTO(_BaseDTO):
    """Request DTO for three-corpora-balanced retrieval. Runs the hybrid pipeline
    once per corpus (regulator / clinical_evidence / practice_voice) so the caller
    receives a guaranteed mix instead of whichever corpus dominates a single
    ranking. `top_k_per_corpus` caps each corpus's contribution."""

    query: str = Field(..., min_length=1)
    top_k_per_corpus: int = Field(default=3, ge=1, le=10)
    top_k_per_leg: int = Field(default=50, ge=5, le=500)
    rrf_k: int = Field(default=60, ge=1, le=1000)


class ThreeCorporaRetrieveRespDTO(_BaseDTO):
    """Returns hits grouped under `respCtxData.per_corpus`, each entry tagged
    with its `corpus_type` and the dataset_names it draws from."""

    respCtxData: dict[str, Any] = Field(default_factory=dict)


class GenerateGroundedDraftReqDTO(_BaseDTO):
    """Request DTO for compliance-grounded content generation. The topic drives
    retrieval; voice_profile is a free-form hint the generator can use to adapt tone
    once a real LLM client lands (today's stub composes excerpts verbatim)."""

    topic: str = Field(..., min_length=1)
    dataset_name: str | None = None
    top_k: int = Field(default=5, ge=1, le=10)
    voice_profile: str | None = None


class GenerateGroundedDraftRespDTO(_BaseDTO):
    """Returns the draft markdown + an aligned `citations` list so callers can
    render inline footnotes deterministically."""

    respCtxData: dict[str, Any] = Field(default_factory=dict)


class CheckGuardrailsReqDTO(_BaseDTO):
    """Request DTO for output-guardrails scanning. Empty `policy_id` uses the
    service default (currently the only loaded policy: ahpra_baseline_v1)."""

    text: str = Field(..., min_length=1)
    policy_id: str | None = None


class CheckGuardrailsRespDTO(_BaseDTO):
    """Returns violations + per-policy metadata. `passed` is True iff no
    violations were detected at any severity."""

    respCtxData: dict[str, Any] = Field(default_factory=dict)


class CitationSnippet(_BaseDTO):
    """Minimal citation shape the faithfulness scorer needs."""

    snippet: str
    parent_id: str | None = None
    child_id: str | None = None


class CheckFaithfulnessReqDTO(_BaseDTO):
    """Request DTO for the Self-RAG faithfulness scorer. `citations` are the
    grounded passages the draft is checked against."""

    text: str = Field(..., min_length=1)
    citations: list[CitationSnippet] = Field(default_factory=list)
    per_sentence_threshold: float = Field(default=0.25, ge=0.0, le=1.0)
    overall_threshold: float = Field(default=0.7, ge=0.0, le=1.0)


class CheckFaithfulnessRespDTO(_BaseDTO):
    """Returns score + per-sentence breakdown + pass/fail vs the overall threshold."""

    respCtxData: dict[str, Any] = Field(default_factory=dict)
