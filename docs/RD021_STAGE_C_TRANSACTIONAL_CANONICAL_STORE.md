# RD-021 Stage C: transactional canonical store candidate

The Stage C core began from `4de483103084026d636fcd60b74a9146f067d031`; the projection convergence candidate is based on `b5e53462194a4e63d7a4b3378bb08a64382c5f83`. It does not bind or create a database, write the canonical Drive file, deploy a service, or perform a production cutover. PostgreSQL is the candidate substrate; the SQLite schema is solely a local transaction-contract fixture.

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

There is no period in which both stores accept canonical truth writes. The projection builder modifies only the uniquely resolved row and preserves unrelated workbook entries and rows. `XlsxProjectionVerifier` has only metadata/download methods: it checks a fresh stable metadata version, parsed identity, projected revision and fields, and never invokes a migration runner or PATCH.

The chosen replay model is **LATEST_STATE_MONOTONIC_PROJECTION**. An outbox event is a lower-bound demand to project its vehicle at least through that canonical revision, not an immutable historical XLSX image. The worker locks that vehicle's canonical row, reads the latest `VehicleProjectionState`, observes the current XLSX revision, and uses a sink whose `replace_if_preimage` operation must atomically bind replacement to the exact observed version and bytes. Older events coalesce to the latest canonical revision. A successful fresh readback terminalizes that revision's event as `PROJECTED` and earlier pending/failed events as `SUPERSEDED_BY_LATER_REVISION`. A durable per-vehicle projection cursor records the last verified revision and row digest. Lower revisions and external edits at the cursor revision hold instead of overwriting. Projection failure leaves the canonical transaction committed for retry.

`VehicleProjectionState` materializes source baseline, verified overlay, original/evidence media refs, creative media refs, and current canonical revision. Creative refs come only from the vehicle's canonical `vehicle_media_link` rows with `usage_class=CREATIVE`, `truth_eligibility=FORBIDDEN`, and `creative_classification=CREATIVE`; they are sorted, deduplicated and serialized as stable `creative:<digest>` identities. The XLSX `銷售素材Refs` cell is derived from those links on every projection, while `原始媒體Refs` remains the imported evidence baseline. Creative admission does not alter verified state or independent truth evidence count. An imported source with nonempty creative refs but no resolvable link holds rather than silently discarding or treating the source text as canonical.

The repository includes a SQLite-backed transaction fixture and an atomic fake XLSX sink that exercises concurrency and stale-preimage rejection. It does **not** provide or certify an atomic conditional-update primitive for the live Drive XLSX file. A live projection sink and exclusive writer binding remain capability debt; read-then-PATCH is not sufficient.

Before the first DB canonical mutation, the candidate cutover state may be marked rolled back and the frozen XLSX preimage may be restored by a separately admitted operator. Once any DB mutation exists, rollback to old XLSX is blocked with `ROLLBACK_BLOCKED_NEW_CANONICAL_WRITES_PRESENT`; recovery requires a new controlled reverse migration.

## Ports and outstanding bindings

`VehicleStatePort` supplies Host current state, `EvidenceAdmissionPort` and `EvidenceReceiptPort` separate evidence readback from assertions, `VehicleMutationPort` supplies the company-commercial completion writer, `MediaLinkPort` admits creative links, and `ProjectionSink` receives idempotent canonical outbox events. None of these interfaces authorizes caller/model-produced evidence or arbitrary SQL access.

The following remain unbound: exact PostgreSQL resource/credentials/schema migration executor, real PostgreSQL integration run, production Host current-state and evidence-admission implementations, Drive projection sink/exclusive writer, live final-preimage capture/freeze, and cutover/rollback operator. This branch must not be described as `POSTGRES_BOUND`, `MIGRATED`, `DEPLOYED`, `LIVE_READBACK_PASS` or `VERIFIED_REPAIR`.
