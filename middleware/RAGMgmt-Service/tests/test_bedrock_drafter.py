"""Tests for BedrockDrafter — locks the Bedrock-on-Anthropic transport shape.

Doesn't hit AWS. boto3 is a real optional dep (`pip install '.[bedrock-drafter]'`),
so we install a fake `boto3` module before loading the drafter — this lets the
tests run on any environment regardless of whether boto3 is installed.

Scope:
  * Constructor rejects empty model_id with ValueError (BEDROCK_MODEL_ID is
    the load-bearing required field).
  * Successful invoke decodes the Bedrock response shape correctly.
  * Empty content / no text blocks raises with stop_reason captured.
  * `_build_drafter` selection in main.py:
      - mode=bedrock + missing model_id → falls back to stub (no exception)
      - mode=bedrock + boto3 missing    → falls back to stub (no exception)

Run from repo root:

    python -m unittest discover -s middleware/RAGMgmt-Service/tests -v
"""

from __future__ import annotations

import asyncio
import io
import json
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
# Fake boto3 — installed at module level so BedrockDrafter's `import boto3`
# inside __init__ resolves to this. Each test resets the fake state.
# ---------------------------------------------------------------------------

class _FakeStreamingBody:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self):
        return self._payload


class _FakeBedrockClient:
    """Records invoke_model calls; returns a canned Bedrock-on-Anthropic
    response shape that BedrockDrafter parses."""

    def __init__(self, response_payload: dict | None = None,
                 raise_on_invoke: Exception | None = None):
        self.calls: list[dict] = []
        self._response = response_payload or {
            "id": "msg_xyz",
            "type": "message",
            "role": "assistant",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 100, "output_tokens": 50},
            "content": [
                {"type": "text", "text": "# Topic\nDraft body grounded in [1].\n"}
            ],
        }
        self._raise = raise_on_invoke

    def invoke_model(self, modelId, contentType, accept, body):
        if self._raise is not None:
            raise self._raise
        self.calls.append({
            "modelId": modelId, "contentType": contentType,
            "accept": accept, "body": body,
        })
        return {
            "body": _FakeStreamingBody(json.dumps(self._response).encode("utf-8")),
        }


# Module-level fake boto3 — lazy-installed by the helper.
def _install_fake_boto3(client_factory):
    """Install a fake boto3 module that returns `client_factory()` from
    boto3.client(...). Returns the fake module."""
    fake = types.ModuleType("boto3")
    fake.client = lambda service, region_name=None: client_factory()  # noqa: ARG005
    sys.modules["boto3"] = fake
    return fake


class TestBedrockDrafterContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # AnthropicDrafter is imported by BedrockDrafter for SYSTEM_PROMPT;
        # ensure its load-time deps are fakeable too.
        _ensure_stub("anthropic", AsyncAnthropic=lambda **k: None)

    def setUp(self):
        # Drop any cached BedrockDrafter so fresh `import boto3` resolves to a
        # fresh fake per test.
        for name in list(sys.modules):
            if name.endswith(".bedrock_drafter"):
                sys.modules.pop(name, None)
        sys.modules.pop("boto3", None)

    def test_empty_model_id_raises(self):
        from service.drafters.bedrock_drafter import BedrockDrafter
        # boto3 import is lazy inside __init__ — the model_id check runs first
        # so we never reach the import.
        with self.assertRaises(ValueError):
            BedrockDrafter(model_id="", region="us-east-1", max_tokens=1000)

    def test_invoke_returns_text(self):
        client = _FakeBedrockClient()
        _install_fake_boto3(lambda: client)
        from service.drafters.bedrock_drafter import BedrockDrafter

        drafter = BedrockDrafter(
            model_id="anthropic.claude-x", region="us-east-1", max_tokens=500,
        )
        result = asyncio.run(drafter.compose_draft(
            topic="AHPRA telehealth advertising",
            citations=[
                {"child_text": "AHPRA forbids testimonials.", "dataset_name": "X",
                 "page_index": 0, "parent_id": "p0"},
            ],
            voice_profile="plain English",
        ))
        self.assertIn("Draft body grounded in [1]", result)
        # Trailing newline for downstream consumers (chunker, faithfulness)
        self.assertTrue(result.endswith("\n"))

        # Verify request shape
        self.assertEqual(len(client.calls), 1)
        body = json.loads(client.calls[0]["body"])
        self.assertEqual(body["anthropic_version"], "bedrock-2023-05-31")
        self.assertEqual(body["max_tokens"], 500)
        self.assertEqual(body["messages"][0]["role"], "user")
        self.assertIn("Topic: AHPRA telehealth advertising", body["messages"][0]["content"])
        self.assertIn("[1]", body["messages"][0]["content"])

    def test_regenerate_hint_threaded(self):
        client = _FakeBedrockClient()
        _install_fake_boto3(lambda: client)
        from service.drafters.bedrock_drafter import BedrockDrafter

        drafter = BedrockDrafter(
            model_id="anthropic.claude-x", region="us-east-1", max_tokens=500,
        )
        asyncio.run(drafter.compose_draft(
            topic="t", citations=[],
            voice_profile=None,
            regenerate_hint="The previous draft scored 0.4.",
        ))
        body = json.loads(client.calls[0]["body"])
        self.assertIn("Regeneration hint", body["messages"][0]["content"])
        self.assertIn("scored 0.4", body["messages"][0]["content"])

    def test_empty_content_raises(self):
        client = _FakeBedrockClient(response_payload={
            "stop_reason": "max_tokens",
            "content": [],  # Bedrock can return empty when truncated
        })
        _install_fake_boto3(lambda: client)
        from service.drafters.bedrock_drafter import BedrockDrafter

        drafter = BedrockDrafter(
            model_id="m", region="us-east-1", max_tokens=10,
        )
        with self.assertRaisesRegex(RuntimeError, "no text blocks"):
            asyncio.run(drafter.compose_draft(
                topic="t", citations=[], voice_profile=None,
            ))

    def test_supports_regeneration_is_true(self):
        client = _FakeBedrockClient()
        _install_fake_boto3(lambda: client)
        from service.drafters.bedrock_drafter import BedrockDrafter

        drafter = BedrockDrafter(model_id="m", region="us-east-1", max_tokens=10)
        # The Self-RAG regenerate loop only runs when this is True.
        self.assertTrue(drafter.supports_regeneration)
        self.assertEqual(drafter.name, "bedrock_anthropic_claude_drafter")


class TestBuildDrafterSelection(unittest.TestCase):
    """Lock the drafter-selection fallback behavior. A misconfigured drafter
    env must not 500 every /generate request — `build_drafter` returns a
    StubDrafter with a WARNING log instead, so the rest of the pipeline
    (faithfulness + guardrails) still scores the stub-composed draft."""

    def setUp(self):
        for name in list(sys.modules):
            if (
                name.endswith(".bedrock_drafter")
                or name.endswith(".factory")
                or name == "boto3"
            ):
                sys.modules.pop(name, None)

    def _fake_settings(self, **overrides):
        defaults = {
            "llm_drafter": "bedrock",
            "anthropic_api_key": None,
            "anthropic_model": "claude-opus-4-7",
            "anthropic_max_tokens": 1500,
            "bedrock_model_id": "",
            "bedrock_region": "us-east-1",
        }
        defaults.update(overrides)
        return types.SimpleNamespace(**defaults)

    def test_bedrock_mode_falls_back_when_model_id_missing(self):
        from service.drafters.factory import build_drafter
        from service.drafters.stub_drafter import StubDrafter
        d = build_drafter(self._fake_settings(bedrock_model_id=""))
        self.assertIsInstance(d, StubDrafter)

    def test_bedrock_mode_falls_back_when_boto3_missing(self):
        from service.drafters.factory import build_drafter
        from service.drafters.stub_drafter import StubDrafter
        # Force ImportError on the `from service.drafters.bedrock_drafter import …`
        # inside the factory's bedrock branch. Setting the entry to None makes
        # a `from X import Y` raise ImportError, which is what we test for.
        sys.modules["service.drafters.bedrock_drafter"] = None  # type: ignore[assignment]
        try:
            d = build_drafter(
                self._fake_settings(bedrock_model_id="anthropic.claude-x")
            )
            self.assertIsInstance(d, StubDrafter)
        finally:
            sys.modules.pop("service.drafters.bedrock_drafter", None)

    def test_bedrock_mode_uses_bedrock_when_both_present(self):
        client = _FakeBedrockClient()
        _install_fake_boto3(lambda: client)
        from service.drafters.factory import build_drafter
        d = build_drafter(
            self._fake_settings(bedrock_model_id="anthropic.claude-x")
        )
        self.assertEqual(d.name, "bedrock_anthropic_claude_drafter")

    def test_anthropic_mode_falls_back_when_no_api_key(self):
        from service.drafters.factory import build_drafter
        from service.drafters.stub_drafter import StubDrafter
        d = build_drafter(self._fake_settings(
            llm_drafter="anthropic", anthropic_api_key=None,
        ))
        self.assertIsInstance(d, StubDrafter)

    def test_auto_mode_falls_back_to_stub_when_no_key(self):
        from service.drafters.factory import build_drafter
        from service.drafters.stub_drafter import StubDrafter
        d = build_drafter(self._fake_settings(
            llm_drafter="auto", anthropic_api_key=None,
        ))
        self.assertIsInstance(d, StubDrafter)

    def test_explicit_stub_mode(self):
        from service.drafters.factory import build_drafter
        from service.drafters.stub_drafter import StubDrafter
        d = build_drafter(self._fake_settings(llm_drafter="stub"))
        self.assertIsInstance(d, StubDrafter)


if __name__ == "__main__":
    unittest.main(verbosity=2)
