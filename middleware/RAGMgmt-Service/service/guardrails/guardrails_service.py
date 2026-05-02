import re
from pathlib import Path
from typing import Protocol

import yaml

from common.dtos import CheckGuardrailsReqDTO, CheckGuardrailsRespDTO
from common.return_codes import RC_OK
from common.tracing import traced

SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}


class IGuardrailsService(Protocol):
    async def check_text(
        self, req: CheckGuardrailsReqDTO, resp: CheckGuardrailsRespDTO
    ) -> int: ...


class GuardrailsService:
    """Output guardrails per the Project A 'Output guardrails' pattern from the Excel.

    Loads a YAML policy of regex-based banned-phrase rules and scans candidate text
    for violations. Each violation surfaces rule id, severity, rationale, the
    matched substring, and char offsets so the customer portal can highlight in-line.

    The Excel architecture eventually layers on Bedrock Guardrails (denied topics,
    PII filter); this regex policy is the always-on first line of defense and runs
    locally with no external dependencies.
    """

    def __init__(self, policy_path: Path) -> None:
        self._policy_path = policy_path
        self._policy: dict | None = None

    @traced("guardrails.check_text")
    async def check_text(
        self, req: CheckGuardrailsReqDTO, resp: CheckGuardrailsRespDTO
    ) -> int:
        policy = self._ensure_policy()

        violations: list[dict] = []
        for rule in policy["rules"]:
            for match in rule["compiled"].finditer(req.text):
                violations.append(
                    {
                        "rule_id": rule["id"],
                        "category": rule["category"],
                        "severity": rule["severity"],
                        "rationale": rule["rationale"],
                        "pattern": rule["pattern"],
                        "matched_text": match.group(0),
                        "char_start": match.start(),
                        "char_end": match.end(),
                    }
                )

        max_sev = None
        if violations:
            max_sev = max(
                (v["severity"] for v in violations),
                key=lambda s: SEVERITY_RANK.get(s, 0),
            )

        ctx = resp.respCtxData
        ctx["policy_id"] = policy["policy_id"]
        ctx["policy_description"] = policy["description"]
        ctx["rule_count"] = len(policy["rules"])
        ctx["violations"] = violations
        ctx["violation_count"] = len(violations)
        ctx["max_severity"] = max_sev
        ctx["passed"] = len(violations) == 0
        ctx["text_length"] = len(req.text)
        return RC_OK

    def _ensure_policy(self) -> dict:
        if self._policy is not None:
            return self._policy

        with self._policy_path.open("r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)

        compiled_rules = []
        for r in raw.get("rules", []):
            compiled_rules.append(
                {
                    "id": r["id"],
                    "pattern": r["pattern"],
                    "compiled": re.compile(r["pattern"], re.IGNORECASE),
                    "category": r["category"],
                    "severity": r["severity"],
                    "rationale": r["rationale"],
                }
            )

        self._policy = {
            "policy_id": raw["policy_id"],
            "description": raw["description"],
            "rules": compiled_rules,
        }
        return self._policy
