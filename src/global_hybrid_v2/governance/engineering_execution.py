"""Trusted pre-tool-selection governance for engineering execution."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from importlib import resources
from typing import Protocol
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import BaseModel, Field, model_validator

from global_hybrid_v2.runtime.state import (
    ProblemConvergenceState,
    RuntimeStateError,
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


class EvidenceProducerClass(StrEnum):
    SEARCH_EXECUTOR = "SEARCH_EXECUTOR"
    GOVERNANCE_ENGINE = "GOVERNANCE_ENGINE"
    TEST_MATRIX_COMPILER = "TEST_MATRIX_COMPILER"
    TOOL_BROKER = "TOOL_BROKER"
    AUTH_RUNTIME = "AUTH_RUNTIME"
    ENGINEER_RUNTIME = "ENGINEER_RUNTIME"
    EXECUTION_ADAPTER = "EXECUTION_ADAPTER"
    VERIFIER = "VERIFIER"


class EvidenceReceiptKind(StrEnum):
    ARCHITECTURE_RESEARCH = "ARCHITECTURE_RESEARCH"
    MATERIAL_GAP = "MATERIAL_GAP"
    BOUNDARY_FREEZE = "BOUNDARY_FREEZE"
    TEST_NOW = "TEST_NOW"
    WRITER_CAPABILITY = "WRITER_CAPABILITY"
    EVIDENCE_ORIGIN = "EVIDENCE_ORIGIN"


MUTATION_OPERATIONS = {
    "create_blob", "update_file", "create_tree", "create_commit", "update_ref",
    "pr_mutation", "pr mutation", "pull_request_mutation", "pull request mutation",
    "legacy_mutation", "legacy path", "alternate_connector_mutation",
    "alternate connector path", "repository_mutation", "code_write", "file_write",
    "commit", "push", "commit_mutation", "ref_mutation",
}
READ_OPERATIONS = {
    "repository_read": EngineeringOperationFamily.REPOSITORY_READ,
    "repository_search": EngineeringOperationFamily.REPOSITORY_SEARCH,
    "diff_readback": EngineeringOperationFamily.DIFF_READBACK,
    "ci_read": EngineeringOperationFamily.CI_READ,
}
REQUIRED_DOWNGRADE_MATRIX = {
    "positive_current_path", "ordinary_path_regression", "omission_downgrade",
    "direct_authority_injection", "forged_stale_wrong_binding",
    "alternate_legacy_path", "missing_capability", "evidence_origin_mismatch",
    "restart_reopen", "external_side_effect_cardinality",
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

    @property
    def digest(self) -> str:
        body = json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(body.encode()).hexdigest()


class TrustedReceipt(BaseModel):
    receipt_id: str = Field(min_length=1)
    receipt_kind: EvidenceReceiptKind
    producer_identity: str = Field(min_length=1)
    producer_class: EvidenceProducerClass
    problem_signature: str = Field(min_length=1)
    repository: str = Field(min_length=1)
    capability_epoch: str = Field(min_length=1)
    revision: int = Field(ge=1)
    evidence_reference: str = Field(min_length=1)
    issued_at: datetime
    integrity_signature: str = Field(pattern=r"^[0-9a-f]{128}$")


class ArchitectureResearchReceipt(TrustedReceipt):
    receipt_kind: EvidenceReceiptKind = EvidenceReceiptKind.ARCHITECTURE_RESEARCH
    authoritative_sources: list[str] = Field(min_length=3)
    convergence_state: str

    @model_validator(mode="after")
    def validate_research(self) -> ArchitectureResearchReceipt:
        if self.convergence_state != "PASS":
            raise ValueError("architecture research has not converged")
        if len(set(self.authoritative_sources)) < 3:
            raise ValueError("three independent authoritative sources are required")
        if any(not source.strip() for source in self.authoritative_sources):
            raise ValueError("authoritative source references cannot be blank")
        return self


class MaterialGapReceipt(TrustedReceipt):
    receipt_kind: EvidenceReceiptKind = EvidenceReceiptKind.MATERIAL_GAP
    material_gaps: list[str] = Field(min_length=1)


class BoundaryFreezeReceipt(TrustedReceipt):
    receipt_kind: EvidenceReceiptKind = EvidenceReceiptKind.BOUNDARY_FREEZE
    boundary_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class TestNowReceipt(TrustedReceipt):
    receipt_kind: EvidenceReceiptKind = EvidenceReceiptKind.TEST_NOW
    matrix_categories: list[str] = Field(min_length=1)


class WriterCapabilityAttestation(TrustedReceipt):
    receipt_kind: EvidenceReceiptKind = EvidenceReceiptKind.WRITER_CAPABILITY
    actor: EngineeringActor
    writer_surface: str = Field(min_length=1)
    auth_context_id: str = Field(min_length=1)
    operation_family: EngineeringOperationFamily
    capability_state: WriterCapabilityState


class EvidenceOriginReceipt(TrustedReceipt):
    receipt_kind: EvidenceReceiptKind = EvidenceReceiptKind.EVIDENCE_ORIGIN
    evidence_name: str = Field(min_length=1)
    execution_binding: str = Field(min_length=1)


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


class _ProducerEvidencePort:
    producer_class: EvidenceProducerClass

    def __init__(
        self,
        store: RuntimeStateStore,
        *,
        producer_identity: str,
        signing_key: Ed25519PrivateKey,
    ):
        if not producer_identity.strip():
            raise ValueError("producer identity cannot be blank")
        self.store = store
        self.producer_identity = producer_identity
        self.__signing_key = signing_key

    def _issue(
        self,
        kind: EvidenceReceiptKind,
        *,
        problem_signature: str,
        repository: str,
        capability_epoch: str,
        evidence_reference: str,
        details: dict[str, object],
        model: type[TrustedReceipt],
    ) -> TrustedReceipt:
        revision = self.store.next_engineering_evidence_revision(
            receipt_kind=kind.value,
            problem_signature=problem_signature,
            repository=repository,
            capability_epoch=capability_epoch,
        )
        payload: dict[str, object] = {
            "receipt_id": str(uuid4()),
            "receipt_kind": kind.value,
            "producer_identity": self.producer_identity,
            "producer_class": self.producer_class.value,
            "problem_signature": problem_signature,
            "repository": repository,
            "capability_epoch": capability_epoch,
            "revision": revision,
            "evidence_reference": evidence_reference,
            "issued_at": datetime.now(UTC).isoformat(),
            **details,
        }
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        payload["integrity_signature"] = self.__signing_key.sign(body).hex()
        persisted = self.store.persist_engineering_evidence_receipt(payload)
        return model.model_validate(persisted)


class ArchitectureResearchEvidencePort(_ProducerEvidencePort):
    producer_class = EvidenceProducerClass.SEARCH_EXECUTOR

    def issue_research(
        self,
        *,
        problem_signature: str,
        repository: str,
        capability_epoch: str,
        evidence_reference: str,
        authoritative_sources: list[str],
    ) -> ArchitectureResearchReceipt:
        return self._issue(
            EvidenceReceiptKind.ARCHITECTURE_RESEARCH,
            problem_signature=problem_signature,
            repository=repository,
            capability_epoch=capability_epoch,
            evidence_reference=evidence_reference,
            details={
                "authoritative_sources": authoritative_sources,
                "convergence_state": "PASS",
            },
            model=ArchitectureResearchReceipt,
        )


class GovernanceEvidencePort(_ProducerEvidencePort):
    producer_class = EvidenceProducerClass.GOVERNANCE_ENGINE

    def issue_material_gap(
        self, *, material_gaps: list[str], **binding: object
    ) -> MaterialGapReceipt:
        return self._issue(
            EvidenceReceiptKind.MATERIAL_GAP,
            details={"material_gaps": material_gaps},
            model=MaterialGapReceipt,
            **binding,
        )

    def issue_boundary_freeze(
        self, *, boundary_map: BoundaryMap, **binding: object
    ) -> BoundaryFreezeReceipt:
        return self._issue(
            EvidenceReceiptKind.BOUNDARY_FREEZE,
            details={"boundary_digest": boundary_map.digest},
            model=BoundaryFreezeReceipt,
            **binding,
        )


class TestMatrixEvidencePort(_ProducerEvidencePort):
    producer_class = EvidenceProducerClass.TEST_MATRIX_COMPILER

    def issue_test_now(
        self, *, matrix_categories: set[str], **binding: object
    ) -> TestNowReceipt:
        if matrix_categories != REQUIRED_DOWNGRADE_MATRIX:
            raise ValueError("COMPLETE_MATRIX_BEFORE_PRIMARY_WRITE")
        return self._issue(
            EvidenceReceiptKind.TEST_NOW,
            details={"matrix_categories": sorted(matrix_categories)},
            model=TestNowReceipt,
            **binding,
        )


class WriterCapabilityEvidencePort(_ProducerEvidencePort):
    def __init__(self, *args: object, producer_class: EvidenceProducerClass, **kwargs: object):
        if producer_class not in {
            EvidenceProducerClass.TOOL_BROKER,
            EvidenceProducerClass.AUTH_RUNTIME,
            EvidenceProducerClass.ENGINEER_RUNTIME,
        }:
            raise ValueError("writer capability port requires a writer producer")
        self.producer_class = producer_class
        super().__init__(*args, **kwargs)

    def issue_writer_capability(
        self,
        admission: WriterAdmission,
        *,
        evidence_reference: str,
        state: WriterCapabilityState = WriterCapabilityState.PROVEN,
    ) -> WriterCapabilityAttestation:
        return self._issue(
            EvidenceReceiptKind.WRITER_CAPABILITY,
            problem_signature=_writer_problem_signature(admission),
            repository=admission.repository,
            capability_epoch=admission.capability_epoch,
            evidence_reference=evidence_reference,
            details={
                "actor": admission.actor.value,
                "writer_surface": admission.writer_surface,
                "auth_context_id": admission.auth_context_id,
                "operation_family": EngineeringOperationFamily.REPOSITORY_MUTATION.value,
                "capability_state": state.value,
            },
            model=WriterCapabilityAttestation,
        )


class ExecutionEvidencePort(_ProducerEvidencePort):
    producer_class = EvidenceProducerClass.EXECUTION_ADAPTER

    def issue_execution_evidence(
        self, *, evidence_name: str, execution_binding: str, **binding: object
    ) -> EvidenceOriginReceipt:
        return self._issue(
            EvidenceReceiptKind.EVIDENCE_ORIGIN,
            details={
                "evidence_name": evidence_name,
                "execution_binding": execution_binding,
            },
            model=EvidenceOriginReceipt,
            **binding,
        )


class VerifierEvidencePort(ExecutionEvidencePort):
    producer_class = EvidenceProducerClass.VERIFIER


def _writer_problem_signature(admission: WriterAdmission) -> str:
    binding = "|".join((
        admission.actor.value, admission.repository, admission.writer_surface,
        admission.auth_context_id, admission.capability_epoch,
    ))
    return f"WRITER:{hashlib.sha256(binding.encode()).hexdigest()}"


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
        self, receipt_id: str, *, admission: WriterAdmission
    ) -> WriterCapabilityRecord:
        payload = self.store.consume_engineering_evidence_receipt(
            receipt_id, receipt_kind=EvidenceReceiptKind.WRITER_CAPABILITY.value,
            problem_signature=_writer_problem_signature(admission),
            repository=admission.repository, capability_epoch=admission.capability_epoch,
        )
        attestation = WriterCapabilityAttestation.model_validate(payload)
        if (
            attestation.actor is not admission.actor
            or attestation.writer_surface != admission.writer_surface
            or attestation.auth_context_id != admission.auth_context_id
            or attestation.operation_family is not EngineeringOperationFamily.REPOSITORY_MUTATION
        ):
            raise RuntimeStateError("WRITER_ATTESTATION_BINDING_MISMATCH")
        return self.store.record_writer_capability(WriterCapabilityRecord(
            actor=attestation.actor, writer_surface=attestation.writer_surface,
            repository=attestation.repository,
            operation_family=attestation.operation_family,
            auth_context_id=attestation.auth_context_id,
            capability_epoch=attestation.capability_epoch,
            state=attestation.capability_state,
            evidence_producer=attestation.producer_class,
            evidence_reference=attestation.receipt_id,
        ))

    def admit(self, admission: WriterAdmission) -> EngineeringRouteDecision:
        family = self.classify_operation(admission.operation)
        if family is not EngineeringOperationFamily.REPOSITORY_MUTATION:
            return EngineeringRouteDecision(
                route=EngineeringRoute.ALLOW_READ, operation_family=family,
                status="READ_ADMITTED",
            )
        if admission.actor is EngineeringActor.AUTHORING_ENGINEERING:
            return EngineeringRouteDecision(
                route=EngineeringRoute.ROUTE_TO_ENGINEER, operation_family=family,
                status="AUTHORING_ENGINEERING_NO_REPO_MUTATION",
            )
        try:
            capability = self.store.load_writer_capability(
                actor=admission.actor, writer_surface=admission.writer_surface,
                repository=admission.repository, operation_family=family,
                auth_context_id=admission.auth_context_id,
                capability_epoch=admission.capability_epoch,
            )
        except RuntimeStateNotFound:
            return EngineeringRouteDecision(
                route=EngineeringRoute.DENY, operation_family=family,
                status="UNKNOWN_WRITE_CAPABILITY_DENY",
            )
        if capability.state is not WriterCapabilityState.PROVEN:
            status = (
                "HARD_DENY_STICKY_UNTIL_CAPABILITY_EPOCH_CHANGE"
                if capability.state is WriterCapabilityState.HARD_DENY
                else "WRITER_CAPABILITY_NOT_PROVEN"
            )
            return EngineeringRouteDecision(
                route=EngineeringRoute.DENY, operation_family=family, status=status
            )
        return EngineeringRouteDecision(
            route=EngineeringRoute.ALLOW_ENGINEER_WRITER, operation_family=family,
            status="EXACT_WRITER_ATTESTATION_PROVEN", writer_tool_selection_count=1,
        )

    def execute_repository_operation(
        self, admission: WriterAdmission, *,
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

    def _consume_problem_receipt(
        self, receipt_id: str, *, kind: EvidenceReceiptKind,
        problem_signature: str, repository: str, capability_epoch: str,
    ) -> dict[str, object]:
        return self.store.consume_engineering_evidence_receipt(
            receipt_id, receipt_kind=kind.value, problem_signature=problem_signature,
            repository=repository, capability_epoch=capability_epoch,
        )

    def _register(
        self, receipt_id: str, *, kind: EvidenceReceiptKind,
        model: type[TrustedReceipt], required_producer: EvidenceProducerClass,
        updates: dict[str, object], **binding: str,
    ) -> ProblemConvergenceState:
        payload = self._consume_problem_receipt(receipt_id, kind=kind, **binding)
        receipt = model.model_validate(payload)
        if receipt.producer_class is not required_producer:
            raise RuntimeStateError("TRUSTED_EVIDENCE_PRODUCER_MISMATCH")
        state = self.store.load_problem_convergence(binding["problem_signature"])
        return self.store.update_problem_convergence(state.model_copy(update=updates))

    def register_architecture_research(
        self, receipt_id: str, **binding: str
    ) -> ProblemConvergenceState:
        return self._register(
            receipt_id, kind=EvidenceReceiptKind.ARCHITECTURE_RESEARCH,
            model=ArchitectureResearchReceipt,
            required_producer=EvidenceProducerClass.SEARCH_EXECUTOR,
            updates={"external_architecture_convergence": True}, **binding,
        )

    def register_material_gap(
        self, receipt_id: str, **binding: str
    ) -> ProblemConvergenceState:
        return self._register(
            receipt_id, kind=EvidenceReceiptKind.MATERIAL_GAP,
            model=MaterialGapReceipt,
            required_producer=EvidenceProducerClass.GOVERNANCE_ENGINE,
            updates={"material_gap_map_complete": True}, **binding,
        )

    def register_boundary_freeze(
        self, receipt_id: str, **binding: str
    ) -> ProblemConvergenceState:
        payload = self._consume_problem_receipt(
            receipt_id, kind=EvidenceReceiptKind.BOUNDARY_FREEZE, **binding
        )
        receipt = BoundaryFreezeReceipt.model_validate(payload)
        if receipt.producer_class is not EvidenceProducerClass.GOVERNANCE_ENGINE:
            raise RuntimeStateError("TRUSTED_EVIDENCE_PRODUCER_MISMATCH")
        state = self.store.load_problem_convergence(binding["problem_signature"])
        return self.store.update_problem_convergence(state.model_copy(update={
            "target_boundary_frozen": True, "boundary_map_complete": True,
            "boundary_digest": receipt.boundary_digest,
        }))

    def register_test_now(
        self, receipt_id: str, **binding: str
    ) -> ProblemConvergenceState:
        payload = self._consume_problem_receipt(
            receipt_id, kind=EvidenceReceiptKind.TEST_NOW, **binding
        )
        receipt = TestNowReceipt.model_validate(payload)
        if receipt.producer_class is not EvidenceProducerClass.TEST_MATRIX_COMPILER:
            raise RuntimeStateError("TRUSTED_EVIDENCE_PRODUCER_MISMATCH")
        if set(receipt.matrix_categories) != REQUIRED_DOWNGRADE_MATRIX:
            raise RuntimeStateError("COMPLETE_MATRIX_BEFORE_PRIMARY_WRITE")
        state = self.store.load_problem_convergence(binding["problem_signature"])
        return self.store.update_problem_convergence(state.model_copy(update={
            "test_now_complete": True, "downgrade_matrix_complete": True,
        }))

    def admit_primary_implementation(
        self, *, problem_signature: str, repository: str, capability_epoch: str,
        change_scope: str, boundary_map: BoundaryMap,
        downgrade_matrix: set[str], required_evidence_receipt_ids: list[str],
    ) -> EngineeringRouteDecision:
        try:
            state = self.store.load_problem_convergence(problem_signature)
        except RuntimeStateNotFound:
            return self._deny("PRIMARY_IMPLEMENTATION_NOT_ADMITTED")
        if state.microfix_frozen and change_scope == "FIELD_LEVEL":
            return EngineeringRouteDecision(
                route=EngineeringRoute.FREEZE_MICROFIX_ROUTE,
                operation_family=EngineeringOperationFamily.REPOSITORY_MUTATION,
                status="FREEZE_MICROFIX_AFTER_REPEAT_ESCAPE",
            )
        if not (
            state.external_architecture_convergence
            and state.material_gap_map_complete and state.target_boundary_frozen
            and state.test_now_complete and state.boundary_map_complete
            and state.downgrade_matrix_complete
        ):
            return self._deny("PRIMARY_IMPLEMENTATION_NOT_ADMITTED")
        if not boundary_map.protected_input_supported_by_port:
            return EngineeringRouteDecision(
                route=EngineeringRoute.CAPABILITY_DEBT,
                operation_family=EngineeringOperationFamily.REPOSITORY_MUTATION,
                status="PORT_CONTRACT_CAPABILITY_DEBT",
            )
        if boundary_map.digest != state.boundary_digest:
            return self._deny("BOUNDARY_FREEZE_BINDING_MISMATCH")
        if downgrade_matrix != REQUIRED_DOWNGRADE_MATRIX:
            return self._deny("COMPLETE_MATRIX_BEFORE_PRIMARY_WRITE")
        if not required_evidence_receipt_ids:
            return EngineeringRouteDecision(
                route=EngineeringRoute.CAPABILITY_DEBT,
                operation_family=EngineeringOperationFamily.REPOSITORY_MUTATION,
                status="MISSING_REQUIRED_EVIDENCE_PRODUCER",
            )
        try:
            for receipt_id in required_evidence_receipt_ids:
                payload = self._consume_problem_receipt(
                    receipt_id, kind=EvidenceReceiptKind.EVIDENCE_ORIGIN,
                    problem_signature=problem_signature, repository=repository,
                    capability_epoch=capability_epoch,
                )
                receipt = EvidenceOriginReceipt.model_validate(payload)
                if receipt.producer_class not in {
                    EvidenceProducerClass.EXECUTION_ADAPTER,
                    EvidenceProducerClass.VERIFIER,
                }:
                    raise RuntimeStateError("EVIDENCE_ORIGIN_MISMATCH")
        except RuntimeStateError:
            return self._deny("EVIDENCE_ORIGIN_MISMATCH")
        return EngineeringRouteDecision(
            route=EngineeringRoute.CONSOLIDATED_IMPLEMENTATION,
            operation_family=EngineeringOperationFamily.REPOSITORY_MUTATION,
            status="FULL_PROBLEM_CONVERGENCE_GUARD_PASS",
        )

    @staticmethod
    def _deny(status: str) -> EngineeringRouteDecision:
        return EngineeringRouteDecision(
            route=EngineeringRoute.DENY,
            operation_family=EngineeringOperationFamily.REPOSITORY_MUTATION,
            status=status,
        )

    def record_consolidated_acceptance(
        self, problem_signature: str, *, focused_green: bool, full_green: bool,
        ci_green: bool, independent_readback: bool,
    ) -> str:
        state = self.store.load_problem_convergence(problem_signature)
        if not (
            state.boundary_map_complete and state.downgrade_matrix_complete
            and state.external_architecture_convergence
            and state.material_gap_map_complete and state.target_boundary_frozen
            and state.test_now_complete and focused_green and full_green
            and ci_green and independent_readback
        ):
            return "CONSOLIDATED_ACCEPTANCE_PENDING"
        if state.consolidated_acceptance_emitted:
            return "CONSOLIDATED_ACCEPTANCE_ALREADY_EMITTED"
        self.store.update_problem_convergence(
            state.model_copy(update={"consolidated_acceptance_emitted": True})
        )
        return "CANDIDATE_TESTED_READY"
