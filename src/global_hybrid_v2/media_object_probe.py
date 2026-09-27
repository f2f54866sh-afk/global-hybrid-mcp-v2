"""Disposable R2 capability probe through the server-owned Worker control endpoint."""
from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
from dataclasses import dataclass
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class MediaObjectProbeError(RuntimeError):
    pass


@dataclass(frozen=True)
class MediaObjectProbeReceipt:
    state: str
    deployment_id: str
    object_key: str
    raw_sha256: str
    object_size: int
    cleanup_readback_digest: str


class MediaObjectDeploymentProbeHttp:
    def __init__(self, *, base_url: str, write_secret: str) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme != "https" or not parsed.hostname or not write_secret:
            raise MediaObjectProbeError("MEDIA_PROBE_BINDING_INCOMPLETE")
        self.base_url = base_url.rstrip("/")
        self.write_secret = write_secret

    def probe(self, raw: bytes, *, deployment_id: str) -> MediaObjectProbeReceipt:
        if not raw or not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", deployment_id):
            raise MediaObjectProbeError("MEDIA_PROBE_SCOPE_INVALID")
        digest = hashlib.sha256(raw).hexdigest()
        nonce = secrets.token_hex(16)
        key = f"__probe__/rd021/{deployment_id}/{nonce}"
        request = Request(
            self.base_url + "/internal/control/media-object-probe",
            data=json.dumps({
                "raw_base64": base64.b64encode(raw).decode(),
                "expected_sha256": digest,
                "expected_object_key": key,
                "deployment_id": deployment_id,
                "nonce": nonce,
            }).encode(),
            headers={"Authorization": f"Bearer {self.write_secret}",
                     "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=10) as response:
                result = json.load(response)
        except Exception as exc:
            raise MediaObjectProbeError("HOLD_PROBE_CLEANUP_FAILED_OR_UNAVAILABLE") from exc
        cleanup_digest = hashlib.sha256((key + ":NOT_FOUND").encode()).hexdigest()
        if (result.get("state") != "PROBE_PASS" or result.get("object_key") != key
            or result.get("raw_sha256") != digest or result.get("object_size") != len(raw)
            or result.get("cleanup_state") != "NOT_FOUND"
            or result.get("cleanup_readback_digest") != cleanup_digest):
            raise MediaObjectProbeError("HOLD_PROBE_CLEANUP_FAILED")
        return MediaObjectProbeReceipt("PROBE_PASS", deployment_id, key, digest, len(raw), cleanup_digest)
