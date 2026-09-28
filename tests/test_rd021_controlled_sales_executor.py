"""Response text cannot bypass the exact MCP persistence terminal."""
from __future__ import annotations

import json

import pytest

from global_hybrid_v2.adapters.controlled_responses import (
    ControlledSalesIngress,
    ForcedHostDispatchAdapter,
    ServerTurnContext,
)
from global_hybrid_v2.adapters.controlled_sales_executor import (
    FAILURE,
    ControlledSalesCompletionExecutor,
)
from global_hybrid_v2.company_commercial_completion import CANONICAL_WORKBENCH_FILE_ID
from global_hybrid_v2.contracts import DomainResult, Owner, PersistenceDisposition, PersistenceReceipt
from global_hybrid_v2.ingress_admission import IngressTaskClass, sha256_task
from tests.test_rd021_ingress_admission import Classifier, ingress_codec

TEXT = "update this company vehicle"
TURN = ServerTurnContext("controlled-conversation", "controlled-turn")


def terminal(state: PersistenceDisposition, *, task="task-1") -> dict:
    receipt = PersistenceReceipt(
        state=state, task_id=task, file_id=CANONICAL_WORKBENCH_FILE_ID,
        preimage_version="version-1" if state is PersistenceDisposition.WRITE_AND_READBACK_PASS else None,
        preimage_sha256="a" * 64 if state is PersistenceDisposition.WRITE_AND_READBACK_PASS else None,
        postwrite_version="version-2" if state is PersistenceDisposition.WRITE_AND_READBACK_PASS else None,
        postwrite_sha256="b" * 64 if state is PersistenceDisposition.WRITE_AND_READBACK_PASS else None,
    )
    return DomainResult(
        owner=Owner.SALES_HUMAN,
        status=(FAILURE if state in {PersistenceDisposition.PERSISTENCE_CAPABILITY_DEBT,
                                     PersistenceDisposition.HOLD_CONFLICT}
                else "COMPANY_COMMERCIAL_DELTA_VERIFIED"),
        persistence_receipt=receipt,
        turn_contract={"task_id": task, "conversation_id": TURN.conversation_id,
                       "turn_id": TURN.turn_id, "request_digest": sha256_task(TEXT, "sales_human")},
    ).model_dump(mode="json")


def call(result, *, name="dispatch_verified_host_task", error=None, text=TEXT):
    return {"type": "mcp_call", "server_label": "global_hybrid_v2", "name": name,
            "arguments": json.dumps({"payload": {"task": {"request_text": text,
                                                       "intent": "sales_human"}}}),
            "error": error, "output": json.dumps(result)}


class FakeResponses:
    def __init__(self, items):
        self.items = items
        self.requests = []

    def create(self, **request):
        self.requests.append(request)
        return {"output": self.items, "output_text": "已完成並同步 AI 車源表。"}


def execute(items):
    transport = FakeResponses(items)
    ingress = ControlledSalesIngress(
        classifier=Classifier(IngressTaskClass.COMPANY_COMMERCIAL_MATCHING),
        token_codec=ingress_codec(),
        responses_adapter=ForcedHostDispatchAdapter(mcp_server_url="https://mcp.example/mcp"),
    )
    outcome = ControlledSalesCompletionExecutor(ingress=ingress, responses=transport).execute(
        turn=TURN, request_text=TEXT, intent="sales_human",
    )
    return outcome, transport


def test_write_receipt_releases_final_text_only_after_exact_call():
    outcome, transport = execute([call(terminal(PersistenceDisposition.WRITE_AND_READBACK_PASS))])
    assert outcome.state == "WRITE_AND_READBACK_PASS"
    assert outcome.user_visible_text == "已完成並同步 AI 車源表。"
    assert transport.requests[0]["tool_choice"] == {
        "type": "mcp", "server_label": "global_hybrid_v2", "name": "dispatch_verified_host_task",
    }
    assert transport.requests[0]["tools"][0]["allowed_tools"] == ["dispatch_verified_host_task"]


def test_no_delta_never_releases_model_write_claim():
    outcome, _ = execute([call(terminal(PersistenceDisposition.NO_DELTA))])
    assert outcome.state == "NO_DELTA"
    assert "同步" not in outcome.user_visible_text


@pytest.mark.parametrize("items", [
    [],
    [call(terminal(PersistenceDisposition.WRITE_AND_READBACK_PASS), name="other_tool")],
    [call(terminal(PersistenceDisposition.WRITE_AND_READBACK_PASS), error="tool failure")],
    [call("not-json")],
    [call(DomainResult(owner=Owner.SALES_HUMAN, status="success").model_dump(mode="json"))],
    [call({"owner": "sales_human", "status": "success",
           "persistence_receipt": {"state": "INVENTED", "task_id": "task-1",
                                   "file_id": CANONICAL_WORKBENCH_FILE_ID}})],
    [call(terminal(PersistenceDisposition.WRITE_AND_READBACK_PASS), text="different request")],
    [call(terminal(PersistenceDisposition.WRITE_AND_READBACK_PASS)),
     call(terminal(PersistenceDisposition.HOLD_CONFLICT))],
])
def test_missing_wrong_failed_malformed_or_duplicate_call_never_releases(items):
    outcome, _ = execute(items)
    assert outcome.state == FAILURE
    assert outcome.user_visible_text is None


@pytest.mark.parametrize("state,expected", [
    (PersistenceDisposition.PERSISTENCE_CAPABILITY_DEBT, "同步能力目前不可用"),
    (PersistenceDisposition.HOLD_CONFLICT, "資料衝突暫停"),
])
def test_blocker_only_releases_bounded_server_text(state, expected):
    outcome, _ = execute([call(terminal(state))])
    assert outcome.state == state.value
    assert expected in outcome.user_visible_text
    assert "已完成並同步" not in outcome.user_visible_text


def test_receipt_file_or_write_readback_binding_mismatch_blocks():
    result = terminal(PersistenceDisposition.WRITE_AND_READBACK_PASS)
    result["persistence_receipt"]["file_id"] = "wrong-file"
    assert execute([call(result)])[0].state == FAILURE
    result = terminal(PersistenceDisposition.WRITE_AND_READBACK_PASS)
    result["persistence_receipt"]["postwrite_version"] = None
    assert execute([call(result)])[0].state == FAILURE
    result = terminal(PersistenceDisposition.WRITE_AND_READBACK_PASS)
    result["persistence_receipt"]["task_id"] = "other-task"
    assert execute([call(result)])[0].state == FAILURE
