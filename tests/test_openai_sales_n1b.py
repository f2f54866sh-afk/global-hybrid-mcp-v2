from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from pydantic import SecretStr

from global_hybrid_v2.adapters.openai_sales import (
    OpenAISalesCandidateGenerator,
    OpenAISalesProductEvaluator,
)
from global_hybrid_v2.governance.sales_final_commit import FinalOutputCommitGateV1, sha256_text
from global_hybrid_v2.sales_controlled_service import ControlledSalesServiceV1

NOW = datetime(2026, 10, 2, 13, 0, tzinfo=UTC)
POLICY = "SALES_VISUAL_EXECUTION_PROFILE_20261002_V99_FINAL_CONSUMER_AUDIT_RESULT_IDENTITY_BINDING_GUARD"
PRODUCER = "controlled-sales-app-v1"
RUNTIME = "n1b-local-candidate"
SECRET = "sk-test-secret-never-serialize"
V99_BAD = (
    "如果你本來就偏好車上有進氣與懸吊改裝，這台的重點很直接："
    "MST Performance 進氣＋BILSTEIN B8 已經在車上。"
)
V98_BAD = "這台的賣點不用繞：MST Performance 進氣、BILSTEIN B8、全景天窗與音響一次到位。"
V97_GOOD = "如果你就是在找已裝 MST Performance 進氣、BILSTEIN B8 前避震的 Tiguan R，這台符合這個條件。"


class FakeResponses:
    def __init__(self, events: list[Any]):
        self.events = list(events)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        event = self.events.pop(0)
        if isinstance(event, BaseException):
            raise event
        return event


class FakeClient:
    def __init__(self, events: list[Any]):
        self.responses = FakeResponses(events)


def response(output_text: str, *, response_id: str, status: str = "completed") -> dict[str, Any]:
    return {"id": response_id, "status": status, "output_text": output_text}


def evaluation(snapshot_digest: str, candidate: str, disposition: str, **extra: Any) -> str:
    payload = {
        "snapshot_digest": snapshot_digest,
        "candidate_digest": sha256_text(candidate),
        "disposition": disposition,
        "reason_codes": ["fixture"],
    }
    payload.update(extra)
    return json.dumps(payload)


def service(client: FakeClient) -> ControlledSalesServiceV1:
    generator = OpenAISalesCandidateGenerator(
        model="candidate-model",
        api_key=SecretStr(SECRET),
        instructions="Current Sales candidate policy projection.",
        client=client,
    )
    evaluator = OpenAISalesProductEvaluator(
        production_model="production-evaluator-model",
        detached_model="detached-evaluator-model",
        api_key=SecretStr(SECRET),
        production_instructions="Current production Product oracle projection.",
        detached_instructions="Detached Product oracle projection.",
        client=client,
    )
    gate = FinalOutputCommitGateV1(
        producer_id=PRODUCER,
        policy_ref=POLICY,
        runtime_commit=RUNTIME,
        now=lambda: NOW,
    )
    return ControlledSalesServiceV1(
        candidate_generator=generator,
        product_evaluator=evaluator,
        commit_gate=gate,
        producer_id=PRODUCER,
        policy_ref=POLICY,
        global_authority_revision="GLOBAL-current",
        sales_authority_revision="SALES-current",
        library_authority_revision="LIBRARY-current",
        real_car_authority_revision="REAL_CAR-current",
        now=lambda: NOW,
        id_factory=lambda: "task-n1b",
    )


def run(client: FakeClient):
    return service(client).handle(
        current_user_request="幫我做 AXT-8911 這台 Tiguan R 的 8891 廣告副標題跟特色說明。",
        conversation_or_session_id="session-n1b",
        task_class="8891_COPY",
        target_surface="8891",
        direct_user_hard_requirements=["不得杜撰 ECU、馬力或改裝效果"],
        vehicle_instance_id="WVGZZZ5NZMW539101",
        evidence_refs=["workbench:AXT-8911"],
    )


def client_for(candidate: str, production: str, detached: str) -> FakeClient:
    snapshot_digest = "DYNAMIC"
    client = FakeClient([])

    original_create = client.responses.create

    def dynamic_create(**kwargs: Any) -> Any:
        client.responses.calls.append(kwargs)
        index = len(client.responses.calls)
        if index == 1:
            return response(candidate, response_id="resp-candidate")
        prompt = json.loads(kwargs["input"])
        digest = prompt["snapshot_digest"]
        if snapshot_digest != "DYNAMIC":
            digest = snapshot_digest
        disposition = production if index == 2 else detached
        return response(
            evaluation(digest, candidate, disposition),
            response_id="resp-production" if index == 2 else "resp-detached",
        )

    client.responses.create = dynamic_create  # type: ignore[method-assign]
    client.responses._unused_original = original_create  # type: ignore[attr-defined]
    return client


def test_v99_natural_bad_candidate_is_failed_and_withheld():
    outcome = run(client_for(V99_BAD, "FAIL", "FAIL"))
    assert outcome.public_output is None
    assert outcome.receipt.final_output_commit == "FAIL"
    assert outcome.receipt.aggregate_product_disposition == "FAIL"


def test_v98_seller_meta_candidate_is_failed_and_withheld():
    outcome = run(client_for(V98_BAD, "FAIL", "FAIL"))
    assert outcome.public_output is None
    assert outcome.receipt.final_output_commit == "FAIL"


def test_v97_exact_conditional_fixture_can_pass_when_both_evaluators_pass():
    outcome = run(client_for(V97_GOOD, "PASS", "PASS"))
    assert outcome.public_output == V97_GOOD
    assert outcome.receipt.final_output_commit == "PASS"
    assert outcome.receipt.public_output_digest == sha256_text(V97_GOOD)


def test_evaluator_timeout_holds_and_withholds_candidate():
    client = FakeClient([])

    def dynamic_create(**kwargs: Any) -> Any:
        client.responses.calls.append(kwargs)
        index = len(client.responses.calls)
        if index == 1:
            return response(V97_GOOD, response_id="resp-candidate")
        prompt = json.loads(kwargs["input"])
        if index == 2:
            raise TimeoutError("provider timeout")
        return response(
            evaluation(prompt["snapshot_digest"], V97_GOOD, "PASS"),
            response_id="resp-detached",
        )

    client.responses.create = dynamic_create  # type: ignore[method-assign]
    outcome = run(client)
    assert outcome.public_output is None
    assert outcome.receipt.final_output_commit == "HOLD"


def test_schema_invalid_holds_and_model_cannot_supply_final_commit():
    client = FakeClient([])

    def dynamic_create(**kwargs: Any) -> Any:
        client.responses.calls.append(kwargs)
        index = len(client.responses.calls)
        if index == 1:
            return response(V97_GOOD, response_id="resp-candidate")
        prompt = json.loads(kwargs["input"])
        payload = json.loads(evaluation(prompt["snapshot_digest"], V97_GOOD, "PASS"))
        if index == 2:
            payload["final_output_commit"] = "PASS"
        return response(
            json.dumps(payload),
            response_id="resp-production" if index == 2 else "resp-detached",
        )

    client.responses.create = dynamic_create  # type: ignore[method-assign]
    outcome = run(client)
    assert outcome.public_output is None
    assert outcome.receipt.final_output_commit == "HOLD"


def test_candidate_digest_echo_mismatch_holds_and_withholds():
    client = FakeClient([])

    def dynamic_create(**kwargs: Any) -> Any:
        client.responses.calls.append(kwargs)
        index = len(client.responses.calls)
        if index == 1:
            return response(V97_GOOD, response_id="resp-candidate")
        prompt = json.loads(kwargs["input"])
        payload = json.loads(evaluation(prompt["snapshot_digest"], V97_GOOD, "PASS"))
        if index == 2:
            payload["candidate_digest"] = "f" * 64
        return response(
            json.dumps(payload),
            response_id="resp-production" if index == 2 else "resp-detached",
        )

    client.responses.create = dynamic_create  # type: ignore[method-assign]
    outcome = run(client)
    assert outcome.public_output is None
    assert outcome.receipt.final_output_commit == "HOLD"


def test_same_snapshot_exact_candidate_all_typed_results_pass_returns_public_copy():
    client = client_for(V97_GOOD, "PASS", "PASS")
    outcome = run(client)
    assert outcome.public_output == V97_GOOD
    assert outcome.receipt.final_output_commit == "PASS"
    assert len(client.responses.calls) == 3
    production_prompt = json.loads(client.responses.calls[1]["input"])
    detached_prompt = json.loads(client.responses.calls[2]["input"])
    assert production_prompt["candidate_digest"] == sha256_text(V97_GOOD)
    assert detached_prompt["candidate_digest"] == sha256_text(V97_GOOD)
    assert production_prompt["snapshot_digest"] == detached_prompt["snapshot_digest"]
    assert "evidence_refs" in production_prompt["task"]
    assert "evidence_refs" not in detached_prompt["task"]
    assert "FINAL_OUTPUT_COMMIT" in production_prompt["constraints"][1]
    assert SECRET not in json.dumps(client.responses.calls, ensure_ascii=False)


def test_production_detached_disagreement_fails_invariance_and_withholds():
    outcome = run(client_for(V97_GOOD, "PASS", "FAIL"))
    assert outcome.public_output is None
    assert outcome.receipt.final_output_commit == "FAIL"


def test_incomplete_evaluator_response_holds_and_withholds():
    client = FakeClient([])

    def dynamic_create(**kwargs: Any) -> Any:
        client.responses.calls.append(kwargs)
        index = len(client.responses.calls)
        if index == 1:
            return response(V97_GOOD, response_id="resp-candidate")
        prompt = json.loads(kwargs["input"])
        return response(
            evaluation(prompt["snapshot_digest"], V97_GOOD, "PASS"),
            response_id="resp-production" if index == 2 else "resp-detached",
            status="in_progress" if index == 2 else "completed",
        )

    client.responses.create = dynamic_create  # type: ignore[method-assign]
    outcome = run(client)
    assert outcome.public_output is None
    assert outcome.receipt.final_output_commit == "HOLD"
