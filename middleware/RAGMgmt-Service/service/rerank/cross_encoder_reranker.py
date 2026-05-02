"""Cross-encoder reranker — the README's named third stage of Hybrid+Rerank.

Distinct from `TokenOverlapReranker`: a learned cross-encoder (default
`cross-encoder/ms-marco-MiniLM-L-6-v2` from sentence-transformers) scores
each (query, candidate) pair via a transformer encoder, capturing semantic
relevance that the pure-stdlib token-overlap blend can't see.

Tradeoffs:

* Adds the `sentence-transformers` dep (~150 MB) which transitively pulls
  `torch` (~2 GB on first install) and downloads the model (~90 MB) on
  first use. That's why this is opt-in via `[cross-encoder-rerank]` extra
  AND `RAG_RERANKER_BACKEND=cross_encoder`. The factory falls back to the
  pure-stdlib token-overlap reranker when either is missing.
* Model loading is **lazy** — happens on first `.rerank()` call, not in
  __init__. This keeps service startup fast and makes the cold-load cost
  attributable to the first request that actually needs it. A preload
  strategy can layer on later if startup scoring is a concern.
* Reranking blends the cross-encoder score with the upstream RRF score
  using the same alpha mechanic as TokenOverlapReranker, so operators can
  trust either signal more by tuning alpha without changing backends.
"""

from __future__ import annotations

import logging
import threading

from common.tracing import traced

LOGGER = logging.getLogger(__name__)


class CrossEncoderReranker:
    """Learned reranker. Implements the same `IReranker` shape as
    TokenOverlapReranker so retrieval_service can call either uniformly.

    `final = alpha * (rrf / max_rrf) + (1 - alpha) * normalized_ce_score`
    where ce_score is the raw output of the cross-encoder (sigmoid of logit
    for ms-marco-MiniLM models). Normalization is min-max within the
    candidate pool so the blend stays in [0, 1].
    """

    name = "cross_encoder"

    def __init__(self, model_name: str, alpha: float = 0.5) -> None:
        if not 0.0 <= alpha <= 1.0:
            raise ValueError(f"alpha must be in [0,1], got {alpha}")
        if not model_name:
            raise ValueError(
                "CrossEncoderReranker requires a model_name; set "
                "RAG_CROSS_ENCODER_MODEL (default cross-encoder/ms-marco-MiniLM-L-6-v2)."
            )
        self._model_name = model_name
        self._alpha = alpha
        self._model = None
        self._load_lock = threading.Lock()

    def _ensure_model(self):
        """Load the cross-encoder lazily and only once. Thread-safe so the
        first concurrent burst of requests doesn't trigger N parallel loads
        (the model download is the slow part)."""
        if self._model is not None:
            return self._model
        with self._load_lock:
            if self._model is not None:
                return self._model
            # Lazy import — keeps the optional dep gate at the call site.
            from sentence_transformers import CrossEncoder  # type: ignore[import-not-found]
            LOGGER.info(
                "CrossEncoderReranker: loading model=%s (cold load — first "
                "rerank call will pay the latency cost)", self._model_name,
            )
            self._model = CrossEncoder(self._model_name)
            return self._model

    @traced("retrieval.rerank.cross_encoder")
    def rerank(
        self, query: str, candidates: list[dict], top_k: int
    ) -> list[dict]:
        if not candidates:
            return []

        model = self._ensure_model()

        pairs = [
            (query, (c.get("hit") or {}).get("child_text") or "")
            for c in candidates
        ]
        # CrossEncoder.predict returns a numpy array; convert to plain floats.
        raw_scores = list(map(float, model.predict(pairs)))

        max_rrf = max((c.get("score") or 0.0) for c in candidates) or 1.0
        ce_min = min(raw_scores)
        ce_max = max(raw_scores)
        ce_range = (ce_max - ce_min) or 1.0

        scored: list[tuple[float, float, dict]] = []
        for c, ce in zip(candidates, raw_scores):
            ce_norm = (ce - ce_min) / ce_range
            rrf_norm = (c.get("score") or 0.0) / max_rrf
            final = self._alpha * rrf_norm + (1.0 - self._alpha) * ce_norm
            scored.append((final, ce, c))

        scored.sort(key=lambda t: -t[0])

        out: list[dict] = []
        for final, ce, c in scored[:top_k]:
            d = dict(c)  # shallow copy — don't mutate caller's input
            d["rerank_score"] = round(final, 6)
            d["rerank_ce_score"] = round(ce, 6)
            out.append(d)
        return out
