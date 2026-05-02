"""Langfuse instrumentation — the README's primary observability commitment.

Langfuse captures prompt/completion + retrieved-chunk metadata + per-turn
faithfulness scores so each draft can be inspected post-hoc by a compliance
reviewer. The README explicitly calls this out as load-bearing for a regulated-
content use case.

Design choices:

* **Optional dep.** `langfuse` is in `[project.optional-dependencies] langfuse`,
  not the base requirements. This module gracefully no-ops when the SDK is not
  installed OR when `LANGFUSE_HOST` is unset, so a fresh local checkout doesn't
  need a running Langfuse instance to run.
* **Single touchpoint.** Instrumentation lives at the API boundary, not threaded
  through every service method. The router calls `emit_generation_trace(req,
  resp_ctx)` once after the service returns; the helper composes a complete
  trace from `respCtxData` (which already has retrieval_meta, faithfulness,
  guardrails, draft_markdown, etc. — see GenerationService). Keeps the service
  layer pure of observability concerns.
* **Lazy flush.** Langfuse's SDK batches events; we flush on FastAPI shutdown.

Set `LANGFUSE_HOST` (and the keys) to enable. Without them, this module is a
no-op — including the function calls — so production paths add zero overhead
when disabled.
"""

from __future__ import annotations

import logging
from typing import Any

LOGGER = logging.getLogger(__name__)

try:
    from langfuse import Langfuse  # type: ignore[import-not-found]
    _HAS_LANGFUSE = True
except ImportError:  # pragma: no cover — exercised by env without the dep
    Langfuse = None  # type: ignore[assignment,misc]
    _HAS_LANGFUSE = False


class LangfuseClient:
    """Thin wrapper that owns a `langfuse.Langfuse` instance — or silently
    represents the disabled state when the SDK isn't installed or the host is
    unset. Callers don't branch; they just call `emit_generation_trace` and
    `flush`."""

    def __init__(
        self,
        host: str | None,
        public_key: str | None,
        secret_key: str | None,
        environment: str | None = None,
    ) -> None:
        self._client: Any | None = None
        self._enabled = False
        if not _HAS_LANGFUSE:
            LOGGER.info(
                "Langfuse SDK not installed — observability disabled. "
                "`pip install '.[langfuse]'` to enable."
            )
            return
        if not host:
            LOGGER.info(
                "LANGFUSE_HOST is unset — Langfuse observability disabled."
            )
            return
        try:
            self._client = Langfuse(  # type: ignore[misc]
                host=host,
                public_key=public_key,
                secret_key=secret_key,
                environment=environment,
            )
            self._enabled = True
            LOGGER.info("Langfuse enabled (host=%s)", host)
        except Exception as exc:  # pragma: no cover — defensive
            LOGGER.warning(
                "Langfuse init failed; continuing without observability: %r", exc
            )
            self._client = None
            self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    def emit_generation_trace(
        self,
        topic: str,
        retrieval_mode: str,
        resp_ctx: dict[str, Any],
    ) -> None:
        """Ship a single composed trace for one generate_grounded_draft call.

        The trace shape is intentionally flat-ish — one trace, four spans
        (retrieval, drafter, faithfulness, guardrails) — because the service
        layer already serializes the stages. A future refactor that streams
        per-stage events live (rather than emitting after-the-fact) plugs in
        here without touching service or router callers.
        """
        if not self._enabled or self._client is None:
            return
        try:
            citations = resp_ctx.get("citations") or []
            retrieval_meta = resp_ctx.get("retrieval_meta") or {}
            faithfulness = resp_ctx.get("faithfulness") or {}
            guardrails = resp_ctx.get("guardrails") or {}
            draft = resp_ctx.get("draft_markdown") or ""

            trace = self._client.trace(  # type: ignore[union-attr]
                name="generate_grounded_draft",
                input=topic,
                output=draft,
                metadata={
                    "retrieval_mode": retrieval_mode,
                    "generator": resp_ctx.get("generator"),
                    "voice_profile": resp_ctx.get("voice_profile"),
                    "draft_attempts": resp_ctx.get("draft_attempts"),
                    "citation_count": len(citations),
                },
            )

            trace.span(
                name="retrieval",
                input=topic,
                output={
                    "corpora_present": retrieval_meta.get("corpora_present"),
                    "corpora_missing": retrieval_meta.get("corpora_missing"),
                    "per_corpus_hit_counts": retrieval_meta.get("per_corpus_hit_counts"),
                    "total_hits": retrieval_meta.get("total_hits"),
                    "reranker": retrieval_meta.get("reranker"),
                    "embedder": retrieval_meta.get("embedder"),
                },
            )

            trace.event(
                name="faithfulness",
                metadata={
                    "scorer": faithfulness.get("scorer"),
                    "score": faithfulness.get("score"),
                    "passed": faithfulness.get("passed"),
                    "supported_count": faithfulness.get("supported_count"),
                    "sentence_count": faithfulness.get("sentence_count"),
                    "regenerate_recommended": faithfulness.get("regenerate_recommended"),
                },
                level="WARNING" if faithfulness.get("passed") is False else "DEFAULT",
            )

            trace.event(
                name="guardrails",
                metadata={
                    "policy_id": guardrails.get("policy_id"),
                    "passed": guardrails.get("passed"),
                    "violation_count": guardrails.get("violation_count"),
                    "max_severity": guardrails.get("max_severity"),
                    # Don't ship the full violations list — could leak the rejected
                    # prompt content into observability storage. Rule IDs are safe.
                    "violated_rule_ids": [
                        v.get("rule_id")
                        for v in (guardrails.get("violations") or [])
                    ],
                },
                level="WARNING" if guardrails.get("passed") is False else "DEFAULT",
            )

            # Brief, redaction-safe citation summary — full snippets aren't
            # forwarded so an LLM-as-judge step can score grounding without
            # the trace becoming a vector for content leakage.
            trace.event(
                name="citations_summary",
                metadata={
                    "citation_count": len(citations),
                    "by_corpus_type": _count_by(citations, "corpus_type"),
                    "by_dataset": _count_by(citations, "dataset_name"),
                },
            )
        except Exception as exc:  # pragma: no cover — observability never raises
            LOGGER.warning("Langfuse trace emit failed: %r", exc)

    def flush(self) -> None:
        """Flush queued events. Safe to call when disabled."""
        if not self._enabled or self._client is None:
            return
        try:
            self._client.flush()  # type: ignore[union-attr]
        except Exception as exc:  # pragma: no cover
            LOGGER.warning("Langfuse flush failed: %r", exc)


def _count_by(items: list[dict], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        v = item.get(key) or "unknown"
        counts[v] = counts.get(v, 0) + 1
    return counts
