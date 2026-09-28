"""Nonproduction candidate: server-owned release after an exact MCP persistence terminal."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from global_hybrid_v2.adapters.controlled_responses import ControlledSalesIngress, ServerTurnContext
from global_hybrid_v2.company_commercial_completion import CANONICAL_WORKBENCH_FILE_ID
from global_hybrid_v2.contracts import DomainResult, PersistenceDisposition, PersistenceReceipt
from global_hybrid_v2.ingress_admission import IngressTaskClass, sha256_task

SERVER_LABEL = "global_hybrid_v2"
TOOL_NAME = "dispatch_verified_host_task"
FAILURE = "NO_SERIALIZE / EXECUTION_FAIL"


class ResponsesExecutionPort(Protocol):
    def create(self, **request: Any) -> Any: ...


class OpenAIResponsesExecutionPort:
    """Use the declared SDK; construction and execution stay outside production composition."""

    def __init__(self, client: Any = None) -> None:
        if client is None:
            from openai import OpenAI

            client = OpenAI()
        self._responses = client.responses

    def create(self, **request: Any) -> Any:
        return self._responses.create(**request)


@dataclass(frozen=True)
class SalesExecutionResult:
    state: str
    user_visible_text: str | None
    receipt: PersistenceReceipt | None = None


def _field(value: Any, name: str) -> Any:
    return value.get(name) if isinstance(value, dict) else getattr(value, name, None)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        value = json.loads(value, object_pairs_hook=_unique_object)
    if not isinstance(value, dict):
        raise ValueError("expected JSON object")
    return value


def _mcp_result(output: Any) -> DomainResult:
    payload = _json_object(output)
    if "structuredContent" in payload:
        payload = _json_object(payload["structuredContent"])
    elif "content" in payload:
        content = payload["content"]
        if not isinstance(content, list) or len(content) != 1 or content[0].get("type") != "text":
            raise ValueError("MCP content is not one text result")
        payload = _json_object(content[0].get("text"))
    return DomainResult.model_validate(payload)


def _exact_arguments(value: Any, *, request_text: str, intent: str) -> bool:
    try:
        arguments = _json_object(value)
    except (ValueError, TypeError):
        return False
    return arguments == {"payload": {"task": {"request_text": request_text, "intent": intent}}}


def _valid_terminal(result: DomainResult, *, turn: ServerTurnContext,
                    request_text: str, intent: str) -> PersistenceReceipt:
    receipt = result.persistence_receipt
    if receipt is None or not receipt.task_id or receipt.file_id != CANONICAL_WORKBENCH_FILE_ID:
        raise ValueError("missing or unbound persistence receipt")
    contract = result.turn_contract
    if not isinstance(contract, dict) or any((
        contract.get("task_id") != receipt.task_id,
        contract.get("conversation_id") != turn.conversation_id,
        contract.get("turn_id") != turn.turn_id,
        contract.get("request_digest") != sha256_task(request_text, intent),
    )):
        raise ValueError("MCP output task binding mismatch")
    if receipt.state is PersistenceDisposition.WRITE_AND_READBACK_PASS:
        if (result.status == FAILURE or not receipt.postwrite_version or
                receipt.preimage_version == receipt.postwrite_version or
                not receipt.postwrite_sha256 or
                bool(receipt.preimage_version) != bool(receipt.preimage_sha256)):
            raise ValueError("write receipt missing readback binding")
    elif receipt.state is PersistenceDisposition.NO_DELTA:
        if result.status == FAILURE or receipt.postwrite_version or receipt.postwrite_sha256:
            raise ValueError("NO_DELTA carries a write or failed result")
    elif receipt.state in {
        PersistenceDisposition.PERSISTENCE_CAPABILITY_DEBT, PersistenceDisposition.HOLD_CONFLICT,
    }:
        if result.status != FAILURE:
            raise ValueError("blocker result was serialized as success")
    else:
        raise ValueError("unknown persistence terminal")
    return receipt


class ControlledSalesCompletionExecutor:
    """Only this executor may release a matching turn's model response."""

    def __init__(self, *, ingress: ControlledSalesIngress, responses: ResponsesExecutionPort):
        self.ingress = ingress
        self.responses = responses

    def execute(self, *, turn: ServerTurnContext, request_text: str, intent: str,
                raw_evidence: bytes = b"", **ingress_options: Any) -> SalesExecutionResult:
        try:
            plan = self.ingress.plan(
                turn=turn, request_text=request_text, intent=intent,
                raw_evidence=raw_evidence, **ingress_options,
            )
            if plan.task_class is not IngressTaskClass.COMPANY_COMMERCIAL_MATCHING:
                return SalesExecutionResult(FAILURE, None)
            response = self.responses.create(**plan.responses_request)
            calls = [item for item in (_field(response, "output") or [])
                     if _field(item, "type") == "mcp_call"]
            if len(calls) != 1:
                return SalesExecutionResult(FAILURE, None)
            call = calls[0]
            if (_field(call, "server_label") != SERVER_LABEL or
                    _field(call, "name") != TOOL_NAME or _field(call, "error") is not None or
                    not _exact_arguments(_field(call, "arguments"),
                                         request_text=request_text, intent=intent)):
                return SalesExecutionResult(FAILURE, None)
            result = _mcp_result(_field(call, "output"))
            receipt = _valid_terminal(
                result, turn=turn, request_text=request_text, intent=intent,
            )
        except Exception:
            # Never serialize model text, tool output, or provider exceptions on a failed fence.
            return SalesExecutionResult(FAILURE, None)
        if receipt.state is PersistenceDisposition.WRITE_AND_READBACK_PASS:
            visible = _field(response, "output_text")
            if not isinstance(visible, str) or not visible.strip():
                return SalesExecutionResult(FAILURE, None)
            return SalesExecutionResult(receipt.state.value, visible, receipt)
        if receipt.state is PersistenceDisposition.NO_DELTA:
            return SalesExecutionResult(receipt.state.value, "沒有新的 AI 車源表變更。", receipt)
        if receipt.state is PersistenceDisposition.PERSISTENCE_CAPABILITY_DEBT:
            return SalesExecutionResult(receipt.state.value, "AI 車源表同步能力目前不可用。", receipt)
        return SalesExecutionResult(receipt.state.value, "AI 車源表同步因資料衝突暫停。", receipt)
