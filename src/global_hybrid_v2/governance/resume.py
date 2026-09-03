"""Fail-closed rehydration of an interrupted engineering task."""

from __future__ import annotations

from dataclasses import dataclass

from global_hybrid_v2.contracts import EngineeringCheckpoint, ResumeRehydrationReceipt

RESUME_BLOCKED = "RESUME_REHYDRATION_BLOCKED"
RESUME_RUNTIME_IDENTITY_UNAVAILABLE = "RESUME_RUNTIME_IDENTITY_UNAVAILABLE"
RESUME_STATE_SCHEMA_INCOMPATIBLE = "RESUME_STATE_SCHEMA_INCOMPATIBLE"
RESUME_AUTHORITY_MISMATCH = "RESUME_AUTHORITY_MISMATCH"
RESUME_COMMIT_BRANCH_MISMATCH = "RESUME_COMMIT_BRANCH_MISMATCH"
RESUME_CAPABILITY_SNAPSHOT_MISMATCH = "RESUME_CAPABILITY_SNAPSHOT_MISMATCH"
RESUME_CONSTRAINT_MISMATCH = "RESUME_CONSTRAINT_MISMATCH"
RESUME_NO_UNFINISHED_STEP = "RESUME_NO_UNFINISHED_STEP"
RESUME_TERMINAL_BLOCKER = "RESUME_TERMINAL_BLOCKER"
RESUME_EFFECT_REPLAY_UNSAFE = "RESUME_EFFECT_REPLAY_UNSAFE"
CURRENT_RESUME_STATE_SCHEMA = 1


@dataclass(frozen=True)
class ResumeAdmission:
    allowed: bool
    blocker: str | None = None
    receipt: ResumeRehydrationReceipt | None = None


class ResumeGate:
    """A single compatibility and replay gate for resumed engineering mutation."""

    def admit(
        self,
        checkpoint: EngineeringCheckpoint,
        *,
        current_authority: dict[str, str],
        current_commit: str | None,
        current_branch: str | None,
        current_item_id: str | None,
        current_backlog_snapshot_id: str | None,
        current_capability_snapshot_id: str | None,
        current_hard_constraints: list[str],
        replay_effect_id: str | None,
        replay_authorized: bool,
    ) -> ResumeAdmission:
        def blocked(code: str) -> ResumeAdmission:
            return ResumeAdmission(False, code)

        if checkpoint.state_schema_version != CURRENT_RESUME_STATE_SCHEMA:
            return blocked(RESUME_STATE_SCHEMA_INCOMPATIBLE)
        if not current_commit or not current_branch:
            return blocked(RESUME_RUNTIME_IDENTITY_UNAVAILABLE)
        if checkpoint.commit_sha != current_commit or checkpoint.branch != current_branch:
            return blocked(RESUME_COMMIT_BRANCH_MISMATCH)
        if checkpoint.authority_revisions != current_authority:
            return blocked(RESUME_AUTHORITY_MISMATCH)
        if not current_item_id or checkpoint.engineering_item_id != current_item_id:
            return blocked(RESUME_CONSTRAINT_MISMATCH)
        if (
            not current_backlog_snapshot_id
            or checkpoint.engineering_backlog_snapshot_id != current_backlog_snapshot_id
        ):
            return blocked(RESUME_CONSTRAINT_MISMATCH)
        if (
            not current_capability_snapshot_id
            or checkpoint.capability_snapshot_id != current_capability_snapshot_id
        ):
            return blocked(RESUME_CAPABILITY_SNAPSHOT_MISMATCH)
        if checkpoint.hard_constraints != current_hard_constraints:
            return blocked(RESUME_CONSTRAINT_MISMATCH)
        if checkpoint.resume_step_id not in checkpoint.unfinished_steps:
            return blocked(RESUME_NO_UNFINISHED_STEP)
        if checkpoint.resume_step_id in checkpoint.completed_steps and not checkpoint.fresh_regression:
            return blocked(RESUME_NO_UNFINISHED_STEP)
        if checkpoint.terminal_blocker:
            if not checkpoint.fresh_capability_change_evidence:
                return blocked(RESUME_TERMINAL_BLOCKER)

        completed = {item.effect_id: item for item in checkpoint.completed_effects}
        effect = completed.get(replay_effect_id or "")
        replay_status = "NOT_APPLICABLE"
        if effect is not None:
            replay_safe = bool(effect.idempotency_key and effect.replay_safe_proof)
            if not replay_safe and not (replay_authorized and checkpoint.replay_authorized):
                return blocked(RESUME_EFFECT_REPLAY_UNSAFE)
            replay_status = "REPLAY_SAFE" if replay_safe else "FRESH_AUTHORIZED"
        receipt = ResumeRehydrationReceipt(
            checkpoint_id=checkpoint.checkpoint_id,
            checkpoint_version=checkpoint.checkpoint_version,
            authority_revisions=checkpoint.authority_revisions,
            commit_sha=checkpoint.commit_sha,
            branch=checkpoint.branch,
            compatibility_result="PASS",
            capability_snapshot_id=checkpoint.capability_snapshot_id,
            engineering_backlog_snapshot_id=checkpoint.engineering_backlog_snapshot_id,
            resumed_step=checkpoint.resume_step_id,
            completed_effect_ids=list(completed),
            replay_status=replay_status,
            status="RESUMED",
            reason="compatible unfinished engineering step admitted",
        )
        return ResumeAdmission(True, receipt=receipt)
