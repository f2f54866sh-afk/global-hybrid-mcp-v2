from __future__ import annotations

from dataclasses import dataclass

from global_hybrid_v2.contracts import (
    AuthoritySnapshot,
    ContextAdmissionReason,
    ContextAuthorityEffect,
    ContextClass,
    ContextContentRole,
    ContextOrigin,
    DomainContractStatus,
    DomainResult,
    EffectType,
    Owner,
    TaskContract,
)
from global_hybrid_v2.domains.base import DomainPort
from global_hybrid_v2.governance.effects import OWNER_EFFECTS
from global_hybrid_v2.governance.firewall import TaskFirewall
from global_hybrid_v2.observer.witness import ReadOnlyWitness
from global_hybrid_v2.runtime.trace import TraceBus


@dataclass(frozen=True)
class FitnessCheck:
    name: str
    passed: bool
    blocker: str | None = None


@dataclass(frozen=True)
class FitnessReport:
    checks: tuple[FitnessCheck, ...]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)


class SystemFitnessFunctions:
    """Executable checks for the small set of system-level architecture invariants."""

    @staticmethod
    def evaluate_composition(
        *, domains: dict[Owner, DomainPort], trace: TraceBus
    ) -> FitnessReport:
        expected = set(Owner)
        witness = trace.witness
        forbidden = {"write", "mutate", "execute", "promote", "update_authority", "tool"}
        checks = (
            FitnessCheck(
                "CURRENT_OWNER_TOPOLOGY",
                set(domains) == expected,
                None if set(domains) == expected else "domain adapter topology differs from five owners",
            ),
            FitnessCheck(
                "WITNESS_ALWAYS_ATTACHED",
                isinstance(witness, ReadOnlyWitness),
                None if isinstance(witness, ReadOnlyWitness) else "read-only witness is not attached",
            ),
            FitnessCheck(
                "WITNESS_ZERO_MUTATION_API",
                witness is not None and not forbidden.intersection(dir(witness)),
                (
                    None
                    if witness is not None and not forbidden.intersection(dir(witness))
                    else "witness exposes a forbidden mutation surface"
                ),
            ),
            FitnessCheck(
                "GLOBAL_THIN_EFFECT_BOUNDARY",
                OWNER_EFFECTS[Owner.GLOBAL] == {EffectType.READ_ONLY},
                None if OWNER_EFFECTS[Owner.GLOBAL] == {EffectType.READ_ONLY} else "GLOBAL can mutate",
            ),
            FitnessCheck(
                "VISUAL_EXECUTION_EFFECT_ISOLATION",
                EffectType.EXTERNAL_WRITE not in OWNER_EFFECTS[Owner.VISUAL]
                and EffectType.EXTERNAL_WRITE in OWNER_EFFECTS[Owner.EXECUTION],
                (
                    None
                    if EffectType.EXTERNAL_WRITE not in OWNER_EFFECTS[Owner.VISUAL]
                    and EffectType.EXTERNAL_WRITE in OWNER_EFFECTS[Owner.EXECUTION]
                    else "VISUAL and EXECUTION effect scopes are not isolated"
                ),
            ),
        )
        return FitnessReport(checks=checks)

    @staticmethod
    def evaluate_authority(snapshot: AuthoritySnapshot) -> FitnessReport:
        entries = snapshot.entries
        required = set(Owner)
        shared_real_car = (
            entries.get(Owner.VISUAL) is not None
            and entries.get(Owner.EXECUTION) is not None
            and entries[Owner.VISUAL].revision == entries[Owner.EXECUTION].revision
            and entries[Owner.VISUAL].path == entries[Owner.EXECUTION].path
        )
        isolated_partitions = (
            entries.get(Owner.VISUAL) is not None
            and entries.get(Owner.EXECUTION) is not None
            and entries[Owner.VISUAL].authority_partition == "VISUAL_JUDGE"
            and entries[Owner.EXECUTION].authority_partition == "EXECUTION_LAB"
        )
        sales_reference_only = (
            entries.get(Owner.SALES_HUMAN) is not None
            and all(
                reference.role.value == "REFERENCE_ONLY"
                for reference in entries[Owner.SALES_HUMAN].references
            )
        )
        return FitnessReport(
            checks=(
                FitnessCheck(
                    "CURRENT_AUTHORITY_UNIQUE",
                    set(entries) == required,
                    None if set(entries) == required else "current authority owner set is incomplete",
                ),
                FitnessCheck(
                    "REAL_CAR_SHARED_CANONICAL",
                    shared_real_car,
                    None if shared_real_car else "VISUAL and EXECUTION do not share exact REAL_CAR",
                ),
                FitnessCheck(
                    "REAL_CAR_PARTITION_ISOLATION",
                    isolated_partitions,
                    None if isolated_partitions else "REAL_CAR partitions are not isolated",
                ),
                FitnessCheck(
                    "SALES_HUMAN_REFERENCE_ONLY",
                    sales_reference_only,
                    None if sales_reference_only else "Sales human reference became normative",
                ),
            )
        )

    @staticmethod
    def evaluate_sales_consumption(
        *,
        snapshot: AuthoritySnapshot,
        contract: TaskContract,
        result: DomainResult,
        trace: TraceBus,
    ) -> FitnessReport:
        packets = [
            item
            for item in contract.domain_contracts
            if item.provider_owner is Owner.LIBRARY_FACT
            and item.consumer_owner is Owner.SALES_HUMAN
        ]
        packet = packets[0] if len(packets) == 1 else None
        required_projection = {
            "library_request_id",
            "projection",
            "contract_version",
            "source_scope",
            "evidence_role",
            "evidence_items",
            "uncertainties",
        }
        directive_receipts = [
            item for item in contract.context_admission_receipts if item.directive_detected
        ]
        no_directive_in_consumer = all(
            item.content_role is ContextContentRole.DATA_ONLY
            and not TaskFirewall.contains_external_directive(item.payload)
            for item in contract.context
        )
        no_history_authority = all(
            not (
                item.origin
                in {ContextOrigin.HISTORY, ContextOrigin.ARCHIVE, ContextOrigin.MEMORY}
                and item.context_class is ContextClass.NORMATIVE_AUTHORITY
            )
            for item in contract.context
        )
        evidence = result.evidence

        def check(name: str, passed: bool, blocker: str) -> FitnessCheck:
            return FitnessCheck(name, passed, None if passed else blocker)

        checks = (
            check(
                "CURRENT_POINTER_MATCH",
                Owner.SALES_HUMAN in snapshot.entries
                and Owner.LIBRARY_FACT in snapshot.entries,
                "Sales or Library authority pointer is unresolved",
            ),
            check(
                "TASK_CONTRACT_PASS",
                bool(contract.contract_id and contract.task_trace_id),
                "task contract identity is incomplete",
            ),
            check(
                "OWNER_ROUTE_PASS",
                contract.owner is Owner.SALES_HUMAN,
                "Sales media task did not route to SALES_HUMAN",
            ),
            check(
                "LIBRARY_REQUEST_EXISTS",
                packet is not None and bool(packet.payload.get("library_request_id")),
                "Library request receipt is missing",
            ),
            check(
                "LIBRARY_PACKET_EXISTS",
                packet is not None,
                "bounded Library packet is missing",
            ),
            check(
                "LIBRARY_PACKET_BOUNDED",
                packet is not None
                and packet.status is DomainContractStatus.PASS
                and set(packet.payload) == required_projection
                and not (set(packet.payload) & packet.blocked_foreign_fields),
                "Library packet is unbounded or contains a foreign decision field",
            ),
            check(
                "LIBRARY_DOES_NOT_DECIDE_TARGETING",
                packet is not None
                and packet.payload.get("evidence_role")
                == "LIBRARY_EVIDENCE_NOT_SALES_DECISION"
                and evidence.get("library_decided_targeting") is False,
                "Library projection asserted a Sales targeting decision",
            ),
            check(
                "SNAPSHOT_CONTAINS_REQUIRED_PROJECTION",
                packet is not None
                and required_projection <= set(packet.payload)
                and packet.used_fields == required_projection,
                "consumer-required Library projection is incomplete",
            ),
            check(
                "SALES_ADAPTER_CONFIGURED",
                evidence.get("adapter_configured") is True,
                "Sales adapter is not configured",
            ),
            check(
                "SALES_ADAPTER_CALLED",
                evidence.get("adapter_called") is True,
                "Sales adapter was not called",
            ),
            check(
                "SALES_CONTEXT_MATCHES_SNAPSHOT",
                packet is not None
                and set(evidence.get("actual_consumed_context", [])) == packet.used_fields,
                "Sales consumed context differs from the admitted projection",
            ),
            check(
                "EXTERNAL_DIRECTIVE_DETECTED",
                not directive_receipts
                or all(item.directive_detected for item in directive_receipts),
                "embedded external directive was not detected",
            ),
            check(
                "EXTERNAL_DIRECTIVE_QUARANTINED",
                not directive_receipts
                or all(
                    item.directive_quarantined
                    and item.reason_code
                    is ContextAdmissionReason.QUARANTINE_EXTERNAL_DIRECTIVE
                    and item.authority_effect is ContextAuthorityEffect.NO_AUTHORITY_EFFECT
                    and item.persistence_effect is False
                    for item in directive_receipts
                ),
                "embedded external directive was not quarantined",
            ),
            check(
                "EXTERNAL_DIRECTIVE_NOT_IN_CONSUMER_CONTEXT",
                no_directive_in_consumer,
                "raw external directive reached Sales consumer context",
            ),
            check(
                "NO_HISTORY_FALLBACK",
                no_history_authority,
                "legacy context supplied normative authority",
            ),
            check(
                "NO_UNAUTHORIZED_SIDE_EFFECT",
                set(contract.effects)
                <= {EffectType.READ_ONLY, EffectType.MODEL_INFERENCE},
                "Sales analysis requested an unauthorized side effect",
            ),
            check(
                "WITNESS_READ_ONLY",
                isinstance(trace.witness, ReadOnlyWitness),
                "read-only Witness is not attached",
            ),
        )
        return FitnessReport(checks=checks)
