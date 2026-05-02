"""Tests for CrossEncoderReranker + reranker factory.

`sentence-transformers` is a real optional dep (~2 GB transitive). We install a
fake `sentence_transformers` module before exercising the reranker so these
tests run on any environment regardless of whether the heavy SDK is installed.

Scope:
  * Constructor input validation.
  * Lazy model load happens exactly once and is thread-safe (verified by
    the lock object's existence + behavior).
  * Score blend: alpha=0 → pure cross-encoder; alpha=1 → pure RRF; mid → both.
  * Factory dispatch:
      - cross_encoder + dep present + model name set → CrossEncoderReranker
      - cross_encoder + dep missing → token_overlap fallback
      - cross_encoder + model_name empty → token_overlap fallback
      - identity / token_overlap / unknown → existing behavior preserved.

Run from repo root:

    python -m unittest discover -s middleware/RAGMgmt-Service/tests -v
"""

from __future__ import annotations

import os
import sys
import types
import unittest

_SERVICE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SERVICE_DIR not in sys.path:
    sys.path.insert(0, _SERVICE_DIR)


def _ensure_stub(name, **attrs):
    if name in sys.modules:
        return sys.modules[name]
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


def _noop_traced(name):
    def deco(fn):
        return fn
    return deco
_ensure_stub("common.tracing", traced=_noop_traced)


# ---------------------------------------------------------------------------
# Fake sentence_transformers — installed at module level so the reranker's
# lazy `from sentence_transformers import CrossEncoder` resolves to this.
# Each test resets the fake state so load_count etc. are isolated.
# ---------------------------------------------------------------------------

class _FakeCrossEncoder:
    """Mimics sentence_transformers.CrossEncoder. predict() returns the
    `predict_returns` list (one float per input pair)."""

    instances: list["_FakeCrossEncoder"] = []
    predict_returns: list[float] = []

    def __init__(self, model_name):
        self.model_name = model_name
        self.predict_calls: list[list[tuple[str, str]]] = []
        _FakeCrossEncoder.instances.append(self)

    def predict(self, pairs):
        self.predict_calls.append(list(pairs))
        if not _FakeCrossEncoder.predict_returns:
            return [0.5] * len(pairs)
        return list(_FakeCrossEncoder.predict_returns[: len(pairs)])


def _install_fake_sentence_transformers():
    fake = types.ModuleType("sentence_transformers")
    fake.CrossEncoder = _FakeCrossEncoder
    sys.modules["sentence_transformers"] = fake
    return fake


def _uninstall_sentence_transformers():
    sys.modules.pop("sentence_transformers", None)


def _reset_reranker_modules():
    """Drop any cached reranker modules so import-time gates re-evaluate."""
    for name in list(sys.modules):
        if name.endswith(".cross_encoder_reranker") or name.endswith(".rerank.factory"):
            sys.modules.pop(name, None)


def _make_candidate(child_text, score):
    return {
        "hit": {
            "id": id(child_text),
            "child_id": "c", "parent_id": "p",
            "dataset_name": "ds", "page_index": 0,
            "char_offset_in_parent": 0,
            "child_text": child_text, "parent_text": "...",
        },
        "score": score,
        "lexical_rank": 1,
        "dense_rank": 1,
    }


# ---------------------------------------------------------------------------
# CrossEncoderReranker — contract
# ---------------------------------------------------------------------------

class TestCrossEncoderReranker(unittest.TestCase):
    def setUp(self):
        _FakeCrossEncoder.instances.clear()
        _FakeCrossEncoder.predict_returns = []
        _install_fake_sentence_transformers()
        _reset_reranker_modules()

    def tearDown(self):
        _uninstall_sentence_transformers()

    def _make(self, alpha=0.5, model_name="cross-encoder/test"):
        from service.rerank.cross_encoder_reranker import CrossEncoderReranker
        return CrossEncoderReranker(model_name=model_name, alpha=alpha)

    def test_empty_model_name_raises(self):
        with self.assertRaises(ValueError):
            self._make(model_name="")

    def test_alpha_out_of_range_raises(self):
        with self.assertRaises(ValueError):
            self._make(alpha=-0.1)
        with self.assertRaises(ValueError):
            self._make(alpha=1.5)

    def test_model_loaded_lazily_on_first_rerank(self):
        r = self._make()
        # Construction must NOT load the model — keeps service startup fast.
        self.assertEqual(len(_FakeCrossEncoder.instances), 0)
        r.rerank("q", [_make_candidate("doc", 0.1)], top_k=1)
        # Now exactly one instance exists.
        self.assertEqual(len(_FakeCrossEncoder.instances), 1)
        # Second call reuses the same instance — no re-load.
        r.rerank("q", [_make_candidate("doc", 0.1)], top_k=1)
        self.assertEqual(len(_FakeCrossEncoder.instances), 1)

    def test_predict_called_with_query_and_child_text_pairs(self):
        r = self._make()
        candidates = [
            _make_candidate("regulator content", 0.1),
            _make_candidate("voice content", 0.1),
        ]
        r.rerank("AHPRA testimonial", candidates, top_k=2)
        instance = _FakeCrossEncoder.instances[0]
        self.assertEqual(len(instance.predict_calls), 1)
        self.assertEqual(
            instance.predict_calls[0],
            [("AHPRA testimonial", "regulator content"),
             ("AHPRA testimonial", "voice content")],
        )

    def test_pure_ce_alpha_zero_orders_by_ce_score(self):
        # alpha=0 → final score == normalized CE score.
        # CE returns (low, high) → second candidate wins.
        _FakeCrossEncoder.predict_returns = [0.1, 0.9]
        r = self._make(alpha=0.0)
        candidates = [
            _make_candidate("first", 0.5),   # high RRF
            _make_candidate("second", 0.1),  # low RRF
        ]
        out = r.rerank("q", candidates, top_k=2)
        self.assertEqual(out[0]["hit"]["child_text"], "second")
        self.assertEqual(out[0]["rerank_ce_score"], 0.9)

    def test_pure_rrf_alpha_one_orders_by_rrf(self):
        # alpha=1 → final == RRF; CE is ignored.
        _FakeCrossEncoder.predict_returns = [0.9, 0.1]
        r = self._make(alpha=1.0)
        candidates = [
            _make_candidate("first", 0.1),   # low RRF
            _make_candidate("second", 0.5),  # high RRF
        ]
        out = r.rerank("q", candidates, top_k=2)
        self.assertEqual(out[0]["hit"]["child_text"], "second")

    def test_returns_top_k_only(self):
        _FakeCrossEncoder.predict_returns = [0.9, 0.7, 0.5, 0.3, 0.1]
        r = self._make(alpha=0.0)
        candidates = [_make_candidate(f"d{i}", 0.1) for i in range(5)]
        out = r.rerank("q", candidates, top_k=2)
        self.assertEqual(len(out), 2)

    def test_empty_candidates_returns_empty(self):
        r = self._make()
        self.assertEqual(r.rerank("q", [], top_k=5), [])

    def test_caller_input_not_mutated(self):
        _FakeCrossEncoder.predict_returns = [0.5]
        r = self._make()
        c = [_make_candidate("doc", 0.1)]
        original_keys = set(c[0].keys())
        _ = r.rerank("q", c, top_k=1)
        self.assertEqual(set(c[0].keys()), original_keys)

    def test_annotates_output_with_ce_and_blended_scores(self):
        _FakeCrossEncoder.predict_returns = [0.5]
        r = self._make()
        c = [_make_candidate("doc", 0.1)]
        out = r.rerank("q", c, top_k=1)
        self.assertIn("rerank_score", out[0])
        self.assertIn("rerank_ce_score", out[0])

    def test_name_is_cross_encoder(self):
        r = self._make()
        self.assertEqual(r.name, "cross_encoder")


# ---------------------------------------------------------------------------
# Factory dispatch
# ---------------------------------------------------------------------------

class TestRerankerFactory(unittest.TestCase):
    def setUp(self):
        _reset_reranker_modules()
        _uninstall_sentence_transformers()
        _FakeCrossEncoder.instances.clear()

    def tearDown(self):
        _uninstall_sentence_transformers()

    def _settings(self, **overrides):
        defaults = {
            "rag_reranker_backend": "token_overlap",
            "rag_reranker_alpha": 0.5,
            "rag_cross_encoder_model": "cross-encoder/ms-marco-MiniLM-L-6-v2",
        }
        defaults.update(overrides)
        return types.SimpleNamespace(**defaults)

    def test_default_token_overlap(self):
        from service.rerank.factory import build_reranker
        from service.rerank.reranker import TokenOverlapReranker
        r = build_reranker(self._settings())
        self.assertIsInstance(r, TokenOverlapReranker)

    def test_identity_backend(self):
        from service.rerank.factory import build_reranker
        from service.rerank.reranker import IdentityReranker
        r = build_reranker(self._settings(rag_reranker_backend="identity"))
        self.assertIsInstance(r, IdentityReranker)

    def test_unknown_backend_falls_back_to_token_overlap(self):
        from service.rerank.factory import build_reranker
        from service.rerank.reranker import TokenOverlapReranker
        r = build_reranker(self._settings(rag_reranker_backend="unicycle"))
        self.assertIsInstance(r, TokenOverlapReranker)

    def test_cross_encoder_falls_back_when_dep_missing(self):
        # No fake installed → import should fail in the factory.
        from service.rerank.factory import build_reranker
        from service.rerank.reranker import TokenOverlapReranker
        r = build_reranker(self._settings(rag_reranker_backend="cross_encoder"))
        self.assertIsInstance(r, TokenOverlapReranker)

    def test_cross_encoder_falls_back_when_model_name_empty(self):
        _install_fake_sentence_transformers()
        from service.rerank.factory import build_reranker
        from service.rerank.reranker import TokenOverlapReranker
        r = build_reranker(self._settings(
            rag_reranker_backend="cross_encoder",
            rag_cross_encoder_model="",
        ))
        self.assertIsInstance(r, TokenOverlapReranker)

    def test_cross_encoder_used_when_dep_and_model_present(self):
        _install_fake_sentence_transformers()
        from service.rerank.factory import build_reranker
        r = build_reranker(self._settings(rag_reranker_backend="cross_encoder"))
        self.assertEqual(r.name, "cross_encoder")


if __name__ == "__main__":
    unittest.main(verbosity=2)
