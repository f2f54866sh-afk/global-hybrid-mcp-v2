from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import uuid4

from global_hybrid_v2.governance.sales_final_commit import (
    AuthoritativeSalesTaskSnapshotV1,
    CommitOutcomeV1,
    FinalOutputCommitGateV1,
    ProductCheckResultV1,
    WorkbenchDisposition,
    sha256_json,
    sha256_text,
)


class CandidateGenerator(Protocol):
    def generate(self, snapshot: AuthoritativeSalesTaskSnapshotV1) -> str: ...


class ProductEvaluator(Protocol):
    def evaluate(
        self,
        snapshot: AuthoritativeSalesTaskSnapshotV1,
        candidate: str,
    ) -> list[ProductCheckResultV1]: ...


class WorkbenchTerminalPort(Protocol):
    def terminal_disposition(self, snapshot: AuthoritativeSalesTaskSnapshotV1) -> WorkbenchDisposition: ...


class ControlledSalesServiceV1:
    """N1A service. It owns snapshot/decision/receipt construction; ports are injected."""

    def __init__(
        self,
        *,
        candidate_generator: CandidateGenerator,
        product_evaluator: ProductEvaluator,
        commit_gate: FinalOutputCommitGateV1,
        producer_id: str,
        policy_ref: str,
        global_authority_revision: str,
        sales_authority_revision: str,
        library_authority_revision: str,
        real_car_authority_revision: str,
        workbench_terminal_port: WorkbenchTerminalPort | None = None,
        now: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.candidate_generator = candidate_generator
        self.product_evaluator = product_evaluator
        self.commit_gate = commit_gate
        self.producer_id = producer_id
        self.policy_ref = policy_ref
        self.global_authority_revision = global_authority_revision
        self.sales_authority_revision = sales_authority_revision
        self.library_authority_revision = library_authority_revision
        self.real_car_authority_revision = real_car_authority_revision
        self.workbench_terminal_port = workbench_terminal_port
        self._now = now or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda: str(uuid4()))

    def handle(
        self,
        *,
        current_user_request: str,
        conversation_or_session_id: str,
        task_class: str,
        target_surface: str,
        direct_user_hard_requirements: list[str] | None = None,
        vehicle_instance_id: str | None = None,
        workbench_file_id: str | None = None,
        workbench_version: str | None = None,
        workbench_sha256: str | None = None,
        evidence_refs: list[str] | None = None,
        persistence_required: bool = False,
    ) -> CommitOutcomeV1:
        issued_at = self._now()
        requirements = list(direct_user_hard_requirements or [])
        evidence = list(evidence_refs or [])
        snapshot = AuthoritativeSalesTaskSnapshotV1(
            task_id=self._id_factory(),
            conversation_or_session_id=conversation_or_session_id,
            current_user_request=current_user_request,
            current_user_request_sha256=sha256_text(current_user_request),
            task_class=task_class,
            target_surface=target_surface,
            direct_user_hard_requirements=requirements,
            hard_requirements_digest=sha256_json(requirements),
            sales_execution_policy_ref=self.policy_ref,
            global_authority_revision=self.global_authority_revision,
            sales_authority_revision=self.sales_authority_revision,
            library_authority_revision=self.library_authority_revision,
            real_car_authority_revision=self.real_car_authority_revision,
            vehicle_instance_id=vehicle_instance_id,
            workbench_file_id=workbench_file_id,
            workbench_version=workbench_version,
            workbench_sha256=workbench_sha256,
            evidence_refs=evidence,
            evidence_set_digest=sha256_json(evidence),
            generation=1,
            issued_at=issued_at,
            valid_until=issued_at + timedelta(minutes=5),
            producer_id=self.producer_id,
            snapshot_digest="0" * 64,
        )
        snapshot = snapshot.model_copy(update={"snapshot_digest": sha256_json(snapshot.digest_payload())})

        candidate = self.candidate_generator.generate(snapshot)
        results = self.product_evaluator.evaluate(snapshot, candidate)
        decision = self.commit_gate.decide(snapshot=snapshot, candidate=candidate, results=results)

        workbench_state: WorkbenchDisposition = "NOT_REQUIRED"
        if persistence_required:
            workbench_state = (
                "HOLD"
                if self.workbench_terminal_port is None
                else self.workbench_terminal_port.terminal_disposition(snapshot)
            )

        return self.commit_gate.commit(
            snapshot=snapshot,
            candidate=candidate,
            decision=decision,
            persistence_required=persistence_required,
            workbench_terminal_disposition=workbench_state,
        )
