"""Deterministic, no-LLM drafter that emits retrieved children verbatim with numbered
citation markers. Acts as the safe fallback when no API key is configured and as the
behavior baseline against which real LLM drafters are compared."""

from common.otel_genai import (
    OP_TEXT_COMPLETION,
    SYSTEM_RHC_STUB,
    set_gen_ai_request,
    set_gen_ai_response,
)
from common.tracing import traced


class StubDrafter:
    name = "stub_compose_with_citations"
    supports_regeneration = False  # deterministic — same input → same output

    @traced("drafter.stub.compose")
    async def compose_draft(
        self,
        topic: str,
        citations: list[dict],
        voice_profile: str | None,
        regenerate_hint: str | None = None,
    ) -> str:
        # OTel GenAI semconv — even the stub gets attributes for consistency
        # so backend dashboards work uniformly across drafter modes.
        set_gen_ai_request(
            system=SYSTEM_RHC_STUB,
            operation=OP_TEXT_COMPLETION,
            model=self.name,
        )
        if not citations:
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
            "compliance-checked LLM drafter replaces it."
        )
        lines.append("")
        for i, h in enumerate(citations, start=1):
            child_text = (h.get("child_text") or h.get("snippet") or "").strip()
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
        body = "\n".join(lines) + "\n"
        # OTel GenAI semconv — response side. No real model is invoked, so
        # token counts approximate via word counts (caller-comparable units).
        set_gen_ai_response(
            model=self.name,
            finish_reasons=["stop"],
            input_tokens=len(topic.split()),
            output_tokens=len(body.split()),
        )
        return body
