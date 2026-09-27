"""Explicit R2 binding probe; callers choose an isolated/staging endpoint."""
from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


class MediaObjectProbeError(RuntimeError):
    pass


@dataclass(frozen=True)
class MediaObjectProbeReceipt:
    state: str
    object_key: str
    raw_sha256: str
    object_size: int


class MediaObjectDeploymentProbeHttp:
    def __init__(self, *, base_url: str, read_secret: str, write_secret: str) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme != "https" or not parsed.hostname or not read_secret or not write_secret:
            raise MediaObjectProbeError("MEDIA_PROBE_BINDING_INCOMPLETE")
        self.base_url = base_url.rstrip("/")
        self.read_secret = read_secret
        self.write_secret = write_secret

    def probe(self, raw: bytes) -> MediaObjectProbeReceipt:
        if not raw:
            raise MediaObjectProbeError("MEDIA_PROBE_RAW_REQUIRED")
        digest = hashlib.sha256(raw).hexdigest()
        key = f"media/sha256/{digest}"
        request = Request(
            self.base_url + "/internal/control/media-object-probe",
            data=json.dumps({
                "raw_base64": base64.b64encode(raw).decode(),
                "expected_sha256": digest,
                "expected_object_key": key,
            }).encode(),
            headers={"Authorization": f"Bearer {self.write_secret}",
                     "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=10) as response:
                result = json.load(response)
            if (result.get("state") not in {"PUT_GET_READBACK_PASS", "IDEMPOTENT_READBACK_PASS"}
                or result.get("object_key") != key or result.get("raw_sha256") != digest
                or result.get("object_size") != len(raw)):
                raise MediaObjectProbeError("MEDIA_PROBE_RECEIPT_INVALID")
            read = Request(
                self.base_url + "/internal/media-object/read?" + urlencode({"object_key": key}),
                headers={"Authorization": f"Bearer {self.read_secret}"},
            )
            with urlopen(read, timeout=10) as response:
                found = response.read()
        except MediaObjectProbeError:
            raise
        except Exception as exc:
            raise MediaObjectProbeError("MEDIA_PROBE_UNAVAILABLE") from exc
        if found != raw or len(found) != len(raw) or hashlib.sha256(found).hexdigest() != digest:
            raise MediaObjectProbeError("MEDIA_PROBE_READBACK_MISMATCH")
        return MediaObjectProbeReceipt(result["state"], key, digest, len(raw))
