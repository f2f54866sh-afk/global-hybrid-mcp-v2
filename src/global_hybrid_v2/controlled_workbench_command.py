"""Direct App command: resolve one document against one XLSX preimage, then commit."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import uuid4

from global_hybrid_v2.adapters.controlled_sales_entry import EntryResult
from global_hybrid_v2.adapters.drive_xlsx_workbench import (
    DriveTransport,
    WorkbenchCapabilityDebt,
    WorkbenchConflict,
)
from global_hybrid_v2.company_commercial_completion import CompanyCommercialCompletionHandler
from global_hybrid_v2.contracts import PersistenceDisposition
from global_hybrid_v2.trusted_workbench_intent import (
    EvidenceBindingState,
    EvidenceReceiptSigner,
    TrustedWorkbenchEvidenceReceipt,
    TrustedWorkbenchIntentProducer,
)
from global_hybrid_v2.workbench_mutation import (
    AI_SHEET,
    PROTECTED_FIELDS,
    _cell,
    _cell_value,
    _header,
    _rows,
    _Workbook,
)
from global_hybrid_v2.workbench_target import WorkbenchTargetBinding

REGISTRATION_FIELDS = frozenset({
    "VIN/車身號碼", "車牌", "排氣量_Canonical", "排氣量單位", "燃料_Canonical",
    "座位數_Canonical", "出廠年月", "原發照日期", "換補照日期", "文件Refs", "證據/缺口摘要",
})
_VIN = re.compile(r"[A-HJ-NPR-Z0-9]{17}")
_PLATE = re.compile(r"[A-Z0-9-]{4,12}")


def _request_digest(request_text: str) -> str:
    payload = json.dumps({"request_text": request_text}, ensure_ascii=False,
                         sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


class EvidenceInterpreterPort(Protocol):
    def interpret(self, *, request_text: str, evidence_bytes: bytes,
                  mime_type: str) -> dict[str, Any]: ...


@dataclass(frozen=True)
class WorkbenchRow:
    ai_row: int
    vehicle_instance_id: str
    fields: dict[str, str]


@dataclass(frozen=True)
class WorkbenchSnapshot:
    file_id: str
    version: str
    sha256: str
    rows: tuple[WorkbenchRow, ...]
    headers: frozenset[str]


class WorkbenchSnapshotReader:
    def __init__(self, *, drive: DriveTransport, target: WorkbenchTargetBinding) -> None:
        self.drive = drive
        self.target = target

    def read(self) -> WorkbenchSnapshot:
        file_id = self.target.file_id
        meta = self.drive.metadata(file_id)
        if meta.get("id") != file_id:
            raise WorkbenchConflict("HOLD_WORKBENCH_TARGET_ID_MISMATCH")
        version = str(meta.get("version") or "")
        if not version:
            raise WorkbenchCapabilityDebt("DRIVE_VERSION_UNAVAILABLE")
        raw = self.drive.download(file_id)
        book = _Workbook.parse(raw)
        root = book.root(AI_SHEET)
        header = _header(root, book.shared)
        if "VEHICLE_INSTANCE_ID" not in header:
            raise WorkbenchConflict("HOLD_VEHICLE_ID_COLUMN_MISSING")
        safe = REGISTRATION_FIELDS | {"VEHICLE_INSTANCE_ID"}
        rows = []
        for row in _rows(root)[1:]:
            values = {}
            for name in safe & header.keys():
                cell = _cell(row, header[name])
                values[name] = "" if cell is None else _cell_value(cell, book.shared)
            if values.get("VEHICLE_INSTANCE_ID"):
                rows.append(WorkbenchRow(
                    int(row.get("r") or 0), values["VEHICLE_INSTANCE_ID"], values,
                ))
        return WorkbenchSnapshot(file_id, version, hashlib.sha256(raw).hexdigest(),
                                 tuple(rows), frozenset(header))


class ControlledEvidenceResolver(Protocol):
    def resolve(self, *, request_text: str, evidence_bytes: bytes, mime_type: str,
                workbench_snapshot: WorkbenchSnapshot,
                task_scope: str) -> TrustedWorkbenchEvidenceReceipt: ...


class RegistrationDocumentResolver:
    def __init__(self, *, interpreter: EvidenceInterpreterPort | None,
                 signer: EvidenceReceiptSigner) -> None:
        self.interpreter = interpreter
        self.signer = signer

    def resolve(self, *, request_text: str, evidence_bytes: bytes, mime_type: str,
                workbench_snapshot: WorkbenchSnapshot,
                task_scope: str) -> TrustedWorkbenchEvidenceReceipt:
        if mime_type != "application/pdf" or not evidence_bytes.startswith(b"%PDF-"):
            raise WorkbenchCapabilityDebt("REGISTRATION_DOCUMENT_ONLY")
        if self.interpreter is None:
            raise WorkbenchCapabilityDebt("EVIDENCE_INTERPRETER_UNAVAILABLE")
        candidate = self.interpreter.interpret(
            request_text=request_text, evidence_bytes=evidence_bytes, mime_type=mime_type,
        )
        if not isinstance(candidate, dict) or set(candidate) & PROTECTED_FIELDS or (
            set(candidate) - REGISTRATION_FIELDS
        ):
            raise WorkbenchConflict("HOLD_DOCUMENT_FIELD_UNADMITTED")
        fields = {key: str(value).strip() for key, value in candidate.items()
                  if value is not None and str(value).strip()}
        vin, plate = fields.get("VIN/車身號碼"), fields.get("車牌")
        if vin and not _VIN.fullmatch(vin):
            raise WorkbenchConflict("HOLD_DOCUMENT_VIN_INVALID")
        if plate and not _PLATE.fullmatch(plate):
            raise WorkbenchConflict("HOLD_DOCUMENT_PLATE_INVALID")
        if not vin and not plate:
            raise WorkbenchConflict("HOLD_VEHICLE_IDENTITY_UNRESOLVED")
        vin_rows = (
            [row for row in workbench_snapshot.rows if row.fields.get("VIN/車身號碼") == vin]
            if vin else []
        )
        plate_rows = (
            [row for row in workbench_snapshot.rows if row.fields.get("車牌") == plate]
            if plate else []
        )
        matches = vin_rows if vin else plate_rows
        if vin and plate and (len(vin_rows) != 1 or len(plate_rows) != 1
                              or vin_rows[0] != plate_rows[0]):
            raise WorkbenchConflict("HOLD_VEHICLE_IDENTITY_CONFLICT")
        if len(matches) != 1:
            raise WorkbenchConflict("HOLD_VEHICLE_IDENTITY_AMBIGUOUS")
        row = matches[0]
        delta = {key: value for key, value in fields.items()
                 if key in workbench_snapshot.headers and row.fields.get(key, "") != value}
        now = datetime.now(UTC)
        evidence_sha = hashlib.sha256(evidence_bytes).hexdigest()
        return self.signer.sign({
            "receipt_id": uuid4().hex, "task_scope": task_scope,
            "vehicle_instance_id": row.vehicle_instance_id, "ai_row": row.ai_row,
            "binding_state": EvidenceBindingState.SAFE_ATTRIBUTABLE,
            "verified_delta": delta, "evidence_refs": (f"sha256:{evidence_sha}",),
            "identity_sources": ("CANONICAL_WORKBENCH", "RAW_EVIDENCE"),
            "request_digest": _request_digest(request_text),
            "evidence_digest": evidence_sha,
            "workbench_file_id": workbench_snapshot.file_id,
            "workbench_preimage_version": workbench_snapshot.version,
            "workbench_preimage_sha256": workbench_snapshot.sha256,
            "issued_at": now, "valid_until": now + timedelta(minutes=4),
        })


class ControlledWorkbenchCommandHandler:
    def __init__(self, *, target: WorkbenchTargetBinding,
                 snapshot_reader: WorkbenchSnapshotReader,
                 resolver: ControlledEvidenceResolver,
                 producer: TrustedWorkbenchIntentProducer,
                 completion: CompanyCommercialCompletionHandler) -> None:
        if (snapshot_reader.target != target or producer.target != target
            or completion.target != target):
            raise ValueError("CONTROLLED_COMMAND_TARGET_BINDING_MISMATCH")
        self.target = target
        self.snapshot_reader = snapshot_reader
        self.resolver = resolver
        self.producer = producer
        self.completion = completion

    def execute(self, *, request_text: str, evidence_bytes: bytes,
                mime_type: str) -> EntryResult:
        task_id = uuid4().hex
        task_scope = f"app-command:{task_id}"
        try:
            snapshot = self.snapshot_reader.read()
            receipt = self.resolver.resolve(
                request_text=request_text, evidence_bytes=evidence_bytes,
                mime_type=mime_type, workbench_snapshot=snapshot, task_scope=task_scope,
            )
            self.producer.verifier.verify(receipt)
            if (receipt.task_scope != task_scope or receipt.workbench_file_id != snapshot.file_id
                or receipt.workbench_preimage_version != snapshot.version
                or receipt.workbench_preimage_sha256 != snapshot.sha256
                or receipt.evidence_digest != hashlib.sha256(evidence_bytes).hexdigest()
                or receipt.request_digest != _request_digest(request_text)):
                raise WorkbenchConflict("HOLD_DOCUMENT_BINDING_MISMATCH")
            intent = self.producer.compile(receipt=receipt, expected_task_scope=task_scope)
            fresh = self.snapshot_reader.read()
            if fresh.version != snapshot.version or fresh.sha256 != snapshot.sha256:
                raise WorkbenchConflict("HOLD_STALE_PREIMAGE")
            terminal = self.completion.consume(task_id=task_id, intent=intent)
        except WorkbenchCapabilityDebt:
            return EntryResult("TERMINAL", PersistenceDisposition.PERSISTENCE_CAPABILITY_DEBT.value,
                               "文件證據解讀或 AI 車源表同步能力目前不可用。")
        except WorkbenchConflict as exc:
            if str(exc) == "HOLD_STALE_PREIMAGE":
                return EntryResult("TERMINAL", PersistenceDisposition.HOLD_CONFLICT.value,
                                   "HOLD_STALE_PREIMAGE")
            return EntryResult("TERMINAL", PersistenceDisposition.HOLD_CONFLICT.value,
                               "車輛或文件證據衝突，AI 車源表同步已暫停。")
        except Exception:
            return EntryResult("EXECUTION_FAIL", None, "AI 車源表同步未完成。")
        state = terminal.state
        if state is PersistenceDisposition.WRITE_AND_READBACK_PASS:
            if (terminal.file_id != self.target.file_id or not terminal.postwrite_version
                or not terminal.postwrite_sha256):
                return EntryResult("EXECUTION_FAIL", None, "AI 車源表同步未完成。")
            return EntryResult("TERMINAL", state.value, "公司車資料已寫入並讀回確認。")
        if state is PersistenceDisposition.NO_DELTA:
            return EntryResult("TERMINAL", state.value, "沒有新的 AI 車源表變更。")
        if state is PersistenceDisposition.PERSISTENCE_CAPABILITY_DEBT:
            return EntryResult("TERMINAL", state.value, "AI 車源表同步能力目前不可用。")
        if state is PersistenceDisposition.HOLD_CONFLICT:
            message = ("HOLD_STALE_PREIMAGE" if terminal.blocker == "HOLD_STALE_PREIMAGE"
                       else "車輛資料衝突，AI 車源表同步已暫停。")
            return EntryResult("TERMINAL", state.value, message)
        return EntryResult("EXECUTION_FAIL", None, "AI 車源表同步未完成。")
