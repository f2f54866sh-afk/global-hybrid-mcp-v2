import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from mcp import Client
from mcp.types import TextContent

from global_hybrid_v2.adapters.mcp_server import create_mcp_server
from global_hybrid_v2.contracts import (
    AuthoritySnapshot,
    CurrentIdentityProjection,
    DialogueBindingState,
    DomainResult,
    EffectType,
    Intent,
    Owner,
    TaskRequest,
)
from global_hybrid_v2.governance.host_projection import (
    CURRENT_IDENTITY_CURRENTNESS_UNPROVEN,
    DIALOGUE_REFERENT_AMBIGUOUS,
    HOST_STATE_PROJECTION_STALE,
    HOST_STATE_PROJECTION_UNAVAILABLE,
    WITNESS_READ_ONLY,
    HostCurrentStateVerification,
    HostCurrentStateVerifier,
    HostProjectionGate,
)
from global_hybrid_v2.governance.research_consumption import (
    ActionKind,
    ActionPlan,
    FinalResponseObject,
    ResearchEvidencePacket,
    TurnContract,
)
from global_hybrid_v2.observer.witness import ReadOnlyWitness
from global_hybrid_v2.runtime.dispatcher import Dispatcher
from global_hybrid_v2.runtime.trace import TraceBus

NOW = datetime(2026, 9, 4, tzinfo=UTC)
HOST_CURRENT_MAPPING = {
    "執行長": "CURRENT_CANONICAL",
    "管家": "GLOBAL",
    "秘書": "GPT",
    "風紀": "EXECUTION_CONTROL",
    "監察官": "WITNESS",
    "書記官": "GITHUB",
}


class _TrustedHostVerifier(HostCurrentStateVerifier):
    def verify(self, projection):
        trusted = (
            projection.source_id == "chat-host-current-state"
            and projection.source_version == "2026.09.04"
            and projection.currentness_token == "current-token"
            and projection.identities == HOST_CURRENT_MAPPING
        )
        return HostCurrentStateVerification(trusted)


class _Authority:
    def resolve(self):
        return AuthoritySnapshot(entries={})


class _Domain:
    def __init__(
        self,
        *,
        drift: bool = False,
        referent_drift: bool = False,
        missing_consumer: bool = False,
    ):
        self.contract = None
        self.drift = drift
        self.referent_drift = referent_drift
        self.missing_consumer = missing_consumer

    def run(self, contract):
        self.contract = contract
        version = "other-version" if self.drift else contract.current_mapping_version
        referent = "other-referent" if self.referent_drift else contract.resolved_referent_id
        binding = {
            "current_mapping_version": version,
            "resolved_referent_id": referent,
            "identity_source_id": contract.identity_source_id,
            "identity_source_version": contract.identity_source_version,
            "identity_currentness_token": contract.identity_currentness_token,
        }
        packet = ResearchEvidencePacket(
            task_id=contract.task_id,
            user_goal="inspect current task",
            research_question="what is bound",
            source_refs=["host:projection"],
            verified_findings=["current host binding"],
            decision_inputs=["current host binding"],
            **binding,
        )
        return DomainResult(
            owner=contract.owner,
            status="DONE",
            output="current host binding",
            research_evidence_packet=packet.model_dump(mode="json"),
            final_response_object=FinalResponseObject(
                task_id=contract.task_id,
                consumed_packet_id=packet.packet_id,
                claims=["current host binding"],
                **binding,
            ).model_dump(mode="json"),
            turn_contract=TurnContract(
                task_id=contract.task_id,
                current_authority_version="current",
                current_user_goal="inspect current task",
                next_external_user_action="DELIVER",
                deliverable_contract="host-handoff",
                required_obligations=["HOST_HANDOFF"],
                **binding,
            ).model_dump(mode="json"),
            action_plan=(
                None
                if self.missing_consumer
                else ActionPlan(
                    kind=ActionKind.DELIVER_HANDOFF,
                    deliverable_contract="host-handoff",
                    fulfilled_obligations=["HOST_HANDOFF"],
                    **binding,
                ).model_dump(mode="json")
            ),
        )


def _request(
    *,
    alias: str = "管家",
    referent: str = "active-task-7",
    valid_until: datetime | None = None,
    identities: dict[str, str] | None = None,
    ambiguity: bool = False,
    effects: list[EffectType] | None = None,
) -> TaskRequest:
    expiry = valid_until or (NOW + timedelta(minutes=5))
    return TaskRequest(
        request_text="inspect task",
        intent=Intent.EXECUTION,
        effects=effects or [EffectType.READ_ONLY],
        current_identity_projection=CurrentIdentityProjection(
            mapping_version="host-map-20260904",
            projection_id="projection-7",
            projection_version="projection-v7",
            source_id="chat-host-current-state",
            source_version="2026.09.04",
            currentness_token="current-token",
            source_state="CURRENT",
            source_provenance=["host:current-state:readback"],
            identities=identities or dict(HOST_CURRENT_MAPPING),
            issued_at=NOW - timedelta(minutes=1),
            valid_until=expiry,
        ),
        dialogue_binding_state=DialogueBindingState(
            mapping_version="host-map-20260904",
            requested_identity_alias=alias,
            resolved_referent_id=referent,
            issued_at=NOW - timedelta(minutes=1),
            valid_until=expiry,
            material_ambiguity=ambiguity,
        ),
    )


def _dispatcher(
    domain: _Domain,
    trace: TraceBus | None = None,
    verifier: HostCurrentStateVerifier | None = None,
) -> Dispatcher:
    return Dispatcher(
        authority=_Authority(),
        domains={Owner.EXECUTION: domain},
        trace=trace or TraceBus(),
        host_projection_gate=HostProjectionGate(
            now=lambda: NOW,
            verifier=verifier or _TrustedHostVerifier(),
        ),
    )


def test_current_host_mapping_routes_and_binds_one_referent(capsys):
    domain = _Domain()
    result = _dispatcher(domain).dispatch(_request(), require_host_projection=True)
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]

    assert result.status == "DONE"
    assert domain.contract.current_mapping_version == "host-map-20260904"
    assert domain.contract.resolved_referent_id == "active-task-7"
    for stage in {"owner_route", "response_egress"}:
        event = next(item for item in events if item["stage"] == stage)
        assert event["metadata"]["current_mapping_version"] == "host-map-20260904"
        assert event["metadata"]["resolved_referent_id"] == "active-task-7"


def test_witness_alias_can_analyze_suspended_referent_without_mutation(capsys):
    trace = TraceBus(witness=ReadOnlyWitness())
    result = _dispatcher(trace=trace, domain=_Domain()).dispatch(
        _request(alias="監察官", referent="suspended-task-previous"),
        require_host_projection=True,
    )
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]

    assert result.status == "DONE"
    observed = [item for item in events if item["stage"] == "witness_observation"]
    assert any(
        item["metadata"]["resolved_referent_id"] == "suspended-task-previous" for item in observed
    )


def test_stale_or_wrong_current_mapping_blocks_before_owner_routing(capsys):
    domain = _Domain()
    stale = _dispatcher(domain).dispatch(
        _request(valid_until=NOW - timedelta(seconds=1)), require_host_projection=True
    )
    assert stale.status == HOST_STATE_PROJECTION_STALE and domain.contract is None

    unproven = _dispatcher(_Domain()).dispatch(
        _request(identities={**HOST_CURRENT_MAPPING, "執行長": "GLOBAL"}),
        require_host_projection=True,
    )
    assert unproven.status == CURRENT_IDENTITY_CURRENTNESS_UNPROVEN
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert not any(event["stage"] == "owner_route" for event in events)


def test_missing_or_stale_currentness_proof_blocks_without_server_local_mapping():
    class StaleTokenVerifier(HostCurrentStateVerifier):
        def verify(self, projection):
            if projection.currentness_token == "stale-token":
                return HostCurrentStateVerification(False, HOST_STATE_PROJECTION_STALE)
            return HostCurrentStateVerification(False, CURRENT_IDENTITY_CURRENTNESS_UNPROVEN)

    missing_proof = _request()
    missing_proof.current_identity_projection = missing_proof.current_identity_projection.model_copy(
        update={"source_provenance": ["host:unverified"]}
    )
    assert (
        _dispatcher(_Domain(), verifier=StaleTokenVerifier()).dispatch(
            missing_proof, require_host_projection=True
        ).status
        == CURRENT_IDENTITY_CURRENTNESS_UNPROVEN
    )

    stale_token = _request()
    stale_token.current_identity_projection = stale_token.current_identity_projection.model_copy(
        update={"currentness_token": "stale-token"}
    )
    assert (
        _dispatcher(_Domain(), verifier=StaleTokenVerifier()).dispatch(
            stale_token, require_host_projection=True
        ).status
        == HOST_STATE_PROJECTION_STALE
    )

    production_default = Dispatcher(
        authority=_Authority(),
        domains={Owner.EXECUTION: _Domain()},
        trace=TraceBus(),
        host_projection_gate=HostProjectionGate(now=lambda: NOW),
    ).dispatch(_request(), require_host_projection=True)
    assert production_default.status == CURRENT_IDENTITY_CURRENTNESS_UNPROVEN
    assert production_default.evidence["host_state_validation"] == "VALIDATION_PENDING"


def test_missing_projection_and_material_ambiguity_fail_closed_before_side_effect():
    missing = _dispatcher(_Domain()).dispatch(
        TaskRequest(request_text="inspect", intent=Intent.EXECUTION), require_host_projection=True
    )
    assert missing.status == HOST_STATE_PROJECTION_UNAVAILABLE

    ambiguous = _dispatcher(_Domain()).dispatch(
        _request(ambiguity=True, effects=[EffectType.EXTERNAL_WRITE]), require_host_projection=True
    )
    assert ambiguous.status == DIALOGUE_REFERENT_AMBIGUOUS


def test_witness_identity_cannot_mutate():
    result = _dispatcher(_Domain()).dispatch(
        _request(alias="監察官", effects=[EffectType.EXTERNAL_WRITE]), require_host_projection=True
    )
    assert result.status == WITNESS_READ_ONLY


def test_egress_blocks_mapping_version_drift():
    result = _dispatcher(_Domain(drift=True)).dispatch(_request(), require_host_projection=True)
    assert result.evidence["host_binding_consumption"] == "FAIL"


def test_egress_blocks_referent_drift_before_serialization():
    result = _dispatcher(_Domain(referent_drift=True)).dispatch(
        _request(), require_host_projection=True
    )
    assert result.evidence["host_binding_consumption"] == "FAIL"


def test_egress_blocks_missing_host_binding_consumer_before_serialization():
    result = _dispatcher(_Domain(missing_consumer=True)).dispatch(
        _request(), require_host_projection=True
    )
    assert result.evidence["host_binding_consumption"] == "FAIL"


def test_mcp_host_transport_requires_current_projection_and_is_stateless():
    dispatcher = _dispatcher(_Domain())
    server = create_mcp_server(SimpleNamespace(dispatcher=dispatcher))

    async def scenario():
        async with Client(server) as client:
            tools = await client.list_tools()
            missing = await client.call_tool(
                "dispatch_task",
                {"payload": {"request_text": "inspect", "intent": "execution"}},
            )
            valid = await client.call_tool(
                "dispatch_task",
                {"payload": _request().model_dump(mode="json")},
            )
            return tools, missing, valid

    tools, missing, valid = asyncio.run(scenario())
    assert {"dispatch_task", "dispatch_host_task"} <= {tool.name for tool in tools.tools}
    assert isinstance(missing.content[0], TextContent)
    assert json.loads(missing.content[0].text)["status"] == HOST_STATE_PROJECTION_UNAVAILABLE
    assert json.loads(valid.content[0].text)["status"] == "DONE"
