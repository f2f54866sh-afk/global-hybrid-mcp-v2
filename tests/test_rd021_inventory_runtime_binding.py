"""Same-turn referent and read-only inventory runtime composition contract."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import replace

import pytest
from pydantic import SecretStr

from global_hybrid_v2.adapters.controlled_responses import ServerTurnContext
from global_hybrid_v2.inventory_identity import (
    AuthoritativeInventoryResolver,
    BindingState,
    GoogleInventorySource,
    InventoryIdentityHold,
    SourceMetadata,
    read_current_snapshot,
)
from global_hybrid_v2.inventory_runtime_binding import (
    InventoryRuntime,
    TrustedTurnReferentIssuer,
    configured_inventory_runtime,
    inventory_binding_readback,
)
from global_hybrid_v2.settings import Settings
from tests.test_rd021_inventory_identity import (
    HEADER,
    META,
    VW,
    EvidenceFixture,
    SourceFixture,
    store,
)

TEXT = "請處理 2021 VW TIGUAN R 的資料"
TURN = ServerTurnContext("conversation-1", "turn-1")


def runtime(source: SourceFixture | None = None) -> InventoryRuntime:
    return InventoryRuntime(source or SourceFixture(), TrustedTurnReferentIssuer())


def test_explicit_turn_issues_candidate_without_minting_vehicle(tmp_path):
    current = runtime()
    snapshot = current.read_snapshot()
    referent = current.issuer.issue(turn=TURN, request_text=TEXT, snapshot=snapshot)
    binding, path = store(tmp_path)
    result = current.resolve_issued(
        referent=referent, turn=TURN, request_text=TEXT, snapshot=snapshot,
        resolver=AuthoritativeInventoryResolver(binding, EvidenceFixture()),
    )
    assert referent.source_observation_id == snapshot.observations[0].observation_id
    assert referent.source_currentness_token == snapshot.currentness_token
    assert (result.binding_state, result.vehicle_instance_id) == (BindingState.INSTANCE_CANDIDATE, None)
    with sqlite3.connect(path) as connection:
        row = connection.execute("SELECT vehicle_instance_id FROM vehicle_source_observation").fetchone()
        assert row == (None,)


def test_existing_canonical_binding_is_freshly_verified(tmp_path):
    current = runtime()
    snapshot = current.read_snapshot()
    referent = current.issuer.issue(turn=TURN, request_text=TEXT, snapshot=snapshot)
    binding, path = store(tmp_path)
    binding.record_snapshot(snapshot)
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE vehicle_source_observation SET vehicle_instance_id = 'vehicle-1', "
                           "binding_state = 'INSTANCE_BOUND' WHERE source_observation_id = ?",
                           (referent.source_observation_id,))
    result = current.resolve_issued(
        referent=referent, turn=TURN, request_text=TEXT, snapshot=snapshot,
        resolver=AuthoritativeInventoryResolver(binding, EvidenceFixture()),
    )
    assert (result.binding_state, result.vehicle_instance_id) == (BindingState.INSTANCE_BOUND, "vehicle-1")


def test_privileged_caller_fields_cannot_be_issued():
    current = runtime()
    snapshot = current.read_snapshot()
    with pytest.raises(TypeError):
        current.issuer.issue(turn=TURN, request_text=TEXT, snapshot=snapshot,
                             vehicle_instance_id="invented", make="BMW")
    referent = current.issuer.issue(
        turn=TURN, request_text=TEXT + " vehicle_instance_id=invented", snapshot=snapshot)
    assert not hasattr(referent, "vehicle_instance_id")
    assert referent.make == "VW"


def test_implicit_referent_and_missing_descriptor_hold():
    current = runtime()
    snapshot = current.read_snapshot()
    with pytest.raises(InventoryIdentityHold, match="HOLD_REFERENT_UNBOUND"):
        current.issuer.issue(turn=TURN, request_text="這台要更新", snapshot=snapshot)
    with pytest.raises(InventoryIdentityHold, match="HOLD_REFERENT_NOT_FOUND"):
        current.issuer.issue(turn=TURN, request_text="2022 BMW X5", snapshot=snapshot)


def test_duplicate_descriptor_holds():
    snapshot = read_current_snapshot(SourceFixture([HEADER, VW, VW]))
    with pytest.raises(InventoryIdentityHold, match="HOLD_IDENTITY_CONFLICT"):
        TrustedTurnReferentIssuer().issue(turn=TURN, request_text=TEXT, snapshot=snapshot)


def test_source_advance_and_request_scope_mismatch_hold(tmp_path):
    source = SourceFixture()
    current = runtime(source)
    snapshot = current.read_snapshot()
    referent = current.issuer.issue(turn=TURN, request_text=TEXT, snapshot=snapshot)
    with pytest.raises(InventoryIdentityHold, match="HOLD_TRUSTED_REFERENT_SCOPE_MISMATCH"):
        current.issuer.verify(referent, turn=TURN, request_text=TEXT + "!", snapshot=snapshot)
    with pytest.raises(InventoryIdentityHold, match="HOLD_TRUSTED_REFERENT_SCOPE_MISMATCH"):
        current.issuer.verify(referent, turn=replace(TURN, turn_id="turn-2"),
                              request_text=TEXT, snapshot=snapshot)
    with pytest.raises(InventoryIdentityHold, match="HOLD_TRUSTED_REFERENT_SCOPE_MISMATCH"):
        current.issuer.verify(replace(referent, source_observation_id="forged"),
                              turn=TURN, request_text=TEXT, snapshot=snapshot)
    source.calls = 0
    source.after = SourceMetadata(META.file_id, "2026-09-28T00:01:00Z", META.sheet_id, META.sheet_name)
    with pytest.raises(InventoryIdentityHold, match="HOLD_INVENTORY_SOURCE_ADVANCED"):
        current.resolve_issued(
            referent=referent, turn=TURN, request_text=TEXT, snapshot=snapshot,
            resolver=AuthoritativeInventoryResolver(store(tmp_path)[0], EvidenceFixture()),
        )


def test_credential_binding_is_read_only_and_has_no_fallback():
    missing = Settings(_env_file=None, google_service_account_json=None)
    with pytest.raises(InventoryIdentityHold, match="INVENTORY_SOURCE_BINDING_UNAVAILABLE"):
        configured_inventory_runtime(missing)
    assert inventory_binding_readback(missing, None)["inventory_source"] == "UNBOUND"
    invalid = Settings(_env_file=None, google_service_account_json=SecretStr("not-json"))
    with pytest.raises(InventoryIdentityHold, match="INVENTORY_SOURCE_BINDING_UNAVAILABLE"):
        configured_inventory_runtime(invalid)
    credential = json.dumps({"type": "service_account", "client_email": "test@example.invalid",
                             "private_key": "dummy", "private_key_id": "test-key"})
    configured = Settings(_env_file=None, google_service_account_json=SecretStr(credential))
    bound = configured_inventory_runtime(configured)
    assert isinstance(bound.source, GoogleInventorySource)
    assert bound.source.required_scopes == (
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.metadata.readonly",
    )
    report = inventory_binding_readback(configured, bound)
    assert (report["inventory_source"], report["trusted_referent_issuer"],
            report["durable_identity_evidence"], report["root_a"]) == (
                "BOUND", "BOUND", "UNBOUND", "UNBOUND")
    assert credential not in str(report)
