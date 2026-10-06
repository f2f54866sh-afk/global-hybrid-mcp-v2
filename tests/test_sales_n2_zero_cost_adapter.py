from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from global_hybrid_v2.adapters.workbench_evidence import (
    WorkbenchEvidenceMaterializerV1,
    WorkbenchPublicFactPolicyV1,
    WorkbenchVehicleEvidenceProjectionV1,
)
from global_hybrid_v2.adapters.zero_cost_sales import (
    ZeroCostBoundedSalesCandidateGeneratorV1,
    ZeroCostBoundedSalesProductEvaluatorV1,
)
from global_hybrid_v2.governance.sales_final_commit import (
    FinalOutputCommitGateV1,
    sha256_text,
)
from global_hybrid_v2.sales_controlled_service import ControlledSalesServiceV1

NOW = datetime(2026, 10, 6, 19, 30, tzinfo=UTC)
POLICY_REF = "N2_ZERO_COST_BOUNDED_SHADOW_V1"
PRODUCER = "controlled-sales-app-v1"
RUNTIME = "ab49442e4e30458214224a15a7afe9d89d13901c"

FILE_ID = "1OfUZ_rh94sdXdTZMjMrKj8IjHgEBUFua"
SHA = "2444595f11c593bf38ea922852540540aafcbc2df99851ba975f142dfc2c2ca1"
MTIME = "2026-10-05T11:13:16.855Z"
VEHICLE = "VIN:WBSGY01070LK10611"
PRICE_STATE = "CURRENT_PUBLIC_ASKING_PRICE_CORROBORATED / WORKBENCH+CURRENT_LISTING"

ORDINARY_CASES = (
    (
        "幫我整理一段這台 BMW X5M 的 8891 刊登介紹，簡潔清楚即可。",
        "2009年 BMW X5M，藍色，里程166,812公里，目前售價738,000元。",
    ),
    (
        "這台 X5M 的里程跟售價幫我寫成一小段介紹。",
        "BMW X5M，里程166,812公里，目前售價738,000元。",
    ),
    (
        "幫我寫一段這台藍色 X5M 的簡短車況介紹。",
        "藍色 BMW X5M，2009年，里程166,812公里。",
    ),
)


class FixedCandidateGenerator:
    def __init__(self, candidate: str) -> None:
        self.candidate = candidate

    def generate(self, snapshot) -> str:
        del snapshot
        return self.candidate


def projection() -> WorkbenchVehicleEvidenceProjectionV1:
    return WorkbenchVehicleEvidenceProjectionV1(
        source_file_id=FILE_ID,
        source_modified_time=MTIME,
        source_sha256=SHA,
        source_row=5,
        source_observation_id="SRC-ROW-5@20260925T0808Z",
        vehicle_instance_id=VEHICLE,
        instance_state="INSTANCE_ANCHORED_BINDING / PARTIAL_VERIFIED_VEHICLE_RECORD",
        company_source_state="CURRENT_MATCHED",
        company_source_row_current=5,
        model_year=2009,
        make="BMW",
        model="X5M",
        color="藍",
        mileage_km=166812,
        asking_price_twd=738000,
        asking_price_disclosure_state=PRICE_STATE,
    )


def policy() -> WorkbenchPublicFactPolicyV1:
    return WorkbenchPublicFactPolicyV1(
        public_fields={
            "model_year",
            "make",
            "model",
            "color",
            "mileage_km",
            "asking_price_twd",
        },
        allowed_price_disclosure_states={PRICE_STATE},
    )


def build_service(*, generator=None) -> ControlledSalesServiceV1:
    p = projection()
    return ControlledSalesServiceV1(
        candidate_generator=generator or ZeroCostBoundedSalesCandidateGeneratorV1(),
        product_evaluator=ZeroCostBoundedSalesProductEvaluatorV1(),
        commit_gate=FinalOutputCommitGateV1(
            producer_id=PRODUCER,
            policy_ref=POLICY_REF,
            runtime_commit=RUNTIME,
            now=lambda: NOW,
        ),
        producer_id=PRODUCER,
        policy_ref=POLICY_REF,
        global_authority_revision="GLOBAL-current",
        sales_authority_revision="SALES-current",
        library_authority_revision="LIBRARY-current",
        real_car_authority_revision="REAL_CAR-current",
        evidence_materializer=WorkbenchEvidenceMaterializerV1(
            projection=p,
            policy=policy(),
        ),
        now=lambda: NOW,
    )


def run(
    user_prompt: str,
    *,
    generator=None,
    workbench_sha256: str = SHA,
):
    p = projection()
    return build_service(generator=generator).handle(
        current_user_request=user_prompt,
        conversation_or_session_id="n2-zero-cost-repo-shadow",
        task_class="8891_COPY",
        target_surface="8891",
        direct_user_hard_requirements=[],
        vehicle_instance_id=VEHICLE,
        workbench_file_id=FILE_ID,
        workbench_version=MTIME,
        workbench_sha256=workbench_sha256,
        evidence_refs=[p.evidence_ref],
        persistence_required=False,
    )


@pytest.mark.parametrize(("user_prompt", "expected"), ORDINARY_CASES)
def test_repo_bound_zero_cost_ordinary_task_acceptance(user_prompt, expected):
    outcome = run(user_prompt)

    assert outcome.public_output == expected
    receipt = outcome.receipt
    assert receipt.aggregate_product_disposition == "PASS"
    assert receipt.final_output_commit == "PASS"
    assert receipt.withhold_blocker is None
    assert receipt.exact_candidate_digest == sha256_text(expected)
    assert receipt.public_output_digest == sha256_text(expected)
    assert receipt.runtime_commit == RUNTIME
    assert receipt.policy_ref == POLICY_REF
    UUID(receipt.task_id)
    assert receipt.decision_id is not None
    UUID(receipt.decision_id)
    assert receipt.decision_digest is not None
    assert len(receipt.snapshot_digest) == 64


def test_known_unsupported_candidate_is_failed_and_withheld():
    candidate = "BMW X5M 555hp xDrive V8 twin turbo"
    outcome = run(
        "幫我整理一段這台 BMW X5M 的 8891 刊登介紹，簡潔清楚即可。",
        generator=FixedCandidateGenerator(candidate),
    )

    assert outcome.public_output is None
    assert outcome.receipt.aggregate_product_disposition == "FAIL"
    assert outcome.receipt.final_output_commit == "FAIL"
    assert outcome.receipt.public_output_digest is None
    assert outcome.receipt.withhold_blocker == "PRODUCT_FAIL"


def test_stale_workbench_binding_holds_and_withholds():
    outcome = run(
        "幫我整理一段這台 BMW X5M 的 8891 刊登介紹，簡潔清楚即可。",
        workbench_sha256="0" * 64,
    )

    assert outcome.public_output is None
    assert outcome.receipt.aggregate_product_disposition == "HOLD"
    assert outcome.receipt.final_output_commit == "HOLD"
    assert outcome.receipt.public_output_digest is None
    assert outcome.receipt.withhold_blocker == "DECISION_UNRESOLVED_SET_NONEMPTY"


def test_unsupported_task_shape_holds_and_withholds():
    outcome = run("請寫一篇完整故事型長文，加入改裝性能與駕駛感受。")

    assert outcome.public_output is None
    assert outcome.receipt.aggregate_product_disposition == "HOLD"
    assert outcome.receipt.final_output_commit == "HOLD"
    assert outcome.receipt.public_output_digest is None


def test_native_mcp_adapter_remains_unwired_from_zero_cost_shadow_path():
    source = Path("src/global_hybrid_v2/adapters/mcp_server.py").read_text(encoding="utf-8")
    assert "ZeroCostBoundedSalesCandidateGeneratorV1" not in source
    assert "ZeroCostBoundedSalesProductEvaluatorV1" not in source
