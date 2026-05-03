"""Tests for the IEmbedder abstraction + factory.

Covers StubEmbedder (default), SentenceTransformerEmbedder (with mocked
heavy dep), and the factory's fall-back behavior. The factory must NEVER
raise — a misconfigured embedder env should fall back to stub with a
warning, not 500 every /retrieve and /generate request.

Run from repo root:

    python -m unittest discover -s middleware/RAGMgmt-Service/tests -v
"""

from __future__ import annotations

import math
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
# StubEmbedder
# ---------------------------------------------------------------------------

class TestStubEmbedder(unittest.TestCase):
    def setUp(self):
        from common.embedding import EMBED_DIM, StubEmbedder
        self.EMBED_DIM = EMBED_DIM
        self.StubEmbedder = StubEmbedder

    def test_dim_attribute(self):
        e = self.StubEmbedder()
        self.assertEqual(e.dim, self.EMBED_DIM)
        self.assertEqual(e.name, "stub_sha256_dim384")

    def test_embed_returns_unit_norm_vector(self):
        e = self.StubEmbedder()
        v = e.embed("AHPRA testimonial advertising rules")
        self.assertEqual(len(v), self.EMBED_DIM)
        norm = math.sqrt(sum(x * x for x in v))
        self.assertAlmostEqual(norm, 1.0, places=5)

    def test_deterministic(self):
        a = self.StubEmbedder().embed("same text")
        b = self.StubEmbedder().embed("same text")
        self.assertEqual(a, b)

    def test_matches_standalone_stub_embed(self):
        # The class wrapper must produce identical output to the standalone
        # function — the DAG-side handler still uses the function directly,
        # so divergence would silently misalign vector spaces.
        from common.embedding import stub_embed
        text = "alignment check"
        self.assertEqual(self.StubEmbedder().embed(text), stub_embed(text))


# ---------------------------------------------------------------------------
# SentenceTransformerEmbedder — fake the heavy dep
# ---------------------------------------------------------------------------

class _FakeSentenceTransformer:
    """Tiny stand-in for sentence_transformers.SentenceTransformer."""

    instances: list["_FakeSentenceTransformer"] = []
    encode_returns: list[list[float]] = []
    reported_dim: int = 384

    def __init__(self, model_name):
        self.model_name = model_name
        self.encode_calls: list[tuple[str, dict]] = []
        _FakeSentenceTransformer.instances.append(self)

    def get_sentence_embedding_dimension(self):
        return _FakeSentenceTransformer.reported_dim

    def encode(self, text, normalize_embeddings=False, convert_to_numpy=False):
        self.encode_calls.append((text, {
            "normalize_embeddings": normalize_embeddings,
            "convert_to_numpy": convert_to_numpy,
        }))
        # Numpy-shaped object — our embedder converts via tolist().
        class _ArrayLike:
            def __init__(self, data):
                self._data = data
            def tolist(self):
                return list(self._data)
        if _FakeSentenceTransformer.encode_returns:
            data = list(_FakeSentenceTransformer.encode_returns)
        else:
            data = [0.5] * _FakeSentenceTransformer.reported_dim
        return _ArrayLike(data)


def _install_fake_sentence_transformers():
    fake = types.ModuleType("sentence_transformers")
    fake.SentenceTransformer = _FakeSentenceTransformer
    sys.modules["sentence_transformers"] = fake
    return fake


def _uninstall_sentence_transformers():
    sys.modules.pop("sentence_transformers", None)


def _reset_embedder_modules():
    for name in list(sys.modules):
        if (
            name.endswith(".sentence_transformer_embedder")
            or name.endswith(".embedding_factory")
        ):
            sys.modules.pop(name, None)


class TestSentenceTransformerEmbedder(unittest.TestCase):
    def setUp(self):
        _FakeSentenceTransformer.instances.clear()
        _FakeSentenceTransformer.encode_returns = []
        _FakeSentenceTransformer.reported_dim = 384
        _install_fake_sentence_transformers()
        _reset_embedder_modules()

    def tearDown(self):
        _uninstall_sentence_transformers()

    def _make(self, model_name="sentence-transformers/test", expected_dim=384):
        from common.sentence_transformer_embedder import SentenceTransformerEmbedder
        return SentenceTransformerEmbedder(
            model_name=model_name, expected_dim=expected_dim,
        )

    def test_empty_model_name_raises(self):
        with self.assertRaises(ValueError):
            self._make(model_name="")

    def test_lazy_load_first_embed_only(self):
        e = self._make()
        # Construction must NOT load the model.
        self.assertEqual(len(_FakeSentenceTransformer.instances), 0)
        e.embed("first")
        self.assertEqual(len(_FakeSentenceTransformer.instances), 1)
        e.embed("second")
        # Second call reuses the same instance.
        self.assertEqual(len(_FakeSentenceTransformer.instances), 1)

    def test_dim_mismatch_raises_at_load_time(self):
        # If the operator picks a model whose output dim doesn't match the
        # configured / pgvector column, the embedder must fail visibly rather
        # than silently producing bad similarity scores.
        _FakeSentenceTransformer.reported_dim = 768
        e = self._make(expected_dim=384)
        with self.assertRaisesRegex(RuntimeError, "produces dim=768"):
            e.embed("anything")

    def test_encode_called_with_normalize_true(self):
        e = self._make()
        e.embed("hello")
        instance = _FakeSentenceTransformer.instances[0]
        self.assertEqual(len(instance.encode_calls), 1)
        text, kwargs = instance.encode_calls[0]
        self.assertEqual(text, "hello")
        self.assertTrue(kwargs["normalize_embeddings"])
        self.assertTrue(kwargs["convert_to_numpy"])

    def test_returns_python_floats(self):
        _FakeSentenceTransformer.encode_returns = [0.1] * 384
        e = self._make()
        v = e.embed("anything")
        self.assertEqual(len(v), 384)
        for x in v:
            self.assertIsInstance(x, float)


# ---------------------------------------------------------------------------
# Factory dispatch
# ---------------------------------------------------------------------------

class TestEmbedderFactory(unittest.TestCase):
    def setUp(self):
        _reset_embedder_modules()
        _uninstall_sentence_transformers()
        _FakeSentenceTransformer.instances.clear()

    def tearDown(self):
        _uninstall_sentence_transformers()

    def _settings(self, **overrides):
        defaults = {
            "rag_embedder_backend": "stub",
            "rag_embedder_model": "sentence-transformers/all-MiniLM-L6-v2",
        }
        defaults.update(overrides)
        return types.SimpleNamespace(**defaults)

    def test_default_stub(self):
        from common.embedding_factory import build_embedder
        from common.embedding import StubEmbedder
        e = build_embedder(self._settings())
        self.assertIsInstance(e, StubEmbedder)

    def test_unknown_backend_falls_back_to_stub(self):
        from common.embedding_factory import build_embedder
        from common.embedding import StubEmbedder
        e = build_embedder(self._settings(rag_embedder_backend="quantum"))
        self.assertIsInstance(e, StubEmbedder)

    def test_sentence_transformer_falls_back_when_dep_missing(self):
        # Poison `sentence_transformers` so the factory's `import
        # sentence_transformers` raises ImportError. Setting to None makes
        # Python's import machinery treat it as "tried and failed" — works
        # whether or not the dep is actually installed on disk, so this
        # test catches the fallback path in BOTH the base CI job and the
        # optional-extras-import matrix entry (which installs the dep
        # deliberately to test the import chain).
        sys.modules["sentence_transformers"] = None  # type: ignore[assignment]
        # Drop any cached factory / embedder module so the next factory
        # call re-runs its `import sentence_transformers` against the poison.
        _reset_embedder_modules()
        sys.modules.pop("common.sentence_transformer_embedder", None)
        try:
            from common.embedding_factory import build_embedder
            from common.embedding import StubEmbedder
            e = build_embedder(self._settings(rag_embedder_backend="sentence_transformer"))
            self.assertIsInstance(e, StubEmbedder)
        finally:
            sys.modules.pop("sentence_transformers", None)

    def test_sentence_transformer_falls_back_when_model_empty(self):
        _install_fake_sentence_transformers()
        from common.embedding_factory import build_embedder
        from common.embedding import StubEmbedder
        e = build_embedder(self._settings(
            rag_embedder_backend="sentence_transformer",
            rag_embedder_model="",
        ))
        self.assertIsInstance(e, StubEmbedder)

    def test_sentence_transformer_used_when_dep_and_model_present(self):
        _install_fake_sentence_transformers()
        from common.embedding_factory import build_embedder
        e = build_embedder(self._settings(
            rag_embedder_backend="sentence_transformer",
        ))
        self.assertEqual(e.name, "sentence_transformer")
        self.assertEqual(e.dim, 384)

    def test_factory_never_raises(self):
        # Operator could pass any combination — the factory's invariant is
        # to never raise. Verify against a few odd shapes.
        from common.embedding_factory import build_embedder
        cases = [
            self._settings(rag_embedder_backend=None),
            self._settings(rag_embedder_backend=""),
            self._settings(rag_embedder_backend="garbage"),
        ]
        for s in cases:
            with self.subTest(backend=s.rag_embedder_backend):
                # Should produce *some* embedder, not raise.
                e = build_embedder(s)
                self.assertTrue(hasattr(e, "embed"))
                self.assertTrue(hasattr(e, "name"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
