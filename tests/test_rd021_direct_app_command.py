"""Direct App registration-document command commits only against its resolved preimage."""
from __future__ import annotations

import io
import zipfile

import pytest

from global_hybrid_v2.adapters.drive_xlsx_workbench import DriveXlsxWorkbenchPort
from global_hybrid_v2.company_commercial_completion import (
    CANONICAL_WORKBENCH_FILE_ID,
    CompanyCommercialCompletionHandler,
)
from global_hybrid_v2.controlled_workbench_command import (
    ControlledWorkbenchCommandHandler,
    RegistrationDocumentResolver,
    SelectionTokenCodec,
    WorkbenchSnapshotReader,
)
from global_hybrid_v2.trusted_workbench_intent import EvidenceReceiptSigner, TrustedWorkbenchIntentProducer
from global_hybrid_v2.workbench_mutation import XlsxWorkbenchMutationBuilder
from global_hybrid_v2.workbench_target import TargetMode, WorkbenchTargetBinding
from tests.test_rd021_completion_fence import Claims, Drive, sheet, workbook

PDF = b"%PDF-1.7\nregistration document fixture\n%%EOF\n"
VIN_A = "WBA12345678901234"
VIN_B = "WBA98765432109876"
PLATE_A = "ABC-1234"
PLATE_B = "XYZ-9876"


def registration_workbook(*, blank_identity=False, unbound=False) -> bytes:
    replacement = sheet(
        ("VEHICLE_INSTANCE_ID", "VIN/車身號碼", "車牌", "排氣量_Canonical", "成本_Canonical",
         "年分", "品牌", "車型"),
        {13: ("" if unbound else "8891:S4806251", "" if blank_identity else VIN_A,
              "" if blank_identity else PLATE_A, "", "", "2018", "BMW", "318I"),
         14: ("8891:S4806252", VIN_B, PLATE_B, "", "", "2020", "BMW", "320I")},
    )
    source = io.BytesIO(workbook())
    output = io.BytesIO()
    with zipfile.ZipFile(source) as before, zipfile.ZipFile(output, "w") as after:
        for info in before.infolist():
            after.writestr(info, replacement if info.filename == "xl/worksheets/sheet1.xml"
                           else before.read(info))
    return output.getvalue()


class Interpreter:
    def __init__(self, fields):
        self.fields = fields
        self.calls = []

    def interpret(self, **kwargs):
        self.calls.append(kwargs)
        return self.fields


def command(fields=None, *, writer=True, interpreter=True, drift=False,
            blank_identity=False, unbound=False):
    target = WorkbenchTargetBinding.qualification("disposable-xlsx-file")
    drive = Drive(registration_workbook(blank_identity=blank_identity, unbound=unbound))
    drive.drift = drift
    signer = EvidenceReceiptSigner(key=b"r" * 32)
    reader = WorkbenchSnapshotReader(drive=drive, target=target)
    offered = fields if fields is not None else {
        "VIN/車身號碼": VIN_A, "車牌": PLATE_A, "排氣量_Canonical": "1998",
    }
    interpreter_port = Interpreter({"identity_hints": {"year": "2018", "make": "BMW",
                                                       "model": "318I"},
                                    "verified_delta": offered}) if interpreter else None
    resolver = RegistrationDocumentResolver(interpreter=interpreter_port, signer=signer)
    producer = TrustedWorkbenchIntentProducer(signer, target=target)
    port = DriveXlsxWorkbenchPort(file_id=target.file_id, drive=drive, claims=Claims()) if writer else None
    completion = CompanyCommercialCompletionHandler(
        writer=port, builder=XlsxWorkbenchMutationBuilder(), target=target,
    )
    handler = ControlledWorkbenchCommandHandler(
        target=target, snapshot_reader=reader, resolver=resolver,
        producer=producer, completion=completion,
        selection_codec=SelectionTokenCodec(b"s" * 32),
    )
    return handler, drive, interpreter_port


def run(handler, token=None):
    if token is None:
        token = handler.list_candidates()[0]["opaque_selection_token"]
    return handler.execute(request_text="同步這台公司車行照", evidence_bytes=PDF,
                           mime_type="application/pdf", target_selection_token=token)


def test_registration_document_unique_vehicle_write_and_readback():
    handler, drive, interpreter = command()
    result = run(handler)
    assert result.terminal_disposition == "WRITE_AND_READBACK_PASS"
    assert drive.writes == 1
    assert interpreter.calls[0]["evidence_bytes"] == PDF
    assert b"1998" in drive.payload


def test_explicit_selection_bootstraps_blank_bmw_identity_on_same_row():
    handler, drive, _ = command(blank_identity=True)
    candidates = handler.list_candidates()
    assert len(candidates) == 2
    assert "2018 BMW 318I" in candidates[0]["display_label"]
    assert "8891:S4806251" not in str(candidates)
    result = run(handler, candidates[0]["opaque_selection_token"])
    assert result.terminal_disposition == "WRITE_AND_READBACK_PASS"
    assert drive.writes == 1
    assert VIN_A.encode() in drive.payload and PLATE_A.encode() in drive.payload
    assert b"8891:S4806251" in drive.payload


@pytest.mark.parametrize("field,value", [("VIN/車身號碼", VIN_B), ("車牌", PLATE_B)])
def test_other_vehicle_identity_collision_never_writes(field, value):
    fields = {"VIN/車身號碼": VIN_A, "車牌": PLATE_A}
    fields[field] = value
    handler, drive, _ = command(fields, blank_identity=True)
    assert run(handler).terminal_disposition == "HOLD_CONFLICT"
    assert drive.writes == 0


def test_selected_row_descriptor_mismatch_never_writes():
    handler, drive, interpreter = command(blank_identity=True)
    interpreter.fields["identity_hints"]["make"] = "Mercedes"
    assert run(handler).terminal_disposition == "HOLD_CONFLICT"
    assert drive.writes == 0


def test_wrong_selected_vehicle_conflicts_with_document_identity():
    handler, drive, interpreter = command()
    token = handler.list_candidates()[1]["opaque_selection_token"]
    result = run(handler, token)
    assert result.terminal_disposition == "HOLD_CONFLICT"
    assert interpreter.calls
    assert drive.writes == 0


def test_missing_selection_and_unbound_observation():
    handler, drive, _ = command()
    missing = handler.execute(request_text="x", evidence_bytes=PDF,
                              mime_type="application/pdf", target_selection_token=None)
    assert missing.result_text == "TARGET_VEHICLE_SELECTION_REQUIRED" and drive.writes == 0
    handler, drive, _ = command(unbound=True)
    snapshot = handler.snapshot_reader.read()
    token = handler.selection_codec.issue(snapshot, snapshot.rows[0])
    result = run(handler, token)
    assert result.result_text == "UNBOUND_OBSERVATION_INSTANCE_CREATION_CAPABILITY_DEBT"
    assert drive.writes == 0


def test_tampered_or_stale_selection_holds_before_interpretation():
    handler, drive, interpreter = command()
    token = handler.list_candidates()[0]["opaque_selection_token"]
    result = run(handler, token[:-3] + "xyz")
    assert result.result_text == "HOLD_STALE_PREIMAGE"
    drive.version = "stale-selection-version"
    result = run(handler, token)
    assert result.result_text == "HOLD_STALE_PREIMAGE"
    assert not interpreter.calls
    assert drive.writes == 0


def test_same_document_values_are_no_delta_without_replace():
    handler, drive, _ = command({"VIN/車身號碼": VIN_A, "車牌": PLATE_A})
    result = run(handler)
    assert result.terminal_disposition == "NO_DELTA" and drive.writes == 0


@pytest.mark.parametrize("fields", [
    {"VIN/車身號碼": VIN_A, "車牌": PLATE_B, "排氣量_Canonical": "1998"},
    {"VIN/車身號碼": "WBA00000000000000", "排氣量_Canonical": "1998"},
    {"VIN/車身號碼": VIN_A, "成本_Canonical": "1"},
    {"VIN/車身號碼": VIN_A, "vehicle_instance_id": "invented"},
    {"VIN/車身號碼": VIN_A, "ai_row": 13},
])
def test_conflict_ambiguous_or_privileged_interpreter_fields_never_write(fields):
    handler, drive, _ = command(fields)
    assert run(handler).terminal_disposition == "HOLD_CONFLICT"
    assert drive.writes == 0


def test_resolution_preimage_drift_holds_before_replace():
    handler, drive, _ = command(drift=True)
    result = run(handler)
    assert result.terminal_disposition == "HOLD_CONFLICT"
    assert result.result_text == "HOLD_STALE_PREIMAGE"
    assert drive.writes == 0


def test_interpreter_or_writer_unavailable_is_capability_debt():
    for options in ({"interpreter": False}, {"writer": False}):
        handler, drive, _ = command(**options)
        assert run(handler).terminal_disposition == "PERSISTENCE_CAPABILITY_DEBT"
        assert drive.writes == 0


def test_target_modes_guard_production_identity():
    assert WorkbenchTargetBinding.production().file_id == CANONICAL_WORKBENCH_FILE_ID
    with pytest.raises(ValueError, match="PRODUCTION_WORKBENCH_TARGET_OVERRIDE_FORBIDDEN"):
        WorkbenchTargetBinding(TargetMode.PRODUCTION, "disposable-xlsx-file")
    with pytest.raises(ValueError, match="NONPRODUCTION_WORKBENCH_TARGET_INVALID"):
        WorkbenchTargetBinding.qualification(CANONICAL_WORKBENCH_FILE_ID)
    with pytest.raises(ValueError, match="NONPRODUCTION_WORKBENCH_TARGET_INVALID"):
        WorkbenchTargetBinding.qualification("")
