# NetPlumber (C++) Testing Strategy

A prioritized plan for hardening the NetPlumber verification backend's core API
so it can be refactored with confidence, grounded in a file-by-file analysis of
`net_plumber/src/` and the existing CppUnit suite.

## Scope

**This strategy covers `net_plumber/` (the C++ verification backend) only.**

`fave/` and `policy_translator/` (the Python tools) are tracked separately in
[`TESTING_STRATEGY_PYTHON.md`](TESTING_STRATEGY_PYTHON.md) (TODO item 9). This
document is the counterpart for the engine and the actionable home of TODO
items **7** (C++ hardening) and **8** (oracle testing); it builds on the
header-space soundness work already done in items **1h**/**1i**.

**It targets the *canonical* build only.** Per the author, the supported
feature set — the one evaluated in the PhD thesis — is the default build:

```
USER_FLAGS = -DWITH_EXTRA_NEW -DCHECK_ANOMALIES -DSTRICT_RW
```

instantiated as `NetPlumber<hs, array_t>` (`main.cc:392`). Everything behind the
other flags is **explicitly out of scope** as abandoned or experimental:

| Flag(s) | Status (per author) |
|---|---|
| `GENERIC_PS` + the `PacketSet` abstraction | Abandoned experiment (BDD-as-low-level-datastructure). Parked behind the unsolved BDD masked-rewrite problem; **low priority**. |
| `USE_BDD` / `BDDPacketSet` | Same; depends on the BDD rewrite problem. `psand`/`count_diff` are `// TODO` stubs (`bdd_packet_set.cc:421,452`). |
| `NEW_HS` | Abandoned experiment (header-space simplification, hit a dead end). |
| `PIPE_SLICING`, `CHECK_REACH_SHADOW`, `CHECK_SIMPLE_SHADOW`, `DENSE_LOOPS`, `SORTED_DIR`, `SORTED_FWD` | Minor experiments. |
| `USE_DEPRECATED` | Legacy functionality from the original NetPlumber, never used. |
| `USE_GROUPS` | Off by default; rule-grouping path. |

Their fate (keep-but-quarantine vs. delete to shrink the `#ifdef` surface) is a
**future consideration**, not part of this testing plan — see the bottom of this
file and TODO item 7.

Everything below assumes the existing tiered runner (`./test.sh integration`
runs `make -C net_plumber/build test`) and that the C++ runner now propagates
failures (item 1i).

---

## TL;DR

The engine has a **solid low-level skeleton** — `array_unit.cc` (1129 LOC) and
`hs_unit.cc` (2009 LOC) exercise the `array_t`/`hs` C API that *is* FaVe's real
verification data structure, wired into a CppUnit harness run by
`net_plumber --test` (94 tests, green). But the safety net has four structural
holes for refactoring:

1. **The orchestrator API is barely tested.** `net_plumber_basic_unit.cc`
   covers ~3 of the ~30 public `NetPlumber` methods (`net_plumber.h:198-339`).
   `check_compliance`, the event API, the query/getter API, and nearly all
   error paths have **no** tests.
2. **Tests assert hand-picked cases, not semantics.** The algebra suites check
   specific inputs against specific expected outputs. There is **no algebraic-law
   coverage** (De Morgan, double-negation, `minus ≡ isect∘cmpl`, …) and **no
   concrete-packet oracle** — so a representation refactor that is wrong-but-
   self-consistent can still pass.
3. **Plumbing tests lean on internals and chain together.** `net_plumber_-
   plumbing_unit.cc` asserts via `get_pipe_stats`/callback instrumentation, and
   the `test_probe_transition_*` cases call `test_routing_*` directly, so a
   single failure cascades and the cause is obscured.
4. **Two confirmed bugs live in untested paths** (`remove_link`,
   `check_compliance`) — ready-made regression tests.

The plan: pin **semantics** with a concrete-packet oracle + algebraic laws over
`array_t`/`hs` (P0), pin **API contracts** through the public interface (P1, and
fix the two bugs there), then conditions/RPC (P2), under
sanitizer/coverage builds (item 7).

---

## Current state — grounded in the build

**Backend instantiation** (`main.cc:376-393`): the canonical `main()` runs
`typed_main<hs, array_t>`. The `GENERIC_PS`/`USE_BDD` branches that select the
`PacketSet` wrappers are never compiled in the supported build.

**What the default `make test` compiles and runs (the 94):**

- `array_unit.cc` / `hs_unit.cc` — the `array_t`/`hs` C API. **In scope, the
  foundation.** Already strong on specific cases (incl. the item-1h regression
  microtests `test_array_isect_len4_regression`, `test_array_is_sub_eq_len4_-
  regression`).
- `conditions_unit.cc` — 7 of the `Condition` predicate types, with a reusable
  `create_flow()` fixture (`conditions_unit.cc:217`). In scope.
- `net_plumber_basic_unit.cc` — 3 methods (`add_link`/ports, `add_table`/
  `add_rule` ids, `RuleNode` construction). In scope; thin.
- `net_plumber_plumbing_unit.cc` — flow routing/pipeline scenarios. In scope but
  internals-coupled and interdependent (see hole #3).
- `net_plumber_anomalies_unit.cc` — partly active (`CHECK_ANOMALIES` is on;
  the `CHECK_*_SHADOW` cases are not).

**Compiled out by default (out of scope here):** `packet_set_unit.cc`
(`GENERIC_PS`-gated; its `test_to_json` is a literal `printf("TODO: implement")`
at `packet_set_unit.cc:91-92`), and the entire `net_plumber_slicing_unit.cc`
(1313 LOC, `PIPE_SLICING`-gated).

---

## Strategy — five principles

1. **Harden the canonical build, ignore the parked configs.** One supported
   configuration (`<hs, array_t>`, default flags) means no test matrix to
   maintain — and it means the abandoned `#ifdef` branches are *not* a testing
   target. (They are instead a refactoring *hazard*; their removal is a separate
   future consideration.)

2. **Pin semantics with a concrete-packet oracle, not snapshots.** For a small
   header length (1–2 bytes ⇒ 8–16 bits), enumerate all `2ⁿ` concrete packets,
   compute each set operation concretely (plain bitset math), and assert the
   symbolic `array_t`/`hs` result has identical membership. This pins *meaning*
   independent of representation — the single most powerful guard for refactoring
   the compaction / diff-list / wildcard machinery in `array.c`/`hs.c`. (It is
   also exactly the oracle a future BDD backend would have to match, so the work
   is reusable if the parked PacketSet line is ever revived.)

3. **Test contracts through the public API, not internal state.** Assert
   observable behavior of `NetPlumber`'s public methods
   (`net_plumber.h:198-339`) and of getters, rather than reaching into pipe
   lists. Break the `test_probe_transition_* → test_routing_*` call chains so
   failures localize.

4. **Property / algebraic-law testing for the algebra.** On top of the
   case-based suites, add laws that must survive any representation change:
   commutativity/associativity of `hs_isect`/`hs_add`, De Morgan, double
   negation (`array_cmpl`/`hs_cmpl`), `hs_minus(A,B) ≡ A ∩ ¬B`, idempotence,
   identity/annihilator, `is_empty ⇔` empty, `A==B ⇔` mutual subset, and the
   `STRICT_RW` rewrite identities (zero-mask = identity, full-mask = constant).

5. **characterize → fix → flip for confirmed bugs.** Add a test that captures
   today's (buggy) behavior, fix the code, flip the assertion to the correct
   contract. Same discipline as the Python strategy.

---

## Prioritized roadmap

### P0 — Header-space algebra: oracle + laws · highest leverage — DONE (2026-06-25)
The `array_t`/`hs` engine is the soundness-critical core and the thing most
likely to be refactored. Lock its *semantics*.
- [x] **Concrete-packet oracle harness** — `src/headerspace/test/oracle_util.h`
  decodes `array_t`/`hs` into characteristic vectors over all `2^(8·len)`
  packets via the raw 2-bit layout only (never the algebra under test), for
  `len ∈ {1,2}`. `OracleTest` (`oracle_unit.{h,cc}`) checks `isect`/`cmpl`/
  `rewrite` and the predicate laws against it.
- [x] **Algebraic-law tests** — De Morgan and `minus ≡ isect∘cmpl` as pure
  API-vs-API laws compared in the concrete domain; commutativity/idempotence
  and the `STRICT_RW` rewrite identities (zero-mask = identity, full-mask =
  constant).
- [x] **`hs_compact` membership-invariance** — set preserved across `compact`,
  directly guarding the item-1h over-merge class.
- **Outcome:** `net_plumber --test` → **OK (110)**. The oracle found and fixed
  two engine bugs — see #C4/#C5 below. **Lessons that shaped the tests:**
  `array_is_sub_eq(a,b)` means *a ⊆ b* (first arg is the subset; the header
  comment is misleading), and the bitwise predicates (`is_empty`/`is_eq`/
  `is_sub_eq`) do **not** treat a z-bit cube as empty (emptiness is via
  `array_has_z`/`isect`), so the predicate laws use normalised non-z cubes.
- *Not done (minor):* `array_minus`/`comp_diff` and `unroll∘compact` identity
  were left out — `minus`/`comp_diff` are NEW_HS-oriented and out of the
  canonical scope.

### P1 — Orchestrator API contracts + the two confirmed bugs · `<hs, array_t>`
Raise `NetPlumber` from ~3 to broad public-method coverage, contract-style.
- [ ] **Topology symmetry**: `add_link`/`remove_link` keep `get_dst_ports`/
  `get_src_ports` mutually consistent. *(Fails today — catches bug #1.)*
- [ ] **`check_compliance` contract** incl. unknown-`dst` input. *(Crashes today
  — bug #2.)*
- [ ] **Registry/lifecycle**: id determinism, rule replacement at an existing
  index frees the old rule, removed table/node/source truly gone.
- [ ] **Error-path contracts**: invalid ports, nonexistent table/node, duplicate
  source id — assert the *documented* outcome (return 0 / log / no-op) so it
  stops being implementation-defined.
- [ ] **Event API**: `get_last_event`/`set_last_event` (zero coverage today).
- [x] **De-chained `test_probe_transition_*`** from `test_routing_*` (principle 3,
  DONE) — extracted assertion-free `setup_routing_*` builders; the six
  probe-transition preconditions now call those instead of the asserting
  `test_routing_*` methods, so a routing regression no longer cascades.

### P2 — Conditions (pure logic) + RPC boundary — DONE (2026-06-25; depth guard deferred)
- [x] **Boolean-composition laws** for `And`/`Or`/`Not` + De Morgan
  (`test_boolean_conditions`). (`HeaderCondition` empty-intersection→false was
  already covered by the existing `test_header`.)
- [x] **`to_json` ↔ `val_to_cond` round-trip** — `test_cond_json_roundtrip`
  (serialise → reparse → serialise must be stable).
- [x] **Malformed-input parser tests** — `test_cond_parse_malformed`
  (null/unknown/missing/non-string `type` → `nullptr`; a path with a malformed
  pathlet still parses). This exposed and fixed a crash on bad RPC input
  (#C6 — `val_to_cond`/`val_to_path` aborted via an `assert` in `asCString`).
- **Outcome:** `net_plumber --test` → **OK (117)**.
- [x] **Recursion depth guard (DONE)** — `val_to_cond` bounds `and`/`or`/`not`
  nesting at `MAX_CONDITION_DEPTH` (256) and propagates null/too-deep operands
  to `nullptr` (no node with a null child). `val_to_path` is iterative, so it
  needs none. `test_cond_parse_malformed` asserts a 5000-deep chain → `nullptr`.
- [x] **`check_compliance`-parser hardening (DONE, #C7)** — extracted a
  validated, testable `val_to_compliance_rules` (+ `free_compliance_rules`):
  rejects malformed input (non-object / non-numeric key / short / ill-typed
  tuple) instead of throwing (`stoull`) or asserting (`asUInt64`), and fixes the
  pre-existing `cond`-array leak. Pinned by `test_compliance_rules_parse`.

### Cross-cutting — sanitizer/coverage builds (TODO item 7)
- [x] **Sanitizer CI job (DONE)** — `sanitizers` job in `ci.yml` rebuilds with
  `-fsanitize=address,undefined -fno-sanitize-recover=all` (via `DEBUG_FLAGS`)
  and runs `net_plumber --test` under ASan+UBSan+LeakSanitizer. The suite is
  clean under all three; bringing it up fixed three benign pre-existing UBs in
  `net_plumber_utils.cc` (#C8). This is the class of guard that catches the
  `remove_link` UB / `hs_add_hs` OOB automatically on every change.
- [ ] Longer term, `gcov`/`lcov` C++ coverage to measure the above.

---

## Confirmed bugs found during analysis

Source-verified in the canonical build (→ characterize→fix→flip regressions).
**All FIXED (2026-06-25).** #1/#2/#3 are TODO items #C1/#C2/#C3; #4/#5 (found by
the P0 oracle) are #C4/#C5. #C4/#C5 touch soundness-critical engine code
(`hs.c`) and warrant author review.

- [x] **#1 — `net_plumber.cc:915-920` (`remove_link`)**: the second loop iterates
  `v_inv = inv_topology[to_port]` but calls `v->erase(it)` — erasing from
  `topology[from_port]` with an iterator into a *different* vector (**undefined
  behavior**), and compares `(*it) == to_port` when `v_inv` holds source ports
  (should be `from_port`). Net effect: inverse topology never cleaned + UB on
  erase. High.
- [ ] **#2 — `net_plumber.cc:2255` (`check_compliance`)**: `this->id_to_node[dst]
  ->source_flow` uses `std::map::operator[]`, which inserts a `nullptr` for a
  missing `dst` and dereferences it → **null-pointer crash** on a compliance
  query naming an unknown destination. High (on the live verification path).
- [x] **#3 (smell) — `net_plumber.cc:2264`**:
  `if (!valid && any || valid && !any)` relied on `&&`-over-`||` precedence.
  Parenthesised (no behavior change).
- [x] **#4 — `hs.c hs_cmpl` (non-NEW_HS)**: a universe (`xxxxxxxx`) element among
  other positive cubes was `continue`d past, but `~(⋃cᵢ)=⋂~cᵢ` is an
  intersection so an empty factor must zero the result. `~(c1 + xxxxxxxx + c3)`
  gave `~c1 ∩ ~c3` (236 packets) instead of ∅; reachable on compacted hs, and
  propagates into `hs_minus`. **Soundness.** Fixed: empty the result and stop.
- [x] **#5 — `hs.c hs_add_hs` (non-NEW_HS)**: a diff-bearing source desynchronised
  the parallel `elems`/`diff` arrays (diff cubes appended via
  `vec_append(...,true)`, which grows `elems` but not `diff`) → out-of-bounds
  **crash**. Fixed: append each source element with its diff cubes into the new
  element's diff slot.
- [x] **#6 — `rpc_handler.cc val_to_cond`/`val_to_path`** (found by P2): a
  condition/pathlet object without a string `"type"` reached
  `val["type"].asCString()`, whose `JSON_ASSERT` is a live `assert()` →
  **`abort()` on malformed RPC input** (DoS). Fixed: guard with
  `isObject`/`isMember`/`isString`, degrade to `nullptr`, skip unknown pathlets.
- [x] **#7 — `rpc_handler.cc check_compliance`** (P2 follow-up): `std::stoull` on
  the policy key (throws on non-numeric) and `dsts[i][0..2]` accesses
  (`asUInt64`/`asCString` assert on short/ill-typed tuples) **crashed the server
  on malformed input**, and every parsed `cond` array **leaked**. Fixed by
  extracting a validated two-pass `val_to_compliance_rules` (+ free helper).
- [x] **#8 — `net_plumber_utils.cc`** (found by the sanitizer job): `qsort(NULL,
  0, …)` / `memcpy(NULL, …, 0)` on empty lists — NULL to a `nonnull` argument
  (UB, UBSan). Guarded on `size > 0`.

---

## Future considerations — NOT part of the testing plan

Surfaced during analysis; recorded for the author's decision (see TODO item 7):

- **Shrink the `#ifdef` surface.** The abandoned/experimental/legacy flags above
  produce many never-built branches (~74 `#ifdef` sites in `net_plumber.cc`
  alone) that every refactor must reason about but no test can cover. Deleting
  the genuinely-dead ones (`NEW_HS` dead-end, `GENERIC_PS`/`USE_BDD` abandoned,
  `USE_DEPRECATED` legacy) would collapse the surface and make refactoring
  markedly safer — while keeping whatever is wanted for thesis reproducibility.
  This is a code-removal decision, independent of the tests above.
- **The PacketSet/BDD line stays parked.** Reviving the abstraction is gated on
  first solving the BDD masked-rewrite problem; both are low priority. If
  revived, the P0 concrete-packet oracle becomes its validation harness (a BDD
  backend must match the same oracle as `hs`).

---

## Suggested first work item

1. **The two-bug PR** (#1, #2 above): small, high-confidence, and it establishes
   the public-API contract-test style (P1).
2. Then **P0** — the concrete-packet oracle + algebraic laws — as the main
   refactoring net for the header-space engine.
