from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse

from global_hybrid_v2.contracts import TaskRequest
from global_hybrid_v2.settings import Settings

settings = Settings()

try:
    from mcp.server.mcpserver import MCPServer
except ImportError as exc:  # clear error for incomplete installs
    raise RuntimeError('MCP SDK v2 is required: pip install "mcp[cli]>=2,<3"') from exc

mcp = MCPServer("GLOBAL Hybrid v2")


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> JSONResponse:
    return JSONResponse(
        {
            "ok": True,
            "service": "GLOBAL Hybrid v2",
            "live_execution": settings.live_execution,
        }
    )


@mcp.tool()
def validate_task(payload: dict) -> dict:
    """Validate the TaskRequest schema only. Does not execute domain work."""
    request = TaskRequest.model_validate(payload)
    return {
        "valid": True,
        "intent": request.intent.value,
        "effects": [effect.value for effect in request.effects],
        "context_items": len(request.context),
    }


def main() -> None:
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=settings.port,
        stateless_http=True,
        json_response=True,
    )


if __name__ == "__main__":
    main()
