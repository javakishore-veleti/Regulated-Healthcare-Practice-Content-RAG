"""Cloud presets — Excel Project A Task 13: `--cloud aws|local` swap.

The factories already swap individual components per env var. This module
groups them into named presets so an operator running smoke / eval / a CLI
flow doesn't have to remember 5 separate variables.

Each preset is a dict of `{ENV_VAR: value}` overrides applied to
`os.environ` before settings are read. Setting an overridden var in the
shell still wins — the preset only fills in unset variables (env wins).

Two presets ship today:

  * `local`  — RAGMgmt's local-dev posture. Stub embedder, token-overlap
              reranker, regex guardrails, postgres retrieval, auto drafter
              (Anthropic when key set, else stub). Zero AWS deps.
  * `aws`    — Excel Project A AWS architecture row alignment. Bedrock
              drafter, Bedrock embedder, OpenSearch Serverless retrieval,
              layered (regex+Bedrock) guardrails, OTel ADOT export.
              Requires `[bedrock-drafter]`, `[opensearch]`, `[langfuse]`
              extras + the AWS_* env vars set.

Adding `azure` / `gcp` presets is symmetric — they'd point the embedder /
drafter / retrieval / guardrails factories at their respective managed
services. Excel Tasks 2 + 8 cover those cloud mirrors; deferred per the
"AWS first" directive.
"""

from __future__ import annotations

import logging
import os

LOGGER = logging.getLogger(__name__)


_LOCAL = {
    "LLM_DRAFTER": "auto",
    "RAG_EMBEDDER_BACKEND": "stub",
    "RAG_RERANKER_BACKEND": "token_overlap",
    "RAG_RETRIEVAL_BACKEND": "postgres",
    "RAG_GUARDRAILS_BACKEND": "regex",
}

_AWS = {
    "LLM_DRAFTER": "bedrock",
    "RAG_EMBEDDER_BACKEND": "aws_bedrock",
    "RAG_RERANKER_BACKEND": "cross_encoder",
    "RAG_RETRIEVAL_BACKEND": "aws_opensearch_serverless",
    "RAG_GUARDRAILS_BACKEND": "layered",
}


_PRESETS: dict[str, dict[str, str]] = {
    "local": _LOCAL,
    "aws": _AWS,
}


AVAILABLE_PRESETS: tuple[str, ...] = tuple(_PRESETS.keys())


def apply_preset(name: str) -> dict[str, str]:
    """Apply a named cloud preset to os.environ. Existing vars in the env
    are NOT overwritten — operators can still override individual values
    by exporting them before launch.

    Returns the dict of variables actually applied (i.e. the keys that
    were unset and got filled in by the preset)."""
    if name not in _PRESETS:
        raise ValueError(
            f"Unknown cloud preset {name!r}. Available: {sorted(AVAILABLE_PRESETS)}"
        )
    preset = _PRESETS[name]
    applied: dict[str, str] = {}
    for k, v in preset.items():
        if not os.environ.get(k):
            os.environ[k] = v
            applied[k] = v
    LOGGER.info(
        "Applied cloud preset %r — set %d env var(s); %d already set in env",
        name, len(applied), len(preset) - len(applied),
    )
    return applied


def describe_preset(name: str) -> dict[str, str]:
    """Return the preset's full var map without mutating os.environ."""
    if name not in _PRESETS:
        raise ValueError(
            f"Unknown cloud preset {name!r}. Available: {sorted(AVAILABLE_PRESETS)}"
        )
    return dict(_PRESETS[name])
