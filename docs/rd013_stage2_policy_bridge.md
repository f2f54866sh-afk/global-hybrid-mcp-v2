# RD-013 Stage 2: APP_OWNED_EXISTING_COPY_POLICY_BRIDGE

Local prototype based on Stage 1 `0c0af1d347c5cafd38becbe3402bfc3de3265f49`.
Historical read-only reference: `7114c86f6c874790ff01bcd7a24e8af8be733080`;
merge base `8cedeebbe4b58441837e48ff97c7c9baf681d8ca`.
No cherry-pick or production dispatcher/contracts changes.

## Architecture mapping

The named Sales policy semantics below are mapping labels supplied by Engineering.
The historical Python files do not export those versioned names as constants.
This prototype maps their observed contracts, not a claim that old code is installed.

| Sales semantic | Existing behavior read | Stage 2 implementation point |
|---|---|---|
| PUBLIC_COPY_ADMISSION_V2 | Immutable host oracle input; source/revision/proof envelope | ExistingCopyPolicyInput inside Stage 1 confirmation digest; confirmation HTML shows policy data |
| NATIVE_COPY_EGRESS_ORACLE_V1 | Product disposition, fail closed on incomplete semantics | ExistingCopyPolicyBridge on Stage 1 PublicCopyGuard port; literal gates only; unresolved semantic dimensions remain FAIL |
| PUBLIC_COPY_ACCEPTANCE_WITNESS_V1 | Exact candidate requirement coverage and consumed proof IDs | acceptance_witness binds candidate, snapshot and current state; claim AND proof payload must be serialized for consumed proof |
| COPY_EGRESS_AUDIT_V2 | Audit binds the same candidate and witness | copy_egress_audit re-executes gates and compares the full expected witness and witness digest |
| COPY_EGRESS_COMMIT_FENCE_V1 | Exact terminal candidate and lineage before egress | commit_fence compares expected audit; existing SQLite save transaction locks/rechecks confirmed snapshot and receipt/output digests |
| PASS-only surface | Fail suppresses public output | Stage 1 API withholds result URL and final_output; result_page validates exact output digest |
| One same-state rewrite | State-bound repair cannot replace authority | same_state_rewrite_allowed checks attempt == 1 and equal state digests; no automatic rewrite, endpoint or persistence |

The snapshot is app-confirmed policy DATA, not independently verified Sales authority.
Policy revision/source references must not be treated as proof of current authority.
No semantic authority promotion or complete claim-entailment check is implemented.

## Deterministic check matrix

| Check | Enforcement boundary |
|---|---|
| Requested field shape/order | Exact label tuple; unchanged Stage 1 pre-guard gate |
| Exact candidate | Canonical Stage 1 SHA256, rechecked at witness/audit/commit/result |
| Snapshot/witness/state binding | Payload digest, task handle, confirmed state/time; complete expected witness/audit equality |
| Structured replay | NFKC/whitespace/case folded literal occurrence of confirmed structured values |
| Active exclusions | Same literal occurrence rule; arbitrary semantic paraphrases are not covered |
| Unknown/provenance leak | Confirmed unknown literals and finite provenance markers; no arbitrary paraphrase oracle |
| Required disclosure | Literal presence; semantic equivalence is not claimed |
| Supporting proof | Confirmed proof ID, claim, payload, evidence refs; full-body scope requires every admitted claim AND payload |
| Supporting point cap | Unique admitted fact occurrences and consumed proof count; free-form semantic point segmentation remains debt |
| Surface bounds/hierarchy | Confirmed per-field character/line bounds and first-field primary-reason literal; no inferred platform defaults |
| Consultant/meta/strategy | Finite known phrase inventory |
| Portable filler | Very specific V94 phrases: 很有誠意 / 性能氣勢 / 都有內容 / 值得直接看實車 |

Blank policy, malformed surface-bound shape and missing primary-reason literal fail closed.
Field bounds and literals are confirmed inputs, not new universal Sales policy values.
Unknown scopes conservatively require full supporting proof serialization.

## Unresolved semantic debt and release boundary

- Complete natural Taiwan used-car seller voice.
- Free-form factual entailment and all newly invented claims.
- Subtle genericity after arbitrary paraphrase.
- Subjective seller narration boundaries.
- Independent current Sales authority/source/evidence verification.
- Literal checks cannot prove contextual repetition, negation, arbitrary leaks,
  semantic supporting-point segmentation or hierarchy beyond explicit surface bounds.

Hard gates may PASS independently. PublicCopyGuardReceipt remains FAIL with explicit
capability_debt, and claim_safety/native_seller_voice remain FAIL. This is deliberate:
the positive fixture proves deterministic hard gates, not full semantic acceptance.
The default local app uses the bridge even when model/API credential settings exist;
it neither constructs nor calls the OpenAI guard. Existing injected fake guards remain
available for unchanged Stage 1 protocol/surface regression tests only.

Witness/audit digests are retained in the existing guard receipt; there is no new DB,
schema table, evaluator framework, LLM, external policy service, or dependency.
This is prototype evidence, not production durability or VERIFIED_REPAIR.

## TEST_NOW

`tests/test_existing_copy_policy_bridge.py` contains A-H and J fixtures, plus explicit
semantic-debt HOLD, default-app no-paid-guard construction, one same-state rewrite
interface rules, confirmation policy visibility, candidate/witness/audit/state
tampering, and transactional state-race rejection without a saved output.
I uses the eight unchanged Stage 1 fixtures.

Use repo-local disposable pytest basetemp. No commit, push or Render deploy is authorized.

Observed local results on 2026-10-02:

- A-J focused + unchanged Stage 1: 47 passed (39 new + 8 incumbent).
- Full repository pytest: 460 passed.
- Ruff: all checks passed.
- Compile: exit 0.
- MCP runtime integration: 11 passed.
- Core import: import-ok.
- Pytest reports one incumbent Starlette/anyio deprecation warning per run.
- Combined V94 fixture blocked by MAX_SUPPORTING_POINTS, STRUCTURED_FIELD_REPLAY
  and V94_PORTABLE_FILLER.
- Local HEAD and remote candidate remain exact Stage 1 SHA; production remote
  remains 1b51e965d91c804ef24c134644782da112d69092.
- commit=NO; push=NO; Render deploy=NO; paid API calls=0.

Status: DESIGN_TESTED_READY. No VERIFIED_REPAIR claim.
