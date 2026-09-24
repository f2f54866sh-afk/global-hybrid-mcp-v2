from __future__ import annotations

import hashlib
import hmac


class RenderVehicleReconciliationEndpoint:
    def __init__(self, *, shared_secret: str, reconcile):
        if not shared_secret:
            raise ValueError("shared secret required")
        self._secret = shared_secret.encode()
        self._reconcile = reconcile

    def handle(self, *, body: bytes, signature: str) -> dict:
        expected = hmac.new(self._secret, body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            return {"status": "REJECTED", "blocker": "CONTROL_AUTH_REQUIRED"}
        if body != b'{"operation":"vehicle-knowledge-reconcile"}':
            return {"status": "REJECTED", "blocker": "CONTROL_TARGET_OVERRIDE_REJECTED"}
        return self._reconcile()
