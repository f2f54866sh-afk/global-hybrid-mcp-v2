import json

import pytest

from global_hybrid_v2.contracts import (
    AuthoritySnapshot,
    ContextClass,
    ContextItem,
    ContextOrigin,
    DomainResult,
    EffectType,
    Intent,
    MaterialChangeReason,
    Owner,
    ResearchEvidenceSource,
    RetryContext,
    TaskContract,
    TaskRequest,
    TransientRetryEvidence,
)
from global_hybrid_v2.governance.authority import AuthorityResolver
from global_hybrid_v2.governance.repeat_action import REPEAT_BLOCKED_NO_NEW_EVIDENCE
from global_hybrid_v2.runtime.dispatcher import Dispatcher
from global_hybrid_v2.runtime.trace import TraceBus


class _StaticAuthority(AuthorityResolver):
    def __init__(self):
        pass

    def resolve(self) -> AuthoritySnapshot:
        return AuthoritySnapshot(entries={})


class _CountingDomain:
    def __init__(self):
        self.calls = 0

    def run(self, contract: TaskContract) -> DomainResult:
        self.calls += 1
        return DomainResult(owner=contract.owner, status="DONE", output="completed")


def _dispatch(
    domain: _CountingDomain,
    *,
    effect: EffectType = EffectType.EXTERNAL_WRITE,
    retry_context: RetryContext | None,
):
    dispatcher = Dispatcher(
        authority=_StaticAuthority(),
        domains={Owner.EXECUTION: domain},
        trace=TraceBus(),
    )
    mutation = effect in {
        EffectType.EXTERNAL_WRITE,
        EffectType.FILE_WRITE,
        EffectType.IMAGE_GENERATE,
    }
    target_system = "repeat-action-test" if mutation else None
    action_class = effect.value if mutation else None
    context = (
        [
            ContextItem(
                id="repeat-action-current-capability",
                origin=ContextOrigin.CURRENT_TOOL_RESULT,
                context_class=ContextClass.CURRENT_CAPABILITY_FACT,
                purpose="admitted current capability for repeat-action testing",
                task_scope="repeat-action",
                payload={
                    "target_system": target_system,
                    "action_class": action_class,
                },
                provenance=["test:current-runtime-readback"],
            )
        ]
        if mutation
        else []
    )
    return dispatcher.dispatch(
        TaskRequest(
            request_text="perform operation",
            intent=Intent.EXECUTION,
            effects=[effect],
            retry_context=retry_context,
            target_system=target_system,
            action_class=action_class,
            context=context,
        )
    )


def _failed_retry(*, reasons: list[str] | None = None) -> RetryContext:
    return RetryContext(
        operation_key="github:write:repository-settings",
        prior_failure_signature="HTTP-403:request-42",
        material_change_reasons=reasons or [],
    )


def test_same_failed_side_effect_without_material_change_is_blocked(capsys):
    domain = _CountingDomain()

    result = _dispatch(domain, retry_context=_failed_retry())
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    gate = next(event for event in events if event["stage"] == "repeat_action_gate")

    assert result.status == REPEAT_BLOCKED_NO_NEW_EVIDENCE
    assert domain.calls == 0
    assert gate["decision"] == "DENY"
    assert gate["metadata"] == {
        "operation_key": "github:write:repository-settings",
        "prior_failure_signature_present": True,
        "material_change_reasons": [],
        "transient_retry_evidence_present": False,
    }


@pytest.mark.parametrize(
    "reason",
    [
        MaterialChangeReason.CODE_CHANGED,
        MaterialChangeReason.CONFIG_CHANGED,
        MaterialChangeReason.ENVIRONMENT_CHANGED,
        MaterialChangeReason.INPUT_CHANGED,
        MaterialChangeReason.DIAGNOSTIC_INSTRUMENTATION_CHANGED,
        MaterialChangeReason.DEPENDENCY_STATE_CHANGED,
    ],
)
def test_admitted_material_change_allows_repeat(reason, capsys):
    domain = _CountingDomain()

    result = _dispatch(domain, retry_context=_failed_retry(reasons=[reason.value]))
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    gate = next(event for event in events if event["stage"] == "repeat_action_gate")

    assert result.status == "DONE"
    assert domain.calls == 1
    assert gate["decision"] == "PASS"
    assert gate["metadata"]["material_change_reasons"] == [reason.value]


def test_retry_language_alone_is_not_a_material_change():
    domain = _CountingDomain()

    result = _dispatch(domain, retry_context=_failed_retry(reasons=["try again"]))

    assert result.status == REPEAT_BLOCKED_NO_NEW_EVIDENCE
    assert domain.calls == 0


def test_verified_transient_retry_evidence_allows_repeat(capsys):
    domain = _CountingDomain()
    context = _failed_retry()
    context.transient_retry_evidence = TransientRetryEvidence(
        source=ResearchEvidenceSource.CURRENT_RUNTIME_READBACK,
        reference="provider-status:request-43",
        observed_result="Current provider status confirms the transient outage cleared.",
        verified=True,
    )

    result = _dispatch(domain, retry_context=context)
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    gate = next(event for event in events if event["stage"] == "repeat_action_gate")

    assert result.status == "DONE"
    assert domain.calls == 1
    assert gate["metadata"]["transient_retry_evidence_present"] is True
    assert gate["metadata"]["material_change_reasons"] == [
        MaterialChangeReason.VERIFIED_TRANSIENT_RETRY_CONDITION.value
    ]


def test_unverified_transient_retry_evidence_is_blocked():
    domain = _CountingDomain()
    context = _failed_retry(
        reasons=[MaterialChangeReason.VERIFIED_TRANSIENT_RETRY_CONDITION.value]
    )
    context.transient_retry_evidence = TransientRetryEvidence(
        source=ResearchEvidenceSource.CURRENT_RUNTIME_READBACK,
        reference="provider-status:request-43",
        observed_result="A transient recovery was suggested but not verified.",
    )

    result = _dispatch(domain, retry_context=context)

    assert result.status == REPEAT_BLOCKED_NO_NEW_EVIDENCE
    assert domain.calls == 0


def test_no_prior_failure_allows_side_effect():
    domain = _CountingDomain()
    context = RetryContext(operation_key="github:write:repository-settings")

    result = _dispatch(domain, retry_context=context)

    assert result.status == "DONE"
    assert domain.calls == 1


@pytest.mark.parametrize("effect", [EffectType.READ_ONLY, EffectType.EXTERNAL_READ])
def test_non_side_effects_are_unaffected(effect):
    domain = _CountingDomain()

    result = _dispatch(domain, effect=effect, retry_context=_failed_retry())

    assert result.status == "DONE"
    assert domain.calls == 1
