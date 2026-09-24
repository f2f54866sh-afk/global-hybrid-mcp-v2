from __future__ import annotations

# ruff: noqa: E501
import hashlib
import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl, model_validator


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


class KnowledgeDecision(StrEnum):
    PASS = "PASS"
    HOLD = "HOLD"
    FAIL = "FAIL"


class PowerUnit(StrEnum):
    PS = "PS"
    HP = "HP"
    KW = "KW"
    NM = "NM"


class VehicleResearchEvidencePacketV1(BaseModel):
    evidence_packet_id: str = Field(min_length=1, max_length=160)
    work_id: str = Field(min_length=1, max_length=160)
    scope_key: str = Field(min_length=1, max_length=240)
    market: str = Field(min_length=1, max_length=32)
    model_year: int = Field(ge=1886, le=3000)
    make: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=120)
    trim_scope: str | None = Field(default=None, max_length=120)
    fact_key: str = Field(min_length=1, max_length=160)
    fact_family: str = Field(min_length=1, max_length=80)
    observed_literal: str = Field(min_length=1, max_length=2000)
    value_candidate: str = Field(min_length=1, max_length=500)
    unit_candidate: PowerUnit | None = None
    source_url: HttpUrl
    source_role: str = Field(min_length=1, max_length=80)
    source_market_scope: str = Field(min_length=1, max_length=32)
    source_model_year_scope: int = Field(ge=1886, le=3000)
    source_quote: str = Field(min_length=1, max_length=4000)
    collected_at: datetime
    producer: str = Field(min_length=1, max_length=160)
    unresolved_notes: list[str] = Field(default_factory=list)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_scope(self) -> VehicleResearchEvidencePacketV1:
        values = [
            self.evidence_packet_id,
            self.work_id,
            self.scope_key,
            self.market,
            self.make,
            self.model,
            self.fact_key,
            self.fact_family,
            self.observed_literal,
            self.value_candidate,
            self.source_role,
            self.source_market_scope,
            self.source_quote,
            self.producer,
        ]
        if any(not value.strip() for value in values):
            raise ValueError("evidence fields cannot be blank")
        if self.trim_scope is not None and not self.trim_scope.strip():
            raise ValueError("trim_scope cannot be blank")
        if self.collected_at.tzinfo is None:
            raise ValueError("collected_at must be timezone-aware")
        if any(not item.strip() for item in self.unresolved_notes):
            raise ValueError("unresolved_notes cannot contain blanks")
        return self


class VerifiedVehicleFact(BaseModel):
    fact_id: str = Field(min_length=1)
    fact_key: str = Field(min_length=1)
    fact_family: str = Field(min_length=1)
    value: str = Field(min_length=1)
    unit: PowerUnit | None = None
    market: str = Field(min_length=1)
    model_year: int
    make: str = Field(min_length=1)
    model: str = Field(min_length=1)
    generation: str | None = None
    body: str | None = None
    trim: str | None = None
    package: str | None = None
    powertrain: str | None = None
    drivetrain: str | None = None
    instance_id: str | None = None
    source_scope: str = Field(min_length=1)
    source_packet_ids: list[str] = Field(min_length=1)


class VehicleFactVerificationReceipt(BaseModel):
    receipt_id: str
    work_id: str
    scope_key: str
    evidence_packet_ids: list[str]
    evidence_digests: list[str]
    verifier_id: str
    verifier_version: str
    parser_version: str
    conflict_state: str
    decision: KnowledgeDecision
    verified_at: datetime
    receipt_digest: str


class DeterministicVehicleConfigurationVerifier:
    verifier_id = "vehicle-configuration-verifier"
    verifier_version = "1"
    parser_version = "typed-unit-parser-v1"

    def verify(
        self,
        packet: VehicleResearchEvidencePacketV1,
        *,
        expected_work_id: str,
        expected_scope_key: str,
    ) -> tuple[VehicleFactVerificationReceipt, VerifiedVehicleFact | None]:
        decision = KnowledgeDecision.PASS
        conflict = "NO_CONFLICT"
        if (
            packet.work_id != expected_work_id
            or packet.scope_key != expected_scope_key
            or packet.market.casefold() != packet.source_market_scope.casefold()
            or packet.model_year != packet.source_model_year_scope
            or packet.unresolved_notes
        ):
            decision = KnowledgeDecision.HOLD
            conflict = "SCOPE_OR_EVIDENCE_UNRESOLVED"
        body = packet.model_dump(mode="json")
        expected_content = hashlib.sha256(packet.source_quote.encode()).hexdigest()
        if packet.content_sha256 != expected_content:
            decision = KnowledgeDecision.FAIL
            conflict = "CONTENT_DIGEST_MISMATCH"
        receipt_body = {
            "work_id": packet.work_id,
            "scope_key": packet.scope_key,
            "evidence_packet_ids": [packet.evidence_packet_id],
            "evidence_digests": [digest(body)],
            "verifier_id": self.verifier_id,
            "verifier_version": self.verifier_version,
            "parser_version": self.parser_version,
            "conflict_state": conflict,
            "decision": decision.value,
        }
        receipt = VehicleFactVerificationReceipt(
            receipt_id=f"verify-{digest(receipt_body)[:24]}",
            verified_at=datetime.now(UTC),
            receipt_digest=digest(receipt_body),
            **receipt_body,
        )
        if decision is not KnowledgeDecision.PASS:
            return receipt, None
        fact_body = {
            "fact_key": packet.fact_key,
            "fact_family": packet.fact_family,
            "value": packet.value_candidate,
            "unit": packet.unit_candidate,
            "market": packet.market,
            "model_year": packet.model_year,
            "make": packet.make,
            "model": packet.model,
            "trim": packet.trim_scope,
            "source_scope": packet.scope_key,
            "source_packet_ids": [packet.evidence_packet_id],
        }
        return receipt, VerifiedVehicleFact(fact_id=f"fact-{digest(fact_body)[:24]}", **fact_body)


@dataclass(frozen=True)
class InventoryRow:
    row_number: int
    make: str
    model_year: str
    model: str
    raw_source_row: tuple[str, ...]


class InventoryNormalizer:
    version = "google-inventory-v1"

    def normalize(self, rows: list[list[str]]) -> tuple[list[InventoryRow], list[int]]:
        result: list[InventoryRow] = []
        held: list[int] = []
        current_make: str | None = None
        for number, source in enumerate(rows, 1):
            raw = tuple(str(item) for item in source)
            padded = list(raw) + [""] * (14 - len(raw))
            if not any(item.strip() for item in padded):
                current_make = None
                continue
            make, year, model = (padded[2].strip(), padded[3].strip(), padded[4].strip())
            if make:
                current_make = make
            elif year or model:
                if current_make is None:
                    held.append(number)
                    continue
                make = current_make
            if year and model:
                result.append(InventoryRow(number, make, year, model, raw))
        return result, held


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations(version TEXT PRIMARY KEY, applied_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS inventory_source_observation(id TEXT PRIMARY KEY, source_revision TEXT NOT NULL, payload TEXT NOT NULL, observed_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS inventory_vehicle_row(id TEXT PRIMARY KEY, observation_id TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS vehicle_coverage_work(id TEXT PRIMARY KEY, scope_key TEXT NOT NULL, state TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS research_evidence_packet(id TEXT PRIMARY KEY, work_id TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS vehicle_fact_verification_receipt(id TEXT PRIMARY KEY, work_id TEXT NOT NULL, decision TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS vehicle_configuration_revision(id TEXT PRIMARY KEY, work_id TEXT NOT NULL, state TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS vehicle_configuration_fact(id TEXT PRIMARY KEY, revision_id TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS vehicle_fact_source(fact_id TEXT NOT NULL, evidence_id TEXT NOT NULL, PRIMARY KEY(fact_id,evidence_id));
CREATE TABLE IF NOT EXISTS vehicle_fact_conflict(id TEXT PRIMARY KEY, revision_id TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS vehicle_snapshot_build(id TEXT PRIMARY KEY, builder_version TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS vehicle_snapshot_promotion(id TEXT PRIMARY KEY, snapshot_id TEXT NOT NULL, promoted_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS vehicle_snapshot_active(singleton INTEGER PRIMARY KEY CHECK(singleton=1), snapshot_id TEXT NOT NULL, promotion_id TEXT NOT NULL);
"""


class VehicleKnowledgeStore:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self.connection.executescript(SCHEMA_SQL)

    def commit_verified_fact(
        self,
        *,
        work_id: str,
        packet: VehicleResearchEvidencePacketV1,
        receipt: VehicleFactVerificationReceipt,
        fact: VerifiedVehicleFact,
        inject_failure: Callable[[], None] | None = None,
    ) -> str:
        if receipt.decision is not KnowledgeDecision.PASS:
            raise ValueError("only verified evidence can enter fact authority")
        revision_body = {"work_id": work_id, "fact_ids": [fact.fact_id], "receipt": receipt.receipt_id}
        revision_id = f"revision-{digest(revision_body)[:24]}"
        with self.connection:
            self.connection.execute(
                "INSERT OR IGNORE INTO research_evidence_packet VALUES(?,?,?)",
                (packet.evidence_packet_id, work_id, canonical_json(packet.model_dump(mode="json"))),
            )
            self.connection.execute(
                "INSERT OR IGNORE INTO vehicle_fact_verification_receipt VALUES(?,?,?,?)",
                (
                    receipt.receipt_id,
                    work_id,
                    receipt.decision.value,
                    canonical_json(receipt.model_dump(mode="json")),
                ),
            )
            if inject_failure:
                inject_failure()
            self.connection.execute(
                "INSERT OR IGNORE INTO vehicle_configuration_revision VALUES(?,?,?,?)",
                (revision_id, work_id, "VERIFIED", canonical_json(revision_body)),
            )
            self.connection.execute(
                "INSERT OR IGNORE INTO vehicle_configuration_fact VALUES(?,?,?)",
                (fact.fact_id, revision_id, canonical_json(fact.model_dump(mode="json"))),
            )
            for source in fact.source_packet_ids:
                self.connection.execute(
                    "INSERT OR IGNORE INTO vehicle_fact_source VALUES(?,?)", (fact.fact_id, source)
                )
            updated = self.connection.execute(
                "UPDATE vehicle_coverage_work SET state='VERIFIED' WHERE id=? AND state!='VERIFIED'",
                (work_id,),
            )
            if updated.rowcount != 1:
                raise ValueError("coverage work binding missing or already terminal")
        return revision_id

    def build_snapshot(self, revision_ids: list[str], *, builder_version: str = "1") -> dict[str, Any]:
        rows = []
        for revision_id in sorted(set(revision_ids)):
            row = self.connection.execute(
                "SELECT state,payload FROM vehicle_configuration_revision WHERE id=?", (revision_id,)
            ).fetchone()
            if row is None or row[0] != "VERIFIED":
                raise ValueError("snapshot contains non-verified revision")
            facts = self.connection.execute(
                "SELECT payload FROM vehicle_configuration_fact WHERE revision_id=? ORDER BY id",
                (revision_id,),
            ).fetchall()
            rows.extend(json.loads(item[0]) for item in facts)
        body = {"builder_version": builder_version, "revision_ids": sorted(set(revision_ids)), "facts": rows}
        snapshot_id = f"snapshot-{digest(body)[:24]}"
        with self.connection:
            self.connection.execute(
                "INSERT OR IGNORE INTO vehicle_snapshot_build VALUES(?,?,?)",
                (snapshot_id, builder_version, canonical_json(body)),
            )
        return {"snapshot_id": snapshot_id, **body}

    def promote_snapshot(self, snapshot_id: str, *, inject_failure: Callable[[], None] | None = None) -> str:
        row = self.connection.execute(
            "SELECT payload FROM vehicle_snapshot_build WHERE id=?", (snapshot_id,)
        ).fetchone()
        if row is None:
            raise ValueError("snapshot candidate missing")
        promotion_id = f"promotion-{digest({'snapshot_id': snapshot_id})[:24]}"
        now = datetime.now(UTC).isoformat()
        with self.connection:
            self.connection.execute(
                "INSERT OR IGNORE INTO vehicle_snapshot_promotion VALUES(?,?,?)",
                (promotion_id, snapshot_id, now),
            )
            if inject_failure:
                inject_failure()
            self.connection.execute(
                "INSERT INTO vehicle_snapshot_active VALUES(1,?,?) ON CONFLICT(singleton) DO UPDATE SET snapshot_id=excluded.snapshot_id,promotion_id=excluded.promotion_id",
                (snapshot_id, promotion_id),
            )
        return promotion_id

    def readback(self) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT snapshot_id,promotion_id FROM vehicle_snapshot_active WHERE singleton=1"
        ).fetchone()
        if row is None:
            return {"active": False, "snapshot_id": None}
        build = self.connection.execute(
            "SELECT builder_version,payload FROM vehicle_snapshot_build WHERE id=?", (row[0],)
        ).fetchone()
        return {
            "active": True,
            "snapshot_id": row[0],
            "promotion_id": row[1],
            "builder_version": build[0],
            "source_revision": digest(json.loads(build[1])["revision_ids"]),
        }


class ModificationClassification(StrEnum):
    OEM = "OEM"
    OPTION = "OPTION"
    PACKAGE = "PACKAGE"
    LIKELY_MODIFICATION = "LIKELY_MODIFICATION"
    VERIFIED_MODIFICATION = "VERIFIED_MODIFICATION"
    UNKNOWN = "UNKNOWN"


class VisualObservationPacket(BaseModel):
    packet_id: str
    task_id: str
    producer_id: str
    source_photo_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    observed_equipment: list[str]
    produced_at: datetime
    server_attested: bool = False


def admit_visual_observation(packet: VisualObservationPacket, *, expected_task_id: str) -> None:
    if not packet.server_attested or packet.task_id != expected_task_id:
        raise ValueError("VISUAL_OBSERVATION_PRODUCER_UNAVAILABLE_OR_UNTRUSTED")
