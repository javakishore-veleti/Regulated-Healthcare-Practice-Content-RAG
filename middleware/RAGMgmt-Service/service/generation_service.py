from typing import Protocol

from common.dtos import (
    CheckFaithfulnessReqDTO,
    CheckFaithfulnessRespDTO,
    CheckGuardrailsReqDTO,
    CheckGuardrailsRespDTO,
    CitationSnippet,
    GenerateGroundedDraftReqDTO,
    GenerateGroundedDraftRespDTO,
    HybridRetrieveReqDTO,
    HybridRetrieveRespDTO,
)
from common.return_codes import RC_OK
from common.tracing import traced
from service.drafters.drafter import IDrafter
from service.faithfulness_service import IFaithfulnessService
from service.guardrails.guardrails_service import IGuardrailsService
from service.retrieval_service import IRetrievalService


class IGenerationService(Protocol):
    async def generate_grounded_draft(
        self, req: GenerateGroundedDraftReqDTO, resp: GenerateGroundedDraftRespDTO
    ) -> int: ...


class GenerationService:
    """Composes a citation-anchored draft from retrieved corpus passages.

    Today's implementation is a deterministic *stub*: it runs the hybrid retrieval
    leg, then concatenates retrieved children verbatim with numbered citation
    markers — no paraphrasing, no LLM call. This guarantees every claim is mapped
    to a retrievable, citable source (the project's compliance bar).

    A real Claude / Bedrock client (per the Excel architecture: Opus for drafting,
    Haiku for compliance check) replaces `_compose_stub_draft` in a follow-up slice.
    The Self-RAG faithfulness loop and output guardrails are separate slices that
    bracket this method.
    """

    def __init__(
        self,
        retrieval_service: IRetrievalService,
        drafter: IDrafter,
        guardrails_service: IGuardrailsService | None = None,
        faithfulness_service: IFaithfulnessService | None = None,
        max_regenerate_attempts: int = 1,
    ) -> None:
        self._retrieval = retrieval_service
        self._drafter = drafter
        self._guardrails = guardrails_service
        self._faithfulness = faithfulness_service
        self._max_regenerate_attempts = max(0, max_regenerate_attempts)

    @traced("generation.grounded_draft")
    async def generate_grounded_draft(
        self, req: GenerateGroundedDraftReqDTO, resp: GenerateGroundedDraftRespDTO
    ) -> int:
        retrieve_req = HybridRetrieveReqDTO(
            query=req.topic,
            dataset_name=req.dataset_name,
            top_k=req.top_k,
        )
        retrieve_resp = HybridRetrieveRespDTO()
        rc = await self._retrieval.hybrid_search(retrieve_req, retrieve_resp)
        if rc != RC_OK:
            return rc

        hits = retrieve_resp.respCtxData.get("hits", []) or []

        ctx = resp.respCtxData
        ctx["topic"] = req.topic
        ctx["voice_profile"] = req.voice_profile or "default"
        ctx["generator"] = self._drafter.name

        # First compose; subsequent attempts run inside the faithfulness block below
        # if regeneration is supported and a hint can be derived.
        draft = await self._drafter.compose_draft(
            topic=req.topic,
            citations=hits,
            voice_profile=req.voice_profile,
        )
        ctx["draft_markdown"] = draft
        ctx["draft_attempts"] = 1
        ctx["regeneration_history"] = []
        ctx["citations"] = [
            {
                "marker": f"[{i}]",
                "dataset_name": h.get("dataset_name"),
                "page_index": h.get("page_index"),
                "parent_id": h.get("parent_id"),
                "child_id": h.get("child_id"),
                "char_offset_in_parent": h.get("char_offset_in_parent"),
                "snippet": (h.get("child_text") or "")[:240],
                "rrf_score": h.get("rrf_score"),
            }
            for i, h in enumerate(hits, start=1)
        ]
        ctx["retrieval_meta"] = {
            "legs": retrieve_resp.respCtxData.get("legs", {}),
            "fusion": retrieve_resp.respCtxData.get("fusion", {}),
        }
        if self._faithfulness is not None:
            citation_models = [
                CitationSnippet(
                    snippet=c["snippet"],
                    parent_id=c.get("parent_id"),
                    child_id=c.get("child_id"),
                )
                for c in ctx["citations"]
            ]
            faithfulness_summary = await self._score_faithfulness(
                ctx["draft_markdown"], citation_models
            )

            # Self-RAG regenerate loop: if the active drafter supports regeneration
            # and the score is below threshold, recompose with a hint listing
            # unsupported sentences. Capped by max_regenerate_attempts.
            attempts_used = 0
            while (
                faithfulness_summary.get("status") == "ok"
                and not faithfulness_summary.get("passed")
                and self._drafter.supports_regeneration
                and attempts_used < self._max_regenerate_attempts
            ):
                hint = _build_regenerate_hint(faithfulness_summary)
                ctx["regeneration_history"].append(
                    {
                        "attempt": attempts_used + 1,
                        "score": faithfulness_summary.get("score"),
                        "passed": faithfulness_summary.get("passed"),
                        "hint": hint,
                    }
                )
                attempts_used += 1
                ctx["draft_attempts"] = attempts_used + 1

                draft = await self._drafter.compose_draft(
                    topic=req.topic,
                    citations=hits,
                    voice_profile=req.voice_profile,
                    regenerate_hint=hint,
                )
                ctx["draft_markdown"] = draft
                faithfulness_summary = await self._score_faithfulness(
                    draft, citation_models
                )

            ctx["faithfulness"] = faithfulness_summary
        else:
            ctx["faithfulness"] = {
                "status": "skipped",
                "reason": "Faithfulness service not configured for this deployment.",
            }

        if self._guardrails is not None:
            gr_req = CheckGuardrailsReqDTO(text=ctx["draft_markdown"])
            gr_resp = CheckGuardrailsRespDTO()
            gr_rc = await self._guardrails.check_text(gr_req, gr_resp)
            if gr_rc == RC_OK:
                gr = gr_resp.respCtxData
                ctx["guardrails"] = {
                    "status": "ok",
                    "policy_id": gr.get("policy_id"),
                    "rule_count": gr.get("rule_count"),
                    "passed": gr.get("passed"),
                    "violation_count": gr.get("violation_count"),
                    "max_severity": gr.get("max_severity"),
                    "violations": gr.get("violations"),
                }
            else:
                ctx["guardrails"] = {
                    "status": "error",
                    "reason": f"guardrails check returned rc={gr_rc}",
                }
        else:
            ctx["guardrails"] = {
                "status": "skipped",
                "reason": "Guardrails service not configured for this deployment.",
            }
        return RC_OK

    async def _score_faithfulness(
        self, draft: str, citations: list[CitationSnippet]
    ) -> dict:
        f_req = CheckFaithfulnessReqDTO(text=draft, citations=citations)
        f_resp = CheckFaithfulnessRespDTO()
        f_rc = await self._faithfulness.check_text(f_req, f_resp)
        if f_rc != RC_OK:
            return {
                "status": "error",
                "reason": f"faithfulness check returned rc={f_rc}",
            }
        f = f_resp.respCtxData
        return {
            "status": "ok",
            "scorer": f.get("scorer"),
            "score": f.get("score"),
            "passed": f.get("passed"),
            "overall_threshold": f.get("overall_threshold"),
            "per_sentence_threshold": f.get("per_sentence_threshold"),
            "sentence_count": f.get("sentence_count"),
            "supported_count": f.get("supported_count"),
            "evidence_free_count": f.get("evidence_free_count"),
            "regenerate_recommended": f.get("regenerate_recommended"),
            "per_sentence_preview": (f.get("per_sentence") or [])[:6],
        }


def _build_regenerate_hint(faithfulness_summary: dict) -> str:
    """Compose a short, actionable hint for the LLM drafter from a failed
    faithfulness check. The drafter receives this as `regenerate_hint`."""
    score = faithfulness_summary.get("score")
    threshold = faithfulness_summary.get("overall_threshold")
    preview = faithfulness_summary.get("per_sentence_preview") or []
    unsupported = [p for p in preview if not p.get("supported")]

    lines = [
        f"The previous draft scored faithfulness {score} (below threshold {threshold}).",
        "Rewrite the draft using ONLY the cited sources. Omit any claim you cannot",
        "directly ground in a citation. Each substantive sentence must cite at least",
        "one [N] source.",
    ]
    if unsupported:
        lines.append("")
        lines.append("Sentences flagged as ungrounded in the previous draft:")
        for u in unsupported[:5]:
            sent = (u.get("sentence") or "").strip()
            lines.append(f'- "{sent[:140]}"')
    return "\n".join(lines)
