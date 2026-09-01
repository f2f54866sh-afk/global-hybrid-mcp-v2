# Research basis

此架構不是從舊 repository 複製，而是依成熟公開架構原則重建。

主要依據：

1. Model Context Protocol architecture
   - Host 負責 orchestration / security / permission
   - Server 應保持 focused capability
   - Server 不應看到完整 conversation 或其他 server 狀態
   - Capability 必須明確宣告
   https://modelcontextprotocol.io/specification/

2. MCP Python SDK v2
   - production 使用 Streamable HTTP
   - `MCPServer` 是 protocol implementation，不應承擔整個 application server responsibility
   - custom health route 與 ASGI deployment 分離
   https://github.com/modelcontextprotocol/python-sdk

3. OpenAI Agents / Responses
   - Agents SDK 適合 handoff / guardrail / tracing
   - 若 application 要自己掌握 loop / tool dispatch / state，應由 host code 控制
   https://openai.github.io/openai-agents-python/
   https://platform.openai.com/docs/

4. Open Policy Agent
   - policy decision 與 policy enforcement 分離
   - 本 v2 先使用 typed Python policy port，保留未來 OPA adapter
   https://www.openpolicyagent.org/

5. OpenTelemetry
   - trace / metric / log 分離為標準 observability signals
   https://opentelemetry.io/docs/

6. Python Packaging User Guide
   - 採 `src/` layout，避免 repo root 誤 import / duplicate package
   https://packaging.python.org/

7. GitHub Actions / protected branch
   - CI 必須先過 tests / import checks 才能合併 main
   https://docs.github.com/actions
   https://docs.github.com/repositories/

8. Render Blueprint
   - rootDir / dockerContext / dockerfilePath 明確指向 repo root
   https://render.com/docs/blueprint-spec
