# APKeep Core (Java) Testing Strategy

## Scope

The vendored APKeep fork under `apkeep/` (Java, atomic-predicate verifier). This
is the **engine** behind FaVe's APKeep backend (`fave/apkeep/`). It is *not*:

- the FaVe Python side (adapter, in-process driver, integration tests) — that is
  [`TESTING_STRATEGY_PYTHON.md`](TESTING_STRATEGY_PYTHON.md);
- the NetPlumber C++ backend — that is `net_plumber/` (items 7–8 in `TODO.md`).

This document exists because we intend to **extend** the APKeep core (more header
fields, packet rewrites, multi-field forwarding) to run further workloads
(`wl_stanford`, `wl_tum`, `wl_up`; see `APKEEP_BACKEND.md` §9). Extending an
untested core is reckless, so this is the prerequisite hardening pass.

## TL;DR

- **The APKeep core has zero Java unit tests today** — no `src/test`, no JUnit /
  surefire / jacoco in `pom.xml`, and the build runs `-DskipTests`. It is covered
  only *indirectly* by five Python integration tests (`fave/test/test_apkeep_*.py`),
  and only on the paths those happen to exercise (IPv4 dst-IP forwarding +
  IP-only ACLs + our `ReachabilityChecker`).
- **Principle: test before extend, and prioritize by what we use.** Harden the
  reachability-critical path (the code every run depends on) and the components
  we are about to extend, *first*. Defer code we do not use until we use it.
- **Phase 0** (this doc) adds a JUnit5 + jacoco harness and characterization /
  unit tests for the critical path, with a coverage ratchet on the touched
  packages. It gates the extension phases in `APKEEP_BACKEND.md`.

## Current state — grounded in what runs

`mvn -o package -DskipTests` (via `fave/test/apkeep_smoke.sh`) builds the fat jar;
no test phase runs. Indirect coverage today:

| Python test | What of the core it exercises |
|---|---|
| `test_apkeep_lib` | snapshot loader (`main.APKeep`) + `Checker.printLoop` (loop golden) |
| `test_apkeep_acl` | `ACLElement` permit/deny + src-IP-seeded `ReachabilityChecker` (IP-only) |
| `test_apkeep_adapter` / `_wl_ifi` / `_i2` | `ForwardElement` LPM, `Network` in-memory build + ACL wiring, division traversal |
| `test_backend_differential` | the above vs NetPlumber on wl_ifi |

Gaps: no isolation (everything goes through JPype + a full model), the **5-tuple
ACL** paths (proto/ports) are never hit, **rewrites** (`NATElement`/`RewriteRule`)
are never hit, and the AP-maintenance invariants (`APKeeper`, `Element` split/
merge/transfer) and BDD encoders are only implicitly trusted.

## Principles

1. **Test before extend.** No core change lands without unit coverage of the
   code it touches, written first to lock current behavior.
2. **Prioritize by use.** Cover the reachability-critical path (used every run)
   and the components on the extension's path. Code we do not call is lowest
   priority — test it only when a workload starts using it.
3. **Characterization tests double as documentation.** Several core semantics
   were reverse-engineered (priority = *higher-wins*; cisco first-match → descending
   priority; permit/deny ports; the src-IP seed; the `_in`/`_out` ACL-node naming
   convention). Pin them in tests so they are documented and regression-proof.
4. **Ratchet, don't gate-on-100%.** A jacoco floor on the critical-path packages
   that only ever rises — mirroring the Python `COVERAGE_MIN` ratchet.
5. **Unit in Java, end-to-end in Python.** Test the core in isolation with JUnit
   (no JPype, no FaVe); keep the Python tests for integration/differential. This
   also makes the vendored fork self-testing — good fork hygiene.

## Coverage map — by what we use (drives priority)

| Component | Used… | Tested today | Priority |
|---|---|---|---|
| `common/BDDACLWrapper` — `encodePrefixBDD`, `encodeSrcIPPrefix`, `encodeACLBDD` (5-tuple), ∃-quant/`replace`, **variable layout** | every run; **extended** for new fields | IPv4-prefix path only, indirectly | **P0** |
| `apkeep/core/APKeeper` — AP split/merge/transfer, `getAPExp` (our seed), min-EC invariant | every run | indirectly | **P0** |
| `apkeep/elements/Element` (base) + `ForwardElement` — encode/insert/`forwardAPs`, **LPM + priority** | every run | indirectly | **P0** |
| `apkeep/elements/ACLElement` + `common/ACLRule` — permit/deny, **5-tuple proto/ports**, first-match prio | wl_ifi (IP-only); stanford needs proto/ports | IP-only only | **P0** |
| `apkeep/core/Network` — in-mem init, `addACLs`/`addNATs` wiring, `getConnectedPorts`, `isACLNode`/`getACLElement`, `getACLSeedAPs` (ours) | every run | indirectly | **P0** |
| `apkeep/checker/ReachabilityChecker` (ours) — `isReachable` ×2, division traversal, src-seed | every run | end-to-end only | **P0** |
| `apkeep/elements/NATElement`, `apkeep/rules/RewriteRule` — ∃-quant rewrites | **new** (state-shell, `APKEEP_BACKEND.md` Phase 2) | not at all | **P1 — before state work** |
| `apkeep/utils/Evaluator`, `Parameters` | bootstrap | indirectly | low |
| `apkeep/main/APKeep` (snapshot loader) | `test_apkeep_lib` golden | golden-pinned | low (pinned) |
| `apkeep/checker/Checker` (loops); `ForwardingGraph`/DFG (path/policy); `common/ForwardingRule6` | **not used** by us | — | skip until used |

## Harness (Phase 0 setup)

- Add to `apkeep/pom.xml`: JUnit 5 (jupiter) test dependency, `maven-surefire-plugin`,
  `jacoco-maven-plugin` (report + `check` with a per-package line floor on
  `apkeep.elements`, `apkeep.core`, `apkeep.checker`, `common`).
- Run `mvn test` from `fave/test/apkeep_smoke.sh` (the CI integration tier already
  builds the jar there), so the gate runs wherever the APKeep tests run.
- Source under `apkeep/src/test/java`, mirroring the package layout.
- Coverage floor is a **ratchet** — record the Phase-0 baseline, raise it as
  tests are added, never lower it.

## Phase 0 — prioritized test roadmap

Each class pins the behavior the extension phases depend on:

1. **`BDDACLWrapperTest`** — prefix / src-IP / ACL-5-tuple encoders (proto range,
   port range, cisco wildcard, `any`/`null`); ∃-quant + `replace`; and a
   **variable-layout lock** (assert the field bit-offsets so a later field
   addition cannot silently shift existing fields).
2. **`ForwardElementTest`** — LPM correctness; **priority = higher-wins** (the bug
   class behind the wl_ifi default-route shadowing); the `/0` default route.
3. **`ACLElementTest`** — permit/deny; **full 5-tuple match (proto + ports —
   currently never exercised)**; first-match → descending priority; the implicit
   default-deny.
4. **`APKeeperTest`** — `getAPExp` (the reachability seed); the **minimum-EC
   invariant** (Theorem 1) on small hand-built networks (split/merge correctness).
5. **`NetworkTest`** — in-memory `initializeNetwork`; ACL/NAT element wiring +
   `isACLNode`/`getACLElement` naming; `getConnectedPorts`; `getACLSeedAPs`.
6. **`ReachabilityCheckerTest`** — both `isReachable` overloads; division
   (permit/deny) traversal; arrival semantics (egress + link-destination ingress);
   loop termination; src-IP seeding (denied vs permitted source).

**Deliverable / gate:** green `mvn test`; jacoco baseline recorded on the P0
packages; floor enforced in CI. P1 (`NATElement`/`RewriteRule`) is written when
Phase 2 (state-shell) begins.

## Sequencing & gating

Phase 0 is a **prerequisite** for every extension phase in `APKEEP_BACKEND.md`
(§9): no element/encoder/wiring change lands without its Phase-0 (or P1) coverage
first. Commit discipline: all `apkeep/` core + test changes are **subtree**
commits, kept separate from FaVe-side (`fave/`, `test.sh`) commits.
