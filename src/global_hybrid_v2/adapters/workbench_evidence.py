from __future__ import annotations

import re
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from global_hybrid_v2.governance.public_claim_coverage import (
    EvidenceProvenance,
    TaskBoundEvidenceFactV1,
    TaskBoundEvidenceManifestV1,
)

if TYPE_CHECKING:
    from global_hybrid_v2.governance.sales_final_commit import AuthoritativeSalesTaskSnapshotV1

WorkbenchPublicFactField = Literal[
    "model_year",
    "make",
    "model",
    "color",
    "mileage_km",
    "asking_price_twd",
]

CURRENT_ANCHORED_INSTANCE_STATES = frozenset(
    {"INSTANCE_ANCHORED_BINDING / PARTIAL_VERIFIED_VEHICLE_RECORD"}
)
_BUILTIN_FACT_IDS = frozenset(
    {
        "workbench-model-year",
        "workbench-make",
        "workbench-model",
        "workbench-color",
        "workbench-mileage-km",
        "workbench-asking-price-twd",
    }
)
_SENSITIVE_SOURCE_TOKENS = ("成本", "同行", "cost", "peer")


class WorkbenchPublicEvidenceFactV1(BaseModel):
    fact_id: str = Field(min_length=1)
    source_field: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    public_safe_forms: list[str] = Field(min_length=1)
    provenance: EvidenceProvenance = "WORKBENCH"
    semantic_scope: str = Field(default="CURRENT_TASK", min_length=1)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_fact(self) -> WorkbenchPublicEvidenceFactV1:
        if self.fact_id in _BUILTIN_FACT_IDS:
            raise ValueError("WORKBENCH_PUBLIC_FACT_ID_RESERVED")
        folded = self.source_field.casefold()
        if any(token in folded for token in _SENSITIVE_SOURCE_TOKENS):
            raise ValueError("WORKBENCH_PUBLIC_FACT_SENSITIVE_SOURCE_DENIED")
        if any(not item.strip() for item in self.public_safe_forms):
            raise ValueError("WORKBENCH_PUBLIC_SAFE_FORM_EMPTY")
        return self


class WorkbenchVehicleEvidenceProjectionV1(BaseModel):
    source_file_id: str = Field(min_length=1)
    source_modified_time: str = Field(min_length=1)
    source_sha256: str = Field(min_length=64, max_length=64)
    source_sheet: Literal["AI工作主表"] = "AI工作主表"
    source_row: int = Field(ge=2)
    source_observation_id: str = Field(min_length=1)
    vehicle_instance_id: str = Field(min_length=1)
    instance_state: str = Field(min_length=1)
    company_source_state: str = Field(min_length=1)
    company_source_row_current: int = Field(ge=2)
    model_year: int = Field(ge=1886, le=2100)
    make: str = Field(min_length=1)
    model: str = Field(min_length=1)
    color: str = Field(min_length=1)
    mileage_km: int = Field(ge=0)
    asking_price_twd: int | None = Field(default=None, gt=0)
    asking_price_disclosure_state: str | None = None
    public_evidence_facts: list[WorkbenchPublicEvidenceFactV1] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @field_validator("source_sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        if re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError("WORKBENCH_SHA256_INVALID")
        return value

    @model_validator(mode="after")
    def validate_current_binding(self) -> WorkbenchVehicleEvidenceProjectionV1:
        if self.company_source_state != "CURRENT_MATCHED":
            raise ValueError("WORKBENCH_COMPANY_SOURCE_NOT_CURRENT")
        if self.company_source_row_current != self.source_row:
            raise ValueError("WORKBENCH_CURRENT_ROW_BINDING_MISMATCH")
        if self.instance_state not in CURRENT_ANCHORED_INSTANCE_STATES:
            raise ValueError("WORKBENCH_VEHICLE_INSTANCE_NOT_ANCHORED")
        fact_ids = [item.fact_id for item in self.public_evidence_facts]
        if len(fact_ids) != len(set(fact_ids)):
            raise ValueError("WORKBENCH_DUPLICATE_PUBLIC_FACT_ID")
        return self

    @property
    def evidence_ref(self) -> str:
        return (
            f"workbench:{self.source_file_id}:sha256:{self.source_sha256}:"
            f"sheet:{self.source_sheet}:row:{self.source_row}:vehicle:{self.vehicle_instance_id}"
        )


class WorkbenchPublicFactPolicyV1(BaseModel):
    public_fields: set[WorkbenchPublicFactField] = Field(min_length=1)
    allowed_price_disclosure_states: set[str] = Field(default_factory=set)

    model_config = ConfigDict(extra="forbid")


class WorkbenchEvidenceMaterializerV1:
    """Materialize closed-world public facts from one bound workbench projection."""

    def __init__(
        self,
        *,
        projection: WorkbenchVehicleEvidenceProjectionV1,
        policy: WorkbenchPublicFactPolicyV1,
        producer_id: str = "workbench-evidence-materializer-v1",
    ) -> None:
        self.projection = projection
        self.policy = policy
        self.producer_id = producer_id

    def materialize(
        self,
        snapshot: AuthoritativeSalesTaskSnapshotV1,
    ) -> TaskBoundEvidenceManifestV1:
        self._validate_snapshot_binding(snapshot)
        facts = self._facts()
        return TaskBoundEvidenceManifestV1.build(
            task_id=snapshot.task_id,
            evidence_set_digest=snapshot.evidence_set_digest,
            producer_id=self.producer_id,
            facts=facts,
        )

    def _validate_snapshot_binding(self, snapshot: AuthoritativeSalesTaskSnapshotV1) -> None:
        expected = self.projection
        checks = (
            (snapshot.workbench_file_id, expected.source_file_id, "WORKBENCH_FILE_BINDING_MISMATCH"),
            (snapshot.workbench_version, expected.source_modified_time, "WORKBENCH_VERSION_BINDING_MISMATCH"),
            (snapshot.workbench_sha256, expected.source_sha256, "WORKBENCH_SHA256_BINDING_MISMATCH"),
            (
                snapshot.vehicle_instance_id,
                expected.vehicle_instance_id,
                "WORKBENCH_VEHICLE_BINDING_MISMATCH",
            ),
        )
        for actual, wanted, reason in checks:
            if actual != wanted:
                raise ValueError(reason)
        if expected.evidence_ref not in snapshot.evidence_refs:
            raise ValueError("WORKBENCH_EVIDENCE_REF_BINDING_MISMATCH")

    def _authority_ref(self, source_field: str) -> str:
        return f"{self.projection.evidence_ref}:field:{source_field}"

    def _fact(
        self,
        *,
        fact_id: str,
        source_field: str,
        statement: str,
        public_safe_forms: list[str],
        provenance: EvidenceProvenance = "WORKBENCH",
        semantic_scope: str = "CURRENT_TASK",
    ) -> TaskBoundEvidenceFactV1:
        return TaskBoundEvidenceFactV1(
            fact_id=fact_id,
            authority_ref=self._authority_ref(source_field),
            statement=statement,
            public_safe_forms=public_safe_forms,
            provenance=provenance,
            semantic_scope=semantic_scope,
        )

    def _facts(self) -> list[TaskBoundEvidenceFactV1]:
        p = self.projection
        fields = self.policy.public_fields
        facts: list[TaskBoundEvidenceFactV1] = []
        if "model_year" in fields:
            facts.append(
                self._fact(
                    fact_id="workbench-model-year",
                    source_field="年分_RAW",
                    statement=str(p.model_year),
                    public_safe_forms=[str(p.model_year), f"{p.model_year}年"],
                )
            )
        if "make" in fields:
            facts.append(
                self._fact(
                    fact_id="workbench-make",
                    source_field="品牌_RAW",
                    statement=p.make,
                    public_safe_forms=[p.make],
                )
            )
        if "model" in fields:
            facts.append(
                self._fact(
                    fact_id="workbench-model",
                    source_field="車型_RAW",
                    statement=p.model,
                    public_safe_forms=[p.model],
                )
            )
        if "color" in fields:
            forms = [p.color]
            if not p.color.endswith("色"):
                forms.append(f"{p.color}色")
            facts.append(
                self._fact(
                    fact_id="workbench-color",
                    source_field="顏色_RAW",
                    statement=p.color,
                    public_safe_forms=forms,
                )
            )
        if "mileage_km" in fields:
            plain = str(p.mileage_km)
            grouped = f"{p.mileage_km:,}"
            facts.append(
                self._fact(
                    fact_id="workbench-mileage-km",
                    source_field="里程_Canonical",
                    statement=f"{plain} km",
                    public_safe_forms=[
                        f"{plain}公里",
                        f"{grouped}公里",
                        f"里程{plain}公里",
                        f"里程{grouped}公里",
                    ],
                )
            )
        if (
            "asking_price_twd" in fields
            and p.asking_price_twd is not None
            and p.asking_price_disclosure_state in self.policy.allowed_price_disclosure_states
        ):
            plain = str(p.asking_price_twd)
            grouped = f"{p.asking_price_twd:,}"
            facts.append(
                self._fact(
                    fact_id="workbench-asking-price-twd",
                    source_field="開價_Canonical",
                    statement=f"{plain} TWD",
                    public_safe_forms=[
                        f"{plain}元",
                        f"{grouped}元",
                        f"售價{plain}元",
                        f"售價{grouped}元",
                        f"目前售價{plain}元",
                        f"目前售價{grouped}元",
                        f"NT${grouped}",
                    ],
                )
            )
        for item in p.public_evidence_facts:
            facts.append(
                self._fact(
                    fact_id=item.fact_id,
                    source_field=item.source_field,
                    statement=item.statement,
                    public_safe_forms=item.public_safe_forms,
                    provenance=item.provenance,
                    semantic_scope=item.semantic_scope,
                )
            )
        return facts
