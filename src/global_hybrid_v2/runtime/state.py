"""Stage 1 durable runtime task state for local single-node operation."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

CURRENT_RUNTIME_STATE_VERSION = 1


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

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

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
