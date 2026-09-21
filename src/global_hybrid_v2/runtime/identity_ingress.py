"""Stage-1 server-owned identity selection ingress for the image runtime."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe
from uuid import uuid4

from global_hybrid_v2.runtime.state import (
    AuthenticatedPrincipal,
    IdentityAuthoritySelection,
    IdentitySecondaryRole,
    IdentitySelectionLifecycle,
    RuntimeStateError,
    RuntimeStateStore,
    identity_authority_selection_digest,
)


class TrustedIdentityIngress:
    """Only an application-owned caller holding a principal can issue selections."""

    def __init__(
        self,
        store: RuntimeStateStore,
        *,
        selection_lifetime: timedelta = timedelta(minutes=10),
    ):
        if selection_lifetime <= timedelta(0):
            raise ValueError("selection lifetime must be positive")
        self.store = store
        self.selection_lifetime = selection_lifetime

    def issue(
        self,
        *,
        principal: AuthenticatedPrincipal,
        conversation_or_thread_id: str,
        runtime_task_id: str,
        person_binding: str,
        master_asset_id: str,
        master_sha256: str,
        secondary_roles: dict[str, IdentitySecondaryRole],
        excluded_generated_source_ids: set[str],
        generative_only: bool,
    ) -> IdentityAuthoritySelection:
        selection = self._new_selection(
            principal=principal,
            conversation_or_thread_id=conversation_or_thread_id,
            runtime_task_id=runtime_task_id,
            person_binding=person_binding,
            master_asset_id=master_asset_id,
            master_sha256=master_sha256,
            secondary_roles=secondary_roles,
            excluded_generated_source_ids=excluded_generated_source_ids,
            generative_only=generative_only,
            revision=1,
        )
        return self.store.create_identity_authority_selection(selection)

    def supersede(
        self,
        *,
        prior_record_id: str,
        principal: AuthenticatedPrincipal,
        conversation_or_thread_id: str,
        runtime_task_id: str,
        person_binding: str,
        master_asset_id: str,
        master_sha256: str,
        secondary_roles: dict[str, IdentitySecondaryRole],
        excluded_generated_source_ids: set[str],
        generative_only: bool,
    ) -> IdentityAuthoritySelection:
        prior = self.store.load_identity_authority_selection(prior_record_id)
        replacement = self._new_selection(
            principal=principal,
            conversation_or_thread_id=conversation_or_thread_id,
            runtime_task_id=runtime_task_id,
            person_binding=person_binding,
            master_asset_id=master_asset_id,
            master_sha256=master_sha256,
            secondary_roles=secondary_roles,
            excluded_generated_source_ids=excluded_generated_source_ids,
            generative_only=generative_only,
            revision=prior.revision + 1,
        )
        return self.store.supersede_identity_authority_selection(
            prior_record_id,
            replacement,
            principal_subject=principal.subject,
            conversation_or_thread_id=conversation_or_thread_id,
            runtime_task_id=runtime_task_id,
        )

    def revoke(
        self,
        *,
        record_id: str,
        principal: AuthenticatedPrincipal,
        conversation_or_thread_id: str,
        runtime_task_id: str,
    ) -> IdentityAuthoritySelection:
        return self.store.revoke_identity_authority_selection(
            record_id,
            principal_subject=principal.subject,
            conversation_or_thread_id=conversation_or_thread_id,
            runtime_task_id=runtime_task_id,
        )

    def verify(
        self, *, record_id: str, principal: AuthenticatedPrincipal,
        conversation_or_thread_id: str, runtime_task_id: str,
    ) -> IdentityAuthoritySelection:
        selection = self.store.load_identity_authority_selection(record_id)
        try:
            current = self.store.load_current_identity_authority_selection(
                principal.subject,
                conversation_or_thread_id,
                runtime_task_id,
            )
        except RuntimeStateError as exc:
            raise PermissionError(
                "identity authority selection verification failed"
            ) from exc
        if not (
            selection.server_digest == identity_authority_selection_digest(selection)
            and selection.principal_subject == principal.subject
            and selection.conversation_or_thread_id == conversation_or_thread_id
            and selection.runtime_task_id == runtime_task_id
            and selection.lifecycle is IdentitySelectionLifecycle.ACTIVE
            and selection.expires_at > datetime.now(UTC)
            and selection.record_id == current.record_id
            and selection.revision == current.revision
        ):
            raise PermissionError("identity authority selection verification failed")
        return selection

    def _new_selection(
        self,
        *,
        principal: AuthenticatedPrincipal,
        conversation_or_thread_id: str,
        runtime_task_id: str,
        person_binding: str,
        master_asset_id: str,
        master_sha256: str,
        secondary_roles: dict[str, IdentitySecondaryRole],
        excluded_generated_source_ids: set[str],
        generative_only: bool,
        revision: int,
    ) -> IdentityAuthoritySelection:
        now = datetime.now(UTC)
        draft = IdentityAuthoritySelection(
            record_id=str(uuid4()),
            principal_subject=principal.subject,
            conversation_or_thread_id=conversation_or_thread_id,
            runtime_task_id=runtime_task_id,
            person_binding=person_binding,
            master_asset_id=master_asset_id,
            master_sha256=master_sha256,
            secondary_roles=secondary_roles,
            excluded_generated_source_ids=excluded_generated_source_ids,
            generative_only=generative_only,
            revision=revision,
            issued_at=now,
            expires_at=now + self.selection_lifetime,
            lifecycle=IdentitySelectionLifecycle.ACTIVE,
            server_nonce=token_urlsafe(24),
            server_digest="0" * 64,
        )
        return draft.model_copy(
            update={"server_digest": identity_authority_selection_digest(draft)}
        )
