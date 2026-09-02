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
composition root 的 `AuthorityResolver` 實際解析 current registry；revision、hash、path、
status 或 binding 不一致時回 HTTP 503。MCP `dispatch_task` 會將 `TaskRequest` 交給同一個
`Dispatcher`，不在 adapter 複製 governance flow。

`AUTHORITY_READY != DOMAIN_EXECUTION_CONFIGURED`：目前五個 Owner 都仍使用既有
`NotConfiguredDomain`。因此 authority readiness 可以通過，而安全 dispatch 的最終 domain
結果可以是 `BLOCKED_NOT_CONFIGURED`。

## 目前狀態

這是「架構骨架 + deterministic governance core」。

它刻意 **沒有**：
- 把舊 GitHub 的 domain prompt 搬進來
- 把 Memory 當 authority
- 自動修改 current authority
- 自動把監察官 finding 升格成修正
- 隨意啟用 live side effects
