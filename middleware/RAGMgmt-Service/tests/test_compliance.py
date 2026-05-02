"""Stdlib unittest suite for the two compliance gates: output guardrails
(banned-phrase / forbidden-claim detection) and Self-RAG faithfulness scoring.

These are the README's load-bearing pieces — every draft passes through both
before the user sees it. Without tests, a refactor of the policy loader or
sentence splitter could silently let a regulatory breach through.

Run from repo root:

    python -m unittest discover -s middleware/RAGMgmt-Service/tests -v
"""

from __future__ import annotations

import os
import sys
import types
import unittest
from pathlib import Path

# Make the service package importable when run from repo root.
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
# Guardrails — output banned-phrase / forbidden-claim detection
# ---------------------------------------------------------------------------

class TestGuardrails(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        from common.dtos import CheckGuardrailsReqDTO, CheckGuardrailsRespDTO
        from service.guardrails.guardrails_service import GuardrailsService
        cls.ReqDTO = CheckGuardrailsReqDTO
        cls.RespDTO = CheckGuardrailsRespDTO
        cls.policy_path = (
            Path(_SERVICE_DIR) / "service" / "guardrails" / "policy.yaml"
        )
        cls.svc = GuardrailsService(policy_path=cls.policy_path)

    async def _check(self, text):
        req = self.ReqDTO(text=text)
        resp = self.RespDTO()
        rc = await self.svc.check_text(req, resp)
        self.assertEqual(rc, 0, "service must return RC_OK")
        return resp.respCtxData

    async def test_clean_text_passes(self):
        ctx = await self._check(
            "Our clinicians work within current professional standards. "
            "We do not advertise discounts on consultations."
        )
        self.assertTrue(ctx["passed"])
        self.assertEqual(ctx["violation_count"], 0)
        self.assertIsNone(ctx["max_severity"])

    async def test_superlative_caught(self):
        ctx = await self._check("We are the best clinic in town.")
        self.assertFalse(ctx["passed"])
        rule_ids = {v["rule_id"] for v in ctx["violations"]}
        self.assertIn("super_best", rule_ids)

    async def test_cure_claim_caught_critical(self):
        ctx = await self._check("Our therapy will cure your back pain.")
        self.assertFalse(ctx["passed"])
        # `cure_terms` is critical severity per policy.yaml — must surface as max.
        self.assertEqual(ctx["max_severity"], "critical")
        rule_ids = {v["rule_id"] for v in ctx["violations"]}
        self.assertIn("cure_terms", rule_ids)

    async def test_guarantee_claim_caught(self):
        ctx = await self._check("We guarantee a full recovery.")
        rule_ids = {v["rule_id"] for v in ctx["violations"]}
        self.assertIn("guarantee_terms", rule_ids)

    async def test_hundred_percent_caught(self):
        ctx = await self._check("Our treatment is 100% safe.")
        rule_ids = {v["rule_id"] for v in ctx["violations"]}
        self.assertTrue(
            "hundred_percent_claim" in rule_ids
            or "completely_safe" in rule_ids,
            f"expected absolute-safety match, got {rule_ids}",
        )

    async def test_completely_safe_caught(self):
        ctx = await self._check("This procedure is completely safe.")
        rule_ids = {v["rule_id"] for v in ctx["violations"]}
        self.assertIn("completely_safe", rule_ids)

    async def test_offsets_correct(self):
        text = "We offer the best service in the area."
        ctx = await self._check(text)
        v = next(x for x in ctx["violations"] if x["rule_id"] == "super_best")
        self.assertEqual(text[v["char_start"]:v["char_end"]].lower(), "best")

    async def test_max_severity_picks_highest(self):
        # 'cure' (critical) + 'best' (high) — max should be critical.
        ctx = await self._check("Our miracle cure is the best you'll find.")
        self.assertEqual(ctx["max_severity"], "critical")
        self.assertGreaterEqual(ctx["violation_count"], 2)

    async def test_multiple_violations_each_counted(self):
        ctx = await self._check(
            "Best clinic. Guaranteed results. Completely safe."
        )
        # Each rule fires independently — count is sum of all matches.
        self.assertGreaterEqual(ctx["violation_count"], 3)
        self.assertFalse(ctx["passed"])

    async def test_policy_metadata_surfaced(self):
        ctx = await self._check("clean text")
        self.assertEqual(ctx["policy_id"], "ahpra_baseline_v1")
        self.assertGreater(ctx["rule_count"], 0)

    async def test_policy_load_is_idempotent(self):
        # Two calls must reuse the cached policy, not re-parse YAML each time.
        ctx1 = await self._check("foo")
        ctx2 = await self._check("bar")
        self.assertEqual(ctx1["rule_count"], ctx2["rule_count"])
        self.assertIs(self.svc._policy, self.svc._ensure_policy())


# ---------------------------------------------------------------------------
# Faithfulness — Self-RAG token-overlap scoring
# ---------------------------------------------------------------------------

class TestFaithfulness(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        from common.dtos import (
            CheckFaithfulnessReqDTO,
            CheckFaithfulnessRespDTO,
            CitationSnippet,
        )
        from service.faithfulness_service import (
            FaithfulnessService,
            _split_into_claims,
            _tokenize,
        )
        cls.ReqDTO = CheckFaithfulnessReqDTO
        cls.RespDTO = CheckFaithfulnessRespDTO
        cls.Snippet = CitationSnippet
        cls.svc = FaithfulnessService()
        cls._split_into_claims = staticmethod(_split_into_claims)
        cls._tokenize = staticmethod(_tokenize)

    async def _score(self, text, citations, **overrides):
        req_kwargs = dict(text=text, citations=citations)
        req_kwargs.update(overrides)
        req = self.ReqDTO(**req_kwargs)
        resp = self.RespDTO()
        rc = await self.svc.check_text(req, resp)
        self.assertEqual(rc, 0)
        return resp.respCtxData

    def _snippet(self, text):
        return self.Snippet(snippet=text, parent_id="p0", child_id="p0_c0")

    # ---- Pure-helper tests (sentence splitter / tokenizer) -----------------

    def test_split_skips_markdown_structure(self):
        text = (
            "# Heading\n"
            "_italic note_\n"
            "---\n"
            "First substantive sentence about regulation.\n"
            "> A quote line.\n"
            "Second sentence about evidence."
        )
        sentences = self._split_into_claims(text)
        joined = " | ".join(sentences)
        # Markdown chrome dropped; substantive lines kept.
        self.assertNotIn("# Heading", joined)
        self.assertNotIn("_italic note_", joined)
        self.assertNotIn("---", joined)
        self.assertIn("First substantive sentence about regulation.", sentences)
        self.assertIn("Second sentence about evidence.", sentences)

    def test_split_handles_quote_prefix(self):
        sentences = self._split_into_claims("> Quoted regulator text here.")
        self.assertEqual(sentences, ["Quoted regulator text here."])

    def test_tokenize_strips_short_and_lowercases(self):
        toks = self._tokenize("AHPRA's Section 133 of the National Law")
        # `s` is too short, "of"/"the" are not stripped here (the faithfulness
        # tokenizer doesn't dedupe stopwords — overlap tolerates them).
        self.assertIn("ahpra", toks)
        self.assertIn("section", toks)
        self.assertIn("national", toks)
        # Confirms regex's {2,} length floor: single chars dropped.
        self.assertNotIn("s", toks)

    # ---- Service-level tests ----------------------------------------------

    async def test_no_citations_marks_evidence_free(self):
        ctx = await self._score(
            "Health practitioners must comply with the National Law.",
            citations=[],
        )
        self.assertEqual(ctx["evidence_free_count"], 1)
        self.assertFalse(ctx["passed"])
        self.assertTrue(ctx["regenerate_recommended"])
        self.assertEqual(ctx["score"], 0.0)

    async def test_full_overlap_passes(self):
        # Every sentence's tokens are entirely in the citation pool.
        cite = self._snippet(
            "Health practitioners must comply with the National Law and must "
            "not include testimonials in advertising of regulated health services."
        )
        draft = (
            "Health practitioners must comply with the National Law. "
            "They must not include testimonials in advertising of regulated "
            "health services."
        )
        ctx = await self._score(draft, citations=[cite])
        self.assertTrue(ctx["passed"])
        self.assertGreaterEqual(ctx["score"], 0.7)
        self.assertEqual(ctx["evidence_free_count"], 0)

    async def test_irrelevant_draft_fails(self):
        cite = self._snippet(
            "Health practitioners must comply with the National Law."
        )
        # Draft talks about something with zero token overlap with the cite.
        draft = (
            "Astronaut training involves centrifuge sessions and underwater "
            "neutral buoyancy practice for spacewalk simulations."
        )
        ctx = await self._score(draft, citations=[cite])
        self.assertFalse(ctx["passed"])
        self.assertTrue(ctx["regenerate_recommended"])
        self.assertLess(ctx["score"], 0.5)

    async def test_short_sentences_auto_supported(self):
        # Sentences with <4 tokens are auto-supported (too short to score).
        cite = self._snippet("anything")
        ctx = await self._score("OK. Yes. Indeed.", citations=[cite])
        # Three short sentences, all auto-supported.
        self.assertEqual(ctx["sentence_count"], 3)
        self.assertEqual(ctx["supported_count"], 3)
        for entry in ctx["per_sentence"]:
            self.assertEqual(entry["reason"], "too_short_to_check")

    async def test_per_sentence_breakdown_shape(self):
        cite = self._snippet("alpha beta gamma delta epsilon zeta")
        ctx = await self._score(
            "Alpha beta gamma delta epsilon. Foo bar baz quux quux.",
            citations=[cite],
        )
        per = ctx["per_sentence"]
        self.assertEqual(len(per), 2)
        for entry in per:
            self.assertIn("sentence", entry)
            self.assertIn("supported", entry)
            self.assertIn("overlap_ratio", entry)
        # First sentence ~100% overlap → supported; second ~0% → not supported.
        self.assertTrue(per[0]["supported"])
        self.assertFalse(per[1]["supported"])

    async def test_threshold_semantics(self):
        cite = self._snippet("alpha beta gamma delta")
        # One supported sentence + one unsupported = 0.5 score.
        draft = "Alpha beta gamma delta. Zebra zebra zebra zebra."
        # Below default 0.7 threshold:
        ctx = await self._score(draft, citations=[cite])
        self.assertAlmostEqual(ctx["score"], 0.5)
        self.assertFalse(ctx["passed"])
        # Above an explicit 0.4 threshold:
        ctx = await self._score(draft, citations=[cite], overall_threshold=0.4)
        self.assertTrue(ctx["passed"])

    async def test_per_sentence_threshold_tunable(self):
        cite = self._snippet("alpha beta gamma delta epsilon zeta")
        # 2 of 6 tokens overlap → 0.33 ratio.
        draft = "Alpha beta xx yy zz aa."
        # At default 0.25, the sentence is supported (0.33 >= 0.25).
        ctx = await self._score(draft, citations=[cite])
        self.assertTrue(ctx["per_sentence"][0]["supported"])
        # At a tighter 0.5, the sentence is not supported.
        ctx = await self._score(draft, citations=[cite], per_sentence_threshold=0.5)
        self.assertFalse(ctx["per_sentence"][0]["supported"])

    async def test_metadata_surfaced(self):
        cite = self._snippet("hello")
        ctx = await self._score("Sentence one.", citations=[cite])
        self.assertEqual(ctx["scorer"], "stub_token_overlap_v1")
        self.assertEqual(ctx["citation_count"], 1)
        self.assertIn("per_sentence_threshold", ctx)
        self.assertIn("overall_threshold", ctx)


if __name__ == "__main__":
    unittest.main(verbosity=2)
