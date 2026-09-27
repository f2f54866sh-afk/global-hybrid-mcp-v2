"""RD-021 completion fence and exact-preimage XLSX mutation contracts."""
from __future__ import annotations

import io
import xml.etree.ElementTree as ET
import zipfile

import pytest

from global_hybrid_v2.adapters.drive_xlsx_workbench import DriveXlsxWorkbenchPort
from global_hybrid_v2.company_commercial_completion import (
    CANONICAL_WORKBENCH_FILE_ID,
    CompanyCommercialCompletionHandler,
)
from global_hybrid_v2.contracts import (
    DomainResult,
    EffectType,
    Intent,
    Owner,
    PersistenceDisposition,
    PersistenceReceipt,
    TaskContract,
    WorkbenchSyncIntent,
)
from global_hybrid_v2.runtime.dispatcher import Dispatcher
from global_hybrid_v2.runtime.trace import TraceBus
from global_hybrid_v2.workbench_mutation import XlsxWorkbenchMutationBuilder

S = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
P = "http://schemas.openxmlformats.org/package/2006/relationships"


def q(name: str) -> str:
    return f"{{{S}}}{name}"


def sheet(headers: tuple[str, ...], rows: dict[int, tuple[str, ...]]) -> bytes:
    root = ET.Element(q("worksheet"))
    data = ET.SubElement(root, q("sheetData"))
    for index, values in [(1, headers), *sorted(rows.items())]:
        row = ET.SubElement(data, q("row"), {"r": str(index)})
        for column, value in enumerate(values):
            if value == "":
                continue
            ref = f"{chr(65 + column)}{index}"
            cell = ET.SubElement(row, q("c"), {"r": ref, "t": "inlineStr"})
            ET.SubElement(ET.SubElement(cell, q("is")), q("t")).text = value
    return ET.tostring(root)


def workbook(*, duplicate: bool = False) -> bytes:
    root = ET.Element(q("workbook"))
    sheets = ET.SubElement(root, q("sheets"))
    names = ("AI工作主表", "VEHICLE_WORK_HISTORY", "CONFIG_COVERAGE")
    for index, name in enumerate(names, 1):
        ET.SubElement(sheets, q("sheet"), {"name": name, "sheetId": str(index), f"{{{R}}}id": f"rId{index}"})
    rels = ET.Element(f"{{{P}}}Relationships")
    for index in range(1, 4):
        ET.SubElement(
            rels, f"{{{P}}}Relationship",
            {"Id": f"rId{index}", "Target": f"worksheets/sheet{index}.xml"},
        )
    ai = sheet(
        ("VEHICLE_INSTANCE_ID", "里程_Canonical", "成本_Canonical", "REFERENCE_CONFIG_MATCH_STATE"),
        {11: ("gran-turismo", "20000", "", ""),
         13: ("8891:S4806251", "80000", "", "") ,
         **({14: ("8891:S4806251", "", "", "")} if duplicate else {})},
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("xl/workbook.xml", ET.tostring(root))
        archive.writestr("xl/_rels/workbook.xml.rels", ET.tostring(rels))
        archive.writestr("xl/worksheets/sheet1.xml", ai)
        archive.writestr(
            "xl/worksheets/sheet2.xml",
            sheet(("IDEMPOTENCY_KEY", "VEHICLE_INSTANCE_ID", "AI_ROW", "EVIDENCE_REFS"), {}),
        )
        archive.writestr(
            "xl/worksheets/sheet3.xml",
            sheet(("AI_ROW", "REFERENCE_CONFIG_MATCH_STATE"), {2: ("13", "")}),
        )
        archive.writestr("xl/other.xml", b"untouched")
    return output.getvalue()


class Drive:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.version = 1
        self.reads = 0
        self.writes = 0
        self.drift = False
        self.corrupt = False

    def metadata(self, file_id: str) -> dict:
        self.reads += 1
        if self.drift and self.reads == 2:
            self.version += 1
        return {"id": file_id, "version": str(self.version)}

    def download(self, file_id: str) -> bytes:
        return self.payload

    def replace(self, file_id: str, payload: bytes, mime_type: str) -> dict:
        self.writes += 1
        self.payload = b"corrupt" if self.corrupt else payload
        self.version += 1
        return {"id": file_id, "version": str(self.version)}


class Claims:
    def claim(self, payload: dict) -> dict:
        return {"state": "CLAIMED"}

    def complete(self, payload: dict) -> dict:
        return {"state": "COMPLETED"}

    def fail(self, payload: dict) -> dict:
        return {"state": "FAILED"}


def intent(delta: dict | None = None, **changes) -> WorkbenchSyncIntent:
    fields = dict(
        target_file_id=CANONICAL_WORKBENCH_FILE_ID,
        vehicle_instance_id="8891:S4806251", ai_row=13,
        safe_attribution=True, identity_conflict=False,
        verified_delta={"里程_Canonical": 84550} if delta is None else delta,
        evidence_refs=("CURRENT_USER_PHOTO",),
    )
    fields.update(changes)
    return WorkbenchSyncIntent(**fields)


def handler(drive: Drive) -> CompanyCommercialCompletionHandler:
    writer = DriveXlsxWorkbenchPort(file_id=CANONICAL_WORKBENCH_FILE_ID, drive=drive, claims=Claims())
    return CompanyCommercialCompletionHandler(writer=writer, builder=XlsxWorkbenchMutationBuilder())


def test_exact_preimage_write_readback_and_idempotent_replay():
    drive = Drive(workbook())
    first = handler(drive).consume(task_id="t1", intent=intent())
    assert first.state is PersistenceDisposition.WRITE_AND_READBACK_PASS
    assert drive.writes == 1
    second = handler(drive).consume(task_id="t1", intent=intent())
    assert second.state is PersistenceDisposition.NO_DELTA
    assert drive.writes == 1
    with zipfile.ZipFile(io.BytesIO(drive.payload)) as archive:
        assert archive.read("xl/other.xml") == b"untouched"


@pytest.mark.parametrize("field,value", [("成本_Canonical", 355000), ("同行_RAW", "x"), ("UNADMITTED", "x")])
def test_protected_and_unadmitted_fields_fail_closed(field, value):
    drive = Drive(workbook())
    receipt = handler(drive).consume(task_id="t1", intent=intent({field: value}))
    assert receipt.state is PersistenceDisposition.HOLD_CONFLICT
    assert drive.writes == 0


def test_zero_delta_and_capability_debt():
    no_delta = CompanyCommercialCompletionHandler().consume(task_id="t", intent=intent({}))
    assert no_delta.state is PersistenceDisposition.NO_DELTA
    no_writer = CompanyCommercialCompletionHandler().consume(task_id="t", intent=intent())
    assert no_writer.state is PersistenceDisposition.PERSISTENCE_CAPABILITY_DEBT
    drive = Drive(workbook())
    writer = DriveXlsxWorkbenchPort(file_id=CANONICAL_WORKBENCH_FILE_ID, drive=drive, claims=Claims())
    no_builder = CompanyCommercialCompletionHandler(writer=writer).consume(task_id="t", intent=intent())
    assert no_builder.state is PersistenceDisposition.PERSISTENCE_CAPABILITY_DEBT
    assert drive.writes == 0


@pytest.mark.parametrize("condition", ["drift", "corrupt", "duplicate", "wrong_target", "identity_conflict"])
def test_conflicts_fail_closed(condition):
    drive = Drive(workbook(duplicate=condition == "duplicate"))
    drive.drift = condition == "drift"
    drive.corrupt = condition == "corrupt"
    current = intent(**({"target_file_id": "different"} if condition == "wrong_target" else
                       {"identity_conflict": True} if condition == "identity_conflict" else {}))
    receipt = handler(drive).consume(task_id="t", intent=current)
    assert receipt.state is PersistenceDisposition.HOLD_CONFLICT
    if condition != "corrupt":
        assert drive.writes == 0


def test_granturismo_row_preserved_by_other_vehicle_mutation():
    original = workbook()
    output = XlsxWorkbenchMutationBuilder().build(original, intent())
    with zipfile.ZipFile(io.BytesIO(original)) as before, zipfile.ZipFile(io.BytesIO(output)) as after:
        old = ET.fromstring(before.read("xl/worksheets/sheet1.xml"))
        new = ET.fromstring(after.read("xl/worksheets/sheet1.xml"))
        old_row = next(row for row in old.find(q("sheetData")) if row.get("r") == "11")
        new_row = next(row for row in new.find(q("sheetData")) if row.get("r") == "11")
        assert ET.tostring(old_row) == ET.tostring(new_row)


def test_self_asserted_receipt_without_dispatcher_trust_cannot_serialize():
    contract = TaskContract(
        task_id="t", request_text="matching vehicle update", intent=Intent.SALES_HUMAN,
        owner=Owner.SALES_HUMAN, effects=[EffectType.EXTERNAL_WRITE],
        authority_snapshot_id="snapshot", context=[], company_commercial_matching=True,
    )
    self_asserted = PersistenceReceipt(
        state=PersistenceDisposition.WRITE_AND_READBACK_PASS,
        task_id="t", file_id=CANONICAL_WORKBENCH_FILE_ID,
    )
    result = DomainResult(
        owner=Owner.SALES_HUMAN, status="PASS", output={"text": "done"},
        persistence_receipt=self_asserted,
    )
    dispatcher = Dispatcher(authority=None, domains={}, trace=TraceBus())
    blocked = dispatcher._validate_egress(contract, result)
    assert blocked.status == "NO_SERIALIZE / EXECUTION_FAIL"
    assert blocked.evidence["egress_decision"] == "BLOCK"
