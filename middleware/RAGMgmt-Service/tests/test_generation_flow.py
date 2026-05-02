"""End-to-end tests for GenerationService — the orchestration layer that
chains retrieval → drafter → faithfulness → guardrails (with a regenerate
loop on faithfulness failure).

Uses fake retrieval / drafter / faithfulness / guardrails so we can exercise
every branch deterministically:
  * three-corpora vs single-corpus dispatch,
  * unknown mode surfaces an error in payload (not HTTP 500),
  * faithfulness-driven regenerate loop respects max_attempts and
    drafter.supports_regeneration,
  * services disabled (None) → "skipped" markers in respCtxData,
  * service errors surface as `status: error` (no exception out of generate).

Run from repo root:

    python -m unittest discover -s middleware/RAGMgmt-Service/tests -v
"""

from __future__ import annotations

import asyncio
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
_ensure_stub("psycopg_pool", AsyncConnectionPool=object)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class _FakeRetrieval:
    """Records calls and returns canned shapes matching the real respCtxData."""

    def __init__(self):
        self.calls: list[tuple[str, object]] = []
        self.three_corpora_payload: dict | None = None
        self.hybrid_payload: dict | None = None

    async def hybrid_search(self, req, resp):
        self.calls.append(("hybrid_search", req))
        payload = self.hybrid_payload if self.hybrid_payload is not None else {
            "hits": [
                {
                    "dataset_name": "X", "page_index": 0, "parent_id": "p0",
                    "child_id": "p0_c0", "char_offset_in_parent": 0,
                    "child_text": "hello world from corpus", "rrf_score": 0.1,
                }
            ],
            "legs": {"lexical": {"hit_count": 1}, "dense": {"hit_count": 1}},
            "fusion": {"method": "rrf", "rrf_k": 60, "fused_candidate_count": 1, "returned": 1},
            "reranker": "token_overlap",
            "embedder": "stub_sha256_dim384",
        }
        resp.respCtxData.update(payload)
        return 0

    async def three_corpora_search(self, req, resp):
        self.calls.append(("three_corpora_search", req))
        payload = self.three_corpora_payload if self.three_corpora_payload is not None else {
            "per_corpus": [
                {
                    "corpus_type": "regulator",
                    "hits": [
                        {
                            "dataset_name": "Public_Regulator_Guidelines",
                            "corpus_type": "regulator",
                            "page_index": 0, "parent_id": "p0", "child_id": "p0_c0",
                            "char_offset_in_parent": 0,
                            "child_text": "AHPRA forbids testimonials in advertising.",
                            "rrf_score": 0.2, "rerank_score": 0.5,
                        }
                    ],
                },
                {
                    "corpus_type": "clinical_evidence",
                    "hits": [
                        {
                            "dataset_name": "PMC_Open_Access_FullText",
                            "corpus_type": "clinical_evidence",
                            "page_index": 0, "parent_id": "p0", "child_id": "p0_c0",
                            "char_offset_in_parent": 0,
                            "child_text": "Evidence shows physiotherapy is effective.",
                            "rrf_score": 0.18, "rerank_score": 0.45,
                        }
                    ],
                },
                {
                    "corpus_type": "practice_voice",
                    "hits": [],  # intentionally empty so corpora_missing surfaces it
                },
            ],
            "reranker": "token_overlap",
            "embedder": "stub_sha256_dim384",
        }
        resp.respCtxData.update(payload)
        return 0


class _FakeDrafter:
    def __init__(self, name="fake_drafter", supports_regeneration=False):
        self.name = name
        self.supports_regeneration = supports_regeneration
        self.calls: list[dict] = []

    async def compose_draft(self, topic, citations, voice_profile, regenerate_hint=None):
        self.calls.append({
            "topic": topic, "citation_count": len(citations),
            "voice_profile": voice_profile, "regenerate_hint": regenerate_hint,
        })
        suffix = " [regen]" if regenerate_hint else ""
        return f"# {topic}{suffix}\n[{len(citations)} citations]"


class _FakeFaithfulness:
    """Returns a canned faithfulness verdict; later attempts can be configured to
    pass so the regenerate loop's exit path is testable."""

    def __init__(self, verdicts: list[dict] | None = None):
        # Each verdict is the inner respCtxData of CheckFaithfulnessRespDTO.
        # If exhausted, last entry is reused.
        self.verdicts = verdicts or [_default_failed_verdict()]
        self.calls = 0

    async def check_text(self, req, resp):
        idx = min(self.calls, len(self.verdicts) - 1)
        resp.respCtxData.update(self.verdicts[idx])
        self.calls += 1
        return 0


class _ErroringFaithfulness:
    async def check_text(self, req, resp):
        # Non-zero return code surfaces as `status: error` in the summary.
        return 7  # arbitrary non-zero rc


class _FakeGuardrails:
    def __init__(self, ctx: dict | None = None):
        self.ctx = ctx or _default_passing_guardrails()
        self.calls = 0

    async def check_text(self, req, resp):
        resp.respCtxData.update(self.ctx)
        self.calls += 1
        return 0


def _default_failed_verdict():
    return {
        "scorer": "stub_token_overlap_v1",
        "score": 0.4,
        "passed": False,
        "overall_threshold": 0.7,
        "per_sentence_threshold": 0.25,
        "sentence_count": 5,
        "supported_count": 2,
        "evidence_free_count": 0,
        "regenerate_recommended": True,
        "per_sentence": [
            {"sentence": "Bad sentence.", "supported": False, "overlap_ratio": 0.1},
        ],
    }


def _default_passing_verdict():
    return {
        "scorer": "stub_token_overlap_v1",
        "score": 0.85,
        "passed": True,
        "overall_threshold": 0.7,
        "per_sentence_threshold": 0.25,
        "sentence_count": 5,
        "supported_count": 4,
        "evidence_free_count": 0,
        "regenerate_recommended": False,
        "per_sentence": [],
    }


def _default_passing_guardrails():
    return {
        "policy_id": "ahpra_baseline_v1",
        "rule_count": 30,
        "passed": True,
        "violation_count": 0,
        "max_severity": None,
        "violations": [],
    }


def _default_failing_guardrails():
    return {
        "policy_id": "ahpra_baseline_v1",
        "rule_count": 30,
        "passed": False,
        "violation_count": 1,
        "max_severity": "critical",
        "violations": [
            {
                "rule_id": "cure_terms",
                "category": "efficacy",
                "severity": "critical",
                "rationale": "...",
                "pattern": "...",
                "matched_text": "cure",
                "char_start": 10, "char_end": 14,
            }
        ],
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGenerationFlow(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        from common.dtos import GenerateGroundedDraftReqDTO, GenerateGroundedDraftRespDTO
        from service.generation_service import GenerationService
        cls.ReqDTO = GenerateGroundedDraftReqDTO
        cls.RespDTO = GenerateGroundedDraftRespDTO
        cls.GenerationService = GenerationService

    def _build(self, **overrides):
        retrieval = overrides.get("retrieval") or _FakeRetrieval()
        drafter = overrides.get("drafter") or _FakeDrafter()
        svc = self.GenerationService(
            retrieval_service=retrieval,
            drafter=drafter,
            guardrails_service=overrides.get("guardrails", _FakeGuardrails()),
            faithfulness_service=overrides.get("faithfulness", _FakeFaithfulness(
                verdicts=[_default_passing_verdict()]
            )),
            max_regenerate_attempts=overrides.get("max_regenerate_attempts", 1),
        )
        return svc, retrieval, drafter

    async def _run(self, svc, **req_kwargs):
        req = self.ReqDTO(topic="AHPRA telehealth advertising", **req_kwargs)
        resp = self.RespDTO()
        rc = await svc.generate_grounded_draft(req, resp)
        self.assertEqual(rc, 0)
        return resp.respCtxData

    # ---- Mode dispatch -----------------------------------------------------

    async def test_default_mode_is_three_corpora(self):
        svc, retrieval, _ = self._build()
        ctx = await self._run(svc)
        self.assertEqual(ctx["retrieval_mode"], "three_corpora")
        self.assertEqual(retrieval.calls[0][0], "three_corpora_search")

    async def test_three_corpora_surfaces_corpora_present_and_missing(self):
        svc, _, _ = self._build()
        ctx = await self._run(svc)
        meta = ctx["retrieval_meta"]
        self.assertEqual(meta["mode"], "three_corpora")
        self.assertEqual(set(meta["corpora_present"]), {"regulator", "clinical_evidence"})
        self.assertEqual(meta["corpora_missing"], ["practice_voice"])
        self.assertEqual(meta["total_hits"], 2)

    async def test_three_corpora_citations_carry_corpus_type(self):
        svc, _, _ = self._build()
        ctx = await self._run(svc)
        cits = ctx["citations"]
        self.assertEqual(len(cits), 2)
        self.assertEqual(cits[0]["corpus_type"], "regulator")
        self.assertEqual(cits[1]["corpus_type"], "clinical_evidence")

    async def test_single_corpus_mode_calls_hybrid_search(self):
        svc, retrieval, _ = self._build()
        ctx = await self._run(svc, retrieval_mode="single_corpus", dataset_name="X")
        self.assertEqual(retrieval.calls[0][0], "hybrid_search")
        self.assertEqual(ctx["retrieval_meta"]["mode"], "single_corpus")
        self.assertEqual(ctx["retrieval_meta"]["dataset_name"], "X")

    async def test_unknown_mode_surfaces_error_in_payload(self):
        svc, _, _ = self._build()
        ctx = await self._run(svc, retrieval_mode="garbage")
        self.assertIn("error", ctx)
        self.assertTrue(ctx["error"].startswith("Unknown retrieval_mode"))

    # ---- Faithfulness regenerate loop --------------------------------------

    async def test_regenerate_loop_skipped_when_drafter_unsupported(self):
        # StubDrafter pattern: supports_regeneration=False — even if faithfulness
        # fails, no regeneration happens.
        drafter = _FakeDrafter(supports_regeneration=False)
        svc, _, _ = self._build(
            drafter=drafter,
            faithfulness=_FakeFaithfulness([_default_failed_verdict()]),
            max_regenerate_attempts=2,
        )
        ctx = await self._run(svc)
        self.assertEqual(ctx["draft_attempts"], 1)
        self.assertEqual(len(drafter.calls), 1)
        self.assertEqual(ctx["regeneration_history"], [])

    async def test_regenerate_loop_runs_once_when_supported(self):
        # First attempt fails → regenerate → second attempt passes → loop exits.
        drafter = _FakeDrafter(supports_regeneration=True)
        svc, _, _ = self._build(
            drafter=drafter,
            faithfulness=_FakeFaithfulness([
                _default_failed_verdict(),     # first scoring → fail
                _default_passing_verdict(),    # second scoring → pass
            ]),
            max_regenerate_attempts=1,
        )
        ctx = await self._run(svc)
        self.assertEqual(ctx["draft_attempts"], 2)
        self.assertEqual(len(drafter.calls), 2)
        self.assertEqual(len(ctx["regeneration_history"]), 1)
        # The second drafter call carried a regenerate_hint:
        self.assertIsNotNone(drafter.calls[1]["regenerate_hint"])
        # Final faithfulness verdict is the passing one:
        self.assertTrue(ctx["faithfulness"]["passed"])

    async def test_regenerate_loop_capped_by_max_attempts(self):
        # Faithfulness keeps failing; loop should exit after max_regenerate_attempts.
        drafter = _FakeDrafter(supports_regeneration=True)
        svc, _, _ = self._build(
            drafter=drafter,
            faithfulness=_FakeFaithfulness([_default_failed_verdict()]),  # always fail
            max_regenerate_attempts=2,
        )
        ctx = await self._run(svc)
        # 1 initial + 2 regen = 3 total attempts.
        self.assertEqual(ctx["draft_attempts"], 3)
        self.assertEqual(len(drafter.calls), 3)
        self.assertEqual(len(ctx["regeneration_history"]), 2)
        # Final verdict is still failed (loop ran out of attempts):
        self.assertFalse(ctx["faithfulness"]["passed"])

    async def test_regenerate_zero_attempts_is_no_op(self):
        # max_regenerate_attempts=0 → never regenerates even if drafter supports it.
        drafter = _FakeDrafter(supports_regeneration=True)
        svc, _, _ = self._build(
            drafter=drafter,
            faithfulness=_FakeFaithfulness([_default_failed_verdict()]),
            max_regenerate_attempts=0,
        )
        ctx = await self._run(svc)
        self.assertEqual(ctx["draft_attempts"], 1)
        self.assertEqual(len(drafter.calls), 1)
        self.assertEqual(ctx["regeneration_history"], [])

    # ---- Disabled / errored compliance services ---------------------------

    async def test_faithfulness_service_none_marks_skipped(self):
        svc, _, _ = self._build(faithfulness=None)
        ctx = await self._run(svc)
        self.assertEqual(ctx["faithfulness"]["status"], "skipped")
        # No regenerate attempted when faithfulness is skipped.
        self.assertEqual(ctx["draft_attempts"], 1)

    async def test_guardrails_service_none_marks_skipped(self):
        svc, _, _ = self._build(guardrails=None)
        ctx = await self._run(svc)
        self.assertEqual(ctx["guardrails"]["status"], "skipped")

    async def test_faithfulness_service_error_surfaces_as_status_error(self):
        svc, _, _ = self._build(faithfulness=_ErroringFaithfulness())
        ctx = await self._run(svc)
        self.assertEqual(ctx["faithfulness"]["status"], "error")
        self.assertIn("rc=", ctx["faithfulness"]["reason"])

    async def test_failing_guardrails_does_not_crash_flow(self):
        svc, _, _ = self._build(guardrails=_FakeGuardrails(_default_failing_guardrails()))
        ctx = await self._run(svc)
        self.assertEqual(ctx["guardrails"]["status"], "ok")
        self.assertFalse(ctx["guardrails"]["passed"])
        self.assertEqual(ctx["guardrails"]["max_severity"], "critical")
        # Draft + citations still surface even when guardrails fail — the
        # caller decides what to do with a flagged draft.
        self.assertGreater(len(ctx["draft_markdown"]), 0)
        self.assertGreater(len(ctx["citations"]), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
