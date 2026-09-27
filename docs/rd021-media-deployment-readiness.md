# RD-021 media deployment candidate

This branch is a repository candidate only. No production D1 migration, R2 object write, Drive mutation, binding change, or runtime deployment is performed by these tests.

## Ordered execution contract

The operator must record an independent readback receipt for each step before advancing. `DeploymentProgress` rejects a skipped step, an empty receipt, or any continuation after a failed step.

1. Read current production state: branch and live commit, D1 schema revision and objects, R2 binding, canonical Drive file metadata and exact bytes. Confirm the expected prior D1 revision from actual readback; do not assume the local fixture revision is live.
2. Verify `MEDIA_BUCKET` is bound and can PUT/GET an isolated probe key `media/sha256/<SHA256>`. Existing-key replay must return identical bytes, size, and digest.
3. Apply the pinned `0002_media_asset.sql` migration once, only after `D1MediaMigrationContract.inspect` returns `READY`. Its SHA256 is pinned in code. Do not drop or recreate partial tables.
4. Read D1 schema again through `/internal/media-schema/readback`. Require expected revision, table/index DDL fingerprint, and columns. Partial/unknown/incompatible state is `HOLD_D1_SCHEMA_CONFLICT`. A second run is `ALREADY_APPLIED` and must not execute SQL.
5. Migrate canonical Drive file `1OfUZ_rh94sdXdTZMjMrKj8IjHgEBUFua` using `CreativeSchemaMigrationRunner`, which builds from the transaction's fresh exact preimage. Require unique `VEHICLE_INSTANCE_ID`, existing `原始媒體Refs`, absent `銷售素材Refs`, and a header-only change.
6. Fetch fresh file metadata and raw bytes. Require the same postwrite version/hash and `CreativeRefsSchemaMigration.verify` against the captured preimage. The new header occurs exactly once; a second run is `NO_DELTA`.
7. Bind the runtime's registry URL, read/write credential references, `MEDIA_BUCKET`, media activity signing key reference, ingress turn signing key reference, and expected schema revision. Missing bindings fail startup when media is enabled. Binding names are references, not credential values in this document.
8. In staging, write/read an isolated synthetic media object and verify SHA256, size, and bytes.
9. In staging, add/read a synthetic creative ref against a noncanonical test workbook. Confirm only the resolved row's `銷售素材Refs` cell changes and `原始媒體Refs` stays intact.
10. Run RD-021 matching end to end and require a persistence terminal receipt before final response.
11. Only then observe production behavior. Any failure halts the sequence; there is no memory, filesystem, raw-D1-blob, Google Sheet, Library, or caller-asserted-truth fallback.

## Rollback fence

The XLSX schema rollback candidate removes only the newly appended `銷售素材Refs` header when the entire column is blank. Any saved creative ref returns `ROLLBACK_BLOCKED_DATA_PRESENT`; deleting creative lineage is prohibited. D1 rollback is not automatic: retain the migrated schema and halt runtime exposure after a partial deployment until a separately reviewed recovery plan is available. R2 probe objects remain content addressed; no delete action is part of this candidate.

## Remaining integration debt

Production D1's actual prior revision, live canonical workbook topology, R2 binding, and credential references require independent preflight. Runtime media provider and controlled Host binding must be wired and tested in a later authorized stage. These repository tests do not establish live deployment or verified repair.
