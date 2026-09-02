from __future__ import annotations

from global_hybrid_v2.contracts import Owner, TraceEvent, WitnessFinding
from global_hybrid_v2.governance.blind_spot import (
    BlindSpotScanReceipt,
    BlindSpotScanRequest,
    PreIncidentBlindSpotScan,
)
from global_hybrid_v2.governance.egress import (
    ASSUMPTION_USED_AS_EVIDENCE,
    CURRENT_CAPABILITY_CLAIM_WITHOUT_CURRENT_EVIDENCE,
    NEGATIVE_RETRIEVAL_CLAIM_WITHOUT_VERIFIED_ABSENCE,
    RESEARCH_GATE_BYPASS,
    RETRIEVAL_FALSE_NEGATIVE,
)
from global_hybrid_v2.governance.validation import (
    DissimilarValidationGate,
    FalsificationEvidence,
    ValidationReceipt,
)


class ReadOnlyWitness:
    """Observer has no mutator/tool dependency by construction."""

    def __init__(self):
        self._claimed_fixed_defects: set[str] = set()
        self._validation = DissimilarValidationGate()
        self._blind_spot_scan = PreIncidentBlindSpotScan()

    def assess_validation(
        self,
        *,
        primary_owner: Owner,
        primary_conclusion: str,
        evidence: list[FalsificationEvidence],
    ) -> ValidationReceipt:
        return self._validation.evaluate(
            primary_owner=primary_owner,
            primary_conclusion=primary_conclusion,
            evidence=evidence,
        )

    def scan_blind_spots(self, request: BlindSpotScanRequest) -> BlindSpotScanReceipt:
        return self._blind_spot_scan.scan(request)

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
        if event.stage == "firewall":
            receipts = event.metadata.get("admission_receipts", [])
            if isinstance(receipts, list) and any(
                isinstance(item, dict)
                and item.get("directive_detected") is True
                and item.get("directive_quarantined") is not True
                for item in receipts
            ):
                return WitnessFinding(
                    task_id=event.task_id,
                    severity="error",
                    code="EXTERNAL_EVIDENCE_CONTEXT_ISOLATION_FAIL",
                    message="Detected external directive was not quarantined.",
                )
        if event.stage == "fitness" and event.decision == "FAIL":
            return WitnessFinding(
                task_id=event.task_id,
                severity="error",
                code="CONSUMPTION_FITNESS_FAIL",
                message="Runtime consumption fitness reported a failed invariant.",
            )
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
            NEGATIVE_RETRIEVAL_CLAIM_WITHOUT_VERIFIED_ABSENCE: (
                "Prior-context absence was claimed without verified absence."
            ),
            RETRIEVAL_FALSE_NEGATIVE: (
                "Matching prior content was found after an earlier negative retrieval claim."
            ),
        }
        for code in (
            ASSUMPTION_USED_AS_EVIDENCE,
            CURRENT_CAPABILITY_CLAIM_WITHOUT_CURRENT_EVIDENCE,
            RESEARCH_GATE_BYPASS,
            NEGATIVE_RETRIEVAL_CLAIM_WITHOUT_VERIFIED_ABSENCE,
            RETRIEVAL_FALSE_NEGATIVE,
        ):
            if code in finding_codes:
                return WitnessFinding(
                    task_id=event.task_id,
                    severity="error",
                    code=code,
                    message=messages[code],
                )
        return None
