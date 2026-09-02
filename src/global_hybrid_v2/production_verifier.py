from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

EXPECTED_OWNERS = {
    "GLOBAL",
    "SALES_HUMAN",
    "LIBRARY_FACT",
    "VISUAL",
    "EXECUTION",
}
EXPECTED_REPO_SLUG = "f2f54866sh-afk/global-hybrid-mcp-v2"


class ProductionVerificationError(RuntimeError):
    pass


def _read_json(
    url: str,
    *,
    opener: Callable[..., Any],
) -> dict[str, Any]:
    request = Request(url, headers={"Accept": "application/json"})
    try:
        with opener(request, timeout=30) as response:
            if response.status != 200:
                raise ProductionVerificationError("PRODUCTION_HTTP_ERROR")
            payload = json.loads(response.read().decode("utf-8"))
    except ProductionVerificationError:
        raise
    except Exception as exc:
        raise ProductionVerificationError("PRODUCTION_HTTP_ERROR") from exc
    if not isinstance(payload, dict):
        raise ProductionVerificationError("PRODUCTION_RESPONSE_INVALID")
    return payload


def verify_production(
    *,
    base_url: str | None,
    expected_commit: str | None,
    opener: Callable[..., Any] = urlopen,
) -> dict[str, Any]:
    normalized_url = (base_url or "").strip().rstrip("/")
    parsed = urlparse(normalized_url)
    if not normalized_url or parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ProductionVerificationError("PRODUCTION_IDENTITY_UNBOUND")
    expected_sha = (expected_commit or "").strip()
    if not expected_sha:
        raise ProductionVerificationError("PRODUCTION_EXPECTED_COMMIT_UNBOUND")

    health = _read_json(f"{normalized_url}/health", opener=opener)
    if health.get("ok") is not True:
        raise ProductionVerificationError("PRODUCTION_HEALTH_INVALID")
    if health.get("live_execution") is not False:
        raise ProductionVerificationError("PRODUCTION_LIVE_EXECUTION_ENABLED")

    ready = _read_json(f"{normalized_url}/ready", opener=opener)
    if ready.get("ready") is not True:
        raise ProductionVerificationError("PRODUCTION_READINESS_INVALID")
    resolved_owners = ready.get("resolved_owners")
    if not isinstance(resolved_owners, list) or set(resolved_owners) != EXPECTED_OWNERS:
        raise ProductionVerificationError("PRODUCTION_OWNER_SET_MISMATCH")
    if len(resolved_owners) != len(EXPECTED_OWNERS):
        raise ProductionVerificationError("PRODUCTION_OWNER_SET_MISMATCH")

    runtime = ready.get("runtime")
    if not isinstance(runtime, dict):
        raise ProductionVerificationError("PRODUCTION_ATTESTATION_MISSING")
    if runtime.get("provider") != "RENDER":
        raise ProductionVerificationError("PRODUCTION_PROVIDER_MISMATCH")
    if runtime.get("repo_slug") != EXPECTED_REPO_SLUG:
        raise ProductionVerificationError("PRODUCTION_REPO_MISMATCH")
    if runtime.get("git_commit") != expected_sha:
        raise ProductionVerificationError("PRODUCTION_COMMIT_MISMATCH")

    return {
        "verified": True,
        "base_url": normalized_url,
        "git_commit": expected_sha,
        "repo_slug": EXPECTED_REPO_SLUG,
        "resolved_owners": resolved_owners,
    }


def main() -> None:
    try:
        result = verify_production(
            base_url=os.environ.get("PRODUCTION_BASE_URL"),
            expected_commit=os.environ.get("EXPECTED_GIT_COMMIT") or os.environ.get("GITHUB_SHA"),
        )
    except ProductionVerificationError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
