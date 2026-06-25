# FaVe Testing Strategy

A prioritized plan for raising the test quality and coverage of FaVe's Python
codebase, grounded in a module-by-module analysis and the current coverage
measurements.

## Scope

**This strategy covers `fave/` and `policy_translator/` only.**

`net_plumber/` (the C++ verification backend) is **explicitly out of scope**
here — it is tracked separately under the "Verification-engine-specific" items
in [`TODO.md`](TODO.md) (C++ sanitizer/coverage builds, the header-space
soundness work). The two Python tools are independent (no cross-imports;
`policy_translator/` is type-checked and tested with its own root), so they are
treated together but assessed on their own terms.

Everything below assumes the existing tiered runner (`./test.sh
fast|integration|e2e|smoke|bench|all`) and the `mypy` gate
(`fave/test/typecheck_test.sh`); the strategy extends that foundation rather
than replacing it.

---

## TL;DR

The suite has a solid *skeleton* — a tiered `test.sh`, a `mypy` gate, ~69 %
measured coverage, a good `FakeSocket` client harness, and strong behavioral
tests for the iptables generator path — but three structural problems:

1. **The two largest, most verification-critical modules have ~0 % real
   coverage.** `netplumber/adapter.py` (1123 LOC) and
   `aggregator/aggregator_service.py` (721 LOC) are never imported by the
   `fast`/`integration` tiers; they are touched only by the (currently broken)
   `test_rpc` and by subprocess benchmarks, so coverage does not even see them.
2. **Much existing coverage is symmetric golden-dict round-trips.** A value that
   is *wrong but serializes/deserializes consistently* still passes. The
   snapshots are also brittle (the `raw_line`/`negated` churn already forced
   edits).
3. **Several `__eq__`/`__hash__` methods are themselves buggy**, so some tests
   pass partly by accident (equality that ignores fields, or asserts on type
   mismatch).

The analysis also surfaced **5 confirmed bugs** (two on the verification path).

**Direction:** fix the equality/identity *foundations* first, then attack pure
verification-critical logic through the seams that already exist, and prefer
invariant/behavioral assertions over more snapshots.

---

## Current state — grounded in coverage

Measured via `COVERAGE=1 ./test.sh all` (fast + integration + e2e); ~69 % total.

| Area | Coverage | Reality |
|---|---|---|
| `util/` pure helpers | 73–100 % | Best-tested; gaps in `packet_util` denormalize/predicates, `ip6np_util` (0 %), `aggregator_utils` (0 %) |
| `rule/rule_model.py` | 80 % | Round-trips tested; **`Match.intersect`/`RuleField.intersect` untested & broken** |
| `devices/` | 28–41 % | Mostly golden-dict snapshots; `add_rules`/`__sub__`/state/relay logic untested; `probe`/`generator` 0 direct |
| `netplumber/vector,mapping` | 71 / 79 % | `intersect_vectors` (the math core) has **0 tests** |
| `netplumber/jsonrpc.py` | 42 % | `FakeSocket` tests are good but cover ~6 of ~25 encoders |
| **`netplumber/adapter.py`** | **~0 % (not imported)** | Bit-packing, negation expansion, model→RPC translation — all untested |
| **`aggregator/aggregator_service.py`** | **~0 % (not imported)** | Event dispatch / state diff — untested; a seam exists (`abstract_engine`) |
| `iptables/parser.py` | 82 % | Good positive tests; no negative/malformed tests |
| **`iptables/generator.py`** | **0 %** | Most complex module in the codebase; totally untested; **testable without pybison** |
| `policy_translator/policy.py` | 65 % | `to_iptables` well-tested; 5 of 6 FPL operators, all error paths, other renderers untested |
| `policy_translator/policy_builder.py` | 78 % | One happy-path FPL string; operator semantics & malformed inputs untested |

---

## Strategy — five principles

1. **Prioritize by risk × reachability-without-backend.** The highest-value
   targets are *pure, verification-critical functions that need no native
   stack* — bit-vector intersection, field encoding, rule-index packing, match
   intersection. These belong in the `fast` tier and currently are not there.
2. **Exploit the seams that already exist** instead of requiring a live backend:
   - the `FakeSocket` (`test_jsonrpc_client.py`) → unlocks all of `jsonrpc` and
     the pure `adapter` helpers (construct the adapter with fake `socks`);
   - `aggregator/abstract_engine.py` → a `MockEngine` recording calls unlocks
     `aggregator_service._sync_diff`/`_handler` without sockets or a backend;
   - hand-built `Tree` ASTs → unlock `iptables/generator.generate()` **without
     pybison** (generation is decoupled from parsing);
   - `socket.socketpair()` → unlocks `aggregator_utils` framing with no mocks.
3. **Assert behavior and invariants, not snapshots.** Augment/replace giant
   `to_json` golden dicts with focused content assertions and *invariants* that
   catch whole bug classes: "every wiring endpoint ∈ `ports`" (catches the ALG
   typo), "priority bands never overlap", "denormalize ∘ normalize = identity".
4. **Fix the test *foundations* before scaling coverage.** The buggy
   `__eq__`/`__hash__` methods must be fixed first, or new equality-based tests
   inherit the blind spots. This is a precondition, not a parallel task.
5. **Characterize → fix → flip** for the confirmed bugs. Write a test pinning
   current (wrong) behavior, fix the code, flip the assertion — so the fix is
   permanently guarded. These are correctness defects in a verification tool,
   not mere coverage gaps.

---

## Prioritized roadmap

Tiers in **bold** indicate where each slice runs.

### P0 — Pure verification core · **fast tier**, no deps, highest risk
New `test_vector.py`, expanded `test_rules.py`, new `test_adapter_pure.py`:
- `vector.intersect_vectors` truth table incl. empty/`None` — *the math core, 0 tests*.
- `Match.intersect` / `RuleField.intersect` incl. the `None` all-ignore case — **broken, live via `generator.py:472`** (see bug #1).
- `adapter._calc_rule_index` / `_calc_port` bit-packing + the three asserts (construct adapter with `FakeSocket`).
- `packet_util` denormalize + `portrange_to_prefix_list` boundaries (0 / 65535) + predicates; `ip6np_util` `_normalize_*` + dispatch exception paths.

### P1 — Device models via behavioral/invariant tests · **fast tier**
- `AbstractFirewallModel.add_rules` priority-band expansion + idx-overflow collision + input-mutation; the broken `remove_rule` (bug #5).
- `router._build_cidr` (netmask→prefix; the unsound `round(log2)`), `parse_cisco_acls`/`parse_cisco_interfaces` (token-count dispatch, NAT, malformed) — feed text, assert *content*, not round-trip.
- `snapshot._swap_field` (all 4 directions + fall-through) and `add_state` reverse-flow.
- A generic **wiring-invariant test** across all device models (catches the ALG `relays_out` bug, #2); `probe`/`generator` JSON round-trips.

### P2 — The bridge via seams · **fast tier**
- Finish `jsonrpc` encoders with `FakeSocket`: `add_source(s_bulk)` payload-shape branch, `add_rules_batch`, `add_links_bulk` sharding / `-1` broadcast, slices, dumps.
- `adapter._expand_negations` / `_build_headerspace` field placement.
- Aggregator: a `MockEngine(AbstractVerificationEngine)` to drive `_sync_diff`/`_handler` + pure `_parse_servers`; pin the `_dump_aggregator` `key>>12` ↔ adapter `<<12` coupling. (Needs a small seam to skip the `Reporter` thread in `__init__`.)
- `aggregator_utils` framing round-trip via `socketpair`.

### P3 — The iptables generator · **fast tier** (device deps, but no pybison)
`generator.generate()` on hand-built ASTs: a simple ruleset (`interweaving=False`)
asserting table contents, then a conntrack ruleset (`interweaving=True`) locking
the state-shell interweaving algorithm. Highest single risk-reduction in the
codebase; also the natural home for a regression test of bug #1.

### P4 — PolicyTranslator · **fast tier**
- All 6 FPL operators' effect on `policy.policies` (assert the dict directly, **not** via `==`, until the `__eq__` bugs are fixed).
- `to_iptables` edges (IPv6-only roles, list-valued addresses → cartesian rule expansion, `provider` sport-vs-dport).
- Malformed-FPL / exception paths (`InvalidSyntaxException`, `NameTakenException`, bad `add_attribute`).
- Promote the gated `fpl_grammar` inline `use_tests` cases into real pytest cases (valid **and** invalid inputs).

### Native / integration & e2e tier
- Fix `test_rpc` (single-socket → list) — and the identical defect in `print_np.py:104`.
- Add negative parser tests (malformed lines, the silent bad-char lexer path, unknown tokens).
- Make benchmark / `example.sh` sub-step failures **fail loudly** (ties into TODO 1p/1n).

---

## Foundational fixes that gate the roadmap

- **Fix `__eq__`/`__hash__`:** return `NotImplemented`/`False` instead of
  asserting on type mismatch (`RuleField`/`Rule`/`AbstractDeviceModel`); fix
  zip-over-dict in `Tree.__eq__`, `Role`/`Superrole.__eq__`, and `Policy.__eq__`
  ignoring `policies`; reconcile `Rule.__hash__` ↔ `__eq__`. **Do this before
  P1/P4 lean on equality.**
- **Coverage visibility:** adapter/aggregator read 0 % only because they are
  never imported — once P0–P2 import them, set a coverage **ratchet** (fail if
  total drops) rather than a hard threshold initially.

---

## Confirmed bugs found during analysis

Each becomes a *characterize → fix → flip* regression test. All five were
verified by reading the cited lines.

| # | Location | Bug | Severity |
|---|---|---|---|
| 1 | `rule/rule_model.py:354-355` | `Match.intersect` sorts `self` twice (`match2 = sorted(self, …)` should be `sorted(other, …)`); ignores `other`. **Live via `iptables/generator.py:472`** (conntrack state shells). | **High — corrupts stateful verification** |
| 2 | `devices/application_layer_gateway.py:160` | wires `relays_out` but the port is defined as `relay_out` (`:103`) → ALG egress wired to a nonexistent port. | **High — breaks ALG connectivity** |
| 3 | `util/tree_util.py:143` | `Tree.__eq__` uses `zip(self, obj)` → a prefix compares equal to a longer tree. | Medium (weakens parser tests) |
| 4 | `util/match_util.py:43` | `'upd_src'` typo (should be `udp_src`); **enshrined by `test/test_utils.py:170`**. | Medium |
| 5 | `devices/abstract_firewall.py:194` | `remove_rule` reads `self.tables[self.node+'_routing']` (underscore, not `.routing`) → KeyError path. | Medium (flagged; confirm) |

Lower-severity, flagged for follow-up (not yet line-verified end-to-end):
- `util/bench_utils.py:134` — dead `-s`/`interweave` append placed outside the `ip6tables.main(...)` call, so `interweave` is silently ignored.
- `devices/router.py:456` — `_build_cidr` derives prefix length via `round(log2(...))`, unsound for non-power-of-two / non-contiguous masks.
- `devices/router.py` `persist` — `CAPACITY = 16` gives only 16 ACL-rule slots per VLAN before `aid` collides across VLANs.
- `util/ip6np_util.py` — dead `else: raise` after `return` in `_normalize_rt_type` / `_normalize_ah_spi`.

---

## Suggested first work item

**Foundation fixes + P0** as a single PR: it is pure `fast`-tier, needs no
native stack, unlocks the verification core, and pins bug #1. Then P1–P3 in
order, with P4 (PolicyTranslator) runnable in parallel since it is an
independent tool.
