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
- MCP server 是 adapter，不是治理中心。
- 不把整段 conversation dump 給 MCP server；Host 應只送本次 TaskRequest。

## 啟動前

`authority/current/registry.json` 目前故意是 `UNSET`。
請把真正 current 原生 Canonical 直接放在 registry 指定的 root path，並完成
`expected_revision` 與 Owner binding 驗證後，才允許 live run。不得為 Canonical
另加 wrapper metadata、改寫或摘要正文。

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
- Health: `/health`
- Transport: Streamable HTTP
- Stateless HTTP: enabled

## 目前狀態

這是「架構骨架 + deterministic governance core」。

它刻意 **沒有**：
- 把舊 GitHub 的 domain prompt 搬進來
- 把 Memory 當 authority
- 自動修改 current authority
- 自動把監察官 finding 升格成修正
- 隨意啟用 live side effects
