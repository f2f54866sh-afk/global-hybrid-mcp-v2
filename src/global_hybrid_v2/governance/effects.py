from __future__ import annotations

from dataclasses import dataclass

from global_hybrid_v2.contracts import EffectType, Owner


class EffectAuthorizationError(RuntimeError):
    pass


@dataclass(frozen=True)
class EffectDecision:
    owner: Owner
    requested: tuple[EffectType, ...]
    denied: tuple[EffectType, ...]
    allowed: bool
    policy_decision_point: str = "GLOBAL_EFFECT_POLICY"
    enforcement_point: str = "DISPATCHER_PRE_DOMAIN"
    blocker: str | None = None


OWNER_EFFECTS: dict[Owner, set[EffectType]] = {
    Owner.GLOBAL: {EffectType.READ_ONLY},
    Owner.SALES_HUMAN: {EffectType.READ_ONLY, EffectType.MODEL_INFERENCE},
    Owner.LIBRARY_FACT: {
        EffectType.READ_ONLY,
        EffectType.MODEL_INFERENCE,
        EffectType.EXTERNAL_READ,
    },
    Owner.VISUAL: {EffectType.READ_ONLY, EffectType.MODEL_INFERENCE},
    Owner.EXECUTION: set(EffectType),
}


class EffectGate:
    def __init__(self, *, live_execution: bool = True):
        self.live_execution = live_execution

    def decide(self, owner: Owner, effects: list[EffectType]) -> EffectDecision:
        allowed = OWNER_EFFECTS[owner]
        mutation = {EffectType.EXTERNAL_WRITE, EffectType.FILE_WRITE, EffectType.IMAGE_GENERATE}
        denied = tuple(
            effect for effect in effects
            if effect not in allowed or (not self.live_execution and effect in mutation)
        )
        return EffectDecision(
            owner=owner,
            requested=tuple(effects),
            denied=denied,
            allowed=not denied,
            blocker=(
                "LIVE_EXECUTION_DISABLED"
                if not self.live_execution and any(e in mutation for e in effects)
                else None
            ),
        )

    def authorize(self, owner: Owner, effects: list[EffectType]) -> EffectDecision:
        decision = self.decide(owner, effects)
        if not decision.allowed:
            names = ", ".join(effect.value for effect in decision.denied)
            raise EffectAuthorizationError(
                decision.blocker or f"{owner.value} cannot perform effects: {names}"
            )
        return decision
