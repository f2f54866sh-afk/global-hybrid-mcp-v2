from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from itertools import pairwise

from pydantic import BaseModel, Field, model_validator

from global_hybrid_v2.contracts import Owner


class PaidAdEligibility(StrEnum):
    PASS = "PASS"
    HOLD = "HOLD"
    NO_GO = "NO_GO"


class AudienceStrategy(StrEnum):
    BROAD = "BROAD"
    GUIDED_BROAD = "GUIDED_BROAD"
    MANUAL_NARROW = "MANUAL_NARROW"
    RETARGETING = "RETARGETING"
    CUSTOM = "CUSTOM"
    LOOKALIKE = "LOOKALIKE"


class AudienceDimension(StrEnum):
    AGE = "AGE"
    GEO = "GEO"
    USE_CASE = "USE_CASE"
    PRICE_BAND = "PRICE_BAND"
    SCARCITY = "SCARCITY"
    SUPPLY_DENSITY = "SUPPLY_DENSITY"
    PLATFORM_CAPABILITY = "PLATFORM_CAPABILITY"
    CAMPAIGN_OUTCOME = "CAMPAIGN_OUTCOME"
    FIRST_PARTY = "FIRST_PARTY"


class AudienceEvidenceKind(StrEnum):
    VEHICLE_MODEL = "VEHICLE_MODEL"
    REGIONAL_DEMAND = "REGIONAL_DEMAND"
    PRICE_BAND = "PRICE_BAND"
    USE_CASE = "USE_CASE"
    COMPETITOR_SUBSTITUTE = "COMPETITOR_SUBSTITUTE"
    PLATFORM_CAPABILITY = "PLATFORM_CAPABILITY"
    CAMPAIGN_STATISTICS = "CAMPAIGN_STATISTICS"
    INQUIRY_GEOGRAPHY = "INQUIRY_GEOGRAPHY"
    CUSTOMER_COHORT = "CUSTOMER_COHORT"
    FUNNEL_OUTCOME = "FUNNEL_OUTCOME"
    FIRST_PARTY_AUDIENCE = "FIRST_PARTY_AUDIENCE"


class EvidenceConfidence(StrEnum):
    UNVERIFIED = "UNVERIFIED"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class AudienceAssertionState(StrEnum):
    AUDIENCE_ASSUMPTION = "AUDIENCE_ASSUMPTION"
    EVIDENCE_BACKED_HYPOTHESIS = "EVIDENCE_BACKED_HYPOTHESIS"


class AudienceDataState(StrEnum):
    UNAVAILABLE = "UNAVAILABLE"
    NOT_USED = "NOT_USED"
    CANDIDATE = "CANDIDATE"
    ACTIVE = "ACTIVE"


class MediaPlanStatus(StrEnum):
    PASS = "PASS"
    HOLD = "HOLD"


class AttributionState(StrEnum):
    CONTROLLED = "CONTROLLED"
    ASSOCIATION_ONLY = "ASSOCIATION_ONLY"
    UNRESOLVED = "UNRESOLVED"


class HypothesisAlignment(StrEnum):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    UNKNOWN = "UNKNOWN"


class ContaminationFlag(StrEnum):
    AUDIENCE_OVERLAP = "AUDIENCE_OVERLAP"
    CREATIVE_CHANGED = "CREATIVE_CHANGED"
    COPY_CHANGED = "COPY_CHANGED"
    BUDGET_CHANGED = "BUDGET_CHANGED"
    VEHICLE_CHANGED = "VEHICLE_CHANGED"
    UNKNOWN = "UNKNOWN"


class MediaLearningDecision(StrEnum):
    OBSERVE = "OBSERVE"
    CALIBRATE = "CALIBRATE"
    HOLD = "HOLD"


class AudienceEvidence(BaseModel):
    provider_owner: Owner = Owner.LIBRARY_FACT
    evidence_id: str = Field(min_length=1)
    vehicle_id: str = Field(min_length=1)
    kind: AudienceEvidenceKind
    dimensions: set[AudienceDimension] = Field(default_factory=set)
    observation: str = Field(min_length=1)
    observed_at: datetime
    valid_until: datetime
    provenance: list[str] = Field(min_length=1)
    transfer_limit: str = Field(min_length=1)
    sample_size: int | None = Field(default=None, ge=0)
    supported_strategies: set[AudienceStrategy] = Field(default_factory=set)

    @model_validator(mode="after")
    def validate_evidence_window(self) -> AudienceEvidence:
        if self.provider_owner is not Owner.LIBRARY_FACT:
            raise ValueError("audience evidence must be qualified by LIBRARY_FACT")
        if self.observed_at.tzinfo is None or self.valid_until.tzinfo is None:
            raise ValueError("audience evidence timestamps must be timezone-aware")
        if self.valid_until <= self.observed_at:
            raise ValueError("audience evidence validity window is invalid")
        if not all(item.strip() for item in self.provenance):
            raise ValueError("audience evidence provenance cannot be blank")
        return self

    def is_current(self, now: datetime) -> bool:
        if now.tzinfo is None:
            raise ValueError("media admission clock must be timezone-aware")
        return self.observed_at <= now <= self.valid_until


class TargetBuyerHypothesis(BaseModel):
    hypothesis: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: EvidenceConfidence = EvidenceConfidence.UNVERIFIED
    transfer_limit: str = Field(min_length=1)


class MediaActivationPlan(BaseModel):
    owner: Owner = Owner.SALES_HUMAN
    campaign_id: str = Field(min_length=1)
    experiment_id: str = Field(min_length=1)
    vehicle_id: str = Field(min_length=1)
    campaign_objective: str = Field(min_length=1)
    paid_ad_eligibility: PaidAdEligibility
    target_buyer_hypothesis: TargetBuyerHypothesis
    selected_strategy: AudienceStrategy
    strategy_candidates: list[AudienceStrategy] = Field(min_length=1)
    age_hypothesis: str | None = None
    geo_hypothesis: str | None = None
    geo_expansion: bool = False
    audience_breadth: str = Field(min_length=1)
    manual_targeting_signals: list[str] = Field(default_factory=list)
    platform_expansion_allowed: bool | None = None
    retargeting_state: AudienceDataState = AudienceDataState.NOT_USED
    custom_audience_state: AudienceDataState = AudienceDataState.NOT_USED
    lookalike_state: AudienceDataState = AudienceDataState.NOT_USED
    audience_data_use_authorized: bool = False
    exclusions: list[str] = Field(default_factory=list)
    budget_test_cell: str | None = None
    creative_variant_id: str | None = None
    copy_variant_id: str | None = None
    positioning_id: str = Field(min_length=1)
    evidence_basis: list[str] = Field(min_length=1)
    evidence: list[AudienceEvidence] = Field(min_length=1)
    uncertainties: list[str] = Field(default_factory=list)
    test_stop_condition: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_sales_media_plan(self) -> MediaActivationPlan:
        if self.owner is not Owner.SALES_HUMAN:
            raise ValueError("MEDIA_ACTIVATION is owned by SALES_HUMAN")
        if self.paid_ad_eligibility is not PaidAdEligibility.PASS:
            raise ValueError("media activation requires PAID_AD_ELIGIBILITY=PASS")
        if self.selected_strategy not in self.strategy_candidates:
            raise ValueError("selected media strategy must be a declared candidate")
        evidence_ids = {item.evidence_id for item in self.evidence}
        if not set(self.evidence_basis) <= evidence_ids:
            raise ValueError("media plan evidence basis contains unknown evidence ids")
        if not set(self.target_buyer_hypothesis.evidence_ids) <= evidence_ids:
            raise ValueError("target buyer hypothesis references unknown evidence")
        if any(item.vehicle_id != self.vehicle_id for item in self.evidence):
            raise ValueError("media evidence vehicle binding mismatch")
        return self


class MediaPlanAdmission(BaseModel):
    campaign_id: str
    owner: Owner
    status: MediaPlanStatus
    age_assertion_state: AudienceAssertionState
    blockers: list[str] = Field(default_factory=list)


class MediaActivationGate:
    def admit(self, plan: MediaActivationPlan, *, now: datetime) -> MediaPlanAdmission:
        evidence_by_id = {item.evidence_id: item for item in plan.evidence}
        basis = [evidence_by_id[evidence_id] for evidence_id in plan.evidence_basis]
        current = [item for item in basis if item.is_current(now)]
        blockers: list[str] = []
        if len(current) != len(basis):
            blockers.append("STALE_CAMPAIGN_EVIDENCE")

        capability = [
            item
            for item in current
            if AudienceDimension.PLATFORM_CAPABILITY in item.dimensions
        ]
        if not any(plan.selected_strategy in item.supported_strategies for item in capability):
            blockers.append("CURRENT_PLATFORM_CAPABILITY_UNVERIFIED")

        if plan.selected_strategy is AudienceStrategy.RETARGETING and plan.retargeting_state not in {
            AudienceDataState.CANDIDATE,
            AudienceDataState.ACTIVE,
        }:
            blockers.append("RETARGETING_AUDIENCE_UNAVAILABLE")
        if plan.selected_strategy is AudienceStrategy.CUSTOM and plan.custom_audience_state not in {
            AudienceDataState.CANDIDATE,
            AudienceDataState.ACTIVE,
        }:
            blockers.append("CUSTOM_AUDIENCE_UNAVAILABLE")
        if plan.selected_strategy is AudienceStrategy.LOOKALIKE and plan.lookalike_state not in {
            AudienceDataState.CANDIDATE,
            AudienceDataState.ACTIVE,
        }:
            blockers.append("LOOKALIKE_AUDIENCE_UNAVAILABLE")
        if plan.selected_strategy in {
            AudienceStrategy.RETARGETING,
            AudienceStrategy.CUSTOM,
            AudienceStrategy.LOOKALIKE,
        } and not plan.audience_data_use_authorized:
            blockers.append("AUDIENCE_DATA_USE_NOT_AUTHORIZED")

        if plan.geo_expansion and not any(
            item.dimensions
            & {
                AudienceDimension.GEO,
                AudienceDimension.SCARCITY,
                AudienceDimension.SUPPLY_DENSITY,
            }
            for item in current
        ):
            blockers.append("GEO_EXPANSION_EVIDENCE_MISSING")

        age_evidence = any(AudienceDimension.AGE in item.dimensions for item in current)
        age_state = (
            AudienceAssertionState.EVIDENCE_BACKED_HYPOTHESIS
            if plan.age_hypothesis and age_evidence
            else AudienceAssertionState.AUDIENCE_ASSUMPTION
        )
        return MediaPlanAdmission(
            campaign_id=plan.campaign_id,
            owner=plan.owner,
            status=MediaPlanStatus.HOLD if blockers else MediaPlanStatus.PASS,
            age_assertion_state=age_state,
            blockers=blockers,
        )


class MediaCandidate(BaseModel):
    audience_cell_id: str = Field(min_length=1)
    strategy: AudienceStrategy
    vehicle_id: str = Field(min_length=1)
    geo_hypothesis: str | None = None
    age_hypothesis: str | None = None
    creative_variant_id: str = Field(min_length=1)
    copy_variant_id: str = Field(min_length=1)
    positioning_id: str = Field(min_length=1)
    budget_amount: Decimal = Field(gt=0)


class MediaCandidateComparison(BaseModel):
    experiment_id: str = Field(min_length=1)
    candidates: list[MediaCandidate] = Field(min_length=2, max_length=5)
    changed_variable: str = "AUDIENCE_STRATEGY"

    @model_validator(mode="after")
    def validate_controlled_comparison(self) -> MediaCandidateComparison:
        if self.changed_variable != "AUDIENCE_STRATEGY":
            raise ValueError("media comparison must isolate audience strategy")
        invariant_fields = {
            (
                item.vehicle_id,
                item.creative_variant_id,
                item.copy_variant_id,
                item.positioning_id,
                item.budget_amount,
            )
            for item in self.candidates
        }
        if len(invariant_fields) != 1:
            raise ValueError("media comparison contains creative, copy, vehicle, or budget contamination")
        if len({item.strategy for item in self.candidates}) < 2:
            raise ValueError("media comparison requires distinct audience strategies")
        if len({item.audience_cell_id for item in self.candidates}) != len(self.candidates):
            raise ValueError("media comparison audience cells must be unique")
        return self


class CampaignFunnel(BaseModel):
    impressions: int = Field(ge=0)
    engaged: int = Field(ge=0)
    clicks: int = Field(ge=0)
    message_starts: int = Field(ge=0)
    qualified_conversations: int = Field(ge=0)
    appointments: int = Field(ge=0)
    show_ups: int = Field(ge=0)
    sold: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_funnel_order(self) -> CampaignFunnel:
        if self.clicks > self.impressions:
            raise ValueError("clicks cannot exceed impressions")
        ordered = (
            self.impressions,
            self.engaged,
            self.message_starts,
            self.qualified_conversations,
            self.appointments,
            self.show_ups,
            self.sold,
        )
        if any(left < right for left, right in pairwise(ordered)):
            raise ValueError("campaign funnel counts must be non-increasing")
        return self


class CampaignOutcomeRecord(BaseModel):
    owner: Owner = Owner.SALES_HUMAN
    campaign_id: str = Field(min_length=1)
    experiment_id: str = Field(min_length=1)
    audience_cell_id: str = Field(min_length=1)
    creative_variant_id: str = Field(min_length=1)
    copy_variant_id: str = Field(min_length=1)
    vehicle_id: str = Field(min_length=1)
    period_start: datetime
    period_end: datetime
    stale_after: datetime
    spend: Decimal = Field(ge=0)
    funnel: CampaignFunnel
    attribution_state: AttributionState
    hypothesis_alignment: HypothesisAlignment = HypothesisAlignment.UNKNOWN
    contamination_flags: set[ContaminationFlag] = Field(default_factory=set)

    @model_validator(mode="after")
    def validate_outcome_window(self) -> CampaignOutcomeRecord:
        if self.owner is not Owner.SALES_HUMAN:
            raise ValueError("campaign outcome learning is owned by SALES_HUMAN")
        if any(
            item.tzinfo is None
            for item in (self.period_start, self.period_end, self.stale_after)
        ):
            raise ValueError("campaign outcome timestamps must be timezone-aware")
        if not self.period_start < self.period_end <= self.stale_after:
            raise ValueError("campaign outcome time window is invalid")
        return self


class MediaLearningCriteria(BaseModel):
    minimum_impressions: int = Field(gt=0)
    high_ctr_threshold: float = Field(ge=0, le=1)
    minimum_qualified_message_rate: float = Field(ge=0, le=1)


class MediaLearningReceipt(BaseModel):
    campaign_id: str
    decision: MediaLearningDecision
    reason_codes: list[str]
    causal_credit_allowed: bool = False


class MediaLearningEvaluator:
    def evaluate(
        self,
        record: CampaignOutcomeRecord,
        *,
        criteria: MediaLearningCriteria,
        now: datetime,
    ) -> MediaLearningReceipt:
        if now.tzinfo is None:
            raise ValueError("media learning clock must be timezone-aware")
        reasons: list[str] = []
        if now > record.stale_after:
            reasons.append("STALE_CAMPAIGN_EVIDENCE")
        if ContaminationFlag.AUDIENCE_OVERLAP in record.contamination_flags:
            reasons.append("AUDIENCE_OVERLAP")
        if record.contamination_flags & {
            ContaminationFlag.CREATIVE_CHANGED,
            ContaminationFlag.COPY_CHANGED,
            ContaminationFlag.BUDGET_CHANGED,
            ContaminationFlag.VEHICLE_CHANGED,
            ContaminationFlag.UNKNOWN,
        }:
            reasons.append("EXPERIMENT_CONTAMINATED")
        if record.funnel.impressions < criteria.minimum_impressions:
            reasons.append("INSUFFICIENT_SAMPLE")
        if reasons:
            return MediaLearningReceipt(
                campaign_id=record.campaign_id,
                decision=MediaLearningDecision.HOLD,
                reason_codes=reasons,
            )

        ctr = record.funnel.clicks / record.funnel.impressions
        qualified_rate = (
            record.funnel.qualified_conversations / record.funnel.message_starts
            if record.funnel.message_starts
            else 0.0
        )
        if (
            ctr >= criteria.high_ctr_threshold
            and qualified_rate < criteria.minimum_qualified_message_rate
        ):
            reasons.append("HIGH_CTR_LOW_QUALIFIED_OUTCOME")
        if (
            record.funnel.sold > 0
            and record.hypothesis_alignment is HypothesisAlignment.CONTRADICTS
        ):
            reasons.append("AUDIENCE_HYPOTHESIS_CONTRADICTED_BY_SOLD_COHORT")
        if reasons:
            return MediaLearningReceipt(
                campaign_id=record.campaign_id,
                decision=MediaLearningDecision.CALIBRATE,
                reason_codes=reasons,
            )

        return MediaLearningReceipt(
            campaign_id=record.campaign_id,
            decision=MediaLearningDecision.OBSERVE,
            reason_codes=["OUTCOME_LINKAGE_OBSERVED"],
            causal_credit_allowed=(
                record.attribution_state is AttributionState.CONTROLLED
            ),
        )
