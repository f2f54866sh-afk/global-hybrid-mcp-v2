from __future__ import annotations

import hashlib
import io
import json
from dataclasses import replace
from pathlib import Path

import pytest

from global_hybrid_v2.creative_schema_migration import CreativeSchemaMigrationRunner
from global_hybrid_v2.media_deployment_sequence import (
    DEPLOYMENT_ORDER,
    DeploymentProgress,
    DeploymentReceiptAuthority,
)
from global_hybrid_v2.media_object_probe import (
    MediaObjectDeploymentProbeHttp,
    MediaObjectProbeError,
    MediaObjectProbeReceipt,
)
from global_hybrid_v2.media_schema_contract import (
    D1MediaMigrationContract,
    D1MediaSchemaReadbackHttp,
    D1MigrationReceipt,
    D1MigrationState,
)
from global_hybrid_v2.settings import MediaCapabilityDebt, Settings

DEPLOYMENT = "isolated001"
TARGET = "staging"
REVISION = "e3db839"
PREIMAGE = "a" * 64


class Response:
    def __init__(self, body):
        self.body = io.BytesIO(body)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.body.read()


def test_probe_uses_disposable_namespace_and_requires_cleanup(monkeypatch):
    raw = b"isolated-r2-probe"
    digest = hashlib.sha256(raw).hexdigest()
    seen = []

    def request(req, timeout):
        body = json.loads(req.data)
        key = body["expected_object_key"]
        seen.append(key)
        assert key.startswith(f"__probe__/rd021/{DEPLOYMENT}/")
        assert not key.startswith("media/sha256/")
        result = {
            "state": "PROBE_PASS", "object_key": key, "raw_sha256": digest,
            "object_size": len(raw), "cleanup_state": "NOT_FOUND",
            "cleanup_readback_digest": hashlib.sha256((key + ":NOT_FOUND").encode()).hexdigest(),
        }
        return Response(json.dumps(result).encode())

    monkeypatch.setattr("global_hybrid_v2.media_object_probe.urlopen", request)
    probe = MediaObjectDeploymentProbeHttp(base_url="https://isolated.example", write_secret="w")
    assert probe.probe(raw, deployment_id=DEPLOYMENT).state == "PROBE_PASS"
    assert probe.probe(raw, deployment_id=DEPLOYMENT).state == "PROBE_PASS"
    assert len(set(seen)) == 2  # each probe gets a new nonce

    def bad_cleanup(req, timeout):
        result = json.loads(request(req, timeout).read())
        result["cleanup_state"] = "PRESENT"
        return Response(json.dumps(result).encode())

    monkeypatch.setattr("global_hybrid_v2.media_object_probe.urlopen", bad_cleanup)
    with pytest.raises(MediaObjectProbeError, match="HOLD_PROBE_CLEANUP_FAILED"):
        probe.probe(raw, deployment_id=DEPLOYMENT)


def test_media_settings_fail_closed_and_sequence_rejects_forgery():
    with pytest.raises(MediaCapabilityDebt, match="INCOMPLETE"):
        Settings().require_media_deployment_bindings()
    valid = Settings(
        media_registry_base_url="https://isolated.example", media_registry_read_secret="r",
        media_registry_write_secret="w", media_r2_binding="MEDIA_BUCKET",
        media_activity_signing_key_ref="MEDIA_ACTIVITY_SIGNING_KEY",
        ingress_turn_signing_key_ref="INGRESS_TURN_SIGNING_KEY",
        expected_control_plane_schema_revision="0002_media_asset",
    )
    valid.require_media_deployment_bindings()
    with pytest.raises(MediaCapabilityDebt, match="R2_BINDING_MISMATCH"):
        valid.model_copy(update={"media_r2_binding": "other"}).require_media_deployment_bindings()
    authority = DeploymentReceiptAuthority(signing_key=b"k" * 32, issuer="server", execution_owner="operator")
    progress = DeploymentProgress(DEPLOYMENT, TARGET, REVISION, PREIMAGE)
    with pytest.raises(ValueError, match="SEQUENCE_CONFLICT"):
        progress.record("PASS", authority=authority)

    # Private minting is used only in this unit test; production issuance is verifier-specific.
    first = authority._seal(
        deployment_id=DEPLOYMENT, step=DEPLOYMENT_ORDER[0], target=TARGET,
        source_revision=REVISION, expected_preimage=PREIMAGE, result_state="READBACK_PASS",
        readback_evidence_digest="b" * 64, previous_step_receipt_digest=None,
    )
    for changed in (
        replace(first, step=DEPLOYMENT_ORDER[1]),
        replace(first, deployment_id="different"),
        replace(first, target="production"),
        replace(first, result_state="READBACK_PASS", signature="0" * 64),
        replace(first, previous_step_receipt_digest="c" * 64),
    ):
        with pytest.raises(ValueError, match="SEQUENCE_CONFLICT"):
            progress.record(changed, authority=authority)
    progress = progress.record(first, authority=authority)
    assert progress.next_step is DEPLOYMENT_ORDER[1]
    forged_progress = replace(progress, receipts=(replace(first, signature="0" * 64),))
    with pytest.raises(ValueError, match="PRIOR_RECEIPT_INVALID"):
        forged_progress.record(first, authority=authority)
    wrong_previous = authority._seal(
        deployment_id=DEPLOYMENT, step=DEPLOYMENT_ORDER[1], target=TARGET,
        source_revision=REVISION, expected_preimage=PREIMAGE, result_state="PROBE_PASS",
        readback_evidence_digest="d" * 64, previous_step_receipt_digest="e" * 64,
    )
    with pytest.raises(ValueError, match="SEQUENCE_CONFLICT"):
        progress.record(wrong_previous, authority=authority)
    failed = authority._seal(
        deployment_id=DEPLOYMENT, step=DEPLOYMENT_ORDER[1], target=TARGET,
        source_revision=REVISION, expected_preimage=PREIMAGE, result_state="HOLD_PROBE_CLEANUP_FAILED",
        readback_evidence_digest="d" * 64, previous_step_receipt_digest=first.digest,
    )
    held = progress.record(failed, authority=authority)
    assert held.next_step is None
    with pytest.raises(ValueError, match="SEQUENCE_CONFLICT"):
        held.record(failed, authority=authority)


def test_only_verified_step_results_can_issue_deployment_receipts(monkeypatch):
    authority = DeploymentReceiptAuthority(signing_key=b"k" * 32, issuer="server", execution_owner="operator")
    common = dict(deployment_id=DEPLOYMENT, target=TARGET, source_revision=REVISION,
                  expected_preimage=PREIMAGE, previous_step_receipt_digest="f" * 64)
    d1 = D1MigrationReceipt(D1MigrationState.APPLIED_READBACK_PASS, "0001", "0002", "a" * 64,
                            schema_fingerprint="b" * 64)
    contract = D1MediaMigrationContract(Path("fixture.sql"), expected_from="0001")
    readback = D1MediaSchemaReadbackHttp(base_url="https://isolated.example", read_secret="r")
    monkeypatch.setattr(readback, "snapshot", lambda: "trusted-readback")
    monkeypatch.setattr(contract, "postmigration", lambda snapshot: d1)
    assert authority.verify(authority.from_d1_postmigration(contract, readback, **common))
    with pytest.raises(ValueError, match="EXECUTOR_INVALID"):
        authority.from_d1_postmigration(object(), readback, **common)
    bad_d1 = replace(d1, state=D1MigrationState.READY)
    monkeypatch.setattr(contract, "postmigration", lambda snapshot: bad_d1)
    with pytest.raises(ValueError, match="NOT_VERIFIED"):
        authority.from_d1_postmigration(contract, readback, **common)
    runner = CreativeSchemaMigrationRunner(None)
    monkeypatch.setattr(runner, "run", lambda *, task_id: pytest.fail("readback attempted a write"))
    with pytest.raises(ValueError, match="EXECUTOR_INVALID"):
        authority.from_xlsx_readback(runner, task_id="schema-test", **common)
    probe = MediaObjectDeploymentProbeHttp(base_url="https://isolated.example", write_secret="w")
    r2 = MediaObjectProbeReceipt("PROBE_PASS", DEPLOYMENT, "__probe__/rd021/test/nonce",
                                 "a" * 64, 1, "d" * 64)
    monkeypatch.setattr(probe, "probe", lambda raw, *, deployment_id: r2)
    assert authority.verify(authority.from_r2_probe(probe, raw=b"x", **common))
    monkeypatch.setattr(probe, "probe", lambda raw, *, deployment_id: replace(r2, state="HOLD"))
    with pytest.raises(ValueError, match="NOT_VERIFIED"):
        authority.from_r2_probe(probe, raw=b"x", **common)
