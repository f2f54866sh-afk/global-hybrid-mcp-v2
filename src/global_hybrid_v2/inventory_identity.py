"""Candidate inventory observation and durable vehicle identity admission.

This module has no default production bindings. A trusted caller supplies the
turn referent, a fresh source read, and independently admitted identity evidence.
"""
from __future__ import annotations

import hashlib
import json
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from global_hybrid_v2.adapters.google_vehicle_control import (
    COMPANY_INVENTORY_RANGE,
    COMPANY_INVENTORY_SPREADSHEET_ID,
)
from global_hybrid_v2.google_auth import ServiceAccountAccessTokenProvider, ServiceAccountIdentity
from global_hybrid_v2.transactional_vehicle_store import _load_json, _Sql


def _digest(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


class InventoryIdentityHold(RuntimeError):
    pass


@dataclass(frozen=True)
class SourceMetadata:
    file_id: str
    modified_time: str
    sheet_id: int
    sheet_name: str


class InventorySourcePort(Protocol):
    def metadata(self) -> SourceMetadata: ...
    def values(self) -> list[list[str]]: ...


class GoogleInventorySource:
    """Read-only, exact-ID Google Drive and Sheets source via a trusted token producer."""

    required_scopes = (
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.metadata.readonly",
    )

    def __init__(self, access_token_provider: Callable[[], str], *, timeout: float = 15):
        self.access_token_provider = access_token_provider
        self.timeout = timeout

    @classmethod
    def from_service_account_json(cls, raw: str) -> GoogleInventorySource:
        identity = ServiceAccountIdentity.from_json(raw)
        token = ServiceAccountAccessTokenProvider(identity, scopes=cls.required_scopes)
        return cls(token)

    def _get(self, url: str) -> dict:
        request = urllib.request.Request(url, headers={
            "authorization": f"Bearer {self.access_token_provider()}",
            "accept": "application/json",
        }, method="GET")
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.load(response)

    def metadata(self) -> SourceMetadata:
        file_id = COMPANY_INVENTORY_SPREADSHEET_ID
        file = self._get("https://www.googleapis.com/drive/v3/files/" + file_id
                         + "?fields=id,mimeType,modifiedTime")
        spreadsheet = self._get("https://sheets.googleapis.com/v4/spreadsheets/" + file_id
                                + "?fields=spreadsheetId,sheets(properties(sheetId,title))")
        matches = [sheet["properties"] for sheet in spreadsheet.get("sheets", [])
                   if sheet.get("properties", {}).get("title") == "車源"]
        if (file.get("id") != file_id or spreadsheet.get("spreadsheetId") != file_id
                or file.get("mimeType") != "application/vnd.google-apps.spreadsheet"
                or len(matches) != 1):
            raise InventoryIdentityHold("HOLD_INVENTORY_SOURCE_IDENTITY")
        return SourceMetadata(file_id, str(file.get("modifiedTime") or ""),
                              int(matches[0]["sheetId"]), "車源")

    def values(self) -> list[list[str]]:
        file_id = COMPANY_INVENTORY_SPREADSHEET_ID
        url = ("https://sheets.googleapis.com/v4/spreadsheets/" + file_id + "/values/"
               + urllib.parse.quote(COMPANY_INVENTORY_RANGE, safe=""))
        payload = self._get(url)
        if not isinstance(payload.get("values"), list):
            raise InventoryIdentityHold("HOLD_INVENTORY_VALUES_UNAVAILABLE")
        return payload["values"]


@dataclass(frozen=True)
class InventoryObservation:
    observation_id: str
    source_row: int
    cells: tuple[str, ...]
    source_snapshot_digest: str
    source_currentness_digest: str
    source_file_id: str
    sheet_id: int
    sheet_name: str
    source_range: str


@dataclass(frozen=True)
class InventorySnapshot:
    metadata: SourceMetadata
    source_range: str
    content_digest: str
    currentness_token: str
    observations: tuple[InventoryObservation, ...]


def read_current_snapshot(source: InventorySourcePort) -> InventorySnapshot:
    """Bracket a range read with metadata and retain exact row positions."""
    try:
        before = source.metadata()
        values = source.values()
        after = source.metadata()
    except InventoryIdentityHold:
        raise
    except (OSError, TimeoutError, ValueError, KeyError, TypeError) as exc:
        raise InventoryIdentityHold("HOLD_INVENTORY_SOURCE_UNAVAILABLE") from exc
    if (before.file_id != COMPANY_INVENTORY_SPREADSHEET_ID or before.sheet_name != "車源"
            or before.sheet_id < 0 or not before.modified_time):
        raise InventoryIdentityHold("HOLD_INVENTORY_SOURCE_IDENTITY")
    if before != after:
        raise InventoryIdentityHold("HOLD_INVENTORY_SOURCE_ADVANCED")
    if not isinstance(values, list) or not values or any(not isinstance(row, list) for row in values):
        raise InventoryIdentityHold("HOLD_INVENTORY_VALUES_UNAVAILABLE")
    normalized = tuple(tuple(str(cell) for cell in row) for row in values)
    content_digest = _digest(normalized)
    currentness_token = _digest((before.file_id, before.sheet_id, before.sheet_name,
                                 COMPANY_INVENTORY_RANGE, before.modified_time, content_digest))
    observations = []
    for row_number, cells in enumerate(normalized[1:], 2):
        if not any(cell.strip() for cell in cells):
            continue
        observation_id = "inventory-observation:" + _digest((
            before.file_id, before.sheet_id, before.sheet_name, row_number,
            content_digest, currentness_token,
        ))
        observations.append(InventoryObservation(
            observation_id, row_number, cells, content_digest, currentness_token,
            before.file_id, before.sheet_id, before.sheet_name, COMPANY_INVENTORY_RANGE,
        ))
    return InventorySnapshot(before, COMPANY_INVENTORY_RANGE, content_digest,
                             currentness_token, tuple(observations))


class BindingState(StrEnum):
    UNBOUND_OBSERVATION = "UNBOUND_OBSERVATION"
    INSTANCE_CANDIDATE = "INSTANCE_CANDIDATE"
    INSTANCE_BOUND = "INSTANCE_BOUND"
    HOLD_IDENTITY_CONFLICT = "HOLD_IDENTITY_CONFLICT"


@dataclass(frozen=True)
class TrustedTurnReferent:
    conversation_id: str
    turn_id: str
    make: str
    model_year: str
    model: str
    source_owner: str


@dataclass(frozen=True)
class AdmittedDurableIdentity:
    key_kind: str
    key_value: str
    vehicle_instance_id: str
    evidence_id: str
    evidence_digest: str
    authority: str


class DurableIdentityEvidencePort(Protocol):
    def resolve(self, observation: InventoryObservation) -> tuple[AdmittedDurableIdentity, ...]: ...


class InventoryBindingPort(Protocol):
    def record_snapshot(self, snapshot: InventorySnapshot) -> None: ...
    def current_binding(self, observation: InventoryObservation) -> str | None: ...
    def vehicle_for_key(self, key_kind: str, key_value: str) -> str | None: ...
    def promote(self, observation: InventoryObservation, vehicle_instance_id: str,
                evidence: tuple[AdmittedDurableIdentity, ...]) -> str: ...


@dataclass(frozen=True)
class InventoryResolution:
    source_observation_id: str | None
    vehicle_instance_id: str | None
    binding_state: BindingState
    source_currentness_token: str
    candidate_count: int
    provenance: tuple[str, ...]
    blocker: str | None = None


class AuthoritativeInventoryResolver:
    def __init__(self, binding: InventoryBindingPort, evidence: DurableIdentityEvidencePort):
        self.binding = binding
        self.evidence = evidence

    def resolve(self, referent: TrustedTurnReferent, snapshot: InventorySnapshot) -> InventoryResolution:
        if not all((referent.conversation_id, referent.turn_id, referent.source_owner,
                    referent.make, referent.model_year, referent.model)):
            raise InventoryIdentityHold("HOLD_TRUSTED_REFERENT_MISSING")
        self.binding.record_snapshot(snapshot)
        matches = [observation for observation in snapshot.observations
                   if self._matches(observation, referent)]
        if len(matches) != 1:
            return InventoryResolution(None, None, BindingState.HOLD_IDENTITY_CONFLICT,
                                       snapshot.currentness_token, len(matches), (),
                                       "HOLD_IDENTITY_CONFLICT")
        observation = matches[0]
        prior = self.binding.current_binding(observation)
        evidence = self.evidence.resolve(observation)
        ids = {item.vehicle_instance_id for item in evidence}
        if prior:
            ids.add(prior)
        for item in evidence:
            if (item.key_kind not in {"VIN", "PLATE", "CANONICAL_ID"} or
                    not all((item.key_value, item.vehicle_instance_id, item.evidence_id,
                             item.evidence_digest, item.authority))):
                return self._conflict(observation, snapshot, "HOLD_IDENTITY_EVIDENCE_INVALID")
            bound = self.binding.vehicle_for_key(item.key_kind, item.key_value)
            if bound and bound != item.vehicle_instance_id:
                return self._conflict(observation, snapshot, "HOLD_IDENTITY_CONFLICT")
        if len(ids) > 1:
            return self._conflict(observation, snapshot, "HOLD_IDENTITY_CONFLICT")
        if prior:
            return InventoryResolution(observation.observation_id, prior, BindingState.INSTANCE_BOUND,
                                       snapshot.currentness_token, 1,
                                       tuple(sorted({item.evidence_id for item in evidence}))
                                       if evidence else ("CANONICAL_BINDING",))
        if not evidence:
            return InventoryResolution(observation.observation_id, None, BindingState.INSTANCE_CANDIDATE,
                                       snapshot.currentness_token, 1, ("UNIQUE_SOURCE_OBSERVATION",))
        vehicle_id = next(iter(ids))
        persisted = self.binding.promote(observation, vehicle_id, evidence)
        if persisted != vehicle_id or self.binding.current_binding(observation) != vehicle_id:
            raise InventoryIdentityHold("HOLD_BINDING_READBACK_MISMATCH")
        return InventoryResolution(observation.observation_id, vehicle_id, BindingState.INSTANCE_BOUND,
                                   snapshot.currentness_token, 1,
                                   tuple(sorted({item.evidence_id for item in evidence})))

    @staticmethod
    def _matches(observation: InventoryObservation, referent: TrustedTurnReferent) -> bool:
        cells = observation.cells + ("",) * max(0, 6 - len(observation.cells))
        return (cells[4].strip().casefold(), cells[5].strip().casefold()) == (
            referent.model_year.strip().casefold(), referent.model.strip().casefold()) and (
            cells[3].strip().casefold() == referent.make.strip().casefold())

    @staticmethod
    def _conflict(observation: InventoryObservation, snapshot: InventorySnapshot,
                  blocker: str) -> InventoryResolution:
        return InventoryResolution(observation.observation_id, None,
                                   BindingState.HOLD_IDENTITY_CONFLICT,
                                   snapshot.currentness_token, 1, (), blocker)


class SqlInventoryBindingStore:
    """Candidate store using the existing observation table; no ID is minted here."""

    def __init__(self, connect: Callable[[], object], *, dialect: str):
        if dialect not in {"postgres", "sqlite_test"}:
            raise ValueError("unsupported inventory binding dialect")
        self.connect, self.dialect = connect, dialect

    def record_snapshot(self, snapshot: InventorySnapshot) -> None:
        connection = self.connect()
        db = _Sql(connection, self.dialect)
        try:
            if self.dialect == "sqlite_test":
                db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE vehicle_source_observation SET is_current = false "
                       "WHERE source_file_id = ? AND source_sheet_id = ? AND source_range = ? "
                       "AND source_currentness_digest <> ?",
                       (snapshot.metadata.file_id, snapshot.metadata.sheet_id,
                        snapshot.source_range, snapshot.currentness_token))
            for observation in snapshot.observations:
                db.execute(
                    "INSERT INTO vehicle_source_observation "
                    "(source_observation_id, source_file_id, source_sha256, source_row, "
                    "source_snapshot, vehicle_instance_id, company_source_state, ai_usage_state, "
                    "source_sheet_id, source_sheet_name, source_range, source_currentness_digest, "
                    "binding_state, is_current) VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, true) "
                    "ON CONFLICT(source_observation_id) DO UPDATE SET is_current = true",
                    (observation.observation_id, observation.source_file_id,
                     observation.source_snapshot_digest, observation.source_row,
                     db.json({"cells": observation.cells}), "CURRENT_SOURCE",
                     "SOURCE_OBSERVATION_ONLY / NOT_INSTANCE_READY", observation.sheet_id,
                     observation.sheet_name, observation.source_range,
                     observation.source_currentness_digest, BindingState.UNBOUND_OBSERVATION.value),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def current_binding(self, observation: InventoryObservation) -> str | None:
        connection = self.connect()
        try:
            row = _Sql(connection, self.dialect).execute(
                "SELECT vehicle_instance_id FROM vehicle_source_observation "
                "WHERE source_observation_id = ? AND source_currentness_digest = ? "
                "AND is_current = true", (observation.observation_id,
                                          observation.source_currentness_digest),
            ).fetchone()
            if row is None:
                raise InventoryIdentityHold("HOLD_OBSERVATION_READBACK_MISSING")
            return row[0]
        finally:
            connection.close()

    def vehicle_for_key(self, key_kind: str, key_value: str) -> str | None:
        connection = self.connect()
        try:
            rows = _Sql(connection, self.dialect).execute(
                "SELECT vehicle_instance_id, durable_identity, verified_state FROM vehicle_record"
            ).fetchall()
            matches = set()
            field = {"VIN": "VIN/車身號碼", "PLATE": "車牌",
                     "CANONICAL_ID": "VEHICLE_INSTANCE_ID"}[key_kind]
            for vehicle_id, durable, verified in rows:
                if key_kind == "CANONICAL_ID" and vehicle_id == key_value:
                    matches.add(vehicle_id)
                elif str(_load_json(durable).get(field, "")) == key_value or (
                        key_kind != "CANONICAL_ID" and
                        str(_load_json(verified).get(field, "")) == key_value):
                    matches.add(vehicle_id)
            if len(matches) > 1:
                raise InventoryIdentityHold("HOLD_IDENTITY_CONFLICT")
            return next(iter(matches), None)
        finally:
            connection.close()

    def promote(self, observation: InventoryObservation, vehicle_instance_id: str,
                evidence: tuple[AdmittedDurableIdentity, ...]) -> str:
        if not evidence:
            raise InventoryIdentityHold("HOLD_IDENTITY_EVIDENCE_MISSING")
        connection = self.connect()
        db = _Sql(connection, self.dialect)
        try:
            if self.dialect == "sqlite_test":
                db.execute("BEGIN IMMEDIATE")
            vehicle = db.execute("SELECT durable_identity, verified_state FROM vehicle_record "
                                 "WHERE vehicle_instance_id = ?", (vehicle_instance_id,)).fetchone()
            if vehicle is None:
                raise InventoryIdentityHold("HOLD_CANONICAL_VEHICLE_NOT_ADMITTED")
            durable, verified = _load_json(vehicle[0]), _load_json(vehicle[1])
            for item in evidence:
                field = {"VIN": "VIN/車身號碼", "PLATE": "車牌",
                         "CANONICAL_ID": "VEHICLE_INSTANCE_ID"}[item.key_kind]
                known = str(durable.get(field) or verified.get(field) or "")
                if known and known != item.key_value:
                    raise InventoryIdentityHold("HOLD_IDENTITY_CONFLICT")
            competing = db.execute(
                "SELECT source_observation_id FROM vehicle_source_observation "
                "WHERE vehicle_instance_id = ? AND is_current = true AND source_observation_id <> ?",
                (vehicle_instance_id, observation.observation_id),
            ).fetchone()
            if competing:
                raise InventoryIdentityHold("HOLD_IDENTITY_CONFLICT")
            prior_observation = db.execute(
                "SELECT source_observation_id FROM vehicle_source_observation "
                "WHERE source_file_id = ? AND vehicle_instance_id = ? "
                "AND source_observation_id <> ?",
                (observation.source_file_id, vehicle_instance_id, observation.observation_id),
            ).fetchone()
            if prior_observation:
                raise InventoryIdentityHold("HOLD_IDENTITY_CONFLICT")
            changed = db.execute(
                "UPDATE vehicle_source_observation SET vehicle_instance_id = ?, "
                "binding_state = ?, ai_usage_state = ? WHERE source_observation_id = ? "
                "AND source_currentness_digest = ? AND is_current = true "
                "AND vehicle_instance_id IS NULL",
                (vehicle_instance_id, BindingState.INSTANCE_BOUND.value, "INSTANCE_READY",
                 observation.observation_id, observation.source_currentness_digest),
            ).rowcount
            if changed != 1:
                existing = db.execute(
                    "SELECT vehicle_instance_id FROM vehicle_source_observation "
                    "WHERE source_observation_id = ? AND source_currentness_digest = ? "
                    "AND is_current = true", (observation.observation_id,
                                              observation.source_currentness_digest),
                ).fetchone()
                if existing is None or existing[0] != vehicle_instance_id:
                    raise InventoryIdentityHold("HOLD_IDENTITY_CONFLICT")
            connection.commit()
            return vehicle_instance_id
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
