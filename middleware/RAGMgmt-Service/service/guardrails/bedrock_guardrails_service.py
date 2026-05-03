"""Bedrock Guardrails — second-line semantic guardrails layered on top of
the regex policy. Excel Project A AWS row "Guardrails" target.

Bedrock Guardrails catches what the regex policy can't: paraphrased
testimonials ("a patient told us"), semantic cure-claim implications
("you'll never need surgery again"), denied topics defined by the
operator's guardrail config. The regex policy stays the load-bearing first
line — fast, free, gives clear `rule_id` + rationale per match — and
Bedrock runs after as a paraphrase / semantic-violation catcher.

Optional dep — install via `pip install '.[bedrock-drafter]'` (boto3 is
shared with the drafter + embedder; one extra installs all three). Auth
via the standard AWS chain.

Required pre-existing AWS setup:
  * A Bedrock guardrail configuration created in the console (denied
    topics, content filters, sensitive-info policy, contextual grounding).
  * IAM principal has `bedrock:ApplyGuardrail` on the guardrail ARN.

The service implements the same `IGuardrailsService` Protocol as the
regex GuardrailsService, so retrieval / generation / API layers don't
know which backend is in play.
"""

from __future__ import annotations

import logging
from typing import Protocol

from common.dtos import CheckGuardrailsReqDTO, CheckGuardrailsRespDTO
from common.return_codes import RC_OK
from common.tracing import traced

LOGGER = logging.getLogger(__name__)


class IGuardrailsService(Protocol):
    async def check_text(
        self, req: CheckGuardrailsReqDTO, resp: CheckGuardrailsRespDTO
    ) -> int: ...


class BedrockGuardrailsService:
    """Second-line guardrails via AWS Bedrock's `apply_guardrail` API.

    Returns violations in the SAME shape as the regex GuardrailsService —
    `respCtxData.violations[]` with `rule_id`, `category`, `severity`,
    `rationale`, `matched_text`, `char_start`, `char_end` — so the
    customer portal renders them through the existing UI without
    branching on backend.

    Char offsets are approximate: Bedrock returns matched substrings but
    not their exact positions in the input. We do a single pass through
    the original text to recover offsets when possible.
    """

    def __init__(
        self,
        guardrail_id: str,
        guardrail_version: str,
        region: str,
        source: str = "OUTPUT",
    ) -> None:
        if not guardrail_id:
            raise ValueError(
                "BedrockGuardrailsService requires a guardrail_id; set "
                "AWS_BEDROCK_GUARDRAIL_ID to the guardrail's identifier "
                "(e.g. 'abcd1234')."
            )
        # Lazy boto3 import — keeps the optional-dep gate at the call site.
        import boto3  # type: ignore[import-not-found]

        self._client = boto3.client("bedrock-runtime", region_name=region)
        self._guardrail_id = guardrail_id
        self._guardrail_version = guardrail_version or "DRAFT"
        self._source = source  # "OUTPUT" for draft scanning, "INPUT" for prompt scanning

    @traced("guardrails.bedrock.check_text")
    async def check_text(
        self, req: CheckGuardrailsReqDTO, resp: CheckGuardrailsRespDTO
    ) -> int:
        # Bedrock's apply_guardrail is synchronous; wrap in to_thread when this
        # surface gets concurrent traffic. For now the per-call latency is
        # additive to the existing /generate path and acceptable.
        import asyncio
        bedrock_resp = await asyncio.to_thread(
            self._client.apply_guardrail,
            guardrailIdentifier=self._guardrail_id,
            guardrailVersion=self._guardrail_version,
            source=self._source,
            content=[{"text": {"text": req.text}}],
        )

        violations = self._extract_violations(bedrock_resp, original_text=req.text)
        action = bedrock_resp.get("action", "NONE")
        passed = action == "NONE" and not violations
        max_sev = _max_severity(violations)

        ctx = resp.respCtxData
        ctx["policy_id"] = f"bedrock_guardrail:{self._guardrail_id}:{self._guardrail_version}"
        ctx["policy_description"] = (
            "AWS Bedrock managed guardrail — denied topics, content filters, "
            "sensitive-info policy, contextual grounding."
        )
        ctx["rule_count"] = -1  # not exposed by Bedrock
        ctx["violations"] = violations
        ctx["violation_count"] = len(violations)
        ctx["max_severity"] = max_sev
        ctx["passed"] = passed
        ctx["text_length"] = len(req.text)
        ctx["bedrock_action"] = action
        return RC_OK

    def _extract_violations(
        self, bedrock_resp: dict, original_text: str
    ) -> list[dict]:
        """Parse Bedrock's assessment block into our violation shape.

        Bedrock returns 5 policy categories under `assessments`:
          * topicPolicy        — denied-topic matches
          * contentPolicy      — content filters (HATE, INSULTS, etc.)
          * wordPolicy         — banned-words / managed-words matches
          * sensitiveInformationPolicy — PII matches
          * contextualGroundingPolicy  — grounding score per chunk

        We map each to a uniform violation row. Severity is derived from
        Bedrock's confidence/strength when present, else "high".
        """
        violations: list[dict] = []
        assessments = bedrock_resp.get("assessments") or []
        for assessment in assessments:
            for entry in assessment.get("topicPolicy", {}).get("topics", []) or []:
                if entry.get("action") == "BLOCKED":
                    violations.append(_make_violation(
                        rule_id=f"bedrock_topic:{entry.get('name', 'unknown')}",
                        category="denied_topic",
                        severity="high",
                        rationale=f"Bedrock denied-topic match: {entry.get('type', '')}",
                        matched_text=entry.get("name", ""),
                        original_text=original_text,
                    ))
            for entry in assessment.get("contentPolicy", {}).get("filters", []) or []:
                if entry.get("action") == "BLOCKED":
                    violations.append(_make_violation(
                        rule_id=f"bedrock_content:{entry.get('type', 'unknown')}",
                        category="content_filter",
                        severity=_strength_to_severity(entry.get("confidence")),
                        rationale=f"Bedrock content filter: {entry.get('type', '')}",
                        matched_text="",  # no surface text for content filters
                        original_text=original_text,
                    ))
            for entry in assessment.get("wordPolicy", {}).get("customWords", []) or []:
                if entry.get("action") == "BLOCKED":
                    violations.append(_make_violation(
                        rule_id=f"bedrock_word:custom",
                        category="banned_phrase",
                        severity="high",
                        rationale="Bedrock custom-word match",
                        matched_text=entry.get("match", ""),
                        original_text=original_text,
                    ))
            for entry in assessment.get("wordPolicy", {}).get("managedWordLists", []) or []:
                if entry.get("action") == "BLOCKED":
                    violations.append(_make_violation(
                        rule_id=f"bedrock_word:{entry.get('type', 'managed')}",
                        category="banned_phrase",
                        severity="high",
                        rationale=f"Bedrock managed-word list: {entry.get('type', '')}",
                        matched_text=entry.get("match", ""),
                        original_text=original_text,
                    ))
            for entry in (
                assessment.get("sensitiveInformationPolicy", {}).get("piiEntities", []) or []
            ):
                if entry.get("action") in ("BLOCKED", "ANONYMIZED"):
                    violations.append(_make_violation(
                        rule_id=f"bedrock_pii:{entry.get('type', 'unknown')}",
                        category="pii",
                        severity="critical",
                        rationale=f"Bedrock PII detector: {entry.get('type', '')}",
                        matched_text=entry.get("match", ""),
                        original_text=original_text,
                    ))
        return violations


def _make_violation(
    *,
    rule_id: str,
    category: str,
    severity: str,
    rationale: str,
    matched_text: str,
    original_text: str,
) -> dict:
    """Bedrock doesn't return char offsets. Approximate by searching the
    original text for the matched substring; if not found (content filters
    have no surface text), report 0/0."""
    if matched_text and matched_text in original_text:
        start = original_text.index(matched_text)
        end = start + len(matched_text)
    else:
        start = 0
        end = 0
    return {
        "rule_id": rule_id,
        "category": category,
        "severity": severity,
        "rationale": rationale,
        "pattern": "",
        "matched_text": matched_text,
        "char_start": start,
        "char_end": end,
    }


def _strength_to_severity(confidence: str | None) -> str:
    """Map Bedrock's confidence labels to our severity scale."""
    if confidence == "HIGH":
        return "critical"
    if confidence == "MEDIUM":
        return "high"
    if confidence == "LOW":
        return "medium"
    return "high"  # default if Bedrock omits confidence


def _max_severity(violations: list[dict]) -> str | None:
    if not violations:
        return None
    rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    return max((v["severity"] for v in violations), key=lambda s: rank.get(s, 0))
