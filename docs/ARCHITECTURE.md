# Architecture

## 1. Why modular monolith

目前需要的是清楚 authority / owner / side-effect 邊界，而不是更多分散服務。
因此採用 modular monolith + ports/adapters：

- 一個 deployable service
- 邏輯邊界仍然強制分離
- 減少 network / distributed state / deployment complexity
- 未來某 domain 真有獨立 scale / security 需求時再拆服務

## 2. Three planes

### A. Governance / Control Plane

Owner: GLOBAL

只負責：

- exact current authority resolution
- task firewall
- deterministic owner routing
- interface contract
- effect authorization
- system-level validation
- closure

不得：

- 寫 Sales 文案
- 判斷車圖好不好看
- 代替 Library 決定硬事實
- 代替 Execution 宣稱工具能力

### B. Domain Plane

固定四個專業 Domain Owner：

- SALES_HUMAN
- LIBRARY_FACT
- VISUAL
- EXECUTION

Domain 只收 typed TaskContract，不直接吃完整 conversation history。

### C. Observability Plane

監察官：

- always attached
- receives immutable TraceEvent copy
- read-only
- no authority mutation
- no tool port
- no domain execution
- finding 只作 evidence

## 3. Runtime normal form

```text
TaskRequest
→ AuthoritySnapshot
→ FirewallDecision
→ RouteDecision
→ EffectDecision
→ DomainExecution
→ Trace
→ Closure
```

監察官平行觀察每個 stage。

## 4. Authority

Authority 與 runtime code 分離。

`authority/current/registry.json` 保存 document pointer 與 Owner binding：

- document name / role / exact revision / current file path
- 既有 Owner 對 live authority document 的唯一 binding
- reference-only 與 shared canonical binding

Document binding 不建立新 Owner，也不合併 Owner 權限。reference-only document 不可成為 live
authority；共享 canonical 只共享 canonical state，不共享 domain authority 或 effect capability。

runtime 不掃 archive 找「看起來最新」的檔案。

`UNSET` / missing / duplicate owner 都 fail-close。

## 5. Context admissibility

Live TaskRequest 不接受任意 history dump。

ContextItem 至少需要：

- origin
- purpose
- task_scope
- authority_revision (authority-derived item 時)

允許 live origin 預設：

- current_user
- current_authority
- current_tool_result

history / archive / memory 預設 quarantine。

## 6. Side effects

Effect type：

- read_only
- model_inference
- external_read
- external_write
- file_write
- image_generate

原則：

- GLOBAL: read_only only
- SALES_HUMAN: read_only + model_inference
- VISUAL: read_only + model_inference
- LIBRARY_FACT: read_only + model_inference + external_read
- EXECUTION: all effects，但仍需 explicit authorization

## 7. MCP boundary

MCP 是 remote adapter，不是 application core。

只暴露：

- inspect_task
- health
- 後續可加 run_task

不暴露：

- mutate_authority
- promote_finding
- bypass_effect_gate
- direct_domain_tool

## 8. LLM boundary

Owner routing / effect authorization 不交給 LLM 決定。

需要 LLM 時，由 domain adapter 呼叫模型，輸入必須是已過 firewall 的 typed payload。

GLOBAL 本身應保持 deterministic。

## 9. Trace

每個 stage 寫 TraceEvent：

- trace_id
- task_id
- stage
- owner
- decision
- metadata
- timestamp

應輸出 structured stdout。
正式 production 可接 OpenTelemetry exporter。

## 10. Failure policy

以下一律 fail-close：

- authority `UNSET`
- authority revision 不可解析
- context provenance 不合格
- owner 不唯一
- effect 超出 owner capability
- observer 嘗試 mutation
- domain output contract invalid
