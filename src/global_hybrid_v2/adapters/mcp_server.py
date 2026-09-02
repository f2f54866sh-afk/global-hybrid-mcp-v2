from __future__ import annotations

from mcp.server.mcpserver import MCPServer
from starlette.requests import Request
from starlette.responses import JSONResponse

from global_hybrid_v2.application import Application, create_application
from global_hybrid_v2.contracts import TaskRequest
from global_hybrid_v2.governance.authority import AuthorityError


def create_mcp_server(application: Application) -> MCPServer:
    server = MCPServer("GLOBAL Hybrid v2")

    @server.custom_route("/health", methods=["GET"])
    async def health(_: Request) -> JSONResponse:
        return JSONResponse(
            {
                "ok": True,
                "service": "GLOBAL Hybrid v2",
                "live_execution": application.settings.live_execution,
            }
        )

    @server.custom_route("/ready", methods=["GET"])
    async def ready(_: Request) -> JSONResponse:
        try:
            snapshot = application.authority.resolve()
        except AuthorityError:
            return JSONResponse(
                {
                    "ready": False,
                    "failure_code": "AUTHORITY_RESOLUTION_FAILED",
                },
                status_code=503,
            )
        return JSONResponse(
            {
                "ready": True,
                "resolved_owners": [owner.value for owner in snapshot.entries],
            }
        )

    @server.tool()
    def validate_task(payload: dict) -> dict:
        """Validate the TaskRequest schema only. Does not execute domain work."""
        request = TaskRequest.model_validate(payload)
        return {
            "valid": True,
            "intent": request.intent.value,
            "effects": [effect.value for effect in request.effects],
            "context_items": len(request.context),
        }

    @server.tool()
    def dispatch_task(payload: dict) -> dict:
        """Dispatch a task through the authoritative governance runtime."""
        request = TaskRequest.model_validate(payload)
        result = application.dispatcher.dispatch(request)
        return result.model_dump(mode="json")

    return server


application = create_application()
mcp = create_mcp_server(application)


def main() -> None:
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=application.settings.port,
        stateless_http=True,
        json_response=True,
    )


if __name__ == "__main__":
    main()
