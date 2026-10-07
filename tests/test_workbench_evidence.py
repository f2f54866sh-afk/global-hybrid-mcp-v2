from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from global_hybrid_v2.adapters.workbench_evidence import (
    WorkbenchEvidenceMaterializerV1,
    WorkbenchPublicEvidenceFactV1,
    WorkbenchPublicFactPolicyV1,
    WorkbenchVehicleEvidenceProjectionV1,
)

FILE_ID = "1OfUZ_rh94sdXdTZMjMrKj8IjHgEBUFua"
SHA = "2444595f11c593bf38ea922852540540aafcbc2df99851ba975f142dfc2c2ca1"
MTIME = "2026-10-05T11:13:16.855Z"
X5M_VEH = "VIN:WBSGY01070LK10611"
TIGUAN_VEH = "VIN:WVGZZZ5NZMW539101"
PRICE_STATE = "CURRENT_PUBLIC_ASKING_PRICE_CORROBORATED / WORKBENCH+CURRENT_LISTING"


def x5m_projection(**kw):
    data = dict(
        source_file_id=FILE_ID,
        source_modified_time=MTIME,
        source_sha256=SHA,
        source_row=5,
        source_observation_id="SRC-ROW-5@20260925T0808Z",
        vehicle_instance_id=X5M_VEH,
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


def tiguan_projection(**kw):
    public_facts = [
        WorkbenchPublicEvidenceFactV1(
            fact_id="tiguan-mst-intake",
            source_field="改裝狀態:MST Performance 進氣",
            statement="MST Performance 進氣",
            public_safe_forms=["MST", "MST進氣", "MST Performance 進氣"],
            provenance="WORKBENCH",
        ),
        WorkbenchPublicEvidenceFactV1(
            fact_id="tiguan-bilstein-b8",
            source_field="改裝狀態:BILSTEIN B8",
            statement="BILSTEIN B8 前懸吊避震器/支柱",
            public_safe_forms=[
                "BILSTEIN B8",
                "BILSTEIN B8 避震",
                "BILSTEIN B8 前避震",
                "BILSTEIN B8 系列避震",
            ],
            provenance="DIRECT_USER",
        ),
        WorkbenchPublicEvidenceFactV1(
            fact_id="tiguan-panoramic-roof",
            source_field="實際配備狀態:全景天窗",
            statement="全景天窗",
            public_safe_forms=["全景天窗"],
        ),
        WorkbenchPublicEvidenceFactV1(
            fact_id="tiguan-digital-cockpit",
            source_field="實際配備狀態:Digital Cockpit數位儀表",
            statement="Digital Cockpit 數位儀表",
            public_safe_forms=["Digital Cockpit", "Digital Cockpit 數位儀表"],
        ),
        WorkbenchPublicEvidenceFactV1(
            fact_id="tiguan-driver-memory",
            source_field="實際配備狀態:駕駛座記憶按鍵",
            statement="駕駛座電動記憶",
            public_safe_forms=["駕駛座電動記憶"],
        ),
        WorkbenchPublicEvidenceFactV1(
            fact_id="tiguan-app-connect",
            source_field="實際配備狀態:App-Connect介面",
            statement="App-Connect",
            public_safe_forms=["App-Connect"],
        ),
        WorkbenchPublicEvidenceFactV1(
            fact_id="tiguan-r-steering",
            source_field="實際配備狀態:R方向盤",
            statement="R 方向盤",
            public_safe_forms=["R 方向盤"],
        ),
        WorkbenchPublicEvidenceFactV1(
            fact_id="tiguan-paddles",
            source_field="實際配備狀態:換檔撥片",
            statement="換檔撥片",
            public_safe_forms=["換檔撥片"],
        ),
        WorkbenchPublicEvidenceFactV1(
            fact_id="tiguan-quad-exhaust",
            source_field="實際配備狀態:四出尾管",
            statement="四出尾管",
            public_safe_forms=["四出尾管"],
        ),
    ]
    data = dict(
        source_file_id=FILE_ID,
        source_modified_time=MTIME,
        source_sha256=SHA,
        source_row=13,
        source_observation_id="SRC-ROW-13@20260925T0808Z",
        vehicle_instance_id=TIGUAN_VEH,
        instance_state="INSTANCE_ANCHORED_BINDING / PARTIAL_VERIFIED_VEHICLE_RECORD",
        company_source_state="CURRENT_MATCHED",
        company_source_row_current=13,
        model_year=2021,
        make="VW",
        model="TIGUAN R",
        color="藍",
        mileage_km=99764,
        asking_price_twd=None,
        asking_price_disclosure_state=None,
        public_evidence_facts=public_facts,
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


def snapshot(p, **kw):
    data = dict(
        task_id="task-n1c",
        evidence_set_digest="d" * 64,
        workbench_file_id=FILE_ID,
        workbench_version=MTIME,
        workbench_sha256=SHA,
        vehicle_instance_id=p.vehicle_instance_id,
        evidence_refs=[p.evidence_ref],
    )
    data.update(kw)
    return SimpleNamespace(**data)


def test_x5m_projection_materializes_closed_world_facts():
    p = x5m_projection()
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


def test_current_tiguan_projection_materializes_bound_modification_and_equipment_facts():
    p = tiguan_projection()
    manifest = WorkbenchEvidenceMaterializerV1(
        projection=p,
        policy=policy(),
    ).materialize(snapshot(p))
    facts = {fact.fact_id: fact for fact in manifest.facts}
    assert facts["workbench-model"].statement == "TIGUAN R"
    assert facts["workbench-mileage-km"].statement == "99764 km"
    assert "MST Performance 進氣" in facts["tiguan-mst-intake"].public_safe_forms
    assert "BILSTEIN B8 避震" in facts["tiguan-bilstein-b8"].public_safe_forms
    assert facts["tiguan-bilstein-b8"].provenance == "DIRECT_USER"
    assert facts["tiguan-app-connect"].statement == "App-Connect"
    assert "workbench-asking-price-twd" not in facts


def test_tiguan_unresolved_price_is_not_materialized():
    p = tiguan_projection()
    manifest = WorkbenchEvidenceMaterializerV1(
        projection=p,
        policy=policy(),
    ).materialize(snapshot(p))
    assert "workbench-asking-price-twd" not in {fact.fact_id for fact in manifest.facts}


def test_opaque_ref_alone_cannot_grant_authority():
    p = x5m_projection()
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
    p = tiguan_projection()
    s = snapshot(p, vehicle_instance_id="VIN:OTHER")
    with pytest.raises(ValueError, match="WORKBENCH_VEHICLE_BINDING_MISMATCH"):
        WorkbenchEvidenceMaterializerV1(projection=p, policy=policy()).materialize(s)


def test_stale_fingerprint_rejected():
    p = tiguan_projection()
    s = snapshot(p, workbench_sha256="0" * 64)
    with pytest.raises(ValueError, match="WORKBENCH_SHA256_BINDING_MISMATCH"):
        WorkbenchEvidenceMaterializerV1(projection=p, policy=policy()).materialize(s)


def test_stale_version_rejected():
    p = tiguan_projection()
    s = snapshot(p, workbench_version="2026-10-04T00:00:00Z")
    with pytest.raises(ValueError, match="WORKBENCH_VERSION_BINDING_MISMATCH"):
        WorkbenchEvidenceMaterializerV1(projection=p, policy=policy()).materialize(s)


def test_wrong_current_row_rejected():
    with pytest.raises(ValidationError, match="WORKBENCH_CURRENT_ROW_BINDING_MISMATCH"):
        tiguan_projection(company_source_row_current=12)


def test_noncurrent_company_source_rejected():
    with pytest.raises(ValidationError, match="WORKBENCH_COMPANY_SOURCE_NOT_CURRENT"):
        tiguan_projection(company_source_state="HISTORICAL_ONLY")


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
        tiguan_projection(instance_state=instance_state)


@pytest.mark.parametrize("source_field", ["成本_RAW", "同行_RAW", "cost_twd", "peer_price"])
def test_internal_or_peer_source_field_cannot_enter_public_fact_projection(source_field):
    with pytest.raises(ValidationError, match="WORKBENCH_PUBLIC_FACT_SENSITIVE_SOURCE_DENIED"):
        WorkbenchPublicEvidenceFactV1(
            fact_id="forbidden",
            source_field=source_field,
            statement="不應公開",
            public_safe_forms=["不應公開"],
        )


def test_duplicate_public_fact_id_rejected():
    fact = WorkbenchPublicEvidenceFactV1(
        fact_id="duplicate",
        source_field="實際配備狀態:A",
        statement="A",
        public_safe_forms=["A"],
    )
    with pytest.raises(ValidationError, match="WORKBENCH_DUPLICATE_PUBLIC_FACT_ID"):
        tiguan_projection(public_evidence_facts=[fact, fact])


def test_reserved_builtin_fact_id_rejected():
    with pytest.raises(ValidationError, match="WORKBENCH_PUBLIC_FACT_ID_RESERVED"):
        WorkbenchPublicEvidenceFactV1(
            fact_id="workbench-model",
            source_field="實際配備狀態:model",
            statement="TIGUAN R",
            public_safe_forms=["TIGUAN R"],
        )


def test_exact_evidence_ref_required_even_with_matching_metadata():
    p = tiguan_projection()
    s = snapshot(p, evidence_refs=["workbench:TIGUAN"])
    with pytest.raises(ValueError, match="WORKBENCH_EVIDENCE_REF_BINDING_MISMATCH"):
        WorkbenchEvidenceMaterializerV1(projection=p, policy=policy()).materialize(s)
