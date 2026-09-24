from __future__ import annotations

import base64
import json
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


class GoogleAuthUnavailable(RuntimeError): ...


class GoogleAccessTokenProvider(Protocol):
    def __call__(self) -> str: ...


class GoogleTokenExchange(Protocol):
    def exchange(self, assertion: str) -> dict: ...


class GoogleOAuthTokenExchange:
    def __init__(self, *, timeout: float = 15):
        self.timeout = timeout

    def exchange(self, assertion: str) -> dict:
        request = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=urllib.parse.urlencode(
                {
                    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                    "assertion": assertion,
                }
            ).encode(),
            method="POST",
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.load(response)


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


@dataclass(frozen=True)
class ServiceAccountIdentity:
    client_email: str
    private_key: str
    private_key_id: str

    @classmethod
    def from_json(cls, raw: str) -> ServiceAccountIdentity:
        try:
            payload = json.loads(raw)
            if payload.get("type") != "service_account":
                raise ValueError
            return cls(
                client_email=payload["client_email"],
                private_key=payload["private_key"],
                private_key_id=payload["private_key_id"],
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise GoogleAuthUnavailable("invalid Google service-account credential") from exc


class ServiceAccountAccessTokenProvider:
    scope = "https://www.googleapis.com/auth/spreadsheets"

    def __init__(
        self,
        identity: ServiceAccountIdentity,
        *,
        exchange: GoogleTokenExchange | None = None,
        clock: Callable[[], float] = time.time,
        refresh_margin_seconds: int = 60,
    ):
        self.identity = identity
        self.exchange = exchange or GoogleOAuthTokenExchange()
        self.clock = clock
        self.refresh_margin_seconds = refresh_margin_seconds
        self._token: str | None = None
        self._expires_at = 0.0

    def __call__(self) -> str:
        now = self.clock()
        if self._token is not None and now < self._expires_at - self.refresh_margin_seconds:
            return self._token
        try:
            response = self.exchange.exchange(self._assertion(now))
            token = response["access_token"]
            expires_in = int(response["expires_in"])
            if not isinstance(token, str) or not token or expires_in <= self.refresh_margin_seconds:
                raise ValueError
        except Exception as exc:
            self._token = None
            self._expires_at = 0.0
            raise GoogleAuthUnavailable("Google service-account token refresh failed") from exc
        self._token = token
        self._expires_at = now + expires_in
        return token

    def _assertion(self, now: float) -> str:
        issued_at = int(now)
        header = {"alg": "RS256", "kid": self.identity.private_key_id, "typ": "JWT"}
        claim = {
            "iss": self.identity.client_email,
            "scope": self.scope,
            "aud": "https://oauth2.googleapis.com/token",
            "iat": issued_at,
            "exp": issued_at + 3600,
        }
        encoded = ".".join(
            _b64url(json.dumps(item, separators=(",", ":"), sort_keys=True).encode())
            for item in (header, claim)
        )
        key = serialization.load_pem_private_key(self.identity.private_key.encode(), password=None)
        signature = key.sign(encoded.encode(), padding.PKCS1v15(), hashes.SHA256())
        return f"{encoded}.{_b64url(signature)}"
