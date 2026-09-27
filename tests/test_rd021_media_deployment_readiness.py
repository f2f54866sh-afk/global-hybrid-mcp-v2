from __future__ import annotations

import hashlib
import io
import json
from urllib.parse import parse_qs, urlparse

import pytest

from global_hybrid_v2.media_deployment_sequence import DEPLOYMENT_ORDER, DeploymentProgress
from global_hybrid_v2.media_object_probe import MediaObjectDeploymentProbeHttp, MediaObjectProbeError
from global_hybrid_v2.settings import MediaCapabilityDebt, Settings


class Response:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.body.read()


def test_probe_put_get_duplicate_and_tamper(monkeypatch):
    raw = b"isolated-r2-probe"
    digest = hashlib.sha256(raw).hexdigest()
    key = f"media/sha256/{digest}"
    stored = {}
    calls = []

    def request(req, timeout):
        calls.append(req.full_url)
        if req.full_url.endswith("/internal/control/media-object-probe"):
            body = json.loads(req.data)
            assert body["expected_object_key"] == key
            assert body["expected_sha256"] == digest
            state = "IDEMPOTENT_READBACK_PASS" if key in stored else "PUT_GET_READBACK_PASS"
            stored.setdefault(key, raw)
            receipt = {"state": state, "object_key": key, "raw_sha256": digest,
                       "object_size": len(raw)}
            return Response(io.BytesIO(json.dumps(receipt).encode()))
        assert parse_qs(urlparse(req.full_url).query)["object_key"] == [key]
        return Response(io.BytesIO(stored[key]))

    monkeypatch.setattr("global_hybrid_v2.media_object_probe.urlopen", request)
    probe = MediaObjectDeploymentProbeHttp(
        base_url="https://isolated.example", read_secret="r", write_secret="w",
    )
    assert probe.probe(raw).state == "PUT_GET_READBACK_PASS"
    assert probe.probe(raw).state == "IDEMPOTENT_READBACK_PASS"
    stored[key] = b"tampered"
    with pytest.raises(MediaObjectProbeError, match="READBACK_MISMATCH"):
        probe.probe(raw)
    assert len(calls) == 6


def test_media_settings_fail_closed_and_sequence_cannot_skip():
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
    progress = DeploymentProgress()
    with pytest.raises(ValueError, match="SEQUENCE_CONFLICT"):
        progress.record(DEPLOYMENT_ORDER[1], passed=True, receipt="fake")
    progress = progress.record(DEPLOYMENT_ORDER[0], passed=True, receipt="preflight:pass")
    assert progress.next_step is DEPLOYMENT_ORDER[1]
    held = progress.record(DEPLOYMENT_ORDER[1], passed=False, receipt="bucket-unavailable")
    assert held.next_step is None
    with pytest.raises(ValueError, match="SEQUENCE_CONFLICT"):
        held.record(DEPLOYMENT_ORDER[2], passed=True, receipt="fake")
