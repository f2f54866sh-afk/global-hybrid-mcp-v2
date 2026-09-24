from __future__ import annotations

import hashlib
import hmac
import json
import re
from datetime import datetime


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
        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {"status": "REJECTED", "blocker": "CONTROL_TARGET_OVERRIDE_REJECTED"}
        if set(payload) != {"operation", "run_id", "scheduled_at"}:
            return {"status": "REJECTED", "blocker": "CONTROL_TARGET_OVERRIDE_REJECTED"}
        run_id = payload.get("run_id")
        scheduled_at = payload.get("scheduled_at")
        if payload.get("operation") != "vehicle-knowledge-reconcile" or not isinstance(run_id, str):
            return {"status": "REJECTED", "blocker": "SCHEDULER_RUN_ID_REQUIRED"}
        if not isinstance(scheduled_at, str) or not re.fullmatch(r"cf-[0-9]{13}", run_id):
            return {"status": "REJECTED", "blocker": "SCHEDULER_RUN_ID_REQUIRED"}
        try:
            scheduled = datetime.fromisoformat(scheduled_at.replace("Z", "+00:00"))
            expected_run_id = f"cf-{int(scheduled.timestamp() * 1000)}"
        except ValueError:
            return {"status": "REJECTED", "blocker": "SCHEDULER_RUN_ID_REQUIRED"}
        if run_id != expected_run_id:
            return {"status": "REJECTED", "blocker": "SCHEDULER_RUN_BINDING_MISMATCH"}
        return self._reconcile()
