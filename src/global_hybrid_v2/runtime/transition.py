"""Stage 2 deterministic continuation transition selection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from global_hybrid_v2.contracts import DomainResult, TaskRequest
from global_hybrid_v2.runtime.state import RuntimeTaskState


@dataclass(frozen=True)
class TransitionDecision:
    kind: str
    reason: str


class TransitionController:
    """Consumes current durable state and the current request/result only."""

    def decide(self, state: RuntimeTaskState, request: TaskRequest) -> TransitionDecision:
        if state.active_blocker:
            return TransitionDecision("WAIT", "active blocker remains")
        if state.closure_state == "CLOSED":
            return TransitionDecision("CLOSE", "runtime task already closed")
        if state.next_action_candidate:
            executable_effects = {
                "external_write",
                "file_write",
                "image_generate",
            }
            is_executable = any(effect.value in executable_effects for effect in request.effects)
            if state.active_subtask_id and state.last_action_result in {"DONE", "PASS", "CLOSED"}:
                return TransitionDecision("SUPPORT", "complete support and resume parent task")
            return TransitionDecision(
                "EXECUTE" if is_executable else "SUPPORT",
                f"continue candidate {state.next_action_candidate}",
            )
        return TransitionDecision("SUPPORT", "continue current runtime task")

    def consume_result(
        self,
        state: RuntimeTaskState,
        request: TaskRequest,
        result: DomainResult,
        transition: TransitionDecision,
    ) -> RuntimeTaskState:
        status = result.status
        blocked = status.startswith("BLOCK") or status.endswith("BLOCKED") or "FAIL" in status
        support_completed = (
            state.active_subtask_id is not None
            and status in {"DONE", "PASS", "CLOSED"}
        )
        return state.model_copy(
            update={
                "current_progress": status,
                "current_phase": "BLOCKED" if blocked else "COMPLETED",
                "active_blocker": status if blocked else None,
                "last_action_id": transition.kind,
                "last_action_result": status,
                "next_action_candidate": None if not blocked else state.next_action_candidate,
                "active_subtask_id": None if support_completed else state.active_subtask_id,
                "active_main_task_id": state.active_main_task_id,
                "closure_state": "CLOSED" if status in {"DONE", "PASS", "CLOSED"} else state.closure_state,
                "updated_at": datetime.now(UTC),
            }
        )
