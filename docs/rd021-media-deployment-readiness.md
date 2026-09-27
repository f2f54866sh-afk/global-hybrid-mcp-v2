# RD-021 media deployment candidate

This branch is a repository candidate only. No production D1 migration, R2 object write, Drive mutation, binding change, or runtime deployment is performed by these tests.

## Ordered execution contract

The operator must record an independent, signed, typed readback receipt for each step before advancing. `DeploymentProgress` rejects a skipped step, wrong deployment/target/source/preimage, broken predecessor digest, invalid signature, or any continuation after a failed step. Its signing key and issuance authority must stay server-side. D1, XLSX, and R2 receipt adapters invoke their verifier/executor directly; the other steps still need concrete issuers and therefore cannot advance merely from prose.

1. Read current production state: branch and live commit, D1 schema revision and objects, R2 binding, canonical Drive file metadata and exact bytes. Confirm the expected prior D1 revision from actual readback; do not assume the local fixture revision is live.
2. Verify `MEDIA_BUCKET` exposes GET, PUT, and DELETE. Probe only `__probe__/rd021/<deployment_id>/<nonce>`: PUT, GET and compare bytes/size/SHA256, DELETE, then GET and require NOT_FOUND. Cleanup failure is `HOLD_PROBE_CLEANUP_FAILED`. This path never enters D1 `media_asset`; normal evidence objects still use `media/sha256/<SHA256>`.
3. Apply the pinned `0002_media_asset.sql` migration once, only after `D1MediaMigrationContract.inspect` returns `READY`. Its SHA256 is pinned in code. Do not drop or recreate partial tables.
4. Read D1 schema again through `/internal/media-schema/readback`. Require expected revision, table/index DDL fingerprint, and columns. Partial/unknown/incompatible state is `HOLD_D1_SCHEMA_CONFLICT`. A second run is `ALREADY_APPLIED` and must not execute SQL.
5. Migrate canonical Drive file `1OfUZ_rh94sdXdTZMjMrKj8IjHgEBUFua` using `CreativeSchemaMigrationRunner`, which builds from the transaction's fresh exact preimage. Require unique `VEHICLE_INSTANCE_ID`, existing `原始媒體Refs`, absent `銷售素材Refs`, and a header-only change.
6. Fetch fresh file metadata and raw bytes. Require the same postwrite version/hash and `CreativeRefsSchemaMigration.verify` against the captured preimage. The new header occurs exactly once; a second run is `NO_DELTA`.
7. Bind the runtime's registry URL, read/write credential references, `MEDIA_BUCKET`, media activity signing key reference, ingress turn signing key reference, and expected schema revision. Missing bindings fail startup when media is enabled. Binding names are references, not credential values in this document.
8. In staging, run another isolated disposable media probe with full cleanup readback.
9. In staging, add/read a synthetic creative ref against a noncanonical test workbook. Confirm only the resolved row's `銷售素材Refs` cell changes and `原始媒體Refs` stays intact.
10. Run RD-021 matching end to end and require a persistence terminal receipt before final response.
11. Only then observe production behavior. Any failure halts the sequence; there is no memory, filesystem, raw-D1-blob, Google Sheet, Library, or caller-asserted-truth fallback.

## Rollback fence

The XLSX schema rollback candidate removes only the newly appended `銷售素材Refs` header when the entire column is blank. Any saved creative ref returns `ROLLBACK_BLOCKED_DATA_PRESENT`; deleting creative lineage is prohibited. D1 rollback is not automatic: retain the migrated schema and halt runtime exposure after a partial deployment until a separately reviewed recovery plan is available. R2 probe objects remain content addressed; no delete action is part of this candidate.

## Remaining integration debt

Production D1's actual prior revision, live canonical workbook topology, R2 binding, and credential references require independent preflight. Runtime media provider and controlled Host binding must be wired and tested in a later authorized stage. These repository tests do not establish live deployment or verified repair.

## A.2.2 durable journal boundary

The candidate journal uses only `__deployment__/rd021/<deployment_id>/`. Its receipt objects are immutable, signed `DeploymentReceipt` JSON, named by ordinal, step, and receipt digest. The Worker uses R2 conditional PUT for absence and ETag compare-and-swap for `head.json`; every write is followed by GET byte and ETag readback. On load it lists the complete receipt prefix, checks every signature, ordinal, predecessor digest, scope, object name, head pointer, and ACTIVE/HOLD/COMPLETE state. A gap, orphan, collision, or competing head update stops with a journal HOLD. This namespace is rejected by the media-object read route and cannot satisfy the `media_asset` canonical object-key admission rule.

Bootstrap accepts server-signed current-state and R2-probe receipts in memory, anchors both in R2, writes and reads back the ACTIVE head, then reloads the full chain. `require_d1_admissible` admits only the exact next D1 migration step after that readback. No production D1 migration executor is added here.

Issuer inventory remains explicit. `R2_BINDING_READY` has the disposable PUT/GET/DELETE probe; `D1_SCHEMA_READBACK` has the D1 schema verifier; `XLSX_FRESH_READBACK` has the exact Drive postwrite verifier. `CANONICAL_XLSX_SCHEMA_MIGRATION` has a real bounded migration runner, but no separate signed step issuer. `CURRENT_STATE_PREFLIGHT`, `D1_MIGRATION`, `RUNTIME_BINDINGS`, `STAGING_MEDIA_READBACK`, `STAGING_CREATIVE_REF_READBACK`, `MATCHING_END_TO_END`, and `PRODUCTION_BEHAVIOR_OBSERVATION` have no trusted step issuer yet. They remain capability debt and cannot be completed by prose, booleans, caller-supplied digests, or model assertions. This branch does not execute live migration, staging writes, or production observation.
