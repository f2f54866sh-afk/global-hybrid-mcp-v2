"""Stage-1 server-owned identity selection ingress for the image runtime."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe
from uuid import uuid4

from global_hybrid_v2.runtime.state import (
    AuthenticatedPrincipal,
    IdentityAuthoritySelection,
    RuntimeStateStore,
)


class TrustedIdentityIngress:
    """Only an application-owned caller holding a principal can issue selections."""

    def __init__(self, store: RuntimeStateStore):
        self.store = store

    def issue(
        self,
        *,
        principal: AuthenticatedPrincipal,
        conversation_or_thread_id: str,
        runtime_task_id: str,
        master_asset_id: str,
        master_sha256: str,
        secondary_roles: dict[str, str],
        excluded_generated_source_ids: set[str],
        generative_only: bool,
        revision: int = 1,
        lifetime: timedelta = timedelta(minutes=10),
    ) -> IdentityAuthoritySelection:
        now = datetime.now(UTC)
        nonce = token_urlsafe(24)
        base = {
            "record_id": str(uuid4()), "principal_subject": principal.subject,
            "conversation_or_thread_id": conversation_or_thread_id, "runtime_task_id": runtime_task_id,
            "master_asset_id": master_asset_id, "master_sha256": master_sha256,
            "secondary_roles": secondary_roles,
            "excluded_generated_source_ids": sorted(excluded_generated_source_ids),
            "generative_only": generative_only, "revision": revision, "issued_at": now.isoformat(),
            "expires_at": (now + lifetime).isoformat(), "current": True, "revoked": False,
            "server_nonce": nonce,
        }
        draft = IdentityAuthoritySelection(**base, server_digest="0" * 64)
        digest = hashlib.sha256(
            json.dumps(
                draft.model_dump(mode="json", exclude={"server_digest"}),
                sort_keys=True, separators=(",", ":"),
            ).encode()
        ).hexdigest()
        selection = draft.model_copy(update={"server_digest": digest})
        return self.store.create_identity_authority_selection(selection)  # type: ignore[attr-defined]

    def verify(
        self, *, record_id: str, principal: AuthenticatedPrincipal,
        conversation_or_thread_id: str, runtime_task_id: str,
    ) -> IdentityAuthoritySelection:
        selection = self.store.load_identity_authority_selection(record_id)  # type: ignore[attr-defined]
        body = selection.model_dump(mode="json", exclude={"server_digest"})
        digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if not (
            selection.server_digest == digest and selection.principal_subject == principal.subject
            and selection.conversation_or_thread_id == conversation_or_thread_id
            and selection.runtime_task_id == runtime_task_id and selection.current
            and not selection.revoked and selection.expires_at > datetime.now(UTC)
        ):
            raise PermissionError("identity authority selection verification failed")
        return selection
