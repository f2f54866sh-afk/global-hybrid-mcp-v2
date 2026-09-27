from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol


class WorkbenchCapabilityDebt(RuntimeError): ...
class WorkbenchConflict(RuntimeError): ...
class WorkbenchPostwriteMismatch(RuntimeError): ...


class DriveTransport(Protocol):
    def metadata(self, file_id: str) -> dict: ...
    def download(self, file_id: str) -> bytes: ...
    def replace(self, file_id: str, payload: bytes, mime_type: str) -> dict: ...


class ClaimTransport(Protocol):
    def claim(self, payload: dict) -> dict: ...
    def complete(self, payload: dict) -> dict: ...
    def fail(self, payload: dict) -> dict: ...


@dataclass(frozen=True)
class WorkbenchWriteReceipt:
    state: str
    file_id: str
    preimage_version: str
    preimage_sha256: str
    postwrite_version: str | None = None
    postwrite_sha256: str | None = None
    claim_id: str | None = None


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class DriveXlsxWorkbenchPort:
    MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    def __init__(self, *, file_id: str, drive: DriveTransport, claims: ClaimTransport):
        if not file_id.strip():
            raise ValueError("WORKBENCH_FILE_ID_REQUIRED")
        self.file_id = file_id
        self.drive = drive
        self.claims = claims

    def write(self, *, task_id: str, intent_sha256: str, new_bytes: bytes) -> WorkbenchWriteReceipt:
        meta = self.drive.metadata(self.file_id)
        pre_version = str(meta.get("version") or "")
        if not pre_version:
            raise WorkbenchCapabilityDebt("DRIVE_VERSION_UNAVAILABLE")
        pre_bytes = self.drive.download(self.file_id)
        pre_sha = sha256_hex(pre_bytes)
        if pre_bytes == new_bytes:
            return WorkbenchWriteReceipt("NO_DELTA", self.file_id, pre_version, pre_sha)

        claim_id = hashlib.sha256(
            f"{self.file_id}:{pre_version}:{pre_sha}:{intent_sha256}:{task_id}".encode()
        ).hexdigest()
        claim = self.claims.claim({
            "claim_id": claim_id,
            "file_id": self.file_id,
            "preimage_version": pre_version,
            "preimage_sha256": pre_sha,
            "intent_sha256": intent_sha256,
            "task_id": task_id,
        })
        if claim.get("state") == "IDEMPOTENT_SUCCESS":
            return WorkbenchWriteReceipt(
                "WRITE_AND_READBACK_PASS",
                self.file_id,
                pre_version,
                pre_sha,
                str(claim.get("postwrite_version") or "") or None,
                claim.get("postwrite_sha256"),
                claim_id,
            )
        if claim.get("state") != "CLAIMED":
            raise WorkbenchConflict(claim.get("blocker") or "WORKBENCH_WRITE_CLAIM_REJECTED")

        fresh_meta = self.drive.metadata(self.file_id)
        fresh_version = str(fresh_meta.get("version") or "")
        fresh_bytes = self.drive.download(self.file_id)
        if fresh_version != pre_version or sha256_hex(fresh_bytes) != pre_sha:
            self.claims.fail({"claim_id": claim_id, "blocker": "HOLD_STALE_PREIMAGE"})
            raise WorkbenchConflict("HOLD_STALE_PREIMAGE")

        expected_post_sha = sha256_hex(new_bytes)
        self.drive.replace(self.file_id, new_bytes, self.MIME)
        post_meta = self.drive.metadata(self.file_id)
        post_version = str(post_meta.get("version") or "")
        post_bytes = self.drive.download(self.file_id)
        post_sha = sha256_hex(post_bytes)
        if not post_version or post_version == pre_version or post_sha != expected_post_sha:
            self.claims.fail({"claim_id": claim_id, "blocker": "HOLD_POSTWRITE_MISMATCH"})
            raise WorkbenchPostwriteMismatch("HOLD_POSTWRITE_MISMATCH")

        complete = self.claims.complete({
            "claim_id": claim_id,
            "postwrite_version": post_version,
            "postwrite_sha256": post_sha,
            "result_state": "WRITE_AND_READBACK_PASS",
        })
        if complete.get("state") not in {"COMPLETED", "IDEMPOTENT_SUCCESS"}:
            raise WorkbenchCapabilityDebt("WORKBENCH_CLAIM_COMPLETION_FAILED")
        return WorkbenchWriteReceipt(
            "WRITE_AND_READBACK_PASS",
            self.file_id,
            pre_version,
            pre_sha,
            post_version,
            post_sha,
            claim_id,
        )
