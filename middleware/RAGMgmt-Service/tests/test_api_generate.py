"""FastAPI TestClient integration tests for /generate.

The unit tests in test_generation_flow.py cover GenerationService end-to-end
with mocked dependencies. These tests cover the HTTP layer that those tests
don't see:

  * Request body validation (pydantic rejects malformed payloads).
  * Response shape (respCtxData wraps payload per the project DTO contract).
  * FastAPI routing — /generate actually maps to the right handler.
  * Service errors → HTTP 500 (not silent 200 with broken body).
  * The Langfuse trace fan-out at the end of the handler.
  * Dependency injection (`Depends(get_generation_service)` etc.) resolves
    against `app.state` correctly.

We mount the router on a fresh FastAPI app rather than booting the real
service's lifespan — that way these tests don't need a DB pool or any of
the real init_otel / build_pool surface. The router handlers themselves
read services off `request.app.state`, so seeding fakes there is enough.

Skipped gracefully when FastAPI isn't importable (rare — it's a base dep —
but the rest of the test suite stays runnable on bare stdlib).

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


# Bypass the heavy import chain: psycopg_pool is needed only by retrieval_dao
# (we don't load it in this test). tracing decorator is a no-op.
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


try:
    from fastapi import FastAPI  # noqa: F401
    from fastapi.testclient import TestClient
    _HAS_FASTAPI = True
except ImportError:
    _HAS_FASTAPI = False


# ---------------------------------------------------------------------------
# Fake services — minimal surfaces matching what the router handlers call.
# ---------------------------------------------------------------------------

class _FakeGenerationService:
    """Records the (req, resp) call and writes a canned respCtxData."""

    def __init__(self, *, return_rc=0, payload=None):
        self.calls = []
        self._return_rc = return_rc
        self._payload = payload or {
            "topic": "<set in test>",
            "retrieval_mode": "three_corpora",
            "draft_markdown": "# Topic\nGenerated body.\n",
            "draft_attempts": 1,
            "regeneration_history": [],
            "citations": [
                {
                    "marker": "[1]",
                    "dataset_name": "Public_Regulator_Guidelines",
                    "corpus_type": "regulator",
                    "page_index": 0,
                    "parent_id": "p0",
                    "child_id": "p0_c0",
                    "char_offset_in_parent": 0,
                    "snippet": "Practitioners must comply...",
                    "rrf_score": 0.2,
                    "rerank_score": 0.5,
                },
            ],
            "retrieval_meta": {
                "mode": "three_corpora",
                "corpora_present": ["regulator"],
                "corpora_missing": ["clinical_evidence", "practice_voice"],
                "per_corpus_hit_counts": {
                    "regulator": 1, "clinical_evidence": 0, "practice_voice": 0,
                },
                "total_hits": 1,
                "reranker": "token_overlap",
                "embedder": "stub_sha256_dim384",
            },
            "faithfulness": {
                "status": "ok", "score": 0.85, "passed": True,
                "scorer": "stub_token_overlap_v1",
                "supported_count": 4, "sentence_count": 5,
                "regenerate_recommended": False,
            },
            "guardrails": {
                "status": "ok", "policy_id": "ahpra_baseline_v1",
                "rule_count": 30, "passed": True, "violation_count": 0,
                "max_severity": None, "violations": [],
            },
            "generator": "stub_compose_with_citations",
            "voice_profile": "default",
        }

    async def generate_grounded_draft(self, req, resp):
        self.calls.append(req)
        resp.respCtxData.update(self._payload)
        resp.respCtxData["topic"] = req.topic  # echo back for assertion
        return self._return_rc


class _SpyLangfuseClient:
    """Records emit_generation_trace calls — verifies the API handler emits
    the trace at the end. enabled=False ensures we never hit a real SDK."""

    def __init__(self):
        self.emissions = []
        self.enabled = False

    def emit_generation_trace(self, *, topic, retrieval_mode, resp_ctx):
        self.emissions.append({
            "topic": topic,
            "retrieval_mode": retrieval_mode,
            "resp_ctx_keys": sorted(resp_ctx.keys()),
        })

    def flush(self):
        pass


def _build_app(generation_service, langfuse_client=None):
    from fastapi import FastAPI
    from api import generation_router
    app = FastAPI()
    app.state.generation_service = generation_service
    app.state.langfuse_client = langfuse_client or _SpyLangfuseClient()
    app.include_router(generation_router.router)
    return app


@unittest.skipUnless(_HAS_FASTAPI, "fastapi not installed")
class TestGenerateEndpoint(unittest.TestCase):
    """Exercises POST /generate end-to-end through TestClient."""

    def test_happy_path_three_corpora(self):
        svc = _FakeGenerationService()
        app = _build_app(svc)
        with TestClient(app) as client:
            resp = client.post("/generate", json={
                "topic": "AHPRA telehealth advertising",
            })
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        # respCtxData wrapper per the project DTO convention.
        self.assertIn("respCtxData", body)
        ctx = body["respCtxData"]
        self.assertEqual(ctx["topic"], "AHPRA telehealth advertising")
        # Default retrieval_mode is three_corpora.
        self.assertEqual(svc.calls[0].retrieval_mode, "three_corpora")

    def test_validation_rejects_empty_topic(self):
        # pydantic's `min_length=1` on `topic` rejects empty strings.
        svc = _FakeGenerationService()
        app = _build_app(svc)
        with TestClient(app) as client:
            resp = client.post("/generate", json={"topic": ""})
        self.assertEqual(resp.status_code, 422)
        # Service must NOT have been called when validation fails.
        self.assertEqual(svc.calls, [])

    def test_validation_rejects_missing_topic(self):
        svc = _FakeGenerationService()
        app = _build_app(svc)
        with TestClient(app) as client:
            resp = client.post("/generate", json={})
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(svc.calls, [])

    def test_validation_rejects_top_k_per_corpus_above_max(self):
        # DTO caps at 10.
        svc = _FakeGenerationService()
        app = _build_app(svc)
        with TestClient(app) as client:
            resp = client.post("/generate", json={
                "topic": "x", "top_k_per_corpus": 99,
            })
        self.assertEqual(resp.status_code, 422)

    def test_service_returns_nonzero_rc_yields_500(self):
        # Per generation_router: rc != RC_OK → HTTPException(500).
        svc = _FakeGenerationService(return_rc=7)
        app = _build_app(svc)
        with TestClient(app) as client:
            resp = client.post("/generate", json={"topic": "x"})
        self.assertEqual(resp.status_code, 500)

    def test_langfuse_trace_emitted_after_service(self):
        # Lock the observability touchpoint: the handler must emit a Langfuse
        # trace AFTER the service returns, with the topic + retrieval_mode +
        # respCtxData passed through.
        svc = _FakeGenerationService()
        spy_lf = _SpyLangfuseClient()
        app = _build_app(svc, langfuse_client=spy_lf)
        with TestClient(app) as client:
            resp = client.post("/generate", json={
                "topic": "AHPRA testimonials",
                "retrieval_mode": "three_corpora",
            })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(spy_lf.emissions), 1)
        emit = spy_lf.emissions[0]
        self.assertEqual(emit["topic"], "AHPRA testimonials")
        self.assertEqual(emit["retrieval_mode"], "three_corpora")
        # Ensure the resp_ctx the trace receives carries the load-bearing keys.
        for required in ("draft_markdown", "citations", "retrieval_meta",
                         "faithfulness", "guardrails"):
            self.assertIn(required, emit["resp_ctx_keys"])

    def test_single_corpus_mode_threads_through(self):
        svc = _FakeGenerationService()
        app = _build_app(svc)
        with TestClient(app) as client:
            resp = client.post("/generate", json={
                "topic": "x",
                "retrieval_mode": "single_corpus",
                "dataset_name": "Public_Regulator_Guidelines",
                "top_k": 3,
            })
        self.assertEqual(resp.status_code, 200)
        req = svc.calls[0]
        self.assertEqual(req.retrieval_mode, "single_corpus")
        self.assertEqual(req.dataset_name, "Public_Regulator_Guidelines")
        self.assertEqual(req.top_k, 3)

    def test_response_carries_citations_with_corpus_type(self):
        # The customer portal renders chips off citations[].corpus_type, so the
        # serialized response shape MUST carry that field.
        svc = _FakeGenerationService()
        app = _build_app(svc)
        with TestClient(app) as client:
            resp = client.post("/generate", json={"topic": "x"})
        ctx = resp.json()["respCtxData"]
        self.assertGreater(len(ctx["citations"]), 0)
        for c in ctx["citations"]:
            self.assertIn("corpus_type", c)


if __name__ == "__main__":
    unittest.main(verbosity=2)
