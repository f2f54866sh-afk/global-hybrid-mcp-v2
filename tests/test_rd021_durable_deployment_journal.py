from __future__ import annotations

import json
from dataclasses import replace
from io import BytesIO

import pytest

from global_hybrid_v2.durable_deployment_journal import (
    DeploymentJournalError,
    DurableDeploymentJournal,
    R2JournalHttpStore,
)
from global_hybrid_v2.media_deployment_sequence import (
    DEPLOYMENT_ORDER,
    DeploymentReceiptAuthority,
)

DEPLOYMENT = "isolated001"


class MemoryR2:
    def __init__(self):
        self.objects = {}
        self.version = 0

    def get(self, deployment_id, key):
        return self.objects.get(key)

    def list_receipts(self, deployment_id):
        prefix = f"__deployment__/rd021/{deployment_id}/receipts/"
        return [key for key in self.objects if key.startswith(prefix)]

    def _write(self, key, raw):
        self.version += 1
        etag = f"etag-{self.version}"
        self.objects[key] = (raw, etag)
        return etag

    def put_immutable(self, deployment_id, key, raw):
        found = self.objects.get(key)
        if found:
            if found[0] == raw:
                return found[1]
            raise DeploymentJournalError("HOLD_DEPLOYMENT_JOURNAL_COLLISION")
        return self._write(key, raw)

    def cas_head(self, deployment_id, key, raw, expected_etag):
        found = self.objects.get(key)
        if (found[1] if found else None) != expected_etag:
            raise DeploymentJournalError("HOLD_DEPLOYMENT_JOURNAL_CAS_CONFLICT")
        return self._write(key, raw)


def setup():
    store = MemoryR2()
    authority = DeploymentReceiptAuthority(signing_key=b"s" * 32, issuer="server", execution_owner="operator")
    journal = DurableDeploymentJournal(store, authority)
    common = dict(deployment_id=DEPLOYMENT, target="staging", source_revision="37a09cd",
                  expected_preimage="a" * 64)
    preflight = authority._seal(
        **common, step=DEPLOYMENT_ORDER[0], result_state="READBACK_PASS",
        readback_evidence_digest="b" * 64, previous_step_receipt_digest=None,
    )
    probe = authority._seal(
        **common, step=DEPLOYMENT_ORDER[1], result_state="PROBE_PASS",
        readback_evidence_digest="c" * 64, previous_step_receipt_digest=preflight.digest,
    )
    return store, authority, journal, preflight, probe, common


def test_bootstrap_readback_restart_and_exact_next_step():
    store, authority, journal, preflight, probe, _ = setup()
    with pytest.raises(DeploymentJournalError, match="JOURNAL_INVALID"):
        journal.require_d1_admissible(DEPLOYMENT)
    first = journal.bootstrap(preflight, probe)
    assert first.next_step is DEPLOYMENT_ORDER[2]
    assert len(store.list_receipts(DEPLOYMENT)) == 2
    assert all(key.startswith(f"__deployment__/rd021/{DEPLOYMENT}/receipts/")
               for key in store.list_receipts(DEPLOYMENT))
    restarted = DurableDeploymentJournal(store, authority)
    assert restarted.load(DEPLOYMENT).next_step is DEPLOYMENT_ORDER[2]
    assert restarted.require_d1_admissible(DEPLOYMENT).head.state == "ACTIVE"
    assert journal.load(DEPLOYMENT).head.latest_receipt_digest == probe.digest
    key = journal._receipt_key(preflight, 0)
    same = store.put_immutable(DEPLOYMENT, key, journal._receipt_bytes(preflight))
    assert same == store.get(DEPLOYMENT, key)[1]
    with pytest.raises(DeploymentJournalError, match="COLLISION"):
        store.put_immutable(DEPLOYMENT, key, b"different")
    assert first.progress.next_step is DEPLOYMENT_ORDER[2]


def test_missing_middle_forged_receipt_and_head_scope_tamper_hold():
    store, authority, journal, preflight, probe, _ = setup()
    journal.bootstrap(preflight, probe)
    middle = journal._receipt_key(preflight, 0)
    saved = store.objects.pop(middle)
    with pytest.raises(DeploymentJournalError, match="JOURNAL_INVALID"):
        journal.load(DEPLOYMENT)
    store.objects[middle] = saved
    store.objects[middle] = (journal._receipt_bytes(replace(preflight, signature="0" * 64)), saved[1])
    with pytest.raises(DeploymentJournalError, match="JOURNAL_INVALID"):
        journal.load(DEPLOYMENT)
    store.objects[middle] = saved
    head_key = f"__deployment__/rd021/{DEPLOYMENT}/head.json"
    head_raw, etag = store.objects[head_key]
    for changed in ({"target": "production"}, {"source_revision": "changed"},
                    {"expected_preimage": "0" * 64}):
        body = {**json.loads(head_raw), **changed}
        store.objects[head_key] = (json.dumps(body).encode(), etag)
        with pytest.raises(DeploymentJournalError, match="JOURNAL_INVALID"):
            journal.load(DEPLOYMENT)
    store.objects[head_key] = (head_raw, etag)
    extra = f"__deployment__/rd021/{DEPLOYMENT}/receipts/01-UNKNOWN-{'0' * 64}.json"
    store.objects[extra] = (b"{}", "etag-extra")
    with pytest.raises(DeploymentJournalError, match="JOURNAL_INVALID"):
        journal.load(DEPLOYMENT)
    del store.objects[extra]


def test_hold_survives_restart_and_cas_conflict_prevents_overwrite():
    store, authority, journal, preflight, probe, _ = setup()
    journal.bootstrap(preflight, probe)
    loaded = journal.hold_exception(DEPLOYMENT, RuntimeError("D1_SCHEMA_CONFLICT"))
    assert loaded.head.state == "HOLD"
    assert loaded.next_step is None
    restarted = DurableDeploymentJournal(store, authority)
    assert restarted.load(DEPLOYMENT).head.hold_reason == "HOLD_RUNTIMEERROR"
    with pytest.raises(DeploymentJournalError, match="STEP_NOT_ADMISSIBLE"):
        restarted.hold_exception(DEPLOYMENT, RuntimeError("retry"))
    head_key = f"__deployment__/rd021/{DEPLOYMENT}/head.json"
    with pytest.raises(DeploymentJournalError, match="CAS_CONFLICT"):
        store.cas_head(DEPLOYMENT, head_key, b"stale", "old-etag")


def test_bootstrap_wrong_chain_or_collision_cannot_admit_d1():
    store, authority, journal, preflight, probe, _ = setup()
    with pytest.raises(DeploymentJournalError, match="JOURNAL_INVALID"):
        journal.bootstrap(preflight, replace(probe, previous_step_receipt_digest="f" * 64))
    assert not store.objects
    store.put_immutable(DEPLOYMENT, journal._receipt_key(preflight, 0), b"collision")
    with pytest.raises(DeploymentJournalError, match="COLLISION"):
        journal.bootstrap(preflight, probe)
    with pytest.raises(DeploymentJournalError, match="JOURNAL_INVALID"):
        journal.require_d1_admissible(DEPLOYMENT)


def test_competing_head_cas_creates_fail_closed_orphan(monkeypatch):
    store, authority, journal, preflight, probe, common = setup()
    journal.bootstrap(preflight, probe)
    next_receipt = authority._seal(
        **common, step=DEPLOYMENT_ORDER[2], result_state="READBACK_PASS",
        readback_evidence_digest="d" * 64, previous_step_receipt_digest=probe.digest,
    )
    monkeypatch.setattr(store, "cas_head", lambda *args: (_ for _ in ()).throw(
        DeploymentJournalError("HOLD_DEPLOYMENT_JOURNAL_CAS_CONFLICT")))
    with pytest.raises(DeploymentJournalError, match="CAS_CONFLICT"):
        journal.append(next_receipt)
    with pytest.raises(DeploymentJournalError, match="JOURNAL_INVALID"):
        journal.load(DEPLOYMENT)


def test_http_store_conditional_write_get_and_list_readback(monkeypatch):
    backing = MemoryR2()

    class Response:
        def __init__(self, result):
            self.body = BytesIO(json.dumps(result).encode())

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return self.body.read()

    def urlopen(request, timeout):
        body = json.loads(request.data)
        deployment_id, operation = body["deployment_id"], body["operation"]
        if operation == "LIST":
            return Response({"state": "LIST", "keys": backing.list_receipts(deployment_id)})
        key = body["key"]
        if operation == "GET":
            found = backing.get(deployment_id, key)
            if not found:
                return Response({"state": "MISS", "key": key})
            import base64
            return Response({"state": "HIT", "key": key, "etag": found[1],
                             "raw_base64": base64.b64encode(found[0]).decode()})
        import base64
        raw = base64.b64decode(body["raw_base64"])
        try:
            if operation == "PUT_IMMUTABLE":
                if backing.get(deployment_id, key):
                    return Response({"state": "CAS_CONFLICT", "key": key})
                etag = backing.put_immutable(deployment_id, key, raw)
            else:
                etag = backing.cas_head(deployment_id, key, raw, body.get("expected_etag"))
        except DeploymentJournalError:
            return Response({"state": "CAS_CONFLICT", "key": key})
        return Response({"state": "PUT_READBACK_PASS", "key": key, "etag": etag})

    monkeypatch.setattr("global_hybrid_v2.durable_deployment_journal.urlopen", urlopen)
    store = R2JournalHttpStore(base_url="https://isolated.example", write_secret="w")
    _, authority, _, preflight, probe, _ = setup()
    journal = DurableDeploymentJournal(store, authority)
    journal.bootstrap(preflight, probe)
    restarted = DurableDeploymentJournal(store, authority)
    assert restarted.require_d1_admissible(DEPLOYMENT).next_step is DEPLOYMENT_ORDER[2]
    key = journal._receipt_key(preflight, 0)
    assert store.put_immutable(DEPLOYMENT, key, journal._receipt_bytes(preflight))
    with pytest.raises(DeploymentJournalError, match="COLLISION"):
        store.put_immutable(DEPLOYMENT, key, b"collision")
