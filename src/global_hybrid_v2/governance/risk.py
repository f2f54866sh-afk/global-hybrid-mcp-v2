from __future__ import annotations

from global_hybrid_v2.contracts import (
    EffectType,
    RiskClass,
    TaskRequest,
)

_RISK_ORDER = {
    RiskClass.R0: 0,
    RiskClass.R1: 1,
    RiskClass.R2: 2,
    RiskClass.R3: 3,
    RiskClass.R4: 4,
}


class TaskRiskClassifier:
    """Apply only the minimum risk floor implied by observable requested effects."""

    def classify(self, request: TaskRequest) -> RiskClass:
        effects = set(request.effects)
        if effects & {EffectType.FILE_WRITE, EffectType.EXTERNAL_WRITE}:
            minimum = RiskClass.R4
        elif EffectType.IMAGE_GENERATE in effects:
            minimum = RiskClass.R3
        elif EffectType.EXTERNAL_READ in effects:
            minimum = RiskClass.R2
        elif EffectType.MODEL_INFERENCE in effects:
            minimum = RiskClass.R1
        else:
            minimum = RiskClass.R0

        requested = request.risk_class
        if requested is None or _RISK_ORDER[requested] < _RISK_ORDER[minimum]:
            return minimum
        return requested
