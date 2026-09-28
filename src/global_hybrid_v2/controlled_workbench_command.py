"""Direct App command: resolve one document against one XLSX preimage, then commit."""
from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken

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
DISPLAY_FIELDS = frozenset({"年分", "年份", "年式", "品牌", "廠牌", "車型", "車色", "顏色"})
IDENTITY_HINT_FIELDS = frozenset({"year", "make", "model", "model_code", "color"})
HINT_COLUMNS = {"year": ("年分", "年份", "年式"), "make": ("品牌", "廠牌"),
                "model": ("車型",), "model_code": ("車型",), "color": ("車色", "顏色")}
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
        safe = REGISTRATION_FIELDS | DISPLAY_FIELDS | {"VEHICLE_INSTANCE_ID"}
        rows = []
        for row in _rows(root)[1:]:
            values = {}
            for name in safe & header.keys():
                cell = _cell(row, header[name])
                values[name] = "" if cell is None else _cell_value(cell, book.shared)
            rows.append(WorkbenchRow(
                int(row.get("r") or 0), values.get("VEHICLE_INSTANCE_ID", ""), values,
            ))
        return WorkbenchSnapshot(file_id, version, hashlib.sha256(raw).hexdigest(),
                                 tuple(rows), frozenset(header))


class ControlledEvidenceResolver(Protocol):
    def resolve(self, *, request_text: str, evidence_bytes: bytes, mime_type: str,
                workbench_snapshot: WorkbenchSnapshot,
                task_scope: str, selected_row: WorkbenchRow) -> TrustedWorkbenchEvidenceReceipt: ...


class SelectionTokenCodec:
    """Server-issued selection bound to one workbook preimage and one existing row."""

    def __init__(self, key: bytes) -> None:
        if len(key) < 32:
            raise ValueError("SELECTION_SIGNING_KEY_INVALID")
        self.cipher = Fernet(base64.urlsafe_b64encode(hashlib.sha256(key).digest()))

    def issue(self, snapshot: WorkbenchSnapshot, row: WorkbenchRow) -> str:
        now = int(datetime.now(UTC).timestamp())
        payload = {"file_id": snapshot.file_id, "version": snapshot.version,
                   "sha256": snapshot.sha256, "ai_row": row.ai_row,
                   "vehicle_instance_id": row.vehicle_instance_id,
                   "issued_at": now, "expiry": now + 300, "nonce": uuid4().hex}
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return self.cipher.encrypt(raw).decode()

    def resolve(self, token: str, snapshot: WorkbenchSnapshot) -> WorkbenchRow:
        try:
            raw = self.cipher.decrypt(token.encode(), ttl=300)
            payload = json.loads(raw)
            now = int(datetime.now(UTC).timestamp())
            if (payload["file_id"] != snapshot.file_id or payload["version"] != snapshot.version
                or payload["sha256"] != snapshot.sha256 or payload["issued_at"] > now
                or payload["expiry"] < now or payload["expiry"] - payload["issued_at"] > 300):
                raise ValueError("preimage")
            row = next(row for row in snapshot.rows if row.ai_row == payload["ai_row"])
            if row.vehicle_instance_id != payload["vehicle_instance_id"]:
                raise ValueError("identity")
            return row
        except (InvalidToken, ValueError, KeyError, TypeError, StopIteration):
            raise WorkbenchConflict("HOLD_STALE_PREIMAGE") from None


class RegistrationDocumentResolver:
    def __init__(self, *, interpreter: EvidenceInterpreterPort | None,
                 signer: EvidenceReceiptSigner) -> None:
        self.interpreter = interpreter
        self.signer = signer

    def resolve(self, *, request_text: str, evidence_bytes: bytes, mime_type: str,
                workbench_snapshot: WorkbenchSnapshot,
                task_scope: str, selected_row: WorkbenchRow) -> TrustedWorkbenchEvidenceReceipt:
        if mime_type != "application/pdf" or not evidence_bytes.startswith(b"%PDF-"):
            raise WorkbenchCapabilityDebt("REGISTRATION_DOCUMENT_ONLY")
        if self.interpreter is None:
            raise WorkbenchCapabilityDebt("EVIDENCE_INTERPRETER_UNAVAILABLE")
        candidate = self.interpreter.interpret(
            request_text=request_text, evidence_bytes=evidence_bytes, mime_type=mime_type,
        )
        if not isinstance(candidate, dict) or set(candidate) != {"identity_hints", "verified_delta"}:
            raise WorkbenchConflict("HOLD_DOCUMENT_FIELD_UNADMITTED")
        hints, offered = candidate["identity_hints"], candidate["verified_delta"]
        if (not isinstance(hints, dict) or not isinstance(offered, dict)
            or set(hints) - IDENTITY_HINT_FIELDS or set(offered) & PROTECTED_FIELDS
            or set(offered) - REGISTRATION_FIELDS):
            raise WorkbenchConflict("HOLD_DOCUMENT_FIELD_UNADMITTED")
        if any(isinstance(value, (dict, list, tuple, set, bool))
               or len(str(value)) > 2048 or any(ord(char) < 32 and char not in "\t\n"
                                                  for char in str(value))
               for value in offered.values() if value is not None):
            raise WorkbenchConflict("HOLD_DOCUMENT_FIELD_UNADMITTED")
        fields = {key: str(value).strip() for key, value in offered.items()
                  if value is not None and str(value).strip()}
        for numeric in ("排氣量_Canonical", "座位數_Canonical"):
            if numeric in fields and not fields[numeric].isdigit():
                raise WorkbenchConflict("HOLD_DOCUMENT_FIELD_UNADMITTED")
        for hint, value in hints.items():
            if value is None or not isinstance(value, str):
                raise WorkbenchConflict("HOLD_DOCUMENT_FIELD_UNADMITTED")
            known = next((selected_row.fields.get(name) for name in HINT_COLUMNS[hint]
                          if selected_row.fields.get(name)), "")
            if known and value.strip() and known.casefold().strip() != value.casefold().strip():
                raise WorkbenchConflict("HOLD_DOCUMENT_IDENTITY_MISMATCH")
        vin, plate = fields.get("VIN/車身號碼"), fields.get("車牌")
        if vin and not _VIN.fullmatch(vin):
            raise WorkbenchConflict("HOLD_DOCUMENT_VIN_INVALID")
        if plate and not _PLATE.fullmatch(plate):
            raise WorkbenchConflict("HOLD_DOCUMENT_PLATE_INVALID")
        row = selected_row
        for field, offered_value in (("VIN/車身號碼", vin), ("車牌", plate)):
            if not offered_value:
                continue
            if row.fields.get(field) and row.fields[field] != offered_value:
                raise WorkbenchConflict("HOLD_VEHICLE_IDENTITY_CONFLICT")
            if any(other.ai_row != row.ai_row and other.fields.get(field) == offered_value
                   for other in workbench_snapshot.rows):
                raise WorkbenchConflict("HOLD_VEHICLE_IDENTITY_CONFLICT")
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
                 completion: CompanyCommercialCompletionHandler,
                 selection_codec: SelectionTokenCodec) -> None:
        if (snapshot_reader.target != target or producer.target != target
            or completion.target != target):
            raise ValueError("CONTROLLED_COMMAND_TARGET_BINDING_MISMATCH")
        self.target = target
        self.snapshot_reader = snapshot_reader
        self.resolver = resolver
        self.producer = producer
        self.completion = completion
        self.selection_codec = selection_codec

    def list_candidates(self) -> list[dict[str, str]]:
        snapshot = self.snapshot_reader.read()
        candidates = []
        for row in snapshot.rows:
            if not row.vehicle_instance_id:
                continue
            label = " ".join(row.fields[name] for name in
                             ("年分", "年份", "年式", "品牌", "廠牌", "車型", "車色", "顏色")
                             if row.fields.get(name)) or f"公司車輛候選 {len(candidates) + 1}"
            candidates.append({"display_label": label,
                               "opaque_selection_token": self.selection_codec.issue(snapshot, row)})
        return candidates

    def execute(self, *, request_text: str, evidence_bytes: bytes,
                mime_type: str, target_selection_token: str | None = None) -> EntryResult:
        if not target_selection_token:
            return EntryResult("EXECUTION_FAIL", None, "TARGET_VEHICLE_SELECTION_REQUIRED")
        task_id = uuid4().hex
        task_scope = f"app-command:{task_id}"
        try:
            snapshot = self.snapshot_reader.read()
            selected_row = self.selection_codec.resolve(target_selection_token, snapshot)
            if not selected_row.vehicle_instance_id:
                raise WorkbenchCapabilityDebt("UNBOUND_OBSERVATION_INSTANCE_CREATION_CAPABILITY_DEBT")
            receipt = self.resolver.resolve(
                request_text=request_text, evidence_bytes=evidence_bytes,
                mime_type=mime_type, workbench_snapshot=snapshot, task_scope=task_scope,
                selected_row=selected_row,
            )
            self.producer.verifier.verify(receipt)
            if (receipt.task_scope != task_scope or receipt.workbench_file_id != snapshot.file_id
                or receipt.workbench_preimage_version != snapshot.version
                or receipt.workbench_preimage_sha256 != snapshot.sha256
                or receipt.evidence_digest != hashlib.sha256(evidence_bytes).hexdigest()
                or receipt.request_digest != _request_digest(request_text)
                or receipt.ai_row != selected_row.ai_row
                or receipt.vehicle_instance_id != selected_row.vehicle_instance_id):
                raise WorkbenchConflict("HOLD_DOCUMENT_BINDING_MISMATCH")
            intent = self.producer.compile(receipt=receipt, expected_task_scope=task_scope)
            fresh = self.snapshot_reader.read()
            if fresh.version != snapshot.version or fresh.sha256 != snapshot.sha256:
                raise WorkbenchConflict("HOLD_STALE_PREIMAGE")
            terminal = self.completion.consume(task_id=task_id, intent=intent)
        except WorkbenchCapabilityDebt as exc:
            return EntryResult("TERMINAL", PersistenceDisposition.PERSISTENCE_CAPABILITY_DEBT.value,
                               (str(exc) if str(exc) ==
                                "UNBOUND_OBSERVATION_INSTANCE_CREATION_CAPABILITY_DEBT"
                                else "文件證據解讀或 AI 車源表同步能力目前不可用。"))
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
