"""Server-owned task classification and short-lived MCP transport admission."""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import threading
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


class IngressAdmissionError(ValueError):
    pass


class IngressTaskClass(StrEnum):
    COMPANY_COMMERCIAL_MATCHING = "COMPANY_COMMERCIAL_MATCHING"
    ORDINARY = "ORDINARY"


class ServerTaskClassifier(Protocol):
    def classify(self, *, request_text: str, evidence_digest: str) -> IngressTaskClass: ...


class NonceClaimStore(Protocol):
    def claim(self, nonce: str, valid_until: datetime) -> bool: ...


class InMemoryNonceClaimStore:
    """Isolated-test implementation; production requires a shared durable claim store."""

    def __init__(self) -> None:
        self._seen: dict[str, datetime] = {}
        self._lock = threading.Lock()

    def claim(self, nonce: str, valid_until: datetime) -> bool:
        with self._lock:
            now = datetime.now(UTC)
            self._seen = {key: expiry for key, expiry in self._seen.items() if expiry >= now}
            if nonce in self._seen:
                return False
            self._seen[nonce] = valid_until
            return True


def sha256_task(request_text: str, intent: str) -> str:
    payload = json.dumps(
        {"request_text": request_text, "intent": intent}, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class IngressTurnBinding(BaseModel):
    conversation_id: str = Field(min_length=1)
    turn_id: str = Field(min_length=1)
    task_class: IngressTaskClass
    intent: str = Field(min_length=1)
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    issued_at: datetime
    valid_until: datetime
    audience: str = Field(min_length=1)
    server: str = Field(min_length=1)
    nonce: str = Field(min_length=1)

    @model_validator(mode="after")
    def valid_window(self) -> IngressTurnBinding:
        if self.issued_at.tzinfo is None or self.valid_until.tzinfo is None:
            raise ValueError("turn binding timestamps must be timezone-aware")
        if not self.issued_at < self.valid_until <= self.issued_at + timedelta(minutes=5):
            raise ValueError("turn binding TTL must be positive and at most five minutes")
        return self

    @property
    def task_scope(self) -> str:
        return f"conversation:{self.conversation_id}:turn:{self.turn_id}"


class IngressTurnTokenCodec:
    """Issue and verify HMAC-bound Authorization credentials outside model arguments."""

    def __init__(
        self,
        *,
        key: bytes,
        audience: str,
        server: str,
        replay_store: NonceClaimStore | None = None,
    ) -> None:
        if len(key) < 32:
            raise ValueError("turn binding key must be at least 32 bytes")
        if not audience.strip() or not server.strip():
            raise ValueError("audience and server are required")
        self._key = key
        self.audience = audience
        self.server = server
        self.replay_store = replay_store

    def issue(
        self,
        *,
        conversation_id: str,
        turn_id: str,
        task_class: IngressTaskClass,
        request_text: str,
        intent: str,
        evidence_digest: str,
        now: datetime | None = None,
    ) -> str:
        current = now or datetime.now(UTC)
        binding = IngressTurnBinding(
            conversation_id=conversation_id,
            turn_id=turn_id,
            task_class=task_class,
            intent=intent,
            request_digest=sha256_task(request_text, intent),
            evidence_digest=evidence_digest,
            issued_at=current,
            valid_until=current + timedelta(minutes=5),
            audience=self.audience,
            server=self.server,
            nonce=uuid4().hex,
        )
        payload = json.dumps(
            binding.model_dump(mode="json"), sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        encoded = base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")
        signature = hmac.new(self._key, encoded.encode("ascii"), hashlib.sha256).hexdigest()
        return f"{encoded}.{signature}"

    def verify_authorization(
        self,
        authorization: str | None,
        *,
        request_text: str,
        intent: str,
        now: datetime | None = None,
    ) -> IngressTurnBinding:
        if not authorization or not authorization.startswith("Bearer "):
            raise IngressAdmissionError("INGRESS_AUTHORIZATION_MISSING")
        token = authorization[7:]
        if len(token) > 8192:
            raise IngressAdmissionError("INGRESS_TOKEN_INVALID")
        try:
            encoded, signature = token.split(".")
            expected = hmac.new(self._key, encoded.encode("ascii"), hashlib.sha256).hexdigest()
            if len(signature) != 64 or not hmac.compare_digest(signature, expected):
                raise IngressAdmissionError("INGRESS_TOKEN_INVALID")
            padded = encoded + "=" * (-len(encoded) % 4)
            binding = IngressTurnBinding.model_validate_json(base64.urlsafe_b64decode(padded))
        except (ValueError, UnicodeError, binascii.Error) as exc:
            if isinstance(exc, IngressAdmissionError):
                raise
            raise IngressAdmissionError("INGRESS_TOKEN_INVALID") from exc
        current = now or datetime.now(UTC)
        if binding.audience != self.audience or binding.server != self.server:
            raise IngressAdmissionError("INGRESS_TOKEN_AUDIENCE_MISMATCH")
        if current < binding.issued_at or current > binding.valid_until:
            raise IngressAdmissionError("INGRESS_TOKEN_EXPIRED")
        if binding.intent != intent or binding.request_digest != sha256_task(request_text, intent):
            raise IngressAdmissionError("INGRESS_REQUEST_DIGEST_MISMATCH")
        if self.replay_store is None:
            raise IngressAdmissionError("INGRESS_REPLAY_STORE_UNAVAILABLE")
        try:
            claimed = self.replay_store.claim(binding.nonce, binding.valid_until)
        except Exception as exc:
            raise IngressAdmissionError("INGRESS_REPLAY_STORE_UNAVAILABLE") from exc
        if not claimed:
            raise IngressAdmissionError("INGRESS_TOKEN_REPLAYED")
        return binding
