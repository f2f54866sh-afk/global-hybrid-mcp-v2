# ADR 0001: Consume current governance at runtime

## Context

The five current authority partitions already define bounded ownership, a common `DOMAIN_CONTRACT`,
Library fact authority, policy/enforcement separation, traceability, promotion/rollback, and a read-only
Witness. The runtime enforced authority, context, effects, response egress, and research, but it did not yet
provide a typed cross-owner envelope, Library write boundary, task-local trace identity, or executable
composition fitness checks.

## Problem

Adding those concepts again as new Canonical rules or importing complete enterprise frameworks would create
parallel semantics. Leaving them as documents alone would preserve a consumption gap.

## Options considered

1. Adopt separate services, a service mesh, a policy server, event sourcing, and a full model registry.
2. Add only documentation and rely on domain adapters to interpret it later.
3. Adapt the minimum mechanisms to the existing modular monolith and current Owner topology.

## Decision

Choose option 3.

- Keep exactly five Owners and the existing authority resolver/bindings.
- Use one provider-owned, consumer-validated `DomainContract` envelope for actual cross-owner handoffs.
- Keep Library as the only fact writer; admit bounded consumer projections and fact-need signals.
- Keep policy decisions in GLOBAL gates and enforce effects in `Dispatcher` before `domain.run`.
- Allocate one trace identity per governed task and logical GLOBAL/domain/Witness spans without prompt or
  hidden-reasoning capture.
- Attach the existing read-only Witness in the single composition root.
- Run a small set of executable composition and authority fitness checks.
- Derive a proportional risk floor only from observable requested effects; do not create a new compliance
  workflow.

This adapts consumer-driven contracts, PDP/PEP separation, trace/span correlation, CQRS read/write separation,
fitness functions, and canary/rollback principles to existing semantics. Current Canonical exact bytes stay
unchanged because these are runtime consumption repairs, not new authority rules.

## Why

The decision closes evidenced runtime gaps while preserving domain payload ownership, current authority,
effect isolation, and the already-verified research provider baseline. It also makes failures attributable to
contract, authority, interface, fact boundary, effect enforcement, domain execution, or closure.

## Consequence

Domain adapters can opt into the common envelope when a real cross-owner handoff exists; single-owner tasks do
not pay that cost. Production domains remain intentionally `NotConfiguredDomain` until separately authorized.
The runtime does not claim domain behavioral fitness for adapters that do not exist.

Rejected complexity includes microservices, distributed tracing infrastructure, a central data-product
platform, full event sourcing, a second policy engine, an alias broker, automated champion/challenger traffic,
and enterprise GRC workflow. Those can be reconsidered only with concrete scale or security evidence.

## Supersedes / Superseded by

Supersedes: none.

Superseded by: none.
