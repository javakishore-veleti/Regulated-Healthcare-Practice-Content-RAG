"""OpenTelemetry GenAI semantic-convention helpers.

Project A Excel Task 3 — instrument every LLM/embedder component with the
GenAI semantic conventions so traces are interoperable across Langfuse,
LangSmith, and generic OTel-aware backends.

Reference: https://opentelemetry.io/docs/specs/semconv/gen-ai/

These helpers don't create spans — they set attributes on the CURRENT span
(typically the one started by the `traced` decorator). Call sites are the
drafter `compose_draft` and embedder `embed` methods, where the system /
model / token-usage values are known.

Attribute naming is normative per the GenAI spec:

  Request side (set BEFORE the LLM/embedder call):
    gen_ai.system                  — provider id (e.g. "anthropic", "aws.bedrock")
    gen_ai.operation.name          — operation type (e.g. "chat", "embedding")
    gen_ai.request.model           — model identifier requested
    gen_ai.request.max_tokens      — request-side cap (drafters only)

  Response side (set AFTER the call returns):
    gen_ai.response.model          — actual model used (may differ from request)
    gen_ai.response.finish_reasons — list of stop reasons
    gen_ai.usage.input_tokens      — prompt tokens consumed
    gen_ai.usage.output_tokens     — completion tokens generated
"""

from __future__ import annotations

from typing import Any, Iterable

from opentelemetry import trace


# Provider identifiers — keep aligned with the GenAI spec's recommended values.
SYSTEM_ANTHROPIC = "anthropic"
SYSTEM_AWS_BEDROCK = "aws.bedrock"
SYSTEM_HUGGINGFACE_ST = "huggingface.sentence_transformers"
SYSTEM_RHC_STUB = "rhc.stub"  # internal stub generators (drafter, embedder)

# Operation names per the spec.
OP_CHAT = "chat"
OP_TEXT_COMPLETION = "text_completion"
OP_EMBEDDING = "embedding"


def set_gen_ai_request(
    *,
    system: str,
    operation: str,
    model: str,
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> None:
    """Set gen_ai.* request-side attributes on the current span.

    Safe to call when no span is active (no-ops in that case)."""
    span = trace.get_current_span()
    if span is None:
        return
    attrs: dict[str, Any] = {
        "gen_ai.system": system,
        "gen_ai.operation.name": operation,
        "gen_ai.request.model": model,
    }
    if max_tokens is not None:
        attrs["gen_ai.request.max_tokens"] = max_tokens
    if temperature is not None:
        attrs["gen_ai.request.temperature"] = temperature
    for k, v in attrs.items():
        span.set_attribute(k, v)


def set_gen_ai_response(
    *,
    model: str | None = None,
    finish_reasons: Iterable[str] | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
) -> None:
    """Set gen_ai.* response-side attributes on the current span.

    Each argument is optional — backends report different subsets (Bedrock
    omits response model identifier, sentence-transformers has no token
    counts). Only the available values are emitted; missing ones don't
    appear as attributes."""
    span = trace.get_current_span()
    if span is None:
        return
    if model is not None:
        span.set_attribute("gen_ai.response.model", model)
    if finish_reasons is not None:
        # Spec wants a string array — coerce just in case.
        span.set_attribute(
            "gen_ai.response.finish_reasons",
            [str(r) for r in finish_reasons],
        )
    if input_tokens is not None:
        span.set_attribute("gen_ai.usage.input_tokens", int(input_tokens))
    if output_tokens is not None:
        span.set_attribute("gen_ai.usage.output_tokens", int(output_tokens))
