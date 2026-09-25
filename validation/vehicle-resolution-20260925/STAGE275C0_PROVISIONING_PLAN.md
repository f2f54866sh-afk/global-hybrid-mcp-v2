# Stage 2.75C0 candidate: explicit migration and provisioning gates

This is a plan only. No Render database, environment variable, GitHub secret,
production commit, or deployment was changed in Stage 2.75C0.

## Proposed resource manifest

| Field | Proposed value |
| --- | --- |
| Resource name | `global-hybrid-exact-object-receipts` |
| Expected owner/workspace | `My Workspace` / `tea-da96b3psrm7s73bas9pg` |
| Region | `singapore` (same as current web service) |
| PostgreSQL major version | `17` |
| Compute plan | paid `0.1c-256mb` candidate; confirm current availability and billing before authorization |
| Initial storage | `1 GB` candidate; validate growth/retention before authorization |
| Database name | `global_hybrid_exact_object` |
| Runtime binding | Render service `DATABASE_URL` = same-region internal connection URL |
| Migration binding | GitHub Actions secret `MIGRATION_DATABASE_URL` = external TLS connection URL |
| Migration owner | manual `.github/workflows/production-db-migrate.yml` dispatch |
| Schema component/version | `exact_object_receipt` / `1` |

The candidate uses one explicit migration command. The workflow checks exact
Git commit, importability, and schema transition before running `upgrade`.
`upgrade` commits the version ledger, receipt table, and latest index in one
transaction; post-commit readback rechecks the version and structure.

The repository's default branch is `main`; current Render service tracks
`hardening/authority-promotion`. Manual dispatch availability on GitHub must be
confirmed after the workflow is published on the default branch. The workflow
checks out the exact input SHA, then verifies `git rev-parse HEAD`. Publishing
the workflow, configuring its secret, and running it are later side effects.

## Ordered future production gates

1. Freshly resolve production repo, branch, live commit, service and owner.
2. Authorize plan/cost; provision paid Render Postgres in Singapore.
3. Read back resource identity, version, database name and connection modes.
4. Publish the manual workflow on GitHub's dispatchable branch; configure the
   external TLS `MIGRATION_DATABASE_URL` as a GitHub environment secret and
   confirm external connectivity without exposing the URL.
5. Dispatch exact commit, expected schema version `0`, target version `1`.
6. Independently read back `schema_migrations`, v1 columns, PK, unique request
   constraint, JSONB, BYTEA and latest index. Failure blocks all later steps.
7. Bind Render runtime `DATABASE_URL` to the internal URL. Confirm privileges.
8. Merge/deploy only the bounded Stage 2.75 production wiring.
9. Read `/ready` and deployed commit.
10. Perform one bounded live exact-object fetch.
11. Verify durable receipt/raw write.
12. Independently read raw bytes, hash, task/object scope and latest semantics.
13. Run P1–P8.
14. Run production smoke.
15. Issue terminal completion receipt only if every gate passes.

The migration and runtime credentials are distinct bindings. Separate database
roles are preferred: migration DDL, runtime receipt-store DML. Render role
provisioning and grants have not been verified; privilege separation remains
deferred capability debt.

## Rollback

Schema v1 is additive. The previous production commit does not consume this
table and was started successfully in candidate testing with DB v1 present.
Application rollback means redeploying the previous Git commit. DB v1 and its
receipts remain; no automatic destructive down migration is provided.

## Cost and lifecycle to decide before provisioning

The paid `0.1c-256mb` PostgreSQL plan is currently listed at approximately
USD 6/month; Render lists storage at USD 0.30/GB/month. Confirm current
pricing, minimum storage and account billing at authorization. The Free DB
is unsuitable for this durable production receipt because it expires after
30 days and has no backups. No paid plan has been ordered.
