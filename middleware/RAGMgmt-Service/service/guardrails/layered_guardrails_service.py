"""Layered guardrails — runs multiple IGuardrailsService implementations and
merges their violations.

Use case: regex first (fast, free, gives clear `rule_id` + rationale), then
Bedrock (semantic, catches paraphrased violations the regex misses). Both
report into a single CheckGuardrailsRespDTO so the downstream UI / API
shape is identical.

Optimization knob: `short_circuit_on_critical=True` skips later layers
when an earlier layer already flagged a critical violation. The downstream
draft is going back to the LLM regardless — paying for Bedrock on top of
that just adds cost.
"""

from __future__ import annotations

from common.dtos import CheckGuardrailsReqDTO, CheckGuardrailsRespDTO
from common.return_codes import RC_OK
from common.tracing import traced

from service.guardrails.guardrails_service import IGuardrailsService, SEVERITY_RANK


class LayeredGuardrailsService:
    name = "layered"

    def __init__(
        self,
        layers: list[IGuardrailsService],
        layer_names: list[str],
        short_circuit_on_critical: bool = True,
    ) -> None:
        if len(layers) != len(layer_names):
            raise ValueError(
                f"layers ({len(layers)}) and layer_names ({len(layer_names)}) "
                "must be the same length"
            )
        if not layers:
            raise ValueError("LayeredGuardrailsService requires at least one layer")
        self._layers = layers
        self._layer_names = layer_names
        self._short_circuit = short_circuit_on_critical

    @traced("guardrails.layered.check_text")
    async def check_text(
        self, req: CheckGuardrailsReqDTO, resp: CheckGuardrailsRespDTO
    ) -> int:
        all_violations: list[dict] = []
        layer_summaries: list[dict] = []
        layer_short_circuited = False
        composite_policy_id = "layered:" + ",".join(self._layer_names)

        for layer, name in zip(self._layers, self._layer_names):
            if layer_short_circuited:
                layer_summaries.append({"name": name, "status": "skipped_short_circuit"})
                continue

            sub_resp = CheckGuardrailsRespDTO()
            rc = await layer.check_text(req, sub_resp)
            if rc != RC_OK:
                layer_summaries.append({"name": name, "status": "error", "rc": rc})
                continue

            sub_ctx = sub_resp.respCtxData
            sub_violations = sub_ctx.get("violations") or []
            # Tag each violation with its source layer so the UI can group / filter.
            for v in sub_violations:
                v_tagged = dict(v)
                v_tagged["source_layer"] = name
                all_violations.append(v_tagged)

            layer_summaries.append({
                "name": name,
                "status": "ok",
                "policy_id": sub_ctx.get("policy_id"),
                "rule_count": sub_ctx.get("rule_count"),
                "violation_count": sub_ctx.get("violation_count"),
                "max_severity": sub_ctx.get("max_severity"),
                "passed": sub_ctx.get("passed"),
            })

            if self._short_circuit and sub_ctx.get("max_severity") == "critical":
                layer_short_circuited = True

        max_sev = _max_severity(all_violations)
        ctx = resp.respCtxData
        ctx["policy_id"] = composite_policy_id
        ctx["policy_description"] = (
            f"Layered guardrails: {' → '.join(self._layer_names)}"
            + (" (short-circuit on critical)" if self._short_circuit else "")
        )
        # rule_count is the SUM of layer rule_counts where reported; -1 markers
        # (Bedrock) are dropped since they're not comparable.
        rule_count = sum(
            (s.get("rule_count") or 0)
            for s in layer_summaries
            if isinstance(s.get("rule_count"), int) and s.get("rule_count", 0) >= 0
        )
        ctx["rule_count"] = rule_count
        ctx["violations"] = all_violations
        ctx["violation_count"] = len(all_violations)
        ctx["max_severity"] = max_sev
        ctx["passed"] = len(all_violations) == 0
        ctx["text_length"] = len(req.text)
        ctx["layers"] = layer_summaries
        return RC_OK


def _max_severity(violations: list[dict]) -> str | None:
    if not violations:
        return None
    return max(
        (v.get("severity") for v in violations if v.get("severity")),
        key=lambda s: SEVERITY_RANK.get(s, 0),
        default=None,
    )
