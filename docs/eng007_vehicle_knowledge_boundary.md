# ENG-007 vehicle knowledge authority boundary

| Value | Producer | Trust/storage | Consumer | Enforcement and omission |
|---|---|---|---|---|
| Inventory rows | Fixed-source GoogleInventoryReader | external observation / D1 | coverage planner | fixed spreadsheet; blank group after separator HOLD |
| Coverage work | coverage planner | server-owned / D1 | research collector | deterministic work ID; duplicate is idempotent |
| Research packet | bounded control adapter | evidence only / D1 | verifier | cannot self-assert verified/query-ready/promotion |
| Verified fact | VehicleConfigurationVerifier | LIBRARY_FACT / D1 | snapshot builder | exact work/scope/source/market/year/unit/digest; ambiguity HOLD |
| Active snapshot | snapshot promoter | D1 singleton pointer | Worker read API | verified revisions only; promotion is atomic |
| Runtime reference | HTTP provider | read model | Library/Sales | HTTP failure is PROVIDER_UNAVAILABLE; no file fallback |
| Required projections | TaskEvidencePlanner | server-owned runtime | Dispatcher | trusted semantics; caller omission cannot remove requirements |
| Visual observation | trusted producer port | capability debt until bound | OEM differential | caller packets rejected; missing producer HOLD |

The Google Control Sheet carries evidence and work coordination only. Git carries code only.
Runtime SQLite remains task state and is not vehicle fact authority.
