from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from global_hybrid_v2.contracts import EffectType, MaterialChangeReason, RetryContext

REPEAT_BLOCKED_NO_NEW_EVIDENCE = "REPEAT_BLOCKED_NO_NEW_EVIDENCE"


@dataclass(frozen=True)
class RepeatActionAdmission:
    decision: str
    metadata: dict[str, Any]

    @property
    def allowed(self) -> bool:
        return self.decision == "PASS"


class RepeatActionGate:
    SIDE_EFFECTS = {
        EffectType.EXTERNAL_WRITE,
        EffectType.FILE_WRITE,
        EffectType.IMAGE_GENERATE,
    }

    def evaluate(
        self,
        *,
        effects: list[EffectType],
        retry_context: RetryContext | None,
    ) -> RepeatActionAdmission:
        context = retry_context
        prior_failure_present = bool(
            context and (context.prior_failure_signature or "").strip()
        )
        transient = context.transient_retry_evidence if context else None
        transient_present = transient is not None
        transient_verified = bool(transient and transient.verified)
        admitted_reasons = self._admitted_reasons(context, transient_verified)
        metadata = {
            "operation_key": context.operation_key if context else None,
            "prior_failure_signature_present": prior_failure_present,
            "material_change_reasons": admitted_reasons,
            "transient_retry_evidence_present": transient_present,
        }

        is_side_effect = bool(set(effects) & self.SIDE_EFFECTS)
        if is_side_effect and prior_failure_present and not admitted_reasons:
            return RepeatActionAdmission(decision="DENY", metadata=metadata)
        return RepeatActionAdmission(decision="PASS", metadata=metadata)

    @staticmethod
    def _admitted_reasons(
        context: RetryContext | None,
        transient_verified: bool,
    ) -> list[str]:
        if context is None:
            return []
        allowed = {reason.value for reason in MaterialChangeReason}
        admitted = []
        for reason in context.material_change_reasons:
            if reason not in allowed:
                continue
            if (
                reason == MaterialChangeReason.VERIFIED_TRANSIENT_RETRY_CONDITION
                and not transient_verified
            ):
                continue
            if reason not in admitted:
                admitted.append(reason)
        if transient_verified:
            transient_reason = MaterialChangeReason.VERIFIED_TRANSIENT_RETRY_CONDITION.value
            if transient_reason not in admitted:
                admitted.append(transient_reason)
        return admitted
