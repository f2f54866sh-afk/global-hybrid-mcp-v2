# Authoritative inventory identity candidate

Base: `76d13bed291c9d665d3e932945d9760a736d34f5`.

The source is the exact Google Sheet `12NL4A7CQ_MsUrRWyDgVDsrzFgKJJBdg94HQo75soikI`,
tab `車源`, range `車源!A1:N`. `GoogleInventorySource` makes read-only Drive metadata,
Sheets metadata, and Sheets values requests through a deployment-owned token producer.
Its service-account factory requests both Sheets read-only and Drive metadata read-only
scopes; the existing reconciliation token's Sheets-only default is insufficient.
No production token, turn-referent owner, or evidence provider is bound by this candidate.

`read_current_snapshot` brackets the values read with metadata reads. The reads must
agree on file ID, modified time, sheet ID, and sheet name. The token digests the file
ID, sheet ID/name, range, modified time, and canonicalized returned values. A metadata
change fails with `HOLD_INVENTORY_SOURCE_ADVANCED`. Drive revision ID is not assumed.

Every nonempty row has a deterministic *observation* ID derived from file ID, sheet ID,
sheet name, row number, source snapshot digest, and currentness token. A row move,
changed content, or source version changes this ID. It is never a physical vehicle ID.
The resolver selects a matching observation using trusted make/year/model referent
fields. A unique match without durable identity is `INSTANCE_CANDIDATE`, with no
`vehicle_instance_id`. Ambiguity is `HOLD_IDENTITY_CONFLICT`.

Only an existing canonical binding or independently admitted VIN, plate, or canonical
identity evidence can yield `INSTANCE_BOUND`. The SQL candidate verifies that the
target vehicle already exists; it never mints an ID. `promote` commits the observation
binding in the same transaction as its conflict checks, then the resolver fresh-reads
it. Repeating the same evidence is idempotent. A key already tied to another vehicle,
another current observation, or a historical observation of this source holds. No
mutable row attributes or row number establish physical identity.

Migration 0004 extends `vehicle_source_observation` with nullable source sheet fields,
currentness digest, binding state, and current marker. It replaces the global row
unique constraint with source-scoped current/snapshot indexes and retains uniqueness
for legacy XLSX rows. This reuses the existing observation table. Stage F import and
verification remain scoped to their frozen XLSX file; Google observations do not alter
the 14 observations / 11 vehicles / 3 unbound import receipt.

This candidate leaves Root A open: production service-account authorization, trusted
conversation referent issuance, and independent document/media evidence admission
still require binding. The controlled fixtures are not production providers.
