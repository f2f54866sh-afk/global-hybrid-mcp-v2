"""Pre-tool-selection governance for engineering mutation and convergence."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from importlib import resources
from typing import Protocol

from pydantic import BaseModel, Field

from global_hybrid_v2.runtime.state import (
    ProblemConvergenceState,
    RuntimeStateNotFound,
    RuntimeStateStore,
    WriterCapabilityRecord,
    WriterCapabilityState,
)


class EngineeringActor(StrEnum):
    AUTHORING_ENGINEERING = "AUTHORING_ENGINEERING"
    ENGINEER = "ENGINEER"


class EngineeringOperationFamily(StrEnum):
    REPOSITORY_READ = "REPOSITORY_READ"
    REPOSITORY_SEARCH = "REPOSITORY_SEARCH"
    DIFF_READBACK = "DIFF_READBACK"
    CI_READ = "CI_READ"
    REPOSITORY_MUTATION = "REPOSITORY_MUTATION"


class EngineeringRoute(StrEnum):
    ALLOW_READ = "ALLOW_READ"
    ALLOW_ENGINEER_WRITER = "ALLOW_ENGINEER_WRITER"
    ROUTE_TO_ENGINEER = "ROUTE_TO_ENGINEER"
    DENY = "DENY"
    FREEZE_MICROFIX_ROUTE = "FREEZE_MICROFIX_ROUTE"
    CONSOLIDATED_IMPLEMENTATION = "CONSOLIDATED_IMPLEMENTATION"
    CAPABILITY_DEBT = "CAPABILITY_DEBT"


MUTATION_OPERATIONS = {
    "create_blob",
    "update_file",
    "create_tree",
    "create_commit",
    "update_ref",
    "pr_mutation",
    "pr mutation",
    "pull_request_mutation",
    "pull request mutation",
    "legacy_mutation",
    "legacy path",
    "alternate_connector_mutation",
    "alternate connector path",
    "repository_mutation",
    "code_write",
    "file_write",
    "commit",
    "push",
    "commit_mutation",
    "ref_mutation",
}

READ_OPERATIONS = {
    "repository_read": EngineeringOperationFamily.REPOSITORY_READ,
    "repository_search": EngineeringOperationFamily.REPOSITORY_SEARCH,
    "diff_readback": EngineeringOperationFamily.DIFF_READBACK,
    "ci_read": EngineeringOperationFamily.CI_READ,
}

TRUSTED_WRITER_EVIDENCE_PRODUCERS = {
    "TOOL_BROKER",
    "ENGINEER_RUNTIME",
    "AUTH_LAYER",
}

HARD_DENY_MARKERS = (
    "403",
    "accessdenied",
    "resource not accessible by integration",
    "missing required repository write permission",
)

REQUIRED_DOWNGRADE_MATRIX = {
    "positive_current_path",
    "ordinary_path_regression",
    "omission_downgrade",
    "direct_authority_injection",
    "forged_stale_wrong_binding",
    "alternate_legacy_path",
    "missing_capability",
    "evidence_origin_mismatch",
    "restart_reopen",
    "external_side_effect_cardinality",
}


class EngineeringExecutionPolicy(BaseModel):
    revision: str = Field(min_length=1)
    invariants: list[str] = Field(min_length=1)
    trusted_writer_evidence_producers: list[str] = Field(min_length=1)
    required_downgrade_matrix: list[str] = Field(min_length=1)

    @classmethod
    def current(cls) -> EngineeringExecutionPolicy:
        raw = resources.files("global_hybrid_v2").joinpath(
            "data/engineering_execution_policy_current.json"
        ).read_text(encoding="utf-8")
        return cls.model_validate(json.loads(raw))


class EngineeringRouteDecision(BaseModel):
    route: EngineeringRoute
    operation_family: EngineeringOperationFamily
    status: str
    writer_tool_selection_count: int = 0
    writer_probe_count: int = 0
    repository_mutation_count: int = 0


class BoundaryMap(BaseModel):
    producer: str = Field(min_length=1)
    consumer: str = Field(min_length=1)
    enforcement_boundary: str = Field(min_length=1)
    evidence_producer: str = Field(min_length=1)
    side_effect_boundary: str = Field(min_length=1)
    protected_input_supported_by_port: bool


class EvidenceClaim(BaseModel):
    evidence_name: str = Field(min_length=1)
    supplied_by: str = Field(min_length=1)
    required_producer: str = Field(min_length=1)


class RepositoryMutationPort(Protocol):
    def mutate(self, *, operation: str, repository: str) -> object: ...


@dataclass(frozen=True)
class WriterAdmission:
    actor: EngineeringActor
    operation: str
    repository: str
    writer_surface: str
    auth_context_id: str
    capability_epoch: str


class EngineeringExecutionGovernor:
    """The only admission point before an engineering writer can be selected."""

    def __init__(self, store: RuntimeStateStore):
        self.store = store
        self.policy = EngineeringExecutionPolicy.current()

    @staticmethod
    def classify_operation(operation: str) -> EngineeringOperationFamily:
        normalized = operation.strip().lower()
        if normalized in MUTATION_OPERATIONS:
            return EngineeringOperationFamily.REPOSITORY_MUTATION
        try:
            return READ_OPERATIONS[normalized]
        except KeyError as exc:
            raise ValueError(f"unknown engineering operation: {operation}") from exc

    def attest_writer_capability(
        self, record: WriterCapabilityRecord
    ) -> WriterCapabilityRecord:
        if record.evidence_producer not in TRUSTED_WRITER_EVIDENCE_PRODUCERS:
            raise PermissionError("WRITER_ATTESTATION_PRODUCER_UNTRUSTED")
        if record.operation_family != EngineeringOperationFamily.REPOSITORY_MUTATION:
            raise ValueError("writer attestation must bind REPOSITORY_MUTATION")
        return self.store.record_writer_capability(record)

    def record_writer_failure(
        self,
        admission: WriterAdmission,
        *,
        error: str,
        evidence_producer: str,
        evidence_reference: str,
    ) -> WriterCapabilityRecord:
        if evidence_producer not in TRUSTED_WRITER_EVIDENCE_PRODUCERS:
            raise PermissionError("WRITER_ATTESTATION_PRODUCER_UNTRUSTED")
        normalized = error.lower()
        state = (
            WriterCapabilityState.HARD_DENY
            if any(marker in normalized for marker in HARD_DENY_MARKERS)
            else WriterCapabilityState.TRANSIENT_FAILURE
        )
        return self.store.record_writer_capability(
            WriterCapabilityRecord(
                actor=admission.actor,
                writer_surface=admission.writer_surface,
                repository=admission.repository,
                operation_family=EngineeringOperationFamily.REPOSITORY_MUTATION,
                auth_context_id=admission.auth_context_id,
                capability_epoch=admission.capability_epoch,
                state=state,
                evidence_producer=evidence_producer,
                evidence_reference=evidence_reference,
            )
        )

    def admit(self, admission: WriterAdmission) -> EngineeringRouteDecision:
        family = self.classify_operation(admission.operation)
        if family is not EngineeringOperationFamily.REPOSITORY_MUTATION:
            return EngineeringRouteDecision(
                route=EngineeringRoute.ALLOW_READ,
                operation_family=family,
                status="READ_ADMITTED",
            )
        if admission.actor is EngineeringActor.AUTHORING_ENGINEERING:
            return EngineeringRouteDecision(
                route=EngineeringRoute.ROUTE_TO_ENGINEER,
                operation_family=family,
                status="AUTHORING_ENGINEERING_NO_REPO_MUTATION",
            )
        try:
            capability = self.store.load_writer_capability(
                actor=admission.actor,
                writer_surface=admission.writer_surface,
                repository=admission.repository,
                operation_family=family,
                auth_context_id=admission.auth_context_id,
                capability_epoch=admission.capability_epoch,
            )
        except RuntimeStateNotFound:
            return EngineeringRouteDecision(
                route=EngineeringRoute.DENY,
                operation_family=family,
                status="UNKNOWN_WRITE_CAPABILITY_DENY",
            )
        if capability.state is not WriterCapabilityState.PROVEN:
            return EngineeringRouteDecision(
                route=EngineeringRoute.DENY,
                operation_family=family,
                status=(
                    "HARD_DENY_STICKY_UNTIL_CAPABILITY_EPOCH_CHANGE"
                    if capability.state is WriterCapabilityState.HARD_DENY
                    else "WRITER_CAPABILITY_NOT_PROVEN"
                ),
            )
        return EngineeringRouteDecision(
            route=EngineeringRoute.ALLOW_ENGINEER_WRITER,
            operation_family=family,
            status="EXACT_WRITER_ATTESTATION_PROVEN",
            writer_tool_selection_count=1,
        )

    def execute_repository_operation(
        self,
        admission: WriterAdmission,
        *,
        writer_selector: Callable[[], RepositoryMutationPort],
    ) -> EngineeringRouteDecision:
        decision = self.admit(admission)
        if decision.route is not EngineeringRoute.ALLOW_ENGINEER_WRITER:
            return decision
        writer = writer_selector()
        writer.mutate(operation=admission.operation, repository=admission.repository)
        return decision.model_copy(update={"repository_mutation_count": 1})

    def register_escape(
        self, problem_signature: str, *, alternate_path: bool = False
    ) -> ProblemConvergenceState:
        return self.store.record_problem_escape(
            problem_signature, alternate_path=alternate_path
        )

    def admit_primary_implementation(
        self,
        *,
        problem_signature: str,
        change_scope: str,
        boundary_map: BoundaryMap,
        downgrade_matrix: set[str],
        evidence_claims: list[EvidenceClaim],
        external_architecture_convergence: bool,
        material_gap_map_complete: bool,
        target_boundary_frozen: bool,
        test_now_complete: bool,
    ) -> EngineeringRouteDecision:
        try:
            state = self.store.load_problem_convergence(problem_signature)
        except RuntimeStateNotFound:
            state = self.store.record_problem_escape(problem_signature)
        if state.microfix_frozen and change_scope == "FIELD_LEVEL":
            return EngineeringRouteDecision(
                route=EngineeringRoute.FREEZE_MICROFIX_ROUTE,
                operation_family=EngineeringOperationFamily.REPOSITORY_MUTATION,
                status="FREEZE_MICROFIX_AFTER_REPEAT_ESCAPE",
            )
        if not all(
            (
                external_architecture_convergence,
                material_gap_map_complete,
                target_boundary_frozen,
                test_now_complete,
            )
        ):
            return EngineeringRouteDecision(
                route=EngineeringRoute.DENY,
                operation_family=EngineeringOperationFamily.REPOSITORY_MUTATION,
                status="PRIMARY_IMPLEMENTATION_NOT_ADMITTED",
            )
        if not boundary_map.protected_input_supported_by_port:
            return EngineeringRouteDecision(
                route=EngineeringRoute.CAPABILITY_DEBT,
                operation_family=EngineeringOperationFamily.REPOSITORY_MUTATION,
                status="PORT_CONTRACT_CAPABILITY_DEBT",
            )
        if any(
            claim.supplied_by != claim.required_producer for claim in evidence_claims
        ):
            return EngineeringRouteDecision(
                route=EngineeringRoute.DENY,
                operation_family=EngineeringOperationFamily.REPOSITORY_MUTATION,
                status="EVIDENCE_ORIGIN_MISMATCH",
            )
        if downgrade_matrix != REQUIRED_DOWNGRADE_MATRIX:
            return EngineeringRouteDecision(
                route=EngineeringRoute.DENY,
                operation_family=EngineeringOperationFamily.REPOSITORY_MUTATION,
                status="COMPLETE_MATRIX_BEFORE_PRIMARY_WRITE",
            )
        updated = state.model_copy(
            update={
                "boundary_map_complete": True,
                "downgrade_matrix_complete": True,
                "external_architecture_convergence": True,
                "material_gap_map_complete": True,
                "target_boundary_frozen": True,
                "test_now_complete": True,
            }
        )
        self.store.update_problem_convergence(updated)
        return EngineeringRouteDecision(
            route=EngineeringRoute.CONSOLIDATED_IMPLEMENTATION,
            operation_family=EngineeringOperationFamily.REPOSITORY_MUTATION,
            status="FULL_PROBLEM_CONVERGENCE_GUARD_PASS",
        )

    def record_consolidated_acceptance(
        self,
        problem_signature: str,
        *,
        focused_green: bool,
        full_green: bool,
        ci_green: bool,
        independent_readback: bool,
    ) -> str:
        state = self.store.load_problem_convergence(problem_signature)
        if not (
            state.boundary_map_complete
            and state.downgrade_matrix_complete
            and state.external_architecture_convergence
            and state.material_gap_map_complete
            and state.target_boundary_frozen
            and state.test_now_complete
            and focused_green
            and full_green
            and ci_green
            and independent_readback
        ):
            return "CONSOLIDATED_ACCEPTANCE_PENDING"
        if state.consolidated_acceptance_emitted:
            return "CONSOLIDATED_ACCEPTANCE_ALREADY_EMITTED"
        self.store.update_problem_convergence(
            state.model_copy(update={"consolidated_acceptance_emitted": True})
        )
        return "CANDIDATE_TESTED_READY"
