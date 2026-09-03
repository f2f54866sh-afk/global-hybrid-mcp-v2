from __future__ import annotations

from dataclasses import dataclass

from global_hybrid_v2.contracts import ContextItem, EffectType


@dataclass(frozen=True)
class PreActionDecision:
    allowed: bool
    blocker: str | None = None


class PreActionConstraintGate:
    MUTATIONS = {EffectType.EXTERNAL_WRITE, EffectType.FILE_WRITE, EffectType.IMAGE_GENERATE}

    def admit(
        self,
        *,
        target_system: str | None,
        action_class: str | None,
        effects: list[EffectType],
        context: list[ContextItem],
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
        return PreActionDecision(allowed=True)
