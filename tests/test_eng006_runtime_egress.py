from global_hybrid_v2.contracts import (
    AuthoritySnapshot,
    ContextItem,
    ContextOrigin,
    DomainResult,
    Intent,
    Owner,
    TaskRequest,
)
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
            return _result(action=ActionKind.ASK_USER)

    request = TaskRequest(
        request_text="status",
        intent=Intent.EXECUTION,
        context=[
            ContextItem(
                id="github",
                origin=ContextOrigin.CURRENT_TOOL_RESULT,
                purpose="read",
                task_scope="status",
                payload={},
            )
        ],
        turn_contract={"forged": "PASS"},
        sources_callable=False,
    )
    result = Dispatcher(
        authority=Authority(), domains={Owner.EXECUTION: Domain()}, trace=TraceBus()
    ).dispatch(request)
    assert result.status == UNKNOWN_WITH_EXACT_BLOCKER


def test_dispatcher_blocks_self_consistent_terminal_state_for_another_task():
    class Authority:
        def resolve(self):
            return AuthoritySnapshot(entries={})

    class Domain:
        def run(self, contract):
            return _result()

    result = Dispatcher(
        authority=Authority(), domains={Owner.EXECUTION: Domain()}, trace=TraceBus()
    ).dispatch(TaskRequest(request_text="status", intent=Intent.EXECUTION))
    assert result.status == UNKNOWN_WITH_EXACT_BLOCKER
    assert result.evidence["terminal_task_binding"] == "FAIL"
