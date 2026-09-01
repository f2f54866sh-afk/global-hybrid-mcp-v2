from __future__ import annotations

from global_hybrid_v2.contracts import TraceEvent, WitnessFinding


class ReadOnlyWitness:
    """Observer has no mutator/tool dependency by construction."""

    def observe(self, event: TraceEvent) -> WitnessFinding | None:
        if event.stage == "effect_gate" and event.decision == "DENY":
            return WitnessFinding(
                task_id=event.task_id,
                severity="warning",
                code="EFFECT_DENIED",
                message="Side effect was rejected by the control plane.",
            )
        return None
