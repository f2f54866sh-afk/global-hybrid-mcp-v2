"""Server-owned composition; absent upstream providers remain capability debt."""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Literal

from global_hybrid_v2.application import Application, create_application
from global_hybrid_v2.canonical_completion import ServerVerifiedMutationProvider
from global_hybrid_v2.ingress_admission import IngressTurnTokenCodec, InMemoryNonceClaimStore
from global_hybrid_v2.inventory_identity import InventoryIdentityHold
from global_hybrid_v2.inventory_runtime_binding import (
    InventoryRuntime,
    configured_inventory_runtime,
    inventory_binding_readback,
)
from global_hybrid_v2.settings import Settings
from global_hybrid_v2.transactional_vehicle_store import EvidenceAdmissionPort
from global_hybrid_v2.trusted_workbench_intent import (
    EvidenceReceiptSigner,
    TrustedDispatchCompiler,
    TrustedHostTaskCompiler,
    TrustedWorkbenchIntentProducer,
)


@dataclass(frozen=True)
class ConsumerBindings:
    """Injected by trusted bootstrap code, never deserialized from a request or env."""

    mutation: ServerVerifiedMutationProvider | None = None
    evidence: EvidenceAdmissionPort | None = None
    host: TrustedHostTaskCompiler | None = None
    ingress: IngressTurnTokenCodec | None = None


def _provider(provider, method: str, scope: str) -> dict:
    try:
        raw = provider.readback()
        identity = getattr(provider, "provider_id", None)
        bound = (callable(getattr(provider, method, None)) and isinstance(identity, str)
                 and re.fullmatch(r"[a-zA-Z0-9_.:-]{1,80}", identity) and raw.get("provider_id") == identity
                 and raw.get("status") == "BOUND" and raw.get("scope") == scope)
    except Exception:
        bound = False
    # Never serialize arbitrary provider metadata, URLs, tokens or exception text.
    return {"status": "BOUND" if bound else "UNBOUND", "provider_id": identity if bound else None}


def binding_readback(settings: Settings, bindings: ConsumerBindings, scope: str,
                     inventory_runtime: InventoryRuntime | None = None) -> dict:
    host, ingress = bindings.host, bindings.ingress
    items = {
        "verified_mutation_provider": _provider(bindings.mutation, "compile", scope),
        "evidence_admission_provider": _provider(bindings.evidence, "resolve", scope),
        "host_current_state_resolver": _provider(
            getattr(host, "host_state_resolver", None), "resolve", scope),
        "evidence_receipt_provider": _provider(getattr(host, "evidence_provider", None), "resolve", scope),
        "nonce_store": _provider(getattr(ingress, "replay_store", None), "claim", scope),
    }
    host_bound = (isinstance(host, TrustedHostTaskCompiler)
                  and isinstance(host.dispatch_compiler, TrustedDispatchCompiler)
                  and isinstance(host.dispatch_compiler.producer, TrustedWorkbenchIntentProducer)
                  and isinstance(host.dispatch_compiler.producer.verifier, EvidenceReceiptSigner)
                  and all(items[k]["status"] == "BOUND" for k in
                          ("host_current_state_resolver", "evidence_receipt_provider")))
    items["trusted_host_binding"] = {"status": "BOUND" if host_bound else "UNBOUND"}
    ingress_bound = isinstance(ingress, IngressTurnTokenCodec) and items["nonce_store"]["status"] == "BOUND"
    if scope == "PRODUCTION" and isinstance(getattr(ingress, "replay_store", None), InMemoryNonceClaimStore):
        items["nonce_store"] = {"status": "UNBOUND", "provider_id": None}
        ingress_bound = False
    items["ingress_admission"] = {"status": "BOUND" if ingress_bound else "UNBOUND"}
    # Media-bound turns require a separately admitted repository; no fake default.
    items["media_repository"] = _provider(getattr(host, "media_repository", None), "by_id", scope)
    required = [v for k, v in items.items() if k != "media_repository" or settings.media_enabled]
    complete = all(v["status"] == "BOUND" for v in required) and settings.canonical_postgres_dsn is not None
    canonical = settings.canonical_vehicle_store_mode == "postgres" and complete
    items["canonical_store_provider"] = {
        "status": "BOUND" if canonical else "UNBOUND",
        "provider_id": "TransactionalVehicleStore.postgres" if canonical else None,
    }
    items["completion_fence"] = {"status": "BOUND" if canonical else "UNBOUND"}
    return {"canonical_store_mode": settings.canonical_vehicle_store_mode,
            "binding_scope": scope, "bindings": items,
            "inventory": inventory_binding_readback(settings, inventory_runtime),
            "ready": settings.canonical_vehicle_store_mode != "postgres" or complete}


def configured_application(*, settings: Settings | None = None,
                           bindings: ConsumerBindings | None = None,
                           binding_scope: Literal["PRODUCTION", "CONTROLLED_TEST"] = "PRODUCTION",
                           **application_options) -> Application:
    """No implicit production providers exist. Postgres startup must fail without them."""
    settings = settings or Settings()
    bindings = bindings or ConsumerBindings()
    reserved = {"canonical_verified_mutation_provider", "canonical_evidence_admission",
                "trusted_host_task_compiler", "ingress_token_codec", "company_commercial_completion_handler"}
    if reserved & application_options.keys():
        raise RuntimeError("COMPOSITION_BINDING_OVERRIDE_FORBIDDEN")
    try:
        inventory_runtime = configured_inventory_runtime(settings)
    except InventoryIdentityHold:
        inventory_runtime = None
    report = binding_readback(settings, bindings, binding_scope, inventory_runtime)
    if not report["ready"]:
        raise RuntimeError("CANONICAL_STORE_BINDING_INCOMPLETE")
    app = create_application(
        settings=settings, canonical_verified_mutation_provider=bindings.mutation,
        canonical_evidence_admission=bindings.evidence, trusted_host_task_compiler=bindings.host,
        ingress_token_codec=bindings.ingress, **application_options,
    )
    return replace(app, inventory_runtime=inventory_runtime,
                   consumer_binding_readback=lambda: binding_readback(
                       settings, bindings, binding_scope, inventory_runtime))


def consumer_readiness(application: Application) -> dict:
    callback = getattr(application, "consumer_binding_readback", None)
    try:
        report = (callback() if callback else
                  binding_readback(application.settings, ConsumerBindings(), "UNBOUND"))
    except Exception:
        report = binding_readback(application.settings, ConsumerBindings(), "UNBOUND")
    return {**report, "runtime": application.runtime_identity.model_dump()}
