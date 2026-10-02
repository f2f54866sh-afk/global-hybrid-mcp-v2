from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

Disposition = Literal["PASS", "FAIL", "HOLD"]
WorkbenchDisposition = Literal[
    "NOT_REQUIRED",
    "NO_DELTA",
    "WRITE_AND_READBACK_PASS",
    "HOLD",
]

REQUIRED_PRODUCT_CHECKS: tuple[str, ...] = (
    "PRODUCTION_PRODUCT",
    "DETACHED_PRODUCT",
    "CONTEXT_ISOLATION",
    "DISPOSITION_INVARIANCE",
    "COPY_EGRESS",
    "PUBLIC_SERIALIZATION",
    "PUBLIC_ACCEPTANCE_WITNESS",
)


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


def sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def check_set_digest(check_ids: Iterable[str]) -> str:
    return sha256_json(sorted(check_ids))


class AuthoritativeSalesTaskSnapshotV1(BaseModel):
    task_id: str = Field(min_length=1)
    conversation_or_session_id: str = Field(min_length=1)
    current_user_request: str = Field(min_length=1)
    current_user_request_sha256: str = Field(min_length=64, max_length=64)
    task_class: str = Field(min_length=1)
    target_surface: str = Field(min_length=1)
    direct_user_hard_requirements: list[str] = Field(default_factory=list)
    hard_requirements_digest: str = Field(min_length=64, max_length=64)
    sales_execution_policy_ref: str = Field(min_length=1)
    global_authority_revision: str = Field(min_length=1)
    sales_authority_revision: str = Field(min_length=1)
    library_authority_revision: str = Field(min_length=1)
    real_car_authority_revision: str = Field(min_length=1)
    vehicle_instance_id: str | None = None
    workbench_file_id: str | None = None
    workbench_version: str | None = None
    workbench_sha256: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    evidence_set_digest: str = Field(min_length=64, max_length=64)
    generation: int = Field(ge=1)
    issued_at: datetime
    valid_until: datetime
    producer_id: str = Field(min_length=1)
    snapshot_digest: str = Field(min_length=64, max_length=64)

    @model_validator(mode="after")
    def validate_snapshot(self) -> AuthoritativeSalesTaskSnapshotV1:
        if self.issued_at.tzinfo is None or self.valid_until.tzinfo is None:
            raise ValueError("SNAPSHOT_TIMESTAMPS_MUST_BE_TIMEZONE_AWARE")
        if self.valid_until <= self.issued_at:
            raise ValueError("SNAPSHOT_VALIDITY_WINDOW_INVALID")
        if self.current_user_request_sha256 != sha256_text(self.current_user_request):
            raise ValueError("USER_REQUEST_DIGEST_MISMATCH")
        if self.hard_requirements_digest != sha256_json(self.direct_user_hard_requirements):
            raise ValueError("HARD_REQUIREMENTS_DIGEST_MISMATCH")
        if self.evidence_set_digest != sha256_json(self.evidence_refs):
            raise ValueError("EVIDENCE_SET_DIGEST_MISMATCH")
        if self.workbench_sha256 is not None and len(self.workbench_sha256) != 64:
            raise ValueError("WORKBENCH_SHA256_INVALID")
        return self

    def digest_payload(self) -> dict:
        return self.model_dump(mode="json", exclude={"snapshot_digest"})

    def recompute_digest(self) -> str:
        return sha256_json(self.digest_payload())


class ProductCheckResultV1(BaseModel):
    check_id: str = Field(min_length=1)
    disposition: Disposition
    result_ref: str = Field(min_length=1)
    snapshot_digest: str = Field(min_length=64, max_length=64)
    candidate_digest: str = Field(min_length=64, max_length=64)


class FinalConsumerDecisionV1(BaseModel):
    decision_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    snapshot_digest: str = Field(min_length=64, max_length=64)
    exact_candidate_digest: str = Field(min_length=64, max_length=64)
    required_check_set_digest: str = Field(min_length=64, max_length=64)
    result_refs: dict[str, str]
    per_check_dispositions: dict[str, Disposition]
    failed_check_ids: list[str]
    unresolved_check_ids: list[str]
    aggregate_product_disposition: Disposition
    decision_digest: str = Field(min_length=64, max_length=64)

    def digest_payload(self) -> dict:
        return self.model_dump(mode="json", exclude={"decision_digest"})

    def recompute_digest(self) -> str:
        return sha256_json(self.digest_payload())


class FinalOutputCommitReceiptV1(BaseModel):
    task_id: str
    snapshot_digest: str
    exact_candidate_digest: str | None
    decision_id: str | None
    decision_digest: str | None
    aggregate_product_disposition: Disposition
    workbench_terminal_disposition: WorkbenchDisposition
    final_output_commit: Disposition
    public_output_digest: str | None
    withhold_blocker: str | None
    runtime_commit: str
    policy_ref: str


class CommitOutcomeV1(BaseModel):
    public_output: str | None
    receipt: FinalOutputCommitReceiptV1


class FinalOutputCommitGateV1:
    def __init__(
        self,
        *,
        producer_id: str,
        policy_ref: str,
        runtime_commit: str,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.producer_id = producer_id
        self.policy_ref = policy_ref
        self.runtime_commit = runtime_commit
        self._now = now or (lambda: datetime.now(UTC))

    def verify_snapshot(self, snapshot: AuthoritativeSalesTaskSnapshotV1) -> str | None:
        if snapshot.producer_id != self.producer_id:
            return "SNAPSHOT_PRODUCER_MISMATCH"
        if snapshot.sales_execution_policy_ref != self.policy_ref:
            return "POLICY_REF_MISMATCH"
        if snapshot.recompute_digest() != snapshot.snapshot_digest:
            return "SNAPSHOT_DIGEST_MISMATCH"
        if snapshot.valid_until <= self._now():
            return "SNAPSHOT_STALE"
        return None

    def decide(
        self,
        *,
        snapshot: AuthoritativeSalesTaskSnapshotV1,
        candidate: str,
        results: list[ProductCheckResultV1],
    ) -> FinalConsumerDecisionV1:
        snapshot_blocker = self.verify_snapshot(snapshot)
        candidate_digest = sha256_text(candidate)
        result_map = {item.check_id: item for item in results}
        required = set(REQUIRED_PRODUCT_CHECKS)
        missing = sorted(required - set(result_map))
        duplicate_ids = sorted(
            {
                item.check_id
                for item in results
                if sum(row.check_id == item.check_id for row in results) > 1
            }
        )
        failed: list[str] = []
        unresolved: list[str] = []

        if snapshot_blocker is not None:
            unresolved.append(snapshot_blocker)
        unresolved.extend(f"{check_id}:DUPLICATE" for check_id in duplicate_ids)

        for check_id in sorted(required & set(result_map)):
            item = result_map[check_id]
            if item.snapshot_digest != snapshot.snapshot_digest:
                unresolved.append(f"{check_id}:SNAPSHOT_BINDING_MISMATCH")
            if item.candidate_digest != candidate_digest:
                unresolved.append(f"{check_id}:CANDIDATE_BINDING_MISMATCH")
            if not item.result_ref.strip():
                unresolved.append(f"{check_id}:RESULT_REF_MISSING")
            if item.disposition == "FAIL":
                failed.append(check_id)
            elif item.disposition == "HOLD":
                unresolved.append(check_id)

        unresolved.extend(f"{check_id}:MISSING" for check_id in missing)
        if failed:
            aggregate: Disposition = "FAIL"
        elif unresolved:
            aggregate = "HOLD"
        else:
            aggregate = "PASS"

        decision = FinalConsumerDecisionV1(
            decision_id=str(uuid4()),
            task_id=snapshot.task_id,
            snapshot_digest=snapshot.snapshot_digest,
            exact_candidate_digest=candidate_digest,
            required_check_set_digest=check_set_digest(REQUIRED_PRODUCT_CHECKS),
            result_refs={key: result_map[key].result_ref for key in sorted(result_map) if key in required},
            per_check_dispositions={
                key: result_map[key].disposition for key in sorted(result_map) if key in required
            },
            failed_check_ids=sorted(set(failed)),
            unresolved_check_ids=sorted(set(unresolved)),
            aggregate_product_disposition=aggregate,
            decision_digest="0" * 64,
        )
        return decision.model_copy(update={"decision_digest": sha256_json(decision.digest_payload())})

    def commit(
        self,
        *,
        snapshot: AuthoritativeSalesTaskSnapshotV1,
        candidate: str,
        decision: FinalConsumerDecisionV1,
        persistence_required: bool,
        workbench_terminal_disposition: WorkbenchDisposition = "NOT_REQUIRED",
    ) -> CommitOutcomeV1:
        candidate_digest = sha256_text(candidate)
        blocker = self.verify_snapshot(snapshot)
        if blocker is None and decision.recompute_digest() != decision.decision_digest:
            blocker = "DECISION_DIGEST_MISMATCH"
        if blocker is None and decision.task_id != snapshot.task_id:
            blocker = "DECISION_TASK_MISMATCH"
        if blocker is None and decision.snapshot_digest != snapshot.snapshot_digest:
            blocker = "DECISION_SNAPSHOT_MISMATCH"
        if blocker is None and decision.exact_candidate_digest != candidate_digest:
            blocker = "DECISION_CANDIDATE_MISMATCH"
        if (
            blocker is None
            and decision.required_check_set_digest != check_set_digest(REQUIRED_PRODUCT_CHECKS)
        ):
            blocker = "REQUIRED_CHECK_SET_MISMATCH"
        required = set(REQUIRED_PRODUCT_CHECKS)
        if blocker is None and set(decision.per_check_dispositions) != required:
            blocker = "DECISION_CHECK_SET_MISMATCH"
        if blocker is None and set(decision.result_refs) != required:
            blocker = "DECISION_RESULT_REF_SET_MISMATCH"
        if blocker is None and any(not value.strip() for value in decision.result_refs.values()):
            blocker = "DECISION_RESULT_REF_MISSING"
        if blocker is None:
            dispositions = decision.per_check_dispositions
            expected_aggregate: Disposition
            if any(value == "FAIL" for value in dispositions.values()):
                expected_aggregate = "FAIL"
            elif any(value == "HOLD" for value in dispositions.values()):
                expected_aggregate = "HOLD"
            else:
                expected_aggregate = "PASS"
            if decision.aggregate_product_disposition != expected_aggregate:
                blocker = "DECISION_AGGREGATE_MISMATCH"
        if blocker is None and decision.failed_check_ids != sorted(
            key for key, value in decision.per_check_dispositions.items() if value == "FAIL"
        ):
            blocker = "DECISION_FAILED_SET_MISMATCH"
        if blocker is None and decision.unresolved_check_ids:
            blocker = "DECISION_UNRESOLVED_SET_NONEMPTY"
        if blocker is None and decision.aggregate_product_disposition != "PASS":
            blocker = f"PRODUCT_{decision.aggregate_product_disposition}"
        if blocker is None and persistence_required and workbench_terminal_disposition not in {
            "NO_DELTA",
            "WRITE_AND_READBACK_PASS",
        }:
            blocker = "WORKBENCH_TERMINAL_HOLD"

        if blocker is not None:
            receipt = FinalOutputCommitReceiptV1(
                task_id=snapshot.task_id,
                snapshot_digest=snapshot.snapshot_digest,
                exact_candidate_digest=candidate_digest,
                decision_id=decision.decision_id,
                decision_digest=decision.decision_digest,
                aggregate_product_disposition=decision.aggregate_product_disposition,
                workbench_terminal_disposition=workbench_terminal_disposition,
                final_output_commit="HOLD" if decision.aggregate_product_disposition != "FAIL" else "FAIL",
                public_output_digest=None,
                withhold_blocker=blocker,
                runtime_commit=self.runtime_commit,
                policy_ref=self.policy_ref,
            )
            return CommitOutcomeV1(public_output=None, receipt=receipt)

        receipt = FinalOutputCommitReceiptV1(
            task_id=snapshot.task_id,
            snapshot_digest=snapshot.snapshot_digest,
            exact_candidate_digest=candidate_digest,
            decision_id=decision.decision_id,
            decision_digest=decision.decision_digest,
            aggregate_product_disposition="PASS",
            workbench_terminal_disposition=workbench_terminal_disposition,
            final_output_commit="PASS",
            public_output_digest=candidate_digest,
            withhold_blocker=None,
            runtime_commit=self.runtime_commit,
            policy_ref=self.policy_ref,
        )
        return CommitOutcomeV1(public_output=candidate, receipt=receipt)
