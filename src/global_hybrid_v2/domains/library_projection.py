from __future__ import annotations

from typing import Any

from global_hybrid_v2.contracts import (
    AuthoritySnapshot,
    ContextClass,
    ContractCurrentness,
    DomainContract,
    DomainContractStatus,
    DomainInteractionMode,
    DomainResult,
    LibraryAccessKind,
    LibraryAccessRequest,
    Owner,
    TaskContract,
)


class LibraryProjectionDomain:
    """LIBRARY-owned bounded read projection; it never makes Sales decisions."""

    owner = Owner.LIBRARY_FACT
    projection_name = "sales_media_evidence"
    contract_version = 1
    allowed_context_classes = {
        ContextClass.UNTRUSTED_EXTERNAL_EVIDENCE,
        ContextClass.CURRENT_FACT,
        ContextClass.CURRENT_CAPABILITY_FACT,
    }
    blocked_sales_decisions = {
        "age_target",
        "geo_target",
        "targeting_winner",
        "budget_decision",
        "creative_decision",
    }

    def project(
        self,
        request: LibraryAccessRequest,
        *,
        task: TaskContract,
        authority: AuthoritySnapshot,
    ) -> DomainContract:
        if request.actor_owner is not Owner.SALES_HUMAN:
            raise ValueError("sales media projection requires SALES_HUMAN consumer")
        if request.access_kind is not LibraryAccessKind.READ_PROJECTION:
            raise ValueError("sales media projection is read-only")
        if request.projection != self.projection_name:
            raise ValueError("unsupported Library projection")

        library_authority = authority.entries[Owner.LIBRARY_FACT]
        evidence_items = [
            self._project_context(item)
            for item in task.context
            if item.context_class in self.allowed_context_classes
        ]
        uncertainties = self._uncertainties(evidence_items)
        payload: dict[str, Any] = {
            "library_request_id": request.request_id,
            "projection": request.projection,
            "contract_version": request.contract_version,
            "source_scope": request.task_scope,
            "evidence_role": "LIBRARY_EVIDENCE_NOT_SALES_DECISION",
            "evidence_items": evidence_items,
            "uncertainties": uncertainties,
        }
        required_fields = request.required_fields or {
            "library_request_id",
            "projection",
            "contract_version",
            "source_scope",
            "evidence_role",
            "evidence_items",
            "uncertainties",
        }
        provenance = [f"library-authority:{library_authority.revision}"]
        for item in task.context:
            if item.context_class in self.allowed_context_classes:
                provenance.extend(item.provenance)

        return DomainContract(
            task_trace_id=task.task_trace_id,
            schema_version=self.contract_version,
            provider_owner=Owner.LIBRARY_FACT,
            consumer_owner=Owner.SALES_HUMAN,
            task_scope=request.task_scope,
            source_authority_revision=library_authority.revision,
            requirement_ids=["SALES_MEDIA_FACT_NEED"],
            required_fields=required_fields,
            optional_fields=set(),
            used_fields=required_fields,
            blocked_foreign_fields=self.blocked_sales_decisions,
            currentness=ContractCurrentness.CURRENT,
            provenance=list(dict.fromkeys(provenance)),
            status=DomainContractStatus.PASS,
            interaction_mode=DomainInteractionMode.SERVICE,
            payload=payload,
        )

    @staticmethod
    def _project_context(item: Any) -> dict[str, Any]:
        payload = item.payload if isinstance(item.payload, dict) else {"claim": item.payload}
        return {
            "context_id": item.id,
            "source": list(item.provenance),
            "as_of": payload.get("as_of"),
            "market_scope": payload.get("market_scope"),
            "confidence": payload.get("confidence", "UNVERIFIED"),
            "conflict_gap": payload.get("conflict_gap", "UNRESOLVED"),
            "evidence_role": payload.get("evidence_role", "UNTRUSTED_EVIDENCE"),
            "claims": payload,
        }

    @staticmethod
    def _uncertainties(evidence_items: list[dict[str, Any]]) -> list[str]:
        if not evidence_items:
            return [
                "VEHICLE_AND_MARKET_EVIDENCE_NOT_PROVIDED",
                "CURRENT_PLATFORM_CAPABILITY_NOT_VERIFIED",
                "CAMPAIGN_OUTCOME_NOT_AVAILABLE",
            ]
        gaps = [
            str(item["conflict_gap"])
            for item in evidence_items
            if str(item["conflict_gap"]).strip()
            and str(item["conflict_gap"]).upper() not in {"NONE", "NO_CONFLICT"}
        ]
        return gaps or ["CURRENT_PLATFORM_AND_OUTCOME_EVIDENCE_REQUIRES_CONFIRMATION"]

    def run(self, contract: TaskContract) -> DomainResult:
        return DomainResult(
            owner=self.owner,
            status="LIBRARY_READ_PROJECTION_ONLY",
            output={"state": "FACT_NEED_REQUIRES_CONSUMER_PROJECTION"},
            evidence={"adapter_configured": True},
        )
