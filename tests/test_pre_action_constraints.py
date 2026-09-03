from global_hybrid_v2.contracts import ContextClass, ContextItem, ContextOrigin, EffectType
from global_hybrid_v2.governance.pre_action import PreActionConstraintGate


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
