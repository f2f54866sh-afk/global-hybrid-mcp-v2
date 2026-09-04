"""Deterministic RC-01 failure ownership classification."""

from global_hybrid_v2.contracts import FailureLocus


def classify_failure_locus(
    *, entered_user_controlled_runtime: bool, platform_bypass: bool = False
) -> FailureLocus:
    if entered_user_controlled_runtime and platform_bypass:
        return FailureLocus.UNKNOWN_LOCUS
    if entered_user_controlled_runtime:
        return FailureLocus.OWNED_RUNTIME
    if platform_bypass:
        return FailureLocus.HOST_PLATFORM
    return FailureLocus.UNKNOWN_LOCUS


def may_reopen_existing(*, locus: FailureLocus, matching_scope_regression: bool) -> bool:
    return locus is FailureLocus.OWNED_RUNTIME and matching_scope_regression


def may_repair(*, locus: FailureLocus) -> bool:
    return locus is FailureLocus.OWNED_RUNTIME


def may_reassess_platform(*, locus: FailureLocus, fresh_platform_capability_change_evidence: bool) -> bool:
    return locus is FailureLocus.HOST_PLATFORM and fresh_platform_capability_change_evidence
