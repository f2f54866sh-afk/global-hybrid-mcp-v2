"""N3A app entry must consume N2 and return only server-owned terminals."""
from __future__ import annotations

import asyncio
import base64
import json
from types import SimpleNamespace

import pytest

from global_hybrid_v2.adapters.controlled_responses import (
    ControlledSalesIngress,
    ForcedHostDispatchAdapter,
)
from global_hybrid_v2.adapters.controlled_sales_entry import (
    CAPABILITY_DEBT,
    EXECUTION_FAIL,
    ControlledSalesEntry,
    OpenAIFile,
    _public_https_url,
)
from global_hybrid_v2.adapters.controlled_sales_executor import ControlledSalesCompletionExecutor
from global_hybrid_v2.adapters.mcp_server import create_mcp_server
from global_hybrid_v2.contracts import PersistenceDisposition
from global_hybrid_v2.ingress_admission import IngressTaskClass
from tests.test_rd021_controlled_sales_executor import TEXT, FakeResponses, call, terminal
from tests.test_rd021_ingress_admission import Classifier, ingress_codec
from tests.test_rd021_media_admission import kit as kit
from tests.test_rd021_media_admission import photo


def file(mime="image/png"):
    return OpenAIFile(download_url="https://files.oaiusercontent.com/file-test", file_id="file-test",
                      mime_type=mime, file_name="evidence.png")


@pytest.mark.parametrize("url", [
    "http://files.oaiusercontent.com/file-test",
    "https://127.0.0.1/file-test",
    "https://files.oaiusercontent.com.evil.example/file-test",
    "https://user:pass@files.oaiusercontent.com/file-test",
])
def test_file_download_rejects_untrusted_origin(url):
    with pytest.raises(ValueError, match="EVIDENCE_DOWNLOAD_URL_INVALID"):
        _public_https_url(url)


def entry(kit, *, state=PersistenceDisposition.WRITE_AND_READBACK_PASS,
          items=None, downloader=None):
    transport = FakeResponses(items if items is not None else [call(terminal(state))])
    ingress = ControlledSalesIngress(
        classifier=Classifier(IngressTaskClass.COMPANY_COMMERCIAL_MATCHING),
        token_codec=ingress_codec(),
        responses_adapter=ForcedHostDispatchAdapter(mcp_server_url="https://mcp.example/mcp"),
        media_gate=kit[2],
    )
    executor = ControlledSalesCompletionExecutor(ingress=ingress, responses=transport)
    return ControlledSalesEntry(executor=executor, media_issuer=kit[1],
                                downloader=downloader or (lambda _: photo())), transport


@pytest.fixture(autouse=True)
def fixed_server_turn(monkeypatch):
    values = iter(["controlled-conversation", "controlled-turn"] * 20)
    monkeypatch.setattr("global_hybrid_v2.adapters.controlled_sales_entry.uuid4",
                        lambda: SimpleNamespace(hex=next(values)))


def test_one_image_releases_only_after_n2_receipt(kit):
    controlled, transport = entry(kit)
    outcome = controlled.execute(request_text=TEXT, evidence_file=[file()])
    assert outcome.terminal_disposition == "WRITE_AND_READBACK_PASS"
    assert outcome.result_text == "已完成並同步 AI 車源表。"
    content = transport.requests[0]["input"][0]["content"]
    assert content[1]["type"] == "input_image"
    assert content[1]["image_url"].startswith("data:image/png;base64,")
    assert "download_url" not in json.dumps(transport.requests[0])


def test_optional_mime_can_be_resolved_from_exact_image_bytes(kit):
    controlled, _ = entry(kit)
    outcome = controlled.execute(request_text=TEXT, evidence_file=[file(None)])
    assert outcome.terminal_disposition == "WRITE_AND_READBACK_PASS"


def test_one_pdf_preserves_exact_preimage_in_n2_request(kit):
    raw = b"%PDF-1.7\nregistration fixture\n%%EOF\n"
    controlled, transport = entry(kit, downloader=lambda _: raw)
    outcome = controlled.execute(request_text=TEXT, evidence_file=[file("application/pdf")])
    assert outcome.terminal_disposition == "WRITE_AND_READBACK_PASS"
    content = transport.requests[0]["input"][0]["content"]
    assert content[1]["type"] == "input_file"
    assert content[1]["file_data"].startswith("data:application/pdf;base64,")
    assert base64.b64decode(content[1]["file_data"].split(",", 1)[1]) == raw
    assert "download_url" not in json.dumps(transport.requests[0])


def test_invalid_pdf_bytes_fail_before_responses(kit):
    controlled, transport = entry(kit, downloader=lambda _: b"not-a-pdf")
    outcome = controlled.execute(request_text=TEXT, evidence_file=[file("application/pdf")])
    assert outcome.execution_state == EXECUTION_FAIL
    assert not transport.requests


@pytest.mark.parametrize("files,expected", [
    ([], "EVIDENCE_FILE_REQUIRED"),
    ([file(), file()], "MULTI_EVIDENCE_BINDING_CAPABILITY_DEBT"),
    ([file("text/plain")], "EVIDENCE_MIME_UNSUPPORTED"),
])
def test_input_cardinality_and_mime_fail_before_responses(kit, files, expected):
    controlled, transport = entry(kit)
    outcome = controlled.execute(request_text=TEXT, evidence_file=files)
    assert outcome.result_text == expected
    assert not transport.requests


@pytest.mark.parametrize("downloader,expected", [
    (lambda _: (_ for _ in ()).throw(OSError("secret-url")), "CONTROLLED_EXECUTION_FAILED"),
    (lambda _: b"x" * (10 * 1024 * 1024 + 1), "EVIDENCE_SIZE_INVALID"),
])
def test_download_or_size_failure_never_calls_n2(kit, downloader, expected):
    controlled, transport = entry(kit, downloader=downloader)
    outcome = controlled.execute(request_text=TEXT, evidence_file=[file()])
    assert outcome.execution_state == EXECUTION_FAIL and outcome.result_text == expected
    assert not transport.requests


@pytest.mark.parametrize("items", [[], [call("not-json")]])
def test_n2_missing_call_or_malformed_receipt_blocks_entry(kit, items):
    controlled, _ = entry(kit, items=items)
    outcome = controlled.execute(request_text=TEXT, evidence_file=[file()])
    assert outcome.execution_state == EXECUTION_FAIL
    assert "已完成" not in outcome.result_text


@pytest.mark.parametrize("state", [
    PersistenceDisposition.NO_DELTA,
    PersistenceDisposition.PERSISTENCE_CAPABILITY_DEBT,
    PersistenceDisposition.HOLD_CONFLICT,
])
def test_nonwrite_terminal_never_returns_model_success(kit, state):
    controlled, _ = entry(kit, state=state)
    outcome = controlled.execute(request_text=TEXT, evidence_file=[file()])
    assert outcome.terminal_disposition == state.value
    assert "已完成並同步" not in outcome.result_text


def test_unbound_entry_is_capability_debt():
    outcome = ControlledSalesEntry(executor=None, media_issuer=None).execute(
        request_text=TEXT, evidence_file=[file()],
    )
    assert outcome.terminal_disposition == CAPABILITY_DEBT


def test_mcp_app_registration_schema_visibility_and_resource(kit):
    controlled, _ = entry(kit)
    application = SimpleNamespace(settings=SimpleNamespace(vehicle_reconciliation_shared_secret=None))
    server = create_mcp_server(application, controlled_sales_entry=controlled)
    tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    assert {"dispatch_verified_host_task", "open_ai_workbench_entry",
            "execute_controlled_sales_turn"} <= tools.keys()
    execution = tools["execute_controlled_sales_turn"]
    assert execution.meta["ui"]["visibility"] == ["app"]
    assert execution.meta["openai/fileParams"] == ["evidence_file"]
    assert set(execution.input_schema["properties"]) == {"request_text", "evidence_file"}
    assert "evidence_file" in execution.input_schema["required"]
    file_schema = execution.input_schema["$defs"]["OpenAIFile"]
    assert set(file_schema["properties"]) == {
        "download_url", "file_id", "mime_type", "file_name",
    }
    assert set(file_schema["required"]) == {"download_url", "file_id"}
    assert execution.input_schema["properties"]["evidence_file"]["items"] == {
        "$ref": "#/$defs/OpenAIFile",
    }
    assert tools["open_ai_workbench_entry"].meta["ui"]["resourceUri"].startswith("ui://")
    resources = asyncio.run(server.list_resources())
    assert any(item.mime_type == "text/html;profile=mcp-app" for item in resources)
    rendered = list(asyncio.run(server.read_resource(
        tools["open_ai_workbench_entry"].meta["ui"]["resourceUri"],
    )))
    assert "execute_controlled_sales_turn" in rendered[0].content
    response = asyncio.run(server.call_tool(
        "execute_controlled_sales_turn",
        {"request_text": TEXT, "evidence_file": [file().model_dump(mode="json")]},
    ))
    assert response.structured_content["terminal_disposition"] == "WRITE_AND_READBACK_PASS"
