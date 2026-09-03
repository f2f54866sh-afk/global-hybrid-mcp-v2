from global_hybrid_v2.contracts import (
    AuthoritySnapshot,
    ContextClass,
    ContextItem,
    ContextOrigin,
    DomainResult,
    EffectType,
    Intent,
    Owner,
    TaskRequest,
)
from global_hybrid_v2.governance.pre_action import PreActionConstraintGate
from global_hybrid_v2.runtime.dispatcher import Dispatcher
from global_hybrid_v2.runtime.trace import TraceBus


def _context(*, blocker="QUOTA_5_OF_5", changed=False, target="automation", action="create"):
    return [
        ContextItem(
            id="cap",
            origin=ContextOrigin.CURRENT_TOOL_RESULT,
            context_class=ContextClass.CURRENT_CAPABILITY_FACT,
            purpose="capability",
            task_scope="automation",
            payload={
                "target_system": target,
                "action_class": action,
                "terminal_blocker": blocker,
                "capability_change_evidence": changed,
            },
            provenance=["tool:current-readback"],
        )
    ]


def test_automation_quota_blocks_sixth_create_before_tool_call():
    assert (
        not PreActionConstraintGate()
        .admit(
            target_system="automation",
            action_class="create",
            effects=[EffectType.EXTERNAL_WRITE],
            context=_context(),
        )
        .allowed
    )


def test_github_write_block_does_not_block_read():
    gate = PreActionConstraintGate()
    assert not gate.admit(
        target_system="github",
        action_class="write",
        effects=[EffectType.EXTERNAL_WRITE],
        context=_context(blocker="GITHUB_WRITE_UNAVAILABLE", target="github", action="write"),
    ).allowed
    assert gate.admit(
        target_system="github",
        action_class="write",
        effects=[EffectType.EXTERNAL_READ],
        context=_context(blocker="GITHUB_WRITE_UNAVAILABLE", target="github", action="write"),
    ).allowed


def test_fresh_capability_change_reopens_admission():
    assert (
        PreActionConstraintGate()
        .admit(
            target_system="automation",
            action_class="create",
            effects=[EffectType.EXTERNAL_WRITE],
            context=_context(changed=True),
        )
        .allowed
    )


def test_dispatcher_consumes_admitted_current_constraint_before_mutation():
    class Authority:
        def resolve(self):
            return AuthoritySnapshot(entries={})

    class Domain:
        def __init__(self):
            self.calls = 0

        def run(self, contract):
            self.calls += 1
            return DomainResult(owner=Owner.EXECUTION, status="DONE")

    domain = Domain()
    result = Dispatcher(authority=Authority(), domains={Owner.EXECUTION: domain}, trace=TraceBus()).dispatch(
        TaskRequest(
            request_text="create",
            intent=Intent.EXECUTION,
            effects=[EffectType.EXTERNAL_WRITE],
            target_system="automation",
            action_class="create",
            context=_context(),
        )
    )
    assert result.status == "PRE_ACTION_BLOCKED" and domain.calls == 0


def test_mutation_missing_state_blocks_but_read_only_passes():
    gate = PreActionConstraintGate()
    assert not gate.admit(
        target_system=None, action_class=None, effects=[EffectType.EXTERNAL_WRITE], context=[]
    ).allowed
    assert gate.admit(
        target_system=None, action_class=None, effects=[EffectType.READ_ONLY], context=[]
    ).allowed
