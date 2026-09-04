from global_hybrid_v2.contracts import FailureLocus
from global_hybrid_v2.governance.failure_locus import classify_failure_locus, may_reopen_existing, may_repair


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
