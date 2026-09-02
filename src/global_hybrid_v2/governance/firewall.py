from __future__ import annotations

from dataclasses import dataclass

from global_hybrid_v2.contracts import (
    AuthoritySnapshot,
    ContextAdmissionDecision,
    ContextAdmissionReason,
    ContextAdmissionReceipt,
    ContextAuthorityEffect,
    ContextClass,
    ContextContentRole,
    ContextItem,
    ContextOrigin,
)


class FirewallError(RuntimeError):
    pass


@dataclass(frozen=True)
class ContextAdmissionResult:
    admitted: list[ContextItem]
    receipts: list[ContextAdmissionReceipt]


class TaskFirewall:
    LEGACY_ORIGINS = {
        ContextOrigin.HISTORY,
        ContextOrigin.ARCHIVE,
        ContextOrigin.MEMORY,
    }
    EXTERNAL_ORIGINS = {
        ContextOrigin.CURRENT_TOOL_RESULT,
        ContextOrigin.EXTERNAL_SOURCE,
    }

    def filter(self, items: list[ContextItem], authority: AuthoritySnapshot) -> list[ContextItem]:
        return self.evaluate(items, authority).admitted

    def evaluate(
        self,
        items: list[ContextItem],
        authority: AuthoritySnapshot,
    ) -> ContextAdmissionResult:
        admitted: list[ContextItem] = []
        receipts: list[ContextAdmissionReceipt] = []
        for item in items:
            receipt = self._evaluate_item(item, authority)
            receipts.append(receipt)
            if receipt.decision is not ContextAdmissionDecision.QUARANTINE:
                admitted.append(item)
        return ContextAdmissionResult(admitted=admitted, receipts=receipts)

    def _evaluate_item(
        self,
        item: ContextItem,
        authority: AuthoritySnapshot,
    ) -> ContextAdmissionReceipt:
        if not item.purpose.strip():
            return self._receipt(
                item,
                ContextAdmissionDecision.QUARANTINE,
                ContextAdmissionReason.MISSING_PURPOSE,
            )
        if not item.task_scope.strip():
            return self._receipt(
                item,
                ContextAdmissionDecision.QUARANTINE,
                ContextAdmissionReason.MISSING_SCOPE,
            )
        if item.context_class is ContextClass.UNKNOWN:
            return self._receipt(
                item,
                ContextAdmissionDecision.QUARANTINE,
                ContextAdmissionReason.UNKNOWN_CONTEXT_CLASS,
            )
        if item.context_class is ContextClass.STALE_OR_SUPERSEDED_RULE:
            return self._receipt(
                item,
                ContextAdmissionDecision.QUARANTINE,
                ContextAdmissionReason.STALE_RULE_BLOCKED,
            )
        if item.context_class is ContextClass.NORMATIVE_AUTHORITY:
            return self._evaluate_authority(item, authority)
        if not self._has_provenance(item):
            return self._receipt(
                item,
                ContextAdmissionDecision.QUARANTINE,
                ContextAdmissionReason.MISSING_PROVENANCE,
            )
        if (
            item.origin in self.EXTERNAL_ORIGINS
            and item.content_role is ContextContentRole.EXECUTABLE_INSTRUCTION
        ):
            return self._receipt(
                item,
                ContextAdmissionDecision.ADVISORY,
                ContextAdmissionReason.EXTERNAL_INSTRUCTION_IGNORED,
            )
        if item.context_class is ContextClass.UNTRUSTED_EXTERNAL_EVIDENCE:
            return self._receipt(
                item,
                ContextAdmissionDecision.ADVISORY,
                ContextAdmissionReason.UNTRUSTED_EVIDENCE_DATA_ONLY,
            )
        if item.context_class is ContextClass.STABLE_USER_PREFERENCE:
            return self._evaluate_stable_preference(item)
        if item.context_class is ContextClass.DOMAIN_HEURISTIC:
            return self._evaluate_domain_heuristic(item)
        if item.context_class is ContextClass.REFERENCE_POINTER:
            return self._receipt(
                item,
                ContextAdmissionDecision.RETRIEVAL_HINT,
                ContextAdmissionReason.REFERENCE_POINTER_ACCEPTED,
            )
        if item.context_class is ContextClass.CASE_HISTORY:
            return self._evaluate_case_history(item)
        if item.context_class is ContextClass.CURRENT_FACT:
            return self._evaluate_current_fact(item)
        if item.context_class is ContextClass.CURRENT_CAPABILITY_FACT:
            return self._evaluate_current_capability(item)
        return self._receipt(
            item,
            ContextAdmissionDecision.QUARANTINE,
            ContextAdmissionReason.UNKNOWN_CONTEXT_CLASS,
        )

    def _evaluate_authority(
        self,
        item: ContextItem,
        authority: AuthoritySnapshot,
    ) -> ContextAdmissionReceipt:
        if item.origin in self.LEGACY_ORIGINS:
            return self._receipt(
                item,
                ContextAdmissionDecision.QUARANTINE,
                ContextAdmissionReason.LEGACY_AUTHORITY_FORBIDDEN,
            )
        if item.origin is not ContextOrigin.CURRENT_AUTHORITY:
            return self._receipt(
                item,
                ContextAdmissionDecision.QUARANTINE,
                ContextAdmissionReason.NORMATIVE_AUTHORITY_REQUIRES_CURRENT_AUTHORITY,
            )
        if not item.authority_owner or not item.authority_revision:
            return self._receipt(
                item,
                ContextAdmissionDecision.QUARANTINE,
                ContextAdmissionReason.AUTHORITY_METADATA_MISSING,
            )
        expected = authority.entries[item.authority_owner].revision
        if item.authority_revision != expected:
            return self._receipt(
                item,
                ContextAdmissionDecision.QUARANTINE,
                ContextAdmissionReason.AUTHORITY_REVISION_MISMATCH,
            )
        if not self._has_provenance(item):
            return self._receipt(
                item,
                ContextAdmissionDecision.QUARANTINE,
                ContextAdmissionReason.MISSING_PROVENANCE,
            )
        return self._receipt(
            item,
            ContextAdmissionDecision.EXECUTABLE,
            ContextAdmissionReason.CURRENT_CONTEXT_ACCEPTED,
            authority_effect=ContextAuthorityEffect.CURRENT_AUTHORITY,
        )

    def _evaluate_stable_preference(self, item: ContextItem) -> ContextAdmissionReceipt:
        if item.origin is ContextOrigin.MEMORY:
            return self._receipt(
                item,
                ContextAdmissionDecision.ADVISORY,
                ContextAdmissionReason.ADVISORY_MEMORY_ACCEPTED,
            )
        if item.origin is ContextOrigin.HISTORY:
            return self._receipt(
                item,
                ContextAdmissionDecision.ADVISORY,
                ContextAdmissionReason.ADVISORY_HISTORY_ACCEPTED,
            )
        if item.origin is ContextOrigin.CURRENT_USER:
            return self._receipt(
                item,
                ContextAdmissionDecision.EXECUTABLE,
                ContextAdmissionReason.CURRENT_CONTEXT_ACCEPTED,
            )
        return self._receipt(
            item,
            ContextAdmissionDecision.QUARANTINE,
            ContextAdmissionReason.UNSUPPORTED_CONTEXT_ORIGIN,
        )

    def _evaluate_domain_heuristic(self, item: ContextItem) -> ContextAdmissionReceipt:
        if item.origin is ContextOrigin.MEMORY:
            reason = ContextAdmissionReason.ADVISORY_MEMORY_ACCEPTED
        elif item.origin is ContextOrigin.HISTORY:
            reason = ContextAdmissionReason.ADVISORY_HISTORY_ACCEPTED
        elif item.origin in {ContextOrigin.CURRENT_USER, ContextOrigin.CURRENT_TOOL_RESULT}:
            reason = ContextAdmissionReason.CURRENT_CONTEXT_ACCEPTED
        else:
            return self._receipt(
                item,
                ContextAdmissionDecision.QUARANTINE,
                ContextAdmissionReason.UNSUPPORTED_CONTEXT_ORIGIN,
            )
        return self._receipt(item, ContextAdmissionDecision.ADVISORY, reason)

    def _evaluate_case_history(self, item: ContextItem) -> ContextAdmissionReceipt:
        if item.origin not in self.LEGACY_ORIGINS:
            return self._receipt(
                item,
                ContextAdmissionDecision.QUARANTINE,
                ContextAdmissionReason.UNSUPPORTED_CONTEXT_ORIGIN,
            )
        if not item.current_binding:
            return self._receipt(
                item,
                ContextAdmissionDecision.QUARANTINE,
                ContextAdmissionReason.CASE_HISTORY_NOT_CURRENTLY_BOUND,
            )
        return self._receipt(
            item,
            ContextAdmissionDecision.ADVISORY,
            ContextAdmissionReason.CASE_HISTORY_CURRENTLY_BOUND,
        )

    def _evaluate_current_fact(self, item: ContextItem) -> ContextAdmissionReceipt:
        if item.origin in self.LEGACY_ORIGINS:
            return self._receipt(
                item,
                ContextAdmissionDecision.RETRIEVAL_HINT,
                ContextAdmissionReason.LEGACY_FACT_RETRIEVAL_HINT,
            )
        if item.origin is ContextOrigin.CURRENT_TOOL_RESULT:
            return self._receipt(
                item,
                ContextAdmissionDecision.EXECUTABLE,
                ContextAdmissionReason.CURRENT_CONTEXT_ACCEPTED,
            )
        return self._receipt(
            item,
            ContextAdmissionDecision.QUARANTINE,
            ContextAdmissionReason.CURRENT_FACT_REQUIRES_VERIFIED_SOURCE,
        )

    def _evaluate_current_capability(self, item: ContextItem) -> ContextAdmissionReceipt:
        if item.origin is ContextOrigin.CURRENT_TOOL_RESULT:
            return self._receipt(
                item,
                ContextAdmissionDecision.EXECUTABLE,
                ContextAdmissionReason.CURRENT_CONTEXT_ACCEPTED,
            )
        return self._receipt(
            item,
            ContextAdmissionDecision.QUARANTINE,
            ContextAdmissionReason.CURRENT_CAPABILITY_REQUIRES_FRESH_EVIDENCE,
        )

    @staticmethod
    def _has_provenance(item: ContextItem) -> bool:
        return any(reference.strip() for reference in item.provenance)

    @staticmethod
    def _receipt(
        item: ContextItem,
        decision: ContextAdmissionDecision,
        reason: ContextAdmissionReason,
        *,
        authority_effect: ContextAuthorityEffect | None = None,
    ) -> ContextAdmissionReceipt:
        external = item.origin in TaskFirewall.EXTERNAL_ORIGINS
        admitted_content_role = (
            ContextContentRole.DATA_ONLY if external else item.content_role
        )
        effective_authority = authority_effect
        if effective_authority is None:
            effective_authority = (
                ContextAuthorityEffect.EXPLICIT_USER_AUTHORIZATION
                if item.origin is ContextOrigin.CURRENT_USER
                and item.content_role is ContextContentRole.EXECUTABLE_INSTRUCTION
                else ContextAuthorityEffect.NO_AUTHORITY_EFFECT
            )
        return ContextAdmissionReceipt(
            context_id=item.id,
            origin=item.origin,
            context_class=item.context_class,
            decision=decision,
            reason_code=reason,
            admitted_content_role=admitted_content_role,
            authority_effect=effective_authority,
        )
