from __future__ import annotations

from dataclasses import dataclass

from global_hybrid_v2.contracts import AuthoritySnapshot, EffectType, Owner
from global_hybrid_v2.domains.base import DomainPort
from global_hybrid_v2.governance.effects import OWNER_EFFECTS
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
