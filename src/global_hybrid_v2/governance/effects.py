from __future__ import annotations

from global_hybrid_v2.contracts import EffectType, Owner


class EffectAuthorizationError(RuntimeError):
    pass


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
    def authorize(self, owner: Owner, effects: list[EffectType]) -> None:
        allowed = OWNER_EFFECTS[owner]
        denied = [effect for effect in effects if effect not in allowed]
        if denied:
            names = ", ".join(effect.value for effect in denied)
            raise EffectAuthorizationError(f"{owner.value} cannot perform effects: {names}")
