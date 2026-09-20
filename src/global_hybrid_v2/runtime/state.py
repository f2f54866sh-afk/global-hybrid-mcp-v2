"""Stage 1 durable runtime task state for local single-node operation."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

CURRENT_RUNTIME_STATE_VERSION = 1


class ImageAttemptState(BaseModel):
    attempts: int = Field(default=0, ge=0)
    active: bool = False
    active_attempt_id: str | None = None
    last_attempt_id: str | None = None
    consumed_authorization_ids: list[str] = Field(default_factory=list)
    last_terminal_result_id: str | None = None
    last_terminal_status: str | None = None
    effect_lifecycle: str | None = None
    started_at: datetime | None = None
    provider_operation_id: str | None = None
    artifact_id: str | None = None


class RuntimeTaskFrame(BaseModel):
    task_id: str = Field(min_length=1)
    primary_user_outcome: str = Field(min_length=1)
    current_phase: str = Field(min_length=1)
    next_action_candidate: str | None = None
    resume_cursor: str | None = None
    action_id: str | None = None
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

    @model_validator(mode="after")
    def validate_version_and_time(self) -> RuntimeTaskState:
        if self.runtime_state_version != CURRENT_RUNTIME_STATE_VERSION:
            raise ValueError(
                f"unsupported runtime_state_version: {self.runtime_state_version}"
            )
        if self.updated_at.tzinfo is None:
            raise ValueError("updated_at must be timezone-aware")
        return self


class RuntimeStateStore(Protocol):
    def create(self, state: RuntimeTaskState) -> RuntimeTaskState: ...

    def update(self, state: RuntimeTaskState) -> RuntimeTaskState: ...

    def load(self, conversation_or_thread_id: str, task_id: str) -> RuntimeTaskState: ...


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
            connection.execute("""CREATE TABLE IF NOT EXISTS image_attempt_budget (
                conversation_or_thread_id TEXT NOT NULL, task_id TEXT NOT NULL,
                source_key TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 0, consumed_authorizations TEXT NOT NULL DEFAULT '[]',
                PRIMARY KEY (conversation_or_thread_id, task_id, source_key))""")
            columns = {row[1] for row in connection.execute("PRAGMA table_info(image_attempt_budget)")}
            for name in (
                "active_attempt_id", "last_terminal_result_id", "last_terminal_status",
                "effect_lifecycle", "started_at", "provider_operation_id", "artifact_id",
                "last_attempt_id",
            ):
                if name not in columns:
                    connection.execute(f"ALTER TABLE image_attempt_budget ADD COLUMN {name} TEXT NULL")
            connection.execute(
                """
                UPDATE image_attempt_budget
                SET active=0, effect_lifecycle='INTERRUPTED_UNKNOWN'
                WHERE active=1 AND (effect_lifecycle IS NULL OR effect_lifecycle IN ('RESERVED', 'IN_FLIGHT'))
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("PRAGMA synchronous=EXTRA")
        return connection

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
        self, conversation_or_thread_id: str, task_id: str, source_key: str,
        attempt_id: str, expected_attempt_number: int,
        authorization_id: str | None = None,
        prior_terminal_result_id: str | None = None,
    ) -> int:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT attempts, active, consumed_authorizations, last_terminal_result_id, "
                "last_terminal_status, effect_lifecycle FROM image_attempt_budget WHERE "
                "conversation_or_thread_id=? AND task_id=? AND source_key=?",
                (conversation_or_thread_id, task_id, source_key),
            ).fetchone()
            attempts, active, consumed, last_result, last_status, lifecycle = (
                row if row else (0, 0, "[]", None, None, None)
            )
            ids = json.loads(consumed)
            if lifecycle == "INTERRUPTED_UNKNOWN":
                raise RuntimeStateError("IMAGE_PRIOR_OUTCOME_UNKNOWN")
            if active or (authorization_id is not None and authorization_id in ids):
                raise RuntimeStateError("IMAGE_ATTEMPT_QUOTA_BLOCKED")
            if expected_attempt_number != attempts + 1:
                raise RuntimeStateError("IMAGE_ATTEMPT_NUMBER_MISMATCH")
            if attempts >= 1 and authorization_id is None:
                raise RuntimeStateError("IMAGE_RETRY_AUTHORIZATION_REQUIRED")
            if attempts >= 1 and (last_status is None or prior_terminal_result_id != last_result):
                raise RuntimeStateError("IMAGE_PRIOR_TERMINAL_RESULT_MISMATCH")
            if authorization_id is not None:
                ids.append(authorization_id)
            attempts += 1
            connection.execute(
                """
                INSERT INTO image_attempt_budget (
                    conversation_or_thread_id, task_id, source_key, attempts, active,
                    consumed_authorizations, active_attempt_id, last_terminal_result_id,
                    last_terminal_status, effect_lifecycle, started_at,
                    provider_operation_id, artifact_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(conversation_or_thread_id, task_id, source_key) DO UPDATE SET
                    attempts=excluded.attempts, active=1,
                    consumed_authorizations=excluded.consumed_authorizations,
                    active_attempt_id=excluded.active_attempt_id,
                    effect_lifecycle='RESERVED', started_at=NULL,
                    provider_operation_id=NULL, artifact_id=NULL
                """,
                (
                    conversation_or_thread_id, task_id, source_key, attempts, 1,
                    json.dumps(ids), attempt_id, last_result, last_status,
                    "RESERVED", None, None, None,
                ),
            )
            return attempts

    def mark_image_attempt_in_flight(
        self, conversation_or_thread_id: str, task_id: str, source_key: str,
        *, attempt_id: str, started_at: datetime,
    ) -> None:
        if started_at.tzinfo is None:
            raise RuntimeStateError("IMAGE_ATTEMPT_STARTED_AT_NOT_TIMEZONE_AWARE")
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE image_attempt_budget SET effect_lifecycle='IN_FLIGHT', started_at=?
                WHERE conversation_or_thread_id=? AND task_id=? AND source_key=?
                    AND active=1 AND active_attempt_id=? AND effect_lifecycle='RESERVED'
                """,
                (started_at.isoformat(), conversation_or_thread_id, task_id, source_key, attempt_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeStateError("IMAGE_ATTEMPT_IN_FLIGHT_BINDING_MISMATCH")

    def release_image_attempt(self, conversation_or_thread_id: str, task_id: str, source_key: str) -> None:
        del conversation_or_thread_id, task_id, source_key
        raise RuntimeStateError("IMAGE_ATTEMPT_RELEASE_FORBIDDEN")

    def read_image_attempt_state(
        self, conversation_or_thread_id: str, task_id: str, source_key: str
    ) -> ImageAttemptState:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT attempts, active, active_attempt_id, consumed_authorizations, "
                "last_terminal_result_id, last_terminal_status, effect_lifecycle, started_at, "
                "provider_operation_id, artifact_id, last_attempt_id FROM image_attempt_budget "
                "WHERE conversation_or_thread_id=? AND task_id=? AND source_key=?",
                (conversation_or_thread_id, task_id, source_key),
            ).fetchone()
        if row is None:
            return ImageAttemptState()
        return ImageAttemptState(
            attempts=row[0], active=bool(row[1]), active_attempt_id=row[2],
            consumed_authorization_ids=json.loads(row[3]), last_terminal_result_id=row[4],
            last_terminal_status=row[5], effect_lifecycle=row[6],
            started_at=datetime.fromisoformat(row[7]) if row[7] else None,
            provider_operation_id=row[8], artifact_id=row[9], last_attempt_id=row[10],
        )

    def complete_image_attempt(
        self, conversation_or_thread_id: str, task_id: str, source_key: str, *,
        attempt_id: str, terminal_result_id: str, terminal_status: str,
        provider_operation_id: str | None = None, artifact_id: str | None = None,
    ) -> None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT effect_lifecycle FROM image_attempt_budget WHERE "
                "conversation_or_thread_id=? AND task_id=? AND source_key=? AND active_attempt_id=?",
                (conversation_or_thread_id, task_id, source_key, attempt_id),
            ).fetchone()
            if row is None:
                raise RuntimeStateError("IMAGE_ATTEMPT_COMPLETION_BINDING_MISMATCH")
            lifecycle = row[0]
            if lifecycle not in {"IN_FLIGHT", "INTERRUPTED_UNKNOWN"}:
                raise RuntimeStateError("IMAGE_ATTEMPT_COMPLETION_LIFECYCLE_MISMATCH")
            if lifecycle == "INTERRUPTED_UNKNOWN":
                evidence_result_id = artifact_id or provider_operation_id
                if evidence_result_id is None or terminal_result_id != evidence_result_id:
                    raise RuntimeStateError("IMAGE_LATE_RECONCILIATION_EVIDENCE_REQUIRED")
            cursor = connection.execute(
                """
                UPDATE image_attempt_budget SET active=0, active_attempt_id=NULL,
                    last_terminal_result_id=?, last_terminal_status=?, effect_lifecycle='TERMINAL',
                    provider_operation_id=?, artifact_id=?, last_attempt_id=?
                WHERE conversation_or_thread_id=? AND task_id=? AND source_key=?
                    AND active_attempt_id=? AND effect_lifecycle IN ('IN_FLIGHT', 'INTERRUPTED_UNKNOWN')
                """,
                (
                    terminal_result_id, terminal_status, provider_operation_id, artifact_id,
                    attempt_id, conversation_or_thread_id, task_id, source_key, attempt_id,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeStateError("IMAGE_ATTEMPT_COMPLETION_BINDING_MISMATCH")
