"""Company-commercial completion backed by a committed canonical transaction."""
from __future__ import annotations

from typing import Protocol

import psycopg

from global_hybrid_v2.company_commercial_completion import CANONICAL_WORKBENCH_FILE_ID
from global_hybrid_v2.contracts import PersistenceDisposition, PersistenceReceipt, WorkbenchSyncIntent
from global_hybrid_v2.transactional_vehicle_store import (
    CanonicalCapabilityDebt,
    CanonicalConflict,
    CanonicalMutation,
    VehicleMutationPort,
)


class ServerVerifiedMutationProvider(Protocol):
    """Only the controlled host may issue a mutation from resolved identity and evidence."""

    def compile(self, *, task_id: str, intent: WorkbenchSyncIntent) -> CanonicalMutation: ...


class CanonicalCompanyCommercialCompletionHandler:
    def __init__(self, *, store: VehicleMutationPort | None,
                 verified_mutations: ServerVerifiedMutationProvider | None):
        self.store = store
        self.verified_mutations = verified_mutations

    def consume(self, *, task_id: str, intent: WorkbenchSyncIntent) -> PersistenceReceipt:
        if intent.target_file_id != CANONICAL_WORKBENCH_FILE_ID:
            return PersistenceReceipt(state=PersistenceDisposition.HOLD_CONFLICT,
                                      task_id=task_id, blocker="HOLD_TARGET_FILE_ID_MISMATCH")
        if intent.identity_conflict or not intent.safe_attribution:
            return PersistenceReceipt(state=PersistenceDisposition.HOLD_CONFLICT,
                                      task_id=task_id, blocker="HOLD_VEHICLE_IDENTITY_UNRESOLVED")
        if self.store is None or self.verified_mutations is None:
            return PersistenceReceipt(state=PersistenceDisposition.PERSISTENCE_CAPABILITY_DEBT,
                                      task_id=task_id, blocker="CANONICAL_BINDING_UNAVAILABLE")
        try:
            mutation = self.verified_mutations.compile(task_id=task_id, intent=intent)
            if mutation.task_id != task_id or mutation.vehicle_instance_id != intent.vehicle_instance_id:
                raise CanonicalConflict("HOLD_TRUSTED_MUTATION_BINDING_MISMATCH")
            if mutation.verified_delta != intent.verified_delta:
                raise CanonicalConflict("HOLD_TRUSTED_DELTA_MISMATCH")
            return self.store.commit_verified(mutation)
        except (CanonicalCapabilityDebt, psycopg.OperationalError, OSError, TimeoutError) as exc:
            return PersistenceReceipt(state=PersistenceDisposition.PERSISTENCE_CAPABILITY_DEBT,
                                      task_id=task_id, blocker=type(exc).__name__)
        except CanonicalConflict as exc:
            return PersistenceReceipt(state=PersistenceDisposition.HOLD_CONFLICT,
                                      task_id=task_id, blocker=str(exc))
        except Exception as exc:
            return PersistenceReceipt(state=PersistenceDisposition.HOLD_CONFLICT,
                                      task_id=task_id,
                                      blocker="CANONICAL_EXECUTION_FAILED:" + type(exc).__name__)
