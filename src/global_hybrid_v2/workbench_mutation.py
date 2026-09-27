"""Bounded mutation of an already-resolved row in an XLSX workbench."""
from __future__ import annotations

import hashlib
import io
import json
import math
import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass

from global_hybrid_v2.adapters.drive_xlsx_workbench import WorkbenchConflict
from global_hybrid_v2.contracts import WorkbenchSyncIntent

AI_SHEET = "AI工作主表"
HISTORY_SHEET = "VEHICLE_WORK_HISTORY"
COVERAGE_SHEET = "CONFIG_COVERAGE"
PROTECTED_FIELDS = frozenset({
    "成本", "同行",
    "成本_RAW", "同行_RAW", "成本_Canonical", "成本幣別", "同行_Canonical", "同行幣別",
    "COMPANY_SOURCE_STATE", "COMPANY_SOURCE_ROW_CURRENT", "COMPANY_SOURCE_MODIFIED_AT",
    "COMPANY_SOURCE_OBSERVED_AT",
})
ALLOWED_FIELDS = frozenset({
    "VIN/車身號碼", "車牌", "實車身分狀態", "排氣量_Canonical", "排氣量單位",
    "里程_Canonical", "里程單位", "開價_Canonical", "開價幣別", "開價揭露狀態",
    "事故/泡水狀態", "維修/保養狀態", "保固狀態", "實際配備狀態", "改裝狀態",
    "原用途", "轉手次數", "權利負擔", "過戶阻礙", "強制險狀態", "檢驗狀態",
    "原始媒體Refs", "媒體綁定狀態", "證據/缺口摘要", "AI使用狀態",
    "版本/等級", "燃料_Canonical", "座位數_Canonical", "車身型式_Canonical",
    "頭燈_Canonical", "出廠年月", "原發照日期", "換補照日期", "文件Refs",
    "車輛資料更新時間", "資料更新依據", "最後更新任務ID", "IDEMPOTENCY_KEY",
    "REFERENCE_CONFIG_MATCH_STATE", "REFERENCE_TRIM_CANDIDATE", "REFERENCE_EQUIPMENT_MATCH",
    "REFERENCE_PROVENANCE_STATE", "REFERENCE_SOURCE", "REFERENCE_LAST_VERIFIED",
    "RESEARCH_STATE", "RESEARCH_GAPS",
})
_S = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_P = "http://schemas.openxmlformats.org/package/2006/relationships"
_CELL = re.compile(r"([A-Z]+)([1-9][0-9]*)$")
ET.register_namespace("", _S)


def _q(tag: str) -> str:
    return f"{{{_S}}}{tag}"


def _column(ref: str) -> int:
    match = _CELL.fullmatch(ref)
    if not match:
        raise WorkbenchConflict("HOLD_WORKBOOK_CELL_REFERENCE_INVALID")
    value = 0
    for letter in match.group(1):
        value = value * 26 + ord(letter) - 64
    return value


def _ref(column: int, row: int) -> str:
    letters = ""
    while column:
        column, digit = divmod(column - 1, 26)
        letters = chr(65 + digit) + letters
    return f"{letters}{row}"


def _cell_value(cell: ET.Element, shared: list[str]) -> str:
    kind = cell.get("t")
    if kind == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(f".//{_q('t')}"))
    value = cell.findtext(_q("v"))
    if value is None:
        return ""
    if kind == "s":
        try:
            return shared[int(value)]
        except (IndexError, ValueError) as exc:
            raise WorkbenchConflict("HOLD_WORKBOOK_SHARED_STRING_INVALID") from exc
    return value


def _set_cell(cell: ET.Element, value: str | int | float) -> None:
    if cell.find(_q("f")) is not None:
        raise WorkbenchConflict("HOLD_FORMULA_CELL_MUTATION")
    for child in list(cell):
        if child.tag in {_q("v"), _q("is")}:
            cell.remove(child)
    if isinstance(value, str):
        cell.set("t", "inlineStr")
        inline = ET.SubElement(cell, _q("is"))
        ET.SubElement(inline, _q("t")).text = value
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(value):
            raise WorkbenchConflict("HOLD_DELTA_VALUE_INVALID")
        cell.attrib.pop("t", None)
        ET.SubElement(cell, _q("v")).text = str(value)
    else:
        raise WorkbenchConflict("HOLD_DELTA_VALUE_INVALID")


@dataclass
class _Workbook:
    entries: dict[str, bytes]
    infos: list[zipfile.ZipInfo]
    sheets: dict[str, str]
    shared: list[str]

    @classmethod
    def parse(cls, payload: bytes) -> _Workbook:
        if len(payload) > 25_000_000:
            raise WorkbenchConflict("HOLD_WORKBOOK_TOO_LARGE")
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                infos = archive.infolist()
                if len(infos) > 250 or any(i.file_size > 10_000_000 for i in infos):
                    raise WorkbenchConflict("HOLD_WORKBOOK_TOO_LARGE")
                if len({i.filename for i in infos}) != len(infos):
                    raise WorkbenchConflict("HOLD_WORKBOOK_DUPLICATE_ENTRY")
                entries = {i.filename: archive.read(i) for i in infos}
            workbook = ET.fromstring(entries["xl/workbook.xml"])
            rels = ET.fromstring(entries["xl/_rels/workbook.xml.rels"])
            targets = {rel.get("Id"): rel.get("Target") for rel in rels.findall(f"{{{_P}}}Relationship")}
            sheets = {}
            for sheet in workbook.findall(f".//{_q('sheet')}"):
                target = targets.get(sheet.get(f"{{{_R}}}id"))
                if not target:
                    raise WorkbenchConflict("HOLD_WORKBOOK_SHEET_BINDING_MISSING")
                path = target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/" + target)
                if not path.startswith("xl/") or path not in entries:
                    raise WorkbenchConflict("HOLD_WORKBOOK_SHEET_BINDING_INVALID")
                name = sheet.get("name")
                if not name or name in sheets:
                    raise WorkbenchConflict("HOLD_WORKBOOK_TOPOLOGY_INVALID")
                sheets[name] = path
            shared = []
            if "xl/sharedStrings.xml" in entries:
                root = ET.fromstring(entries["xl/sharedStrings.xml"])
                shared = ["".join(t.text or "" for t in si.findall(f".//{_q('t')}"))
                          for si in root.findall(_q("si"))]
            return cls(entries, infos, sheets, shared)
        except (KeyError, zipfile.BadZipFile, ET.ParseError, OSError) as exc:
            raise WorkbenchConflict("HOLD_WORKBOOK_UNREADABLE") from exc

    def root(self, sheet: str) -> ET.Element:
        path = self.sheets.get(sheet)
        if path is None:
            raise WorkbenchConflict("HOLD_WORKBOOK_SHEET_MISSING:" + sheet)
        try:
            return ET.fromstring(self.entries[path])
        except ET.ParseError as exc:
            raise WorkbenchConflict("HOLD_WORKBOOK_SHEET_UNREADABLE") from exc

    def render(self, replacements: dict[str, ET.Element]) -> bytes:
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            for info in self.infos:
                data = self.entries[info.filename]
                if info.filename in replacements:
                    data = ET.tostring(replacements[info.filename], encoding="utf-8", xml_declaration=True)
                archive.writestr(info, data)
        return output.getvalue()


def _rows(root: ET.Element) -> list[ET.Element]:
    data = root.find(_q("sheetData"))
    if data is None:
        raise WorkbenchConflict("HOLD_WORKBOOK_SHEET_DATA_MISSING")
    return data.findall(_q("row"))


def _header(root: ET.Element, shared: list[str]) -> dict[str, int]:
    rows = _rows(root)
    if not rows or rows[0].get("r") != "1":
        raise WorkbenchConflict("HOLD_WORKBOOK_HEADER_MISSING")
    header = {}
    for cell in rows[0].findall(_q("c")):
        value = _cell_value(cell, shared)
        if value in header:
            raise WorkbenchConflict("HOLD_WORKBOOK_DUPLICATE_HEADER")
        header[value] = _column(cell.get("r") or "")
    return header


def _row(root: ET.Element, number: int) -> ET.Element:
    matches = [row for row in _rows(root) if row.get("r") == str(number)]
    if len(matches) != 1:
        raise WorkbenchConflict("HOLD_VEHICLE_ROW_UNRESOLVED")
    return matches[0]


def _cell(row: ET.Element, column: int, *, create: bool = False) -> ET.Element | None:
    row_number = int(row.get("r") or 0)
    ref = _ref(column, row_number)
    matches = [cell for cell in row.findall(_q("c")) if cell.get("r") == ref]
    if len(matches) > 1:
        raise WorkbenchConflict("HOLD_WORKBOOK_DUPLICATE_CELL")
    if matches:
        return matches[0]
    if not create:
        return None
    cell = ET.Element(_q("c"), {"r": ref})
    for index, existing in enumerate(row.findall(_q("c"))):
        if _column(existing.get("r") or "") > column:
            row.insert(index, cell)
            return cell
    row.append(cell)
    return cell


def _values(row: ET.Element, shared: list[str]) -> dict[int, str]:
    return {_column(c.get("r") or ""): _cell_value(c, shared) for c in row.findall(_q("c"))}


class XlsxWorkbenchMutationBuilder:
    """Update one resolved AI row and append one idempotent history record."""

    def build(self, preimage: bytes, intent: WorkbenchSyncIntent) -> bytes:
        book = _Workbook.parse(preimage)
        ai = book.root(AI_SHEET)
        header = _header(ai, book.shared)
        identity_column = header.get("VEHICLE_INSTANCE_ID")
        if identity_column is None:
            raise WorkbenchConflict("HOLD_VEHICLE_ID_COLUMN_MISSING")
        matches = [candidate for candidate in _rows(ai)[1:]
                   if (cell := _cell(candidate, identity_column)) is not None
                   and _cell_value(cell, book.shared) == intent.vehicle_instance_id]
        if len(matches) != 1:
            raise WorkbenchConflict("HOLD_VEHICLE_IDENTITY_AMBIGUOUS")
        row = _row(ai, intent.ai_row)
        if matches[0] is not row:
            raise WorkbenchConflict("HOLD_VEHICLE_ROW_MISMATCH")
        identity_cell = _cell(row, identity_column)
        if identity_cell is None or _cell_value(identity_cell, book.shared) != intent.vehicle_instance_id:
            raise WorkbenchConflict("HOLD_VEHICLE_INSTANCE_MISMATCH")
        if set(intent.verified_delta) & PROTECTED_FIELDS:
            raise WorkbenchConflict("HOLD_PROTECTED_FIELD_MUTATION")
        if set(intent.verified_delta) - ALLOWED_FIELDS:
            raise WorkbenchConflict("HOLD_UNADMITTED_FIELD_MUTATION")
        if any(key not in header for key in intent.verified_delta):
            raise WorkbenchConflict("HOLD_WORKBOOK_DELTA_COLUMN_MISSING")
        changed = False
        for field, value in intent.verified_delta.items():
            if not isinstance(value, (str, int, float)) or isinstance(value, bool):
                raise WorkbenchConflict("HOLD_DELTA_VALUE_INVALID")
            current = _cell(row, header[field])
            if ("" if current is None else _cell_value(current, book.shared)) == str(value):
                continue
            _set_cell(_cell(row, header[field], create=True), value)
            changed = True
        if not changed:
            return preimage
        history = book.root(HISTORY_SHEET)
        history_header = _header(history, book.shared)
        required = {"IDEMPOTENCY_KEY", "VEHICLE_INSTANCE_ID"}
        if not required.issubset(history_header):
            raise WorkbenchConflict("HOLD_HISTORY_HEADER_MISSING")
        intent_key = hashlib.sha256(json.dumps(
            {"vehicle": intent.vehicle_instance_id, "row": intent.ai_row,
             "delta": intent.verified_delta, "evidence": intent.evidence_refs},
            ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode()).hexdigest()
        for existing in _rows(history)[1:]:
            key_cell = _cell(existing, history_header["IDEMPOTENCY_KEY"])
            if key_cell is not None and _cell_value(key_cell, book.shared) == intent_key:
                raise WorkbenchConflict("HOLD_HISTORY_ROW_ALREADY_PRESENT_WITH_DRIFT")
        history_rows = _rows(history)
        number = max(int(item.get("r") or 0) for item in history_rows) + 1
        new_row = ET.SubElement(history.find(_q("sheetData")), _q("row"), {"r": str(number)})
        history_values = {
            "IDEMPOTENCY_KEY": intent_key,
            "VEHICLE_INSTANCE_ID": intent.vehicle_instance_id,
            "AI_ROW": intent.ai_row,
            "EVIDENCE_REFS": ",".join(intent.evidence_refs),
        }
        for name, column in sorted(history_header.items(), key=lambda item: item[1]):
            if name in history_values:
                _set_cell(_cell(new_row, column, create=True), history_values[name])
        replacements = {book.sheets[AI_SHEET]: ai, book.sheets[HISTORY_SHEET]: history}
        if any(field.startswith("REFERENCE_") for field in intent.verified_delta):
            coverage = book.root(COVERAGE_SHEET)
            coverage_header = _header(coverage, book.shared)
            ai_column = coverage_header.get("AI_ROW")
            if ai_column is None:
                raise WorkbenchConflict("HOLD_CONFIG_COVERAGE_BINDING_MISSING")
            matches = [item for item in _rows(coverage)[1:]
                       if (cell := _cell(item, ai_column)) is not None
                       and _cell_value(cell, book.shared) == str(intent.ai_row)]
            if len(matches) != 1:
                raise WorkbenchConflict("HOLD_CONFIG_COVERAGE_BINDING_AMBIGUOUS")
            for field, value in intent.verified_delta.items():
                if field.startswith("REFERENCE_"):
                    column = coverage_header.get(field)
                    if column is None:
                        raise WorkbenchConflict("HOLD_CONFIG_COVERAGE_COLUMN_MISSING")
                    _set_cell(_cell(matches[0], column, create=True), value)
            replacements[book.sheets[COVERAGE_SHEET]] = coverage
        output = book.render(replacements)
        self.verify(preimage, output, intent)
        return output

    def verify(self, preimage: bytes, output: bytes, intent: WorkbenchSyncIntent) -> None:
        before = _Workbook.parse(preimage)
        after = _Workbook.parse(output)
        if list(before.sheets) != list(after.sheets) or list(before.entries) != list(after.entries):
            raise WorkbenchConflict("HOLD_WORKBOOK_TOPOLOGY_CHANGED")
        permitted_entries = {before.sheets[AI_SHEET], before.sheets[HISTORY_SHEET]}
        if any(key.startswith("REFERENCE_") for key in intent.verified_delta):
            permitted_entries.add(before.sheets[COVERAGE_SHEET])
        for name in before.entries:
            if name not in permitted_entries and before.entries[name] != after.entries[name]:
                raise WorkbenchConflict("HOLD_UNRELATED_WORKBOOK_ENTRY_CHANGED")
        old_ai, new_ai = before.root(AI_SHEET), after.root(AI_SHEET)
        if [r.get("r") for r in _rows(old_ai)] != [r.get("r") for r in _rows(new_ai)]:
            raise WorkbenchConflict("HOLD_VEHICLE_ROW_TOPOLOGY_CHANGED")
        header = _header(old_ai, before.shared)
        for old_row, new_row in zip(_rows(old_ai), _rows(new_ai), strict=True):
            old_values, new_values = _values(old_row, before.shared), _values(new_row, after.shared)
            if old_row.get("r") != str(intent.ai_row):
                if ET.tostring(old_row) != ET.tostring(new_row):
                    raise WorkbenchConflict("HOLD_UNRELATED_VEHICLE_ROW_CHANGED")
                continue
            changed_columns = {column for column in old_values.keys() | new_values.keys()
                               if old_values.get(column, "") != new_values.get(column, "")}
            allowed_columns = {header[field] for field in intent.verified_delta}
            if not changed_columns.issubset(allowed_columns):
                raise WorkbenchConflict("HOLD_UNADMITTED_CELL_CHANGED")
            for field, value in intent.verified_delta.items():
                if new_values.get(header[field], "") != str(value):
                    raise WorkbenchConflict("HOLD_DELTA_READBACK_MISMATCH")
            old_cells = {cell.get("r"): cell for cell in old_row.findall(_q("c"))}
            new_cells = {cell.get("r"): cell for cell in new_row.findall(_q("c"))}
            for ref in old_cells.keys() | new_cells.keys():
                if _column(ref or "") not in allowed_columns:
                    old_cell, new_cell = old_cells.get(ref), new_cells.get(ref)
                    if old_cell is None or new_cell is None or ET.tostring(old_cell) != ET.tostring(new_cell):
                        raise WorkbenchConflict("HOLD_UNADMITTED_CELL_CHANGED")
        old_history, new_history = before.root(HISTORY_SHEET), after.root(HISTORY_SHEET)
        old_rows, new_rows = _rows(old_history), _rows(new_history)
        if len(new_rows) != len(old_rows) + 1:
            raise WorkbenchConflict("HOLD_HISTORY_APPEND_MISSING")
        for old_row, new_row in zip(old_rows, new_rows, strict=False):
            if ET.tostring(old_row) != ET.tostring(new_row):
                raise WorkbenchConflict("HOLD_HISTORY_PREIMAGE_CHANGED")
        history_header = _header(old_history, before.shared)
        appended = _values(new_rows[-1], after.shared)
        if (
            appended.get(history_header["VEHICLE_INSTANCE_ID"]) != intent.vehicle_instance_id
            or appended.get(history_header["AI_ROW"]) != str(intent.ai_row)
            or not appended.get(history_header["IDEMPOTENCY_KEY"])
        ):
            raise WorkbenchConflict("HOLD_HISTORY_APPEND_MISMATCH")
        if before.sheets.get(COVERAGE_SHEET) in permitted_entries:
            old_coverage, new_coverage = before.root(COVERAGE_SHEET), after.root(COVERAGE_SHEET)
            old_rows, new_rows = _rows(old_coverage), _rows(new_coverage)
            if len(old_rows) != len(new_rows):
                raise WorkbenchConflict("HOLD_COVERAGE_TOPOLOGY_CHANGED")
            coverage_header = _header(old_coverage, before.shared)
            ai_column = coverage_header.get("AI_ROW")
            if ai_column is None:
                raise WorkbenchConflict("HOLD_CONFIG_COVERAGE_BINDING_MISSING")
            allowed = {coverage_header[field] for field in intent.verified_delta
                       if field.startswith("REFERENCE_")}
            matched = 0
            for old_row, new_row in zip(old_rows, new_rows, strict=True):
                old_values = _values(old_row, before.shared)
                new_values = _values(new_row, after.shared)
                is_target = old_values.get(ai_column) == str(intent.ai_row)
                matched += is_target
                changed = {col for col in old_values.keys() | new_values.keys()
                           if old_values.get(col, "") != new_values.get(col, "")}
                if changed and (not is_target or not changed.issubset(allowed)):
                    raise WorkbenchConflict("HOLD_UNRELATED_COVERAGE_CELL_CHANGED")
            if matched != 1:
                raise WorkbenchConflict("HOLD_CONFIG_COVERAGE_BINDING_AMBIGUOUS")
