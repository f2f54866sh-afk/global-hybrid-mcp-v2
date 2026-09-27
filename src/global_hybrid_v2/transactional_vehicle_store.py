"""RD-021 candidate canonical transaction port; never binds a production database itself."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from global_hybrid_v2.contracts import PersistenceDisposition, PersistenceReceipt
from global_hybrid_v2.media_admission import FIELD_SCOPED_ALLOWED
from global_hybrid_v2.workbench_mutation import ALLOWED_FIELDS, PROTECTED_FIELDS


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


class CanonicalConflict(RuntimeError):
    pass


class CanonicalCapabilityDebt(RuntimeError):
    pass


@dataclass(frozen=True)
class FieldEvidence:
    field_name: str
    value_digest: str
    evidence_asset_id: str
    independent_evidence_root: str
    verification_state: str
    support_scope: tuple[str, ...]
    truth_eligibility: str
    provenance_class: str
    provenance_confidence: str
    extractor_revision: str
    verifier_revision: str

    def validate(self) -> None:
        if self.truth_eligibility not in {"FULL", "FIELD_SCOPED", "LIMITED"}:
            raise CanonicalConflict("HOLD_TRUTH_FORBIDDEN")
        if self.provenance_class in {"AI_GENERATED", "AI_EDITED", "COMPOSITED"}:
            raise CanonicalConflict("HOLD_CREATIVE_CANNOT_UPDATE_TRUTH")
        if self.provenance_confidence not in {"VERIFIED", "PARTIAL", "UNKNOWN"}:
            raise CanonicalConflict("HOLD_PROVENANCE_CONFIDENCE_INVALID")
        if self.provenance_class == "FIRST_OBSERVED_EXTERNAL" and self.provenance_confidence == "VERIFIED":
            raise CanonicalConflict("HOLD_FIRST_OBSERVED_NOT_ORIGINAL_VERIFIED")
        if self.field_name not in self.support_scope:
            raise CanonicalConflict("HOLD_FIELD_SUPPORT_SCOPE_MISMATCH")
        if self.truth_eligibility in {"FIELD_SCOPED", "LIMITED"} and self.field_name in {
            "VIN/車身號碼", "車牌", "實車身分狀態",
        }:
            raise CanonicalConflict("HOLD_IDENTITY_FIELD_REQUIRES_FULL_EVIDENCE")
        if self.truth_eligibility in {"FIELD_SCOPED", "LIMITED"} and (
            self.field_name not in FIELD_SCOPED_ALLOWED
        ):
            raise CanonicalConflict("HOLD_LIMITED_FIELD_NOT_VISIBLE_ADMISSIBLE")
        if not all((self.evidence_asset_id, self.independent_evidence_root,
                    self.extractor_revision, self.verifier_revision)):
            raise CanonicalConflict("HOLD_EVIDENCE_INCOMPLETE")


@dataclass(frozen=True)
class CanonicalMutation:
    mutation_id: str
    vehicle_instance_id: str
    expected_revision: int
    verified_delta: dict[str, Any]
    evidence: tuple[FieldEvidence, ...]
    request_id: str
    task_id: str
    identity_conflict: bool = False

    @property
    def payload_digest(self) -> str:
        return _digest({
            "vehicle_instance_id": self.vehicle_instance_id,
            "expected_revision": self.expected_revision,
            "verified_delta": self.verified_delta,
            "evidence": [item.__dict__ for item in self.evidence],
            "request_id": self.request_id,
            "task_id": self.task_id,
        })

    def validate(self) -> None:
        if not all((self.mutation_id, self.vehicle_instance_id, self.request_id, self.task_id)):
            raise CanonicalConflict("HOLD_MUTATION_IDENTITY_MISSING")
        if self.expected_revision < 0 or self.identity_conflict:
            raise CanonicalConflict("HOLD_VEHICLE_IDENTITY_CONFLICT")
        fields = set(self.verified_delta)
        if fields & PROTECTED_FIELDS or fields - ALLOWED_FIELDS:
            raise CanonicalConflict("HOLD_UNADMITTED_FIELD_MUTATION")
        if not self.verified_delta:
            return
        by_field: dict[str, list[FieldEvidence]] = {}
        for item in self.evidence:
            item.validate()
            by_field.setdefault(item.field_name, []).append(item)
        if set(by_field) != fields:
            raise CanonicalConflict("HOLD_FIELD_EVIDENCE_MISMATCH")
        for field, value in self.verified_delta.items():
            if any(item.value_digest != _digest(value) for item in by_field[field]):
                raise CanonicalConflict("HOLD_FIELD_VALUE_DIGEST_MISMATCH")


@dataclass(frozen=True)
class CanonicalReadback:
    vehicle_instance_id: str
    revision: int
    verified_state: dict[str, Any]
    durable_identity: dict[str, Any]
    source_snapshot: dict[str, Any]

    @property
    def current_state(self) -> dict[str, Any]:
        return {**self.source_snapshot, **self.verified_state}


@dataclass(frozen=True)
class CreativeProjectionRef:
    creative_ref_id: str
    media_asset_id: str
    channels: tuple[str, ...]


@dataclass(frozen=True)
class VehicleProjectionState:
    vehicle_instance_id: str
    canonical_revision: int
    source_snapshot: dict[str, Any]
    verified_state: dict[str, Any]
    original_media_refs: tuple[str, ...]
    creative_media_refs: tuple[CreativeProjectionRef, ...]
    original_media_cell: str

    @property
    def current_state(self) -> dict[str, Any]:
        fields = {**self.source_snapshot, **self.verified_state}
        fields["原始媒體Refs"] = self.original_media_cell
        fields["銷售素材Refs"] = _canonical([ref.creative_ref_id for ref in self.creative_media_refs])
        return fields


@dataclass(frozen=True)
class CreativeAdmission:
    admission_id: str
    vehicle_instance_id: str
    expected_revision: int
    media_asset_id: str
    independent_evidence_root: str
    provenance_class: str
    truth_eligibility: str
    channels: tuple[str, ...]
    request_id: str
    task_id: str

    @property
    def payload_digest(self) -> str:
        return _digest(self.__dict__)

    def validate(self) -> None:
        if not all((self.admission_id, self.vehicle_instance_id, self.media_asset_id,
                    self.independent_evidence_root, self.request_id, self.task_id)):
            raise CanonicalConflict("HOLD_CREATIVE_ADMISSION_INCOMPLETE")
        if self.truth_eligibility != "FORBIDDEN":
            raise CanonicalConflict("HOLD_CREATIVE_TRUTH_ELIGIBILITY_MISMATCH")
        if self.provenance_class not in {"AI_GENERATED", "AI_EDITED", "COMPOSITED"}:
            raise CanonicalConflict("HOLD_CREATIVE_PROVENANCE_MISMATCH")
        if not self.channels or set(self.channels) - {"8891", "FB", "Marketplace", "IG"}:
            raise CanonicalConflict("HOLD_CREATIVE_CHANNEL_UNSUPPORTED")


class VehicleStatePort(Protocol):
    def read_vehicle(self, vehicle_instance_id: str) -> CanonicalReadback | None: ...
    def read_projection_state(self, vehicle_instance_id: str) -> VehicleProjectionState | None: ...


class VehicleMutationPort(VehicleStatePort, Protocol):
    def commit_verified(self, mutation: CanonicalMutation) -> PersistenceReceipt: ...


class EvidenceReceiptPort(Protocol):
    def field_evidence(self, vehicle_instance_id: str, field_name: str) -> tuple[FieldEvidence, ...]: ...


class EvidenceAdmissionPort(Protocol):
    """Independent server-side media/evidence readback, never a candidate payload assertion."""

    def resolve(self, *, vehicle_instance_id: str, field_name: str,
                value_digest: str, evidence_asset_id: str) -> FieldEvidence | None: ...


class MediaLinkPort(Protocol):
    def admit_creative(self, admission: CreativeAdmission) -> PersistenceReceipt: ...


class _Sql:
    def __init__(self, connection: Any, dialect: str):
        self.connection, self.dialect = connection, dialect

    def execute(self, query: str, params: tuple[Any, ...] = ()) -> Any:
        if self.dialect == "postgres":
            query = query.replace("?", "%s")
        return self.connection.execute(query, params)

    def json(self, value: object) -> Any:
        if self.dialect == "postgres":
            from psycopg.types.json import Jsonb

            return Jsonb(value)
        return _canonical(value)


class TransactionalVehicleStore(VehicleMutationPort):
    """DB-API boundary; SQLite is isolated contract-test only, PostgreSQL is the candidate target."""

    def __init__(self, connect: Callable[[], Any], *, dialect: str = "postgres",
                 evidence_admission: EvidenceAdmissionPort | None = None):
        if dialect not in {"postgres", "sqlite_test"}:
            raise ValueError("unsupported canonical store dialect")
        self.connect, self.dialect = connect, dialect
        self.evidence_admission = evidence_admission

    @classmethod
    def postgres_candidate(cls, dsn: str, *, evidence_admission: EvidenceAdmissionPort
                           ) -> TransactionalVehicleStore:
        """Explicit candidate binding; callers must supply an admitted DSN, never a fallback."""
        if not dsn.strip():
            raise CanonicalCapabilityDebt("POSTGRES_DSN_NOT_BOUND")
        import psycopg

        return cls(lambda: psycopg.connect(dsn, autocommit=False), dialect="postgres",
                   evidence_admission=evidence_admission)

    def _open(self) -> Any:
        try:
            return self.connect()
        except Exception as exc:
            raise CanonicalCapabilityDebt("CANONICAL_STORE_UNAVAILABLE") from exc

    def read_vehicle(self, vehicle_instance_id: str) -> CanonicalReadback | None:
        connection = self._open()
        try:
            row = _Sql(connection, self.dialect).execute(
                "SELECT revision, verified_state, durable_identity, source_snapshot FROM vehicle_record "
                "WHERE vehicle_instance_id = ?", (vehicle_instance_id,),
            ).fetchone()
            if row is None:
                return None
            return CanonicalReadback(vehicle_instance_id, int(row[0]),
                                     _load_json(row[1]), _load_json(row[2]), _load_json(row[3]))
        finally:
            connection.close()

    def read_projection_state(self, vehicle_instance_id: str) -> VehicleProjectionState | None:
        connection = self._open()
        try:
            return self._projection_state(_Sql(connection, self.dialect), vehicle_instance_id)
        finally:
            connection.close()

    @staticmethod
    def _projection_state(db: _Sql, vehicle_instance_id: str) -> VehicleProjectionState | None:
        row = db.execute(
            "SELECT revision, source_snapshot, verified_state FROM vehicle_record "
            "WHERE vehicle_instance_id = ?", (vehicle_instance_id,),
        ).fetchone()
        if row is None:
            return None
        revision = int(row[0])
        source, verified = _load_json(row[1]), _load_json(row[2])
        if str(source.get("銷售素材Refs", "")).strip():
            raise CanonicalConflict("HOLD_IMPORTED_CREATIVE_LINKAGE_UNRESOLVED")
        links = db.execute(
            "SELECT media_asset_id, usage_class, truth_eligibility, creative_classification, "
            "channels FROM vehicle_media_link WHERE vehicle_instance_id = ?",
            (vehicle_instance_id,),
        ).fetchall()
        baseline = verified.get("原始媒體Refs", source.get("原始媒體Refs", ""))
        baseline_text = str(baseline)
        original_refs = _parse_media_refs(baseline_text)
        added_original: list[str] = []
        creative: dict[str, CreativeProjectionRef] = {}
        for media_id, usage, truth, classification, channels_raw in links:
            if usage == "CREATIVE":
                if truth != "FORBIDDEN" or classification != "CREATIVE":
                    raise CanonicalConflict("HOLD_CREATIVE_MEDIA_LINK_INVALID")
                channels = _load_list(channels_raw)
                if not channels or not all(isinstance(ch, str) and ch for ch in channels):
                    raise CanonicalConflict("HOLD_CREATIVE_CHANNELS_INVALID")
                ref_digest = hashlib.sha256(f"{vehicle_instance_id}\0{media_id}".encode()).hexdigest()
                creative[media_id] = CreativeProjectionRef(
                    f"creative:{ref_digest}", media_id, tuple(sorted(set(channels))),
                )
            elif usage in {"ORIGINAL_EVIDENCE", "EVIDENCE"}:
                if truth == "FORBIDDEN" or classification == "CREATIVE":
                    raise CanonicalConflict("HOLD_ORIGINAL_MEDIA_LINK_INVALID")
                added_original.append(media_id)
        merged_original = tuple(sorted(set(original_refs) | set(added_original)))
        original_cell = (_canonical(merged_original) if added_original else baseline_text)
        after = db.execute(
            "SELECT revision FROM vehicle_record WHERE vehicle_instance_id = ?",
            (vehicle_instance_id,),
        ).fetchone()
        if after is None or int(after[0]) != revision:
            raise CanonicalConflict("HOLD_PROJECTION_SOURCE_DRIFT")
        return VehicleProjectionState(
            vehicle_instance_id, revision, source, verified, merged_original,
            tuple(sorted(creative.values(), key=lambda item: item.creative_ref_id)), original_cell,
        )

    def commit_verified(self, mutation: CanonicalMutation) -> PersistenceReceipt:
        mutation.validate()
        if not mutation.verified_delta:
            return PersistenceReceipt(state=PersistenceDisposition.NO_DELTA, task_id=mutation.task_id)
        if self.evidence_admission is None:
            raise CanonicalCapabilityDebt("EVIDENCE_ADMISSION_UNAVAILABLE")
        for item in mutation.evidence:
            admitted = self.evidence_admission.resolve(
                vehicle_instance_id=mutation.vehicle_instance_id, field_name=item.field_name,
                value_digest=item.value_digest, evidence_asset_id=item.evidence_asset_id,
            )
            if admitted != item:
                raise CanonicalConflict("HOLD_EVIDENCE_READBACK_MISMATCH")
        connection = self._open()
        db = _Sql(connection, self.dialect)
        try:
            if self.dialect == "sqlite_test":
                db.execute("BEGIN IMMEDIATE")
            cutover = db.execute(
                "SELECT state FROM canonical_cutover WHERE singleton = ?", (True,),
            ).fetchone()
            if cutover is None or cutover[0] != "DB_CANONICAL":
                raise CanonicalConflict("HOLD_DB_NOT_CANONICAL")
            prior = db.execute(
                "SELECT payload_digest, resulting_revision, resulting_state_digest "
                "FROM vehicle_mutation WHERE mutation_id = ?",
                (mutation.mutation_id,),
            ).fetchone()
            if prior is not None:
                if prior[0] != mutation.payload_digest:
                    raise CanonicalConflict("HOLD_IDEMPOTENCY_COLLISION")
                connection.commit()
                return self._receipt(mutation.task_id, int(prior[1]), prior[2])
            row = db.execute(
                "SELECT revision, verified_state FROM vehicle_record WHERE vehicle_instance_id = ?",
                (mutation.vehicle_instance_id,),
            ).fetchone()
            if row is None:
                raise CanonicalConflict("HOLD_VEHICLE_IDENTITY_UNRESOLVED")
            if int(row[0]) != mutation.expected_revision:
                raise CanonicalConflict("STALE_CANONICAL_REVISION")
            state = _load_json(row[1])
            state.update(mutation.verified_delta)
            changed = db.execute(
                "UPDATE vehicle_record SET verified_state = ?, revision = revision + 1, "
                "updated_at = ? WHERE vehicle_instance_id = ? AND revision = ?",
                (db.json(state), datetime.now(UTC).isoformat(), mutation.vehicle_instance_id,
                 mutation.expected_revision),
            ).rowcount
            if changed != 1:
                raise CanonicalConflict("STALE_CANONICAL_REVISION")
            now = datetime.now(UTC).isoformat()
            for item in mutation.evidence:
                db.execute(
                    "INSERT INTO vehicle_field_evidence (vehicle_instance_id, field_name, value_digest, "
                    "evidence_asset_id, independent_evidence_root, truth_eligibility, "
                    "provenance_class, provenance_confidence, verification_state, support_scope, "
                    "extractor_revision, verifier_revision, first_verified_at, last_verified_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (mutation.vehicle_instance_id, item.field_name, item.value_digest,
                     item.evidence_asset_id, item.independent_evidence_root, item.truth_eligibility,
                     item.provenance_class, item.provenance_confidence, item.verification_state,
                     ",".join(item.support_scope), item.extractor_revision, item.verifier_revision,
                     now, now),
                )
            db.execute(
                "INSERT INTO vehicle_mutation (mutation_id, payload_digest, resulting_state_digest, "
                "vehicle_instance_id, "
                "expected_revision, resulting_revision, verified_delta, evidence_refs, request_id, "
                "task_id, terminal_disposition, committed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (mutation.mutation_id, mutation.payload_digest, _digest(state), mutation.vehicle_instance_id,
                 mutation.expected_revision, mutation.expected_revision + 1, db.json(mutation.verified_delta),
                 db.json([item.evidence_asset_id for item in mutation.evidence]), mutation.request_id,
                 mutation.task_id, "COMMITTED", now),
            )
            db.execute(
                "INSERT INTO projection_outbox (event_id, vehicle_instance_id, canonical_revision, state) "
                "VALUES (?, ?, ?, ?)",
                (mutation.mutation_id, mutation.vehicle_instance_id,
                 mutation.expected_revision + 1, "PROJECTION_PENDING"),
            )
            connection.commit()
        except CanonicalConflict as exc:
            connection.rollback()
            if str(exc) == "STALE_CANONICAL_REVISION":
                prior = self._prior_mutation(mutation.mutation_id)
                if prior is not None:
                    if prior[0] != mutation.payload_digest:
                        raise CanonicalConflict("HOLD_IDEMPOTENCY_COLLISION") from exc
                    return self._receipt(mutation.task_id, int(prior[1]), prior[2])
            raise
        except Exception as exc:
            connection.rollback()
            constraint = getattr(getattr(exc, "diag", None), "constraint_name", "") or str(exc)
            if "vehicle_verified_vin_unique" in constraint or "vehicle_verified_plate_unique" in constraint:
                raise CanonicalConflict("HOLD_VEHICLE_IDENTITY_CONFLICT") from exc
            raise
        finally:
            connection.close()
        return self._readback_receipt(mutation, mutation.expected_revision + 1)

    def _readback_receipt(self, mutation: CanonicalMutation, revision: int) -> PersistenceReceipt:
        fresh = self.read_vehicle(mutation.vehicle_instance_id)
        if fresh is None or fresh.revision != revision or any(
            fresh.verified_state.get(field) != value for field, value in mutation.verified_delta.items()
        ):
            raise CanonicalConflict("HOLD_CANONICAL_POSTCOMMIT_READBACK_MISMATCH")
        return self._receipt(mutation.task_id, revision, _digest(fresh.verified_state))

    @staticmethod
    def _receipt(task_id: str, revision: int, state_digest: str) -> PersistenceReceipt:
        return PersistenceReceipt(
            state=PersistenceDisposition.WRITE_AND_READBACK_PASS, task_id=task_id,
            postwrite_version=str(revision), postwrite_sha256=state_digest,
        )

    def _prior_mutation(self, mutation_id: str) -> tuple[Any, ...] | None:
        connection = self._open()
        try:
            return _Sql(connection, self.dialect).execute(
                "SELECT payload_digest, resulting_revision, resulting_state_digest "
                "FROM vehicle_mutation WHERE mutation_id = ?", (mutation_id,),
            ).fetchone()
        finally:
            connection.close()

    def field_evidence(self, vehicle_instance_id: str, field_name: str) -> tuple[FieldEvidence, ...]:
        connection = self._open()
        try:
            rows = _Sql(connection, self.dialect).execute(
                "SELECT value_digest, evidence_asset_id, independent_evidence_root, verification_state, "
                "support_scope, truth_eligibility, provenance_class, provenance_confidence, "
                "extractor_revision, verifier_revision FROM vehicle_field_evidence "
                "WHERE vehicle_instance_id = ? AND field_name = ?",
                (vehicle_instance_id, field_name),
            ).fetchall()
            return tuple(FieldEvidence(field_name, row[0], row[1], row[2], row[3],
                                       tuple(row[4].split(",")), row[5], row[6], row[7], row[8], row[9])
                         for row in rows)
        finally:
            connection.close()

    def independent_evidence_count(self, vehicle_instance_id: str) -> int:
        connection = self._open()
        try:
            row = _Sql(connection, self.dialect).execute(
                "SELECT COUNT(DISTINCT independent_evidence_root) FROM vehicle_field_evidence "
                "WHERE vehicle_instance_id = ?", (vehicle_instance_id,),
            ).fetchone()
            return int(row[0])
        finally:
            connection.close()

    def admit_creative(self, admission: CreativeAdmission) -> PersistenceReceipt:
        """Media link, revision, receipt and projection event commit together; truth is untouched."""
        admission.validate()
        connection = self._open()
        db = _Sql(connection, self.dialect)
        try:
            if self.dialect == "sqlite_test":
                db.execute("BEGIN IMMEDIATE")
            cutover = db.execute("SELECT state FROM canonical_cutover WHERE singleton = ?",
                                 (True,)).fetchone()
            if cutover is None or cutover[0] != "DB_CANONICAL":
                raise CanonicalConflict("HOLD_DB_NOT_CANONICAL")
            prior = db.execute(
                "SELECT payload_digest, resulting_revision, resulting_state_digest "
                "FROM vehicle_mutation WHERE mutation_id = ?", (admission.admission_id,),
            ).fetchone()
            if prior is not None:
                if prior[0] != admission.payload_digest:
                    raise CanonicalConflict("HOLD_IDEMPOTENCY_COLLISION")
                connection.commit()
                return self._receipt(admission.task_id, int(prior[1]), prior[2])
            existing = db.execute(
                "SELECT truth_eligibility, creative_classification, channels FROM vehicle_media_link "
                "WHERE vehicle_instance_id = ? AND media_asset_id = ? AND usage_class = ?",
                (admission.vehicle_instance_id, admission.media_asset_id, "CREATIVE"),
            ).fetchone()
            if existing is not None:
                if (existing[0] != "FORBIDDEN" or existing[1] != "CREATIVE"
                    or sorted(_load_list(existing[2])) != sorted(set(admission.channels))):
                    raise CanonicalConflict("HOLD_CREATIVE_MEDIA_LINK_COLLISION")
                connection.commit()
                return PersistenceReceipt(state=PersistenceDisposition.NO_DELTA,
                                          task_id=admission.task_id)
            row = db.execute(
                "SELECT revision, verified_state FROM vehicle_record WHERE vehicle_instance_id = ?",
                (admission.vehicle_instance_id,),
            ).fetchone()
            if row is None:
                raise CanonicalConflict("HOLD_VEHICLE_IDENTITY_UNRESOLVED")
            if int(row[0]) != admission.expected_revision:
                raise CanonicalConflict("STALE_CANONICAL_REVISION")
            changed = db.execute(
                "UPDATE vehicle_record SET revision = revision + 1, updated_at = ? "
                "WHERE vehicle_instance_id = ? AND revision = ?",
                (datetime.now(UTC).isoformat(), admission.vehicle_instance_id,
                 admission.expected_revision),
            ).rowcount
            if changed != 1:
                raise CanonicalConflict("STALE_CANONICAL_REVISION")
            db.execute(
                "INSERT INTO vehicle_media_link (vehicle_instance_id, media_asset_id, usage_class, "
                "truth_eligibility, provenance_class, provenance_confidence, "
                "independent_evidence_root, creative_classification, channels) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (admission.vehicle_instance_id, admission.media_asset_id, "CREATIVE", "FORBIDDEN",
                 admission.provenance_class, "VERIFIED", admission.independent_evidence_root,
                 "CREATIVE", db.json(sorted(set(admission.channels)))),
            )
            now = datetime.now(UTC).isoformat()
            db.execute(
                "INSERT INTO vehicle_mutation (mutation_id, payload_digest, resulting_state_digest, "
                "vehicle_instance_id, expected_revision, resulting_revision, verified_delta, "
                "evidence_refs, request_id, task_id, terminal_disposition, committed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (admission.admission_id, admission.payload_digest, _digest(_load_json(row[1])),
                 admission.vehicle_instance_id, admission.expected_revision,
                 admission.expected_revision + 1, db.json({}), db.json([admission.media_asset_id]),
                 admission.request_id, admission.task_id, "COMMITTED", now),
            )
            db.execute(
                "INSERT INTO projection_outbox (event_id, vehicle_instance_id, canonical_revision, state) "
                "VALUES (?, ?, ?, ?)",
                (admission.admission_id, admission.vehicle_instance_id,
                 admission.expected_revision + 1, "PROJECTION_PENDING"),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        fresh = self.read_vehicle(admission.vehicle_instance_id)
        if fresh is None or fresh.revision != admission.expected_revision + 1:
            raise CanonicalConflict("HOLD_CREATIVE_POSTCOMMIT_READBACK_MISMATCH")
        connection = self._open()
        try:
            link = _Sql(connection, self.dialect).execute(
                "SELECT truth_eligibility, independent_evidence_root, creative_classification "
                "FROM vehicle_media_link WHERE vehicle_instance_id = ? AND media_asset_id = ? "
                "AND usage_class = ?",
                (admission.vehicle_instance_id, admission.media_asset_id, "CREATIVE"),
            ).fetchone()
            if link != ("FORBIDDEN", admission.independent_evidence_root, "CREATIVE"):
                raise CanonicalConflict("HOLD_CREATIVE_LINK_READBACK_MISMATCH")
        finally:
            connection.close()
        return self._receipt(admission.task_id, fresh.revision, _digest(fresh.verified_state))


def _load_json(value: Any) -> dict[str, Any]:
    return json.loads(value) if isinstance(value, str) else dict(value)


def _load_list(value: Any) -> list[str]:
    return json.loads(value) if isinstance(value, str) else list(value)


def _parse_media_refs(value: str) -> tuple[str, ...]:
    if not value:
        return ()
    if value.startswith("["):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise CanonicalConflict("HOLD_ORIGINAL_MEDIA_REFS_INVALID") from exc
        if not isinstance(parsed, list) or any(not isinstance(ref, str) for ref in parsed):
            raise CanonicalConflict("HOLD_ORIGINAL_MEDIA_REFS_INVALID")
        return tuple(sorted(set(parsed)))
    return (value,)


def sqlite_contract_schema(connection: sqlite3.Connection) -> None:
    """SQLite contract fixture only; never a production fallback or binding."""
    connection.executescript("""
        CREATE TABLE vehicle_record (vehicle_instance_id TEXT PRIMARY KEY, revision INTEGER NOT NULL,
            durable_identity TEXT NOT NULL, source_snapshot TEXT NOT NULL,
            verified_state TEXT NOT NULL, source_row INTEGER UNIQUE NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE UNIQUE INDEX vehicle_verified_vin_unique ON vehicle_record (
            json_extract(verified_state, '$."VIN/車身號碼"'))
            WHERE nullif(json_extract(verified_state, '$."VIN/車身號碼"'), '') IS NOT NULL;
        CREATE UNIQUE INDEX vehicle_verified_plate_unique ON vehicle_record (
            json_extract(verified_state, '$."車牌"'))
            WHERE nullif(json_extract(verified_state, '$."車牌"'), '') IS NOT NULL;
        CREATE TABLE vehicle_field_evidence (vehicle_instance_id TEXT, field_name TEXT,
            value_digest TEXT, evidence_asset_id TEXT, independent_evidence_root TEXT,
            truth_eligibility TEXT, provenance_class TEXT, provenance_confidence TEXT,
            verification_state TEXT, support_scope TEXT, extractor_revision TEXT,
            verifier_revision TEXT, first_verified_at TEXT, last_verified_at TEXT);
        CREATE TABLE vehicle_mutation (mutation_id TEXT PRIMARY KEY, payload_digest TEXT,
            resulting_state_digest TEXT,
            vehicle_instance_id TEXT, expected_revision INTEGER, resulting_revision INTEGER,
            verified_delta TEXT, evidence_refs TEXT, request_id TEXT, task_id TEXT,
            terminal_disposition TEXT, committed_at TEXT);
        CREATE TABLE projection_outbox (event_id TEXT PRIMARY KEY, vehicle_instance_id TEXT,
            canonical_revision INTEGER, state TEXT NOT NULL CHECK (state IN
            ('PROJECTION_PENDING','PROJECTION_FAILED','PROJECTED',
             'SUPERSEDED_BY_LATER_REVISION','HOLD_CONFLICT')),
            attempts INTEGER DEFAULT 0, last_error TEXT, projected_sha256 TEXT,
            satisfied_by_revision INTEGER, updated_at TEXT);
        CREATE TABLE vehicle_projection_cursor (vehicle_instance_id TEXT PRIMARY KEY,
            projected_revision INTEGER NOT NULL, projected_row_digest TEXT NOT NULL,
            projected_sha256 TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE vehicle_media_link (vehicle_instance_id TEXT, media_asset_id TEXT,
            usage_class TEXT, truth_eligibility TEXT, provenance_class TEXT,
            provenance_confidence TEXT, independent_evidence_root TEXT, creative_classification TEXT,
            channels TEXT,
            PRIMARY KEY (vehicle_instance_id, media_asset_id, usage_class));
        CREATE TABLE canonical_cutover (singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
            source_file_id TEXT NOT NULL, source_sha256 TEXT NOT NULL,
            source_topology_digest TEXT NOT NULL, source_state_digest TEXT NOT NULL,
            source_vehicle_count INTEGER NOT NULL, state TEXT NOT NULL, declared_at TEXT);
    """)
