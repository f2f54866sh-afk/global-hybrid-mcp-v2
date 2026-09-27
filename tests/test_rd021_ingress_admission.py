"""Ingress classification precedes evidence and transport auth owns turn identity."""
from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx2
import pytest
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

from global_hybrid_v2.adapters.controlled_responses import (
    ControlledSalesIngress,
    ForcedHostDispatchAdapter,
    ServerTurnContext,
)
from global_hybrid_v2.adapters.mcp_server import (
    create_mcp_server,
    dispatch_verified_host_task_from_headers,
)
from global_hybrid_v2.ingress_admission import (
    IngressTaskClass,
    IngressTurnTokenCodec,
    InMemoryNonceClaimStore,
)
from global_hybrid_v2.trusted_workbench_intent import TrustedHostTaskCompiler
from tests.test_rd021_trusted_host_binding import (
    EVIDENCE_DIGEST,
    EvidenceProvider,
    HostResolver,
    RecordingDispatcher,
    call_mcp,
    compiler,
    ingress_codec,
    signed_for,
)


class Classifier:
    def __init__(self, task_class: IngressTaskClass):
        self.task_class = task_class
        self.calls = 0

    def classify(self, *, request_text: str, evidence_digest: str) -> IngressTaskClass:
        self.calls += 1
        assert request_text
        assert len(evidence_digest) == 64
        return self.task_class


def issue(codec, *, task_class=IngressTaskClass.COMPANY_COMMERCIAL_MATCHING,
          request_text="update this vehicle", evidence_digest=EVIDENCE_DIGEST, now=None):
    return codec.issue(
        conversation_id="c1", turn_id="7", task_class=task_class,
        request_text=request_text, intent="sales_human", evidence_digest=evidence_digest,
        now=now,
    )


def dispatch_with(codec, provider, *, task_class=IngressTaskClass.COMPANY_COMMERCIAL_MATCHING,
                  request_text="update this vehicle", task=None, token=None):
    dispatcher = RecordingDispatcher()
    compiler_binding = TrustedHostTaskCompiler(
        dispatch_compiler=compiler(), host_state_resolver=HostResolver(),
        evidence_provider=provider,
    )
    app = SimpleNamespace(
        dispatcher=dispatcher, trusted_host_task_compiler=compiler_binding,
        ingress_token_codec=codec,
    )
    raw = token or issue(codec, task_class=task_class, request_text=request_text)
    result = dispatch_verified_host_task_from_headers(
        app,
        {"task": task or {"request_text": request_text, "intent": "sales_human"}},
        {"Authorization": f"Bearer {raw}"},
    )
    return result, dispatcher


def test_controlled_ingress_classifies_before_model_and_sends_raw_media_inputs():
    codec = ingress_codec()
    classifier = Classifier(IngressTaskClass.COMPANY_COMMERCIAL_MATCHING)
    ingress = ControlledSalesIngress(
        classifier=classifier, token_codec=codec,
        responses_adapter=ForcedHostDispatchAdapter(mcp_server_url="https://mcp.example/endpoint"),
    )
    evidence = b"original-photo-bytes"
    image = {"type": "input_image", "image_url": "data:image/jpeg;base64,YQ=="}
    plan = ingress.plan(
        turn=ServerTurnContext("c1", "7"), request_text="update this vehicle",
        intent="sales_human", raw_evidence=evidence, media_inputs=(image,),
    )
    assert classifier.calls == 1
    assert plan.responses_request["tool_choice"] == "required"
    tool = plan.responses_request["tools"][0]
    assert tool["allowed_tools"] == ["dispatch_verified_host_task"]
    assert plan.responses_request["input"][0]["content"][1] == image
    binding = codec.verify_authorization(
        f"Bearer {tool['authorization']}",
        request_text="update this vehicle", intent="sales_human",
    )
    assert binding.task_class is IngressTaskClass.COMPANY_COMMERCIAL_MATCHING
    assert binding.evidence_digest == hashlib.sha256(evidence).hexdigest()


def test_classifier_missing_fails_before_model_plan():
    ingress = ControlledSalesIngress(
        classifier=None, token_codec=ingress_codec(),
        responses_adapter=ForcedHostDispatchAdapter(mcp_server_url="https://mcp.example/endpoint"),
    )
    with pytest.raises(RuntimeError, match="SERVER_TASK_CLASSIFIER_UNAVAILABLE"):
        ingress.plan(
            turn=ServerTurnContext("c1", "7"), request_text="vehicle",
            intent="sales_human", raw_evidence=b"",
        )


@pytest.mark.parametrize("mode", ["none", "unavailable", "exception"])
def test_matching_missing_evidence_never_becomes_ordinary(mode):
    class BrokenProvider:
        def resolve(self, **kwargs):
            raise RuntimeError("offline")

    provider = (
        None if mode == "unavailable"
        else BrokenProvider() if mode == "exception"
        else EvidenceProvider(None)
    )
    result, dispatcher = dispatch_with(ingress_codec(), provider)
    assert result["status"] == "NO_SERIALIZE / EXECUTION_FAIL"
    assert result["persistence_receipt"]["state"] == "PERSISTENCE_CAPABILITY_DEBT"
    assert not dispatcher.calls


def test_matching_invalid_receipt_and_identity_conflict_hold():
    invalid = signed_for("update this vehicle").model_copy(
        update={"evidence_digest": "0" * 64},
    )
    result, dispatcher = dispatch_with(ingress_codec(), EvidenceProvider(invalid))
    assert result["persistence_receipt"]["state"] == "HOLD_CONFLICT"
    assert not dispatcher.calls

    sheet_only = signed_for(
        "update this vehicle", identity_sources=("COMPANY_SHEET_READ_ONLY",),
    )
    result, dispatcher = dispatch_with(ingress_codec(), EvidenceProvider(sheet_only))
    assert result["blocker"] == "DURABLE_IDENTITY_PROVENANCE_MISSING"
    assert result["persistence_receipt"]["state"] == "HOLD_CONFLICT"
    assert not dispatcher.calls


def test_caller_matching_and_host_authority_fields_rejected():
    payload = {"request_text": "update this vehicle", "intent": "sales_human",
               "company_commercial_matching": True}
    result, dispatcher = dispatch_with(ingress_codec(), EvidenceProvider(None), task=payload)
    assert result["persistence_receipt"]["state"] == "HOLD_CONFLICT"
    assert not dispatcher.calls

    result, dispatcher = dispatch_with(ingress_codec(), EvidenceProvider(None), task={
        "request_text": "update this vehicle", "intent": "sales_human",
        "current_identity_projection": {"source_id": "caller"},
    })
    assert result["persistence_receipt"]["state"] == "HOLD_CONFLICT"
    assert not dispatcher.calls


def test_model_cannot_supply_conversation_or_turn_in_tool_payload():
    codec = ingress_codec()
    app = SimpleNamespace(ingress_token_codec=codec, trusted_host_task_compiler=None)
    result = dispatch_verified_host_task_from_headers(
        app,
        {"conversation_id": "caller", "turn_id": "caller",
         "task": {"request_text": "vehicle", "intent": "sales_human"}},
        {"Authorization": f"Bearer {issue(codec, request_text='vehicle')}"},
    )
    assert result["blocker"] == "HOST_TASK_PAYLOAD_INVALID"


def test_missing_authorization_from_mcp_context_rejected():
    app = SimpleNamespace(
        ingress_token_codec=ingress_codec(), trusted_host_task_compiler=None,
    )
    result = call_mcp(app, "dispatch_verified_host_task", {
        "task": {"request_text": "vehicle", "intent": "sales_human"},
    })
    assert result["blocker"] == "INGRESS_AUTHORIZATION_MISSING"


def test_http_mcp_context_reads_transport_authorization():
    codec = ingress_codec()
    app = SimpleNamespace(
        ingress_token_codec=codec, trusted_host_task_compiler=None,
    )
    server = create_mcp_server(app)
    asgi = server.streamable_http_app(
        stateless_http=True, json_response=True, host="testserver",
    )
    token = issue(codec, request_text="vehicle")

    async def run():
        async with server.session_manager.run():
            async with httpx2.AsyncClient(
                transport=httpx2.ASGITransport(app=asgi),
                base_url="http://testserver",
                headers={"Authorization": f"Bearer {token}"},
            ) as http:
                async with streamable_http_client(
                    "http://testserver/mcp", http_client=http,
                ) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        return await session.call_tool(
                            "dispatch_verified_host_task",
                            {"payload": {"task": {
                                "request_text": "vehicle", "intent": "sales_human",
                            }}},
                        )

    response = asyncio.run(run())
    result = json.loads(response.content[0].text)
    assert result["blocker"] == "TRUSTED_HOST_BINDING_UNAVAILABLE"
    assert result["persistence_receipt"]["state"] == "PERSISTENCE_CAPABILITY_DEBT"


@pytest.mark.parametrize("problem", ["invalid", "expired", "wrong_audience", "request_digest"])
def test_invalid_transport_token_rejected(problem):
    codec = ingress_codec()
    token = issue(codec, request_text="update this vehicle",
                  now=datetime.now(UTC) - timedelta(minutes=6) if problem == "expired" else None)
    if problem == "invalid":
        token = token[:-1] + ("0" if token[-1] != "0" else "1")
    if problem == "wrong_audience":
        other = IngressTurnTokenCodec(
            key=b"t" * 32, audience="different", server="global-hybrid-v2",
            replay_store=InMemoryNonceClaimStore(),
        )
        token = issue(other)
    result, dispatcher = dispatch_with(
        codec, EvidenceProvider(None), token=token,
        task={"request_text": "changed" if problem == "request_digest" else "update this vehicle",
              "intent": "sales_human"},
    )
    assert result["status"] == "NO_SERIALIZE / EXECUTION_FAIL"
    assert "persistence_receipt" not in result
    assert not dispatcher.calls


def test_replayed_transport_token_blocks_before_provider():
    codec = ingress_codec()
    token = issue(codec)
    first, _ = dispatch_with(codec, EvidenceProvider(None), token=token)
    second, dispatcher = dispatch_with(codec, EvidenceProvider(None), token=token)
    assert first["persistence_receipt"]["state"] == "PERSISTENCE_CAPABILITY_DEBT"
    assert second["blocker"] == "INGRESS_TOKEN_REPLAYED"
    assert not dispatcher.calls


def test_nonmatching_ordinary_skips_evidence_provider():
    codec = ingress_codec()
    result, dispatcher = dispatch_with(
        codec, provider=None, task_class=IngressTaskClass.ORDINARY,
    )
    assert result["status"] == "CALLED"
    assert "persistence_receipt" in result  # The test dispatcher serializes its optional field.
    assert result["persistence_receipt"] is None
    assert len(dispatcher.calls) == 1
