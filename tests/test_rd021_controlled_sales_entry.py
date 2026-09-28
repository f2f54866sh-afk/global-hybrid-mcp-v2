"""The App tool admits one file and calls its direct command boundary."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from global_hybrid_v2.adapters.controlled_sales_entry import (
    CAPABILITY_DEBT,
    EXECUTION_FAIL,
    ControlledSalesEntry,
    EntryResult,
    OpenAIFile,
    _public_https_url,
)
from global_hybrid_v2.adapters.mcp_server import create_mcp_server

PDF = b"%PDF-1.7\nregistration fixture\n%%EOF\n"


def file(mime="application/pdf"):
    return OpenAIFile(download_url="https://files.oaiusercontent.com/file-test", file_id="file-test",
                      mime_type=mime, file_name="registration.pdf")


class Command:
    def __init__(self, result=None):
        self.result = result or EntryResult("TERMINAL", "WRITE_AND_READBACK_PASS", "已寫入並讀回。")
        self.calls = []

    def execute(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


@pytest.mark.parametrize("url", [
    "http://files.oaiusercontent.com/file-test",
    "https://127.0.0.1/file-test",
    "https://files.oaiusercontent.com.evil.example/file-test",
    "https://user:pass@files.oaiusercontent.com/file-test",
])
def test_file_download_rejects_untrusted_origin(url):
    with pytest.raises(ValueError, match="EVIDENCE_DOWNLOAD_URL_INVALID"):
        _public_https_url(url)


def test_pdf_calls_direct_command_with_exact_bytes():
    command = Command()
    entry = ControlledSalesEntry(command_handler=command, downloader=lambda _: PDF)
    outcome = entry.execute(request_text="update this company vehicle", evidence_file=[file()])
    assert outcome.terminal_disposition == "WRITE_AND_READBACK_PASS"
    assert command.calls == [{"request_text": "update this company vehicle",
                              "evidence_bytes": PDF, "mime_type": "application/pdf"}]


@pytest.mark.parametrize("files,expected", [
    ([], "EVIDENCE_FILE_REQUIRED"),
    ([file(), file()], "MULTI_EVIDENCE_BINDING_CAPABILITY_DEBT"),
    ([file("text/plain")], "EVIDENCE_MIME_UNSUPPORTED"),
])
def test_invalid_input_never_reaches_command(files, expected):
    command = Command()
    outcome = ControlledSalesEntry(command_handler=command).execute(
        request_text="update", evidence_file=files,
    )
    assert outcome.result_text == expected and not command.calls


def test_photo_is_explicit_later_capability_debt():
    command = Command()
    outcome = ControlledSalesEntry(command_handler=command, downloader=lambda _: b"photo").execute(
        request_text="update", evidence_file=[file("image/png")],
    )
    assert outcome.terminal_disposition == CAPABILITY_DEBT and not command.calls


@pytest.mark.parametrize("downloader,expected", [
    (lambda _: (_ for _ in ()).throw(OSError("secret-url")), "CONTROLLED_EXECUTION_FAILED"),
    (lambda _: b"x" * (10 * 1024 * 1024 + 1), "EVIDENCE_SIZE_INVALID"),
])
def test_download_failure_and_oversize_fail_closed(downloader, expected):
    command = Command()
    outcome = ControlledSalesEntry(command_handler=command, downloader=downloader).execute(
        request_text="update", evidence_file=[file()],
    )
    assert outcome.execution_state == EXECUTION_FAIL and outcome.result_text == expected
    assert not command.calls


def test_missing_command_is_capability_debt():
    outcome = ControlledSalesEntry(command_handler=None).execute(
        request_text="update", evidence_file=[file()],
    )
    assert outcome.terminal_disposition == CAPABILITY_DEBT


def test_mcp_schema_app_visibility_and_resource():
    command = Command()
    entry = ControlledSalesEntry(command_handler=command, downloader=lambda _: PDF)
    application = SimpleNamespace(settings=SimpleNamespace(vehicle_reconciliation_shared_secret=None))
    server = create_mcp_server(application, controlled_sales_entry=entry)
    tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    assert {"dispatch_verified_host_task", "open_ai_workbench_entry",
            "execute_controlled_sales_turn"} <= tools.keys()
    execution = tools["execute_controlled_sales_turn"]
    assert execution.meta["ui"]["visibility"] == ["app"]
    assert execution.meta["openai/fileParams"] == ["evidence_file"]
    assert set(execution.input_schema["properties"]) == {"request_text", "evidence_file"}
    file_schema = execution.input_schema["$defs"]["OpenAIFile"]
    assert set(file_schema["required"]) == {"download_url", "file_id"}
    assert set(file_schema["properties"]) == {
        "download_url", "file_id", "mime_type", "file_name",
    }
    resource_uri = tools["open_ai_workbench_entry"].meta["ui"]["resourceUri"]
    resource = list(asyncio.run(server.read_resource(resource_uri)))
    assert "execute_controlled_sales_turn" in resource[0].content
    response = asyncio.run(server.call_tool("execute_controlled_sales_turn", {
        "request_text": "update", "evidence_file": [file().model_dump(mode="json")],
    }))
    assert response.structured_content["terminal_disposition"] == "WRITE_AND_READBACK_PASS"
    assert command.calls[0]["evidence_bytes"] == PDF
