"""No-network qualification of the PDF-only structured Responses interpreter."""
from __future__ import annotations

import base64
import json
from types import SimpleNamespace

import pytest

from global_hybrid_v2.adapters.drive_xlsx_workbench import WorkbenchCapabilityDebt, WorkbenchConflict
from global_hybrid_v2.adapters.openai_registration_interpreter import (
    REGISTRATION_OUTPUT_SCHEMA,
    OpenAIRegistrationEvidenceInterpreter,
)
from global_hybrid_v2.settings import Settings
from tests.fixtures.rd021_synthetic_registration import synthetic_registration_pdf
from tests.test_rd021_direct_app_command import VIN_A, command

PDF = synthetic_registration_pdf()


def payload(*, hints=None, delta=None):
    values = {name: None for name in REGISTRATION_OUTPUT_SCHEMA["properties"]["verified_delta"]["required"]}
    values.update(delta or {})
    identity = {name: None for name in REGISTRATION_OUTPUT_SCHEMA["properties"]["identity_hints"]["required"]}
    identity.update(hints or {})
    return {"identity_hints": identity, "verified_delta": values}


class FakeResponses:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.result


def interpreter(result=None, error=None, *, model="explicit-pdf-capable-model"):
    transport = FakeResponses(result, error)
    settings = Settings(registration_interpreter_model=model, _env_file=None)
    return OpenAIRegistrationEvidenceInterpreter(settings=settings, client=SimpleNamespace(
        responses=transport,
    )), transport


def response(data):
    return {"status": "completed", "output_text": json.dumps(data), "output": []}


def test_exact_pdf_high_detail_and_strict_structured_output_enriches_selected_bmw():
    data = payload(hints={"year": "2018", "make": "BMW", "model": "318I"},
                   delta={"VIN/車身號碼": VIN_A, "車牌": "TEST-1234",
                          "排氣量_Canonical": "1998", "燃料_Canonical": "gasoline",
                          "出廠年月": "2018-06"})
    live, transport = interpreter(response(data))
    handler, drive, _ = command(blank_identity=True)
    handler.resolver.interpreter = live
    token = handler.list_candidates()[0]["opaque_selection_token"]
    result = handler.execute(request_text="同步這台公司車行照", evidence_bytes=PDF,
                             mime_type="application/pdf", target_selection_token=token)
    assert result.terminal_disposition == "WRITE_AND_READBACK_PASS"
    assert drive.writes == 1
    assert b"8891:S4806251" in drive.payload
    for value in (VIN_A, "TEST-1234", "1998", "gasoline", "2018-06"):
        assert value.encode() in drive.payload
    args = transport.calls[0]
    assert args["model"] == "explicit-pdf-capable-model"
    assert args["store"] is False and args["tools"] == [] and args["tool_choice"] == "none"
    file_part = args["input"][1]["content"][0]
    assert file_part["type"] == "input_file" and file_part["filename"] == "registration.pdf"
    assert file_part["detail"] == "high"
    assert base64.b64decode(file_part["file_data"].split(",", 1)[1]) == PDF
    assert args["text"]["format"]["strict"] is True
    assert args["text"]["format"]["schema"] == REGISTRATION_OUTPUT_SCHEMA


@pytest.mark.parametrize("extra", [
    {"vehicle_instance_id": "forged"}, {"ai_row": "13"}, {"成本_Canonical": "1"},
])
def test_privileged_or_protected_output_is_capability_debt(extra):
    data = payload(delta={"VIN/車身號碼": VIN_A})
    data["verified_delta"].update(extra)
    live, _ = interpreter(response(data))
    with pytest.raises(WorkbenchCapabilityDebt, match="EVIDENCE_INTERPRETER_UNAVAILABLE"):
        live.interpret(request_text="x", evidence_bytes=PDF, mime_type="application/pdf")


@pytest.mark.parametrize("field,value", [
    ("VIN/車身號碼", "INVALID"), ("車牌", "!!!"),
])
def test_existing_resolver_format_guards_hold_without_write(field, value):
    data = payload(delta={field: value})
    live, _ = interpreter(response(data))
    handler, drive, _ = command(blank_identity=True)
    handler.resolver.interpreter = live
    token = handler.list_candidates()[0]["opaque_selection_token"]
    result = handler.execute(request_text="x", evidence_bytes=PDF,
                             mime_type="application/pdf", target_selection_token=token)
    assert result.terminal_disposition == "HOLD_CONFLICT" and drive.writes == 0


def test_empty_evidence_proposes_no_write():
    live, _ = interpreter(response(payload()))
    handler, drive, _ = command(blank_identity=True)
    handler.resolver.interpreter = live
    token = handler.list_candidates()[0]["opaque_selection_token"]
    result = handler.execute(request_text="x", evidence_bytes=PDF,
                             mime_type="application/pdf", target_selection_token=token)
    assert result.terminal_disposition == "NO_DELTA" and drive.writes == 0


@pytest.mark.parametrize("result,error", [
    ({"status": "completed", "output_text": "", "output": [
        {"content": [{"type": "refusal", "refusal": "cannot process"}]},
    ]}, None),
    ({"status": "completed", "output_text": "{broken", "output": []}, None),
    (None, RuntimeError("upstream failure")),
    ({"status": "incomplete", "output_text": "{}", "output": []}, None),
])
def test_refusal_malformed_api_error_and_incomplete_are_capability_debt(result, error):
    live, _ = interpreter(result, error)
    with pytest.raises(WorkbenchCapabilityDebt, match="EVIDENCE_INTERPRETER_UNAVAILABLE"):
        live.interpret(request_text="x", evidence_bytes=PDF, mime_type="application/pdf")


def test_missing_model_or_credential_and_unsupported_pdf_fail_closed(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GLOBAL_OPENAI_API_KEY", raising=False)
    for model in ("", "explicit-pdf-capable-model"):
        live = OpenAIRegistrationEvidenceInterpreter(settings=Settings(
            registration_interpreter_model=model, _env_file=None,
        ))
        with pytest.raises(WorkbenchCapabilityDebt, match="EVIDENCE_INTERPRETER_UNAVAILABLE"):
            live.interpret(request_text="x", evidence_bytes=PDF, mime_type="application/pdf")
    configured, transport = interpreter(response(payload()))
    with pytest.raises(WorkbenchConflict, match="HOLD_DOCUMENT_PREIMAGE_INVALID"):
        configured.interpret(request_text="x", evidence_bytes=b"not a PDF", mime_type="text/plain")
    assert not transport.calls


def test_dedicated_model_setting_uses_exact_environment_name(monkeypatch):
    monkeypatch.setenv("GLOBAL_REGISTRATION_INTERPRETER_MODEL", "configured-vision-model")
    assert Settings(_env_file=None).registration_interpreter_model == "configured-vision-model"
