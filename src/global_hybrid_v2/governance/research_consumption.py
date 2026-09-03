"""ENG-006: immutable retrieval-to-decision-to-egress consumption."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field


class ResearchEvidencePacket(BaseModel):
    packet_id: str = Field(default_factory=lambda: str(uuid4()))
    task_id: str = Field(min_length=1)
    user_goal: str = Field(min_length=1)
    research_question: str = Field(min_length=1)
    source_refs: list[str] = Field(min_length=1)
    currentness: str = "CURRENT"
    verified_findings: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    unknown_items: list[str] = Field(default_factory=list)
    decision_inputs: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    stale: bool = False
    current_mapping_version: str | None = None
    resolved_referent_id: str | None = None
    identity_source_id: str | None = None
    identity_source_version: str | None = None
    identity_currentness_token: str | None = None


class FinalResponseObject(BaseModel):
    task_id: str
    consumed_packet_id: str
    claims: list[str] = Field(default_factory=list)
    labelled_inferences: list[str] = Field(default_factory=list)
    current_mapping_version: str | None = None
    resolved_referent_id: str | None = None
    identity_source_id: str | None = None
    identity_source_version: str | None = None
    identity_currentness_token: str | None = None


class SelfResolvabilityDecision(BaseModel):
    ask_user: bool
    next_action: str
    blocker: str | None = None


class ActionKind(str):
    SELF_RETRIEVE = "SELF_RETRIEVE"
    ASK_USER = "ASK_USER"
    ANSWER = "ANSWER"
    DELIVER_HANDOFF = "DELIVER_HANDOFF"
    EXECUTE_EFFECT = "EXECUTE_EFFECT"
    BLOCK = "BLOCK"


class InputRequiredReceipt(BaseModel):
    reason: str
    exact_missing_input: str


class TurnContract(BaseModel):
    task_id: str
    current_authority_version: str
    current_user_goal: str
    next_external_user_action: str
    deliverable_contract: str
    required_obligations: list[str] = Field(default_factory=list)
    prohibited_actions: list[str] = Field(default_factory=list)
    required_information: list[str] = Field(default_factory=list)
    current_evidence_refs: list[str] = Field(default_factory=list)
    ask_user_admission_state: str = "UNDECIDED"
    current_mapping_version: str | None = None
    resolved_referent_id: str | None = None
    identity_source_id: str | None = None
    identity_source_version: str | None = None
    identity_currentness_token: str | None = None


class ActionPlan(BaseModel):
    kind: str
    payload: str = ""
    deliverable_contract: str | None = None
    fulfilled_obligations: list[str] = Field(default_factory=list)
    input_required_receipt: InputRequiredReceipt | None = None
    current_mapping_version: str | None = None
    resolved_referent_id: str | None = None
    identity_source_id: str | None = None
    identity_source_version: str | None = None
    identity_currentness_token: str | None = None


class FinalEgressVerdict(BaseModel):
    serialize: bool
    reason: str


class ResearchConsumptionGate:
    """Single final-consumption gate; prose never mutates a packet."""

    @staticmethod
    def self_resolvability(
        *, sources_callable: bool, input_required: bool = False
    ) -> SelfResolvabilityDecision:
        if sources_callable:
            return SelfResolvabilityDecision(ask_user=False, next_action="SELF_RETRIEVE")
        if input_required:
            return SelfResolvabilityDecision(ask_user=True, next_action="ASK_USER", blocker="INPUT_REQUIRED")
        return SelfResolvabilityDecision(ask_user=False, next_action="BLOCK", blocker="SOURCE_UNAVAILABLE")

    @staticmethod
    def invalidate_for_scope_change(packet: ResearchEvidencePacket) -> ResearchEvidencePacket:
        return packet.model_copy(update={"stale": True, "currentness": "STALE"})

    @staticmethod
    def admit_action(contract: TurnContract, plan: ActionPlan, *, sources_callable: bool) -> ActionPlan:
        if plan.kind == ActionKind.ASK_USER:
            if sources_callable:
                raise ValueError("NO_SERIALIZE: self-retrievable information requires SELF_RETRIEVE")
            if plan.input_required_receipt is None:
                raise ValueError("NO_SERIALIZE: ASK_USER requires INPUT_REQUIRED_RECEIPT")
        if contract.required_obligations and plan.deliverable_contract != contract.deliverable_contract:
            raise ValueError("NO_SERIALIZE: deliverable contract is not fulfilled")
        if not set(contract.required_obligations) <= set(plan.fulfilled_obligations):
            raise ValueError("NO_SERIALIZE: required deliverable obligations are unfulfilled")
        return plan

    @staticmethod
    def validate_terminal(
        contract: TurnContract,
        plan: ActionPlan,
        final: FinalResponseObject,
        packet: ResearchEvidencePacket,
    ) -> FinalEgressVerdict:
        ResearchConsumptionGate.admit_action(contract, plan, sources_callable=False)
        ResearchConsumptionGate.validate_final(packet, final)
        if any(item in plan.payload for item in contract.prohibited_actions):
            return FinalEgressVerdict(serialize=False, reason="NO_SERIALIZE: prohibited action serialized")
        return FinalEgressVerdict(serialize=True, reason="PASS")

    @staticmethod
    def validate_final(packet: ResearchEvidencePacket, final: FinalResponseObject) -> FinalResponseObject:
        if packet.stale or packet.currentness != "CURRENT":
            raise ValueError("BLOCK_EGRESS: current evidence packet is stale")
        if final.task_id != packet.task_id:
            raise ValueError("BLOCK_EGRESS: final task id does not match evidence packet")
        if final.consumed_packet_id != packet.packet_id:
            raise ValueError("BLOCK_EGRESS: final consumed packet id mismatch")
        unsupported = set(final.claims) - set(packet.verified_findings)
        if unsupported:
            raise ValueError("BLOCK_EGRESS: final claims are not verified by current evidence packet")
        return final
