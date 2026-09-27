"""Build a controlled Responses request with one required MCP action."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse


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

    def plan(self, *, user_input: str, task_scope: str) -> ForcedDispatchPlan:
        if not user_input.strip() or not task_scope.strip():
            raise ValueError("user_input and task_scope are required")
        return ForcedDispatchPlan(
            task_scope=task_scope,
            responses_request={
                "model": self.model,
                "input": user_input,
                "tools": [{
                    "type": "mcp",
                    "server_label": "global_hybrid_v2",
                    "server_url": self.mcp_server_url,
                    "allowed_tools": ["dispatch_verified_host_task"],
                    "require_approval": "never",
                }],
                "tool_choice": "required",
            },
        )
