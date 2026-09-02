from __future__ import annotations

from global_hybrid_v2.contracts import TraceEvent, WitnessFinding
from global_hybrid_v2.governance.egress import (
    ASSUMPTION_USED_AS_EVIDENCE,
    CURRENT_CAPABILITY_CLAIM_WITHOUT_CURRENT_EVIDENCE,
    RESEARCH_GATE_BYPASS,
)


class ReadOnlyWitness:
    """Observer has no mutator/tool dependency by construction."""

    def __init__(self):
        self._claimed_fixed_defects: set[str] = set()

    def observe(self, event: TraceEvent) -> WitnessFinding | None:
        if event.stage == "effect_gate" and event.decision == "DENY":
            return WitnessFinding(
                task_id=event.task_id,
                severity="warning",
                code="EFFECT_DENIED",
                message="Side effect was rejected by the control plane.",
            )
        if event.stage == "response_egress":
            return self._observe_response_egress(event)
        return None

    def _observe_response_egress(self, event: TraceEvent) -> WitnessFinding | None:
        defect_family = event.metadata.get("defect_family")
        if isinstance(defect_family, str) and event.metadata.get("fix_claimed") is True:
            self._claimed_fixed_defects.add(defect_family)

        if (
            isinstance(defect_family, str)
            and event.metadata.get("user_reported_recurrence") is True
            and defect_family in self._claimed_fixed_defects
        ):
            return WitnessFinding(
                task_id=event.task_id,
                severity="error",
                code="RECURRENT_DEFECT",
                message=f"Previously fixed defect recurred: {defect_family}",
            )

        finding_codes = event.metadata.get("finding_codes", [])
        if not isinstance(finding_codes, list):
            return None
        messages = {
            ASSUMPTION_USED_AS_EVIDENCE: "Unsupported assumption was used as evidence.",
            CURRENT_CAPABILITY_CLAIM_WITHOUT_CURRENT_EVIDENCE: (
                "Current capability claim lacked current evidence."
            ),
            RESEARCH_GATE_BYPASS: "Required research admission was bypassed.",
        }
        for code in (
            ASSUMPTION_USED_AS_EVIDENCE,
            CURRENT_CAPABILITY_CLAIM_WITHOUT_CURRENT_EVIDENCE,
            RESEARCH_GATE_BYPASS,
        ):
            if code in finding_codes:
                return WitnessFinding(
                    task_id=event.task_id,
                    severity="error",
                    code=code,
                    message=messages[code],
                )
        return None
