"""Local synthetic A-J contract fixtures; no semantic evaluator or network calls."""
import pytest
from pydantic import ValidationError
from starlette.testclient import TestClient

from global_hybrid_v2.existing_copy_policy_bridge import (
    SEMANTIC_DEBT,
    ExistingCopyPolicyBridge,
    acceptance_witness,
    commit_fence,
    copy_egress_audit,
    same_state_rewrite_allowed,
    state_digest,
)
from global_hybrid_v2.finalizer_app import FinalizerSettings, create_finalizer_app
from global_hybrid_v2.public_copy_finalizer import (
    AdmittedSupportingProof,
    AppOwnedPublicCopyFinalizer,
    ExistingCopyPolicyInput,
    GuardCheck,
    GuardDecision,
    PublicCopyCandidate,
    PublicCopyField,
    PublicCopySnapshotInput,
    SQLitePublicCopyFinalizerStore,
    confirmation_page,
    result_page,
    sha256_json,
)
from tests.test_public_copy_finalizer import PassGuard


def policy(**updates):
    return ExistingCopyPolicyInput(
        policy_revision="fixture-existing-sales-policy", source_refs=("fixture-confirmed-input",),
        supporting_proofs=(AdmittedSupportingProof(
            proof_id="proof-1", claim="BILSTEIN避震", proof_payload="保養單可查", evidence_refs=("record-1",),
        ),),
        field_max_chars=(40, 200), field_max_lines=(1, 4), primary_reason_literal="日常代步",
    ).model_copy(update=updates)


def candidate(body="BILSTEIN避震，保養單可查。", subtitle="日常代步，保養紀錄可查"):
    return PublicCopyCandidate(fields=(
        PublicCopyField(label="廣告副標題", value=subtitle), PublicCopyField(label="特色說明", value=body),
    ))


def setup(tmp_path, **updates):
    store = SQLitePublicCopyFinalizerStore(tmp_path / "stage1-existing.sqlite")
    data = PublicCopySnapshotInput(
        target_surface="8891", copy_scope="PARTIAL_8891_FIELD_REQUEST", user_request="副標與特色說明",
        requested_fields=("廣告副標題", "特色說明"), existing_copy_policy=policy(),
        structured_fields_already_exposed=("2018年", "里程8萬公里"), active_exclusions=("貸款保證",),
        verified_public_facts=("BILSTEIN避震", "MST進氣", "全景天窗", "電動尾門", "環景"),
        internal_only_unknowns=("ECU是否寫程式", "BILSTEIN確切型號未知"), max_supporting_points=2,
    ).model_copy(update=updates)
    draft = store.create_draft(data)
    return store, store.confirm(draft.task_handle, draft.confirmation_nonce)


def test_a_positive_hard_gates_pass_but_semantics_never_silently_pass(tmp_path):
    store, snapshot = setup(tmp_path)
    value = candidate()
    witness = acceptance_witness(snapshot, value, sha256_json(value))
    assert not witness.hard_gate_blockers
    assert witness.consumed_proof_refs == ("proof-1",)
    service = AppOwnedPublicCopyFinalizer(store=store, guard=ExistingCopyPolicyBridge())
    receipt = service.finalize(snapshot.task_handle, value)
    assert receipt.guard_receipt.deterministic_hard_gates is GuardCheck.PASS
    assert receipt.guard_receipt.capability_debt == SEMANTIC_DEBT
    assert receipt.decision is GuardDecision.FAIL and receipt.final_output is None
    assert store.load_receipt(receipt.receipt_id).final_output is None
    with pytest.raises(PermissionError):
        result_page(receipt)


@pytest.mark.parametrize(("body", "blocker"), [
    ("BILSTEIN避震、MST進氣、全景天窗、電動尾門、環景", "MAX_SUPPORTING_POINTS"),
    ("2018年，里程8萬公里", "STRUCTURED_FIELD_REPLAY"),
    ("很有誠意", "V94_PORTABLE_FILLER"), ("性能氣勢", "V94_PORTABLE_FILLER"),
    ("都有內容", "V94_PORTABLE_FILLER"), ("值得直接看實車", "V94_PORTABLE_FILLER"),
    ("ECU 是否寫程式", "INTERNAL_UNKNOWN_LEAK"),
    ("BILSTEIN 確切型號未知", "INTERNAL_UNKNOWN_LEAK"),
    ("貸款保證", "ACTIVE_EXCLUSION"), ("provenance：來源待查", "PROVENANCE_LEAK"),
    ("建議您依目標客群安排銷售策略", "KNOWN_CONSULTANT_PROSE"),
])
def test_b_c_d_known_failures(tmp_path, body, blocker):
    store, snapshot = setup(tmp_path)
    value = candidate(body)
    receipt = AppOwnedPublicCopyFinalizer(store=store, guard=ExistingCopyPolicyBridge()).finalize(
        snapshot.task_handle, value,
    )
    assert blocker in receipt.guard_receipt.blocker_codes
    assert receipt.guard_receipt.deterministic_hard_gates is GuardCheck.FAIL
    assert receipt.final_output is None


def test_b_v94_combined_matching_failure(tmp_path):
    _, snapshot = setup(tmp_path)
    value = candidate("2018年，里程8萬公里。BILSTEIN避震、MST進氣、全景天窗、電動尾門、環景，"
                      "很有誠意，性能氣勢都有內容，值得直接看實車。")
    witness = acceptance_witness(snapshot, value, sha256_json(value))
    assert {"MAX_SUPPORTING_POINTS", "STRUCTURED_FIELD_REPLAY", "V94_PORTABLE_FILLER"} <= set(
        witness.hard_gate_blockers
    )


def test_e_required_material_disclosure(tmp_path):
    _, snapshot = setup(tmp_path, required_material_disclosures=("右後門曾鈑修",))
    value = candidate()
    assert "REQUIRED_DISCLOSURE_MISSING" in acceptance_witness(
        snapshot, value, sha256_json(value)
    ).hard_gate_blockers
    disclosed = candidate("BILSTEIN避震，保養單可查。右後門曾鈑修。")
    assert not acceptance_witness(snapshot, disclosed, sha256_json(disclosed)).hard_gate_blockers


@pytest.mark.parametrize("reverse", [True, False])
def test_f_field_shape(tmp_path, reverse):
    store, snapshot = setup(tmp_path)
    fields = candidate().fields
    value = PublicCopyCandidate(fields=tuple(reversed(fields)) if reverse else fields[:1])
    receipt = AppOwnedPublicCopyFinalizer(store=store, guard=ExistingCopyPolicyBridge()).finalize(
        snapshot.task_handle, value,
    )
    assert receipt.final_output is None
    assert "PUBLIC_COPY_REQUESTED_FIELD_SHAPE_MISMATCH" in receipt.guard_receipt.blocker_codes


@pytest.mark.parametrize("field", ["candidate_digest", "snapshot_digest", "current_state_digest",
                                  "consumed_proof_refs", "capability_debt"])
def test_g_witness_binding(tmp_path, field):
    _, snapshot = setup(tmp_path)
    value = candidate()
    witness = acceptance_witness(snapshot, value, sha256_json(value))
    bad = witness.model_copy(update={field: () if field in ("consumed_proof_refs", "capability_debt")
                                     else "0" * 64})
    audit = copy_egress_audit(snapshot, value, bad, sha256_json(bad))
    assert "WITNESS_BINDING_MISMATCH" in audit.hard_gate_blockers


def test_g_exact_candidate_snapshot_audit_and_task_binding(tmp_path):
    _, snapshot = setup(tmp_path)
    value = candidate()
    wrong_digest = acceptance_witness(snapshot, value, "0" * 64)
    assert "CANDIDATE_DIGEST_MISMATCH" in wrong_digest.hard_gate_blockers
    changed = snapshot.model_copy(update={"snapshot_digest": "0" * 64})
    assert "SNAPSHOT_DIGEST_MISMATCH" in acceptance_witness(
        changed, value, sha256_json(value)
    ).hard_gate_blockers
    witness = acceptance_witness(snapshot, value, sha256_json(value))
    audit = copy_egress_audit(snapshot, value, witness, sha256_json(witness))
    assert "WITNESS_BINDING_MISMATCH" in copy_egress_audit(
        snapshot, value, witness, "0" * 64
    ).hard_gate_blockers
    assert "COMMIT_FENCE_BINDING_MISMATCH" in commit_fence(
        snapshot, value, witness, audit.model_copy(update={"witness_digest": "0" * 64}),
    )
    other_task = snapshot.model_copy(update={"task_handle": "other-task" * 8})
    assert commit_fence(other_task, value, witness, audit)
    assert commit_fence(snapshot, candidate("changed candidate"), witness, audit)


@pytest.mark.parametrize("body", ["保養紀錄可查。", "BILSTEIN避震。", "保養單可查。"])
def test_h_full_body_requires_admitted_proof_claim_and_payload(tmp_path, body):
    _, snapshot = setup(tmp_path, copy_scope="FULL_8891_BODY")
    value = candidate(body)
    assert "SUPPORTING_PROOF_NOT_SERIALIZED" in acceptance_witness(
        snapshot, value, sha256_json(value)
    ).hard_gate_blockers


def test_h_full_body_literal_proof_positive(tmp_path):
    _, snapshot = setup(tmp_path, copy_scope="FULL_8891_BODY")
    value = candidate()
    assert not acceptance_witness(snapshot, value, sha256_json(value)).hard_gate_blockers


@pytest.mark.parametrize(("value", "blocker"), [
    (candidate(subtitle="日常代步" * 11), "SURFACE_LENGTH"),
    (candidate(subtitle="日常代步\n保養可查"), "SURFACE_HIERARCHY"),
    (candidate(subtitle="保養可查"), "PRIMARY_REASON_MISSING"),
])
def test_surface_bounds(tmp_path, value, blocker):
    _, snapshot = setup(tmp_path)
    assert blocker in acceptance_witness(snapshot, value, sha256_json(value)).hard_gate_blockers


def test_j_commit_fence_detects_state_changed_during_guard(tmp_path):
    store, snapshot = setup(tmp_path)

    class RacingGuard(PassGuard):
        def evaluate(self, **kwargs):
            receipt = super().evaluate(**kwargs)
            with store._connect() as connection:
                connection.execute("UPDATE public_copy_task_snapshot SET state = 'DRAFT'")
            return receipt

    service = AppOwnedPublicCopyFinalizer(store=store, guard=RacingGuard())
    with pytest.raises(RuntimeError, match="PUBLIC_COPY_COMMIT_FENCE_STATE_MISMATCH"):
        service.finalize(snapshot.task_handle, candidate())
    with store._connect() as connection:
        assert connection.execute("SELECT count(*) FROM public_copy_finalization").fetchone()[0] == 0


def test_j_result_surface_rejects_changed_exact_candidate(tmp_path):
    store, snapshot = setup(tmp_path)
    receipt = AppOwnedPublicCopyFinalizer(store=store, guard=PassGuard()).finalize(
        snapshot.task_handle, candidate(),
    )
    assert "日常代步" in result_page(receipt)
    with pytest.raises(RuntimeError, match="PUBLIC_COPY_COMMIT_FENCE_BINDING_MISMATCH"):
        result_page(receipt.model_copy(update={"final_output": candidate("changed")}))


def test_j_confirmed_policy_immutable_and_confirmation_displays_it(tmp_path):
    store, snapshot = setup(tmp_path)
    assert "fixture-existing-sales-policy" in confirmation_page(snapshot)
    with pytest.raises(ValidationError):
        snapshot.snapshot.existing_copy_policy.policy_revision = "changed"
    before = snapshot.snapshot_digest
    snapshot.snapshot.authority_revisions["untrusted-memory-edit"] = "changed"
    assert store.load_snapshot(snapshot.task_handle).snapshot_digest == before
    assert store.confirm(snapshot.task_handle, snapshot.confirmation_nonce).snapshot_digest == before


def test_default_app_uses_bridge_even_if_credential_exists_and_returns_hold(tmp_path, monkeypatch):
    def no_paid_guard(*args, **kwargs):
        raise AssertionError("paid guard must not be constructed")

    monkeypatch.setattr("global_hybrid_v2.public_copy_finalizer.OpenAI", no_paid_guard)
    settings = FinalizerSettings(db_path=str(tmp_path / "app.sqlite"), base_url="https://fixture",
                                 model="unused", openai_api_key="synthetic-not-a-key",
                                 allow_ephemeral_canary=True)
    app = create_finalizer_app(settings=settings)
    client = TestClient(app)
    assert client.get("/health").json()["evaluator_configured"] is False
    store, snapshot = setup(tmp_path)
    # Inject the same confirmed store through the existing Stage 1 app factory.
    client = TestClient(create_finalizer_app(settings=settings, finalizer=AppOwnedPublicCopyFinalizer(
        store=store, guard=ExistingCopyPolicyBridge(),
    )))
    response = client.post(f"/api/tasks/{snapshot.task_handle}/finalize", json=candidate().model_dump())
    assert response.status_code == 422
    assert response.json()["deterministic_hard_gates"] == "PASS"
    assert response.json()["capability_debt"]
    assert "result_url" not in response.json()
    assert client.get(f"/results/{response.json()['receipt_id']}").status_code == 404


def test_one_same_state_rewrite_interface_only(tmp_path):
    _, snapshot = setup(tmp_path)
    digest = state_digest(snapshot)
    assert same_state_rewrite_allowed(attempt=1, previous_state_digest=digest, current_state_digest=digest)
    assert not same_state_rewrite_allowed(
        attempt=2, previous_state_digest=digest, current_state_digest=digest,
    )
    assert not same_state_rewrite_allowed(
        attempt=1, previous_state_digest=digest, current_state_digest="0" * 64,
    )


@pytest.mark.parametrize(("update", "blocker"), [
    ({"existing_copy_policy": None}, "EXISTING_COPY_POLICY_MISSING"),
    ({"existing_copy_policy": policy(field_max_chars=(40,))}, "SURFACE_BOUNDS_SHAPE"),
    ({"existing_copy_policy": policy(required_literals=("預約看車",))}, "LITERAL_REQUIREMENT_MISSING"),
    ({"existing_copy_policy": policy(supporting_proofs=()), "copy_scope": "FULL_8891_BODY"},
     "SUPPORTING_PROOF_NOT_SERIALIZED"),
])
def test_missing_policy_requirements_fail_closed(tmp_path, update, blocker):
    _, snapshot = setup(tmp_path, **update)
    value = candidate()
    assert blocker in acceptance_witness(snapshot, value, sha256_json(value)).hard_gate_blockers


def test_low_risk_unresolved_semantics_remain_debt_without_hard_blocker(tmp_path):
    store, snapshot = setup(tmp_path)
    value = candidate("一起慢慢感受日常。")
    receipt = AppOwnedPublicCopyFinalizer(store=store, guard=ExistingCopyPolicyBridge()).finalize(
        snapshot.task_handle, value,
    )
    assert receipt.guard_receipt.deterministic_hard_gates is GuardCheck.PASS
    assert "FREE_FORM_FACTUAL_ENTAILMENT" in receipt.guard_receipt.capability_debt
    assert receipt.final_output is None


def test_high_risk_unresolved_semantics_have_explicit_hard_blocker(tmp_path):
    store, snapshot = setup(tmp_path)
    value = candidate("動力提升百分之五十。")
    receipt = AppOwnedPublicCopyFinalizer(store=store, guard=ExistingCopyPolicyBridge()).finalize(
        snapshot.task_handle, value,
    )
    assert receipt.guard_receipt.deterministic_hard_gates is GuardCheck.FAIL
    assert "TYPED_EVIDENCE_UNPARSED_REMAINDER" in receipt.guard_receipt.blocker_codes
    assert receipt.final_output is None
