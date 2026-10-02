from pathlib import Path

from global_hybrid_v2.public_copy_finalizer import (
    AppOwnedPublicCopyFinalizer,
    GuardCheck,
    GuardDecision,
    PublicCopyCandidate,
    PublicCopyField,
    PublicCopyGuardReceipt,
    PublicCopySnapshotInput,
    SnapshotState,
    SQLitePublicCopyFinalizerStore,
    sha256_json,
)


class PassGuard:
    def evaluate(self, *, snapshot, candidate, candidate_digest):
        return PublicCopyGuardReceipt(
            decision=GuardDecision.PASS,
            candidate_digest=candidate_digest,
            snapshot_digest=snapshot.snapshot_digest,
            requested_field_shape=GuardCheck.PASS,
            claim_safety=GuardCheck.PASS,
            internal_unknown_suppression=GuardCheck.PASS,
            structured_field_redundancy=GuardCheck.PASS,
            supporting_point_minimization=GuardCheck.PASS,
            native_seller_voice=GuardCheck.PASS,
            material_disclosure=GuardCheck.PASS,
        )


class BadDigestGuard(PassGuard):
    def evaluate(self, *, snapshot, candidate, candidate_digest):
        receipt = super().evaluate(
            snapshot=snapshot, candidate=candidate, candidate_digest=candidate_digest
        )
        return receipt.model_copy(update={"candidate_digest": "0" * 64})


def snapshot_input():
    return PublicCopySnapshotInput(
        target_surface="8891",
        copy_scope="PARTIAL_8891_FIELD_REQUEST",
        user_request="只要廣告副標題與特色說明",
        requested_fields=("廣告副標題", "特色說明"),
        hard_requirements=("公開文案",),
        structured_fields_already_exposed=("車型", "年份", "里程"),
        verified_public_facts=("MST Performance進氣", "BILSTEIN避震", "全景天窗"),
        internal_only_unknowns=("ECU是否寫程式", "BILSTEIN確切型號"),
        voice_contract=("自然台灣中古車業務語氣", "不要AI旁白"),
    )


def candidate():
    return PublicCopyCandidate(
        fields=(
            PublicCopyField(label="廣告副標題", value="MST Performance進氣＋BILSTEIN避震"),
            PublicCopyField(label="特色說明", value="MST Performance進氣、BILSTEIN避震都有。"),
        )
    )


def test_draft_cannot_finalize(tmp_path: Path):
    store = SQLitePublicCopyFinalizerStore(tmp_path / "state.sqlite")
    finalizer = AppOwnedPublicCopyFinalizer(store=store, guard=PassGuard())
    draft = finalizer.create_draft(snapshot_input())
    assert draft.state is SnapshotState.DRAFT
    try:
        finalizer.finalize(draft.task_handle, candidate())
    except PermissionError as exc:
        assert str(exc) == "PUBLIC_COPY_TASK_CONFIRMATION_REQUIRED"
    else:
        raise AssertionError("unconfirmed draft finalized")


def test_wrong_confirmation_nonce_fails(tmp_path: Path):
    store = SQLitePublicCopyFinalizerStore(tmp_path / "state.sqlite")
    draft = store.create_draft(snapshot_input())
    try:
        store.confirm(draft.task_handle, "wrong-nonce" * 4)
    except PermissionError as exc:
        assert str(exc) == "PUBLIC_COPY_CONFIRMATION_NONCE_INVALID"
    else:
        raise AssertionError("wrong nonce confirmed")


def test_confirmed_snapshot_exact_candidate_passes(tmp_path: Path):
    store = SQLitePublicCopyFinalizerStore(tmp_path / "state.sqlite")
    finalizer = AppOwnedPublicCopyFinalizer(store=store, guard=PassGuard())
    draft = finalizer.create_draft(snapshot_input())
    confirmed = finalizer.confirm(draft.task_handle, draft.confirmation_nonce)
    assert confirmed.state is SnapshotState.CONFIRMED
    receipt = finalizer.finalize(draft.task_handle, candidate())
    assert receipt.decision is GuardDecision.PASS
    assert receipt.final_output == candidate()
    assert receipt.candidate_digest == sha256_json(candidate())
    loaded = store.load_receipt(receipt.receipt_id)
    assert loaded.final_output == candidate()


def test_candidate_shape_mismatch_never_passes(tmp_path: Path):
    store = SQLitePublicCopyFinalizerStore(tmp_path / "state.sqlite")
    finalizer = AppOwnedPublicCopyFinalizer(store=store, guard=PassGuard())
    draft = finalizer.create_draft(snapshot_input())
    finalizer.confirm(draft.task_handle, draft.confirmation_nonce)
    bad = PublicCopyCandidate(fields=(PublicCopyField(label="特色說明", value="x"),))
    receipt = finalizer.finalize(draft.task_handle, bad)
    assert receipt.decision is GuardDecision.FAIL
    assert receipt.final_output is None
    assert "PUBLIC_COPY_REQUESTED_FIELD_SHAPE_MISMATCH" in receipt.guard_receipt.blocker_codes


def test_guard_digest_mismatch_fails_closed(tmp_path: Path):
    store = SQLitePublicCopyFinalizerStore(tmp_path / "state.sqlite")
    finalizer = AppOwnedPublicCopyFinalizer(store=store, guard=BadDigestGuard())
    draft = finalizer.create_draft(snapshot_input())
    finalizer.confirm(draft.task_handle, draft.confirmation_nonce)
    receipt = finalizer.finalize(draft.task_handle, candidate())
    assert receipt.decision is GuardDecision.FAIL
    assert receipt.final_output is None
    assert "PUBLIC_COPY_FINALIZER_BINDING_MISMATCH" in receipt.guard_receipt.blocker_codes


def test_confirm_is_immutable_and_idempotent(tmp_path: Path):
    store = SQLitePublicCopyFinalizerStore(tmp_path / "state.sqlite")
    draft = store.create_draft(snapshot_input())
    first = store.confirm(draft.task_handle, draft.confirmation_nonce)
    second = store.confirm(draft.task_handle, draft.confirmation_nonce)
    assert first.snapshot_digest == second.snapshot_digest == draft.snapshot_digest
    assert first.state is second.state is SnapshotState.CONFIRMED
