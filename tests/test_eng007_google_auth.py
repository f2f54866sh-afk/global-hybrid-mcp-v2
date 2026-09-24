from __future__ import annotations

import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from global_hybrid_v2.google_auth import (
    GoogleAuthUnavailable,
    ServiceAccountAccessTokenProvider,
    ServiceAccountIdentity,
)


def _identity():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_key = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    return ServiceAccountIdentity(
        client_email="vehicle@example.iam.gserviceaccount.com",
        private_key=private_key,
        private_key_id="key-1",
    )


class Exchange:
    def __init__(self):
        self.calls = []
        self.fail = False

    def exchange(self, assertion):
        self.calls.append(assertion)
        if self.fail:
            raise OSError("unavailable")
        return {"access_token": f"token-{len(self.calls)}", "expires_in": 3600}


def test_service_account_token_is_acquired_reused_and_refreshed():
    now = [1_000.0]
    exchange = Exchange()
    provider = ServiceAccountAccessTokenProvider(
        _identity(), exchange=exchange, clock=lambda: now[0]
    )
    assert provider() == "token-1"
    assert provider() == "token-1"
    assert len(exchange.calls) == 1
    now[0] += 3_541
    assert provider() == "token-2"
    assert len(exchange.calls) == 2
    header, claim, signature = exchange.calls[0].split(".")
    assert header and claim and signature


def test_expired_token_refresh_failure_holds_without_static_fallback(caplog):
    now = [1_000.0]
    exchange = Exchange()
    provider = ServiceAccountAccessTokenProvider(
        _identity(), exchange=exchange, clock=lambda: now[0]
    )
    token = provider()
    now[0] += 3_541
    exchange.fail = True
    with pytest.raises(GoogleAuthUnavailable, match="refresh failed"):
        provider()
    assert token not in caplog.text
    exchange.fail = False
    assert provider() == "token-3"


def test_only_service_account_credential_schema_is_admitted():
    with pytest.raises(GoogleAuthUnavailable):
        ServiceAccountIdentity.from_json(json.dumps({"type": "authorized_user"}))
