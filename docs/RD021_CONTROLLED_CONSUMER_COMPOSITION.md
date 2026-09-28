# Controlled consumer composition candidate

Base: `56f1a6ab61d08846842bb2b03aeda5f02c6f35e5`.
This composition candidate does not connect the natural ChatGPT Sales workflow, provision a
production database, deploy, or switch canonical authority.

## Provider inventory

| Protocol | Concrete implementation | Input source | Authority source | Config source | Readback | Fail closed |
|---|---|---|---|---|---|---|
| ServerVerifiedMutationProvider | No production implementation; controlled test only | Upstream verified mutation source unavailable | Server verification required | Trusted bootstrap injection, not request/env module loading | CAPABILITY_DEBT | Postgres startup rejected |
| EvidenceAdmissionPort | No production implementation; controlled test only | Independent evidence registry unavailable | Independent server evidence | Trusted bootstrap injection | CAPABILITY_DEBT | Postgres startup rejected |
| HostCurrentStateResolver | No production implementation; controlled test only | Actual Host current state unavailable | Current conversation/turn owner | Trusted bootstrap injection | CAPABILITY_DEBT | Postgres startup rejected |
| EvidenceReceiptProvider | No production implementation; controlled test only | Signed verifier receipts unavailable | Existing EvidenceReceiptSigner verification | Trusted bootstrap injection | CAPABILITY_DEBT | Postgres startup rejected |
| NonceClaimStore | InMemoryNonceClaimStore is explicitly test-only | Shared durable claim store unavailable | Server transport replay admission | Existing codec replay_store injection | CAPABILITY_DEBT | In-memory implementation rejected for production scope |
| MediaAssetRepository | D1MediaAssetRepository exists | Existing D1 media-asset read endpoint | Server credentials and validated asset readback | Explicit HTTPS base URL/read/write secrets | Existing by_id validates asset; composition health contract still missing | MEDIA_REGISTRY_UNAVAILABLE / registry HOLD; no automatic binding |

No new upstream endpoint, secret, vehicle identity, verified delta or production provider is invented.

## Composition and readiness

`configured_application` is the single MCP startup factory. `ConsumerBindings` is a Python object
supplied by trusted bootstrap code. It is not request data, a model tool argument, an import path
from environment variables, or a provider registry populated with test doubles.

Postgres startup requires DSN plus admitted mutation/evidence/Host/receipt/ingress/nonce bindings.
The existing trusted compiler, signer and ingress codec are reused. Media-enabled startup also
requires the media repository. A media-bound request without that repository remains fail-closed
through the existing compiler. No deployment bootstrap currently supplies production providers:
setting only GLOBAL_CANONICAL_VEHICLE_STORE_MODE=postgres and a DSN intentionally fails startup.

Providers must implement their protocol method, a stable `provider_id`, and a side-effect-free,
bounded `readback()` returning `provider_id`, `status=BOUND`, and `scope=PRODUCTION` or
`CONTROLLED_TEST`. This is configuration health, not an evidence credential; the existing receipt
signature, request digest, identity and independent evidence checks still govern each request.
Production scope is the default; controlled-test scope is an explicit code-only test invocation.

Readiness reports mode, scope, provider binding status, completion-fence composition, and runtime
commit/branch. Arbitrary readback metadata, DSNs, keys and exception messages are excluded. Runtime
provider loss yields ready=false/503 in postgres mode. BOUND does not certify database availability,
upstream semantic correctness, a natural consumer, or production cutover admission.

## Existing completion path

The unchanged trusted ingress/compiler/Dispatcher path calls the existing canonical completion
handler and TransactionalVehicleStore. The handler binds the resulting terminal to its already
validated workbench target, so the existing egress validator can check task ID, file ID and
disposition. Store transactions and egress eligibility rules are unchanged; no second fence exists.

Controlled tests use isolated SQLite for fast local coverage and the existing PostgreSQL 18 CI
service for real transaction/readback coverage. Tests cover both successful dispositions, startup
debt, runtime provider loss, transport forgery/expiry, caller injection, database-triggered rollback,
committed-write/readback failure, and missing terminal receipts. Test providers are never default
production bindings. Production Host/evidence sources and durable nonce ownership remain debt.
