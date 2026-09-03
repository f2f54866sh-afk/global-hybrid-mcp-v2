from __future__ import annotations

import pytest

from global_hybrid_v2.governance.research_consumption import (
    FinalResponseObject,
    ResearchConsumptionGate,
    ResearchEvidencePacket,
)


def _packet(**changes):
    data = dict(
        task_id="task-1", user_goal="check CI", research_question="what passed?",
        source_refs=["github:run"], verified_findings=["finding A"],
        unknown_items=["unknown X"], decision_inputs=["finding A"],
    )
    data.update(changes)
    return ResearchEvidencePacket(**data)


def test_github_is_self_retrieved_not_requested_from_user():
    decision = ResearchConsumptionGate.self_resolvability(sources_callable=True)
    assert decision.ask_user is False and decision.next_action == "SELF_RETRIEVE"


def test_intervening_prose_cannot_replace_retrieved_finding():
    packet = _packet()
    final = FinalResponseObject(task_id="task-1", consumed_packet_id=packet.packet_id, claims=["finding A"])
    assert ResearchConsumptionGate.validate_final(packet, final) == final


def test_conflicting_intervening_prose_is_blocked():
    packet = _packet()
    final = FinalResponseObject(task_id="task-1", consumed_packet_id=packet.packet_id, claims=["prose guess"])
    with pytest.raises(ValueError, match="not verified"):
        ResearchConsumptionGate.validate_final(packet, final)


def test_next_step_consumes_current_packet_not_salience():
    packet = _packet()
    final = FinalResponseObject(task_id="task-1", consumed_packet_id=packet.packet_id, claims=["finding A"])
    assert ResearchConsumptionGate.validate_final(packet, final).consumed_packet_id == packet.packet_id


def test_scope_change_stales_packet():
    packet = ResearchConsumptionGate.invalidate_for_scope_change(_packet())
    with pytest.raises(ValueError, match="stale"):
        ResearchConsumptionGate.validate_final(
            packet, FinalResponseObject(task_id="task-1", consumed_packet_id=packet.packet_id)
        )


def test_unknown_cannot_be_promoted_by_prose():
    packet = _packet(verified_findings=[])
    with pytest.raises(ValueError, match="not verified"):
        ResearchConsumptionGate.validate_final(packet, FinalResponseObject(
            task_id="task-1", consumed_packet_id=packet.packet_id, claims=["unknown X"])
        )


def test_non_packet_current_fact_blocks_egress():
    packet = _packet()
    with pytest.raises(ValueError, match="not verified"):
        ResearchConsumptionGate.validate_final(packet, FinalResponseObject(
            task_id="task-1", consumed_packet_id=packet.packet_id, claims=["new current fact"]))
