"""Controlled providers only; these never certify the natural ChatGPT consumer."""
import json
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import SecretStr

from global_hybrid_v2.adapters.controlled_responses import (
    ControlledSalesIngress,
    ForcedHostDispatchAdapter,
    ServerTurnContext,
)
from global_hybrid_v2.adapters.controlled_sales_executor import (
    FAILURE,
    ControlledSalesCompletionExecutor,
)
from global_hybrid_v2.adapters.mcp_server import dispatch_verified_host_task_from_headers
from global_hybrid_v2.canonical_cutover import compile_import, declare_db_canonical, import_fixed_preimage
from global_hybrid_v2.company_commercial_completion import CANONICAL_WORKBENCH_FILE_ID
from global_hybrid_v2.contracts import DomainResult, Owner
from global_hybrid_v2.ingress_admission import IngressTaskClass
from global_hybrid_v2.runtime_composition import (
    ConsumerBindings,
    binding_readback,
    configured_application,
    consumer_readiness,
)
from global_hybrid_v2.transactional_vehicle_store import (
    CanonicalMutation,
    FieldEvidence,
    TransactionalVehicleStore,
    _digest,
    sqlite_contract_schema,
)
from global_hybrid_v2.trusted_workbench_intent import TrustedHostTaskCompiler
from tests.test_mcp_server import _copy_authority_repo, _test_settings
from tests.test_rd021_ingress_admission import Classifier, issue
from tests.test_rd021_media_admission import creative_workbook
from tests.test_rd021_postgres_integration import pg as pg
from tests.test_rd021_trusted_host_binding import (
    EVIDENCE_BYTES,
    EvidenceProvider,
    HostResolver,
    compiler,
    ingress_codec,
    signed_for,
)

TEXT = "update this company vehicle"
VEHICLE = "8891:S4806251"
FIELD = "實際配備狀態"


class Controlled:
    provider_id = "controlled-test-provider"
    active = True

    def readback(self):
        return {"provider_id": self.provider_id, "status": "BOUND" if self.active else "UNBOUND",
                "scope": "CONTROLLED_TEST", "secret": "must-not-leak"}


class Host(Controlled, HostResolver):
    def resolve(self, **kw):
        data = super().resolve(**kw)
        for key in ("current_identity_projection", "dialogue_binding_state"):
            data[key]["issued_at"] = datetime.now(UTC) - timedelta(seconds=5)
            data[key]["valid_until"] = datetime.now(UTC) + timedelta(minutes=4)
        return data


class Receipts(Controlled, EvidenceProvider):
    pass


class Evidence(Controlled):
    value = FieldEvidence(FIELD, _digest("sport"), "fixture:photo", "fixture:root", "VERIFIED",
                          (FIELD,), "LIMITED", "FIRST_OBSERVED_EXTERNAL", "UNKNOWN", "fixture:1", "fixture:1")

    def resolve(self, **kw):
        assert kw == dict(vehicle_instance_id=VEHICLE, field_name=FIELD,
                          value_digest=_digest("sport"), evidence_asset_id="fixture:photo")
        return self.value


class Mutations(Controlled):
    delta = {FIELD: "sport"}

    def compile(self, *, task_id, intent):
        assert intent.vehicle_instance_id == VEHICLE and intent.verified_delta == self.delta
        return CanonicalMutation("controlled:mutation", VEHICLE, 0, self.delta,
                                 (Evidence.value,) if self.delta else (), "controlled:request", task_id)


def bindings():
    codec = ingress_codec()
    class Nonces(Controlled, type(codec.replay_store)):
        pass
    codec.replay_store = Nonces()
    host = TrustedHostTaskCompiler(dispatch_compiler=compiler(), host_state_resolver=Host(),
                                   evidence_provider=Receipts(signed_for(TEXT, delta={FIELD: "sport"})))
    return ConsumerBindings(Mutations(), Evidence(), host, codec)


def settings(dsn="postgresql://unused/controlled"):
    return _test_settings().model_copy(update={"canonical_vehicle_store_mode": "postgres",
                                               "canonical_postgres_dsn": SecretStr(dsn)})


@pytest.mark.parametrize("missing", [
    "mutation", "evidence", "host", "resolver", "receipt", "ingress", "nonce",
])
def test_startup_rejects_incomplete_binding(missing):
    b = bindings()
    if missing in {"mutation", "evidence", "host", "ingress"}:
        b = replace(b, **{missing: None})
    elif missing == "receipt":
        b.host.evidence_provider = None
    elif missing == "resolver":
        b.host.host_state_resolver = None
    else:
        b.ingress.replay_store = None
    with pytest.raises(RuntimeError, match="CANONICAL_STORE_BINDING_INCOMPLETE"):
        configured_application(settings=settings(), bindings=b, binding_scope="CONTROLLED_TEST")


def test_test_providers_cannot_satisfy_production_startup():
    with pytest.raises(RuntimeError, match="CANONICAL_STORE_BINDING_INCOMPLETE"):
        configured_application(settings=settings(), bindings=bindings())
    report = binding_readback(settings(), bindings(), "CONTROLLED_TEST")
    assert report["ready"] and "must-not-leak" not in str(report)


@pytest.fixture(params=["sqlite", "postgres"])
def composed(request, tmp_path, monkeypatch):
    b = bindings()
    if request.param == "postgres":
        dsn, _, _ = request.getfixturevalue("pg")
        store = TransactionalVehicleStore.postgres_candidate(dsn, evidence_admission=b.evidence)
    else:
        path = tmp_path / "controlled.sqlite"
        with sqlite3.connect(path) as c:
            sqlite_contract_schema(c)
        store = TransactionalVehicleStore(lambda: sqlite3.connect(path), dialect="sqlite_test",
                                           evidence_admission=b.evidence)
        dsn = "postgresql://unused/controlled"
        monkeypatch.setattr(TransactionalVehicleStore, "postgres_candidate", lambda *a, **kw: store)
    raw = creative_workbook()
    manifest = compile_import(raw, file_id=CANONICAL_WORKBENCH_FILE_ID)
    import_fixed_preimage(store, raw, manifest)
    declare_db_canonical(store, manifest)
    app = configured_application(repo_root=_copy_authority_repo(tmp_path), settings=settings(dsn),
                                 bindings=b, binding_scope="CONTROLLED_TEST")
    return app, b, store


def dispatch(app, b, *, token=None, task=None):
    return dispatch_verified_host_task_from_headers(
        app, {"task": task or {"request_text": TEXT, "intent": "sales_human"}},
        {"Authorization": "Bearer " + (token or issue(b.ingress, request_text=TEXT))})


@pytest.mark.parametrize("drop_terminal", [False, True])
def test_controlled_executor_consumes_actual_dispatcher_result(composed, monkeypatch, drop_terminal):
    app, bindings_set, _ = composed
    if drop_terminal:
        monkeypatch.setattr(app.dispatcher, "_complete_company_commercial", lambda _contract: None)

    class InProcessResponses:
        def create(self, **request):
            tool = request["tools"][0]
            payload = {"task": {"request_text": TEXT, "intent": "sales_human"}}
            actual = dispatch_verified_host_task_from_headers(
                app, payload, {"Authorization": "Bearer " + tool["authorization"]},
            )
            if not drop_terminal:
                assert actual.get("persistence_receipt"), actual
            self.actual = actual
            return {"output": [{"type": "mcp_call", "server_label": "global_hybrid_v2",
                                "name": "dispatch_verified_host_task", "error": None,
                                "arguments": json.dumps({"payload": payload}),
                                "output": json.dumps(actual)}],
                    "output_text": "Sales task completed after persistence."}

    ingress = ControlledSalesIngress(
        classifier=Classifier(IngressTaskClass.COMPANY_COMMERCIAL_MATCHING),
        token_codec=bindings_set.ingress,
        responses_adapter=ForcedHostDispatchAdapter(mcp_server_url="https://mcp.example/mcp"),
    )
    transport = InProcessResponses()
    outcome = ControlledSalesCompletionExecutor(ingress=ingress, responses=transport).execute(
        turn=ServerTurnContext("c1", "7"), request_text=TEXT, intent="sales_human",
        raw_evidence=EVIDENCE_BYTES,
    )
    if drop_terminal:
        assert outcome.state == FAILURE and outcome.user_visible_text is None
    else:
        assert outcome.state == "WRITE_AND_READBACK_PASS"
        assert outcome.user_visible_text == "Sales task completed after persistence."


@pytest.mark.parametrize("no_delta", [False, True])
def test_controlled_commit_readback_before_eligible_response(composed, no_delta):
    app, b, store = composed
    if no_delta:
        b.mutation.delta = {}
        b.host.evidence_provider.value = signed_for(TEXT, delta={})
    out = dispatch(app, b)
    assert out["status"] == "COMPANY_COMMERCIAL_DELTA_VERIFIED", out
    assert out["persistence_receipt"]["state"] == ("NO_DELTA" if no_delta else "WRITE_AND_READBACK_PASS")
    fresh = store.read_vehicle(VEHICLE)
    assert fresh.revision == (0 if no_delta else 1)
    assert fresh.verified_state == ({} if no_delta else {FIELD: "sport"})
    assert consumer_readiness(app)["ready"]
    b.evidence.active = False
    assert not consumer_readiness(app)["ready"]


def test_ready_endpoint_reports_lost_binding_without_secrets(composed):
    from starlette.testclient import TestClient

    from global_hybrid_v2.adapters.mcp_server import create_mcp_server

    app, b, _ = composed
    server = create_mcp_server(app)
    with TestClient(server.streamable_http_app(stateless_http=True, json_response=True)) as client:
        response = client.get("/ready")
        assert response.status_code == 200
        assert response.json()["binding_scope"] == "CONTROLLED_TEST"
        assert response.json()["bindings"]["completion_fence"]["status"] == "BOUND"
        b.evidence.active = False
        response = client.get("/ready")
        assert response.status_code == 503 and response.json()["ready"] is False
        assert "must-not-leak" not in response.text and "postgresql://" not in response.text


@pytest.mark.parametrize("failure", ["invalid_token", "stale_token", "injection", "commit", "readback",
                                     "missing_receipt", "host_resolver", "evidence_receipt"])
def test_controlled_failure_never_serializes_completion(composed, monkeypatch, failure):
    app, b, store = composed
    read_vehicle = store.read_vehicle
    task, token = None, None
    if failure == "invalid_token":
        token = "invalid"
    elif failure == "stale_token":
        token = issue(b.ingress, request_text=TEXT, now=datetime.now(UTC)-timedelta(minutes=6))
    elif failure == "injection":
        task = {"request_text": TEXT, "intent": "sales_human", "workbench_sync_intent": {}}
    elif failure == "host_resolver":
        b.host.host_state_resolver = None
    elif failure == "evidence_receipt":
        b.host.evidence_provider = None
    elif failure == "missing_receipt":
        monkeypatch.setattr(app.dispatcher, "dispatch", lambda *a, **kw:
                            DomainResult(owner=Owner.SALES_HUMAN, status="COMPANY_COMMERCIAL_DELTA_VERIFIED"))
    elif failure == "commit":
        with store._open() as connection:
            if store.dialect == "postgres":
                connection.execute("CREATE FUNCTION g1a_fail() RETURNS trigger LANGUAGE plpgsql AS $$ "
                                   "BEGIN RAISE EXCEPTION 'injected'; END; $$")
                connection.execute("CREATE TRIGGER g1a_fail BEFORE INSERT ON vehicle_mutation "
                                   "FOR EACH ROW EXECUTE FUNCTION g1a_fail()")
            else:
                connection.execute("CREATE TRIGGER g1a_fail BEFORE INSERT ON vehicle_mutation "
                                   "BEGIN SELECT RAISE(ABORT, 'injected'); END")
    else:
        def broken(*a, **kw):
            raise OSError("controlled failure")
        # Same class patch affects the separately composed PostgreSQL store instance.
        monkeypatch.setattr(TransactionalVehicleStore,
                            "commit_verified" if failure == "commit" else "read_vehicle", broken)
    out = dispatch(app, b, token=token, task=task)
    assert out["status"] == "NO_SERIALIZE / EXECUTION_FAIL"
    assert read_vehicle(VEHICLE).revision == (1 if failure == "readback" else 0)
