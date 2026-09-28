from __future__ import annotations

import base64
import binascii
import hashlib
import json
import logging
from collections.abc import Callable
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.context import Context
from starlette.requests import Request
from starlette.responses import JSONResponse

from global_hybrid_v2.application import Application
from global_hybrid_v2.company_commercial_completion import CANONICAL_WORKBENCH_FILE_ID
from global_hybrid_v2.contracts import PersistenceDisposition, PersistenceReceipt, TaskRequest
from global_hybrid_v2.domains.vehicle_configuration import VehicleConfigurationReadbackProvider
from global_hybrid_v2.governance.authority import AUTHORITY_ACTIVATION_INVALID, AuthorityError
from global_hybrid_v2.ingress_admission import IngressAdmissionError, IngressTaskClass, IngressTurnBinding
from global_hybrid_v2.render_vehicle_control import RenderVehicleReconciliationEndpoint
from global_hybrid_v2.runtime_composition import configured_application, consumer_readiness
from global_hybrid_v2.trusted_workbench_intent import (
    CallerTask,
    HostBindingCapabilityDebt,
    TrustBoundaryError,
)
from global_hybrid_v2.vehicle_reconciliation import configured_vehicle_reconciliation

logger = logging.getLogger(__name__)
_FORBIDDEN_WORKBENCH_FIELDS = frozenset({
    "persistence_receipt", "verified_delta", "workbench_sync_intent",
    "company_commercial_matching",
})


def _caller_workbench_authority_blocked(payload: dict) -> bool:
    return any(
        payload.get(key) not in (None, False)
        for key in _FORBIDDEN_WORKBENCH_FIELDS
    )


def _ingress_block(
    blocker: str,
    *,
    binding: IngressTurnBinding | None = None,
    state: PersistenceDisposition = PersistenceDisposition.PERSISTENCE_CAPABILITY_DEBT,
) -> dict:
    result = {"status": "NO_SERIALIZE / EXECUTION_FAIL", "blocker": blocker}
    if binding is not None and binding.task_class is IngressTaskClass.COMPANY_COMMERCIAL_MATCHING:
        receipt = PersistenceReceipt(
            state=state,
            task_id=f"ingress:{binding.nonce}",
            file_id=CANONICAL_WORKBENCH_FILE_ID,
            blocker=blocker,
        )
        result["persistence_receipt"] = receipt.model_dump(mode="json")
    return result


def dispatch_verified_host_task_from_headers(
    application: Application,
    payload: dict,
    headers: dict[str, str] | None,
) -> dict:
    """Transport Authorization, never a model argument, owns turn identity and class."""
    if not isinstance(payload, dict) or set(payload) != {"task"}:
        return _ingress_block("HOST_TASK_PAYLOAD_INVALID")
    try:
        caller = CallerTask.model_validate(payload["task"])
    except (ValueError, TypeError):
        return _ingress_block("TRUSTED_HOST_INPUT_INVALID")
    codec = getattr(application, "ingress_token_codec", None)
    if codec is None:
        return _ingress_block("INGRESS_ADMISSION_UNAVAILABLE")
    matches = [value for key, value in (headers or {}).items() if key.lower() == "authorization"]
    if len(matches) != 1:
        return _ingress_block("INGRESS_AUTHORIZATION_MISSING")
    try:
        binding = codec.verify_authorization(
            matches[0], request_text=caller.request_text, intent=caller.intent,
        )
    except IngressAdmissionError as exc:
        return _ingress_block(str(exc))
    compiler = getattr(application, "trusted_host_task_compiler", None)
    if compiler is None:
        return _ingress_block("TRUSTED_HOST_BINDING_UNAVAILABLE", binding=binding)
    try:
        compiled = compiler.compile_admitted(caller_task=caller, binding=binding)
        request = TaskRequest.model_validate({
            "request_text": caller.request_text, "intent": caller.intent,
        })
    except HostBindingCapabilityDebt as exc:
        return _ingress_block(str(exc), binding=binding)
    except TrustBoundaryError as exc:
        return _ingress_block(
            str(exc), binding=binding, state=PersistenceDisposition.HOLD_CONFLICT,
        )
    except (ValueError, TypeError):
        return _ingress_block("TRUSTED_HOST_INPUT_INVALID", binding=binding)
    except Exception:
        return _ingress_block("TRUSTED_HOST_PROVIDER_FAILURE", binding=binding)
    try:
        result = application.dispatcher.dispatch(request, trusted_host_dispatch=compiled)
    except Exception:
        return _ingress_block("TRUSTED_HOST_DISPATCH_FAILURE", binding=binding)
    if binding.task_class is IngressTaskClass.COMPANY_COMMERCIAL_MATCHING:
        if result.persistence_receipt is None:
            return _ingress_block("PERSISTENCE_TERMINAL_RECEIPT_MISSING", binding=binding)
        if result.persistence_receipt.state not in {
            PersistenceDisposition.WRITE_AND_READBACK_PASS,
            PersistenceDisposition.NO_DELTA,
        } and result.status != "NO_SERIALIZE / EXECUTION_FAIL":
            return _ingress_block(
                "PERSISTENCE_TERMINAL_NOT_ELIGIBLE", binding=binding,
                state=result.persistence_receipt.state,
            )
        # The MCP result itself must bind the Dispatcher task to the verified Host turn.
        result = result.model_copy(update={"turn_contract": {
            **(result.turn_contract or {}),
            "task_id": result.persistence_receipt.task_id,
            "conversation_id": binding.conversation_id,
            "turn_id": binding.turn_id,
            "request_digest": binding.request_digest,
        }})
    return result.model_dump(mode="json")


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
        loaded_activation = json.loads((registry_path.parent / "activation.json").read_text(encoding="utf-8"))
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
        "activation_key_id": (activation_key_id if isinstance(activation_key_id, str) else "UNAVAILABLE"),
        "registry_path": str(registry_path),
    }


def create_mcp_server(
    application: Application,
    *,
    vehicle_reconciliation: Callable[[], dict] | None = None,
) -> MCPServer:
    server = MCPServer("GLOBAL Hybrid v2")
    reconciliation_endpoint = None
    settings = getattr(application, "settings", None)
    secret = getattr(settings, "vehicle_reconciliation_shared_secret", None)
    if secret is not None and vehicle_reconciliation is not None:
        reconciliation_endpoint = RenderVehicleReconciliationEndpoint(
            shared_secret=secret.get_secret_value(),
            reconcile=vehicle_reconciliation,
        )

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
        consumer = consumer_readiness(application)
        if not consumer["ready"]:
            return JSONResponse({**consumer, "failure_code": "CANONICAL_STORE_BINDING_INCOMPLETE"},
                                status_code=503)
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
        payload = {
            **consumer,
            "ready": True,
            "resolved_owners": [owner.value for owner in snapshot.entries],
            "runtime": application.runtime_identity.model_dump(),
        }
        provider = application.vehicle_configuration_provider
        if isinstance(provider, VehicleConfigurationReadbackProvider):
            payload["vehicle_configuration_provider"] = provider.readback().model_dump(mode="json")
        elif provider is not None:
            payload["vehicle_configuration_provider"] = {
                "provider_id": getattr(provider, "provider_id", type(provider).__name__),
                "provider_version": getattr(provider, "provider_version", "UNAVAILABLE"),
                "snapshot_id": getattr(provider, "snapshot_id", None),
                "source_revision": getattr(provider, "source_revision", None),
                "generated_at": getattr(provider, "generated_at", None),
                "active": True,
            }
        return JSONResponse(payload)

    @server.custom_route("/internal/vehicle-knowledge/reconcile", methods=["POST"])
    async def vehicle_knowledge_reconcile(request: Request) -> JSONResponse:
        if reconciliation_endpoint is None:
            return JSONResponse(
                {"status": "REJECTED", "blocker": "RECONCILIATION_NOT_CONFIGURED"},
                status_code=503,
            )
        result = reconciliation_endpoint.handle(
            body=await request.body(),
            signature=request.headers.get("x-vehicle-control-signature", ""),
        )
        status = result.get("status")
        status_code = 200 if status == "PASS" else 403 if status == "REJECTED" else 503
        return JSONResponse(result, status_code=status_code)

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
        """Dispatch a live Host task through mandatory current-state admission."""
        if _caller_workbench_authority_blocked(payload):
            return {
                "status": "NO_SERIALIZE / EXECUTION_FAIL",
                "blocker": "CALLER_WORKBENCH_AUTHORITY_FORBIDDEN",
            }
        request = TaskRequest.model_validate(payload)
        result = application.dispatcher.dispatch(request, require_host_projection=True)
        return result.model_dump(mode="json")

    @server.tool()
    def dispatch_host_task(payload: dict) -> dict:
        """Compatibility name for the same mandatory live Host dispatch path."""
        if _caller_workbench_authority_blocked(payload):
            return {
                "status": "NO_SERIALIZE / EXECUTION_FAIL",
                "blocker": "CALLER_WORKBENCH_AUTHORITY_FORBIDDEN",
            }
        request = TaskRequest.model_validate(payload)
        result = application.dispatcher.dispatch(request, require_host_projection=True)
        return result.model_dump(mode="json")

    @server.tool()
    def dispatch_verified_host_task(payload: dict, ctx: Context) -> dict:
        """Resolve Host identity and signed vehicle evidence inside the server boundary."""
        return dispatch_verified_host_task_from_headers(application, payload, dict(ctx.headers or {}))

    return server


application = configured_application()
vehicle_reconciliation = configured_vehicle_reconciliation(application.settings)
mcp = create_mcp_server(application, vehicle_reconciliation=vehicle_reconciliation)


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
