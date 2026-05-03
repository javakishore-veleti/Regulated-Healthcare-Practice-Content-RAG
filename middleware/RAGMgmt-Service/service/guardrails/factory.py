"""Guardrails selection factory — picks IGuardrailsService per
`Settings.rag_guardrails_backend`.

Backends:
  * `regex`     — GuardrailsService (default; the 30-rule AHPRA policy).
  * `bedrock`   — BedrockGuardrailsService (managed semantic guardrails;
                  requires `[bedrock-drafter]` extra + AWS_BEDROCK_GUARDRAIL_ID).
  * `layered`   — LayeredGuardrailsService that runs regex FIRST then bedrock.
                  Recommended for production: regex catches the obvious 30
                  patterns with clear rationale; Bedrock catches paraphrased /
                  semantic violations the regex misses.

Same fall-back-with-WARNING invariant as the drafter / reranker / embedder /
retrieval factories: never raises; falls back to the regex policy when an
opt-in backend is misconfigured.
"""

from __future__ import annotations

import logging
from pathlib import Path

from service.guardrails.guardrails_service import (
    GuardrailsService,
    IGuardrailsService,
)

LOGGER = logging.getLogger(__name__)


def build_guardrails_service(
    settings, regex_policy_path: Path
) -> IGuardrailsService:
    backend = (settings.rag_guardrails_backend or "regex").lower()
    regex_layer = GuardrailsService(policy_path=regex_policy_path)

    if backend == "regex":
        LOGGER.info("Using regex GuardrailsService (30-rule AHPRA policy)")
        return regex_layer

    if backend == "bedrock":
        return _build_bedrock_or_fallback(settings, regex_layer)

    if backend == "layered":
        return _build_layered_or_fallback(settings, regex_layer)

    LOGGER.warning(
        "Unknown RAG_GUARDRAILS_BACKEND=%r — falling back to regex", backend,
    )
    return regex_layer


def _build_bedrock_layer(settings):
    """Build the Bedrock layer in isolation. Returns None if dep / config
    is missing — callers decide whether to fall back or raise."""
    if not getattr(settings, "aws_bedrock_guardrail_id", None):
        LOGGER.warning(
            "RAG_GUARDRAILS_BACKEND requires AWS_BEDROCK_GUARDRAIL_ID; "
            "Bedrock layer disabled."
        )
        return None
    try:
        from service.guardrails.bedrock_guardrails_service import (
            BedrockGuardrailsService,
        )
        import boto3  # type: ignore[import-not-found] # noqa: F401
    except ImportError as exc:
        LOGGER.warning(
            "RAG_GUARDRAILS_BACKEND requires boto3 (%s); install with "
            "`pip install '.[bedrock-drafter]'`. Bedrock layer disabled.",
            exc,
        )
        return None

    return BedrockGuardrailsService(
        guardrail_id=settings.aws_bedrock_guardrail_id,
        guardrail_version=getattr(settings, "aws_bedrock_guardrail_version", "DRAFT"),
        region=getattr(settings, "bedrock_region", "us-east-1"),
        source=getattr(settings, "aws_bedrock_guardrail_source", "OUTPUT"),
    )


def _build_bedrock_or_fallback(settings, regex_layer) -> IGuardrailsService:
    bedrock = _build_bedrock_layer(settings)
    if bedrock is None:
        LOGGER.warning(
            "Falling back to regex GuardrailsService (Bedrock layer unavailable)"
        )
        return regex_layer
    LOGGER.info(
        "Using BedrockGuardrailsService (guardrail_id=%s, version=%s) — "
        "regex layer is NOT in play; only Bedrock checks run.",
        settings.aws_bedrock_guardrail_id,
        getattr(settings, "aws_bedrock_guardrail_version", "DRAFT"),
    )
    return bedrock


def _build_layered_or_fallback(settings, regex_layer) -> IGuardrailsService:
    bedrock = _build_bedrock_layer(settings)
    if bedrock is None:
        LOGGER.warning(
            "RAG_GUARDRAILS_BACKEND=layered but Bedrock layer is unavailable; "
            "falling back to regex-only."
        )
        return regex_layer

    from service.guardrails.layered_guardrails_service import LayeredGuardrailsService
    LOGGER.info(
        "Using LayeredGuardrailsService (regex → bedrock) — "
        "regex catches obvious patterns; Bedrock catches semantic / paraphrased."
    )
    return LayeredGuardrailsService(
        layers=[regex_layer, bedrock],
        layer_names=["regex", "bedrock"],
        short_circuit_on_critical=getattr(
            settings, "rag_guardrails_short_circuit_on_critical", True,
        ),
    )
