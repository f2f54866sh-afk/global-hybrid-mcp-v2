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
→ ResponseEgressDecision
→ Trace
→ Closure
```

監察官平行觀察每個 stage。

## 4. Authority

Authority 與 runtime code 分離。

`authority/current/registry.json` 保存 document pointer 與 Owner binding：

- document key / runtime role / expected revision / content SHA-256 / exact root path
- 既有 Owner 對 normative authority document 的唯一 binding
- reference-only binding 與 shared canonical 的 partition binding

Document binding 不建立新 Owner，也不合併 Owner 權限。`SALES_HUMAN_REFERENCE`
不可成為 live authority。`VISUAL` 與 `EXECUTION` 共用同一份 `REAL_CAR`
canonical 與 exact revision，卻分別以 `VISUAL_JUDGE` 與 `EXECUTION_LAB` partition
消費；Owner 與 effect capability 仍互相隔離。

專案根目錄直接保存原生 Canonical，不加 wrapper、不重寫也不摘要。只有
registry `expected_revision` 精確等於原生文件開頭的 `CURRENT_REVISION`，
原生 `STATUS` 為 `CURRENT`，且 exact file bytes 符合 registry `content_sha256` 時，
該 document 才可被解析。原生文件若有 `OWNER`，resolver 也必須驗證其與
document binding 相符。

Registry `role` 是 runtime/governance classification；原生 `AUTHORITY_ROLE` 是 domain
semantic metadata。兩者不是同一 type，resolver 不得比較其字串。

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
- persistent repair design 沒有 fresh matching-scope research admission receipt
- architecture-affecting current platform/capability claim 沒有 current evidence

## 11. Research-backed response egress

Research admission 的 consumption point 位於 domain execution 與 closure 之間，不建立新 Owner、
router 或平行 research gate。Output 會以下列類型表示：

- `DIAGNOSIS_ONLY`
- `PERSISTENT_REPAIR_DESIGN`
- `CURRENT_EXTERNAL_FACT_CLAIM`
- `CURRENT_PLATFORM_OR_CAPABILITY_CLAIM`
- `MUTATION_REPORT`

`REPAIR_DIRECTION / SHOULD_CHANGE / ARCHITECTURE_CHOICE / CANDIDATE_RULE /
IMPLEMENTATION_PATTERN / PERSISTENT_MUTATION` 會 deterministic 地觸發
`PERSISTENT_REPAIR_DESIGN`。Current/changeable 且 capability/architecture-sensitive 的 platform claim
也會觸發 research requirement；不會對所有外部敘述一律要求搜尋。

放行需要 `RESEARCH_ADMISSION_RECEIPT=PASS`，其 semantic key 與 scope 必須 exact match，
時間必須位於 receipt 的有效期，並包含 current tool、current web 或 official-source
evidence。「我以為」、「我猜」、「我覺得」、「應該」、「可能」、`probably`、`likely`、
`inferred from memory` 與 `model knowledge alone` 不會被解析為 receipt。

若 receipt 不存在、過期或 scope/semantic key 不合，egress 會移除原 repair design，
只返回 `RUN_REQUIRED_RESEARCH / UNKNOWN / exact blocker`。目前 runtime 沒有 research
tool adapter，因此該狀態 fail-close，不會以 model confidence 取代 research。
