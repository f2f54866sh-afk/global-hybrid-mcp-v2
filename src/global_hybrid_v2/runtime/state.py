"""Stage 1 durable runtime task state for local single-node operation."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

CURRENT_RUNTIME_STATE_VERSION = 1


class ImageAttemptState(BaseModel):
    attempts: int = Field(default=0, ge=0)
    active: bool = False
    active_attempt_id: str | None = None
    consumed_authorization_ids: list[str] = Field(default_factory=list)
    last_terminal_result_id: str | None = None
    last_terminal_status: str | None = None


class AuthenticatedPrincipal(BaseModel):
    """Server-injected identity; Stage 1 callers cannot construct trusted ingress."""

    subject: str = Field(min_length=1)
    authentication_source: str = Field(min_length=1)


class IdentitySelectionLifecycle(StrEnum):
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    REVOKED = "REVOKED"


class IdentitySecondaryRole(StrEnum):
    BODY = "BODY"
    TATTOO = "TATTOO"
    POSE = "POSE"


Sha256Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class IdentityAuthoritySelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_id: str = Field(min_length=1)
    principal_subject: str = Field(min_length=1)
    conversation_or_thread_id: str = Field(min_length=1)
    runtime_task_id: str = Field(min_length=1)
    person_binding: str | None = None
    master_asset_id: str = Field(min_length=1)
    master_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    secondary_roles: dict[str, IdentitySecondaryRole] = Field(default_factory=dict)
    secondary_sha256: dict[str, Sha256Digest] = Field(default_factory=dict)
    excluded_generated_source_ids: set[str] = Field(default_factory=set)
    generative_only: bool = False
    revision: int = Field(ge=1)
    issued_at: datetime
    expires_at: datetime
    lifecycle: IdentitySelectionLifecycle = IdentitySelectionLifecycle.ACTIVE
    server_nonce: str = Field(min_length=1)
    server_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_identity_source_schema(self) -> IdentityAuthoritySelection:
        if self.person_binding is not None and not self.person_binding.strip():
            raise ValueError("person_binding must not be blank")
        if any(not asset_id.strip() for asset_id in self.secondary_roles):
            raise ValueError("secondary role asset IDs must not be blank")
        secondary_ids = set(self.secondary_roles)
        if self.secondary_sha256 and set(self.secondary_sha256) != secondary_ids:
            raise ValueError("secondary digest keys must exactly match secondary role keys")
        if self.master_asset_id in secondary_ids:
            raise ValueError("master asset cannot occupy a secondary role")
        if not secondary_ids.isdisjoint(self.excluded_generated_source_ids):
            raise ValueError("excluded generated source cannot occupy a secondary role")
        return self


def identity_authority_selection_digest(selection: IdentityAuthoritySelection) -> str:
    body = selection.model_dump(mode="json", exclude={"server_digest"})
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _decode_identity_authority_selection(payload: str) -> IdentityAuthoritySelection:
    data = json.loads(payload)
    schema_migration_required = (
        "lifecycle" not in data
        or "person_binding" not in data
        or "secondary_sha256" not in data
    )
    if schema_migration_required:
        stored_digest = data.get("server_digest")
        legacy_body = {
            key: value for key, value in data.items() if key != "server_digest"
        }
        legacy_digest = hashlib.sha256(
            json.dumps(
                legacy_body,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        if stored_digest != legacy_digest:
            raise RuntimeStateError("IDENTITY_SELECTION_LEGACY_DIGEST_MISMATCH")
    if "lifecycle" not in data:
        revoked = bool(data.pop("revoked", False))
        current = bool(data.pop("current", True))
        data["lifecycle"] = (
            IdentitySelectionLifecycle.REVOKED
            if revoked
            else (
                IdentitySelectionLifecycle.ACTIVE
                if current
                else IdentitySelectionLifecycle.SUPERSEDED
            )
        )
    if schema_migration_required:
        data.setdefault("person_binding", None)
        data.setdefault("secondary_sha256", {})
        migrated = IdentityAuthoritySelection.model_validate(data)
        return migrated.model_copy(
            update={"server_digest": identity_authority_selection_digest(migrated)}
        )
    return IdentityAuthoritySelection.model_validate(data)


class RuntimeTaskFrame(BaseModel):
    task_id: str = Field(min_length=1)
    primary_user_outcome: str = Field(min_length=1)
    current_phase: str = Field(min_length=1)
    next_action_candidate: str | None = None
    resume_cursor: str | None = None
    action_id: str | None = None
    idempotency_key: str | None = None
    requirement_ids: list[str] = Field(default_factory=list)


class RuntimeTaskState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_state_version: int = Field(ge=1)
    conversation_or_thread_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    primary_user_outcome: str = Field(min_length=1)
    current_progress: str = Field(min_length=1)
    active_main_task_id: str | None = Field(default=None, min_length=1)
    active_subtask_id: str | None = Field(default=None, min_length=1)
    current_phase: str = Field(min_length=1)
    active_blocker: str | None = Field(default=None, min_length=1)
    current_authority_revisions: dict[str, str] = Field(default_factory=dict)
    current_requirement_ids: list[str] = Field(default_factory=list)
    selected_route: str | None = Field(default=None, min_length=1)
    next_action_candidate: str | None = Field(default=None, min_length=1)
    last_action_id: str | None = Field(default=None, min_length=1)
    last_action_result: str | None = None
    closure_state: str = Field(min_length=1)
    resume_cursor: str | None = Field(default=None, min_length=1)
    action_id: str | None = Field(default=None, min_length=1)
    idempotency_key: str | None = Field(default=None, min_length=1)
    action_status: str | None = Field(default=None, min_length=1)
    action_effect_type: str | None = Field(default=None, min_length=1)
    action_result_status: str | None = Field(default=None, min_length=1)
    action_result_output: object = None
    action_result_evidence: dict[str, object] = Field(default_factory=dict)
    logical_action_identity: str | None = Field(default=None, min_length=1)
    interrupted_task_stack: list[RuntimeTaskFrame] = Field(default_factory=list)
    updated_at: datetime
    runtime_checkpoint_id: str | None = None
    runtime_checkpoint_event_id: str | None = None

    @model_validator(mode="after")
    def validate_version_and_time(self) -> RuntimeTaskState:
        if self.runtime_state_version != CURRENT_RUNTIME_STATE_VERSION:
            raise ValueError(f"unsupported runtime_state_version: {self.runtime_state_version}")
        if self.updated_at.tzinfo is None:
            raise ValueError("updated_at must be timezone-aware")
        return self


class RuntimeStateStore(Protocol):
    def create(self, state: RuntimeTaskState) -> RuntimeTaskState: ...

    def update(self, state: RuntimeTaskState) -> RuntimeTaskState: ...

    def load(self, conversation_or_thread_id: str, task_id: str) -> RuntimeTaskState: ...

    def create_identity_authority_selection(
        self, selection: IdentityAuthoritySelection
    ) -> IdentityAuthoritySelection: ...

    def load_identity_authority_selection(
        self, record_id: str
    ) -> IdentityAuthoritySelection: ...

    def load_current_identity_authority_selection(
        self,
        principal_subject: str,
        conversation_or_thread_id: str,
        runtime_task_id: str,
    ) -> IdentityAuthoritySelection: ...

    def supersede_identity_authority_selection(
        self,
        prior_record_id: str,
        replacement: IdentityAuthoritySelection,
        *,
        principal_subject: str,
        conversation_or_thread_id: str,
        runtime_task_id: str,
    ) -> IdentityAuthoritySelection: ...

    def revoke_identity_authority_selection(
        self,
        record_id: str,
        *,
        principal_subject: str,
        conversation_or_thread_id: str,
        runtime_task_id: str,
    ) -> IdentityAuthoritySelection: ...


class RuntimeStateError(RuntimeError):
    """Base error for durable runtime state operations."""


class RuntimeStateNotFound(RuntimeStateError):
    pass


class RuntimeStateAlreadyExists(RuntimeStateError):
    pass


class RuntimeStateVersionError(RuntimeStateError):
    pass


class SQLiteRuntimeStateStore:
    """SQLite-backed state store keyed by (conversation_or_thread_id, task_id)."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS runtime_task_state (
                    conversation_or_thread_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    runtime_state_version INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (conversation_or_thread_id, task_id)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS runtime_event_journal (
                    event_id TEXT PRIMARY KEY, conversation_or_thread_id TEXT NOT NULL,
                    task_id TEXT NOT NULL, dispatch_task_id TEXT, trace_id TEXT,
                    stage TEXT NOT NULL, event_type TEXT NOT NULL, action_id TEXT,
                    idempotency_key TEXT, checkpoint_id TEXT, payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS identity_authority_selection (
                record_id TEXT PRIMARY KEY, conversation_or_thread_id TEXT NOT NULL,
                task_id TEXT NOT NULL, payload TEXT NOT NULL,
                principal_subject TEXT, lifecycle TEXT, revision INTEGER, expires_at TEXT)"""
            )
            identity_columns = {
                row[1]
                for row in connection.execute(
                    "PRAGMA table_info(identity_authority_selection)"
                )
            }
            for name, column_type in (
                ("principal_subject", "TEXT"),
                ("lifecycle", "TEXT"),
                ("revision", "INTEGER"),
                ("expires_at", "TEXT"),
            ):
                if name not in identity_columns:
                    connection.execute(
                        f"ALTER TABLE identity_authority_selection "
                        f"ADD COLUMN {name} {column_type}"
                    )
            for record_id, payload in connection.execute(
                "SELECT record_id, payload FROM identity_authority_selection"
            ).fetchall():
                selection = _decode_identity_authority_selection(payload)
                connection.execute(
                    """
                    UPDATE identity_authority_selection
                    SET payload=?, principal_subject=?, lifecycle=?, revision=?, expires_at=?
                    WHERE record_id=?
                    """,
                    (
                        json.dumps(selection.model_dump(mode="json")),
                        selection.principal_subject,
                        selection.lifecycle.value,
                        selection.revision,
                        selection.expires_at.isoformat(),
                        record_id,
                    ),
                )
            connection.execute("""CREATE TABLE IF NOT EXISTS image_attempt_budget (
                conversation_or_thread_id TEXT NOT NULL, task_id TEXT NOT NULL,
                source_key TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 0, consumed_authorizations TEXT NOT NULL DEFAULT '[]',
                PRIMARY KEY (conversation_or_thread_id, task_id, source_key))""")
            columns = {row[1] for row in connection.execute("PRAGMA table_info(image_attempt_budget)")}
            for name in ("active_attempt_id", "last_terminal_result_id", "last_terminal_status"):
                if name not in columns:
                    connection.execute(f"ALTER TABLE image_attempt_budget ADD COLUMN {name} TEXT NULL")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def create_identity_authority_selection(
        self, selection: IdentityAuthoritySelection
    ) -> IdentityAuthoritySelection:
        self._validate_new_identity_selection(selection, expected_revision=1)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._assert_no_current_identity_selection(connection, selection)
            connection.execute(
                """
                INSERT INTO identity_authority_selection (
                    record_id, conversation_or_thread_id, task_id, payload,
                    principal_subject, lifecycle, revision, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._identity_selection_row(selection),
            )
        return selection

    def load_identity_authority_selection(self, record_id: str) -> IdentityAuthoritySelection:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM identity_authority_selection WHERE record_id = ?", (record_id,)
            ).fetchone()
        if row is None:
            raise RuntimeStateNotFound(f"identity authority selection not found: {record_id}")
        return _decode_identity_authority_selection(row[0])

    def load_current_identity_authority_selection(
        self,
        principal_subject: str,
        conversation_or_thread_id: str,
        runtime_task_id: str,
    ) -> IdentityAuthoritySelection:
        now = datetime.now(UTC)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload FROM identity_authority_selection
                WHERE principal_subject=? AND conversation_or_thread_id=? AND task_id=?
                    AND lifecycle='ACTIVE'
                ORDER BY revision DESC
                """,
                (principal_subject, conversation_or_thread_id, runtime_task_id),
            ).fetchall()
        current = [
            _decode_identity_authority_selection(row[0])
            for row in rows
            if _decode_identity_authority_selection(row[0]).expires_at > now
        ]
        if len(current) != 1:
            raise RuntimeStateError("IDENTITY_SELECTION_CURRENTNESS_INVALID")
        return current[0]

    def supersede_identity_authority_selection(
        self,
        prior_record_id: str,
        replacement: IdentityAuthoritySelection,
        *,
        principal_subject: str,
        conversation_or_thread_id: str,
        runtime_task_id: str,
    ) -> IdentityAuthoritySelection:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            prior = self._load_identity_selection_in_transaction(connection, prior_record_id)
            self._validate_active_identity_selection(
                prior,
                principal_subject=principal_subject,
                conversation_or_thread_id=conversation_or_thread_id,
                runtime_task_id=runtime_task_id,
            )
            if (
                replacement.principal_subject != principal_subject
                or replacement.conversation_or_thread_id != conversation_or_thread_id
                or replacement.runtime_task_id != runtime_task_id
                or replacement.revision != prior.revision + 1
                or replacement.lifecycle is not IdentitySelectionLifecycle.ACTIVE
            ):
                raise RuntimeStateError("IDENTITY_SELECTION_REPLACEMENT_BINDING_MISMATCH")
            self._validate_new_identity_selection(
                replacement,
                expected_revision=prior.revision + 1,
            )
            superseded = prior.model_copy(
                update={"lifecycle": IdentitySelectionLifecycle.SUPERSEDED}
            )
            superseded = superseded.model_copy(
                update={"server_digest": identity_authority_selection_digest(superseded)}
            )
            connection.execute(
                """
                UPDATE identity_authority_selection
                SET payload=?, lifecycle=?
                WHERE record_id=? AND lifecycle='ACTIVE'
                """,
                (
                    json.dumps(superseded.model_dump(mode="json")),
                    superseded.lifecycle.value,
                    prior_record_id,
                ),
            )
            connection.execute(
                """
                INSERT INTO identity_authority_selection (
                    record_id, conversation_or_thread_id, task_id, payload,
                    principal_subject, lifecycle, revision, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._identity_selection_row(replacement),
            )
        return replacement

    def revoke_identity_authority_selection(
        self,
        record_id: str,
        *,
        principal_subject: str,
        conversation_or_thread_id: str,
        runtime_task_id: str,
    ) -> IdentityAuthoritySelection:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            selection = self._load_identity_selection_in_transaction(connection, record_id)
            self._validate_active_identity_selection(
                selection,
                principal_subject=principal_subject,
                conversation_or_thread_id=conversation_or_thread_id,
                runtime_task_id=runtime_task_id,
            )
            revoked = selection.model_copy(
                update={"lifecycle": IdentitySelectionLifecycle.REVOKED}
            )
            revoked = revoked.model_copy(
                update={"server_digest": identity_authority_selection_digest(revoked)}
            )
            cursor = connection.execute(
                """
                UPDATE identity_authority_selection
                SET payload=?, lifecycle=?
                WHERE record_id=? AND lifecycle='ACTIVE'
                """,
                (json.dumps(revoked.model_dump(mode="json")), revoked.lifecycle.value, record_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeStateError("IDENTITY_SELECTION_REVOKE_CONFLICT")
        return revoked

    @staticmethod
    def _identity_selection_row(selection: IdentityAuthoritySelection) -> tuple:
        return (
            selection.record_id,
            selection.conversation_or_thread_id,
            selection.runtime_task_id,
            json.dumps(selection.model_dump(mode="json")),
            selection.principal_subject,
            selection.lifecycle.value,
            selection.revision,
            selection.expires_at.isoformat(),
        )

    @staticmethod
    def _load_identity_selection_in_transaction(
        connection: sqlite3.Connection, record_id: str
    ) -> IdentityAuthoritySelection:
        row = connection.execute(
            "SELECT payload FROM identity_authority_selection WHERE record_id=?",
            (record_id,),
        ).fetchone()
        if row is None:
            raise RuntimeStateNotFound(
                f"identity authority selection not found: {record_id}"
            )
        return _decode_identity_authority_selection(row[0])

    @staticmethod
    def _validate_active_identity_selection(
        selection: IdentityAuthoritySelection,
        *,
        principal_subject: str,
        conversation_or_thread_id: str,
        runtime_task_id: str,
    ) -> None:
        if selection.server_digest != identity_authority_selection_digest(selection):
            raise RuntimeStateError("IDENTITY_SELECTION_DIGEST_MISMATCH")
        if (
            selection.principal_subject != principal_subject
            or selection.conversation_or_thread_id != conversation_or_thread_id
            or selection.runtime_task_id != runtime_task_id
        ):
            raise RuntimeStateError("IDENTITY_SELECTION_BINDING_MISMATCH")
        if selection.lifecycle is not IdentitySelectionLifecycle.ACTIVE:
            raise RuntimeStateError("IDENTITY_SELECTION_NOT_ACTIVE")
        if selection.expires_at <= datetime.now(UTC):
            raise RuntimeStateError("IDENTITY_SELECTION_EXPIRED")

    @staticmethod
    def _validate_new_identity_selection(
        selection: IdentityAuthoritySelection,
        *,
        expected_revision: int,
    ) -> None:
        if selection.lifecycle is not IdentitySelectionLifecycle.ACTIVE:
            raise RuntimeStateError("IDENTITY_SELECTION_NOT_ACTIVE")
        if selection.revision != expected_revision:
            raise RuntimeStateError("IDENTITY_SELECTION_REVISION_MISMATCH")
        if selection.expires_at <= selection.issued_at:
            raise RuntimeStateError("IDENTITY_SELECTION_EXPIRY_INVALID")
        if selection.server_digest != identity_authority_selection_digest(selection):
            raise RuntimeStateError("IDENTITY_SELECTION_DIGEST_MISMATCH")

    @staticmethod
    def _assert_no_current_identity_selection(
        connection: sqlite3.Connection,
        selection: IdentityAuthoritySelection,
    ) -> None:
        rows = connection.execute(
            """
            SELECT payload FROM identity_authority_selection
            WHERE principal_subject=? AND conversation_or_thread_id=? AND task_id=?
                AND lifecycle='ACTIVE'
            """,
            (
                selection.principal_subject,
                selection.conversation_or_thread_id,
                selection.runtime_task_id,
            ),
        ).fetchall()
        now = datetime.now(UTC)
        if any(
            _decode_identity_authority_selection(row[0]).expires_at > now
            for row in rows
        ):
            raise RuntimeStateAlreadyExists("IDENTITY_SELECTION_ACTIVE_ALREADY_EXISTS")

    @staticmethod
    def _validate(state: RuntimeTaskState) -> RuntimeTaskState:
        if state.runtime_state_version != CURRENT_RUNTIME_STATE_VERSION:
            raise RuntimeStateVersionError(
                f"unsupported runtime_state_version: {state.runtime_state_version}"
            )
        return state

    def create(self, state: RuntimeTaskState) -> RuntimeTaskState:
        state = self._validate(state)
        payload = json.dumps(state.model_dump(mode="json"), ensure_ascii=False)
        try:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO runtime_task_state VALUES (?, ?, ?, ?)",
                    (state.conversation_or_thread_id, state.task_id, state.runtime_state_version, payload),
                )
        except sqlite3.IntegrityError as exc:
            raise RuntimeStateAlreadyExists(
                f"runtime state already exists: {state.conversation_or_thread_id}/{state.task_id}"
            ) from exc
        return state

    def update(self, state: RuntimeTaskState) -> RuntimeTaskState:
        state = self._validate(state)
        payload = json.dumps(state.model_dump(mode="json"), ensure_ascii=False)
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE runtime_task_state
                SET runtime_state_version = ?, payload = ?
                WHERE conversation_or_thread_id = ? AND task_id = ?
                """,
                (
                    state.runtime_state_version,
                    payload,
                    state.conversation_or_thread_id,
                    state.task_id,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeStateNotFound(
                    f"runtime state not found: {state.conversation_or_thread_id}/{state.task_id}"
                )
        return state

    def checkpoint(
        self,
        state: RuntimeTaskState,
        *,
        stage: str,
        event_type: str = "CHECKPOINT_COMMITTED",
        dispatch_task_id: str | None = None,
        trace_id: str | None = None,
        action_id: str | None = None,
        idempotency_key: str | None = None,
        payload: dict | None = None,
    ) -> RuntimeTaskState:
        state = self._validate(state)
        checkpoint_id = state.runtime_checkpoint_id or str(uuid4())
        event_id = str(uuid4())
        state = state.model_copy(
            update={
                "runtime_checkpoint_id": checkpoint_id,
                "runtime_checkpoint_event_id": event_id,
                "action_result_evidence": {
                    **state.action_result_evidence,
                    "runtime_checkpoint_id": checkpoint_id,
                    "runtime_checkpoint_event_id": event_id,
                },
            }
        )
        body = json.dumps(payload or state.model_dump(mode="json"), ensure_ascii=False)
        with self._connect() as connection:
            connection.execute("BEGIN")
            cursor = connection.execute(
                (
                    "UPDATE runtime_task_state SET runtime_state_version = ?, payload = ? "
                    "WHERE conversation_or_thread_id = ? AND task_id = ?"
                ),
                (
                    state.runtime_state_version,
                    json.dumps(state.model_dump(mode="json"), ensure_ascii=False),
                    state.conversation_or_thread_id,
                    state.task_id,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeStateNotFound(
                    f"runtime state not found: {state.conversation_or_thread_id}/{state.task_id}"
                )
            connection.execute(
                "INSERT INTO runtime_event_journal VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    event_id,
                    state.conversation_or_thread_id,
                    state.task_id,
                    dispatch_task_id,
                    trace_id,
                    stage,
                    event_type,
                    action_id,
                    idempotency_key,
                    checkpoint_id,
                    body,
                    state.updated_at.isoformat(),
                ),
            )
        return state

    def append_event(self, event: dict) -> str:
        event_id = event.get("event_id") or str(uuid4())
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO runtime_event_journal VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    event_id,
                    event["conversation_or_thread_id"],
                    event["runtime_task_id"],
                    event.get("dispatch_task_id"),
                    event.get("trace_id"),
                    event["stage"],
                    event.get("event_type", "TRACE"),
                    event.get("action_id"),
                    event.get("idempotency_key"),
                    event.get("checkpoint_id"),
                    json.dumps(event.get("payload", {}), ensure_ascii=False),
                    event.get("created_at", datetime.now().isoformat()),
                ),
            )
        return event_id

    def journal(self, conversation_or_thread_id: str, task_id: str) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                (
                    "SELECT event_id, stage, event_type, action_id, idempotency_key, checkpoint_id, payload "
                    "FROM runtime_event_journal WHERE conversation_or_thread_id = ? "
                    "AND task_id = ? ORDER BY rowid"
                ),
                (conversation_or_thread_id, task_id),
            ).fetchall()
        return [
            {
                "event_id": r[0],
                "stage": r[1],
                "event_type": r[2],
                "action_id": r[3],
                "idempotency_key": r[4],
                "checkpoint_id": r[5],
                "payload": json.loads(r[6]),
            }
            for r in rows
        ]

    def load(self, conversation_or_thread_id: str, task_id: str) -> RuntimeTaskState:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT runtime_state_version, payload
                FROM runtime_task_state
                WHERE conversation_or_thread_id = ? AND task_id = ?
                """,
                (conversation_or_thread_id, task_id),
            ).fetchone()
        if row is None:
            raise RuntimeStateNotFound(f"runtime state not found: {conversation_or_thread_id}/{task_id}")
        version, payload = row
        if version != CURRENT_RUNTIME_STATE_VERSION:
            raise RuntimeStateVersionError(f"unsupported runtime_state_version: {version}")
        try:
            return RuntimeTaskState.model_validate(json.loads(payload))
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise RuntimeStateVersionError("invalid or stale runtime state payload") from exc

    def reserve_image_attempt(
        self,
        conversation_or_thread_id: str,
        task_id: str,
        source_key: str,
        attempt_id: str,
        expected_attempt_number: int,
        authorization_id: str | None = None,
        prior_terminal_result_id: str | None = None,
    ) -> int:
        """Atomically reserve one image side effect and consume a single-use retry receipt."""
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT attempts, active, active_attempt_id, consumed_authorizations, last_terminal_result_id, last_terminal_status FROM image_attempt_budget WHERE conversation_or_thread_id=? AND task_id=? AND source_key=?",  # noqa: E501
                (conversation_or_thread_id, task_id, source_key),
            ).fetchone()
            attempts, active, active_attempt_id, consumed, last_result, last_status = (
                row if row else (0, 0, None, "[]", None, None)
            )
            ids = json.loads(consumed)
            if active or (authorization_id is not None and authorization_id in ids):
                raise RuntimeStateError("IMAGE_ATTEMPT_QUOTA_BLOCKED")
            if expected_attempt_number != attempts + 1:
                raise RuntimeStateError("IMAGE_ATTEMPT_NUMBER_MISMATCH")
            if attempts >= 1 and authorization_id is None:
                raise RuntimeStateError("IMAGE_RETRY_AUTHORIZATION_REQUIRED")
            if attempts >= 1 and (
                last_status is None or prior_terminal_result_id != last_result
            ):
                raise RuntimeStateError("IMAGE_PRIOR_TERMINAL_RESULT_MISMATCH")
            if authorization_id is not None:
                ids.append(authorization_id)
            attempts += 1
            connection.execute(
                """
                INSERT INTO image_attempt_budget (
                    conversation_or_thread_id, task_id, source_key, attempts, active,
                    consumed_authorizations, active_attempt_id,
                    last_terminal_result_id, last_terminal_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(conversation_or_thread_id, task_id, source_key) DO UPDATE SET
                    attempts=excluded.attempts,
                    active=1,
                    consumed_authorizations=excluded.consumed_authorizations,
                    active_attempt_id=excluded.active_attempt_id
                """,
                (
                    conversation_or_thread_id, task_id, source_key, attempts, 1,
                    json.dumps(ids), attempt_id, last_result, last_status,
                ),
            )
            return attempts

    def release_image_attempt(self, conversation_or_thread_id: str, task_id: str, source_key: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE image_attempt_budget SET active=0, attempts=attempts-1 WHERE conversation_or_thread_id=? AND task_id=? AND source_key=? AND active=1",  # noqa: E501
                (conversation_or_thread_id, task_id, source_key),
            )

    def read_image_attempt_state(
        self, conversation_or_thread_id: str, task_id: str, source_key: str
    ) -> ImageAttemptState:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT attempts, active, active_attempt_id, consumed_authorizations, "
                "last_terminal_result_id, last_terminal_status FROM image_attempt_budget "
                "WHERE conversation_or_thread_id=? AND task_id=? AND source_key=?",
                (conversation_or_thread_id, task_id, source_key),
            ).fetchone()
        if row is None:
            return ImageAttemptState()
        return ImageAttemptState(
            attempts=row[0],
            active=bool(row[1]),
            active_attempt_id=row[2],
            consumed_authorization_ids=json.loads(row[3]),
            last_terminal_result_id=row[4],
            last_terminal_status=row[5],
        )

    def complete_image_attempt(
        self,
        conversation_or_thread_id: str,
        task_id: str,
        source_key: str,
        *,
        attempt_id: str,
        terminal_result_id: str,
        terminal_status: str,
    ) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE image_attempt_budget
                SET active=0, active_attempt_id=NULL,
                    last_terminal_result_id=?, last_terminal_status=?
                WHERE conversation_or_thread_id=? AND task_id=? AND source_key=?
                    AND active=1 AND active_attempt_id=?
                """,
                (
                    terminal_result_id, terminal_status,
                    conversation_or_thread_id, task_id, source_key, attempt_id,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeStateError("IMAGE_ATTEMPT_COMPLETION_BINDING_MISMATCH")
