"""Standalone app-owned public-Copy finalizer surface.

This app is intentionally separate from the ChatGPT Project/MCP response surface.
A draft snapshot is non-authoritative until the user confirms it on this app's
HTML surface. Only confirmed snapshots may be finalized, and accepted Copy is
served from this app's result URL so the ChatGPT model cannot rewrite it after
final acceptance.
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs

import uvicorn
from pydantic import AliasChoices, Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.routing import Route

from global_hybrid_v2.existing_copy_policy_bridge import ExistingCopyPolicyBridge
from global_hybrid_v2.public_copy_finalizer import (
    AppOwnedPublicCopyFinalizer,
    GuardDecision,
    PublicCopyCandidate,
    PublicCopyField,
    PublicCopySnapshotInput,
    SQLitePublicCopyFinalizerStore,
    UnavailablePublicCopyGuard,
    confirmation_page,
    result_page,
)


class FinalizerSettings(BaseSettings):
    db_path: str = "/tmp/public-copy-finalizer.sqlite"
    base_url: str = ""
    model: str | None = None
    allow_ephemeral_canary: bool = False
    openai_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_API_KEY", "GLOBAL_OPENAI_API_KEY"),
    )
    port: int = 8000

    model_config = SettingsConfigDict(
        env_prefix="PUBLIC_COPY_FINALIZER_",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )


def _build_finalizer(settings: FinalizerSettings) -> AppOwnedPublicCopyFinalizer:
    path = Path(settings.db_path)
    if str(path).startswith("/tmp/") and not settings.allow_ephemeral_canary:
        raise RuntimeError("EPHEMERAL_FINALIZER_STORE_REQUIRES_EXPLICIT_CANARY_MODE")
    store = SQLitePublicCopyFinalizerStore(path)
    return AppOwnedPublicCopyFinalizer(store=store, guard=ExistingCopyPolicyBridge())


def create_finalizer_app(
    *,
    settings: FinalizerSettings | None = None,
    finalizer: AppOwnedPublicCopyFinalizer | None = None,
) -> Starlette:
    cfg = settings or FinalizerSettings()
    service = finalizer or _build_finalizer(cfg)
    base_url = cfg.base_url.rstrip("/")

    async def health(_: Request) -> JSONResponse:
        return JSONResponse(
            {
                "ok": True,
                "service": "app-owned-public-copy-finalizer",
                "ephemeral_canary": str(Path(cfg.db_path)).startswith("/tmp/"),
                "evaluator_configured": not isinstance(
                    service.guard, (UnavailablePublicCopyGuard, ExistingCopyPolicyBridge)
                ),
                "deterministic_policy_bridge": isinstance(service.guard, ExistingCopyPolicyBridge),
            }
        )

    async def create_draft(request: Request) -> JSONResponse:
        try:
            payload = PublicCopySnapshotInput.model_validate(await request.json())
            draft = service.create_draft(payload)
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            return JSONResponse(
                {"status": "REJECTED", "blocker": type(exc).__name__},
                status_code=400,
            )
        if not base_url:
            return JSONResponse(
                {
                    "status": "BLOCKED",
                    "blocker": "PUBLIC_COPY_FINALIZER_BASE_URL_NOT_CONFIGURED",
                    "task_handle": draft.task_handle,
                    "snapshot_digest": draft.snapshot_digest,
                },
                status_code=503,
            )
        return JSONResponse(
            {
                "status": "USER_CONFIRMATION_REQUIRED",
                "task_handle": draft.task_handle,
                "snapshot_digest": draft.snapshot_digest,
                "confirmation_url": f"{base_url}/tasks/{draft.task_handle}/confirm",
                "requires_user_confirmation": True,
            },
            status_code=202,
        )

    async def confirm_task(request: Request) -> HTMLResponse:
        task_handle = request.path_params["task_handle"]
        try:
            snapshot = service.store.load_snapshot(task_handle)
        except (KeyError, RuntimeError):
            return HTMLResponse("Task not found", status_code=404)
        if request.method == "GET":
            return HTMLResponse(confirmation_page(snapshot))
        try:
            raw = (await request.body()).decode("utf-8")
            form = parse_qs(raw, keep_blank_values=True)
            nonce = form.get("confirmation_nonce", [""])[0]
            snapshot = service.confirm(task_handle, nonce)
        except (UnicodeDecodeError, PermissionError, RuntimeError):
            return HTMLResponse("Confirmation rejected", status_code=403)
        if not base_url:
            return HTMLResponse("Confirmed, but base URL is not configured", status_code=503)
        return HTMLResponse(
            "<!doctype html><meta charset='utf-8'><h1>Task confirmed</h1>"
            f"<p>Snapshot {snapshot.snapshot_digest}</p>"
            f"<p><a href='{base_url}/tasks/{task_handle}/candidate'>Submit candidate Copy</a></p>"
        )

    async def candidate_form(request: Request) -> HTMLResponse:
        task_handle = request.path_params["task_handle"]
        try:
            snapshot = service.store.load_snapshot(task_handle)
        except (KeyError, RuntimeError):
            return HTMLResponse("Task not found", status_code=404)
        if snapshot.state.value != "CONFIRMED":
            return HTMLResponse("Task confirmation required", status_code=409)
        inputs = "".join(
            f"<h2>{label}</h2><textarea name='field_{index}' rows='8' cols='80'></textarea>"
            for index, label in enumerate(snapshot.snapshot.requested_fields)
        )
        return HTMLResponse(
            "<!doctype html><meta charset='utf-8'><h1>Submit candidate Copy</h1>"
            f"<form method='post'>{inputs}<p><button type='submit'>Run finalizer</button></p></form>"
        )

    async def candidate_submit(request: Request):
        task_handle = request.path_params["task_handle"]
        try:
            snapshot = service.store.load_snapshot(task_handle)
            if snapshot.state.value != "CONFIRMED":
                return HTMLResponse("Task confirmation required", status_code=409)
            raw = (await request.body()).decode("utf-8")
            form = parse_qs(raw, keep_blank_values=True)
            fields = tuple(
                PublicCopyField(
                    label=label,
                    value=form.get(f"field_{index}", [""])[0],
                )
                for index, label in enumerate(snapshot.snapshot.requested_fields)
            )
            receipt = service.finalize(task_handle, PublicCopyCandidate(fields=fields))
        except (ValidationError, ValueError, KeyError, PermissionError, RuntimeError) as exc:
            return HTMLResponse(f"Finalization rejected: {type(exc).__name__}", status_code=400)
        if receipt.decision is not GuardDecision.PASS:
            blockers = ", ".join(receipt.guard_receipt.blocker_codes)
            return HTMLResponse(
                "<!doctype html><meta charset='utf-8'><h1>Copy withheld</h1>"
                f"<p>{blockers}</p>",
                status_code=422,
            )
        if not base_url:
            return HTMLResponse("PASS, but base URL is not configured", status_code=503)
        return RedirectResponse(
            f"{base_url}/results/{receipt.receipt_id}",
            status_code=303,
        )

    async def finalize_api(request: Request) -> JSONResponse:
        task_handle = request.path_params["task_handle"]
        try:
            candidate = PublicCopyCandidate.model_validate(await request.json())
            receipt = service.finalize(task_handle, candidate)
        except (ValidationError, ValueError, KeyError, PermissionError, RuntimeError) as exc:
            return JSONResponse(
                {"status": "REJECTED", "blocker": type(exc).__name__},
                status_code=409,
            )
        if receipt.decision is GuardDecision.PASS:
            if not base_url:
                return JSONResponse(
                    {"status": "BLOCKED", "blocker": "PUBLIC_COPY_FINALIZER_BASE_URL_NOT_CONFIGURED"},
                    status_code=503,
                )
            return JSONResponse(
                {
                    "status": "PASS",
                    "receipt_id": receipt.receipt_id,
                    "candidate_digest": receipt.candidate_digest,
                    "snapshot_digest": receipt.snapshot_digest,
                    "result_url": f"{base_url}/results/{receipt.receipt_id}",
                }
            )
        return JSONResponse(
            {
                "status": "HOLD",
                "receipt_id": receipt.receipt_id,
                "candidate_digest": receipt.candidate_digest,
                "snapshot_digest": receipt.snapshot_digest,
                "blocker_codes": list(receipt.guard_receipt.blocker_codes),
                "reasons": list(receipt.guard_receipt.reasons),
                "deterministic_hard_gates": receipt.guard_receipt.deterministic_hard_gates,
                "capability_debt": list(receipt.guard_receipt.capability_debt),
            },
            status_code=422,
        )

    async def result(request: Request) -> HTMLResponse:
        try:
            receipt = service.store.load_receipt(request.path_params["receipt_id"])
            return HTMLResponse(result_page(receipt))
        except (KeyError, PermissionError, RuntimeError):
            return HTMLResponse("Result not available", status_code=404)

    return Starlette(
        routes=[
            Route("/health", health, methods=["GET"]),
            Route("/api/tasks/draft", create_draft, methods=["POST"]),
            Route("/tasks/{task_handle:str}/confirm", confirm_task, methods=["GET", "POST"]),
            Route("/tasks/{task_handle:str}/candidate", candidate_form, methods=["GET"]),
            Route("/tasks/{task_handle:str}/candidate", candidate_submit, methods=["POST"]),
            Route("/api/tasks/{task_handle:str}/finalize", finalize_api, methods=["POST"]),
            Route("/results/{receipt_id:str}", result, methods=["GET"]),
        ]
    )


def main() -> None:
    settings = FinalizerSettings()
    application = create_finalizer_app(settings=settings)
    uvicorn.run(application, host="0.0.0.0", port=settings.port)


if __name__ == "__main__":
    main()
