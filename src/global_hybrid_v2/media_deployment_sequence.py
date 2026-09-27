"""Fail-stop ordering for the RD-021 media deployment candidate."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class DeploymentStep(StrEnum):
    CURRENT_STATE_PREFLIGHT = "CURRENT_STATE_PREFLIGHT"
    R2_BINDING_READY = "R2_BINDING_READY"
    D1_MIGRATION = "D1_MIGRATION"
    D1_SCHEMA_READBACK = "D1_SCHEMA_READBACK"
    CANONICAL_XLSX_SCHEMA_MIGRATION = "CANONICAL_XLSX_SCHEMA_MIGRATION"
    XLSX_FRESH_READBACK = "XLSX_FRESH_READBACK"
    RUNTIME_BINDINGS = "RUNTIME_BINDINGS"
    STAGING_MEDIA_READBACK = "STAGING_MEDIA_READBACK"
    STAGING_CREATIVE_REF_READBACK = "STAGING_CREATIVE_REF_READBACK"
    MATCHING_END_TO_END = "MATCHING_END_TO_END"
    PRODUCTION_BEHAVIOR_OBSERVATION = "PRODUCTION_BEHAVIOR_OBSERVATION"


DEPLOYMENT_ORDER = tuple(DeploymentStep)


@dataclass(frozen=True)
class DeploymentProgress:
    completed: tuple[DeploymentStep, ...] = ()
    hold: str | None = None

    @property
    def next_step(self) -> DeploymentStep | None:
        if self.hold or len(self.completed) == len(DEPLOYMENT_ORDER):
            return None
        return DEPLOYMENT_ORDER[len(self.completed)]

    def record(self, step: DeploymentStep, *, passed: bool, receipt: str) -> DeploymentProgress:
        if self.hold or step is not self.next_step or not receipt.strip():
            raise ValueError("HOLD_DEPLOYMENT_SEQUENCE_CONFLICT")
        if not passed:
            return DeploymentProgress(self.completed, f"{step.value}:{receipt}")
        return DeploymentProgress((*self.completed, step))
