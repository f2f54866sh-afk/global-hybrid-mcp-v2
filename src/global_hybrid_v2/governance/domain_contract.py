from __future__ import annotations

from dataclasses import dataclass

from global_hybrid_v2.contracts import (
    AuthoritySnapshot,
    ContractCurrentness,
    DomainContract,
    DomainContractStatus,
    Owner,
)


class DomainContractError(RuntimeError):
    pass


@dataclass(frozen=True)
class DomainContractAdmission:
    contract_id: str
    provider_owner: Owner
    consumer_owner: Owner
    decision: str


class DomainContractGate:
    """Validate the common envelope without interpreting its domain payload."""

    def admit(
        self,
        contract: DomainContract,
        *,
        consumer: Owner,
        authority: AuthoritySnapshot,
    ) -> DomainContractAdmission:
        if contract.consumer_owner is not consumer:
            raise DomainContractError("domain contract consumer binding mismatch")
        provider_authority = authority.entries.get(contract.provider_owner)
        if provider_authority is None:
            raise DomainContractError("domain contract provider authority is unresolved")
        if contract.source_authority_revision != provider_authority.revision:
            raise DomainContractError("domain contract authority revision mismatch")
        if contract.status is not DomainContractStatus.PASS:
            raise DomainContractError("domain contract is not admitted")
        if contract.currentness is not ContractCurrentness.CURRENT:
            raise DomainContractError("domain contract is not current")

        return DomainContractAdmission(
            contract_id=contract.contract_id,
            provider_owner=contract.provider_owner,
            consumer_owner=contract.consumer_owner,
            decision="PASS",
        )
