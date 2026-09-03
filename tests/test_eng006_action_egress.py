from __future__ import annotations

import pytest

from global_hybrid_v2.governance.research_consumption import (
    ActionKind,
    ActionPlan,
    FinalResponseObject,
    InputRequiredReceipt,
    ResearchConsumptionGate,
    ResearchEvidencePacket,
    TurnContract,
)


def _packet():
    return ResearchEvidencePacket(
        task_id="t",
        user_goal="next",
        research_question="q",
        source_refs=["repo"],
        verified_findings=["current finding"],
        decision_inputs=["current finding"],
    )


def _contract(**values):
    data = dict(
        task_id="t",
        current_authority_version="current",
        current_user_goal="next",
        next_external_user_action="DELIVER_ENGINEER_INSTRUCTION",
        deliverable_contract="EXACTLY_ONE_COPYABLE_ENGINEERING_INSTRUCTION",
        required_obligations=["ENGINEER_INSTRUCTION"],
    )
    data.update(values)
    return TurnContract(**data)


def test_eng006_selfretrieve_001_through_004_block_user_offload_when_sources_remain():
    with pytest.raises(ValueError, match="SELF_RETRIEVE"):
        ResearchConsumptionGate.admit_action(
            _contract(next_external_user_action="ANSWER"),
            ActionPlan(kind=ActionKind.ASK_USER, payload="paste SHA"),
            sources_callable=True,
        )


def test_eng006_elicit_005_requires_typed_receipt():
    plan = ActionPlan(
        kind=ActionKind.ASK_USER,
        input_required_receipt=InputRequiredReceipt(
            reason="TOOL_INPUT_REQUIRED", exact_missing_input="repository authorization"
        ),
    )
    assert (
        ResearchConsumptionGate.admit_action(
            _contract(next_external_user_action="ANSWER"), plan, sources_callable=False
        )
        == plan
    )


def test_eng006_instruction_010_and_011_block_status_without_required_handoff():
    with pytest.raises(ValueError, match="engineer instruction"):
        ResearchConsumptionGate.admit_action(
            _contract(), ActionPlan(kind=ActionKind.ANSWER, payload="notes updated"), sources_callable=False
        )


def test_eng006_instruction_012_delivers_one_copyable_instruction():
    packet = _packet()
    plan = ActionPlan(kind=ActionKind.DELIVER_HANDOFF, payload="ENGINEER_INSTRUCTION: implement exact fix")
    final = FinalResponseObject(task_id="t", consumed_packet_id=packet.packet_id, claims=["current finding"])
    assert ResearchConsumptionGate.validate_terminal(_contract(), plan, final, packet).serialize


def test_eng006_egress_014_rewrite_is_revalidated():
    packet = _packet()
    plan = ActionPlan(kind=ActionKind.DELIVER_HANDOFF, payload="ENGINEER_INSTRUCTION")
    final = FinalResponseObject(task_id="t", consumed_packet_id=packet.packet_id, claims=["current finding"])
    assert ResearchConsumptionGate.validate_terminal(_contract(), plan, final, packet).serialize
    assert not ResearchConsumptionGate.validate_terminal(
        _contract(), ActionPlan(kind=ActionKind.DELIVER_HANDOFF, payload="status only"), final, packet
    ).serialize


def test_eng006_evidence_006_to_009_packet_beats_intervening_prose_and_stale_scope_blocks():
    packet = _packet()
    final = FinalResponseObject(task_id="t", consumed_packet_id=packet.packet_id, claims=["current finding"])
    assert ResearchConsumptionGate.validate_final(packet, final) == final
    stale = ResearchConsumptionGate.invalidate_for_scope_change(packet)
    with pytest.raises(ValueError, match="stale"):
        ResearchConsumptionGate.validate_final(stale, final)
