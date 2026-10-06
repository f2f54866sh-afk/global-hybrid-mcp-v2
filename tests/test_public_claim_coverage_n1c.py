from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from pydantic import SecretStr, ValidationError

from global_hybrid_v2.adapters.openai_sales import OpenAISalesProductEvaluator
from global_hybrid_v2.governance.public_claim_coverage import (
    ClaimCoveragePayloadV1,
    ClaimCoverageSegmentV1,
    TaskBoundEvidenceFactV1,
    TaskBoundEvidenceManifestV1,
    evaluate_claim_coverage,
)
from global_hybrid_v2.governance.sales_final_commit import (
    REQUIRED_PRODUCT_CHECKS,
    AuthoritativeSalesTaskSnapshotV1,
    FinalOutputCommitGateV1,
    ProductCheckResultV1,
    sha256_json,
    sha256_text,
)
from global_hybrid_v2.sales_controlled_service import ControlledSalesServiceV1

NOW = datetime(2026, 10, 6, 9, 0, tzinfo=UTC)
PRODUCER = "controlled-sales-app-v1"
POLICY = "SALES_VISUAL_EXECUTION_PROFILE_20261006_V109_USER_VISIBLE_EGRESS_FORMAT_CONSUMPTION_GUARD"


def facts(*, include_555: bool = False):
    safe_forms = {
        "fact-model": ["BMW X5 M", "X5 M"],
        "fact-year": ["2009", "2009年"],
        "fact-mileage": ["166,812 km", "里程166,812公里"],
        "fact-price": ["NT$738,000", "目前售價73.8萬"],
    }
    rows = [
        ("fact-model", "BMW X5 M"),
        ("fact-year", "2009"),
        ("fact-color", "藍色"),
        ("fact-mileage", "166,812 km"),
        ("fact-price", "NT$738,000"),
        ("fact-displacement", "4395cc"),
        ("fact-maintenance", "引擎大整理約30萬；工單／單據齊全"),
    ]
    if include_555:
        rows.append(("fact-555", "原廠555匹"))
    return [
        TaskBoundEvidenceFactV1(
            fact_id=fact_id,
            authority_ref=f"workbench:x5m:{fact_id}",
            statement=statement,
            public_safe_forms=safe_forms.get(fact_id, [statement]),
            provenance="WORKBENCH" if fact_id != "fact-555" else "DIRECT_USER",
        )
        for fact_id, statement in rows
    ]


def manifest(*, include_555: bool = False):
    return TaskBoundEvidenceManifestV1.build(
        task_id="task-x5m",
        evidence_set_digest=sha256_json(["workbench:X5M"]),
        producer_id="fixture-materializer",
        facts=facts(include_555=include_555),
    )


def segment(candidate: str, text: str, *, kind="FACTUAL", refs=None, support=None, start=0):
    offset = candidate.index(text, start)
    return ClaimCoverageSegmentV1(
        start=offset,
        end=offset + len(text),
        text=text,
        kind=kind,
        authority_fact_ids=list(refs or []),
        support=support,
    )


def detached(candidate: str, production_segments: list[ClaimCoverageSegmentV1]):
    return ClaimCoveragePayloadV1(
        manifest_digest=None,
        segments=[
            ClaimCoverageSegmentV1(
                start=item.start,
                end=item.end,
                text=item.text,
                kind=item.kind,
                authority_fact_ids=[],
                support=None if item.kind == "FACTUAL" else "NOT_APPLICABLE",
            )
            for item in production_segments
        ],
    )


def test_bound_x5m_facts_can_pass_closed_world_coverage():
    candidate = "2009年 BMW X5 M，藍色，里程166,812公里，目前售價73.8萬。"
    m = manifest()
    production_segments = [
        segment(candidate, "2009年", refs=["fact-year"], support="SUPPORTED"),
        segment(candidate, "BMW X5 M", refs=["fact-model"], support="SUPPORTED"),
        segment(candidate, "藍色", refs=["fact-color"], support="SUPPORTED"),
        segment(candidate, "里程166,812公里", refs=["fact-mileage"], support="SUPPORTED"),
        segment(candidate, "目前售價73.8萬", refs=["fact-price"], support="SUPPORTED"),
    ]
    decision = evaluate_claim_coverage(
        candidate=candidate,
        manifest=m,
        production=ClaimCoveragePayloadV1(
            manifest_digest=m.manifest_digest,
            segments=production_segments,
        ),
        detached=detached(candidate, production_segments),
    )
    assert decision.disposition == "PASS"
    assert decision.reason_codes == []


def test_x5m_ambient_oem_specs_fail_even_when_other_facts_are_bound():
    candidate = (
        "2009年 BMW X5 M，原廠555匹 V8 雙渦輪，搭配 xDrive 四輪驅動。"
        "藍色，里程166,812公里，目前售價73.8萬。"
    )
    m = manifest()
    production_segments = [
        segment(candidate, "2009年", refs=["fact-year"], support="SUPPORTED"),
        segment(candidate, "BMW X5 M", refs=["fact-model"], support="SUPPORTED"),
        segment(candidate, "原廠555匹 V8 雙渦輪", support="UNSUPPORTED"),
        segment(candidate, "搭配 xDrive 四輪驅動", support="UNSUPPORTED"),
        segment(candidate, "藍色", refs=["fact-color"], support="SUPPORTED"),
        segment(candidate, "里程166,812公里", refs=["fact-mileage"], support="SUPPORTED"),
        segment(candidate, "目前售價73.8萬", refs=["fact-price"], support="SUPPORTED"),
    ]
    decision = evaluate_claim_coverage(
        candidate=candidate,
        manifest=m,
        production=ClaimCoveragePayloadV1(
            manifest_digest=m.manifest_digest,
            segments=production_segments,
        ),
        detached=detached(candidate, production_segments),
    )
    assert decision.disposition == "FAIL"
    assert sum(code.startswith("UNBOUND_PUBLIC_CLAIM_ATOM") for code in decision.reason_codes) == 2


def test_generation_scope_claim_without_authority_fails():
    candidate = "初代 X5 M，藍色。"
    m = manifest()
    production_segments = [
        segment(candidate, "初代 X5 M", support="UNSUPPORTED"),
        segment(candidate, "藍色", refs=["fact-color"], support="SUPPORTED"),
    ]
    decision = evaluate_claim_coverage(
        candidate=candidate,
        manifest=m,
        production=ClaimCoveragePayloadV1(
            manifest_digest=m.manifest_digest,
            segments=production_segments,
        ),
        detached=detached(candidate, production_segments),
    )
    assert decision.disposition == "FAIL"
    assert any(code.startswith("UNBOUND_PUBLIC_CLAIM_ATOM") for code in decision.reason_codes)


def test_generic_color_cannot_be_semantically_strengthened_without_authority():
    candidate = "經典藍色"
    m = manifest()
    production_segments = [segment(candidate, candidate, refs=["fact-color"], support="SUPPORTED")]
    decision = evaluate_claim_coverage(
        candidate=candidate,
        manifest=m,
        production=ClaimCoveragePayloadV1(
            manifest_digest=m.manifest_digest,
            segments=production_segments,
        ),
        detached=detached(candidate, production_segments),
    )
    assert decision.disposition == "FAIL"


def test_direct_555_authority_does_not_promote_xdrive():
    candidate = "原廠555匹，xDrive 四輪驅動。"
    m = manifest(include_555=True)
    production_segments = [
        segment(candidate, "原廠555匹", refs=["fact-555"], support="SUPPORTED"),
        segment(candidate, "xDrive 四輪驅動", support="UNSUPPORTED"),
    ]
    decision = evaluate_claim_coverage(
        candidate=candidate,
        manifest=m,
        production=ClaimCoveragePayloadV1(
            manifest_digest=m.manifest_digest,
            segments=production_segments,
        ),
        detached=detached(candidate, production_segments),
    )
    assert decision.disposition == "FAIL"
    assert sum(code.startswith("UNBOUND_PUBLIC_CLAIM_ATOM") for code in decision.reason_codes) == 1


def test_missing_semantic_character_coverage_holds():
    candidate = "BMW X5 M 2009"
    m = manifest()
    production_segments = [
        segment(candidate, "BMW X5 M", refs=["fact-model"], support="SUPPORTED"),
    ]
    decision = evaluate_claim_coverage(
        candidate=candidate,
        manifest=m,
        production=ClaimCoveragePayloadV1(
            manifest_digest=m.manifest_digest,
            segments=production_segments,
        ),
        detached=detached(candidate, production_segments),
    )
    assert decision.disposition == "HOLD"
    assert any("SEMANTIC_COVERAGE_GAP" in code for code in decision.reason_codes)


def test_unknown_authority_fact_id_holds():
    candidate = "BMW X5 M"
    m = manifest()
    production_segments = [
        segment(candidate, candidate, refs=["fact-does-not-exist"], support="SUPPORTED"),
    ]
    decision = evaluate_claim_coverage(
        candidate=candidate,
        manifest=m,
        production=ClaimCoveragePayloadV1(
            manifest_digest=m.manifest_digest,
            segments=production_segments,
        ),
        detached=detached(candidate, production_segments),
    )
    assert decision.disposition == "HOLD"
    assert any(code.startswith("UNKNOWN_AUTHORITY_FACT_ID") for code in decision.reason_codes)


def test_production_detached_factuality_disagreement_holds():
    candidate = "BMW X5 M"
    m = manifest()
    production_segment = segment(candidate, candidate, refs=["fact-model"], support="SUPPORTED")
    detached_segment = ClaimCoverageSegmentV1(
        start=0,
        end=len(candidate),
        text=candidate,
        kind="NON_FACTUAL",
        authority_fact_ids=[],
        support="NOT_APPLICABLE",
    )
    decision = evaluate_claim_coverage(
        candidate=candidate,
        manifest=m,
        production=ClaimCoveragePayloadV1(
            manifest_digest=m.manifest_digest,
            segments=[production_segment],
        ),
        detached=ClaimCoveragePayloadV1(manifest_digest=None, segments=[detached_segment]),
    )
    assert decision.disposition == "HOLD"
    assert any(code.startswith("CLAIM_CLASSIFICATION_INVARIANCE_HOLD") for code in decision.reason_codes)


def test_missing_manifest_holds_instead_of_assuming_ambient_knowledge():
    candidate = "BMW X5 M"
    production_segments = [segment(candidate, candidate, support="AMBIGUOUS")]
    decision = evaluate_claim_coverage(
        candidate=candidate,
        manifest=None,
        production=ClaimCoveragePayloadV1(manifest_digest=None, segments=production_segments),
        detached=detached(candidate, production_segments),
    )
    assert decision.disposition == "HOLD"
    assert "EVIDENCE_MANIFEST_MISSING" in decision.reason_codes


def test_claim_fail_is_required_by_final_commit_even_when_other_checks_pass():
    evidence_refs = ["workbench:X5M"]
    m = manifest()
    snapshot = AuthoritativeSalesTaskSnapshotV1(
        task_id="task-x5m",
        conversation_or_session_id="session-x5m",
        current_user_request="幫我寫8891刊登文案",
        current_user_request_sha256=sha256_text("幫我寫8891刊登文案"),
        task_class="8891_COPY",
        target_surface="8891",
        direct_user_hard_requirements=[],
        hard_requirements_digest=sha256_json([]),
        sales_execution_policy_ref=POLICY,
        global_authority_revision="GLOBAL-current",
        sales_authority_revision="SALES-current",
        library_authority_revision="LIBRARY-current",
        real_car_authority_revision="REAL_CAR-current",
        vehicle_instance_id="VIN:WBSGY01070LK10611",
        evidence_refs=evidence_refs,
        evidence_set_digest=sha256_json(evidence_refs),
        task_bound_evidence_manifest=m,
        generation=1,
        issued_at=NOW,
        valid_until=NOW + timedelta(minutes=5),
        producer_id=PRODUCER,
        snapshot_digest="0" * 64,
    )
    snapshot = snapshot.model_copy(update={"snapshot_digest": sha256_json(snapshot.digest_payload())})
    candidate = "原廠555匹 BMW X5 M"
    rows = [
        ProductCheckResultV1(
            check_id=check_id,
            disposition="FAIL" if check_id == "PUBLIC_CLAIM_COVERAGE" else "PASS",
            result_ref=f"result:{check_id}",
            snapshot_digest=snapshot.snapshot_digest,
            candidate_digest=sha256_text(candidate),
        )
        for check_id in REQUIRED_PRODUCT_CHECKS
    ]
    gate = FinalOutputCommitGateV1(
        producer_id=PRODUCER,
        policy_ref=POLICY,
        runtime_commit="n1c-test",
        now=lambda: NOW,
    )
    decision = gate.decide(snapshot=snapshot, candidate=candidate, results=rows)
    outcome = gate.commit(
        snapshot=snapshot,
        candidate=candidate,
        decision=decision,
        persistence_required=False,
    )
    assert outcome.public_output is None
    assert outcome.receipt.final_output_commit == "FAIL"
    assert "PUBLIC_CLAIM_COVERAGE" in decision.failed_check_ids


def coverage_decision(candidate, m, segments):
    return evaluate_claim_coverage(
        candidate=candidate,
        manifest=m,
        production=ClaimCoveragePayloadV1(manifest_digest=m.manifest_digest, segments=segments),
        detached=detached(candidate, segments),
    )


@pytest.mark.parametrize("support", ["SUPPORTED", "UNSUPPORTED", "AMBIGUOUS", "NOT_APPLICABLE", None])
@pytest.mark.parametrize("text,fact_id", [
    ("BMW X5 M", "fact-model"),
    ("X5 M", "fact-model"),
    ("2009年", "fact-year"),
    ("藍色", "fact-color"),
    ("原廠555匹", "fact-555"),
    ("引擎大整理約30萬；工單／單據齊全", "fact-maintenance"),
])
def test_application_support_uses_exact_safe_form_independent_of_model_enum(support, text, fact_id):
    m = manifest(include_555=True)
    decision = coverage_decision(text, m, [segment(text, text, refs=[fact_id], support=support)])
    assert decision.disposition == "PASS"


@pytest.mark.parametrize("support", ["SUPPORTED", "UNSUPPORTED", "AMBIGUOUS", "NOT_APPLICABLE", None])
def test_irrelevant_evidence_binding_neg(support):
    candidate = "BMW X5 M 555hp xDrive V8 twin turbo"
    m = TaskBoundEvidenceManifestV1.build(
        task_id="task-x5m", evidence_set_digest=sha256_json(["workbench:X5M"]),
        producer_id="fixture-materializer", facts=[facts()[0]],
    )
    decision = coverage_decision(
        candidate, m, [segment(candidate, candidate, refs=["fact-model"], support=support)],
    )
    assert decision.disposition == "FAIL"
    assert "CLAIM_NOT_ENTAILED_BY_BOUND_FACT:0" in decision.reason_codes


def test_whole_sentence_masking_neg():
    candidate = "2009年 BMW X5 M 原廠555匹"
    m = TaskBoundEvidenceManifestV1.build(
        task_id="task-x5m", evidence_set_digest=sha256_json(["workbench:X5M"]),
        producer_id="fixture-materializer", facts=facts()[:2],
    )
    decision = coverage_decision(candidate, m, [
        segment(candidate, candidate, refs=["fact-year", "fact-model"], support="SUPPORTED"),
    ])
    assert decision.disposition == "HOLD"
    assert "NON_ATOMIC_FACTUAL_SEGMENT:0" in decision.reason_codes


def test_atomic_year_and_model_positive():
    candidate = "2009年 BMW X5 M"
    decision = coverage_decision(candidate, manifest(), [
        segment(candidate, "2009年", refs=["fact-year"]),
        segment(candidate, "BMW X5 M", refs=["fact-model"]),
    ])
    assert decision.disposition == "PASS"


@pytest.mark.parametrize("text", ["原廠555匹", "xDrive 四輪驅動"])
def test_model_supported_without_authority_still_fails(text):
    decision = coverage_decision(text, manifest(), [segment(text, text, support="SUPPORTED")])
    assert decision.disposition == "FAIL"
    assert "UNBOUND_PUBLIC_CLAIM_ATOM:0" in decision.reason_codes


def test_555_safe_form_does_not_authorize_xdrive_even_when_model_claims_support():
    candidate = "原廠555匹，xDrive 四輪驅動"
    decision = coverage_decision(candidate, manifest(include_555=True), [
        segment(candidate, "原廠555匹", refs=["fact-555"], support="SUPPORTED"),
        segment(candidate, "xDrive 四輪驅動", refs=["fact-555"], support="SUPPORTED"),
    ])
    assert decision.disposition == "FAIL"
    assert "CLAIM_NOT_ENTAILED_BY_BOUND_FACT:1" in decision.reason_codes


def test_missing_safe_forms_holds_without_statement_fallback():
    fact = facts()[0].model_copy(update={"public_safe_forms": []})
    m = TaskBoundEvidenceManifestV1.build(
        task_id="task-x5m", evidence_set_digest=sha256_json(["workbench:X5M"]),
        producer_id="fixture-materializer", facts=[fact],
    )
    decision = coverage_decision("BMW X5 M", m, [
        segment("BMW X5 M", "BMW X5 M", refs=["fact-model"], support="SUPPORTED"),
    ])
    assert decision.disposition == "HOLD"
    assert "PUBLIC_SAFE_FORMS_MISSING:0" in decision.reason_codes


def test_blank_safe_form_rejected():
    with pytest.raises(ValidationError, match="PUBLIC_SAFE_FORM_EMPTY"):
        TaskBoundEvidenceFactV1(
            fact_id="blank", authority_ref="workbench:X5M", statement="BMW X5 M",
            public_safe_forms=[" \t\n"], provenance="WORKBENCH",
        )


@pytest.mark.parametrize("candidate,expected", [
    ("BMW  X5\tM", "PASS"),
    ("BMW X5 M 555hp", "FAIL"),
    ("BMW X5 M!", "FAIL"),
    ("bmw x5 m", "FAIL"),
])
def test_safe_form_normalization_preserves_meaning(candidate, expected):
    decision = coverage_decision(candidate, manifest(), [
        segment(candidate, candidate, refs=["fact-model"], support="SUPPORTED"),
    ])
    assert decision.disposition == expected


@pytest.mark.parametrize("candidate,refs,expected", [
    ("BMW X5 M 555hp xDrive V8 twin turbo", ["fact-model"], "FAIL"),
    ("2009年 BMW X5 M 原廠555匹", ["fact-year", "fact-model"], "HOLD"),
])
def test_r1_exact_final_consumer_falsifiers_withhold(candidate, refs, expected):
    class Materializer:
        def materialize(self, snapshot):
            return TaskBoundEvidenceManifestV1.build(
                task_id=snapshot.task_id, evidence_set_digest=snapshot.evidence_set_digest,
                producer_id="fixture-materializer",
                facts=[fact for fact in facts() if fact.fact_id in refs],
            )

    class Responses:
        def create(self, **kwargs):
            prompt = json.loads(kwargs["input"])
            m = prompt["task"].get("task_bound_evidence_manifest")
            payload = {
                "snapshot_digest": prompt["snapshot_digest"],
                "candidate_digest": prompt["candidate_digest"],
                "disposition": "PASS", "reason_codes": [],
                "claim_coverage": {
                    "manifest_digest": m["manifest_digest"] if m else None,
                    "segments": [{
                        "start": 0, "end": len(candidate), "text": candidate, "kind": "FACTUAL",
                        "authority_fact_ids": refs if m else [], "support": "SUPPORTED" if m else None,
                    }],
                },
            }
            return {"id": "fixture-response", "status": "completed", "output_text": json.dumps(payload)}

    evaluator = OpenAISalesProductEvaluator(
        production_model="fixture-production", detached_model="fixture-detached",
        api_key=SecretStr("fixture-only"), production_instructions="Product evaluation",
        detached_instructions="Detached evaluation", client=SimpleNamespace(responses=Responses()),
    )
    gate = FinalOutputCommitGateV1(
        producer_id=PRODUCER, policy_ref=POLICY, runtime_commit="n1c-r1", now=lambda: NOW,
    )
    service = ControlledSalesServiceV1(
        candidate_generator=SimpleNamespace(generate=lambda snapshot: candidate),
        product_evaluator=evaluator, commit_gate=gate, producer_id=PRODUCER, policy_ref=POLICY,
        global_authority_revision="GLOBAL-current", sales_authority_revision="SALES-current",
        library_authority_revision="LIBRARY-current", real_car_authority_revision="REAL_CAR-current",
        evidence_materializer=Materializer(), now=lambda: NOW, id_factory=lambda: "task-x5m",
    )
    outcome = service.handle(
        current_user_request="Use task evidence only", conversation_or_session_id="session-x5m",
        task_class="8891_COPY", target_surface="8891", direct_user_hard_requirements=[],
        vehicle_instance_id="fixture-X5M", evidence_refs=["workbench:X5M"],
    )
    assert outcome.receipt.final_output_commit == expected
    assert outcome.public_output is None
