from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class RuntimeIdentity:
    provider: str
    git_commit: str | None
    git_branch: str | None
    repo_slug: str | None

    def model_dump(self) -> dict[str, str | None]:
        return asdict(self)


def read_runtime_identity(environ: Mapping[str, str] | None = None) -> RuntimeIdentity:
    env = environ if environ is not None else os.environ
    if env.get("RENDER"):
        return RuntimeIdentity(
            provider="RENDER",
            git_commit=env.get("RENDER_GIT_COMMIT") or None,
            git_branch=env.get("RENDER_GIT_BRANCH") or None,
            repo_slug=env.get("RENDER_GIT_REPO_SLUG") or None,
        )
    return RuntimeIdentity(
        provider="LOCAL_OR_UNKNOWN",
        git_commit=None,
        git_branch=None,
        repo_slug=None,
    )
