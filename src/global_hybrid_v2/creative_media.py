"""Manual creative admission is separate from vehicle truth evidence."""
from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from global_hybrid_v2.adapters.drive_xlsx_workbench import (
    DriveXlsxWorkbenchPort,
    WorkbenchCapabilityDebt,
    WorkbenchConflict,
    WorkbenchPostwriteMismatch,
)
from global_hybrid_v2.company_commercial_completion import CANONICAL_WORKBENCH_FILE_ID
from global_hybrid_v2.contracts import PersistenceDisposition, PersistenceReceipt
from global_hybrid_v2.media_admission import (
    MediaAdmissionError,
    MediaAsset,
    TruthEligibility,
)
from global_hybrid_v2.workbench_mutation import (
    AI_SHEET,
    _cell,
    _cell_value,
    _header,
    _row,
    _rows,
    _set_cell,
    _values,
    _Workbook,
)

CREATIVE_REFS_COLUMN = "銷售素材Refs"
CREATIVE_CHANNELS = frozenset({"8891", "FB", "Marketplace", "IG"})


class CreativeMediaAction(StrEnum):
    ADD_AS_CREATIVE_ASSET = "ADD_AS_CREATIVE_ASSET"


@dataclass(frozen=True)
class CreativeMediaRef:
    creative_ref_id: str
    media_asset_id: str
    vehicle_instance_id: str
    target_column: str
    channels: tuple[str, ...]
    admitted_at: str


class CreativeMediaRepository(Protocol):
    def insert_immutable(self, ref: CreativeMediaRef) -> CreativeMediaRef: ...


def add_as_creative_asset(
    *, action: CreativeMediaAction, asset: MediaAsset, resolved_vehicle_instance_id: str,
    channels: tuple[str, ...], repository: CreativeMediaRepository,
) -> CreativeMediaRef:
    if action is not CreativeMediaAction.ADD_AS_CREATIVE_ASSET:
        raise MediaAdmissionError("CREATIVE_ACTION_INVALID")
    if not resolved_vehicle_instance_id.strip():
        raise MediaAdmissionError("CREATIVE_VEHICLE_IDENTITY_UNRESOLVED")
    if asset.source_lineage != resolved_vehicle_instance_id:
        raise MediaAdmissionError("CREATIVE_VEHICLE_LINEAGE_MISMATCH")
    if asset.truth_eligibility is not TruthEligibility.FORBIDDEN:
        raise MediaAdmissionError("CREATIVE_ADMISSION_REQUIRES_FORBIDDEN_TRUTH_LINEAGE")
    if not channels or set(channels) - CREATIVE_CHANNELS:
        raise MediaAdmissionError("CREATIVE_CHANNEL_UNSUPPORTED")
    ref_id = hashlib.sha256(
        f"{resolved_vehicle_instance_id}\0{asset.media_asset_id}".encode()
    ).hexdigest()
    ref = CreativeMediaRef(
        creative_ref_id=f"creative:{ref_id}", media_asset_id=asset.media_asset_id,
        vehicle_instance_id=resolved_vehicle_instance_id,
        target_column=CREATIVE_REFS_COLUMN, channels=tuple(sorted(set(channels))),
        admitted_at=datetime.now(UTC).isoformat(),
    )
    return repository.insert_immutable(ref)


def original_media_ref(asset: MediaAsset) -> str:
    if asset.truth_eligibility is TruthEligibility.FORBIDDEN:
        raise MediaAdmissionError("CREATIVE_CANNOT_ENTER_ORIGINAL_MEDIA_REFS")
    return asset.media_asset_id


class CreativeXlsxMutationBuilder:
    """Only an existing resolved row's dedicated sales-material reference cell may change."""

    def build(self, preimage: bytes, ref: CreativeMediaRef, *, ai_row: int) -> bytes:
        book = _Workbook.parse(preimage)
        ai = book.root(AI_SHEET)
        header = _header(ai, book.shared)
        identity_col = header.get("VEHICLE_INSTANCE_ID")
        creative_col = header.get(CREATIVE_REFS_COLUMN)
        if identity_col is None or creative_col is None:
            raise WorkbenchConflict("HOLD_CREATIVE_REFS_COLUMN_MISSING")
        matches = [candidate for candidate in _rows(ai)[1:]
                   if (cell := _cell(candidate, identity_col)) is not None
                   and _cell_value(cell, book.shared) == ref.vehicle_instance_id]
        if len(matches) != 1 or matches[0] is not _row(ai, ai_row):
            raise WorkbenchConflict("HOLD_CREATIVE_VEHICLE_IDENTITY_AMBIGUOUS")
        target = _cell(matches[0], creative_col, create=True)
        current = _cell_value(target, book.shared)
        try:
            ids = json.loads(current) if current else []
        except json.JSONDecodeError as exc:
            raise WorkbenchConflict("HOLD_CREATIVE_REFS_INVALID") from exc
        if not isinstance(ids, list) or any(not isinstance(item, str) for item in ids):
            raise WorkbenchConflict("HOLD_CREATIVE_REFS_INVALID")
        if ref.creative_ref_id in ids:
            return preimage
        ids.append(ref.creative_ref_id)
        _set_cell(target, json.dumps(ids, ensure_ascii=False, separators=(",", ":")))
        output = book.render({book.sheets[AI_SHEET]: ai})
        self.verify(preimage, output, ref, ai_row=ai_row)
        return output

    def verify(self, preimage: bytes, output: bytes, ref: CreativeMediaRef, *, ai_row: int) -> None:
        before, after = _Workbook.parse(preimage), _Workbook.parse(output)
        if list(before.entries) != list(after.entries) or before.sheets != after.sheets:
            raise WorkbenchConflict("HOLD_WORKBOOK_TOPOLOGY_CHANGED")
        ai_path = before.sheets[AI_SHEET]
        if any(before.entries[name] != after.entries[name] for name in before.entries if name != ai_path):
            raise WorkbenchConflict("HOLD_UNRELATED_WORKBOOK_ENTRY_CHANGED")
        old_ai, new_ai = before.root(AI_SHEET), after.root(AI_SHEET)
        old_rows, new_rows = _rows(old_ai), _rows(new_ai)
        if [row.get("r") for row in old_rows] != [row.get("r") for row in new_rows]:
            raise WorkbenchConflict("HOLD_VEHICLE_ROW_TOPOLOGY_CHANGED")
        header = _header(old_ai, before.shared)
        creative_col = header.get(CREATIVE_REFS_COLUMN)
        identity_col = header.get("VEHICLE_INSTANCE_ID")
        if creative_col is None or identity_col is None:
            raise WorkbenchConflict("HOLD_CREATIVE_REFS_COLUMN_MISSING")
        for old_row, new_row in zip(old_rows, new_rows, strict=True):
            if old_row.get("r") != str(ai_row):
                if ET.tostring(old_row) != ET.tostring(new_row):
                    raise WorkbenchConflict("HOLD_UNRELATED_VEHICLE_ROW_CHANGED")
                continue
            old_values = _values(old_row, before.shared)
            new_values = _values(new_row, after.shared)
            if old_values.get(identity_col) != ref.vehicle_instance_id or (
                new_values.get(identity_col) != ref.vehicle_instance_id
            ):
                raise WorkbenchConflict("HOLD_CREATIVE_VEHICLE_IDENTITY_AMBIGUOUS")
            changed = {col for col in old_values.keys() | new_values.keys()
                       if old_values.get(col, "") != new_values.get(col, "")}
            if changed != {creative_col}:
                raise WorkbenchConflict("HOLD_UNADMITTED_CELL_CHANGED")
            old_cells = {cell.get("r"): cell for cell in old_row.findall("{*}c")}
            new_cells = {cell.get("r"): cell for cell in new_row.findall("{*}c")}
            for cell_ref in old_cells.keys() | new_cells.keys():
                if cell_ref != f"{_column_letters(creative_col)}{ai_row}":
                    old_cell, new_cell = old_cells.get(cell_ref), new_cells.get(cell_ref)
                    if old_cell is None or new_cell is None or ET.tostring(old_cell) != ET.tostring(new_cell):
                        raise WorkbenchConflict("HOLD_UNADMITTED_CELL_CHANGED")
            try:
                refs = json.loads(new_values[creative_col])
            except (KeyError, json.JSONDecodeError) as exc:
                raise WorkbenchConflict("HOLD_CREATIVE_REFS_INVALID") from exc
            if ref.creative_ref_id not in refs:
                raise WorkbenchConflict("HOLD_CREATIVE_REF_READBACK_MISMATCH")


def _column_letters(column: int) -> str:
    letters = ""
    while column:
        column, digit = divmod(column - 1, 26)
        letters = chr(65 + digit) + letters
    return letters


class CreativeMediaCompletionHandler:
    """Separate same-file creative write; never passes through verified vehicle delta."""

    def __init__(
        self, *, writer: DriveXlsxWorkbenchPort | None,
        builder: CreativeXlsxMutationBuilder | None = None,
    ) -> None:
        self.writer = writer
        self.builder = builder or CreativeXlsxMutationBuilder()

    def consume(self, *, task_id: str, ref: CreativeMediaRef, ai_row: int) -> PersistenceReceipt:
        def terminal(state: PersistenceDisposition, blocker: str | None = None) -> PersistenceReceipt:
            return PersistenceReceipt(
                state=state, task_id=task_id, file_id=CANONICAL_WORKBENCH_FILE_ID,
                blocker=blocker,
            )

        if not ref.vehicle_instance_id or ref.target_column != CREATIVE_REFS_COLUMN or ai_row < 2:
            return terminal(PersistenceDisposition.HOLD_CONFLICT, "CREATIVE_REF_INVALID")
        if self.writer is None or self.writer.file_id != CANONICAL_WORKBENCH_FILE_ID:
            return terminal(
                PersistenceDisposition.PERSISTENCE_CAPABILITY_DEBT, "WORKBENCH_WRITER_UNAVAILABLE",
            )
        digest = hashlib.sha256(
            f"{ref.creative_ref_id}\0{ref.vehicle_instance_id}\0{ai_row}".encode()
        ).hexdigest()
        try:
            receipt = self.writer.mutate(
                task_id=task_id, intent_sha256=digest,
                build_new_bytes=lambda preimage: self.builder.build(preimage, ref, ai_row=ai_row),
                verify_mutation=lambda preimage, output: self.builder.verify(
                    preimage, output, ref, ai_row=ai_row,
                ) if preimage != output else None,
            )
        except (WorkbenchConflict, WorkbenchPostwriteMismatch) as exc:
            return terminal(PersistenceDisposition.HOLD_CONFLICT, str(exc))
        except (WorkbenchCapabilityDebt, OSError, TimeoutError) as exc:
            return terminal(PersistenceDisposition.PERSISTENCE_CAPABILITY_DEBT, type(exc).__name__)
        if receipt.state not in {"WRITE_AND_READBACK_PASS", "NO_DELTA"}:
            return terminal(PersistenceDisposition.HOLD_CONFLICT, "CREATIVE_WRITE_RECEIPT_INVALID")
        return PersistenceReceipt(
            state=PersistenceDisposition(receipt.state), task_id=task_id,
            file_id=receipt.file_id, preimage_version=receipt.preimage_version,
            preimage_sha256=receipt.preimage_sha256,
            postwrite_version=receipt.postwrite_version,
            postwrite_sha256=receipt.postwrite_sha256,
        )
