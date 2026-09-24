from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime

import pytest

from global_hybrid_v2.adapters.google_vehicle_control import (
    COMPANY_INVENTORY_RANGE,
    COMPANY_INVENTORY_SPREADSHEET_ID,
    GoogleControlSheetAdapter,
    GoogleInventoryReader,
    GoogleQuotaExceeded,
)
from global_hybrid_v2.adapters.http_vehicle_configuration import (
    HttpVehicleConfigurationProvider,
)
from global_hybrid_v2.application import create_application
from global_hybrid_v2.contracts import VehicleConfigurationQuery
from global_hybrid_v2.domains.vehicle_configuration import VehicleConfigurationLookupState
from global_hybrid_v2.render_vehicle_control import RenderVehicleReconciliationEndpoint
from global_hybrid_v2.settings import Settings
from global_hybrid_v2.task_evidence import TaskEvidencePlanner, TrustedTaskSemantics
from global_hybrid_v2.vehicle_knowledge import (
    DeterministicVehicleConfigurationVerifier,
    InventoryNormalizer,
    KnowledgeDecision,
    PowerUnit,
    VehicleKnowledgeStore,
    VehicleResearchEvidencePacketV1,
    VisualObservationPacket,
    admit_visual_observation,
)
from global_hybrid_v2.vehicle_worker_contract import (
    CONTROL_PATHS,
    VehicleKnowledgeWorkerContract,
    WorkerProviderUnavailable,
    WorkerQuotaExceeded,
)


def _packet(**updates):
    quote = "最大馬力 320 PS"
    values = {
        "evidence_packet_id": "evidence-tiguan-r-power",
        "work_id": "work-tw-2021-vw-tiguan-r",
        "scope_key": "TW/2021/VW/TIGUAN R",
        "market": "TW",
        "model_year": 2021,
        "make": "VW",
        "model": "TIGUAN R",
        "trim_scope": "R",
        "fact_key": "power.max",
        "fact_family": "POWERTRAIN",
        "observed_literal": "320 PS",
        "value_candidate": "320",
        "unit_candidate": PowerUnit.PS,
        "source_url": "https://www.volkswagen.tw/example",
        "source_role": "TAIWAN_OEM",
        "source_market_scope": "TW",
        "source_model_year_scope": 2021,
        "source_quote": quote,
        "collected_at": datetime.now(UTC),
        "producer": "OpenAIWebResearchPort",
        "unresolved_notes": [],
        "content_sha256": hashlib.sha256(quote.encode()).hexdigest(),
    }
    values.update(updates)
    return VehicleResearchEvidencePacketV1(**values)


def _verified():
    packet = _packet()
    receipt, fact = DeterministicVehicleConfigurationVerifier().verify(
        packet, expected_work_id=packet.work_id, expected_scope_key=packet.scope_key
    )
    assert fact is not None
    return packet, receipt, fact


def test_live_compatible_inventory_normalization_preserves_group_and_raw_row():
    rows = [
        ["", "", "VW", "2021", "TIGUAN R"],
        ["", "", "", "2022", "GOLF R"],
        [],
        ["", "", "", "2023", "NO GROUP"],
        ["", "", "BMW", "2018", "318I"],
    ]
    normalized, held = InventoryNormalizer().normalize(rows)
    assert [(item.make, item.model) for item in normalized] == [
        ("VW", "TIGUAN R"),
        ("VW", "GOLF R"),
        ("BMW", "318I"),
    ]
    assert held == [4]
    assert normalized[0].raw_source_row == tuple(rows[0])


class RecordingSheets:
    def __init__(self, rows=None, failure=None):
        self.rows = rows or []
        self.failure = failure
        self.calls = []
        self.writes = []

    def read_values(self, spreadsheet_id, range_name):
        self.calls.append((spreadsheet_id, range_name))
        if self.failure:
            raise self.failure()
        return self.rows

    def write_values(self, spreadsheet_id, range_name, values):
        self.writes.append((spreadsheet_id, range_name, values))
        return {"updatedRows": len(values)}


def test_inventory_reader_uses_fixed_source_and_google_quota_holds():
    transport = RecordingSheets(failure=GoogleQuotaExceeded)
    result = GoogleInventoryReader(transport).read()
    assert result.state == "HOLD"
    assert result.blocker == "FREE_TIER_QUOTA_EXHAUSTED"
    assert result.attempts == 3
    assert transport.calls == [(COMPANY_INVENTORY_SPREADSHEET_ID, COMPANY_INVENTORY_RANGE)] * 3


@pytest.mark.parametrize("claim", ["verified", "query_ready", "promoted", "authority_state"])
def test_control_sheet_rejects_direct_authority_and_target_override(claim):
    with pytest.raises(ValueError, match="AUTHORITY_CLAIM"):
        GoogleControlSheetAdapter.reject_authority_claim({claim: True})
    with pytest.raises(ValueError, match="TARGET_OVERRIDE"):
        GoogleControlSheetAdapter.reject_authority_claim({"spreadsheet_id": "caller"})


def test_control_sheet_adapter_is_bounded_to_allowed_tabs_and_evidence_role():
    transport = RecordingSheets(rows=[["work-1"]])
    adapter = GoogleControlSheetAdapter(transport)
    assert adapter.read("RESEARCH_QUEUE", "A1:A10") == [["work-1"]]
    result = adapter.write_evidence("EVIDENCE_INBOX", "A1:A1", [["evidence-1"]])
    assert result == {"updatedRows": 1}
    assert transport.writes[0][1] == "EVIDENCE_INBOX!A1:A1"
    with pytest.raises(ValueError, match="TAB_REJECTED"):
        adapter.read("VERIFIED_FACTS", "A1")
    with pytest.raises(ValueError, match="RECEIPT_ONLY"):
        adapter.write_evidence("CONTROL_READBACK", "A1", [["forged"]])


def test_tiguan_taiwan_power_unit_is_ps_not_hp_and_verifier_binds_scope():
    packet, receipt, fact = _verified()
    assert receipt.decision is KnowledgeDecision.PASS
    assert fact.value == "320"
    assert fact.unit is PowerUnit.PS
    assert fact.market == "TW"
    wrong, no_fact = DeterministicVehicleConfigurationVerifier().verify(
        packet, expected_work_id="wrong", expected_scope_key=packet.scope_key
    )
    assert wrong.decision is KnowledgeDecision.HOLD
    assert no_fact is None


def test_invalid_digest_conflict_and_wrong_market_year_hold_or_fail():
    packet = _packet(content_sha256="0" * 64)
    receipt, fact = DeterministicVehicleConfigurationVerifier().verify(
        packet, expected_work_id=packet.work_id, expected_scope_key=packet.scope_key
    )
    assert receipt.decision is KnowledgeDecision.FAIL
    assert fact is None
    for updates in (
        {"source_market_scope": "US"},
        {"source_model_year_scope": 2020},
        {"unresolved_notes": ["conflict"]},
    ):
        packet = _packet(**updates)
        receipt, fact = DeterministicVehicleConfigurationVerifier().verify(
            packet, expected_work_id=packet.work_id, expected_scope_key=packet.scope_key
        )
        assert receipt.decision is KnowledgeDecision.HOLD
        assert fact is None


def _store():
    connection = sqlite3.connect(":memory:")
    store = VehicleKnowledgeStore(connection)
    packet, receipt, fact = _verified()
    connection.execute(
        "INSERT INTO vehicle_coverage_work VALUES(?,?,?)",
        (packet.work_id, packet.scope_key, "OPEN"),
    )
    connection.commit()
    return store, connection, packet, receipt, fact


def test_verified_fact_commit_snapshot_promotion_and_restart():
    store, connection, packet, receipt, fact = _store()
    revision = store.commit_verified_fact(work_id=packet.work_id, packet=packet, receipt=receipt, fact=fact)
    snapshot = store.build_snapshot([revision])
    promotion = store.promote_snapshot(snapshot["snapshot_id"])
    assert store.readback()["promotion_id"] == promotion
    reopened = VehicleKnowledgeStore(connection)
    assert reopened.readback()["snapshot_id"] == snapshot["snapshot_id"]
    assert reopened.commit_verified_fact


def test_atomic_fact_failure_has_zero_partial_authority_writes():
    store, connection, packet, receipt, fact = _store()

    def fail():
        raise sqlite3.OperationalError("second write failed")

    with pytest.raises(sqlite3.OperationalError):
        store.commit_verified_fact(
            work_id=packet.work_id,
            packet=packet,
            receipt=receipt,
            fact=fact,
            inject_failure=fail,
        )
    for table in (
        "research_evidence_packet",
        "vehicle_fact_verification_receipt",
        "vehicle_configuration_revision",
        "vehicle_configuration_fact",
    ):
        assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def test_failed_promotion_preserves_previous_active_snapshot_and_duplicates_idempotent():
    store, connection, packet, receipt, fact = _store()
    revision = store.commit_verified_fact(work_id=packet.work_id, packet=packet, receipt=receipt, fact=fact)
    snapshot = store.build_snapshot([revision])
    first = store.promote_snapshot(snapshot["snapshot_id"])
    assert store.promote_snapshot(snapshot["snapshot_id"]) == first
    connection.execute("INSERT INTO vehicle_snapshot_build VALUES(?,?,?)", ("candidate-2", "1", "{}"))
    connection.commit()
    with pytest.raises(RuntimeError):
        store.promote_snapshot(
            "candidate-2", inject_failure=lambda: (_ for _ in ()).throw(RuntimeError("fail"))
        )
    assert store.readback()["snapshot_id"] == snapshot["snapshot_id"]


class FakeHttp:
    def __init__(self, failure=False):
        self.failure = failure
        self.calls = []

    def get_json(self, path, params):
        self.calls.append((path, params))
        if self.failure:
            raise OSError("unavailable")
        if path.endswith("readback"):
            return {
                "provider_id": "cloudflare-d1-http",
                "provider_version": "snapshot-1",
                "snapshot_id": "snapshot-1",
                "source_revision": "revision-1",
                "generated_at": "2026-09-24T00:00:00Z",
                "active": True,
                "readback_at": "2026-09-24T00:00:01Z",
            }
        return {
            "state": "HIT",
            "query": {"market": "TW", "model_year": 2021, "make": "VW", "model": "TIGUAN R"},
            "configurations": [],
            "uncertainties": [],
            "provenance": ["snapshot:snapshot-1"],
            "provider_id": "cloudflare-d1-http",
            "provider_version": "snapshot-1",
        }


def test_http_provider_query_readback_and_unavailable_has_no_file_fallback():
    query = VehicleConfigurationQuery(market="TW", model_year=2021, make="VW", model="TIGUAN R")
    provider = HttpVehicleConfigurationProvider(FakeHttp())
    assert provider.lookup(query).state is VehicleConfigurationLookupState.HIT
    assert provider.readback().snapshot_id == "snapshot-1"
    failed = HttpVehicleConfigurationProvider(FakeHttp(failure=True))
    result = failed.lookup(query)
    assert result.state is VehicleConfigurationLookupState.PROVIDER_UNAVAILABLE
    assert result.provider_id == "cloudflare-d1-http"
    assert all("file" not in item for item in result.provenance)


def test_cloudflare_mode_incomplete_configuration_fails_without_file_fallback(tmp_path):
    with pytest.raises(RuntimeError, match="incompletely configured"):
        create_application(
            repo_root=tmp_path,
            settings=Settings(vehicle_configuration_provider_mode="cloudflare_d1_http"),
        )


def test_server_owned_evidence_plan_cannot_be_downgraded_by_query_omission():
    query = VehicleConfigurationQuery(market="TW", model_year=2021, make="VW", model="TIGUAN R")
    plan = TaskEvidencePlanner().plan(
        TrustedTaskSemantics("OEM_VS_OBSERVED", query, requires_visual_observation=True)
    )
    assert plan.required_projections == ("vehicle_configuration_reference", "visual_vehicle_observation")
    with pytest.raises(ValueError, match="TRUSTED_VEHICLE_QUERY_REQUIRED"):
        TaskEvidencePlanner().plan(TrustedTaskSemantics("VEHICLE_MODIFICATION"))


def test_visual_packet_is_capability_debt_until_server_attested():
    packet = VisualObservationPacket(
        packet_id="visual-1",
        task_id="task-1",
        producer_id="caller",
        source_photo_sha256="a" * 64,
        observed_equipment=["spoiler"],
        produced_at=datetime.now(UTC),
        server_attested=False,
    )
    with pytest.raises(ValueError, match="UNAVAILABLE_OR_UNTRUSTED"):
        admit_visual_observation(packet, expected_task_id="task-1")


def test_render_control_endpoint_authenticates_and_forbids_target_override():
    endpoint = RenderVehicleReconciliationEndpoint(
        shared_secret="secret", reconcile=lambda: {"status": "PASS"}
    )
    body = (
        b'{"operation":"vehicle-knowledge-reconcile","run_id":"cf-1790208000000",'
        b'"scheduled_at":"2026-09-24T00:00:00.000Z"}'
    )
    import hmac

    signature = hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    assert endpoint.handle(body=body, signature=signature) == {"status": "PASS"}
    assert endpoint.handle(body=body, signature="bad")["status"] == "REJECTED"
    other = body[:-1] + b',"spreadsheet_id":"caller"}'
    other_signature = hmac.new(b"secret", other, hashlib.sha256).hexdigest()
    assert (
        endpoint.handle(body=other, signature=other_signature)["blocker"]
        == "CONTROL_TARGET_OVERRIDE_REJECTED"
    )


def _worker(
    control_handler=lambda path, payload: {"ok": True}, read_handler=lambda path, payload: {"ok": True}
):
    return VehicleKnowledgeWorkerContract(
        control_secret="write-secret",
        read_secret="read-secret",
        control_handler=control_handler,
        read_handler=read_handler,
    )


def test_worker_separates_control_and_read_credentials_and_rejects_injection():
    worker = _worker()
    for path in CONTROL_PATHS:
        assert worker.handle(path, token=None, payload={})[0] == 403
        assert worker.handle(path, token="read-secret", payload={})[0] == 403
        assert worker.handle(path, token="write-secret", payload={}) == (200, {"ok": True})
    assert worker.handle("/v1/vehicle-config/query", token="write-secret", payload={})[0] == 403
    assert worker.handle("/v1/vehicle-config/query", token="read-secret", payload={})[0] == 200
    for field in ("raw_sql", "table_name", "spreadsheet_id", "verified", "promotion_state", "query_ready"):
        status, result = worker.handle(
            "/internal/control/verified-revision",
            token="write-secret",
            payload={field: "caller"},
        )
        assert status == 400
        assert result["error"] == "DIRECT_AUTHORITY_INJECTION"


@pytest.mark.parametrize(
    ("error", "blocker"),
    [
        (WorkerQuotaExceeded, "FREE_TIER_QUOTA_EXHAUSTED"),
        (WorkerProviderUnavailable, "PROVIDER_UNAVAILABLE"),
    ],
)
def test_worker_d1_quota_and_unavailable_fail_closed(error, blocker):
    def fail(path, payload):
        raise error()

    status, result = _worker(control_handler=fail).handle(
        "/internal/control/verified-revision", token="write-secret", payload={}
    )
    assert status == 503
    assert result == {"state": "HOLD", "blocker": blocker}
