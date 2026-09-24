from __future__ import annotations

from dataclasses import dataclass

from global_hybrid_v2.contracts import VehicleConfigurationQuery


@dataclass(frozen=True)
class TrustedTaskSemantics:
    task_kind: str
    vehicle_query: VehicleConfigurationQuery | None = None
    requires_visual_observation: bool = False


@dataclass(frozen=True)
class TaskEvidencePlan:
    required_projections: tuple[str, ...]
    vehicle_query: VehicleConfigurationQuery | None


class TaskEvidencePlanner:
    VEHICLE_KINDS = frozenset({"VEHICLE_MODIFICATION", "OEM_VS_OBSERVED"})

    def plan(self, semantics: TrustedTaskSemantics) -> TaskEvidencePlan:
        if semantics.task_kind in self.VEHICLE_KINDS:
            if semantics.vehicle_query is None:
                raise ValueError("TRUSTED_VEHICLE_QUERY_REQUIRED")
            projections = ["vehicle_configuration_reference"]
            if semantics.requires_visual_observation:
                projections.append("visual_vehicle_observation")
            return TaskEvidencePlan(tuple(projections), semantics.vehicle_query)
        return TaskEvidencePlan((), None)
