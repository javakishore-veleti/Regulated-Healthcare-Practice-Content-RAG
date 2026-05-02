"""Tests for Langfuse observability — the README's primary observability
mechanism. Locks in:

  * Graceful no-op when the SDK isn't installed (so a fresh checkout doesn't
    fail because Langfuse is missing).
  * Graceful no-op when the SDK is installed but LANGFUSE_HOST is unset.
  * When both are present, a single composed trace is emitted from the
    respCtxData shape that GenerationService produces.
  * Trace payload doesn't ship full violation snippets / citation snippets to
    the observability backend (privacy / data-leak surface area).

Run from repo root:

    python -m unittest discover -s middleware/RAGMgmt-Service/tests -v
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path

_SERVICE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SERVICE_DIR not in sys.path:
    sys.path.insert(0, _SERVICE_DIR)

_MODULE_PATH = Path(_SERVICE_DIR) / "common" / "langfuse_client.py"


def _load_client_module(with_sdk: bool, fake_sdk_class=None):
    """Load common/langfuse_client.py from a clean module state, optionally
    injecting a fake `langfuse` SDK so tests don't need the real package."""
    # Drop any cached version from prior tests.
    for mod_name in list(sys.modules):
        if mod_name in ("langfuse",) or mod_name.endswith(".langfuse_client"):
            sys.modules.pop(mod_name, None)

    if with_sdk:
        fake = types.ModuleType("langfuse")
        fake.Langfuse = fake_sdk_class  # type: ignore[attr-defined]
        sys.modules["langfuse"] = fake
    else:
        # Force ImportError on `from langfuse import Langfuse`.
        sys.modules["langfuse"] = None  # type: ignore[assignment]

    spec = importlib.util.spec_from_file_location(
        f"_lc_{with_sdk}", _MODULE_PATH
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _FakeTrace:
    def __init__(self):
        self.events = []
        self.spans = []

    def span(self, **kwargs):
        self.spans.append(kwargs)
        return self

    def event(self, **kwargs):
        self.events.append(kwargs)


class _FakeLangfuseSDK:
    def __init__(self, **init_kwargs):
        self.init_kwargs = init_kwargs
        self.traces = []
        self.flushed = 0

    def trace(self, **kwargs):
        t = _FakeTrace()
        self.traces.append((kwargs, t))
        return t

    def flush(self):
        self.flushed += 1


_SAMPLE_RESP_CTX = {
    "retrieval_meta": {
        "corpora_present": ["regulator", "practice_voice"],
        "corpora_missing": ["clinical_evidence"],
        "per_corpus_hit_counts": {"regulator": 3, "practice_voice": 2, "clinical_evidence": 0},
        "total_hits": 5,
        "reranker": "token_overlap",
        "embedder": "stub_sha256_dim384",
    },
    "faithfulness": {
        "scorer": "stub_token_overlap_v1",
        "score": 0.85,
        "passed": True,
        "supported_count": 4,
        "sentence_count": 5,
        "regenerate_recommended": False,
    },
    "guardrails": {
        "policy_id": "ahpra_baseline_v1",
        "passed": False,
        "violation_count": 1,
        "max_severity": "critical",
        "violations": [
            {
                "rule_id": "cure_terms",
                "matched_text": "will cure your back pain",  # sensitive: shouldn't ship
                "char_start": 30,
                "char_end": 53,
            }
        ],
    },
    "draft_markdown": "# Topic\nSample draft body.\n",
    "citations": [
        {"corpus_type": "regulator", "dataset_name": "Public_Regulator_Guidelines",
         "snippet": "Practitioners must comply..."},
        {"corpus_type": "practice_voice", "dataset_name": "Practice_Voice_Sample",
         "snippet": "Our clinicians work within..."},
        {"corpus_type": "clinical_evidence", "dataset_name": "PMC_Open_Access_Subset",
         "snippet": "Evidence shows..."},
    ],
    "generator": "fake_drafter",
    "draft_attempts": 1,
    "voice_profile": "default",
}


class TestLangfuseDisabledWithoutSDK(unittest.TestCase):
    def setUp(self):
        self.mod = _load_client_module(with_sdk=False)

    def test_has_langfuse_false(self):
        self.assertFalse(self.mod._HAS_LANGFUSE)

    def test_client_disabled_even_with_host(self):
        c = self.mod.LangfuseClient(
            host="http://lf:3000", public_key="pk", secret_key="sk"
        )
        self.assertFalse(c.enabled)

    def test_emit_does_not_raise(self):
        c = self.mod.LangfuseClient(host="http://lf:3000", public_key="pk", secret_key="sk")
        # Must accept any input without raising.
        c.emit_generation_trace(
            topic="test", retrieval_mode="three_corpora", resp_ctx={}
        )
        c.emit_generation_trace(
            topic="test", retrieval_mode="three_corpora", resp_ctx=_SAMPLE_RESP_CTX
        )

    def test_flush_does_not_raise(self):
        c = self.mod.LangfuseClient(host=None, public_key=None, secret_key=None)
        c.flush()  # no-op


class TestLangfuseDisabledWithoutHost(unittest.TestCase):
    def setUp(self):
        self.mod = _load_client_module(with_sdk=True, fake_sdk_class=_FakeLangfuseSDK)

    def test_has_langfuse_true(self):
        self.assertTrue(self.mod._HAS_LANGFUSE)

    def test_client_disabled_when_host_none(self):
        c = self.mod.LangfuseClient(host=None, public_key="pk", secret_key="sk")
        self.assertFalse(c.enabled)

    def test_client_disabled_when_host_empty_string(self):
        c = self.mod.LangfuseClient(host="", public_key="pk", secret_key="sk")
        self.assertFalse(c.enabled)


class TestLangfuseEnabled(unittest.TestCase):
    def setUp(self):
        self.mod = _load_client_module(with_sdk=True, fake_sdk_class=_FakeLangfuseSDK)
        self.client = self.mod.LangfuseClient(
            host="http://localhost:3000",
            public_key="pk-lf-test",
            secret_key="sk-lf-test",
            environment="local-dev",
        )

    def test_enabled_when_host_provided(self):
        self.assertTrue(self.client.enabled)

    def test_emits_one_trace_per_call(self):
        sdk = self.client._client
        self.client.emit_generation_trace(
            topic="topic A", retrieval_mode="three_corpora", resp_ctx=_SAMPLE_RESP_CTX,
        )
        self.client.emit_generation_trace(
            topic="topic B", retrieval_mode="single_corpus", resp_ctx=_SAMPLE_RESP_CTX,
        )
        self.assertEqual(len(sdk.traces), 2)

    def test_trace_carries_topic_as_input(self):
        self.client.emit_generation_trace(
            topic="AHPRA telehealth", retrieval_mode="three_corpora",
            resp_ctx=_SAMPLE_RESP_CTX,
        )
        kwargs, _ = self.client._client.traces[-1]
        self.assertEqual(kwargs["name"], "generate_grounded_draft")
        self.assertEqual(kwargs["input"], "AHPRA telehealth")
        self.assertEqual(kwargs["output"], "# Topic\nSample draft body.\n")
        self.assertEqual(kwargs["metadata"]["retrieval_mode"], "three_corpora")
        self.assertEqual(kwargs["metadata"]["citation_count"], 3)
        self.assertEqual(kwargs["metadata"]["generator"], "fake_drafter")

    def test_emits_retrieval_span(self):
        self.client.emit_generation_trace(
            topic="t", retrieval_mode="three_corpora", resp_ctx=_SAMPLE_RESP_CTX,
        )
        _, trace = self.client._client.traces[-1]
        retrieval_spans = [s for s in trace.spans if s["name"] == "retrieval"]
        self.assertEqual(len(retrieval_spans), 1)
        out = retrieval_spans[0]["output"]
        self.assertEqual(out["corpora_present"], ["regulator", "practice_voice"])
        self.assertEqual(out["corpora_missing"], ["clinical_evidence"])
        self.assertEqual(out["reranker"], "token_overlap")

    def test_emits_faithfulness_event(self):
        self.client.emit_generation_trace(
            topic="t", retrieval_mode="three_corpora", resp_ctx=_SAMPLE_RESP_CTX,
        )
        _, trace = self.client._client.traces[-1]
        faith = [e for e in trace.events if e["name"] == "faithfulness"]
        self.assertEqual(len(faith), 1)
        meta = faith[0]["metadata"]
        self.assertEqual(meta["score"], 0.85)
        self.assertTrue(meta["passed"])
        self.assertEqual(meta["supported_count"], 4)
        # Passed → DEFAULT level (not WARNING).
        self.assertEqual(faith[0]["level"], "DEFAULT")

    def test_failed_faithfulness_logs_warning_level(self):
        ctx = dict(_SAMPLE_RESP_CTX)
        ctx["faithfulness"] = dict(_SAMPLE_RESP_CTX["faithfulness"])
        ctx["faithfulness"]["passed"] = False
        self.client.emit_generation_trace(
            topic="t", retrieval_mode="three_corpora", resp_ctx=ctx,
        )
        _, trace = self.client._client.traces[-1]
        faith = next(e for e in trace.events if e["name"] == "faithfulness")
        self.assertEqual(faith["level"], "WARNING")

    def test_guardrails_event_redacts_violation_text(self):
        # Sensitive content (matched_text, char positions) must NOT be shipped.
        # Only the rule_ids — which are non-sensitive identifiers — are forwarded.
        self.client.emit_generation_trace(
            topic="t", retrieval_mode="three_corpora", resp_ctx=_SAMPLE_RESP_CTX,
        )
        _, trace = self.client._client.traces[-1]
        gr = next(e for e in trace.events if e["name"] == "guardrails")
        meta = gr["metadata"]
        # Identifiers + verdict shipped:
        self.assertEqual(meta["policy_id"], "ahpra_baseline_v1")
        self.assertEqual(meta["max_severity"], "critical")
        self.assertEqual(meta["violated_rule_ids"], ["cure_terms"])
        # Sensitive raw match content NOT shipped:
        self.assertNotIn("matched_text", meta)
        self.assertNotIn("char_start", meta)
        # Failed guardrails surface as WARNING level.
        self.assertEqual(gr["level"], "WARNING")

    def test_citations_summary_redacts_snippets(self):
        # Citation snippets contain potentially-sensitive corpus content; only
        # aggregate counts ship.
        self.client.emit_generation_trace(
            topic="t", retrieval_mode="three_corpora", resp_ctx=_SAMPLE_RESP_CTX,
        )
        _, trace = self.client._client.traces[-1]
        summary = next(e for e in trace.events if e["name"] == "citations_summary")
        meta = summary["metadata"]
        self.assertEqual(meta["citation_count"], 3)
        self.assertEqual(
            meta["by_corpus_type"],
            {"regulator": 1, "practice_voice": 1, "clinical_evidence": 1},
        )
        # Snippet content must not have leaked into the summary.
        self.assertNotIn("snippet", meta)

    def test_count_by_helper_handles_missing_keys(self):
        items = [{"corpus_type": "x"}, {}, {"corpus_type": "x"}, {"corpus_type": None}]
        self.assertEqual(
            self.mod._count_by(items, "corpus_type"),
            {"x": 2, "unknown": 2},
        )

    def test_flush_delegates_to_sdk(self):
        self.assertEqual(self.client._client.flushed, 0)
        self.client.flush()
        self.assertEqual(self.client._client.flushed, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
