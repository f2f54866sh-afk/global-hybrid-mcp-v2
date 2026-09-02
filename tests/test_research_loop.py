import asyncio
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from mcp import Client
from mcp.types import TextContent

from global_hybrid_v2.adapters.mcp_server import create_mcp_server
from global_hybrid_v2.application import Application, create_application
from global_hybrid_v2.contracts import (
    AuthorityDocument,
    AuthorityDocumentRole,
    AuthorityEntry,
    AuthoritySnapshot,
    DomainResult,
    Intent,
    OutputClassification,
    Owner,
    ResearchAdmissionReceipt,
    ResearchAdmissionStatus,
    ResearchCoverage,
    ResearchEvidence,
    ResearchEvidenceSource,
    ResearchExecutionReceipt,
    ResearchExecutionStatus,
    ResearchProviderAvailability,
    ResearchRequest,
    TaskContract,
    TaskRequest,
)
from global_hybrid_v2.governance.authority import AuthorityResolver
from global_hybrid_v2.governance.egress import (
    UNKNOWN_WITH_EXACT_BLOCKER,
    ResponseEgressValidator,
)
from global_hybrid_v2.observer.witness import ReadOnlyWitness
from global_hybrid_v2.research import ResearchExecutor, UnavailableResearchPort
from global_hybrid_v2.runtime.deployment import read_runtime_identity
from global_hybrid_v2.runtime.dispatcher import (
    RESEARCH_COVERAGE_INSUFFICIENT,
    RESEARCH_MAX_ATTEMPTS_REACHED,
    RESEARCH_PROVIDER_EXECUTION_FAILED,
    RESEARCH_PROVIDER_UNAVAILABLE,
    RESEARCH_RECEIPT_INVALID,
    RESEARCH_REPEAT_BLOCKED_NO_NEW_INFORMATION,
    Dispatcher,
)
from global_hybrid_v2.runtime.trace import TraceBus
from global_hybrid_v2.settings import Settings

NOW = datetime(2026, 9, 3, 1, 0, tzinfo=UTC)
SCOPE = "current platform capability for the bounded architecture task"
REVISION = "GLOBAL_TEST_REVISION"


class _StaticAuthority(AuthorityResolver):
    def __init__(self):
        pass

    def resolve(self) -> AuthoritySnapshot:
        document = AuthorityDocument(
            name="GLOBAL",
            role=AuthorityDocumentRole.LIVE_AUTHORITY,
            revision=REVISION,
            path="GLOBAL_WINDOW_CANONICAL.md",
        )
        return AuthoritySnapshot(
            entries={
                Owner.GLOBAL: AuthorityEntry(
                    owner=Owner.GLOBAL,
                    normative_authority=document,
                )
            }
        )


def _admission_receipt() -> ResearchAdmissionReceipt:
    return ResearchAdmissionReceipt(
        status=ResearchAdmissionStatus.PASS,
        semantic_key=OutputClassification.CURRENT_PLATFORM_CAPABILITY,
        scope=SCOPE,
        issued_at=NOW - timedelta(minutes=1),
        valid_until=NOW + timedelta(minutes=10),
        evidence=[
            ResearchEvidence(
                source=ResearchEvidenceSource.CURRENT_OFFICIAL_DOCUMENTATION,
                reference="official:current-capability",
                observed_result="The current capability was verified from the source.",
            )
        ],
    )


class _CapabilityDomain:
    def __init__(self, *, initial_receipts: list[ResearchAdmissionReceipt] | None = None):
        self.initial_receipts = initial_receipts or []
        self.contracts: list[TaskContract] = []

    def run(self, contract: TaskContract) -> DomainResult:
        self.contracts.append(contract)
        receipts = (
            contract.research_admission_receipts
            if contract.research_admission_receipts
            else self.initial_receipts
        )
        return DomainResult(
            owner=Owner.GLOBAL,
            status="READY",
            output="Current platform capability is supported for this bounded task.",
            output_classifications={OutputClassification.CURRENT_PLATFORM_CAPABILITY},
            research_scope=SCOPE,
            research_admission_receipts=receipts,
            research_execution_receipts=contract.research_execution_receipts,
        )


class _FakeResearchPort:
    provider = "DETERMINISTIC_FAKE"
    availability = ResearchProviderAvailability.CALLABLE

    def __init__(
        self,
        factory: Callable[[ResearchRequest, int], ResearchExecutionReceipt | object],
    ):
        self.factory = factory
        self.requests: list[ResearchRequest] = []

    def execute(self, request: ResearchRequest) -> ResearchExecutionReceipt:
        self.requests.append(request)
        result = self.factory(request, len(self.requests))
        return result  # type: ignore[return-value]


def _execution_receipt(
    request: ResearchRequest,
    *,
    evidence: list[ResearchEvidence] | None = None,
    complete: bool = True,
    covered: set[OutputClassification] | None = None,
    status: ResearchExecutionStatus = ResearchExecutionStatus.PASS,
    error: str | None = None,
) -> ResearchExecutionReceipt:
    evidence = evidence if evidence is not None else [
        ResearchEvidence(
            source=ResearchEvidenceSource.CURRENT_OFFICIAL_DOCUMENTATION,
            reference="official:current-capability",
            observed_result="The current capability was verified from the source.",
        )
    ]
    return ResearchExecutionReceipt(
        request_id=request.request_id,
        provider="DETERMINISTIC_FAKE",
        started_at=NOW,
        completed_at=NOW + timedelta(seconds=1),
        status=status,
        queries_executed=request.queries,
        source_references=[item.reference for item in evidence],
        evidence=evidence,
        coverage=ResearchCoverage(
            complete=complete,
            covered_semantic_keys=(
                set(request.required_semantic_keys) if covered is None else covered
            ),
            unresolved_gaps=[] if complete else ["coverage incomplete"],
        ),
        error=error,
    )


def _dispatcher(
    domain: _CapabilityDomain,
    research: object,
    *,
    trace: TraceBus | None = None,
    dispatcher_type: type[Dispatcher] = Dispatcher,
) -> Dispatcher:
    return dispatcher_type(
        authority=_StaticAuthority(),
        domains={Owner.GLOBAL: domain},
        trace=trace or TraceBus(),
        egress=ResponseEgressValidator(clock=lambda: NOW, research_available=True),
        research_executor=ResearchExecutor(research),  # type: ignore[arg-type]
    )


def _request() -> TaskRequest:
    return TaskRequest(request_text="verify the current capability", intent=Intent.GOVERNANCE)


def test_sufficient_evidence_skips_research():
    domain = _CapabilityDomain(initial_receipts=[_admission_receipt()])
    provider = _FakeResearchPort(lambda request, _: _execution_receipt(request))

    result = _dispatcher(domain, provider).dispatch(_request())

    assert result.status == "READY"
    assert provider.requests == []
    assert len(domain.contracts) == 1


def test_production_composition_marks_research_provider_unavailable():
    application = create_application()

    assert (
        application.research_executor.availability
        is ResearchProviderAvailability.UNAVAILABLE
    )
    assert application.research_executor.provider == "UNAVAILABLE"


def test_callable_provider_runs_research_and_resumes_same_task(capsys):
    domain = _CapabilityDomain()
    provider = _FakeResearchPort(lambda request, _: _execution_receipt(request))

    result = _dispatcher(domain, provider).dispatch(_request())
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]

    assert result.status == "READY"
    assert len(provider.requests) == 1
    assert len(domain.contracts) == 2
    task_ids = {event["task_id"] for event in events}
    assert task_ids == {domain.contracts[0].task_id}
    assert domain.contracts[0].task_id == domain.contracts[1].task_id
    assert provider.requests[0].task_id == domain.contracts[0].task_id
    assert provider.requests[0].original_owner is Owner.GLOBAL
    assert provider.requests[0].authority_revision == REVISION
    stages = [event["stage"] for event in events]
    for stage in (
        "research_required",
        "research_request_created",
        "research_execution_started",
        "research_execution_completed",
        "research_evidence_admission",
        "task_resumed",
        "research_loop_closed",
    ):
        assert stage in stages


def test_mcp_dispatch_runs_the_same_automatic_research_loop():
    domain = _CapabilityDomain()
    provider = _FakeResearchPort(lambda request, _: _execution_receipt(request))
    authority = _StaticAuthority()
    trace = TraceBus()
    research_executor = ResearchExecutor(provider)
    dispatcher = Dispatcher(
        authority=authority,
        domains={Owner.GLOBAL: domain},
        trace=trace,
        egress=ResponseEgressValidator(clock=lambda: NOW, research_available=True),
        research_executor=research_executor,
    )
    application = Application(
        repo_root=Path.cwd(),
        settings=Settings(),
        authority=authority,
        research_executor=research_executor,
        runtime_identity=read_runtime_identity(),
        trace=trace,
        dispatcher=dispatcher,
    )
    server = create_mcp_server(application)

    async def scenario():
        async with Client(server) as client:
            return await client.call_tool(
                "dispatch_task",
                {
                    "payload": {
                        "request_text": "verify the current capability",
                        "intent": "governance",
                        "effects": ["read_only"],
                    }
                },
            )

    tool_result = asyncio.run(scenario())

    assert tool_result.is_error is False
    assert isinstance(tool_result.content[0], TextContent)
    assert json.loads(tool_result.content[0].text)["status"] == "READY"
    assert len(provider.requests) == 1


def test_coverage_insufficient_returns_exact_blocker():
    domain = _CapabilityDomain()
    provider = _FakeResearchPort(
        lambda request, _: _execution_receipt(request, complete=False, covered=set())
    )

    result = _dispatcher(domain, provider).dispatch(_request())

    assert result.status == UNKNOWN_WITH_EXACT_BLOCKER
    assert result.output["blocker"] == RESEARCH_COVERAGE_INSUFFICIENT
    assert len(domain.contracts) == 1


def test_provider_unavailable_returns_exact_blocker():
    domain = _CapabilityDomain()

    result = _dispatcher(domain, UnavailableResearchPort()).dispatch(_request())

    assert result.status == UNKNOWN_WITH_EXACT_BLOCKER
    assert result.output["blocker"] == RESEARCH_PROVIDER_UNAVAILABLE
    assert len(domain.contracts) == 1


def test_provider_failure_returns_exact_blocker():
    domain = _CapabilityDomain()
    provider = _FakeResearchPort(
        lambda request, _: _execution_receipt(
            request,
            evidence=[],
            status=ResearchExecutionStatus.FAILED,
            error="provider failed",
        )
    )

    result = _dispatcher(domain, provider).dispatch(_request())

    assert result.status == UNKNOWN_WITH_EXACT_BLOCKER
    assert result.output["blocker"] == RESEARCH_PROVIDER_EXECUTION_FAILED


def test_invalid_research_receipt_fails_closed():
    domain = _CapabilityDomain()
    provider = _FakeResearchPort(lambda _request, _call: {"status": "PASS"})

    result = _dispatcher(domain, provider).dispatch(_request())

    assert result.status == UNKNOWN_WITH_EXACT_BLOCKER
    assert result.output["blocker"] == RESEARCH_RECEIPT_INVALID


def test_pre_research_egress_suppresses_substantive_answer(capsys):
    domain = _CapabilityDomain()
    provider = _FakeResearchPort(lambda request, _: _execution_receipt(request))

    _dispatcher(domain, provider).dispatch(_request())
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]

    suppression_index = next(
        index
        for index, event in enumerate(events)
        if event["stage"] == "pre_research_egress_suppression"
    )
    execution_index = next(
        index
        for index, event in enumerate(events)
        if event["stage"] == "research_execution_started"
    )
    assert suppression_index < execution_index
    assert "Current platform capability is supported" not in json.dumps(
        events[: execution_index + 1]
    )


class _SameQueryDispatcher(Dispatcher):
    def _build_research_request(
        self,
        *,
        contract: TaskContract,
        scope: str,
        required: list[OutputClassification],
        authority_revision: str,
        attempt: int,
    ) -> ResearchRequest:
        request = super()._build_research_request(
            contract=contract,
            scope=scope,
            required=required,
            authority_revision=authority_revision,
            attempt=attempt,
        )
        if attempt == 1:
            self.first_queries = request.queries
            return request
        return request.model_copy(
            update={
                "queries": self.first_queries,
                "retrieval_strategy": "PRIMARY_CURRENT_SOURCE",
            }
        )


def _inadmissible_evidence() -> list[ResearchEvidence]:
    return [
        ResearchEvidence(
            source=ResearchEvidenceSource.CURRENT_USER_PROVIDED_OBSERVATION,
            reference="user observation",
            observed_result="The platform does not support this capability.",
        )
    ]


def test_same_research_without_material_change_is_not_repeated():
    domain = _CapabilityDomain()
    provider = _FakeResearchPort(
        lambda request, _: _execution_receipt(
            request,
            evidence=_inadmissible_evidence(),
        )
    )

    result = _dispatcher(
        domain,
        provider,
        dispatcher_type=_SameQueryDispatcher,
    ).dispatch(_request())

    assert result.output["blocker"] == RESEARCH_REPEAT_BLOCKED_NO_NEW_INFORMATION
    assert len(provider.requests) == 1


def test_second_materially_different_query_can_execute_and_pass():
    domain = _CapabilityDomain()

    def sequence(request: ResearchRequest, call: int) -> ResearchExecutionReceipt:
        evidence = _inadmissible_evidence() if call == 1 else None
        return _execution_receipt(request, evidence=evidence)

    provider = _FakeResearchPort(sequence)

    result = _dispatcher(domain, provider).dispatch(_request())

    assert result.status == "READY"
    assert len(provider.requests) == 2
    assert provider.requests[0].queries != provider.requests[1].queries
    assert provider.requests[0].retrieval_strategy != provider.requests[1].retrieval_strategy


def test_max_attempts_stops_after_two_materially_different_queries():
    domain = _CapabilityDomain()
    provider = _FakeResearchPort(
        lambda request, _: _execution_receipt(
            request,
            evidence=_inadmissible_evidence(),
        )
    )

    result = _dispatcher(domain, provider).dispatch(_request())

    assert result.output["blocker"] == RESEARCH_MAX_ATTEMPTS_REACHED
    assert len(provider.requests) == 2


def test_research_evidence_does_not_become_authority():
    domain = _CapabilityDomain()
    provider = _FakeResearchPort(lambda request, _: _execution_receipt(request))

    result = _dispatcher(domain, provider).dispatch(_request())

    assert "RESEARCH" not in {owner.value for owner in Owner}
    assert result.research_execution_receipts
    receipt_payload = result.research_execution_receipts[0].model_dump(mode="json")
    assert "normative_authority" not in receipt_payload
    assert domain.contracts[0].authority_snapshot_id == domain.contracts[1].authority_snapshot_id


def test_observer_only_observes_research_trace():
    witness = ReadOnlyWitness()
    trace = TraceBus(witness=witness)
    domain = _CapabilityDomain()
    provider = _FakeResearchPort(lambda request, _: _execution_receipt(request))

    result = _dispatcher(domain, provider, trace=trace).dispatch(_request())

    assert result.status == "READY"
    assert not {"write", "execute", "promote"}.intersection(dir(witness))
    assert len(provider.requests) == 1
