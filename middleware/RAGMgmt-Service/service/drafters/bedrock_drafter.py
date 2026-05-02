"""LLM drafter via AWS Bedrock — the README's stated production target (Claude
Opus served via Bedrock rather than the direct Anthropic API).

Identical prompt template to AnthropicDrafter — both backends serve the same
regulator-aligned compliance brief. Only the transport differs:
  * AnthropicDrafter → Anthropic Messages API (direct).
  * BedrockDrafter   → AWS Bedrock InvokeModel (uses the Anthropic-on-Bedrock
                        request shape: `anthropic_version: bedrock-2023-05-31`).

Optional dep — install via `pip install '.[bedrock-drafter]'` (boto3 with
bedrock-runtime). Credentials come from the standard AWS chain (env vars,
~/.aws/credentials, IRSA / Pod Identity in EKS, SSO).

boto3's `invoke_model` is sync; we wrap it in asyncio.to_thread so the
FastAPI event loop stays cooperative. For lower latency a future slice can
swap to aioboto3 — that's a transport optimization, not a contract change.
"""

from __future__ import annotations

import asyncio
import json
import logging

from common.otel_genai import (
    OP_CHAT,
    SYSTEM_AWS_BEDROCK,
    set_gen_ai_request,
    set_gen_ai_response,
)
from common.tracing import traced

# Share the system prompt + citation formatter with AnthropicDrafter — both
# backends are the same drafter, different transports.
from service.drafters.anthropic_drafter import (
    SYSTEM_PROMPT,
    _format_citations_for_prompt,
)

LOGGER = logging.getLogger(__name__)


class BedrockDrafter:
    name = "bedrock_anthropic_claude_drafter"
    supports_regeneration = True  # LLM can produce a different draft from a hint

    def __init__(self, model_id: str, region: str, max_tokens: int) -> None:
        if not model_id:
            raise ValueError(
                "BedrockDrafter requires `bedrock_model_id` — set BEDROCK_MODEL_ID "
                "to the Bedrock identifier of your Claude model "
                "(e.g. anthropic.claude-opus-4-7-... or a cross-region profile)."
            )
        # Lazy import so this module loads even when boto3 isn't installed —
        # the optional-dep gate lives at the import site in main.py.
        import boto3  # type: ignore[import-not-found]

        self._client = boto3.client("bedrock-runtime", region_name=region)
        self._model_id = model_id
        self._max_tokens = max_tokens

    @traced("drafter.bedrock.compose")
    async def compose_draft(
        self,
        topic: str,
        citations: list[dict],
        voice_profile: str | None,
        regenerate_hint: str | None = None,
    ) -> str:
        citations_text = _format_citations_for_prompt(citations)
        voice = voice_profile or (
            "professional, plain English, suitable for an allied-health "
            "practice website"
        )

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
                [
                    "",
                    "Regeneration hint (the previous draft failed faithfulness checks):",
                    regenerate_hint,
                ]
            )
        user_text_parts.extend(
            [
                "",
                "Compose a compliance-grounded Markdown draft on the topic. "
                "Cite every claim by [N]. Do not introduce facts not in the citations.",
            ]
        )
        user_text = "\n".join(user_text_parts)

        # OTel GenAI semconv — request side.
        set_gen_ai_request(
            system=SYSTEM_AWS_BEDROCK,
            operation=OP_CHAT,
            model=self._model_id,
            max_tokens=self._max_tokens,
        )

        # Bedrock-on-Anthropic request body. The `anthropic_version` is the
        # invariant Bedrock requires; bumping it without coordinating with the
        # Bedrock team is not safe.
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": self._max_tokens,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_text}],
        }

        response = await asyncio.to_thread(
            self._client.invoke_model,
            modelId=self._model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(body),
        )

        # boto3's StreamingBody is read once.
        raw = response["body"].read()
        payload = json.loads(raw)

        usage = payload.get("usage") or {}
        LOGGER.info(
            "bedrock_drafter usage: input=%s output=%s stop_reason=%s",
            usage.get("input_tokens"),
            usage.get("output_tokens"),
            payload.get("stop_reason"),
        )

        # OTel GenAI semconv — response side. Bedrock doesn't echo a response
        # model identifier; we surface the request model_id so backends still
        # see SOMETHING in gen_ai.response.model.
        stop = payload.get("stop_reason")
        set_gen_ai_response(
            model=self._model_id,
            finish_reasons=[stop] if stop else None,
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
        )

        content = payload.get("content") or []
        text_blocks = [
            block.get("text", "")
            for block in content
            if block.get("type") == "text"
        ]
        if not text_blocks:
            raise RuntimeError(
                "bedrock_drafter: no text blocks in response. "
                f"stop_reason={payload.get('stop_reason')!r} "
                f"content_types={[b.get('type') for b in content]}"
            )
        return "\n".join(text_blocks).strip() + "\n"
