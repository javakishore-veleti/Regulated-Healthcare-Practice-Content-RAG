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
        guardrails_service: IGuardrailsService | None = None,
        faithfulness_service: IFaithfulnessService | None = None,
    ) -> None:
        self._retrieval = retrieval_service
        self._guardrails = guardrails_service
        self._faithfulness = faithfulness_service

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
        ctx["generator"] = "stub_compose_with_citations"
        ctx["draft_markdown"] = self._compose_stub_draft(req.topic, hits)
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
            f_req = CheckFaithfulnessReqDTO(
                text=ctx["draft_markdown"], citations=citation_models
            )
            f_resp = CheckFaithfulnessRespDTO()
            f_rc = await self._faithfulness.check_text(f_req, f_resp)
            if f_rc == RC_OK:
                f = f_resp.respCtxData
                ctx["faithfulness"] = {
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
                    # Trim per-sentence detail to keep the response light; full
                    # detail is available via /faithfulness/check.
                    "per_sentence_preview": (f.get("per_sentence") or [])[:6],
                }
            else:
                ctx["faithfulness"] = {
                    "status": "error",
                    "reason": f"faithfulness check returned rc={f_rc}",
                }
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

    @staticmethod
    def _compose_stub_draft(topic: str, hits: list[dict]) -> str:
        if not hits:
            return (
                f"# {topic}\n\n"
                "_No grounded passages were retrieved for this topic. The stub "
                "generator will not fabricate content; expand the corpus or refine "
                "the topic and retry._\n"
            )

        lines: list[str] = [f"# {topic}", ""]
        lines.append(
            "Drawing on the indexed Project A corpus, the following passages "
            "ground this topic. Each citation marker links to the source row in "
            "`child_chunk_embeddings`. No paraphrasing has been performed — the "
            "stub generator emits retrieved children verbatim until a "
            "compliance-checked LLM drafter replaces it.",
        )
        lines.append("")
        for i, h in enumerate(hits, start=1):
            child_text = (h.get("child_text") or "").strip()
            ds = h.get("dataset_name")
            page = h.get("page_index")
            parent = h.get("parent_id")
            lines.append(f"## Source [{i}]")
            lines.append(f"_{ds} · page {page} · {parent}_")
            lines.append("")
            lines.append(f"> {child_text}")
            lines.append("")
        lines.append("---")
        lines.append(
            "_Stub-generated draft. Self-RAG faithfulness scoring + output "
            "guardrails (banned-phrase / forbidden-claim detection) are separate "
            "follow-up slices._"
        )
        return "\n".join(lines) + "\n"
