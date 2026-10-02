import re
from pathlib import Path

from starlette.testclient import TestClient

from global_hybrid_v2.finalizer_app import FinalizerSettings, create_finalizer_app
from global_hybrid_v2.public_copy_finalizer import (
    AppOwnedPublicCopyFinalizer,
    GuardCheck,
    GuardDecision,
    PublicCopyGuardReceipt,
    SQLitePublicCopyFinalizerStore,
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


def _client(tmp_path: Path):
    finalizer = AppOwnedPublicCopyFinalizer(
        store=SQLitePublicCopyFinalizerStore(tmp_path / "f.sqlite"),
        guard=PassGuard(),
    )
    settings = FinalizerSettings(
        db_path=str(tmp_path / "unused.sqlite"),
        base_url="https://finalizer.example",
        allow_ephemeral_canary=True,
    )
    return TestClient(create_finalizer_app(settings=settings, finalizer=finalizer))


def _draft(client):
    return client.post(
        "/api/tasks/draft",
        json={
            "target_surface": "8891",
            "copy_scope": "PARTIAL_8891_FIELD_REQUEST",
            "user_request": "只要廣告副標題與特色說明",
            "requested_fields": ["廣告副標題", "特色說明"],
            "verified_public_facts": ["MST Performance進氣", "BILSTEIN避震"],
            "internal_only_unknowns": ["ECU是否寫程式"],
            "voice_contract": ["自然台灣中古車業務語氣"],
        },
    )


def test_user_confirm_then_final_result(tmp_path: Path):
    client = _client(tmp_path)
    response = _draft(client)
    assert response.status_code == 202
    task = response.json()["task_handle"]
    page = client.get(f"/tasks/{task}/confirm")
    nonce = re.search(r"name='confirmation_nonce' value='([^']+)'", page.text).group(1)
    confirmed = client.post(
        f"/tasks/{task}/confirm",
        data={"confirmation_nonce": nonce},
        follow_redirects=False,
    )
    assert confirmed.status_code == 200
    result = client.post(
        f"/api/tasks/{task}/finalize",
        json={
            "fields": [
                {"label": "廣告副標題", "value": "MST Performance進氣＋BILSTEIN避震"},
                {"label": "特色說明", "value": "MST Performance進氣、BILSTEIN避震都有。"},
            ]
        },
    )
    assert result.status_code == 200
    final_page = client.get(f"/results/{result.json()['receipt_id']}")
    assert final_page.status_code == 200
    assert "MST Performance進氣＋BILSTEIN避震" in final_page.text


def test_unconfirmed_api_finalize_is_blocked(tmp_path: Path):
    client = _client(tmp_path)
    task = _draft(client).json()["task_handle"]
    blocked = client.post(
        f"/api/tasks/{task}/finalize",
        json={
            "fields": [
                {"label": "廣告副標題", "value": "x"},
                {"label": "特色說明", "value": "y"},
            ]
        },
    )
    assert blocked.status_code == 409
