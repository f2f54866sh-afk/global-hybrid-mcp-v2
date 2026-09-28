"""PDF-only Responses interpreter; it proposes evidence fields but never selects or writes a vehicle."""
from __future__ import annotations

import base64
import json
from typing import Any

from openai import OpenAI

from global_hybrid_v2.adapters.drive_xlsx_workbench import (
    WorkbenchCapabilityDebt,
    WorkbenchConflict,
)
from global_hybrid_v2.controlled_workbench_command import IDENTITY_HINT_FIELDS, REGISTRATION_FIELDS
from global_hybrid_v2.settings import Settings

_SYSTEM = (
    "Read only the attached vehicle registration PDF. Extract only facts visibly supported "
    "by that document. Use null for unknown, absent, or visually uncertain values. Never guess "
    "trim, market, vehicle identity, or VIN characters. Do not use the user's task text as "
    "evidence for a field absent from the document. Distinguish ambiguous characters by "
    "leaving the field null. Descriptive similarity is not vehicle identity authority. "
    "Return identity_hints for comparison and verified_delta for proposed registration facts only. "
    "Do not decide which workbook vehicle receives the facts or whether any write is permitted."
)


def _object_schema(names: frozenset[str]) -> dict[str, Any]:
    ordered = sorted(names)
    return {"type": "object", "properties": {
        name: {"type": ["string", "null"]} for name in ordered
    }, "required": ordered, "additionalProperties": False}


REGISTRATION_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "identity_hints": _object_schema(IDENTITY_HINT_FIELDS),
        "verified_delta": _object_schema(REGISTRATION_FIELDS),
    },
    "required": ["identity_hints", "verified_delta"],
    "additionalProperties": False,
}


def _field(value: Any, name: str) -> Any:
    return value.get(name) if isinstance(value, dict) else getattr(value, name, None)


def _has_refusal(response: Any) -> bool:
    for item in _field(response, "output") or []:
        for content in _field(item, "content") or []:
            if _field(content, "type") == "refusal" or _field(content, "refusal"):
                return True
    return False


def _validated_output(text: str) -> dict[str, dict[str, str]]:
    try:
        payload = json.loads(text)
        if not isinstance(payload, dict) or set(payload) != set(REGISTRATION_OUTPUT_SCHEMA["required"]):
            raise ValueError("root")
        result = {}
        for section, allowed in (("identity_hints", IDENTITY_HINT_FIELDS),
                                 ("verified_delta", REGISTRATION_FIELDS)):
            values = payload[section]
            if not isinstance(values, dict) or set(values) != allowed:
                raise ValueError(section)
            if any(value is not None and not isinstance(value, str) for value in values.values()):
                raise ValueError(section)
            result[section] = {key: value for key, value in values.items() if value is not None}
        return result
    except (ValueError, TypeError, KeyError):
        raise WorkbenchCapabilityDebt("EVIDENCE_INTERPRETER_UNAVAILABLE") from None


class OpenAIRegistrationEvidenceInterpreter:
    """Strict, non-storing interpretation of one exact registration PDF preimage."""

    def __init__(self, *, settings: Settings, client: Any | None = None) -> None:
        self.model = (settings.registration_interpreter_model or "").strip()
        secret = (settings.openai_api_key.get_secret_value().strip()
                  if settings.openai_api_key else "")
        self.client = client if client is not None else (
            OpenAI(api_key=secret, timeout=30.0, max_retries=0) if secret else None
        )

    def interpret(self, *, request_text: str, evidence_bytes: bytes,
                  mime_type: str) -> dict[str, Any]:
        if (mime_type != "application/pdf" or not evidence_bytes.startswith(b"%PDF-")
            or b"%%EOF" not in evidence_bytes[-1024:]):
            raise WorkbenchConflict("HOLD_DOCUMENT_PREIMAGE_INVALID")
        if not self.model or self.client is None:
            raise WorkbenchCapabilityDebt("EVIDENCE_INTERPRETER_UNAVAILABLE")
        try:
            response = self.client.responses.create(
                model=self.model,
                store=False,
                tools=[],
                tool_choice="none",
                input=[
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": [
                        {"type": "input_file", "filename": "registration.pdf",
                         "file_data": "data:application/pdf;base64," +
                         base64.b64encode(evidence_bytes).decode(), "detail": "high"},
                        {"type": "input_text", "text": "Task context (not evidence): " + request_text},
                    ]},
                ],
                text={"format": {"type": "json_schema", "name": "registration_evidence",
                                 "strict": True, "schema": REGISTRATION_OUTPUT_SCHEMA}},
            )
        except Exception:
            raise WorkbenchCapabilityDebt("EVIDENCE_INTERPRETER_UNAVAILABLE") from None
        if (_field(response, "status") != "completed" or _has_refusal(response)
            or not isinstance(_field(response, "output_text"), str)):
            raise WorkbenchCapabilityDebt("EVIDENCE_INTERPRETER_UNAVAILABLE")
        return _validated_output(_field(response, "output_text"))
