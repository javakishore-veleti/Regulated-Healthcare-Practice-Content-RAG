"""RAG-triad metrics — stdlib-only heuristic implementations.

The three scores match Ragas's named metrics so the Excel acceptance
criteria are directly comparable:

  * Faithfulness          ≥ 0.90 — claim-grounded support
  * Context precision     ≥ 0.75 — retrieved-context relevance
  * Answer relevance      ≥ 0.85 — answer-topic alignment

These are heuristic proxies; a `[ragas]` extra would let operators swap
in the LLM-as-judge versions without changing the harness orchestration.

Implementations:

* `compute_faithfulness` — re-uses the live FaithfulnessService score
  the /generate path already returns in respCtxData.faithfulness.score.

* `compute_context_precision` — of the retrieved citations, what fraction
  match the triple's expected_citations? Match is exact on Dataset#Section
  OR fallback prefix-match on Dataset alone (handy for pre-section-ID
  corpora).

* `compute_answer_relevance` — Jaccard token overlap between the topic and
  the generated draft, with stopwords filtered. Captures whether the
  draft is on-topic at the surface level.
"""

from __future__ import annotations

import re
from typing import Iterable


_TOKEN_RE = re.compile(r"[A-Za-z0-9]{2,}")
_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "of", "in", "on", "at", "to", "for",
    "from", "with", "by", "as", "is", "are", "was", "were", "be", "been",
    "this", "that", "it", "its", "do", "does", "did", "have", "has", "had",
    "what", "how", "why", "who", "when", "where", "which", "their", "they",
    "any", "some", "about", "into", "such",
})


def _tokens(text: str) -> frozenset[str]:
    return frozenset(
        t.lower() for t in _TOKEN_RE.findall(text)
        if t.lower() not in _STOPWORDS and len(t) > 1
    )


def compute_faithfulness(resp_ctx: dict) -> float:
    """Pull faithfulness.score from the /generate respCtxData. Returns 0.0
    when faithfulness was skipped / errored — those count as failures
    toward the 0.9 acceptance bar."""
    f = resp_ctx.get("faithfulness") or {}
    if f.get("status") != "ok":
        return 0.0
    score = f.get("score")
    if score is None:
        return 0.0
    return float(score)


def compute_context_precision(
    resp_ctx: dict, expected_citations: Iterable[str]
) -> float:
    """Of the retrieved citations, what fraction match the expected list?

    Match rules (in order):
      1. Exact match on `Dataset#Section_id` form.
      2. Prefix match on `Dataset` alone (covers pre-section-ID corpora).

    A triple with empty expected_citations gets 1.0 — there's nothing to
    not match. A response with zero citations gets 0.0 unless expected
    is also empty (in which case 1.0 again, vacuously)."""
    expected = list(expected_citations)
    citations = resp_ctx.get("citations") or []
    if not expected:
        return 1.0
    if not citations:
        return 0.0

    expected_full = {e for e in expected if "#" in e}
    expected_dataset_only = {e for e in expected if "#" not in e}

    matches = 0
    for cit in citations:
        ds = cit.get("dataset_name") or ""
        section_id = cit.get("section_id")
        if section_id:
            full = f"{ds}#{section_id}"
            if full in expected_full:
                matches += 1
                continue
        if ds in expected_dataset_only:
            matches += 1
    return matches / max(len(citations), 1)


def compute_answer_relevance(topic: str, draft_markdown: str) -> float:
    """Jaccard token overlap between topic tokens and draft tokens.

    Empty topic OR empty draft → 0.0. Tight overlap → high score; drafts
    that are on-topic but use synonyms get penalized — that's a known
    limitation of the heuristic and the upgrade path is Ragas's
    LLM-as-judge `answer_relevancy` metric."""
    topic_tokens = _tokens(topic)
    draft_tokens = _tokens(draft_markdown)
    if not topic_tokens or not draft_tokens:
        return 0.0
    inter = topic_tokens & draft_tokens
    union = topic_tokens | draft_tokens
    if not union:
        return 0.0
    # Use the FRACTION OF TOPIC TOKENS COVERED — heavier weight on the
    # topic side than vanilla Jaccard, because a draft can legitimately
    # introduce new tokens (citations, supporting detail) without being
    # off-topic. This matches the Ragas `answer_relevancy` framing more
    # closely than symmetric Jaccard.
    return len(inter) / len(topic_tokens)


def passes(triad: dict) -> dict:
    """Acceptance verdict per the Excel thresholds."""
    return {
        "faithfulness_pass":          triad["faithfulness"] >= 0.90,
        "context_precision_pass":     triad["context_precision"] >= 0.75,
        "answer_relevance_pass":      triad["answer_relevance"] >= 0.85,
        "all_pass": (
            triad["faithfulness"] >= 0.90
            and triad["context_precision"] >= 0.75
            and triad["answer_relevance"] >= 0.85
        ),
    }
