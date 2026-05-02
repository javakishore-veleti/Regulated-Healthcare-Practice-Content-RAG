"""Real LLM drafter via the Anthropic Messages API.

Uses prompt caching on the system prompt (the regulator-compliance brief) so repeated
runs against the same compliance posture amortize the cache cost. Per-request user
content (topic + retrieved citations) is the only varying portion. The model is
configurable via Settings; the Excel architecture for Project A calls for Claude
Opus 4.7 on Bedrock — this implementation uses the direct Anthropic API for local
dev simplicity, with the same prompt template a Bedrock client would use.

When the API call fails the drafter raises; `GenerationService` does not silently
degrade to stub here — config-time selection picks one drafter per process, so a
runtime failure is a real signal worth surfacing.
"""

from __future__ import annotations

import json
import logging

from anthropic import AsyncAnthropic

from common.tracing import traced

LOGGER = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a compliance-grounded content drafter for allied-health practices in regulated jurisdictions (primarily Australia under AHPRA, United States under FTC). Your only job is to draft Markdown content that an allied-health practice could publish without breaching advertising regulations.

ABSOLUTE CONSTRAINTS (non-negotiable):
1. Every claim in your draft MUST be supported by at least one of the citations provided in the user message. If you cannot ground a claim in a citation, omit the claim. Do not hallucinate facts, statistics, dates, names, or quotes.
2. Cite by inline numbered markers like [1], [2] matching the citation indices in the user message. Multiple citations on one claim look like [1][2].
3. NEVER use any of these regulator-banned phrases or claim categories:
   - Superlatives: "best", "premier", "world-class", "leading", "top", "#1", "number one"
   - Comparatives: "better than", "superior to", "more effective than"
   - Cure / efficacy claims: "cure", "miracle", "miraculous", "guaranteed", "100% effective", "instant relief", "permanent results"
   - Safety absolutes: "completely safe", "totally safe", "no side effects"
   - Testimonials / endorsements: "patient testimonial", "client review", "before-and-after photos", "doctor-recommended" (without source), "FDA approved", "celebrity-endorsed"
   - Hype: "revolutionary", "amazing results", "life-changing", "breakthrough", "transformative"
   - Unsubstantiated authority: "clinically proven", "clinically tested" (without linked evidence)
   - Urgency / scarcity: "limited time", "act now", "while stocks last"
4. Do not include any specific therapeutic claims about cancer, diabetes, arthritis, chronic pain, asthma, depression, or anxiety unless the citation explicitly states it.
5. Use plain English at a reading level appropriate for a clinic patient. Avoid jargon; expand acronyms on first use.

OUTPUT FORMAT (Markdown):
- First line: `# {topic}` heading.
- Subsequent paragraphs are substantive content, each citing at least one source by [N] marker(s).
- Use `## Subheadings` to structure longer drafts.
- End with a `---` separator and a brief italic meta line stating the draft is grounded in the supplied citations.

If the citations are insufficient to write anything compliant about the topic, output ONLY:
`# {topic}\\n\\n_Insufficient grounded sources to draft compliant content on this topic._`"""


def _format_citations_for_prompt(citations: list[dict]) -> str:
    blocks: list[str] = []
    for i, h in enumerate(citations, start=1):
        text = (h.get("child_text") or h.get("snippet") or "").strip()
        ds = h.get("dataset_name")
        page = h.get("page_index")
        parent = h.get("parent_id")
        blocks.append(
            f"[{i}] dataset={ds} page={page} parent={parent}\n    {text}"
        )
    return "\n\n".join(blocks) if blocks else "(no citations available)"


class AnthropicDrafter:
    name = "anthropic_claude_drafter"
    supports_regeneration = True  # LLM can produce a different draft from a hint

    def __init__(self, api_key: str, model: str, max_tokens: int) -> None:
        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens

    @traced("drafter.anthropic.compose")
    async def compose_draft(
        self,
        topic: str,
        citations: list[dict],
        voice_profile: str | None,
        regenerate_hint: str | None = None,
    ) -> str:
        citations_text = _format_citations_for_prompt(citations)
        voice = voice_profile or "professional, plain English, suitable for an allied-health practice website"

        user_text_parts = [
            f"Topic: {topic}",
            "",
            f"Voice profile: {voice}",
            "",
            "Citations from the indexed corpus (cite by [N] marker):",
            "",
            citations_text,
        ]
        if regenerate_hint:
            user_text_parts.extend(
                ["", "Regeneration hint (the previous draft failed faithfulness checks):", regenerate_hint]
            )
        user_text_parts.extend(
            ["", "Compose a compliance-grounded Markdown draft on the topic. Cite every claim by [N]. Do not introduce facts not in the citations."]
        )
        user_text = "\n".join(user_text_parts)

        # System prompt is cached: it's stable across requests for a given compliance
        # policy version, so the Anthropic prompt cache amortizes its tokens across
        # many calls.
        message = await self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_text}],
        )

        try:
            usage = message.usage
            LOGGER.info(
                "anthropic_drafter usage: input=%s output=%s cache_read=%s cache_create=%s",
                getattr(usage, "input_tokens", "?"),
                getattr(usage, "output_tokens", "?"),
                getattr(usage, "cache_read_input_tokens", "?"),
                getattr(usage, "cache_creation_input_tokens", "?"),
            )
        except Exception:  # noqa: BLE001
            pass

        if not message.content:
            raise RuntimeError(
                f"anthropic_drafter: empty content. stop_reason={message.stop_reason}"
            )
        text_blocks = [
            block.text for block in message.content if getattr(block, "type", None) == "text"
        ]
        if not text_blocks:
            raise RuntimeError(
                "anthropic_drafter: no text blocks in response: "
                + json.dumps([getattr(b, "type", str(b)) for b in message.content])
            )
        return "\n".join(text_blocks).strip() + "\n"
