import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from mcp import Client

from global_hybrid_v2.adapters.drive_xlsx_workbench import DriveXlsxWorkbenchPort
from global_hybrid_v2.adapters.mcp_server import create_mcp_server
from global_hybrid_v2.application import create_application
from global_hybrid_v2.company_commercial_completion import CompanyCommercialCompletionHandler
from global_hybrid_v2.contracts import DomainResult, Owner
from global_hybrid_v2.trusted_workbench_intent import (
    CANONICAL_WORKBENCH_FILE_ID,
    CallerTask,
    EvidenceBindingState,
    EvidenceReceiptSigner,
    ForcedHostDispatchAdapter,
    HostBindingCapabilityDebt,
    TrustBoundaryError,
    TrustedDispatchCompiler,
    TrustedHostTaskCompiler,
    TrustedWorkbenchIntentProducer,
)
from global_hybrid_v2.workbench_mutation import XlsxWorkbenchMutationBuilder
from tests.test_mcp_server import _copy_authority_repo, _test_settings
from tests.test_rd021_completion_fence import Claims, Drive, workbook

NOW = datetime(2026, 9, 27, 8, 0, tzinfo=UTC)
KEY = b"k" * 32


def signer():
    return EvidenceReceiptSigner(key=KEY)


def receipt(**overrides):
    fields = dict(
        receipt_id="evr-1",
        task_scope="conversation:c1:turn:7",
        vehicle_instance_id="8891:S4806251",
        ai_row=13,
        binding_state=EvidenceBindingState.SAFE_ATTRIBUTABLE,
        verified_delta={"里程_Canonical": 84550},
        evidence_refs=("CURRENT_USER_PHOTO:sha256:abc",),
        issued_at=NOW - timedelta(minutes=1),
        valid_until=NOW + timedelta(minutes=4),
    )
    fields.update(overrides)
    return signer().sign(fields)


def compiler():
    return TrustedDispatchCompiler(TrustedWorkbenchIntentProducer(signer()))


def task(**overrides):
    fields = dict(request_text="update this company vehicle", intent="sales_human")
    fields.update(overrides)
    return CallerTask(**fields)


def test_positive_server_receipt_compiles_canonical_intent():
    out = compiler().compile(
        caller_task=task(),
        task_scope="conversation:c1:turn:7",
        evidence_receipt=receipt(),
        now=NOW,
    )
    assert out.company_commercial_matching is True
    assert out.trusted_workbench_intent.target_file_id == CANONICAL_WORKBENCH_FILE_ID
    assert out.trusted_workbench_intent.vehicle_instance_id == "8891:S4806251"
    assert out.trusted_workbench_intent.trusted_evidence_receipt_id == "evr-1"


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("workbench_sync_intent", {"verified_delta": {}}, "CALLER_WORKBENCH_INTENT_FORBIDDEN"),
        ("persistence_receipt", {"state": "WRITE_AND_READBACK_PASS"}, "CALLER_PERSISTENCE_RECEIPT_FORBIDDEN"),
        ("company_commercial_matching", True, "CALLER_COMPANY_COMMERCIAL_MATCH_FORBIDDEN"),
    ],
)
def test_caller_cannot_self_author_completion_state(field, value, code):
    with pytest.raises(TrustBoundaryError, match=code):
        compiler().compile(
            caller_task=task(**{field: value}),
            task_scope="conversation:c1:turn:7",
            evidence_receipt=None,
            now=NOW,
        )


def test_forged_receipt_rejected():
    r = receipt().model_copy(update={"verified_delta": {"里程_Canonical": 1}})
    with pytest.raises(TrustBoundaryError, match="UNTRUSTED"):
        compiler().compile(
            caller_task=task(), task_scope="conversation:c1:turn:7", evidence_receipt=r, now=NOW
        )


def test_stale_receipt_rejected():
    r = receipt(valid_until=NOW - timedelta(seconds=1))
    with pytest.raises(TrustBoundaryError, match="STALE"):
        compiler().compile(
            caller_task=task(), task_scope="conversation:c1:turn:7", evidence_receipt=r, now=NOW
        )


def test_cross_turn_receipt_replay_rejected():
    with pytest.raises(TrustBoundaryError, match="SCOPE_MISMATCH"):
        compiler().compile(
            caller_task=task(), task_scope="conversation:c1:turn:8", evidence_receipt=receipt(), now=NOW
        )


def test_conflict_receipt_compiles_hold_intent_not_safe_write():
    r = receipt(binding_state=EvidenceBindingState.HOLD_CONFLICT, verified_delta={})
    out = compiler().compile(
        caller_task=task(), task_scope="conversation:c1:turn:7", evidence_receipt=r, now=NOW
    )
    assert out.trusted_workbench_intent.safe_attribution is False
    assert out.trusted_workbench_intent.identity_conflict is True


def test_no_receipt_is_ordinary_nonmatching_dispatch():
    out = compiler().compile(
        caller_task=task(), task_scope="conversation:c1:turn:7", evidence_receipt=None, now=NOW
    )
    assert out.company_commercial_matching is False
    assert out.trusted_workbench_intent is None


def test_forced_dispatch_only_allows_required_dispatch_host_task():
    plan = ForcedHostDispatchAdapter(mcp_server_url="https://runtime.example/mcp").plan(
        user_input="sell this vehicle", task_scope="conversation:c1:turn:7"
    )
    tool = plan.responses_request["tools"][0]
    choice = plan.responses_request["tool_choice"]
    assert tool["allowed_tools"] == ["dispatch_verified_host_task"]
    assert choice == "required"


def test_forced_dispatch_rejects_non_https_remote_mcp():
    with pytest.raises(ValueError, match="https"):
        ForcedHostDispatchAdapter(mcp_server_url="http://localhost/mcp")


def test_receipt_signer_rejects_short_key():
    with pytest.raises(ValueError, match="32 bytes"):
        EvidenceReceiptSigner(key=b"short")

class HostResolver:
    def __init__(self):
        self.calls = 0

    def resolve(self, *, conversation_id, turn_id, request_text):
        self.calls += 1
        return {
            "current_identity_projection": {
                "projection_id": f"{conversation_id}:{turn_id}",
                "projection_version": "1", "source_id": "server-current",
                "source_version": "7", "source_state": "CURRENT",
                "source_provenance": ["HOST_CURRENT_STATE:rev-7"],
                "mapping_version": "7", "identities": {"this car": "8891:S4806251"},
                "issued_at": NOW - timedelta(minutes=1),
                "valid_until": NOW + timedelta(minutes=4),
            },
            "dialogue_binding_state": {
                "mapping_version": "7", "requested_identity_alias": "this car",
                "resolved_referent_id": "8891:S4806251",
                "issued_at": NOW - timedelta(minutes=1),
                "valid_until": NOW + timedelta(minutes=4),
            },
            "source_ref": "HOST_CURRENT_STATE:rev-7",
        }


class EvidenceProvider:
    def __init__(self, value):
        self.value = value
        self.calls = 0

    def resolve(self, *, task_scope, request_text):
        self.calls += 1
        return self.value


class RecordingDispatcher:
    def __init__(self):
        self.calls = []

    def dispatch(self, request, **kwargs):
        self.calls.append((request, kwargs))
        return DomainResult(owner=Owner.GLOBAL, status="CALLED")


def call_mcp(application, name, payload):
    server = create_mcp_server(application)

    async def run():
        async with Client(server) as client:
            return await client.call_tool(name, {"payload": payload})

    response = asyncio.run(run())
    assert response.is_error is False
    return json.loads(response.content[0].text)


@pytest.mark.parametrize(
    "field,value",
    [
        ("workbench_sync_intent", {"verified_delta": {}}),
        ("persistence_receipt", {"state": "WRITE_AND_READBACK_PASS"}),
        ("company_commercial_matching", True),
        ("verified_delta", {"里程_Canonical": 84550}),
    ],
)
def test_raw_host_dispatch_never_accepts_self_authored_workbench_state(field, value):
    dispatcher = RecordingDispatcher()
    app = SimpleNamespace(dispatcher=dispatcher)
    output = call_mcp(
        app, "dispatch_host_task",
        {"request_text": "vehicle", "intent": "sales_human", field: value},
    )
    assert output["status"] == "NO_SERIALIZE / EXECUTION_FAIL"
    assert not dispatcher.calls


def test_verified_host_tool_without_compiler_fails_closed():
    dispatcher = RecordingDispatcher()
    app = SimpleNamespace(dispatcher=dispatcher, trusted_host_task_compiler=None)
    output = call_mcp(app, "dispatch_verified_host_task", {
        "conversation_id": "c1", "turn_id": "7",
        "task": {"request_text": "vehicle", "intent": "sales_human"},
    })
    assert output["blocker"] == "TRUSTED_HOST_BINDING_UNAVAILABLE"
    assert not dispatcher.calls


def test_verified_host_tool_resolves_trusted_receipt_before_dispatch():
    now = datetime.now(UTC)
    signed = signer().sign({
        "receipt_id": "live-receipt", "task_scope": "conversation:c1:turn:7",
        "vehicle_instance_id": "8891:S4806251", "ai_row": 13,
        "binding_state": EvidenceBindingState.SAFE_ATTRIBUTABLE,
        "verified_delta": {"里程_Canonical": 84550},
        "evidence_refs": ("fixture:photo",),
        "issued_at": now - timedelta(seconds=10),
        "valid_until": now + timedelta(minutes=4),
    })

    class FreshHostResolver(HostResolver):
        def resolve(self, *, conversation_id, turn_id, request_text):
            data = super().resolve(
                conversation_id=conversation_id, turn_id=turn_id, request_text=request_text,
            )
            for key in ("current_identity_projection", "dialogue_binding_state"):
                data[key]["issued_at"] = now - timedelta(seconds=10)
                data[key]["valid_until"] = now + timedelta(minutes=4)
            return data

    dispatcher = RecordingDispatcher()
    host, evidence = FreshHostResolver(), EvidenceProvider(signed)
    compiled = TrustedHostTaskCompiler(
        dispatch_compiler=compiler(), host_state_resolver=host, evidence_provider=evidence,
    )
    app = SimpleNamespace(dispatcher=dispatcher, trusted_host_task_compiler=compiled)
    output = call_mcp(app, "dispatch_verified_host_task", {
        "conversation_id": "c1", "turn_id": "7",
        "task": {"request_text": "vehicle", "intent": "sales_human"},
    })
    assert output["status"] == "CALLED"
    assert host.calls == evidence.calls == len(dispatcher.calls) == 1
    request, kwargs = dispatcher.calls[0]
    assert request.workbench_sync_intent is None
    trusted = kwargs["trusted_host_dispatch"]
    assert trusted.trusted_workbench_intent.target_file_id == CANONICAL_WORKBENCH_FILE_ID
    assert trusted.trusted_workbench_intent.trusted_evidence_receipt_id == "live-receipt"


def test_forged_receipt_cannot_reach_dispatcher():
    signed = receipt().model_copy(update={"verified_delta": {"里程_Canonical": 1}})
    dispatcher = RecordingDispatcher()
    compiled = TrustedHostTaskCompiler(
        dispatch_compiler=compiler(), host_state_resolver=HostResolver(),
        evidence_provider=EvidenceProvider(signed),
    )
    app = SimpleNamespace(dispatcher=dispatcher, trusted_host_task_compiler=compiled)
    output = call_mcp(app, "dispatch_verified_host_task", {
        "conversation_id": "c1", "turn_id": "7",
        "task": {"request_text": "vehicle", "intent": "sales_human"},
    })
    assert output["blocker"] == "UNTRUSTED_WORKBENCH_EVIDENCE_RECEIPT"
    assert not dispatcher.calls


@pytest.mark.parametrize("problem", ["stale", "wrong_turn"])
def test_stale_or_wrong_turn_receipt_cannot_reach_dispatcher(problem):
    now = datetime.now(UTC)
    fields = {
        "receipt_id": "scope-receipt",
        "task_scope": "conversation:c1:turn:8" if problem == "wrong_turn" else "conversation:c1:turn:7",
        "vehicle_instance_id": "8891:S4806251", "ai_row": 13,
        "binding_state": EvidenceBindingState.SAFE_ATTRIBUTABLE,
        "verified_delta": {"里程_Canonical": 84550},
        "issued_at": now - timedelta(minutes=3),
        "valid_until": now - timedelta(minutes=1) if problem == "stale" else now + timedelta(minutes=1),
    }
    dispatcher = RecordingDispatcher()
    compiled = TrustedHostTaskCompiler(
        dispatch_compiler=compiler(), host_state_resolver=HostResolver(),
        evidence_provider=EvidenceProvider(signer().sign(fields)),
    )
    app = SimpleNamespace(dispatcher=dispatcher, trusted_host_task_compiler=compiled)
    output = call_mcp(app, "dispatch_verified_host_task", {
        "conversation_id": "c1", "turn_id": "7",
        "task": {"request_text": "vehicle", "intent": "sales_human"},
    })
    assert output["status"] == "NO_SERIALIZE / EXECUTION_FAIL"
    assert not dispatcher.calls


def test_verified_host_tool_rejects_privileged_caller_fields_before_provider_reads():
    dispatcher = RecordingDispatcher()
    host, evidence = HostResolver(), EvidenceProvider(None)
    compiled = TrustedHostTaskCompiler(
        dispatch_compiler=compiler(), host_state_resolver=host, evidence_provider=evidence,
    )
    app = SimpleNamespace(dispatcher=dispatcher, trusted_host_task_compiler=compiled)
    output = call_mcp(app, "dispatch_verified_host_task", {
        "conversation_id": "c1", "turn_id": "7",
        "task": {"request_text": "vehicle", "intent": "sales_human",
                 "workbench_sync_intent": {"verified_delta": {"里程_Canonical": 84550}}},
    })
    assert output["blocker"] == "CALLER_WORKBENCH_INTENT_FORBIDDEN"
    assert host.calls == evidence.calls == len(dispatcher.calls) == 0


@pytest.mark.parametrize("corrupt", [False, True])
def test_verified_host_tool_reaches_exact_preimage_write_and_receipt(tmp_path, corrupt):
    now = datetime.now(UTC)
    signed = signer().sign({
        "receipt_id": "e2e-receipt", "task_scope": "conversation:c1:turn:7",
        "vehicle_instance_id": "8891:S4806251", "ai_row": 13,
        "binding_state": EvidenceBindingState.SAFE_ATTRIBUTABLE,
        "verified_delta": {"里程_Canonical": 84550},
        "evidence_refs": ("fixture:photo",),
        "issued_at": now - timedelta(seconds=10),
        "valid_until": now + timedelta(minutes=4),
    })

    class FreshHostResolver(HostResolver):
        def resolve(self, *, conversation_id, turn_id, request_text):
            data = super().resolve(
                conversation_id=conversation_id, turn_id=turn_id, request_text=request_text,
            )
            for key in ("current_identity_projection", "dialogue_binding_state"):
                data[key]["issued_at"] = now - timedelta(seconds=10)
                data[key]["valid_until"] = now + timedelta(minutes=4)
            return data

    drive = Drive(workbook())
    drive.corrupt = corrupt
    writer = DriveXlsxWorkbenchPort(
        file_id=CANONICAL_WORKBENCH_FILE_ID, drive=drive, claims=Claims(),
    )
    completion = CompanyCommercialCompletionHandler(
        writer=writer, builder=XlsxWorkbenchMutationBuilder(),
    )
    compiler_binding = TrustedHostTaskCompiler(
        dispatch_compiler=compiler(), host_state_resolver=FreshHostResolver(),
        evidence_provider=EvidenceProvider(signed),
    )
    application = create_application(
        repo_root=_copy_authority_repo(tmp_path), settings=_test_settings(),
        company_commercial_completion_handler=completion,
        trusted_host_task_compiler=compiler_binding,
    )
    result = call_mcp(application, "dispatch_verified_host_task", {
        "conversation_id": "c1", "turn_id": "7",
        "task": {"request_text": "update this company vehicle", "intent": "sales_human"},
    })
    assert result["status"] == (
        "NO_SERIALIZE / EXECUTION_FAIL" if corrupt else "COMPANY_COMMERCIAL_DELTA_VERIFIED"
    )
    assert result["persistence_receipt"]["state"] == (
        "HOLD_CONFLICT" if corrupt else "WRITE_AND_READBACK_PASS"
    )
    assert drive.writes == 1


def test_server_resolves_host_state_and_evidence_outside_caller_payload():
    host = HostResolver()
    evidence = EvidenceProvider(receipt())
    c = TrustedHostTaskCompiler(
        dispatch_compiler=compiler(), host_state_resolver=host, evidence_provider=evidence
    )
    out = c.compile(caller_task=task(), conversation_id="c1", turn_id="7", now=NOW)
    assert out.task_scope == "conversation:c1:turn:7"
    assert out.host_state.source_ref == "HOST_CURRENT_STATE:rev-7"
    assert out.company_commercial_matching is True
    assert host.calls == 1 and evidence.calls == 1


def test_missing_host_resolver_is_capability_debt_not_model_fallback():
    c = TrustedHostTaskCompiler(
        dispatch_compiler=compiler(), host_state_resolver=None, evidence_provider=EvidenceProvider(None)
    )
    with pytest.raises(HostBindingCapabilityDebt, match="HOST_CURRENT_STATE_RESOLVER_UNAVAILABLE"):
        c.compile(caller_task=task(), conversation_id="c1", turn_id="7", now=NOW)


def test_missing_evidence_provider_is_capability_debt_not_caller_intent_fallback():
    c = TrustedHostTaskCompiler(
        dispatch_compiler=compiler(), host_state_resolver=HostResolver(), evidence_provider=None
    )
    with pytest.raises(HostBindingCapabilityDebt, match="TRUSTED_EVIDENCE_PROVIDER_UNAVAILABLE"):
        c.compile(caller_task=task(), conversation_id="c1", turn_id="7", now=NOW)
