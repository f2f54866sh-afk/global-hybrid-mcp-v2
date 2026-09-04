from global_hybrid_v2.contracts import FailureLocus
from global_hybrid_v2.governance.failure_locus import (
    classify_failure_locus,
    may_reassess_platform,
    may_reopen_existing,
    may_repair,
)


def test_host_recurrence_is_parked_without_repair():
    locus = classify_failure_locus(entered_user_controlled_runtime=False, platform_bypass=True)
    assert locus is FailureLocus.HOST_PLATFORM
    assert not may_repair(locus=locus)
    assert not may_reopen_existing(locus=locus, matching_scope_regression=True)


def test_owned_matching_regression_can_reopen():
    locus = classify_failure_locus(entered_user_controlled_runtime=True)
    assert may_repair(locus=locus)
    assert may_reopen_existing(locus=locus, matching_scope_regression=True)


def test_unknown_locus_is_evidence_only():
    locus = classify_failure_locus(entered_user_controlled_runtime=False)
    assert locus is FailureLocus.UNKNOWN_LOCUS
    assert not may_repair(locus=locus)


def test_contradictory_runtime_and_platform_evidence_is_unknown():
    assert classify_failure_locus(
        entered_user_controlled_runtime=True, platform_bypass=True
    ) is FailureLocus.UNKNOWN_LOCUS


def test_platform_reassessment_does_not_authorize_repair():
    locus = FailureLocus.HOST_PLATFORM
    assert may_reassess_platform(
        locus=locus, fresh_platform_capability_change_evidence=True
    )
    assert not may_repair(locus=locus)
