import pytest

from global_hybrid_v2.contracts import (
    AuthorityDocument,
    AuthorityDocumentRole,
    AuthorityEntry,
    AuthoritySnapshot,
    CompletedEffect,
    ContextClass,
    ContextItem,
    ContextOrigin,
    DomainResult,
    EffectType,
    EngineeringCheckpoint,
    Intent,
    Owner,
    TaskRequest,
)
from global_hybrid_v2.governance.resume import (
    CURRENT_RESUME_STATE_SCHEMA,
    RESUME_AUTHORITY_MISMATCH,
    RESUME_COMMIT_BRANCH_MISMATCH,
    RESUME_EFFECT_REPLAY_UNSAFE,
    RESUME_NO_UNFINISHED_STEP,
    RESUME_RUNTIME_IDENTITY_UNAVAILABLE,
    RESUME_STATE_SCHEMA_INCOMPATIBLE,
    RESUME_TERMINAL_BLOCKER,
)
from global_hybrid_v2.runtime.dispatcher import Dispatcher
from global_hybrid_v2.runtime.trace import TraceBus


class _Authority:
    def resolve(self):
        document = AuthorityDocument(
            name="EXECUTION",
            role=AuthorityDocumentRole.LIVE_AUTHORITY,
            revision="rev-1",
            path="EXECUTION.md",
        )
        return AuthoritySnapshot(
            entries={
                Owner.EXECUTION: AuthorityEntry(
                    owner=Owner.EXECUTION,
                    normative_authority=document,
                )
            }
        )


class _Domain:
    def __init__(self):
        self.contract = None

    def run(self, contract):
        self.contract = contract
        return DomainResult(owner=contract.owner, status="DONE")


def _checkpoint(**updates) -> EngineeringCheckpoint:
    values = {
        "checkpoint_id": "cp-1",
        "checkpoint_version": "cp-v1",
        "state_schema_version": CURRENT_RESUME_STATE_SCHEMA,
        "engineering_item_id": "ENG-RESUME",
        "engineering_backlog_snapshot_id": "backlog-1",
        "authority_revisions": {"EXECUTION": "rev-1"},
        "commit_sha": "abc123",
        "branch": "hardening/engineering-resume-gate",
        "capability_snapshot_id": "cap-1",
        "hard_constraints": ["no-duplicate-effect"],
        "completed_steps": ["step-1"],
        "unfinished_steps": ["step-2"],
        "resume_step_id": "step-2",
    }
    values.update(updates)
    return EngineeringCheckpoint(**values)


def _request(checkpoint: EngineeringCheckpoint | None = None, **updates) -> TaskRequest:
    values = {
        "request_text": "resume engineering step",
        "intent": Intent.EXECUTION,
        "effects": [EffectType.EXTERNAL_WRITE],
        "target_system": "test-system",
        "action_class": "write",
        "context": [
            ContextItem(
                id="capability",
                origin=ContextOrigin.CURRENT_TOOL_RESULT,
                context_class=ContextClass.CURRENT_CAPABILITY_FACT,
                purpose="current capability",
                task_scope="resume",
                payload={
                    "target_system": "test-system",
                    "action_class": "write",
                },
                provenance=["test:current-readback"],
            )
        ],
        "engineering_checkpoint": checkpoint,
        "engineering_item_id": "ENG-RESUME",
        "engineering_backlog_snapshot_id": "backlog-1",
        "capability_snapshot_id": "cap-1",
        "hard_constraints": ["no-duplicate-effect"],
    }
    values.update(updates)
    return TaskRequest(**values)


def _dispatch(request: TaskRequest, domain: _Domain | None = None):
    domain = domain or _Domain()
    result = Dispatcher(
        authority=_Authority(),
        domains={Owner.EXECUTION: domain},
        trace=TraceBus(),
        runtime_commit="abc123",
        runtime_branch="hardening/engineering-resume-gate",
    ).dispatch(request)
    return result, domain


def test_compatible_resume_only_rehydrates_unfinished_step_and_emits_receipt():
    result, domain = _dispatch(_request(_checkpoint()))

    assert result.status == "DONE"
    assert domain.contract.resume_rehydration_receipt.status == "RESUMED"
    assert domain.contract.resume_rehydration_receipt.resumed_step == "step-2"
    assert result.evidence["resume_rehydration"] == "PASS"


@pytest.mark.parametrize(
    ("field", "value", "status"),
    [
        ("authority_revisions", {"EXECUTION": "old"}, RESUME_AUTHORITY_MISMATCH),
        ("commit_sha", "other", RESUME_COMMIT_BRANCH_MISMATCH),
        ("branch", "main", RESUME_COMMIT_BRANCH_MISMATCH),
        ("state_schema_version", CURRENT_RESUME_STATE_SCHEMA + 1, RESUME_STATE_SCHEMA_INCOMPATIBLE),
    ],
)
def test_resume_compatibility_mismatch_blocks(field, value, status):
    result, domain = _dispatch(_request(_checkpoint(**{field: value})))
    assert result.status == status
    assert domain.contract is None


def test_missing_runtime_identity_blocks_resume():
    dispatcher = Dispatcher(
        authority=_Authority(), domains={Owner.EXECUTION: _Domain()}, trace=TraceBus()
    )
    result = dispatcher.dispatch(_request(_checkpoint()))
    assert result.status == RESUME_RUNTIME_IDENTITY_UNAVAILABLE


def test_completed_step_without_fresh_regression_cannot_reopen():
    result, _ = _dispatch(
        _request(_checkpoint(completed_steps=["step-2"], unfinished_steps=["step-2"]))
    )
    assert result.status == RESUME_NO_UNFINISHED_STEP


def test_terminal_blocker_without_capability_change_cannot_retry():
    result, _ = _dispatch(_request(_checkpoint(terminal_blocker="QUOTA_5_OF_5")))
    assert result.status == RESUME_TERMINAL_BLOCKER


def test_completed_effect_is_not_replayed_without_idempotency_or_authorization():
    checkpoint = _checkpoint(
        completed_effects=[CompletedEffect(effect_id="effect-1")],
    )
    result, _ = _dispatch(_request(checkpoint, replay_effect_id="effect-1"))
    assert result.status == RESUME_EFFECT_REPLAY_UNSAFE


def test_completed_effect_with_replay_safe_proof_can_resume():
    checkpoint = _checkpoint(
        completed_effects=[
            CompletedEffect(
                effect_id="effect-1",
                idempotency_key="idem-1",
                replay_safe_proof="proof-1",
            )
        ],
    )
    result, _ = _dispatch(_request(checkpoint, replay_effect_id="effect-1"))
    assert result.status == "DONE"
    assert result.evidence["resume_rehydration_receipt"]["replay_status"] == "REPLAY_SAFE"


def test_ordinary_chat_without_checkpoint_does_not_depend_on_engineering_state():
    result, _ = _dispatch(
        TaskRequest(request_text="hello", intent=Intent.EXECUTION, effects=[EffectType.READ_ONLY])
    )
    assert result.status == "DONE"
