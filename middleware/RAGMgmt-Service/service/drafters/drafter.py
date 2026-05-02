from typing import Protocol


class IDrafter(Protocol):
    """Composes a compliance-grounded draft from retrieved citation hits.

    Implementations vary from the deterministic `StubDrafter` (verbatim citation
    quoting) to a real LLM-backed drafter (e.g., `AnthropicDrafter`). The contract
    is intentionally narrow: take a topic + citations + voice hint, return markdown.
    The Self-RAG faithfulness loop and guardrail layer wrap this method, not modify it.
    """

    name: str

    async def compose_draft(
        self,
        topic: str,
        citations: list[dict],
        voice_profile: str | None,
        regenerate_hint: str | None = None,
    ) -> str: ...
