"""Mandatory persistence terminal for an admitted company-commercial vehicle delta."""
from __future__ import annotations

import hashlib
import json

from global_hybrid_v2.adapters.drive_xlsx_workbench import (
    DriveXlsxWorkbenchPort,
    WorkbenchCapabilityDebt,
    WorkbenchConflict,
    WorkbenchPostwriteMismatch,
)
from global_hybrid_v2.contracts import (
    PersistenceDisposition,
    PersistenceReceipt,
    WorkbenchSyncIntent,
)
from global_hybrid_v2.workbench_mutation import (
    ALLOWED_FIELDS,
    PROTECTED_FIELDS,
    XlsxWorkbenchMutationBuilder,
)

CANONICAL_WORKBENCH_FILE_ID = "1OfUZ_rh94sdXdTZMjMrKj8IjHgEBUFua"


class CompanyCommercialCompletionHandler:
    def __init__(
        self,
        *,
        writer: DriveXlsxWorkbenchPort | None = None,
        builder: XlsxWorkbenchMutationBuilder | None = None,
    ) -> None:
        self.writer = writer
        self.builder = builder

    def consume(self, *, task_id: str, intent: WorkbenchSyncIntent) -> PersistenceReceipt:
        def terminal(state: PersistenceDisposition, blocker: str | None = None) -> PersistenceReceipt:
            return PersistenceReceipt(
                state=state, task_id=task_id, file_id=CANONICAL_WORKBENCH_FILE_ID,
                blocker=blocker,
            )

        if intent.target_file_id != CANONICAL_WORKBENCH_FILE_ID:
            return terminal(PersistenceDisposition.HOLD_CONFLICT, "HOLD_TARGET_FILE_ID_MISMATCH")
        if intent.identity_conflict or not intent.safe_attribution:
            return terminal(PersistenceDisposition.HOLD_CONFLICT, "HOLD_VEHICLE_IDENTITY_UNRESOLVED")
        fields = set(intent.verified_delta)
        if fields & PROTECTED_FIELDS:
            return terminal(PersistenceDisposition.HOLD_CONFLICT, "HOLD_PROTECTED_FIELD_MUTATION")
        if fields - ALLOWED_FIELDS:
            return terminal(PersistenceDisposition.HOLD_CONFLICT, "HOLD_UNADMITTED_FIELD_MUTATION")
        if not fields:
            return terminal(PersistenceDisposition.NO_DELTA)
        if self.writer is None or self.writer.file_id != CANONICAL_WORKBENCH_FILE_ID:
            return terminal(
                PersistenceDisposition.PERSISTENCE_CAPABILITY_DEBT, "WORKBENCH_WRITER_UNAVAILABLE"
            )
        if self.builder is None:
            return terminal(
                PersistenceDisposition.PERSISTENCE_CAPABILITY_DEBT, "WORKBENCH_BUILDER_UNAVAILABLE"
            )
        digest = hashlib.sha256(json.dumps(
            intent.model_dump(mode="json"), ensure_ascii=False, sort_keys=True,
            separators=(",", ":"),
        ).encode()).hexdigest()
        try:
            receipt = self.writer.mutate(
                task_id=task_id,
                intent_sha256=digest,
                build_new_bytes=lambda preimage: self.builder.build(preimage, intent),
                verify_mutation=lambda preimage, output: self.builder.verify(preimage, output, intent)
                if preimage != output else None,
            )
        except (WorkbenchConflict, WorkbenchPostwriteMismatch) as exc:
            return terminal(PersistenceDisposition.HOLD_CONFLICT, str(exc))
        except (WorkbenchCapabilityDebt, OSError, TimeoutError) as exc:
            return terminal(PersistenceDisposition.PERSISTENCE_CAPABILITY_DEBT, type(exc).__name__)
        if receipt.state not in {"WRITE_AND_READBACK_PASS", "NO_DELTA"}:
            return terminal(PersistenceDisposition.HOLD_CONFLICT, "WORKBENCH_RECEIPT_INVALID")
        return PersistenceReceipt(
            state=PersistenceDisposition(receipt.state), task_id=task_id,
            file_id=receipt.file_id, preimage_version=receipt.preimage_version,
            preimage_sha256=receipt.preimage_sha256,
            postwrite_version=receipt.postwrite_version,
            postwrite_sha256=receipt.postwrite_sha256,
        )
