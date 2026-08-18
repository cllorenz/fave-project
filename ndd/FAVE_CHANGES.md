# FaVe modifications to NDD

This directory is a **fork of the upstream NDD** decision-diagram library (Li,
Zhang, Zhang, Yang, *"NDD: A Decision Diagram for Network Verification"*, NSDI
'25), vendored into FaVe as a git subtree:

- Upstream: <https://github.com/XJTU-NetVerify/NDD> (see `LICENSE`)
- Imported from upstream commit `c8414b433fe8d1d8b289be7fdee740a293371571`
  (2026-08-05, "Update per-field mixed label backends"), via a FaVe-owned fork.

NDD is planned as the second **engine** behind FaVe's backend-agnostic APKeep
adapter (BDD today, NDD next); see `../APKEEP_NDD_PLAN.md` and `../APKEEP_NDD_EVAL.md`.
As with `apkeep/FAVE_CHANGES.md`, we state our changes prominently here. Kinds:

- **[NEW]** — a capability NDD did not have;
- **[FIX]** — a correctness bug in the upstream code;
- **[INFRA]** — build, test, and tooling that do not change library behaviour.

All items below are reachable via `git log -- ndd/`.

---

## 1. Differential-vs-BDD trust suite on FaVe's IPv6 profile  **[INFRA]**

`src/test/java/org/ants/jndd/diagram/NDDIPv6DifferentialTest.java` (**new test**).
The upstream suite exercises the paper's IPv4-style profile; FaVe's workloads are
IPv6, so this adds a trust suite on **two 128-bit IPv6 address fields** (src, dst)
plus small transport fields — the case the plan flags as highest-risk
(`createVar`/`declareField` at 128 bits). It is a *differential against BDD*: every
NDD boolean op is checked to commute with the `toBDD` homomorphism
(`toBDD(op_NDD(P,Q)) == op_BDD(toBDD(P), toBDD(Q))`) using the same JDD engine NDD
runs on (`NDD.getBDDEngine()`), compared by **canonical node-id equality** — an
exact set-equality oracle that (unlike `satCount` over a 2^280 space) never rounds.
`exist` is checked with layout-independent algebraic identities because NDD fields
share a BDD variable template (so a `getBDDVars`-built cube is not in the `toBDD`
variable space). 7 tests: 128-bit field addressing; IPv6 prefix containment/
disjointness; boolean-op differential (AND/OR/NOT/DIFF/XOR, 400 iters); exist
projection semantics; RONDD canonicity (AND-order + distributivity yield the same
node id); de Morgan/absorption. No upstream behaviour changed; runs in the existing
JUnit 5 + surefire harness (`mvn test`). Full context: `../APKEEP_NDD_EVAL.md` §2.1.

---

*Full FaVe-side context (why NDD, the field-locality GO/NO-GO, the integration
roadmap) lives in `../APKEEP_NDD_PLAN.md` and `../APKEEP_NDD_EVAL.md`.*
