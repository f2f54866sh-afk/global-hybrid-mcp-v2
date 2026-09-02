# Blind-spot and media activation semantic audit

Baseline: `0076eaffdade5abc02ead3a3bb11938d6ccabee3`.

| Candidate | Existing mechanism | Classification | Minimum patch |
|---|---|---|---|
| Untrusted external evidence boundary | Context provenance/currentness, history quarantine, research source capture, bounded evidence receipts | PRESENT_PARTIAL | External content is explicitly `DATA_ONLY / NO_AUTHORITY_EFFECT`; source instructions are ignored and obvious instruction-shaped research output fails closed. |
| Dissimilar/falsifying validation | GLOBAL §10A and Witness §11B already require evidence capable of falsification | PRESENT_PARTIAL | Typed gate distinguishes independent raw/readback/consumer/counterexample paths from owner self-certification and role restatement. |
| Pre-incident blind-spot scan | Proactive Witness audit, adversarial tests, risk floor, promotion/rollback | PRESENT_PARTIAL | Read-only Witness exposes one bounded high-impact precheck with at most five findings and no score/framework. |
| Media activation and audience learning | Sales paid-ad eligibility, target-buyer hypothesis, acquisition brief, outcome funnel/attribution; Library audience evidence | TRUE_GAP | Sales-owned media plan, current capability admission, controlled audience comparison, and campaign outcome calibration contracts. |

No Owner, Canonical, policy engine, acquisition pipeline, or second Witness was added. The current Sales
acquisition path remains authoritative. Media is a sibling activation payload after paid-ad eligibility, not a
new authority partition. Library evidence remains evidence; Sales makes the activation decision.

## Evidence-path decisions

- External pages and retrieved documents are treated as untrusted content because prompt injection is an
  external-content attack and needs layered source/sink controls. Reference:
  [OpenAI prompt injection overview](https://openai.com/safety/prompt-injections/) and
  [OpenAI agent resistance design](https://openai.com/index/designing-agents-to-resist-prompt-injection/).
- Validation uses a materially dissimilar path rather than another role reading the same summary. The patch
  reuses current GLOBAL §10A/§11B and adds only a typed receipt; it does not claim a second independent model.
- The pre-incident scan operationalizes existing proactive Witness semantics and NIST's testing/evaluation/
  verification/validation orientation without importing an enterprise risk-management system. Reference:
  [NIST AI Resource Center](https://airc.nist.gov/).
- Media strategy values are candidates, never permanent demographic rules. Current platform capability is an
  input receipt rather than hardcoded truth. Meta currently documents both automated/manual placement choices,
  A/B testing, and permission requirements for customer-list audiences; these facts can change and therefore
  must be refreshed for a real campaign. References:
  [Meta Reels ads and A/B testing](https://www.facebook.com/business/ads/facebook-instagram-reels-ads) and
  [Meta Customer List Custom Audiences Terms](https://www.facebook.com/legal/terms/customaudience/update).

## Explicitly rejected duplicates

- prompt-injection policy engine separate from the existing TaskFirewall;
- second Witness or validation Owner;
- FMEA/STPA/GRC scoring platform;
- MEDIA Owner or separate acquisition pipeline;
- hardcoded demographic profiles or evergreen Meta capability claims;
- automatic causal winner selection from CTR/CPM/message volume;
- real campaign execution or audience upload without a separately authorized domain adapter.
