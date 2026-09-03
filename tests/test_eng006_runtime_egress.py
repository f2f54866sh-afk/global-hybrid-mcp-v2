from global_hybrid_v2.contracts import AuthoritySnapshot, DomainResult, Intent, Owner, TaskRequest
from global_hybrid_v2.governance.egress import UNKNOWN_WITH_EXACT_BLOCKER, ResponseEgressValidator
from global_hybrid_v2.governance.research_consumption import (
    ActionKind,
    ActionPlan,
    FinalResponseObject,
    ResearchEvidencePacket,
    TurnContract,
)
from global_hybrid_v2.runtime.dispatcher import Dispatcher
from global_hybrid_v2.runtime.trace import TraceBus


def _result(*, sources_callable=False, action=ActionKind.DELIVER_HANDOFF):
    packet = ResearchEvidencePacket(
        task_id="t",
        user_goal="next",
        research_question="q",
        source_refs=["repo"],
        verified_findings=["finding"],
        decision_inputs=["finding"],
    )
    return DomainResult(
        owner=Owner.EXECUTION,
        status="OK",
        evidence={"sources_callable": sources_callable},
        research_evidence_packet=packet.model_dump(mode="json"),
        final_response_object=FinalResponseObject(
            task_id="t", consumed_packet_id=packet.packet_id, claims=["finding"]
        ).model_dump(),
        turn_contract=TurnContract(
            task_id="t",
            current_authority_version="v",
            current_user_goal="next",
            next_external_user_action="DELIVER_ENGINEER_INSTRUCTION",
            deliverable_contract="one",
            required_obligations=["ENGINEER_INSTRUCTION"],
        ).model_dump(),
        action_plan=ActionPlan(kind=action, payload="ENGINEER_INSTRUCTION").model_dump(),
    )


def test_terminal_egress_consumes_runtime_turn_and_evidence():
    assert ResponseEgressValidator().validate(_result()).evidence["evidence_packet_check"] == "PASS"


def test_terminal_egress_blocks_ask_user_when_runtime_source_callable():
    result = _result(sources_callable=True, action=ActionKind.ASK_USER)
    assert ResponseEgressValidator().validate(result).status == UNKNOWN_WITH_EXACT_BLOCKER


def test_dispatcher_assembles_terminal_inputs_and_blocks_self_retrievable_ask_user():
    class Authority:
        def resolve(self):
            return AuthoritySnapshot(entries={})

    class Domain:
        def run(self, contract):
            return DomainResult(owner=Owner.EXECUTION, status="OK")

    packet = ResearchEvidencePacket(
        task_id="placeholder",
        user_goal="goal",
        research_question="q",
        source_refs=["github"],
        verified_findings=["finding"],
        decision_inputs=["finding"],
    )
    request = TaskRequest(
        request_text="status",
        intent=Intent.EXECUTION,
        turn_contract=TurnContract(
            task_id="placeholder",
            current_authority_version="v",
            current_user_goal="goal",
            next_external_user_action="ANSWER",
            deliverable_contract="answer",
        ).model_dump(),
        action_plan=ActionPlan(kind=ActionKind.ASK_USER, payload="paste SHA").model_dump(),
        research_evidence_packet=packet.model_dump(mode="json"),
        final_response_object=FinalResponseObject(
            task_id="placeholder", consumed_packet_id=packet.packet_id, claims=["finding"]
        ).model_dump(),
        sources_callable=True,
    )
    result = Dispatcher(
        authority=Authority(), domains={Owner.EXECUTION: Domain()}, trace=TraceBus()
    ).dispatch(request)
    assert result.status == UNKNOWN_WITH_EXACT_BLOCKER
