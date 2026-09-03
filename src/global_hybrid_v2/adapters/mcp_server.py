from __future__ import annotations

import base64
import binascii
import hashlib
import json
import logging
from typing import Any

from mcp.server.mcpserver import MCPServer
from starlette.requests import Request
from starlette.responses import JSONResponse

from global_hybrid_v2.application import Application, create_application
from global_hybrid_v2.contracts import TaskRequest
from global_hybrid_v2.governance.authority import AUTHORITY_ACTIVATION_INVALID, AuthorityError

logger = logging.getLogger(__name__)


def _decoded_sha256(value: Any, *, expected_length: int) -> str:
    if not isinstance(value, str):
        return "UNAVAILABLE"
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, UnicodeError, binascii.Error):
        return "INVALID"
    if len(decoded) != expected_length:
        return "INVALID"
    return hashlib.sha256(decoded).hexdigest()


def _authority_verification_fingerprints(application: Application) -> dict[str, str]:
    registry_path = application.authority.registry_path
    try:
        registry_sha256 = hashlib.sha256(registry_path.read_bytes()).hexdigest()
    except OSError:
        registry_sha256 = "UNAVAILABLE"

    activation: dict[str, Any] = {}
    try:
        loaded_activation = json.loads(
            (registry_path.parent / "activation.json").read_text(encoding="utf-8")
        )
        if isinstance(loaded_activation, dict):
            activation = loaded_activation
    except (OSError, UnicodeError, json.JSONDecodeError):
        pass

    trusted_key_id = application.authority.trusted_key_id
    activation_key_id = activation.get("key_id")
    return {
        "registry_raw_sha256": registry_sha256,
        "trusted_public_key_raw_sha256": _decoded_sha256(
            application.authority.trusted_public_key,
            expected_length=32,
        ),
        "activation_signature_raw_sha256": _decoded_sha256(
            activation.get("signature"),
            expected_length=64,
        ),
        "trusted_key_id": trusted_key_id if isinstance(trusted_key_id, str) else "UNSET",
        "activation_key_id": (
            activation_key_id if isinstance(activation_key_id, str) else "UNAVAILABLE"
        ),
        "registry_path": str(registry_path),
    }


def create_mcp_server(application: Application) -> MCPServer:
    server = MCPServer("GLOBAL Hybrid v2")

    @server.custom_route("/health", methods=["GET"])
    async def health(_: Request) -> JSONResponse:
        return JSONResponse(
            {
                "ok": True,
                "service": "GLOBAL Hybrid v2",
                "live_execution": application.settings.live_execution,
            }
        )

    @server.custom_route("/ready", methods=["GET"])
    async def ready(_: Request) -> JSONResponse:
        try:
            snapshot = application.authority.resolve()
        except AuthorityError as exc:
            fingerprints = _authority_verification_fingerprints(application)
            logger.exception(
                "Authority readiness check failed; "
                "registry_raw_sha256=%s; "
                "trusted_public_key_raw_sha256=%s; "
                "activation_signature_raw_sha256=%s; "
                "trusted_key_id=%r; activation_key_id=%r; registry_path=%r",
                fingerprints["registry_raw_sha256"],
                fingerprints["trusted_public_key_raw_sha256"],
                fingerprints["activation_signature_raw_sha256"],
                fingerprints["trusted_key_id"],
                fingerprints["activation_key_id"],
                fingerprints["registry_path"],
            )
            failure_code = (
                AUTHORITY_ACTIVATION_INVALID
                if str(exc) == AUTHORITY_ACTIVATION_INVALID
                else "AUTHORITY_RESOLUTION_FAILED"
            )
            return JSONResponse(
                {
                    "ready": False,
                    "failure_code": failure_code,
                },
                status_code=503,
            )
        return JSONResponse(
            {
                "ready": True,
                "resolved_owners": [owner.value for owner in snapshot.entries],
                "runtime": application.runtime_identity.model_dump(),
            }
        )

    @server.tool()
    def validate_task(payload: dict) -> dict:
        """Validate the TaskRequest schema only. Does not execute domain work."""
        request = TaskRequest.model_validate(payload)
        return {
            "valid": True,
            "intent": request.intent.value,
            "effects": [effect.value for effect in request.effects],
            "context_items": len(request.context),
        }

    @server.tool()
    def dispatch_task(payload: dict) -> dict:
        """Dispatch a task through the authoritative governance runtime."""
        request = TaskRequest.model_validate(payload)
        result = application.dispatcher.dispatch(request)
        return result.model_dump(mode="json")

    @server.tool()
    def dispatch_host_task(payload: dict) -> dict:
        """Dispatch one stateless task with its current Host identity projection."""
        request = TaskRequest.model_validate(payload)
        result = application.dispatcher.dispatch(request, require_host_projection=True)
        return result.model_dump(mode="json")

    return server


application = create_application()
mcp = create_mcp_server(application)


def main() -> None:
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=application.settings.port,
        stateless_http=True,
        json_response=True,
    )


if __name__ == "__main__":
    main()
