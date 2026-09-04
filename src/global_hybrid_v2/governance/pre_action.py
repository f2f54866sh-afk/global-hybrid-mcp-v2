from __future__ import annotations

from dataclasses import dataclass

from global_hybrid_v2.contracts import ContextItem, EffectType


@dataclass(frozen=True)
class PreActionDecision:
    allowed: bool
    blocker: str | None = None


@dataclass(frozen=True)
class CurrentPreActionBinding:
    goal_id: str
    task_id: str
    selected_next_action: str
    responsibility_owner: str
    effect_class: EffectType
    current_constraint: str | None = None


class PreActionConstraintGate:
    MUTATIONS = {EffectType.EXTERNAL_WRITE, EffectType.FILE_WRITE, EffectType.IMAGE_GENERATE}

    def admit(
        self,
        *,
        target_system: str | None,
        action_class: str | None,
        effects: list[EffectType],
        context: list[ContextItem],
        current_binding: CurrentPreActionBinding | None = None,
        proposed_owner: str | None = None,
    ) -> PreActionDecision:
        if not self.MUTATIONS & set(effects):
            return PreActionDecision(allowed=True)
        if not target_system or not action_class:
            return PreActionDecision(allowed=False, blocker="PRE_ACTION_TARGET_OR_CLASS_UNRESOLVED")
        matched = False
        for item in context:
            payload = item.payload if isinstance(item.payload, dict) else {}
            if payload.get("target_system") != target_system or payload.get("action_class") != action_class:
                continue
            matched = True
            if payload.get("capability_change_evidence") is True:
                continue
            blocker = payload.get("terminal_blocker")
            if isinstance(blocker, str) and blocker:
                return PreActionDecision(allowed=False, blocker=blocker)
        if not matched:
            return PreActionDecision(allowed=False, blocker="PRE_ACTION_CAPABILITY_UNRESOLVED")
        if current_binding is not None:
            if (
                proposed_owner != current_binding.responsibility_owner
                or current_binding.effect_class not in effects
                or not current_binding.selected_next_action
            ):
                return PreActionDecision(allowed=False, blocker="BLOCK_ACTION_SELECTION_DRIFT")
        return PreActionDecision(allowed=True)
