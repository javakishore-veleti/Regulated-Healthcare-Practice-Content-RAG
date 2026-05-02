"""Drafter selection factory — picks one IDrafter implementation per
`Settings.llm_drafter`. Pulled out of main.py so the dispatch is unit-testable
without dragging FastAPI / OpenTelemetry / DB pool bootstrapping in.

The factory's contract: NEVER raises. A misconfigured drafter env shouldn't
500 every /generate request — falling back to StubDrafter (with a clear
WARNING log) keeps the rest of the pipeline alive (faithfulness + guardrails
still score the stub-composed draft).
"""

from __future__ import annotations

import logging

from service.drafters.anthropic_drafter import AnthropicDrafter
from service.drafters.drafter import IDrafter
from service.drafters.stub_drafter import StubDrafter

LOGGER = logging.getLogger(__name__)


def build_drafter(settings) -> IDrafter:
    """Pick a drafter per `LLM_DRAFTER`.

    Modes:
      * `auto`     — Anthropic when ANTHROPIC_API_KEY is set, else stub.
      * `anthropic`— direct Anthropic Messages API (requires ANTHROPIC_API_KEY).
      * `bedrock`  — AWS Bedrock InvokeModel (requires `[bedrock-drafter]` extra
                     installed AND BEDROCK_MODEL_ID set; credentials come from
                     the standard AWS chain).
      * `stub`     — deterministic verbatim-citation composer (no LLM call).

    Cloud-secret refs on ANTHROPIC_API_KEY (`aws-sm://`, `azure-kv://`,
    `gcp-sm://`) are resolved at Settings load time; see common/secrets.py.
    """
    mode = (settings.llm_drafter or "auto").lower()

    if mode == "bedrock":
        return _build_bedrock_or_fallback(settings)

    api_key = settings.anthropic_api_key
    if mode in ("anthropic", "auto") and api_key:
        LOGGER.info("Using AnthropicDrafter with model=%s", settings.anthropic_model)
        return AnthropicDrafter(
            api_key=api_key,
            model=settings.anthropic_model,
            max_tokens=settings.anthropic_max_tokens,
        )
    if mode == "anthropic":
        LOGGER.warning(
            "LLM_DRAFTER=anthropic but ANTHROPIC_API_KEY is unset / unresolved; "
            "falling back to stub."
        )

    LOGGER.info("Using StubDrafter (deterministic, no LLM call)")
    return StubDrafter()


def _build_bedrock_or_fallback(settings) -> IDrafter:
    if not settings.bedrock_model_id:
        LOGGER.warning(
            "LLM_DRAFTER=bedrock but BEDROCK_MODEL_ID is unset; "
            "falling back to stub."
        )
        return StubDrafter()
    try:
        from service.drafters.bedrock_drafter import BedrockDrafter
    except ImportError as exc:
        LOGGER.warning(
            "LLM_DRAFTER=bedrock but boto3 not installed (%s); "
            "install with `pip install '.[bedrock-drafter]'`. Falling back to stub.",
            exc,
        )
        return StubDrafter()
    LOGGER.info(
        "Using BedrockDrafter with model=%s region=%s",
        settings.bedrock_model_id, settings.bedrock_region,
    )
    return BedrockDrafter(
        model_id=settings.bedrock_model_id,
        region=settings.bedrock_region,
        max_tokens=settings.anthropic_max_tokens,
    )
