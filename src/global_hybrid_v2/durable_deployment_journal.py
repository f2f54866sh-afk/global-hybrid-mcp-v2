"""R2-backed, CAS-anchored deployment receipt journal (candidate; no live binding)."""
from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import Protocol
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from global_hybrid_v2.media_deployment_sequence import (
    DEPLOYMENT_ORDER,
    PASS_STATE,
    DeploymentProgress,
    DeploymentReceipt,
    DeploymentReceiptAuthority,
    DeploymentStep,
)


class DeploymentJournalError(RuntimeError):
    pass


class JournalObjectStore(Protocol):
    def get(self, deployment_id: str, key: str) -> tuple[bytes, str] | None: ...
    def list_receipts(self, deployment_id: str) -> list[str]: ...
    def put_immutable(self, deployment_id: str, key: str, raw: bytes) -> str: ...
    def cas_head(self, deployment_id: str, key: str, raw: bytes, expected_etag: str | None) -> str: ...


class R2JournalHttpStore:
    """Control endpoint uses R2 conditional PUT and GET readback; no D1 dependency."""

    def __init__(self, *, base_url: str, write_secret: str) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme != "https" or not parsed.hostname or not write_secret:
            raise DeploymentJournalError("HOLD_DEPLOYMENT_JOURNAL_BINDING_INVALID")
        self.base_url = base_url.rstrip("/")
        self.write_secret = write_secret

    def _call(self, deployment_id: str, operation: str, **body: str) -> dict:
        request = Request(
            self.base_url + "/internal/control/deployment-journal",
            data=json.dumps({"deployment_id": deployment_id, "operation": operation, **body}).encode(),
            headers={"Authorization": f"Bearer {self.write_secret}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=10) as response:
                result = json.load(response)
        except Exception as exc:
            raise DeploymentJournalError("HOLD_DEPLOYMENT_JOURNAL_UNAVAILABLE") from exc
        if result.get("state") == "HOLD":
            raise DeploymentJournalError("HOLD_DEPLOYMENT_JOURNAL_UNAVAILABLE")
        return result

    def get(self, deployment_id: str, key: str) -> tuple[bytes, str] | None:
        result = self._call(deployment_id, "GET", key=key)
        if result.get("state") == "MISS":
            return None
        if result.get("state") != "HIT" or result.get("key") != key or not result.get("etag"):
            raise DeploymentJournalError("HOLD_DEPLOYMENT_JOURNAL_READBACK_INVALID")
        try:
            return base64.b64decode(result["raw_base64"], validate=True), result["etag"]
        except (KeyError, ValueError) as exc:
            raise DeploymentJournalError("HOLD_DEPLOYMENT_JOURNAL_READBACK_INVALID") from exc

    def list_receipts(self, deployment_id: str) -> list[str]:
        result = self._call(deployment_id, "LIST")
        if result.get("state") != "LIST" or not isinstance(result.get("keys"), list):
            raise DeploymentJournalError("HOLD_DEPLOYMENT_JOURNAL_LIST_INVALID")
        return result["keys"]

    def _write(self, deployment_id: str, operation: str, key: str, raw: bytes,
               expected_etag: str | None = None) -> str:
        payload = {"key": key, "raw_base64": base64.b64encode(raw).decode()}
        if expected_etag is not None:
            payload["expected_etag"] = expected_etag
        result = self._call(deployment_id, operation, **payload)
        if result.get("state") == "CAS_CONFLICT":
            raise DeploymentJournalError("HOLD_DEPLOYMENT_JOURNAL_CAS_CONFLICT")
        if result.get("state") != "PUT_READBACK_PASS" or result.get("key") != key:
            raise DeploymentJournalError("HOLD_DEPLOYMENT_JOURNAL_READBACK_INVALID")
        fresh = self.get(deployment_id, key)
        if fresh is None or fresh[0] != raw or fresh[1] != result.get("etag"):
            raise DeploymentJournalError("HOLD_DEPLOYMENT_JOURNAL_READBACK_INVALID")
        return fresh[1]

    def put_immutable(self, deployment_id: str, key: str, raw: bytes) -> str:
        try:
            return self._write(deployment_id, "PUT_IMMUTABLE", key, raw)
        except DeploymentJournalError as exc:
            if str(exc) != "HOLD_DEPLOYMENT_JOURNAL_CAS_CONFLICT":
                raise
            found = self.get(deployment_id, key)
            if found and found[0] == raw:
                return found[1]
            raise DeploymentJournalError("HOLD_DEPLOYMENT_JOURNAL_COLLISION") from exc

    def cas_head(self, deployment_id: str, key: str, raw: bytes, expected_etag: str | None) -> str:
        return self._write(deployment_id, "CAS_HEAD", key, raw, expected_etag)


@dataclass(frozen=True)
class DeploymentHead:
    deployment_id: str
    target: str
    source_revision: str
    expected_preimage: str
    current_step: int
    latest_receipt_digest: str
    prior_head_etag: str | None
    state: str
    hold_reason: str | None


@dataclass(frozen=True)
class LoadedDeployment:
    progress: DeploymentProgress
    head: DeploymentHead
    head_etag: str

    @property
    def next_step(self) -> DeploymentStep | None:
        return self.progress.next_step if self.head.state == "ACTIVE" else None


class DurableDeploymentJournal:
    def __init__(self, store: JournalObjectStore, authority: DeploymentReceiptAuthority) -> None:
        self.store = store
        self.authority = authority

    @staticmethod
    def _prefix(deployment_id: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", deployment_id):
            raise DeploymentJournalError("HOLD_DEPLOYMENT_JOURNAL_SCOPE_INVALID")
        return f"__deployment__/rd021/{deployment_id}/"

    @classmethod
    def _receipt_key(cls, receipt: DeploymentReceipt, ordinal: int) -> str:
        prefix = cls._prefix(receipt.deployment_id)
        return f"{prefix}receipts/{ordinal:02d}-{receipt.step.value}-{receipt.digest}.json"

    @staticmethod
    def _receipt_bytes(receipt: DeploymentReceipt) -> bytes:
        return json.dumps(asdict(receipt), sort_keys=True, separators=(",", ":")).encode()

    @staticmethod
    def _head_bytes(head: DeploymentHead) -> bytes:
        return json.dumps(asdict(head), sort_keys=True, separators=(",", ":")).encode()

    def _verify_receipt(self, receipt: DeploymentReceipt, *, deployment_id: str,
                        target: str, source_revision: str, expected_preimage: str,
                        ordinal: int, prior_digest: str | None) -> None:
        if (receipt.deployment_id != deployment_id or receipt.target != target
            or receipt.source_revision != source_revision or receipt.expected_preimage != expected_preimage
            or ordinal >= len(DEPLOYMENT_ORDER) or receipt.step is not DEPLOYMENT_ORDER[ordinal]
            or receipt.previous_step_receipt_digest != prior_digest
            or not self.authority.verify(receipt)):
            raise DeploymentJournalError("HOLD_DEPLOYMENT_JOURNAL_INVALID")

    def load(self, deployment_id: str) -> LoadedDeployment:
        prefix = self._prefix(deployment_id)
        found_head = self.store.get(deployment_id, prefix + "head.json")
        keys = self.store.list_receipts(deployment_id)
        if found_head is None or not keys:
            raise DeploymentJournalError("HOLD_DEPLOYMENT_JOURNAL_INVALID")
        try:
            head = DeploymentHead(**json.loads(found_head[0]))
            if (head.deployment_id != deployment_id or head.state not in {"ACTIVE", "HOLD", "COMPLETE"}
                or not head.target or not head.source_revision or not head.expected_preimage
                or head.current_step != len(keys) - 1
                or (head.current_step > 1 and not head.prior_head_etag)
                or (head.state != "HOLD" and head.hold_reason is not None)):
                raise ValueError("head")
            receipts: list[DeploymentReceipt] = []
            prior = None
            for ordinal, key in enumerate(sorted(keys)):
                raw = self.store.get(deployment_id, key)
                if raw is None:
                    raise ValueError("gap")
                values = json.loads(raw[0])
                values["step"] = DeploymentStep(values["step"])
                receipt = DeploymentReceipt(**values)
                self._verify_receipt(
                    receipt, deployment_id=deployment_id, target=head.target,
                    source_revision=head.source_revision, expected_preimage=head.expected_preimage,
                    ordinal=ordinal, prior_digest=prior,
                )
                if key != self._receipt_key(receipt, ordinal) or raw[0] != self._receipt_bytes(receipt):
                    raise ValueError("receipt key or bytes")
                if ordinal < len(keys) - 1 and receipt.result_state != PASS_STATE[receipt.step]:
                    raise ValueError("failure before end")
                receipts.append(receipt)
                prior = receipt.digest
            if head.latest_receipt_digest != prior:
                raise ValueError("head digest")
            last = receipts[-1]
            if (head.state == "HOLD") != (last.result_state != PASS_STATE[last.step]):
                raise ValueError("head state")
            if head.state == "COMPLETE" and len(receipts) != len(DEPLOYMENT_ORDER):
                raise ValueError("incomplete")
            if head.state == "ACTIVE" and len(receipts) == len(DEPLOYMENT_ORDER):
                raise ValueError("complete state required")
            if head.state == "HOLD" and not head.hold_reason:
                raise ValueError("hold reason")
            progress = DeploymentProgress(
                deployment_id, head.target, head.source_revision, head.expected_preimage,
                tuple(receipts if head.state != "HOLD" else receipts[:-1]),
                head.hold_reason if head.state == "HOLD" else None,
            )
            return LoadedDeployment(progress, head, found_head[1])
        except (ValueError, TypeError, KeyError, AttributeError, DeploymentJournalError) as exc:
            raise DeploymentJournalError("HOLD_DEPLOYMENT_JOURNAL_INVALID") from exc

    def bootstrap(self, preflight: DeploymentReceipt, r2: DeploymentReceipt) -> LoadedDeployment:
        deployment_id = preflight.deployment_id
        prefix = self._prefix(deployment_id)
        self._verify_receipt(
            preflight, deployment_id=deployment_id, target=preflight.target,
            source_revision=preflight.source_revision, expected_preimage=preflight.expected_preimage,
            ordinal=0, prior_digest=None,
        )
        self._verify_receipt(
            r2, deployment_id=deployment_id, target=preflight.target,
            source_revision=preflight.source_revision, expected_preimage=preflight.expected_preimage,
            ordinal=1, prior_digest=preflight.digest,
        )
        if preflight.result_state != PASS_STATE[preflight.step] or r2.result_state != PASS_STATE[r2.step]:
            raise DeploymentJournalError("HOLD_DEPLOYMENT_BOOTSTRAP_NOT_PASS")
        if self.store.get(deployment_id, prefix + "head.json") is not None:
            raise DeploymentJournalError("HOLD_DEPLOYMENT_JOURNAL_ALREADY_STARTED")
        for ordinal, receipt in enumerate((preflight, r2)):
            self.store.put_immutable(deployment_id, self._receipt_key(receipt, ordinal),
                                     self._receipt_bytes(receipt))
        head = DeploymentHead(deployment_id, preflight.target, preflight.source_revision,
                              preflight.expected_preimage, 1, r2.digest, None, "ACTIVE", None)
        self.store.cas_head(deployment_id, prefix + "head.json", self._head_bytes(head), None)
        loaded = self.load(deployment_id)
        if loaded.next_step is not DeploymentStep.D1_MIGRATION:
            raise DeploymentJournalError("HOLD_DEPLOYMENT_BOOTSTRAP_READBACK_INVALID")
        return loaded

    def append(self, receipt: DeploymentReceipt) -> LoadedDeployment:
        loaded = self.load(receipt.deployment_id)
        if loaded.head.state != "ACTIVE" or loaded.next_step is not receipt.step:
            raise DeploymentJournalError("HOLD_DEPLOYMENT_STEP_NOT_ADMISSIBLE")
        ordinal = loaded.head.current_step + 1
        self._verify_receipt(
            receipt, deployment_id=receipt.deployment_id, target=loaded.head.target,
            source_revision=loaded.head.source_revision, expected_preimage=loaded.head.expected_preimage,
            ordinal=ordinal, prior_digest=loaded.head.latest_receipt_digest,
        )
        self.store.put_immutable(receipt.deployment_id, self._receipt_key(receipt, ordinal),
                                 self._receipt_bytes(receipt))
        passing = receipt.result_state == PASS_STATE[receipt.step]
        state = ("COMPLETE" if ordinal == len(DEPLOYMENT_ORDER) - 1 else "ACTIVE") if passing else "HOLD"
        head = DeploymentHead(
            receipt.deployment_id, receipt.target, receipt.source_revision, receipt.expected_preimage,
            ordinal, receipt.digest, loaded.head_etag, state,
            None if passing else receipt.result_state,
        )
        self.store.cas_head(receipt.deployment_id, self._prefix(receipt.deployment_id) + "head.json",
                            self._head_bytes(head), loaded.head_etag)
        return self.load(receipt.deployment_id)

    def hold_exception(self, deployment_id: str, error: Exception) -> LoadedDeployment:
        """Persist a fail-closed terminal from a server-side executor exception."""
        loaded = self.load(deployment_id)
        if loaded.next_step is None:
            raise DeploymentJournalError("HOLD_DEPLOYMENT_STEP_NOT_ADMISSIBLE")
        evidence = f"{type(error).__name__}:{error}".encode()
        receipt = self.authority._seal(
            deployment_id=deployment_id, step=loaded.next_step, target=loaded.head.target,
            source_revision=loaded.head.source_revision,
            expected_preimage=loaded.head.expected_preimage,
            result_state=f"HOLD_{type(error).__name__.upper()}",
            readback_evidence_digest=hashlib.sha256(evidence).hexdigest(),
            previous_step_receipt_digest=loaded.head.latest_receipt_digest,
        )
        return self.append(receipt)

    def require_d1_admissible(self, deployment_id: str) -> LoadedDeployment:
        loaded = self.load(deployment_id)
        if loaded.next_step is not DeploymentStep.D1_MIGRATION or loaded.head.current_step != 1:
            raise DeploymentJournalError("HOLD_D1_JOURNAL_NOT_ANCHORED")
        return loaded
