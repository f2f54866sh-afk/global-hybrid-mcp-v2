import json

import pytest

from global_hybrid_v2.production_verifier import (
    ProductionVerificationError,
    verify_production,
)

BASE_URL = "https://production.example"
EXPECTED_SHA = "a" * 40


class _Response:
    status = 200

    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def _opener(
    *,
    provider="RENDER",
    repo_slug="f2f54866sh-afk/global-hybrid-mcp-v2",
    git_commit=EXPECTED_SHA,
):
    payloads = {
        f"{BASE_URL}/health": {
            "ok": True,
            "live_execution": False,
        },
        f"{BASE_URL}/ready": {
            "ready": True,
            "resolved_owners": [
                "GLOBAL",
                "SALES_HUMAN",
                "LIBRARY_FACT",
                "VISUAL",
                "EXECUTION",
            ],
            "runtime": {
                "provider": provider,
                "git_commit": git_commit,
                "git_branch": "main",
                "repo_slug": repo_slug,
            },
        },
    }

    def open_request(request, *, timeout):
        assert timeout == 30
        return _Response(payloads[request.full_url])

    return open_request


def test_production_verifier_passes_matching_attestation():
    result = verify_production(
        base_url=BASE_URL,
        expected_commit=EXPECTED_SHA,
        opener=_opener(),
    )

    assert result["verified"] is True
    assert result["git_commit"] == EXPECTED_SHA


def test_production_verifier_fails_when_identity_is_unbound():
    with pytest.raises(ProductionVerificationError, match="PRODUCTION_IDENTITY_UNBOUND"):
        verify_production(base_url=None, expected_commit=EXPECTED_SHA, opener=_opener())


@pytest.mark.parametrize(
    ("opener", "failure_code"),
    [
        (_opener(provider="LOCAL_OR_UNKNOWN"), "PRODUCTION_PROVIDER_MISMATCH"),
        (_opener(repo_slug="other/repository"), "PRODUCTION_REPO_MISMATCH"),
        (_opener(git_commit="b" * 40), "PRODUCTION_COMMIT_MISMATCH"),
    ],
)
def test_production_verifier_fails_on_attestation_mismatch(opener, failure_code):
    with pytest.raises(ProductionVerificationError, match=failure_code):
        verify_production(
            base_url=BASE_URL,
            expected_commit=EXPECTED_SHA,
            opener=opener,
        )
