from __future__ import annotations

import io
import zipfile

import pytest

from global_hybrid_v2.adapters.drive_xlsx_workbench import (
    DriveXlsxWorkbenchPort,
    WorkbenchConflict,
)
from global_hybrid_v2.runtime.deployment import RuntimeIdentity
from global_hybrid_v2.workbench_qualification import (
    REQUIRED_SHEETS,
    QualificationBinding,
    load_binding,
    run_qualification,
)


def xlsx_bytes(comment=b""):
    stream = io.BytesIO()
    workbook = (
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheets>'
        + "".join(
            f'<sheet name="{name}" sheetId="{index}"/>'
            for index, name in enumerate(REQUIRED_SHEETS, 1)
        )
        + "</sheets></workbook>"
    )
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.comment = comment
    return stream.getvalue()


class FakeDrive:
    def __init__(self, payload):
        self.payload = payload
        self.version = 1
        self.replacements = 0

    def metadata(self, file_id):
        return {"id": file_id, "version": str(self.version)}

    def download(self, file_id):
        return self.payload

    def replace(self, file_id, payload, mime_type):
        self.payload = payload
        self.version += 1
        self.replacements += 1
        return {"id": file_id, "version": str(self.version)}


class FakeClaims:
    def claim(self, payload):
        return {"state": "CLAIMED"}

    def complete(self, payload):
        return {"state": "COMPLETED"}

    def fail(self, payload):
        return {"state": "FAILED"}


def binding():
    return QualificationBinding(
        file_id="candidate-file",
        google_service_account_json="{}",
        control_base_url="https://control.example",
        control_write_secret="secret",
        expected_commit="head",
        expected_branch="candidate",
        expected_repo_slug="owner/repo",
    )


def test_qualification_probe_is_reversible_and_final_bytes_are_exact():
    baseline = xlsx_bytes()
    drive = FakeDrive(baseline)
    port = DriveXlsxWorkbenchPort(file_id="candidate-file", drive=drive, claims=FakeClaims())
    receipt = run_qualification(binding(), port=port)
    assert receipt.state == "QUALIFICATION_PASS"
    assert receipt.baseline_sha256 == receipt.restored_sha256
    assert drive.payload == baseline
    assert drive.replacements == 2
    assert receipt.sheets == REQUIRED_SHEETS


def test_binding_fails_closed_on_runtime_or_live_execution_mismatch():
    env = {
        "GLOBAL_WORKBENCH_QUALIFICATION_ENABLED": "true",
        "GLOBAL_LIVE_EXECUTION": "false",
        "GLOBAL_WORKBENCH_QUALIFICATION_EXPECTED_COMMIT": "head",
        "GLOBAL_WORKBENCH_QUALIFICATION_EXPECTED_BRANCH": "candidate",
        "GLOBAL_WORKBENCH_QUALIFICATION_EXPECTED_REPO_SLUG": "owner/repo",
        "GLOBAL_WORKBENCH_DRIVE_FILE_ID": "candidate-file",
        "GLOBAL_GOOGLE_SERVICE_ACCOUNT_JSON": "{}",
        "GLOBAL_VEHICLE_CONTROL_HTTP_BASE_URL": "https://control.example",
        "GLOBAL_VEHICLE_CONTROL_HTTP_WRITE_SECRET": "secret",
    }
    runtime = RuntimeIdentity("RENDER", "head", "candidate", "owner/repo")
    assert load_binding(env, runtime).file_id == "candidate-file"

    bad = dict(env)
    bad["GLOBAL_LIVE_EXECUTION"] = "true"
    with pytest.raises(WorkbenchConflict, match="LIVE_EXECUTION_FALSE"):
        load_binding(bad, runtime)

    wrong = RuntimeIdentity("RENDER", "other", "candidate", "owner/repo")
    with pytest.raises(WorkbenchConflict, match="COMMIT_MISMATCH"):
        load_binding(env, wrong)


def test_binding_is_disabled_by_default():
    with pytest.raises(Exception, match="QUALIFICATION_DISABLED"):
        load_binding({}, RuntimeIdentity("RENDER", "head", "candidate", "owner/repo"))


def test_wrong_workbook_topology_holds_before_write():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr(
            "xl/workbook.xml",
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheets><sheet name="only-one" sheetId="1"/></sheets></workbook>',
        )
    drive = FakeDrive(stream.getvalue())
    port = DriveXlsxWorkbenchPort(file_id="candidate-file", drive=drive, claims=FakeClaims())
    with pytest.raises(WorkbenchConflict, match="TOPOLOGY_MISMATCH"):
        run_qualification(binding(), port=port)
    assert drive.replacements == 0
