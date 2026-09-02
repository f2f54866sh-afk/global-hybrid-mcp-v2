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
    def decide(self, owner: Owner, effects: list[EffectType]) -> EffectDecision:
        allowed = OWNER_EFFECTS[owner]
        denied = tuple(effect for effect in effects if effect not in allowed)
        return EffectDecision(
            owner=owner,
            requested=tuple(effects),
            denied=denied,
            allowed=not denied,
        )

    def authorize(self, owner: Owner, effects: list[EffectType]) -> EffectDecision:
        decision = self.decide(owner, effects)
        if not decision.allowed:
            names = ", ".join(effect.value for effect in decision.denied)
            raise EffectAuthorizationError(f"{owner.value} cannot perform effects: {names}")
        return decision
