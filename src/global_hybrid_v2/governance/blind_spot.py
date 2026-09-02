from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class HighImpactMutationKind(StrEnum):
    CANONICAL = "CANONICAL"
    OWNER_INTERFACE = "OWNER_INTERFACE"
    AUTHORITY = "AUTHORITY"
    PERSISTENCE = "PERSISTENCE"
    EXECUTION_ROUTE = "EXECUTION_ROUTE"
    EXTERNAL_SIDE_EFFECT = "EXTERNAL_SIDE_EFFECT"
    SALES_MEDIA_ARCHITECTURE = "SALES_MEDIA_ARCHITECTURE"


class BlindSpotStatus(StrEnum):
    PASS = "PASS"
    HOLD = "HOLD"


class BlindSpotFinding(BaseModel):
    failure_mode: str = Field(min_length=1)
    current_control: str = Field(min_length=1)
    residual_risk: str = Field(min_length=1)
    test_or_mitigation: str = Field(min_length=1)
    needs_architecture_change: bool = False


class BlindSpotScanRequest(BaseModel):
    mutation_kind: HighImpactMutationKind
    user_true_goal: str = Field(min_length=1)
    proposed_design: str = Field(min_length=1)
    external_content_in_scope: bool = False
    external_boundary_tested: bool = False
    shared_assumptions: list[str] = Field(default_factory=list)
    local_validation_passed: bool = False
    end_to_end_validation_passed: bool = False
    proxy_metrics_used: list[str] = Field(default_factory=list)
    business_outcome_observed: bool = False
    alternatives_considered: list[str] = Field(default_factory=list)
    failure_locus_observable: bool = True
    rollback_residue_checked: bool = False


class BlindSpotScanReceipt(BaseModel):
    mutation_kind: HighImpactMutationKind
    status: BlindSpotStatus
    top_blind_spots: list[BlindSpotFinding] = Field(max_length=5)


class PreIncidentBlindSpotScan:
    """A bounded precheck for high-impact candidates, not a risk-scoring system."""

    def scan(self, request: BlindSpotScanRequest) -> BlindSpotScanReceipt:
        findings: list[BlindSpotFinding] = []
        if request.external_content_in_scope and not request.external_boundary_tested:
            findings.append(
                BlindSpotFinding(
                    failure_mode="SOURCE_OR_CONTEXT_POISONING",
                    current_control="UNTRUSTED_EXTERNAL_EVIDENCE_BOUNDARY",
                    residual_risk="external instructions may reach a governed sink untested",
                    test_or_mitigation="run malicious-source negative tests before candidate admission",
                )
            )
        if request.local_validation_passed and not request.end_to_end_validation_passed:
            findings.append(
                BlindSpotFinding(
                    failure_mode="LOCAL_PASS_END_TO_END_FAIL",
                    current_control="VALIDATION_CONTRACT_AND_TASK_TRACE",
                    residual_risk="the actual consumer or enforcement route is unproven",
                    test_or_mitigation="run the smallest safe consumer-side end-to-end canary",
                )
            )
        if any(item.strip() for item in request.shared_assumptions):
            findings.append(
                BlindSpotFinding(
                    failure_mode="SHARED_ASSUMPTION_COMMON_MODE_FAILURE",
                    current_control="DISSIMILAR_VALIDATION",
                    residual_risk="multiple roles may agree from one unsupported evidence lineage",
                    test_or_mitigation="bind a materially independent falsification path",
                )
            )
        if request.proxy_metrics_used and not request.business_outcome_observed:
            findings.append(
                BlindSpotFinding(
                    failure_mode="METRIC_PROXY_MISTAKEN_FOR_BUSINESS_SUCCESS",
                    current_control="OUTCOME_ATTRIBUTION_CONTRACT",
                    residual_risk="local engagement metrics may mask weak qualified demand",
                    test_or_mitigation="hold causal promotion until downstream outcome linkage exists",
                )
            )
        if not any(item.strip() for item in request.alternatives_considered):
            findings.append(
                BlindSpotFinding(
                    failure_mode="SOLUTION_SPACE_PREMATURELY_NARROWED",
                    current_control="FIT_GAP_RISK_ALTERNATIVE_CHECK",
                    residual_risk="one plausible design may be treated as the only design",
                    test_or_mitigation="record at least one bounded alternative or exact rejection reason",
                )
            )
        if not request.failure_locus_observable:
            findings.append(
                BlindSpotFinding(
                    failure_mode="FAILURE_NOT_OBSERVABLE",
                    current_control="TASK_TRACE_AND_WITNESS",
                    residual_risk="a regression can occur without an attributable failure locus",
                    test_or_mitigation="add the minimum trace receipt before promotion",
                    needs_architecture_change=True,
                )
            )
        if not request.rollback_residue_checked:
            findings.append(
                BlindSpotFinding(
                    failure_mode="STALE_STATE_SURVIVES_ROLLBACK",
                    current_control="PROMOTION_AND_ROLLBACK_READBACK",
                    residual_risk="current pointers may roll back while derived state remains stale",
                    test_or_mitigation=(
                        "verify pointer, cache, snapshot, and consumer readback after rollback"
                    ),
                )
            )

        bounded = findings[:5]
        return BlindSpotScanReceipt(
            mutation_kind=request.mutation_kind,
            status=BlindSpotStatus.HOLD if bounded else BlindSpotStatus.PASS,
            top_blind_spots=bounded,
        )
