"""Stdlib unittest suite for the RAG core: pure-function logic that the rest
of the pipeline depends on. No DB, no FastAPI, no LLM — just the math.

Run from the service directory:

    cd middleware/RAGMgmt-Service && python -m unittest discover -s tests -v

Or from repo root:

    python -m unittest discover -s middleware/RAGMgmt-Service/tests -v
"""

from __future__ import annotations

import math
import os
import sys
import types
import unittest

# Make the service package importable when run from repo root.
_SERVICE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SERVICE_DIR not in sys.path:
    sys.path.insert(0, _SERVICE_DIR)


# ---------------------------------------------------------------------------
# Test fixtures: stub heavy import-time deps so these tests are runnable
# without the full venv (e.g. on a CI container that hasn't installed psycopg).
# ---------------------------------------------------------------------------

def _ensure_stub(name: str, **attrs) -> types.ModuleType:
    """Install a stub module if missing, populate it with attributes for any
    test that needs to read them. Doesn't override real installs."""
    if name in sys.modules:
        return sys.modules[name]
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


# psycopg_pool is dragged in by dao.retrieval_dao at module load. We don't
# exercise the DAO in these tests; stub the import target so retrieval_service
# still imports cleanly.
_psycopg_pool = _ensure_stub("psycopg_pool", AsyncConnectionPool=object)

# tracing decorator pulls opentelemetry. Replace with a no-op decorator before
# the modules that use it import.
def _noop_traced(name):
    def deco(fn):
        return fn
    return deco
_ensure_stub("common.tracing", traced=_noop_traced)


# ---------------------------------------------------------------------------
# 1. Embedding — load-bearing for retrieval correctness.
# ---------------------------------------------------------------------------

class TestStubEmbedding(unittest.TestCase):
    def setUp(self):
        from common.embedding import EMBED_DIM, stub_embed, vector_literal
        self.EMBED_DIM = EMBED_DIM
        self.stub_embed = stub_embed
        self.vector_literal = vector_literal

    def test_dimension_is_384(self):
        self.assertEqual(len(self.stub_embed("hello")), self.EMBED_DIM)

    def test_unit_norm(self):
        v = self.stub_embed("a moderately long passage about clinical evidence")
        norm = math.sqrt(sum(x * x for x in v))
        self.assertAlmostEqual(norm, 1.0, places=5)

    def test_deterministic(self):
        a = self.stub_embed("AHPRA testimonial advertising rules")
        b = self.stub_embed("AHPRA testimonial advertising rules")
        self.assertEqual(a, b)

    def test_different_text_different_vector(self):
        # Different inputs must yield different vectors (with overwhelming
        # probability) — guards against a future refactor that accidentally
        # hashes the empty string for everything.
        a = self.stub_embed("regulator advertising rules")
        b = self.stub_embed("clinical evidence systematic review")
        self.assertNotEqual(a, b)

    def test_empty_string_handled(self):
        v = self.stub_embed("")
        self.assertEqual(len(v), self.EMBED_DIM)

    def test_vector_literal_format(self):
        v = self.stub_embed("x")
        lit = self.vector_literal(v)
        self.assertTrue(lit.startswith("[") and lit.endswith("]"))
        # 384 comma-separated floats inside the brackets.
        self.assertEqual(lit.count(","), self.EMBED_DIM - 1)


# ---------------------------------------------------------------------------
# 2. Corpus taxonomy — three-corpora grounding hangs off this map.
# ---------------------------------------------------------------------------

class TestCorpusTypes(unittest.TestCase):
    def setUp(self):
        from common.corpus_types import (
            ALL_CORPUS_TYPES,
            DATASET_NAME_TO_CORPUS_TYPE,
            REGULATOR,
            CLINICAL_EVIDENCE,
            PRACTICE_VOICE,
            corpus_for_dataset,
            datasets_for_corpus,
        )
        self.ALL = ALL_CORPUS_TYPES
        self.MAP = DATASET_NAME_TO_CORPUS_TYPE
        self.REGULATOR = REGULATOR
        self.EVIDENCE = CLINICAL_EVIDENCE
        self.VOICE = PRACTICE_VOICE
        self.corpus_for_dataset = corpus_for_dataset
        self.datasets_for_corpus = datasets_for_corpus

    def test_three_corpus_types(self):
        self.assertEqual(set(self.ALL), {self.REGULATOR, self.EVIDENCE, self.VOICE})

    def test_every_corpus_has_at_least_one_dataset(self):
        for c in self.ALL:
            with self.subTest(corpus=c):
                self.assertGreater(
                    len(self.datasets_for_corpus(c)),
                    0,
                    f"Corpus {c} has no datasets — three-corpora retrieval will silently skip it.",
                )

    def test_every_mapped_corpus_is_known(self):
        for ds, c in self.MAP.items():
            with self.subTest(dataset=ds):
                self.assertIn(c, self.ALL, f"Dataset {ds} maps to unknown corpus {c}")

    def test_unknown_dataset_returns_none(self):
        self.assertIsNone(self.corpus_for_dataset("Definitely_Not_A_Dataset"))

    def test_seeded_datasets_present(self):
        # These names must stay aligned with the V004/V009/V010 migrations.
        for required in (
            "Public_Regulator_Guidelines",
            "Practice_Voice_Sample",
            "PMC_Open_Access_FullText",
        ):
            with self.subTest(dataset=required):
                self.assertIn(required, self.MAP)


# ---------------------------------------------------------------------------
# 3. Chunking — parent-child split, reconstruction property.
# ---------------------------------------------------------------------------

class TestChunkingHelpers(unittest.TestCase):
    def setUp(self):
        from service.chunking_service import (
            _split_into_children,
            _split_into_parents,
        )
        self.split_parents = _split_into_parents
        self.split_children = _split_into_children

    def test_parents_split_on_blank_lines(self):
        text = "paragraph one\n\nparagraph two\n\nparagraph three"
        parents = self.split_parents(text, max_size=200)
        self.assertEqual(len(parents), 3)

    def test_long_paragraph_subsplit_to_cap(self):
        # Each parent must not exceed the cap.
        long_para = "word " * 500  # 2500 chars
        parents = self.split_parents(long_para, max_size=300)
        self.assertGreater(len(parents), 1)
        for p in parents:
            with self.subTest(p=p[:30]):
                self.assertLessEqual(len(p), 300)

    def test_children_offsets_round_trip(self):
        # Each child's text should appear at its reported offset within the parent.
        parent = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu"
        children = self.split_children(parent, max_size=20)
        self.assertGreater(len(children), 1)
        for offset, child in children:
            with self.subTest(offset=offset, child=child):
                self.assertEqual(parent[offset : offset + len(child)], child)

    def test_children_respect_size_cap(self):
        parent = "x" * 1000
        children = self.split_children(parent, max_size=50)
        for offset, child in children:
            with self.subTest(child_len=len(child)):
                self.assertLessEqual(len(child), 50)


# ---------------------------------------------------------------------------
# 4. RRF fusion — math sanity for hybrid retrieval.
# ---------------------------------------------------------------------------

class TestRRFFusion(unittest.TestCase):
    def setUp(self):
        from service.retrieval_service import _rrf_fuse
        self._rrf_fuse = _rrf_fuse

    def _hit(self, hit_id):
        return {
            "id": hit_id,
            "dataset_name": "ds",
            "page_index": 0,
            "parent_id": "p0",
            "child_id": f"p0_c{hit_id}",
            "parent_text": "...",
            "child_text": f"text {hit_id}",
            "char_offset_in_parent": 0,
            "leg_score": 0.5,
        }

    def test_empty_inputs_empty_output(self):
        self.assertEqual(self._rrf_fuse([], [], k=60), [])

    def test_single_leg_in_order(self):
        hits = [self._hit(1), self._hit(2), self._hit(3)]
        fused = self._rrf_fuse(hits, [], k=60)
        # Order preserved: 1 has rank 1, gets the highest score.
        self.assertEqual([f["hit"]["id"] for f in fused], [1, 2, 3])

    def test_overlap_boosted_above_either_leg_alone(self):
        # An item appearing high in both legs should fuse above an item appearing
        # high in only one leg.
        lex = [self._hit(1), self._hit(2)]
        dense = [self._hit(2), self._hit(3)]
        fused = self._rrf_fuse(lex, dense, k=60)
        # Item 2 appears in both legs — should be #1 in fused order.
        self.assertEqual(fused[0]["hit"]["id"], 2)

    def test_lexical_only_records_no_dense_rank(self):
        lex = [self._hit(1)]
        fused = self._rrf_fuse(lex, [], k=60)
        self.assertEqual(fused[0]["lexical_rank"], 1)
        self.assertIsNone(fused[0]["dense_rank"])


# ---------------------------------------------------------------------------
# 5. Reranker — token-overlap behavior + identity baseline.
# ---------------------------------------------------------------------------

class TestRerankers(unittest.TestCase):
    def setUp(self):
        from service.rerank.reranker import (
            IdentityReranker,
            TokenOverlapReranker,
            _jaccard,
            _tokenize,
        )
        self.IdentityReranker = IdentityReranker
        self.TokenOverlapReranker = TokenOverlapReranker
        self._jaccard = _jaccard
        self._tokenize = _tokenize

    def _make_candidate(self, child_text, score):
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

    def test_tokenize_drops_stopwords(self):
        toks = self._tokenize("the AHPRA testimonial in advertising")
        # Stopwords "the" and "in" must be gone; substantive tokens stay.
        self.assertNotIn("the", toks)
        self.assertNotIn("in", toks)
        self.assertIn("ahpra", toks)
        self.assertIn("testimonial", toks)
        self.assertIn("advertising", toks)

    def test_jaccard_overlap_math(self):
        a = frozenset({"alpha", "beta", "gamma"})
        b = frozenset({"beta", "gamma", "delta"})
        # |A ∩ B|=2, |A ∪ B|=4 → 0.5
        self.assertAlmostEqual(self._jaccard(a, b), 0.5)
        # Empty side returns 0
        self.assertEqual(self._jaccard(a, frozenset()), 0.0)

    def test_identity_is_passthrough(self):
        c = [self._make_candidate("x", 0.1), self._make_candidate("y", 0.05)]
        out = self.IdentityReranker().rerank("any query", c, top_k=2)
        self.assertEqual([h["hit"]["child_text"] for h in out], ["x", "y"])

    def test_token_overlap_promotes_topical_hit(self):
        # Realistic RRF profile: hybrid retrieval often produces tight scores,
        # and the topical match comes in slightly below the noisier hit. The
        # token-overlap signal should be enough to flip them at alpha=0.5.
        # Math: max=0.10 → relevant_rrf_norm=0.8, irrelevant_rrf_norm=1.0;
        # relevant Jaccard ≈ 0.33 (3 common stems) vs irrelevant Jaccard 0.
        # final_relevant   = 0.5*0.8 + 0.5*0.33 ≈ 0.57
        # final_irrelevant = 0.5*1.0 + 0.5*0    = 0.50
        relevant = self._make_candidate(
            "AHPRA advertising rules forbid testimonials", 0.08
        )
        irrelevant = self._make_candidate(
            "telehealth follow-ups are appropriate for many concerns", 0.10
        )
        out = self.TokenOverlapReranker(alpha=0.5).rerank(
            "AHPRA testimonial rules", [relevant, irrelevant], top_k=2,
        )
        self.assertEqual(out[0]["hit"]["child_text"].split()[0], "AHPRA")
        self.assertIn("rerank_score", out[0])
        self.assertIn("rerank_overlap", out[0])

    def test_token_overlap_alpha_pure_overlap_zeroes_irrelevant(self):
        c1 = self._make_candidate("AHPRA advertising rules", 0.5)
        c2 = self._make_candidate("zebra paragraph nothing relevant", 0.5)
        out = self.TokenOverlapReranker(alpha=0.0).rerank(
            "AHPRA rules", [c1, c2], top_k=2,
        )
        # alpha=0.0 → score is pure overlap → c2 has 0 overlap → rerank_score=0
        self.assertGreater(out[0]["rerank_score"], 0.0)
        self.assertEqual(out[1]["rerank_score"], 0.0)

    def test_alpha_out_of_range_raises(self):
        with self.assertRaises(ValueError):
            self.TokenOverlapReranker(alpha=1.5)
        with self.assertRaises(ValueError):
            self.TokenOverlapReranker(alpha=-0.1)

    def test_empty_candidates_returns_empty(self):
        out = self.TokenOverlapReranker().rerank("anything", [], top_k=5)
        self.assertEqual(out, [])

    def test_caller_input_not_mutated(self):
        c = [self._make_candidate("abc", 0.1)]
        original_keys = set(c[0].keys())
        _ = self.TokenOverlapReranker().rerank("abc query", c, top_k=1)
        # Caller's candidate dict should be unchanged.
        self.assertEqual(set(c[0].keys()), original_keys)


if __name__ == "__main__":
    unittest.main(verbosity=2)
