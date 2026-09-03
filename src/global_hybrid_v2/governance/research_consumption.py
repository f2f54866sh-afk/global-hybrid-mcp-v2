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


class FinalResponseObject(BaseModel):
    task_id: str
    consumed_packet_id: str
    claims: list[str] = Field(default_factory=list)
    labelled_inferences: list[str] = Field(default_factory=list)


class SelfResolvabilityDecision(BaseModel):
    ask_user: bool
    next_action: str
    blocker: str | None = None


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
