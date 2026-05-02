"""Rerankers — the third stage of the Hybrid+Rerank pattern from the README.

Until this slice landed, retrieval_service truncated the RRF-fused list to
`top_k` and called that "rerank". This module replaces that with an
injectable `IReranker` interface plus two concrete implementations:

  * `IdentityReranker` — preserves the old behavior (just truncate). Useful as
    a baseline and for tests where deterministic order matters.
  * `TokenOverlapReranker` — pure-stdlib rerank that combines the RRF score with
    Jaccard token overlap between the query and each child chunk. No model, no
    deps. Good default for the small corpora in local dev.

A real cross-encoder (e.g. cross-encoder/ms-marco-MiniLM-L-6-v2 via
sentence-transformers) plugs in here as a third implementation. It is
deliberately *not* added in this slice — adding it pulls in torch (~2 GB
transitive deps) and a ~90 MB model download, which contradicts the project's
"don't pull what you can't already use" cache policy. When the user asks for
it, the implementation hooks at `IReranker` with no other code changes needed.

Selection is driven by `Settings.rag_reranker_backend` (`identity` |
`token_overlap`); see main.py.
"""

from __future__ import annotations

import re
from typing import Protocol


class IReranker(Protocol):
    name: str

    def rerank(
        self, query: str, candidates: list[dict], top_k: int
    ) -> list[dict]: ...


class IdentityReranker:
    """Passthrough — preserves RRF order, just truncates to top_k. Acts as the
    pre-slice baseline so behavior diffs against TokenOverlapReranker are
    isolated to the reranker."""

    name = "identity_truncate"

    def rerank(
        self, query: str, candidates: list[dict], top_k: int
    ) -> list[dict]:
        return list(candidates[:top_k])


class TokenOverlapReranker:
    """Combines normalized RRF score with Jaccard token overlap between the
    query and the candidate's child_text:

        final = alpha * (rrf / max_rrf) + (1 - alpha) * jaccard(Q_tokens, C_tokens)

    Tokens are case-folded ASCII word chunks with a small stopword cut. This is
    not a learned model — it's a cheap signal that biases reranking toward
    candidates whose surface form actually mentions the query terms, which the
    pure RRF score does not directly reward.

    `alpha = 0.5` (default) blends the two signals evenly. Set closer to 1.0 to
    trust the upstream hybrid+RRF more; closer to 0.0 to lean on lexical
    overlap. The reranker also annotates each returned candidate with
    `rerank_score` and `rerank_overlap` so traces explain the new ordering.
    """

    name = "token_overlap"

    def __init__(self, alpha: float = 0.5) -> None:
        if not 0.0 <= alpha <= 1.0:
            raise ValueError(f"alpha must be in [0,1], got {alpha}")
        self._alpha = alpha

    def rerank(
        self, query: str, candidates: list[dict], top_k: int
    ) -> list[dict]:
        if not candidates:
            return []

        q_tokens = _tokenize(query)
        max_rrf = max((c.get("score") or 0.0) for c in candidates) or 1.0

        scored: list[tuple[float, float, dict]] = []
        for c in candidates:
            text = (c.get("hit") or {}).get("child_text") or ""
            c_tokens = _tokenize(text)
            overlap = _jaccard(q_tokens, c_tokens)
            rrf_norm = (c.get("score") or 0.0) / max_rrf
            final = self._alpha * rrf_norm + (1.0 - self._alpha) * overlap
            scored.append((final, overlap, c))

        scored.sort(key=lambda t: -t[0])

        out: list[dict] = []
        for final, overlap, c in scored[:top_k]:
            # Shallow copy so we don't mutate the caller's input list.
            d = dict(c)
            d["rerank_score"] = round(final, 6)
            d["rerank_overlap"] = round(overlap, 6)
            out.append(d)
        return out


_STOPWORDS = frozenset(
    {
        "a", "an", "the",
        "and", "or", "but", "if", "then",
        "of", "in", "on", "at", "to", "for", "from", "with", "by", "as", "into",
        "is", "are", "was", "were", "be", "been", "being",
        "this", "that", "these", "those", "it", "its",
        "i", "we", "you", "your", "our", "they", "them", "their",
        "do", "does", "did", "have", "has", "had",
        "will", "would", "should", "can", "could", "may", "might",
        "not", "no",
    }
)

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def _tokenize(text: str) -> frozenset[str]:
    return frozenset(
        t.lower()
        for t in _TOKEN_RE.findall(text)
        if len(t) > 1 and t.lower() not in _STOPWORDS
    )


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if inter == 0:
        return 0.0
    return inter / len(a | b)
