from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from global_hybrid_v2.adapters.workbench_evidence import (
    WorkbenchEvidenceMaterializerV1,
    WorkbenchPublicFactPolicyV1,
    WorkbenchVehicleEvidenceProjectionV1,
)

FILE_ID = "1OfUZ_rh94sdXdTZMjMrKj8IjHgEBUFua"
SHA = "2444595f11c593bf38ea922852540540aafcbc2df99851ba975f142dfc2c2ca1"
MTIME = "2026-10-05T11:13:16.855Z"
VEH = "VIN:WBSGY01070LK10611"
PRICE_STATE = "CURRENT_PUBLIC_ASKING_PRICE_CORROBORATED / WORKBENCH+CURRENT_LISTING"


def projection(**kw):
    data = dict(
        source_file_id=FILE_ID,
        source_modified_time=MTIME,
        source_sha256=SHA,
        source_row=5,
        source_observation_id="SRC-ROW-5@20260925T0808Z",
        vehicle_instance_id=VEH,
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
    data.update(kw)
    return WorkbenchVehicleEvidenceProjectionV1(**data)


def policy(**kw):
    data = dict(
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
    data.update(kw)
    return WorkbenchPublicFactPolicyV1(**data)


def snapshot(p=None, **kw):
    p = p or projection()
    data = dict(
        task_id="task-n1c",
        evidence_set_digest="d" * 64,
        workbench_file_id=FILE_ID,
        workbench_version=MTIME,
        workbench_sha256=SHA,
        vehicle_instance_id=VEH,
        evidence_refs=[p.evidence_ref],
    )
    data.update(kw)
    return SimpleNamespace(**data)


def test_real_current_projection_materializes_closed_world_facts():
    p = projection()
    manifest = WorkbenchEvidenceMaterializerV1(
        projection=p,
        policy=policy(),
    ).materialize(snapshot(p))
    assert [fact.fact_id for fact in manifest.facts] == [
        "workbench-model-year",
        "workbench-make",
        "workbench-model",
        "workbench-color",
        "workbench-mileage-km",
        "workbench-asking-price-twd",
    ]
    assert manifest.facts[4].public_safe_forms[-1] == "里程166,812公里"
    assert "目前售價738,000元" in manifest.facts[5].public_safe_forms
    assert all(fact.provenance == "WORKBENCH" for fact in manifest.facts)


def test_opaque_ref_alone_cannot_grant_authority():
    p = projection()
    s = snapshot(
        p,
        workbench_file_id=None,
        workbench_version=None,
        workbench_sha256=None,
        evidence_refs=["workbench:X5M"],
    )
    with pytest.raises(ValueError, match="WORKBENCH_FILE_BINDING_MISMATCH"):
        WorkbenchEvidenceMaterializerV1(projection=p, policy=policy()).materialize(s)


def test_wrong_vehicle_binding_rejected():
    p = projection()
    s = snapshot(p, vehicle_instance_id="VIN:OTHER")
    with pytest.raises(ValueError, match="WORKBENCH_VEHICLE_BINDING_MISMATCH"):
        WorkbenchEvidenceMaterializerV1(projection=p, policy=policy()).materialize(s)


def test_stale_fingerprint_rejected():
    p = projection()
    s = snapshot(p, workbench_sha256="0" * 64)
    with pytest.raises(ValueError, match="WORKBENCH_SHA256_BINDING_MISMATCH"):
        WorkbenchEvidenceMaterializerV1(projection=p, policy=policy()).materialize(s)


def test_stale_version_rejected():
    p = projection()
    s = snapshot(p, workbench_version="2026-10-04T00:00:00Z")
    with pytest.raises(ValueError, match="WORKBENCH_VERSION_BINDING_MISMATCH"):
        WorkbenchEvidenceMaterializerV1(projection=p, policy=policy()).materialize(s)


def test_wrong_current_row_rejected():
    with pytest.raises(ValidationError, match="WORKBENCH_CURRENT_ROW_BINDING_MISMATCH"):
        projection(company_source_row_current=6)


def test_noncurrent_company_source_rejected():
    with pytest.raises(ValidationError, match="WORKBENCH_COMPANY_SOURCE_NOT_CURRENT"):
        projection(company_source_state="HISTORICAL_ONLY")


@pytest.mark.parametrize(
    "instance_state",
    [
        "ENTITY_MATCH_UNRESOLVED",
        "NOT_INSTANCE_ANCHORED_BINDING",
        "INSTANCE_ANCHORED_BINDING / ENTITY_MATCH_UNRESOLVED",
        "AMBIGUOUS_INSTANCE_ANCHORED_BINDING",
    ],
)
def test_nonadmitted_vehicle_instance_states_rejected(instance_state):
    with pytest.raises(ValidationError, match="WORKBENCH_VEHICLE_INSTANCE_NOT_ANCHORED"):
        projection(instance_state=instance_state)


def test_internal_cost_cannot_enter_projection_schema():
    data = projection().model_dump()
    data["cost_twd"] = 727000
    with pytest.raises(ValidationError, match="extra_forbidden"):
        WorkbenchVehicleEvidenceProjectionV1(**data)


def test_price_requires_application_owned_disclosure_policy():
    p = projection()
    pol = policy(allowed_price_disclosure_states=set())
    manifest = WorkbenchEvidenceMaterializerV1(
        projection=p,
        policy=pol,
    ).materialize(snapshot(p))
    assert "workbench-asking-price-twd" not in {fact.fact_id for fact in manifest.facts}


def test_exact_evidence_ref_required_even_with_matching_metadata():
    p = projection()
    s = snapshot(p, evidence_refs=["workbench:X5M"])
    with pytest.raises(ValueError, match="WORKBENCH_EVIDENCE_REF_BINDING_MISMATCH"):
        WorkbenchEvidenceMaterializerV1(projection=p, policy=policy()).materialize(s)
