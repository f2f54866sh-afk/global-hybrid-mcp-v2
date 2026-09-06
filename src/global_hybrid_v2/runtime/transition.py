"""Stage 2 deterministic continuation transition selection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from global_hybrid_v2.contracts import DomainResult, TaskRequest
from global_hybrid_v2.runtime.state import RuntimeTaskFrame, RuntimeTaskState


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
                state.next_action_candidate,
            )
        if state.last_action_result in {"DONE", "PASS", "CLOSED"}:
            return TransitionDecision("WAIT", "completed action has no new candidate")
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
        restored_frame = (
            state.interrupted_task_stack[-1]
            if support_completed and state.interrupted_task_stack
            else None
        )
        action_id = state.action_id or transition.reason
        restored_action_id = (
            restored_frame.action_id
            if restored_frame is not None and restored_frame.action_id
            else action_id
        )
        return state.model_copy(
            update={
                "current_progress": status,
                "active_blocker": status if blocked else None,
                "last_action_id": action_id,
                "last_action_result": status,
                "action_id": restored_action_id,
                "logical_action_identity": transition.reason,
                "action_status": "COMPLETED" if not blocked else "FAILED",
                "action_result_status": status,
                "action_result_output": result.output,
                "action_result_evidence": result.evidence,
                "next_action_candidate": (
                    restored_frame.next_action_candidate
                    if restored_frame is not None
                    else state.resume_cursor
                    if support_completed
                    else None if not blocked else state.next_action_candidate
                ),
                "active_subtask_id": None if support_completed else state.active_subtask_id,
                "active_main_task_id": (
                    restored_frame.task_id if restored_frame is not None else state.active_main_task_id
                ),
                "primary_user_outcome": (
                    restored_frame.primary_user_outcome
                    if restored_frame is not None
                    else state.primary_user_outcome
                ),
                "current_requirement_ids": (
                    restored_frame.requirement_ids
                    if restored_frame is not None
                    else state.current_requirement_ids
                ),
                "resume_cursor": (
                    restored_frame.resume_cursor
                    if restored_frame is not None
                    else state.resume_cursor
                ),
                "interrupted_task_stack": (
                    state.interrupted_task_stack[:-1]
                    if restored_frame is not None
                    else state.interrupted_task_stack
                ),
                "closure_state": (
                    "OPEN"
                    if support_completed
                    else "CLOSED" if status in {"DONE", "PASS", "CLOSED"} else state.closure_state
                ),
                "current_phase": (
                    "PARENT_CONTINUATION"
                    if support_completed
                    else "BLOCKED" if blocked else "COMPLETED"
                ),
                "updated_at": datetime.now(UTC),
            }
        )
    def interrupt(self, state: RuntimeTaskState, child_task_id: str) -> RuntimeTaskState:
        frame = RuntimeTaskFrame(
            task_id=state.task_id,
            primary_user_outcome=state.primary_user_outcome,
            current_phase=state.current_phase,
            next_action_candidate=state.next_action_candidate,
            resume_cursor=state.resume_cursor,
            action_id=state.action_id,
            requirement_ids=state.current_requirement_ids,
        )
        return state.model_copy(update={
            "interrupted_task_stack": [*state.interrupted_task_stack, frame],
            "active_subtask_id": child_task_id,
            "current_phase": "INTERRUPTED",
        })
