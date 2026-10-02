"""App-owned authoritative public-Copy finalizer.

DRAFT task state may be proposed by a model/tool, but gains authority only after
an out-of-band user confirmation POST to the app-owned confirmation surface.
Confirmed snapshots are immutable. Final customer Copy is served only from the
app result surface after an exact-candidate, fail-closed evaluator PASS.
"""
from __future__ import annotations

import hashlib
import html
import json
import secrets
import sqlite3
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, model_validator


class SnapshotState(StrEnum):
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"


class GuardDecision(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"


class GuardCheck(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"


class PublicCopyField(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1)
    value: str = Field(min_length=1)


class PublicCopyCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fields: tuple[PublicCopyField, ...]

    @model_validator(mode="after")
    def validate_unique_labels(self) -> PublicCopyCandidate:
        labels = [item.label for item in self.fields]
        if len(labels) != len(set(labels)):
            raise ValueError("candidate field labels must be unique")
        return self


class PublicCopySnapshotInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_surface: str = Field(min_length=1)
    copy_scope: str = Field(min_length=1)
    user_request: str = Field(min_length=1)
    requested_fields: tuple[str, ...] = Field(min_length=1)
    hard_requirements: tuple[str, ...] = ()
    active_exclusions: tuple[str, ...] = ()
    structured_fields_already_exposed: tuple[str, ...] = ()
    verified_public_facts: tuple[str, ...] = ()
    required_material_disclosures: tuple[str, ...] = ()
    internal_only_unknowns: tuple[str, ...] = ()
    voice_contract: tuple[str, ...] = ()
    max_supporting_points: int = Field(default=4, ge=1, le=12)
    authority_revisions: dict[str, str] = Field(default_factory=dict)
    evidence_refs: tuple[str, ...] = ()
    generation: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def validate_requested_fields(self) -> PublicCopySnapshotInput:
        if len(self.requested_fields) != len(set(self.requested_fields)):
            raise ValueError("requested_fields must be unique")
        return self


class AppOwnedPublicCopySnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_handle: str = Field(min_length=32)
    snapshot: PublicCopySnapshotInput
    snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    state: SnapshotState
    confirmation_nonce: str = Field(min_length=32)
    created_at: datetime
    confirmed_at: datetime | None = None


class PublicCopyGuardReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: GuardDecision
    candidate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    requested_field_shape: GuardCheck
    claim_safety: GuardCheck
    internal_unknown_suppression: GuardCheck
    structured_field_redundancy: GuardCheck
    supporting_point_minimization: GuardCheck
    native_seller_voice: GuardCheck
    material_disclosure: GuardCheck
    blocker_codes: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    evaluator_run_id: str | None = None
    evaluator_model: str | None = None

    @model_validator(mode="after")
    def validate_decision_consistency(self) -> PublicCopyGuardReceipt:
        checks = (
            self.requested_field_shape,
            self.claim_safety,
            self.internal_unknown_suppression,
            self.structured_field_redundancy,
            self.supporting_point_minimization,
            self.native_seller_voice,
            self.material_disclosure,
        )
        if self.decision is GuardDecision.PASS:
            if any(item is not GuardCheck.PASS for item in checks):
                raise ValueError("PASS requires every guard check to PASS")
            if self.blocker_codes or self.reasons:
                raise ValueError("PASS may not carry blockers or unresolved reasons")
        elif not self.blocker_codes:
            raise ValueError("FAIL requires at least one blocker code")
        return self


class PublicCopyFinalizationReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    receipt_id: str = Field(min_length=32)
    task_handle: str = Field(min_length=32)
    snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: GuardDecision
    guard_receipt: PublicCopyGuardReceipt
    final_output: PublicCopyCandidate | None = None
    created_at: datetime

    @model_validator(mode="after")
    def validate_final_output(self) -> PublicCopyFinalizationReceipt:
        if self.decision is GuardDecision.PASS and self.final_output is None:
            raise ValueError("PASS requires exact final output")
        if self.decision is GuardDecision.FAIL and self.final_output is not None:
            raise ValueError("FAIL must not retain customer Copy")
        return self


class PublicCopyGuard(Protocol):
    def evaluate(
        self,
        *,
        snapshot: AppOwnedPublicCopySnapshot,
        candidate: PublicCopyCandidate,
        candidate_digest: str,
    ) -> PublicCopyGuardReceipt: ...


def canonical_json(value: Any) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class SQLitePublicCopyFinalizerStore:
    """Uses the incumbent SQLite substrate; no second external state service is created."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS public_copy_task_snapshot (
                    task_handle TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    snapshot_digest TEXT NOT NULL,
                    state TEXT NOT NULL,
                    confirmation_nonce TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    confirmed_at TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS public_copy_finalization (
                    receipt_id TEXT PRIMARY KEY,
                    task_handle TEXT NOT NULL,
                    snapshot_digest TEXT NOT NULL,
                    candidate_digest TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    guard_receipt TEXT NOT NULL,
                    final_output TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def create_draft(self, value: PublicCopySnapshotInput) -> AppOwnedPublicCopySnapshot:
        now = datetime.now(UTC)
        snapshot = AppOwnedPublicCopySnapshot(
            task_handle=secrets.token_urlsafe(32),
            snapshot=value,
            snapshot_digest=sha256_json(value),
            state=SnapshotState.DRAFT,
            confirmation_nonce=secrets.token_urlsafe(32),
            created_at=now,
        )
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO public_copy_task_snapshot VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    snapshot.task_handle,
                    canonical_json(snapshot.snapshot),
                    snapshot.snapshot_digest,
                    snapshot.state.value,
                    snapshot.confirmation_nonce,
                    snapshot.created_at.isoformat(),
                    None,
                ),
            )
        return snapshot

    def load_snapshot(self, task_handle: str) -> AppOwnedPublicCopySnapshot:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload, snapshot_digest, state, confirmation_nonce, created_at, confirmed_at
                FROM public_copy_task_snapshot WHERE task_handle = ?
                """,
                (task_handle,),
            ).fetchone()
        if row is None:
            raise KeyError("PUBLIC_COPY_TASK_NOT_FOUND")
        payload, digest, state, nonce, created_at, confirmed_at = row
        snapshot = PublicCopySnapshotInput.model_validate_json(payload)
        if sha256_json(snapshot) != digest:
            raise RuntimeError("PUBLIC_COPY_SNAPSHOT_DIGEST_MISMATCH")
        return AppOwnedPublicCopySnapshot(
            task_handle=task_handle,
            snapshot=snapshot,
            snapshot_digest=digest,
            state=SnapshotState(state),
            confirmation_nonce=nonce,
            created_at=datetime.fromisoformat(created_at),
            confirmed_at=datetime.fromisoformat(confirmed_at) if confirmed_at else None,
        )

    def confirm(self, task_handle: str, confirmation_nonce: str) -> AppOwnedPublicCopySnapshot:
        snapshot = self.load_snapshot(task_handle)
        if not secrets.compare_digest(snapshot.confirmation_nonce, confirmation_nonce):
            raise PermissionError("PUBLIC_COPY_CONFIRMATION_NONCE_INVALID")
        if snapshot.state is SnapshotState.CONFIRMED:
            return snapshot
        confirmed_at = datetime.now(UTC)
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE public_copy_task_snapshot
                SET state = ?, confirmed_at = ?
                WHERE task_handle = ? AND state = ? AND snapshot_digest = ?
                """,
                (
                    SnapshotState.CONFIRMED.value,
                    confirmed_at.isoformat(),
                    task_handle,
                    SnapshotState.DRAFT.value,
                    snapshot.snapshot_digest,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("PUBLIC_COPY_CONFIRMATION_RACE")
        return self.load_snapshot(task_handle)

    def save_receipt(self, receipt: PublicCopyFinalizationReceipt) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO public_copy_finalization VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    receipt.receipt_id,
                    receipt.task_handle,
                    receipt.snapshot_digest,
                    receipt.candidate_digest,
                    receipt.decision.value,
                    canonical_json(receipt.guard_receipt),
                    canonical_json(receipt.final_output) if receipt.final_output is not None else None,
                    receipt.created_at.isoformat(),
                ),
            )

    def load_receipt(self, receipt_id: str) -> PublicCopyFinalizationReceipt:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT task_handle, snapshot_digest, candidate_digest, decision,
                       guard_receipt, final_output, created_at
                FROM public_copy_finalization WHERE receipt_id = ?
                """,
                (receipt_id,),
            ).fetchone()
        if row is None:
            raise KeyError("PUBLIC_COPY_RECEIPT_NOT_FOUND")
        task_handle, snapshot_digest, candidate_digest, decision, guard_json, output_json, created_at = row
        return PublicCopyFinalizationReceipt(
            receipt_id=receipt_id,
            task_handle=task_handle,
            snapshot_digest=snapshot_digest,
            candidate_digest=candidate_digest,
            decision=GuardDecision(decision),
            guard_receipt=PublicCopyGuardReceipt.model_validate_json(guard_json),
            final_output=(PublicCopyCandidate.model_validate_json(output_json) if output_json else None),
            created_at=datetime.fromisoformat(created_at),
        )


class UnavailablePublicCopyGuard:
    def __init__(self, blocker: str = "PUBLIC_COPY_FINALIZER_EVALUATOR_UNAVAILABLE"):
        self.blocker = blocker

    def evaluate(
        self,
        *,
        snapshot: AppOwnedPublicCopySnapshot,
        candidate: PublicCopyCandidate,
        candidate_digest: str,
    ) -> PublicCopyGuardReceipt:
        return PublicCopyGuardReceipt(
            decision=GuardDecision.FAIL,
            candidate_digest=candidate_digest,
            snapshot_digest=snapshot.snapshot_digest,
            requested_field_shape=GuardCheck.FAIL,
            claim_safety=GuardCheck.FAIL,
            internal_unknown_suppression=GuardCheck.FAIL,
            structured_field_redundancy=GuardCheck.FAIL,
            supporting_point_minimization=GuardCheck.FAIL,
            native_seller_voice=GuardCheck.FAIL,
            material_disclosure=GuardCheck.FAIL,
            blocker_codes=(self.blocker,),
            reasons=("Evaluator is not configured; fail closed.",),
        )


class _ModelGuardPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: GuardDecision
    candidate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    requested_field_shape: GuardCheck
    claim_safety: GuardCheck
    internal_unknown_suppression: GuardCheck
    structured_field_redundancy: GuardCheck
    supporting_point_minimization: GuardCheck
    native_seller_voice: GuardCheck
    material_disclosure: GuardCheck
    blocker_codes: tuple[str, ...]
    reasons: tuple[str, ...]


class OpenAIPublicCopyGuard:
    def __init__(self, *, model: str, api_key: SecretStr, client: Any | None = None):
        self.model = model.strip()
        secret = api_key.get_secret_value().strip()
        if not self.model or not secret:
            raise ValueError("public Copy finalizer evaluator is incompletely configured")
        self.client = client if client is not None else OpenAI(api_key=secret)

    def evaluate(
        self,
        *,
        snapshot: AppOwnedPublicCopySnapshot,
        candidate: PublicCopyCandidate,
        candidate_digest: str,
    ) -> PublicCopyGuardReceipt:
        evaluator_input = {
            "purpose": "APP_OWNED_PUBLIC_COPY_FINALIZER",
            "snapshot": snapshot.snapshot.model_dump(mode="json"),
            "snapshot_digest": snapshot.snapshot_digest,
            "candidate": candidate.model_dump(mode="json"),
            "candidate_digest": candidate_digest,
            "required_checks": [
                "requested_field_shape: exact requested field labels only, in the requested order",
                (
                    "claim_safety: every affirmative factual claim must be supported by "
                    "verified_public_facts or explicit user creative authority in hard_requirements"
                ),
                (
                    "internal_unknown_suppression: internal_only_unknowns/provenance/audit language "
                    "must not be serialized unless a hard requirement or required disclosure makes "
                    "it customer-relevant"
                ),
                (
                    "structured_field_redundancy: already exposed structured facts must not be "
                    "mechanically replayed without a new decision role"
                ),
                (
                    "supporting_point_minimization: avoid feature soup; supporting points must stay "
                    "within max_supporting_points unless required_material_disclosures force more"
                ),
                (
                    "native_seller_voice: public prose must read like natural customer-facing seller "
                    "copy, not consultant/AI narration, taxonomy, audit report, or meta "
                    "selling-strategy explanation"
                ),
                "material_disclosure: required_material_disclosures must not be hidden or softened away",
            ],
            "pass_rule": (
                "PASS only if every required check passes and there are no blockers or unresolved "
                "reasons."
            ),
        }
        try:
            response = self.client.responses.create(
                model=self.model,
                input=canonical_json(evaluator_input),
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "app_owned_public_copy_guard",
                        "strict": True,
                        "schema": _ModelGuardPayload.model_json_schema(),
                    }
                },
            )
            if getattr(response, "status", None) != "completed":
                raise RuntimeError("PUBLIC_COPY_FINALIZER_EVALUATOR_INCOMPLETE")
            payload = _ModelGuardPayload.model_validate_json(getattr(response, "output_text", ""))
        except (ValidationError, ValueError, TypeError, RuntimeError, json.JSONDecodeError):
            return UnavailablePublicCopyGuard("PUBLIC_COPY_FINALIZER_EVALUATOR_FAILED").evaluate(
                snapshot=snapshot,
                candidate=candidate,
                candidate_digest=candidate_digest,
            )
        if (
            payload.candidate_digest != candidate_digest
            or payload.snapshot_digest != snapshot.snapshot_digest
        ):
            return UnavailablePublicCopyGuard("PUBLIC_COPY_FINALIZER_BINDING_MISMATCH").evaluate(
                snapshot=snapshot,
                candidate=candidate,
                candidate_digest=candidate_digest,
            )
        return PublicCopyGuardReceipt(
            **payload.model_dump(),
            evaluator_run_id=getattr(response, "id", None),
            evaluator_model=getattr(response, "model", None) or self.model,
        )


class AppOwnedPublicCopyFinalizer:
    def __init__(self, *, store: SQLitePublicCopyFinalizerStore, guard: PublicCopyGuard):
        self.store = store
        self.guard = guard

    def create_draft(self, value: PublicCopySnapshotInput) -> AppOwnedPublicCopySnapshot:
        return self.store.create_draft(value)

    def confirm(self, task_handle: str, confirmation_nonce: str) -> AppOwnedPublicCopySnapshot:
        return self.store.confirm(task_handle, confirmation_nonce)

    def finalize(self, task_handle: str, candidate: PublicCopyCandidate) -> PublicCopyFinalizationReceipt:
        snapshot = self.store.load_snapshot(task_handle)
        if snapshot.state is not SnapshotState.CONFIRMED:
            raise PermissionError("PUBLIC_COPY_TASK_CONFIRMATION_REQUIRED")
        expected_labels = snapshot.snapshot.requested_fields
        actual_labels = tuple(item.label for item in candidate.fields)
        if actual_labels != expected_labels:
            guard_receipt = PublicCopyGuardReceipt(
                decision=GuardDecision.FAIL,
                candidate_digest=sha256_json(candidate),
                snapshot_digest=snapshot.snapshot_digest,
                requested_field_shape=GuardCheck.FAIL,
                claim_safety=GuardCheck.FAIL,
                internal_unknown_suppression=GuardCheck.FAIL,
                structured_field_redundancy=GuardCheck.FAIL,
                supporting_point_minimization=GuardCheck.FAIL,
                native_seller_voice=GuardCheck.FAIL,
                material_disclosure=GuardCheck.FAIL,
                blocker_codes=("PUBLIC_COPY_REQUESTED_FIELD_SHAPE_MISMATCH",),
                reasons=(f"expected {expected_labels!r}, received {actual_labels!r}",),
            )
        else:
            candidate_digest = sha256_json(candidate)
            guard_receipt = self.guard.evaluate(
                snapshot=snapshot,
                candidate=candidate,
                candidate_digest=candidate_digest,
            )
        candidate_digest = sha256_json(candidate)
        if (
            guard_receipt.candidate_digest != candidate_digest
            or guard_receipt.snapshot_digest != snapshot.snapshot_digest
        ):
            guard_receipt = UnavailablePublicCopyGuard("PUBLIC_COPY_FINALIZER_BINDING_MISMATCH").evaluate(
                snapshot=snapshot,
                candidate=candidate,
                candidate_digest=candidate_digest,
            )
        decision = guard_receipt.decision
        receipt = PublicCopyFinalizationReceipt(
            receipt_id=str(uuid4()),
            task_handle=task_handle,
            snapshot_digest=snapshot.snapshot_digest,
            candidate_digest=candidate_digest,
            decision=decision,
            guard_receipt=guard_receipt,
            final_output=candidate if decision is GuardDecision.PASS else None,
            created_at=datetime.now(UTC),
        )
        self.store.save_receipt(receipt)
        return receipt


def confirmation_page(snapshot: AppOwnedPublicCopySnapshot) -> str:
    data = snapshot.snapshot
    nonce = html.escape(snapshot.confirmation_nonce)

    def rows(values: tuple[str, ...]) -> str:
        return "".join(f"<li>{html.escape(value)}</li>" for value in values) or "<li>None</li>"
    return f"""<!doctype html><html><meta charset='utf-8'><title>Confirm public Copy task</title>
<body><h1>Confirm public Copy task</h1>
<p><strong>Surface:</strong> {html.escape(data.target_surface)}</p>
<p><strong>Scope:</strong> {html.escape(data.copy_scope)}</p>
<p><strong>User request:</strong> {html.escape(data.user_request)}</p>
<p><strong>Requested fields:</strong> {html.escape(', '.join(data.requested_fields))}</p>
<h2>Hard requirements</h2><ul>{rows(data.hard_requirements)}</ul>
<h2>Active exclusions</h2><ul>{rows(data.active_exclusions)}</ul>
<h2>Verified public facts</h2><ul>{rows(data.verified_public_facts)}</ul>
<h2>Required material disclosures</h2><ul>{rows(data.required_material_disclosures)}</ul>
<h2>Internal-only unknowns</h2><ul>{rows(data.internal_only_unknowns)}</ul>
<h2>Voice contract</h2><ul>{rows(data.voice_contract)}</ul>
<form method='post'><input type='hidden' name='confirmation_nonce' value='{nonce}'>
<button type='submit'>Confirm and lock this task</button></form></body></html>"""


def result_page(receipt: PublicCopyFinalizationReceipt) -> str:
    if receipt.decision is not GuardDecision.PASS or receipt.final_output is None:
        raise PermissionError("PUBLIC_COPY_RESULT_NOT_AVAILABLE")
    blocks = "".join(
        f"<h2>{html.escape(item.label)}</h2><pre>{html.escape(item.value)}</pre>"
        for item in receipt.final_output.fields
    )
    return (
        "<!doctype html><html><meta charset='utf-8'><title>Final public Copy</title>"
        f"<body><h1>Final public Copy</h1>{blocks}</body></html>"
    )
