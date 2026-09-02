from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from global_hybrid_v2.contracts import Owner
from global_hybrid_v2.domains.sales_media import (
    AttributionState,
    AudienceAssertionState,
    AudienceDataState,
    AudienceDimension,
    AudienceEvidence,
    AudienceEvidenceKind,
    AudienceStrategy,
    CampaignFunnel,
    CampaignOutcomeRecord,
    ContaminationFlag,
    EvidenceConfidence,
    HypothesisAlignment,
    MediaActivationGate,
    MediaActivationPlan,
    MediaCandidate,
    MediaCandidateComparison,
    MediaLearningCriteria,
    MediaLearningDecision,
    MediaLearningEvaluator,
    MediaPlanStatus,
    PaidAdEligibility,
    TargetBuyerHypothesis,
)
from global_hybrid_v2.governance.blind_spot import (
    BlindSpotScanRequest,
    BlindSpotStatus,
    HighImpactMutationKind,
    PreIncidentBlindSpotScan,
)
from global_hybrid_v2.governance.validation import (
    DissimilarValidationGate,
    EvidenceVerdict,
    FalsificationEvidence,
    FalsificationPath,
    ValidationClaim,
    ValidationStatus,
)
from global_hybrid_v2.observer.witness import ReadOnlyWitness

NOW = datetime(2026, 9, 3, 4, 0, tzinfo=UTC)


def _validation_evidence(
    evidence_id: str,
    *,
    path: FalsificationPath,
    verdict: EvidenceVerdict,
    lineage_id: str,
    owner: Owner | None = None,
) -> FalsificationEvidence:
    return FalsificationEvidence(
        evidence_id=evidence_id,
        path=path,
        verdict=verdict,
        reference=f"receipt:{evidence_id}",
        lineage_id=lineage_id,
        source_owner=owner,
    )


def test_same_summary_role_agreement_is_not_independent_validation():
    receipt = DissimilarValidationGate().evaluate(
        primary_owner=Owner.GLOBAL,
        primary_conclusion="candidate is safe",
        evidence=[
            _validation_evidence(
                "global-summary",
                path=FalsificationPath.OWNER_SELF_CERTIFICATION,
                verdict=EvidenceVerdict.SUPPORTS,
                lineage_id="same-summary",
                owner=Owner.GLOBAL,
            ),
            _validation_evidence(
                "witness-restatement",
                path=FalsificationPath.ROLE_RESTATEMENT,
                verdict=EvidenceVerdict.SUPPORTS,
                lineage_id="same-summary",
            ),
        ],
    )

    assert receipt.status is ValidationStatus.UNRESOLVED
    assert receipt.claim is ValidationClaim.INTERNALLY_CONSISTENT
    assert receipt.independent_evidence_ids == []


@pytest.mark.parametrize(
    "path",
    [FalsificationPath.RAW_TOOL_RECEIPT, FalsificationPath.CONSUMER_TRACE],
)
def test_independent_raw_or_consumer_evidence_can_contradict_primary(path):
    receipt = DissimilarValidationGate().evaluate(
        primary_owner=Owner.EXECUTION,
        primary_conclusion="execution succeeded",
        evidence=[
            _validation_evidence(
                "contradiction",
                path=path,
                verdict=EvidenceVerdict.CONTRADICTS,
                lineage_id="actual-route-readback",
            )
        ],
    )

    assert receipt.status is ValidationStatus.CONTRADICTED
    assert receipt.claim is ValidationClaim.PRIMARY_CONCLUSION_CONTRADICTED
    assert receipt.contradiction_ids == ["contradiction"]


def test_independent_contract_assertion_allows_independently_validated_claim():
    receipt = ReadOnlyWitness().assess_validation(
        primary_owner=Owner.LIBRARY_FACT,
        primary_conclusion="consumer projection preserves fact scope",
        evidence=[
            _validation_evidence(
                "contract-test",
                path=FalsificationPath.INDEPENDENT_CONTRACT_TEST,
                verdict=EvidenceVerdict.SUPPORTS,
                lineage_id="consumer-owned-test",
                owner=Owner.SALES_HUMAN,
            )
        ],
    )

    assert receipt.status is ValidationStatus.SUPPORTED
    assert receipt.claim is ValidationClaim.INDEPENDENTLY_VALIDATED


def _safe_scan(**updates: object) -> BlindSpotScanRequest:
    values: dict[str, object] = {
        "mutation_kind": HighImpactMutationKind.OWNER_INTERFACE,
        "user_true_goal": "preserve a reliable acquisition handoff",
        "proposed_design": "bounded consumer contract",
        "external_content_in_scope": False,
        "external_boundary_tested": True,
        "shared_assumptions": [],
        "local_validation_passed": True,
        "end_to_end_validation_passed": True,
        "proxy_metrics_used": [],
        "business_outcome_observed": True,
        "alternatives_considered": ["retain current contract"],
        "failure_locus_observable": True,
        "rollback_residue_checked": True,
    }
    values.update(updates)
    return BlindSpotScanRequest.model_validate(values)


def test_blind_spot_scan_detects_local_pass_end_to_end_fail():
    receipt = PreIncidentBlindSpotScan().scan(
        _safe_scan(end_to_end_validation_passed=False)
    )
    assert receipt.status is BlindSpotStatus.HOLD
    assert receipt.top_blind_spots[0].failure_mode == "LOCAL_PASS_END_TO_END_FAIL"


def test_blind_spot_scan_detects_shared_assumption_and_unobservable_failure():
    receipt = PreIncidentBlindSpotScan().scan(
        _safe_scan(
            shared_assumptions=["all roles consumed the same owner summary"],
            failure_locus_observable=False,
        )
    )
    modes = {item.failure_mode for item in receipt.top_blind_spots}
    assert "SHARED_ASSUMPTION_COMMON_MODE_FAILURE" in modes
    assert "FAILURE_NOT_OBSERVABLE" in modes
    assert next(
        item for item in receipt.top_blind_spots if item.failure_mode == "FAILURE_NOT_OBSERVABLE"
    ).needs_architecture_change


def test_blind_spot_scan_detects_stale_rollback_residue_and_bounds_output():
    receipt = PreIncidentBlindSpotScan().scan(
        _safe_scan(
            external_content_in_scope=True,
            external_boundary_tested=False,
            shared_assumptions=["shared assumption"],
            end_to_end_validation_passed=False,
            proxy_metrics_used=["CTR"],
            business_outcome_observed=False,
            alternatives_considered=[],
            failure_locus_observable=False,
            rollback_residue_checked=False,
        )
    )
    assert receipt.status is BlindSpotStatus.HOLD
    assert len(receipt.top_blind_spots) == 5

    rollback = PreIncidentBlindSpotScan().scan(
        _safe_scan(rollback_residue_checked=False)
    )
    assert rollback.top_blind_spots[0].failure_mode == "STALE_STATE_SURVIVES_ROLLBACK"


def test_blind_spot_scan_passes_when_all_bounded_controls_are_proven():
    receipt = ReadOnlyWitness().scan_blind_spots(_safe_scan())
    assert receipt.status is BlindSpotStatus.PASS
    assert receipt.top_blind_spots == []


def _evidence(
    evidence_id: str,
    vehicle_id: str,
    *,
    dimensions: set[AudienceDimension],
    kind: AudienceEvidenceKind = AudienceEvidenceKind.VEHICLE_MODEL,
    supported: set[AudienceStrategy] | None = None,
    stale: bool = False,
) -> AudienceEvidence:
    observed_at = NOW - timedelta(days=30)
    valid_until = NOW - timedelta(days=1) if stale else NOW + timedelta(days=30)
    return AudienceEvidence(
        evidence_id=evidence_id,
        vehicle_id=vehicle_id,
        kind=kind,
        dimensions=dimensions,
        observation=f"synthetic bounded observation for {vehicle_id}",
        observed_at=observed_at,
        valid_until=valid_until,
        provenance=[f"fixture:{evidence_id}"],
        transfer_limit="synthetic contract fixture; no demographic generalization",
        sample_size=50,
        supported_strategies=supported or set(),
    )


def _plan(
    vehicle_id: str,
    *,
    selected: AudienceStrategy,
    evidence: list[AudienceEvidence],
    target_hypothesis: str,
    **updates: object,
) -> MediaActivationPlan:
    values: dict[str, object] = {
        "campaign_id": f"campaign-{vehicle_id}-{selected.value}",
        "experiment_id": f"experiment-{vehicle_id}",
        "vehicle_id": vehicle_id,
        "campaign_objective": "qualified conversations",
        "paid_ad_eligibility": PaidAdEligibility.PASS,
        "target_buyer_hypothesis": TargetBuyerHypothesis(
            hypothesis=target_hypothesis,
            evidence_ids=[
                item.evidence_id
                for item in evidence
                if item.kind is not AudienceEvidenceKind.PLATFORM_CAPABILITY
            ],
            confidence=EvidenceConfidence.LOW,
            transfer_limit="campaign-local hypothesis only",
        ),
        "selected_strategy": selected,
        "strategy_candidates": [selected],
        "audience_breadth": "bounded test cell",
        "positioning_id": f"positioning-{vehicle_id}",
        "evidence_basis": [item.evidence_id for item in evidence],
        "evidence": evidence,
        "uncertainties": ["real campaign outcome pending"],
        "test_stop_condition": "stop at the pre-declared spend or safety boundary",
    }
    values.update(updates)
    return MediaActivationPlan.model_validate(values)


def _platform(vehicle_id: str, *strategies: AudienceStrategy) -> AudienceEvidence:
    return _evidence(
        f"platform-{vehicle_id}",
        vehicle_id,
        dimensions={AudienceDimension.PLATFORM_CAPABILITY},
        kind=AudienceEvidenceKind.PLATFORM_CAPABILITY,
        supported=set(strategies),
    )


def test_same_sienta_like_evidence_allows_distinct_testable_media_hypotheses():
    vehicle_id = "sienta-like-fixture"
    use_case = _evidence(
        "sienta-use-case",
        vehicle_id,
        dimensions={AudienceDimension.USE_CASE, AudienceDimension.GEO},
        kind=AudienceEvidenceKind.USE_CASE,
    )
    platform = _platform(vehicle_id, AudienceStrategy.BROAD, AudienceStrategy.GUIDED_BROAD)
    broad = _plan(
        vehicle_id,
        selected=AudienceStrategy.BROAD,
        evidence=[use_case, platform],
        target_hypothesis="broad use-case discovery hypothesis",
    )
    guided = _plan(
        vehicle_id,
        selected=AudienceStrategy.GUIDED_BROAD,
        evidence=[use_case, platform],
        target_hypothesis="guided use-case signal hypothesis",
    )

    assert MediaActivationGate().admit(broad, now=NOW).status is MediaPlanStatus.PASS
    assert MediaActivationGate().admit(guided, now=NOW).status is MediaPlanStatus.PASS
    assert broad.target_buyer_hypothesis.hypothesis != guided.target_buyer_hypothesis.hypothesis


def test_altis_like_supply_and_a250_like_scarcity_support_different_geo_tests():
    commuter_id = "altis-like-fixture"
    commuter_evidence = _evidence(
        "commuter-supply",
        commuter_id,
        dimensions={AudienceDimension.SUPPLY_DENSITY, AudienceDimension.GEO},
    )
    commuter = _plan(
        commuter_id,
        selected=AudienceStrategy.MANUAL_NARROW,
        evidence=[commuter_evidence, _platform(commuter_id, AudienceStrategy.MANUAL_NARROW)],
        target_hypothesis="local acquisition candidate under high substitute supply",
        geo_hypothesis="bounded local travel test",
    )

    niche_id = "a250-like-fixture"
    niche_evidence = _evidence(
        "niche-scarcity",
        niche_id,
        dimensions={AudienceDimension.SCARCITY, AudienceDimension.GEO},
    )
    niche = _plan(
        niche_id,
        selected=AudienceStrategy.GUIDED_BROAD,
        evidence=[niche_evidence, _platform(niche_id, AudienceStrategy.GUIDED_BROAD)],
        target_hypothesis="scarcity-backed wider acquisition candidate",
        geo_hypothesis="expanded travel-distance test",
        geo_expansion=True,
    )

    assert MediaActivationGate().admit(commuter, now=NOW).status is MediaPlanStatus.PASS
    assert MediaActivationGate().admit(niche, now=NOW).status is MediaPlanStatus.PASS


def test_demographic_without_matching_evidence_stays_audience_assumption():
    vehicle_id = "demographic-unknown-fixture"
    plan = _plan(
        vehicle_id,
        selected=AudienceStrategy.BROAD,
        evidence=[_platform(vehicle_id, AudienceStrategy.BROAD)],
        target_hypothesis="non-demographic discovery hypothesis",
        age_hypothesis="synthetic age-cell candidate without known answer",
    )

    admission = MediaActivationGate().admit(plan, now=NOW)

    assert admission.status is MediaPlanStatus.PASS
    assert admission.age_assertion_state is AudienceAssertionState.AUDIENCE_ASSUMPTION


def test_retargeting_requires_available_state_and_current_platform_evidence():
    vehicle_id = "retargeting-fixture"
    evidence = [_platform(vehicle_id, AudienceStrategy.RETARGETING)]
    unavailable = _plan(
        vehicle_id,
        selected=AudienceStrategy.RETARGETING,
        evidence=evidence,
        target_hypothesis="prior-engagement retargeting candidate",
    )
    active = unavailable.model_copy(
        update={
            "retargeting_state": AudienceDataState.ACTIVE,
            "audience_data_use_authorized": True,
        }
    )

    assert "RETARGETING_AUDIENCE_UNAVAILABLE" in MediaActivationGate().admit(
        unavailable, now=NOW
    ).blockers
    assert MediaActivationGate().admit(active, now=NOW).status is MediaPlanStatus.PASS


def test_custom_or_lookalike_audience_requires_authorized_data_use():
    vehicle_id = "first-party-fixture"
    plan = _plan(
        vehicle_id,
        selected=AudienceStrategy.CUSTOM,
        evidence=[_platform(vehicle_id, AudienceStrategy.CUSTOM)],
        target_hypothesis="authorized first-party audience candidate",
        custom_audience_state=AudienceDataState.CANDIDATE,
    )

    admission = MediaActivationGate().admit(plan, now=NOW)

    assert admission.status is MediaPlanStatus.HOLD
    assert "AUDIENCE_DATA_USE_NOT_AUTHORIZED" in admission.blockers


def test_broad_vs_narrow_comparison_rejects_creative_contamination():
    common = {
        "vehicle_id": "comparison-fixture",
        "creative_variant_id": "creative-1",
        "copy_variant_id": "copy-1",
        "positioning_id": "positioning-1",
        "budget_amount": Decimal("1000"),
    }
    broad = MediaCandidate(
        audience_cell_id="cell-broad",
        strategy=AudienceStrategy.BROAD,
        **common,
    )
    narrow = MediaCandidate(
        audience_cell_id="cell-narrow",
        strategy=AudienceStrategy.MANUAL_NARROW,
        **common,
    )
    comparison = MediaCandidateComparison(
        experiment_id="experiment-comparison",
        candidates=[broad, narrow],
    )
    assert len(comparison.candidates) == 2

    with pytest.raises(ValidationError, match="contamination"):
        MediaCandidateComparison(
            experiment_id="experiment-contaminated",
            candidates=[
                broad,
                narrow.model_copy(update={"creative_variant_id": "creative-2"}),
            ],
        )


def _outcome(**updates: object) -> CampaignOutcomeRecord:
    values: dict[str, object] = {
        "campaign_id": "campaign-outcome",
        "experiment_id": "experiment-outcome",
        "audience_cell_id": "cell-1",
        "creative_variant_id": "creative-1",
        "copy_variant_id": "copy-1",
        "vehicle_id": "vehicle-outcome",
        "period_start": NOW - timedelta(days=7),
        "period_end": NOW - timedelta(days=1),
        "stale_after": NOW + timedelta(days=7),
        "spend": Decimal("1200"),
        "funnel": CampaignFunnel(
            impressions=1000,
            engaged=200,
            clicks=30,
            message_starts=50,
            qualified_conversations=20,
            appointments=10,
            show_ups=5,
            sold=2,
        ),
        "attribution_state": AttributionState.ASSOCIATION_ONLY,
    }
    values.update(updates)
    return CampaignOutcomeRecord.model_validate(values)


CRITERIA = MediaLearningCriteria(
    minimum_impressions=500,
    high_ctr_threshold=0.05,
    minimum_qualified_message_rate=0.1,
)


def test_high_ctr_with_low_qualified_outcome_triggers_calibration():
    record = _outcome(
        funnel=CampaignFunnel(
            impressions=1000,
            engaged=200,
            clicks=100,
            message_starts=50,
            qualified_conversations=1,
            appointments=0,
            show_ups=0,
            sold=0,
        )
    )
    receipt = MediaLearningEvaluator().evaluate(record, criteria=CRITERIA, now=NOW)
    assert receipt.decision is MediaLearningDecision.CALIBRATE
    assert receipt.reason_codes == ["HIGH_CTR_LOW_QUALIFIED_OUTCOME"]


def test_age_hypothesis_can_be_contradicted_by_sold_cohort_without_hardcoded_age():
    record = _outcome(hypothesis_alignment=HypothesisAlignment.CONTRADICTS)
    receipt = MediaLearningEvaluator().evaluate(record, criteria=CRITERIA, now=NOW)
    assert receipt.decision is MediaLearningDecision.CALIBRATE
    assert "AUDIENCE_HYPOTHESIS_CONTRADICTED_BY_SOLD_COHORT" in receipt.reason_codes


@pytest.mark.parametrize(
    ("updates", "reason"),
    [
        (
            {
                "stale_after": NOW - timedelta(hours=1),
                "period_end": NOW - timedelta(days=1),
            },
            "STALE_CAMPAIGN_EVIDENCE",
        ),
        (
            {
                "funnel": CampaignFunnel(
                    impressions=100,
                    engaged=20,
                    clicks=3,
                    message_starts=5,
                    qualified_conversations=2,
                    appointments=1,
                    show_ups=0,
                    sold=0,
                )
            },
            "INSUFFICIENT_SAMPLE",
        ),
        ({"contamination_flags": {ContaminationFlag.AUDIENCE_OVERLAP}}, "AUDIENCE_OVERLAP"),
        ({"contamination_flags": {ContaminationFlag.CREATIVE_CHANGED}}, "EXPERIMENT_CONTAMINATED"),
    ],
)
def test_media_learning_holds_stale_small_or_contaminated_evidence(updates, reason):
    receipt = MediaLearningEvaluator().evaluate(
        _outcome(**updates),
        criteria=CRITERIA,
        now=NOW,
    )
    assert receipt.decision is MediaLearningDecision.HOLD
    assert reason in receipt.reason_codes


def test_causal_credit_requires_clean_controlled_outcome():
    record = _outcome(attribution_state=AttributionState.CONTROLLED)
    receipt = MediaLearningEvaluator().evaluate(record, criteria=CRITERIA, now=NOW)
    assert receipt.decision is MediaLearningDecision.OBSERVE
    assert receipt.causal_credit_allowed is True


def test_stale_platform_capability_holds_media_activation():
    vehicle_id = "stale-platform-fixture"
    plan = _plan(
        vehicle_id,
        selected=AudienceStrategy.BROAD,
        evidence=[
            _evidence(
                "stale-platform",
                vehicle_id,
                dimensions={AudienceDimension.PLATFORM_CAPABILITY},
                kind=AudienceEvidenceKind.PLATFORM_CAPABILITY,
                supported={AudienceStrategy.BROAD},
                stale=True,
            )
        ],
        target_hypothesis="platform capability must be current",
    )
    admission = MediaActivationGate().admit(plan, now=NOW)
    assert admission.status is MediaPlanStatus.HOLD
    assert "STALE_CAMPAIGN_EVIDENCE" in admission.blockers
    assert "CURRENT_PLATFORM_CAPABILITY_UNVERIFIED" in admission.blockers


def test_media_plan_cannot_change_owner_or_bypass_paid_ad_eligibility():
    vehicle_id = "owner-boundary-fixture"
    evidence = [_platform(vehicle_id, AudienceStrategy.BROAD)]
    with pytest.raises(ValidationError, match="owned by SALES_HUMAN"):
        _plan(
            vehicle_id,
            selected=AudienceStrategy.BROAD,
            evidence=evidence,
            target_hypothesis="bounded hypothesis",
            owner=Owner.GLOBAL,
        )
    with pytest.raises(ValidationError, match="PAID_AD_ELIGIBILITY=PASS"):
        _plan(
            vehicle_id,
            selected=AudienceStrategy.BROAD,
            evidence=evidence,
            target_hypothesis="bounded hypothesis",
            paid_ad_eligibility=PaidAdEligibility.HOLD,
        )


def test_library_qualifies_audience_evidence_but_cannot_own_media_decision():
    with pytest.raises(ValidationError, match="qualified by LIBRARY_FACT"):
        AudienceEvidence(
            provider_owner=Owner.SALES_HUMAN,
            evidence_id="unqualified-audience",
            vehicle_id="owner-separation-fixture",
            kind=AudienceEvidenceKind.VEHICLE_MODEL,
            dimensions={AudienceDimension.USE_CASE},
            observation="unqualified audience claim",
            observed_at=NOW - timedelta(days=1),
            valid_until=NOW + timedelta(days=1),
            provenance=["fixture:unqualified"],
            transfer_limit="not admitted",
        )

    with pytest.raises(ValidationError, match="owned by SALES_HUMAN"):
        _plan(
            "owner-separation-fixture",
            selected=AudienceStrategy.BROAD,
            evidence=[
                _platform("owner-separation-fixture", AudienceStrategy.BROAD)
            ],
            target_hypothesis="Library cannot own this decision",
            owner=Owner.LIBRARY_FACT,
        )
