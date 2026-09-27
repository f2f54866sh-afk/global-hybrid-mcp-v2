"""Build a controlled Responses request with one required MCP action."""
from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from global_hybrid_v2.ingress_admission import (
    IngressTaskClass,
    IngressTurnTokenCodec,
    ServerTaskClassifier,
)
from global_hybrid_v2.media_admission import (
    MediaAdmissionError,
    MediaAdmissionGate,
    ProducingActivity,
    canonical_image_mime,
    require_truth_eligible,
)


@dataclass(frozen=True)
class ForcedDispatchPlan:
    responses_request: dict[str, Any]
    task_scope: str


class ForcedHostDispatchAdapter:
    def __init__(self, *, mcp_server_url: str, model: str = "gpt-5.6") -> None:
        parsed = urlparse(mcp_server_url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("remote MCP server must use https")
        self.mcp_server_url = mcp_server_url
        self.model = model

    def plan(
        self,
        *,
        user_input: str,
        task_scope: str,
        authorization: str | None = None,
        media_inputs: tuple[dict[str, Any], ...] = (),
    ) -> ForcedDispatchPlan:
        if not user_input.strip() or not task_scope.strip():
            raise ValueError("user_input and task_scope are required")
        if any(item.get("type") not in {"input_image", "input_file"} for item in media_inputs):
            raise ValueError("only controlled image/file inputs are allowed")
        tool = {
            "type": "mcp",
            "server_label": "global_hybrid_v2",
            "server_url": self.mcp_server_url,
            "allowed_tools": ["dispatch_verified_host_task"],
            "require_approval": "never",
        }
        if authorization is not None:
            tool["authorization"] = authorization
        return ForcedDispatchPlan(
            task_scope=task_scope,
            responses_request={
                "model": self.model,
                "input": (
                    [{"role": "user", "content": [
                        {"type": "input_text", "text": user_input}, *media_inputs,
                    ]}]
                    if media_inputs else user_input
                ),
                "tools": [tool],
                "tool_choice": "required",
            },
        )


@dataclass(frozen=True)
class ServerTurnContext:
    conversation_id: str
    turn_id: str


class ControlledSalesIngress:
    """Classify and bind a turn before any model sees the request."""

    def __init__(
        self,
        *,
        classifier: ServerTaskClassifier | None,
        token_codec: IngressTurnTokenCodec,
        responses_adapter: ForcedHostDispatchAdapter,
        media_gate: MediaAdmissionGate | None = None,
    ) -> None:
        self.classifier = classifier
        self.token_codec = token_codec
        self.responses_adapter = responses_adapter
        self.media_gate = media_gate

    def plan(
        self,
        *,
        turn: ServerTurnContext,
        request_text: str,
        intent: str,
        raw_evidence: bytes,
        media_inputs: tuple[dict[str, Any], ...] = (),
        media_activity: ProducingActivity | None = None,
        media_attestation: str | None = None,
        media_source_lineage: str | None = None,
        media_parent_asset_id: str | None = None,
    ) -> ForcedDispatchPlan:
        if self.classifier is None:
            raise RuntimeError("SERVER_TASK_CLASSIFIER_UNAVAILABLE")
        if media_inputs:
            if (len(media_inputs) != 1 or self.media_gate is None or media_activity is None
                or media_attestation is None or media_source_lineage is None):
                raise MediaAdmissionError("MEDIA_ADMISSION_REQUIRED")
            # The model receives bytes built from the exact admitted preimage, never caller media URLs.
            mime = canonical_image_mime(raw_evidence)
            admitted = self.media_gate.ingest(
                raw=raw_evidence, mime=mime, activity=media_activity,
                source_lineage=media_source_lineage,
                task_lineage=f"conversation:{turn.conversation_id}:turn:{turn.turn_id}",
                attestation=media_attestation, parent_asset_id=media_parent_asset_id,
            )
            media_inputs = ({
                "type": "input_image",
                "image_url": f"data:{mime};base64," + base64.b64encode(raw_evidence).decode(),
            },)
        else:
            admitted = None
        evidence_digest = hashlib.sha256(raw_evidence).hexdigest()
        task_class = IngressTaskClass(self.classifier.classify(
            request_text=request_text, evidence_digest=evidence_digest,
        ))
        if task_class is IngressTaskClass.COMPANY_COMMERCIAL_MATCHING and intent != "sales_human":
            raise ValueError("matching company-commercial task requires Sales owner")
        if task_class is IngressTaskClass.COMPANY_COMMERCIAL_MATCHING and admitted is not None:
            require_truth_eligible((admitted.asset,))
        token = self.token_codec.issue(
            conversation_id=turn.conversation_id,
            turn_id=turn.turn_id,
            task_class=task_class,
            request_text=request_text,
            intent=intent,
            evidence_digest=evidence_digest,
            media_asset_id=admitted.asset.media_asset_id if admitted else None,
        )
        return self.responses_adapter.plan(
            user_input=request_text,
            task_scope=f"conversation:{turn.conversation_id}:turn:{turn.turn_id}",
            authorization=token,
            media_inputs=media_inputs,
        )
