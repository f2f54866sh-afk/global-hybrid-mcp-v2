# Public Copy terminal execution lineage

This bounded repair uses the existing `TraceBus`, SQLite `runtime_event_journal`,
`ReadOnlyWitness`, Dispatcher and response egress. It does not change Sales
Canonical, the Sales + Visual V84 profile/kernel, or any product acceptance policy.

## Integration boundary

The host identifies a public commercial Copy request with
`TaskRequest.public_commercial_copy=True` and supplies the nonempty, distinct
`public_copy_requirement_ids` from its task requirements. Ordinary requests keep
their existing path. This is an explicit host contract, not a natural-language
classifier; hosts must set it for every public Copy request.

Configure `create_application(public_copy_checks=...)` (or Dispatcher) with an
application-owned `PublicCopyChecks` implementation that executes the existing
checks. No production implementation is installed here. Missing configuration,
missing durable binding, malformed receipts and execution exceptions fail closed.
Domain-result evidence and prompt self-reports cannot configure this port or
supply its execution receipts. Test ports and Sales results are recording fakes.

Each call receives a stage, immutable canonical JSON for the exact terminal
candidate (`output` plus `final_response_object`), the immutable acceptance witness
JSON for subsequent calls, and the requirement IDs. It returns `CopyCheckResult`:

- `decision`: `PASS` or `FAIL`.
- `exact_candidate_digest`: SHA-256 of canonical candidate JSON (UTF-8, sorted
  keys, compact separators, Unicode preserved, nonfinite numbers rejected).
- `witness_digest`: subsequent checks must independently return the digest of
  the supplied witness JSON. Production and Detached receive the identical JSON.
- `details`: JSON execution proof. Acceptance requires
  `public_copy_acceptance_witness`, `non_binding_literal_leak_check` and
  `supporting_proof_serialization`, each `PASS`; a nonempty `supporting_proof`
  object; and `hard_requirement_coverage` mapping every requested ID to
  `{decision: PASS, exact_candidate_digest: ...}`. Invariance and audit require
  `disposition_invariance: PASS` and `copy_egress_audit: PASS`, respectively.

The runtime computes the witness digest over the acceptance receipt's exact
candidate digest and details. It serializes the proof before emitting the receipt;
it does not infer semantic product correctness from the copy text. The configured
product checks remain responsible for their actual evaluations.

## Durable consumption

The candidate, five required stages, and final `response_egress` are appended via
TraceBus to the existing journal. The existing journal envelope supplies runtime
task ID, dispatch task ID and trace ID. Each check and egress reference the actual
journal event IDs of all its predecessor inputs. Both oracle receipts carry the
same acceptance witness digest. The candidate receipt also references its task
contract and records the requirement manifest.

At egress and closure, Witness queries the SQLite journal, bounded by the terminal
event ID. It requires a single ordered chain in the same dispatch/runtime task and
trace, all decisions PASS, exact candidate and witness digest equality, complete
candidate-bound coverage and the required proof checks. Missing, duplicate,
out-of-order, mismatched or post-terminal evidence fails. All eight check results
are persisted as `WITNESS_ASSESSMENT` in that same journal; failures also use the
existing `WITNESS_FINDING` mechanism. Dispatcher suppresses Copy output on failure
before committing the result. No second store or tracing authority is introduced.

After reopening SQLite, `ReadOnlyWitness.assess_public_copy(...)` independently
recomputes the eight checks using the conversation, runtime task, dispatch task,
trace and terminal event IDs; it does not trust the persisted assessment's PASS.
Public Copy does not use the ordinary committed-output replay shortcut: a new
execution requires a fresh runtime task and returns
`PUBLIC_COPY_REPLAY_REQUIRES_NEW_DISPATCH` otherwise. Read-only journal inspection
of the completed execution remains available after reopen.

## Qualification

`tests/test_public_copy_lineage.py` covers positive dispatch/checkpoint/reopen;
every missing required stage; candidate and witness mismatch; invariance and audit
failure; self-asserted and post-hoc proof; ordinary-task isolation; invalid receipt,
proof and evaluator errors; and replay isolation. All use synthetic Copy and
recording checks, without real Sales/product/image or publishing side effects.

This qualifies traced-runtime implementation only. It does **not** prove that a
ChatGPT Sales + Visual Project is connected to this runtime, or that a production
product oracle adapter is configured or semantically qualified.
