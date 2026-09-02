# GLOBAL Hybrid MCP v2

從零重建的 GLOBAL Hybrid 執行層。

這個 repository **不是** Sales / Human / Visual / Library / Execution 的規則本體，
也不是用來保存舊對話或 Memory 的地方。

它只負責：

1. 讀取「當前 authority 指標」
2. 建立本次 Task Contract / Task Firewall
3. deterministic Owner routing
4. effect / side-effect authorization
5. 呼叫正確的專業 Owner adapter
6. 寫 trace / closure evidence
7. 讓唯讀監察官觀察整個流程
8. 透過 MCP 暴露最小必要接口

## 架構

```text
MCP / HTTP Adapter
       │
       ▼
┌────────────────────────────┐
│ GLOBAL CONTROL PLANE       │
│ - Authority Resolver       │
│ - Task Firewall            │
│ - Owner Router             │
│ - Effect Gate              │
│ - Closure                  │
└────────────┬───────────────┘
             │ typed contract only
             ▼
┌────────────────────────────┐
│ DOMAIN PLANE               │
│ - Sales / Human            │
│ - Library / Fact           │
│ - Visual                   │
│ - Execution / Diagnostic   │
└────────────────────────────┘

所有 control/domain 事件
             │ immutable event copy
             ▼
┌────────────────────────────┐
│ 監察官 / OBSERVABILITY     │
│ READ-ONLY witness          │
│ no tool / no mutation      │
└────────────────────────────┘
```

## 關鍵限制

- GLOBAL 不做 domain reasoning。
- 專業 Owner 不能直接跨域呼叫另一個 Owner。
- 只有 Execution 可以執行有外部副作用的 effect。
- Library / Fact 可以做 external read，但不能做 external write。
- 監察官永遠只讀，沒有 mutation port。
- history / archive / memory 不可自行進 live task context。
- authority 必須能解析到 exact current revision；`UNSET` 直接 fail-close。
- persistent repair design 與 architecture-sensitive current capability claim 必須在 response egress
  前具有 fresh matching-scope research admission receipt；模型推測不是 evidence。
- MCP server 是 adapter，不是治理中心。
- 不把整段 conversation dump 給 MCP server；Host 應只送本次 TaskRequest。

## Current authority

`authority/current/registry.json` 已綁定 repository root 的 current 原生 Canonical，
並以 `expected_revision` 與 exact-bytes `content_sha256` 驗證。任何 revision、hash、
path、status 或 binding 不一致都會 fail-close。Canonical 不加 wrapper，也不改寫或摘要。

VISUAL 與 EXECUTION 不各自複製 authority document；兩者共用同一份 REAL_CAR
canonical，並透過不同 authority partition 維持 Owner 與 effect 權限隔離。

## Bounded automatic research

`Dispatcher` 在 response egress 判定 `RUN_REQUIRED_RESEARCH` 時，會先抑制實質輸出，
再透過 task-local `ResearchPort` 執行 bounded research、把結果轉成既有
`ResearchEvidence / ResearchAdmissionReceipt`，並以同一 `task_id` resume 原任務。
同一 scope/semantic keys 最多兩次；第二次沒有 material query/source/provider/strategy
變更時 fail-close，不會重跑相同研究。

Research provider 是工具 port，不是 Owner，也不能修改 authority。Production composition
支援既有 `ResearchPort` 的 `OpenAIWebResearchPort`，透過 Responses API 的 built-in
`web_search` 執行 bounded research，並只從 `web_search_call.action.sources` 接受來源 URL。
API 完成不等於 coverage complete；每個 required semantic key 都必須具有 matching source-backed
evidence，否則仍 fail-close。Deterministic fake provider 僅供 tests 驗證完整 loop。

Production image 的正式 runtime dependency 包含 `openai>=2.25,<3`。Provider 只有在下列設定
全部有效時才是 `CALLABLE`，否則 composition 明確使用 `UnavailableResearchPort`：

- `GLOBAL_RESEARCH_PROVIDER=openai_web`
- `GLOBAL_RESEARCH_MODEL=<configured model>`
- `OPENAI_API_KEY=<secret>`（亦相容 `GLOBAL_OPENAI_API_KEY`）

API key 使用 secret settings 讀取，不會進入 trace、research receipt 或 provider error detail；
repository 與 `render.yaml` 都不保存 key value。

## 本機

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
pytest -q
```

## MCP / Render

```bash
python -m global_hybrid_v2.adapters.mcp_server
```

預設：

- MCP: `/mcp`
- Liveness: `/health`
- Authority readiness: `/ready`
- Transport: Streamable HTTP
- Stateless HTTP: enabled

`/health` 只表示 process 與 MCP HTTP service 存活。`/ready` 會使用 production
composition root 的 `AuthorityResolver` 實際驗證 owner activation signature，再解析 current
registry；signature、revision、hash、path、status 或 binding 不一致時回 HTTP 503。MCP
`dispatch_task` 會將 `TaskRequest` 交給同一個 `Dispatcher`，不在 adapter 複製 governance
flow。

`/ready` 的 readiness 只代表 authority / governance runtime 可解析。它會附加僅從
`RENDER / RENDER_GIT_COMMIT / RENDER_GIT_BRANCH / RENDER_GIT_REPO_SLUG` 讀取的非敏感
deployment attestation；local 明確標記 `LOCAL_OR_UNKNOWN`，identity incomplete 不會改變
authority readiness。`render.yaml` 使用 `/ready` 作 deploy health check，並維持
`GLOBAL_LIVE_EXECUTION=false`。

`AUTHORITY_READY != DOMAIN_EXECUTION_CONFIGURED`：SALES_HUMAN 現在只綁定 bounded media-analysis
adapter，LIBRARY_FACT 只提供 read-only consumer projection；GLOBAL、VISUAL、EXECUTION 與非 media
Sales 工作仍可回 `BLOCKED_NOT_CONFIGURED`。這個 binding 不會執行廣告投放或開啟 live side effect。

## Authority promotion

Canonical 與 registry 的變更只是 `CANDIDATE_CHANGE`。成為 current authority 還需要 owner review、
owner-held Ed25519 private key直接簽署 `registry.json` exact bytes、寫入
`authority/current/activation.json`，以及 resolver 全部驗證成功。可信 key ID 與 public key 由
runtime environment 在 repository write boundary 外設定；`authority/trust/` 只保留說明文件。
Private key 不得進入 repository、tests fixture、Codex/ChatGPT workspace 或 Render，也沒有
fallback 自動簽章或 production bypass。

Production endpoint 由明確的 `PRODUCTION_BASE_URL` 綁定。部署完成後，手動執行
`.github/workflows/production-smoke.yml`，由 workflow dispatch 輸入 exact URL 與預期 commit；
也可直接執行：

```bash
EXPECTED_GIT_COMMIT="$GITHUB_SHA" python -m global_hybrid_v2.production_verifier
```

URL 未綁定會 hard-fail `PRODUCTION_IDENTITY_UNBOUND`，而 `/ready` attested SHA 不符會 hard-fail
`PRODUCTION_COMMIT_MISMATCH`；不需要 Render API key 或 service ID。Core CI 不執行 production
verification，避免與 Render auto-deploy 競速。

## 目前狀態

這是「架構骨架 + deterministic governance core」。

它刻意 **沒有**：
- 把舊 GitHub 的 domain prompt 搬進來
- 把 Memory 當 authority
- 自動修改 current authority
- 自動把監察官 finding 升格成修正
- 隨意啟用 live side effects
