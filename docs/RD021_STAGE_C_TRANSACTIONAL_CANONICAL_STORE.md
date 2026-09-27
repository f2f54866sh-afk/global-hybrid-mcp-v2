# RD-021 Stage C: transactional canonical store candidate

This branch is based on `4de483103084026d636fcd60b74a9146f067d031`. It does not bind or create a database, write the canonical Drive file, deploy a service, or perform a production cutover. PostgreSQL is the candidate substrate; the SQLite schema is solely a local transaction-contract fixture.

## Authority and transaction

`vehicle_record.vehicle_instance_id` is the durable key. The imported XLSX cells are preserved in `source_snapshot`; they are **not** promoted to verified facts. Only a server-compiled delta whose field evidence independently resolves through `EvidenceAdmissionPort` enters `verified_state`. Limited or field-scoped media may support only the admitted visible field scope. AI-generated, AI-edited and composited assets cannot support truth. A separate creative admission can store a forbidden-truth media link without modifying vehicle truth.

`TransactionalVehicleStore.commit_verified` checks the current revision, updates exactly one vehicle row with `WHERE vehicle_instance_id = ? AND revision = ?`, and increments it once. Field evidence, the immutable mutation receipt and the projection outbox event are inserted in the same transaction. Any failure rolls back all four. A second request with the same mutation ID and semantic digest returns the original receipt; a different semantic digest holds. A fresh connection reads canonical state after commit before the completion handler can return `WRITE_AND_READBACK_PASS`. The only completion terminals remain `WRITE_AND_READBACK_PASS`, `NO_DELTA`, `PERSISTENCE_CAPABILITY_DEBT`, and `HOLD_CONFLICT`.

PostgreSQL uniqueness constraints protect vehicle ID, source row, verified VIN and verified plate. The candidate has no automatic fallback to SQLite, Drive, Sheets or Library. `GLOBAL_CANONICAL_VEHICLE_STORE_MODE=postgres` forbids the legacy XLSX completion handler and requires an explicit DSN, server-verified mutation provider and independent evidence admission binding. The default remains the existing production behavior until a separately authorized cutover.

## Import and cutover

The offline import takes the exact canonical XLSX bytes and file ID, hashes the full source, parses every AI vehicle row, checks unique `VEHICLE_INSTANCE_ID`, and records sheet/entry topology, row order, media refs, creative refs, field values and vehicle count. It inserts source snapshots into an empty candidate DB in one transaction, then uses a separate readback connection to compare the complete imported state digest. A changed byte stream, missing row, changed field or duplicate identity holds. The candidate schema does not infer verification from a cell value.

The future live cutover sequence is fixed:

1. Freeze the canonical XLSX **truth** writer and prove that freeze is effective.
2. Freshly capture the final XLSX bytes and immutable source identity; compile the import manifest.
3. Import into an empty PostgreSQL target and independently read back exact source/target parity.
4. Declare DB canonical once, then enable the DB completion writer.
5. Make XLSX a projection-only output. Add `CANONICAL_REVISION` as a bounded projection schema change, then enable the outbox worker and controlled completion path.

There is no period in which both stores accept canonical truth writes. The projection builder modifies only the uniquely resolved row and preserves unrelated workbook entries and rows. `XlsxProjectionVerifier` has only metadata/download methods: it checks a fresh stable metadata version, parsed identity, projected revision and fields, and never invokes a migration runner or PATCH. Projection failure leaves the canonical transaction committed and records `PROJECTION_FAILED`; retry uses the same unique event ID. A live projection sink, its exclusive writer binding and concurrency policy are still capability debt.

Before the first DB canonical mutation, the candidate cutover state may be marked rolled back and the frozen XLSX preimage may be restored by a separately admitted operator. Once any DB mutation exists, rollback to old XLSX is blocked with `ROLLBACK_BLOCKED_NEW_CANONICAL_WRITES_PRESENT`; recovery requires a new controlled reverse migration.

## Ports and outstanding bindings

`VehicleStatePort` supplies Host current state, `EvidenceAdmissionPort` and `EvidenceReceiptPort` separate evidence readback from assertions, `VehicleMutationPort` supplies the company-commercial completion writer, `MediaLinkPort` admits creative links, and `ProjectionSink` receives idempotent canonical outbox events. None of these interfaces authorizes caller/model-produced evidence or arbitrary SQL access.

The following remain unbound: exact PostgreSQL resource/credentials/schema migration executor, real PostgreSQL integration run, production Host current-state and evidence-admission implementations, Drive projection sink/exclusive writer, live final-preimage capture/freeze, and cutover/rollback operator. This branch must not be described as `POSTGRES_BOUND`, `MIGRATED`, `DEPLOYED`, `LIVE_READBACK_PASS` or `VERIFIED_REPAIR`.
