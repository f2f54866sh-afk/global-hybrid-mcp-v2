from __future__ import annotations

import json
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import SecretStr

from global_hybrid_v2.adapters.openai_research import (
    OPENAI_WEB_EVIDENCE_MISSING,
    OPENAI_WEB_OUTPUT_INVALID,
    OPENAI_WEB_PROVIDER,
    OPENAI_WEB_REQUEST_FAILED,
    OPENAI_WEB_SOURCES_MISSING,
    OpenAIWebResearchPort,
    configured_research_port,
)
from global_hybrid_v2.contracts import (
    OutputClassification,
    Owner,
    ResearchEvidenceSource,
    ResearchExecutionStatus,
    ResearchProviderAvailability,
    ResearchRequest,
)
from global_hybrid_v2.research import UnavailableResearchPort
from global_hybrid_v2.settings import Settings

REPO_ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 9, 3, 2, 0, tzinfo=UTC)
SOURCE_URL = "https://example.com/current-capability"
UNRETURNED_URL = "https://invented.invalid/not-returned"
SECRET = "sk-test-secret-must-never-escape"


class _FakeResponses:
    def __init__(self, result: Any = None, error: Exception | None = None):
        self.result = result
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.result


class _FakeClient:
    def __init__(self, result: Any = None, error: Exception | None = None):
        self.responses = _FakeResponses(result=result, error=error)


def _request(
    *keys: OutputClassification,
) -> ResearchRequest:
    required = list(keys) or [OutputClassification.CURRENT_PLATFORM_CAPABILITY]
    return ResearchRequest(
        task_id="task-1",
        original_owner=Owner.GLOBAL,
        original_task_scope="Do not forward this original user task to the provider.",
        research_scope="current platform capability for one bounded architecture decision",
        required_semantic_keys=required,
        queries=[f"Verify {item.value} from current sources" for item in required],
        allowed_source_classes=[
            ResearchEvidenceSource.CURRENT_OFFICIAL_DOCUMENTATION,
            ResearchEvidenceSource.CURRENT_WEB_SOURCE,
        ],
        authority_revision="GLOBAL_TEST_REVISION",
        attempt=1,
        retrieval_strategy="PRIMARY_CURRENT_SOURCE",
    )


def _response(
    *,
    evidence: list[dict[str, Any]] | None = None,
    unresolved: list[str] | None = None,
    sources: list[str] | None = None,
    status: str = "completed",
    output_text: str | None = None,
) -> dict[str, Any]:
    source_urls = [SOURCE_URL] if sources is None else sources
    payload = {
        "evidence": evidence
        if evidence is not None
        else [
            {
                "semantic_key": "CURRENT_PLATFORM_CAPABILITY",
                "observed_result": "The current capability is supported by the source.",
                "source_urls": [SOURCE_URL],
            }
        ],
        "unresolved_semantic_keys": unresolved or [],
    }
    return {
        "status": status,
        "output_text": json.dumps(payload) if output_text is None else output_text,
        "output": [
            {
                "type": "web_search_call",
                "action": {
                    "type": "search",
                    "query": "current capability query executed by the provider",
                    "sources": [
                        {"type": "url", "url": source_url}
                        for source_url in source_urls
                    ],
                },
            }
        ],
    }


def _port(client: _FakeClient) -> OpenAIWebResearchPort:
    return OpenAIWebResearchPort(
        model="gpt-test",
        api_key=SecretStr(SECRET),
        client=client,
        clock=lambda: NOW,
    )


def test_missing_api_key_is_unavailable():
    settings = Settings(
        research_provider="openai_web",
        research_model="gpt-test",
        openai_api_key=None,
    )

    provider = configured_research_port(settings)

    assert isinstance(provider, UnavailableResearchPort)
    assert provider.availability is ResearchProviderAvailability.UNAVAILABLE


def test_disabled_provider_is_unavailable():
    settings = Settings(
        research_provider="disabled",
        research_model="gpt-test",
        openai_api_key=SecretStr(SECRET),
    )

    provider = configured_research_port(settings)

    assert isinstance(provider, UnavailableResearchPort)
    assert provider.availability is ResearchProviderAvailability.UNAVAILABLE


def test_valid_config_is_callable_and_accepts_standard_openai_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", SECRET)
    settings = Settings(
        research_provider="openai_web",
        research_model="gpt-test",
    )

    provider = configured_research_port(settings)

    assert isinstance(provider, OpenAIWebResearchPort)
    assert provider.availability is ResearchProviderAvailability.CALLABLE
    assert settings.openai_api_key is not None
    assert settings.openai_api_key.get_secret_value() == SECRET
    assert SECRET not in repr(settings)


def test_api_success_uses_current_web_search_schema_and_captures_sources():
    client = _FakeClient(result=_response())

    receipt = _port(client).execute(_request())

    assert receipt.status is ResearchExecutionStatus.PASS
    assert receipt.provider == OPENAI_WEB_PROVIDER
    assert receipt.source_references == [SOURCE_URL]
    assert [item.reference for item in receipt.evidence] == [SOURCE_URL]
    assert receipt.coverage.complete is True
    call = client.responses.calls[0]
    assert call["tools"] == [{"type": "web_search"}]
    assert call["tool_choice"] == "required"
    assert call["include"] == ["web_search_call.action.sources"]
    prompt = json.loads(call["input"])
    assert prompt["research_scope"] == _request().research_scope
    assert prompt["required_semantic_keys"] == ["CURRENT_PLATFORM_CAPABILITY"]
    assert prompt["queries"] == _request().queries
    assert "allowed_source_classes" in prompt
    assert _request().original_task_scope not in call["input"]
    assert SECRET not in call["input"]


def test_api_success_without_sources_fails_coverage_closed():
    receipt = _port(_FakeClient(result=_response(sources=[]))).execute(_request())

    assert receipt.status is ResearchExecutionStatus.FAILED
    assert receipt.blocker == OPENAI_WEB_SOURCES_MISSING
    assert receipt.coverage.complete is False
    assert receipt.source_references == []


def test_api_error_returns_safe_failed_receipt_without_secret():
    receipt = _port(
        _FakeClient(error=RuntimeError(f"provider error included {SECRET}"))
    ).execute(_request())
    serialized = receipt.model_dump_json()

    assert receipt.status is ResearchExecutionStatus.FAILED
    assert receipt.blocker == OPENAI_WEB_REQUEST_FAILED
    assert receipt.error == "RuntimeError"
    assert SECRET not in serialized


def test_required_semantic_keys_must_each_have_matching_evidence():
    request = _request(
        OutputClassification.CURRENT_PLATFORM_CAPABILITY,
        OutputClassification.CURRENT_TOOL_CAPABILITY,
    )

    receipt = _port(_FakeClient(result=_response())).execute(request)

    assert receipt.status is ResearchExecutionStatus.PASS
    assert receipt.coverage.complete is False
    assert receipt.coverage.covered_semantic_keys == {
        OutputClassification.CURRENT_PLATFORM_CAPABILITY
    }
    assert receipt.coverage.unresolved_gaps == ["CURRENT_TOOL_CAPABILITY"]


def test_source_urls_are_only_admitted_from_returned_source_objects():
    response = _response(
        evidence=[
            {
                "semantic_key": "CURRENT_PLATFORM_CAPABILITY",
                "observed_result": "The returned source supports this observation.",
                "source_urls": [UNRETURNED_URL, SOURCE_URL],
            }
        ]
    )

    receipt = _port(_FakeClient(result=response)).execute(_request())

    assert receipt.source_references == [SOURCE_URL]
    assert [item.reference for item in receipt.evidence] == [SOURCE_URL]
    assert UNRETURNED_URL not in receipt.model_dump_json()


def test_sources_without_valid_evidence_fail_closed():
    response = _response(
        evidence=[
            {
                "semantic_key": "CURRENT_PLATFORM_CAPABILITY",
                "observed_result": "Unsupported because its URL was not returned.",
                "source_urls": [UNRETURNED_URL],
            }
        ]
    )

    receipt = _port(_FakeClient(result=response)).execute(_request())

    assert receipt.status is ResearchExecutionStatus.FAILED
    assert receipt.blocker == OPENAI_WEB_EVIDENCE_MISSING
    assert receipt.coverage.complete is False


def test_non_json_model_output_fails_closed():
    receipt = _port(
        _FakeClient(result=_response(output_text="not structured JSON"))
    ).execute(_request())

    assert receipt.status is ResearchExecutionStatus.FAILED
    assert receipt.blocker == OPENAI_WEB_OUTPUT_INVALID


def test_openai_is_a_production_dependency_for_docker_install():
    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = project["project"]["dependencies"]
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "openai>=2.25,<3" in dependencies
    assert "RUN pip install ." in dockerfile
