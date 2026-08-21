# FaVe modifications to ad6

`ad6` is the author's own 2014 SECRYPT'15 proof-of-concept (SAT/QBF model checking for
IPv6 firewalls/networks) — first-party code, not a vendored fork of an external project.
It is being revived and integrated as a fourth verification family alongside NetPlumber
(HSA), APKeep(BDD), and APKeep(NDD); see `../AD6_PLAN.md`. As with `apkeep/FAVE_CHANGES.md`
and `ndd/FAVE_CHANGES.md`, changes are stated prominently here. Kinds:

- **[NEW]** — a capability ad6 did not have;
- **[FIX]** — a correctness/environment bug surfaced by reviving 2014 code on a modern
  toolchain (Python 3.12, current Ubuntu);
- **[INFRA]** — build, test, and tooling that do not change library behaviour.

All items below are reachable via `git log -- ad6/`.

---

## 1. `test/` package shadowed by Python's own stdlib `test` package  **[FIX]**

`test/` had no `__init__.py`, so on Python 3 (PEP 420 namespace packages) the import
`from test.satsuite import SATSuite` in `test/test.py` resolved to CPython's own
`/usr/lib/.../test` package instead of ad6's local `test/` directory
(`ModuleNotFoundError: No module named 'test.satsuite'; 'test' is not a package`).
Added `test/__init__.py` to make ad6's `test/` an explicit regular package, which takes
precedence. No behaviour change; this only affects how the test suite is discovered.
`ad6/.gitignore` also blanket-ignored every `__init__.py` in the tree (an apparent
leftover from an Eclipse/PyDev-generated template, alongside `.project`/`.pydevproject`)
— removed that line so the new file, and any future package markers, actually get
tracked.

## 2. Test-fixture XML used a firewall-key convention `_ConnectOutputs` cannot resolve  **[FIX]**

`Instantiator`/`KripkeUtils._ConnectOutputs` wires an `accept`-tagged rule node to its
egress interface by string-prefix match: it derives the firewall's key from the rule key
(stripping the trailing `_<table>_r<n>` segments) and requires an interface key that
**starts with** that exact firewall key. Real usage (`main.py` + `GenUtils.firewall`,
exercised by `bench/tum`, `bench/up`) always sets a firewall's `key` to exactly the
`--rulesets` name (e.g. `tum_fw`), and the network XML names the node to match — so the
firewall key and the interface's key prefix coincide by construction.

Every hand-authored fixture under `test/core/*.xml`, `test/integration/testIntegration.xml`,
and `test/system/testSystem.xml` instead gave each firewall a key one segment **longer**
than its node (e.g. node `n0`, firewall key `net0_n0_fw0`, but interface key
`net0_n0_eth0`) — a convention the production path never produces and that
`_ConnectOutputs`'s prefix match cannot satisfy. The result: the `accept` node's forward
transition to its egress interface was silently never created, breaking `testKripke`
(assertion failure) and, one layer up, every reachability/cycle/shadow/cross query built
on top of these fixtures (only surfaced once the missing `minisat`/`clasp` binaries — see
item 3 — stopped masking it with an earlier `FileNotFoundError`).

Fixed by normalising every affected fixture's firewall key (and all rule keys/`target=`/
`keyref=` references derived from it) to drop the redundant `_fw0` suffix, matching the
convention real bench configs already use — e.g. `net0_n0_fw0_output_r0` →
`net0_n0_output_r0`. Applied mechanically (per-file key mapping, longest-match-first
substitution) to keep behaviour otherwise identical; corresponding hardcoded expectations
in `test/core/kripketest.py`, `test/core/instantiatortest.py`, and
`test/system/systemtest.py` updated the same way. `src/core/kripke.py` itself is
unchanged — this was purely a test-fixture bug, not a production-path bug (confirmed by
tracing `GenUtils.firewall`/`main.py`'s real config-generation path, which never produces
the broken convention).

**Result:** `make test` is green (46/46), previously erroring/failing across
`kripketest`, `instantiatortest`, `integrationtest`, and `systemtest`.

## 3. Pin ad6's runtime deps in the shared `Dockerfile`  **[INFRA]**

`ad6/` had no dependency manifest. Added to `../Dockerfile`, alongside NP/APKeep/NDD:
apt `minisat` (1:2.2.1-8build1) + `clasp` (3.3.5-4.2build1) — the two solver adapters
`main.py --solver` can shell out to; pip `lxml==6.1.2` (Kripke/SAT-instance XML),
`yappi==1.7.6` (`main.py --profile`), `pycosat==0.6.6` (the default in-process solver,
needs `python3-dev`, already present for the NetPlumber/APKeep bindings). No source
changes.

## 4. wl_tum differential test vs NetPlumber  **[NEW]**

`test/differential/tumdifftest.py` + `test/differentialsuite.py` (wired into
`test/test.py`, AD6_PLAN.md §4.3): confirms ad6 agrees with the NetPlumber oracle on
FaVe's wl_tum benchmark. Confirmed first that no translation is needed —
`bench/tum/tum-ruleset` is byte-identical to FaVe's own default (ipv4) wl_tum ruleset
(`fave/bench/wl_tum/rulesets/tum-ruleset`) — and that neither side's model needs the
ruleset's VLAN sub-interfaces represented in topology: FaVe's own wl_tum model injects
directly into the FORWARD chain (`source.tum -> fw.tum.forward_filter_in`) and probes the
FORWARD chain's ACCEPT exit (`fw.tum.forward_filter_accept -> probe.tum`), bypassing
interface admission entirely; the exact same shape holds in ad6 (`tum_fw_forward_r0`, the
first FORWARD rule, as the sole init; reachability of the synthesized `tum_fw_accept_r0`).
**Result: ad6 says reachable=True, matching NetPlumber exactly** (oracle obtained via
`fave/bench/apkeep_tum_diff.py --emit netplumber`, see the test's docstring for exact
repro). `bench/tum/tum.xml`'s bundled topology is unused by this query on either side —
not a gap after all (§4.1's original note was premature; corrected here). Runtime ~30s
(dominated by CNF instantiation over the 3794-rule model), so this lives in its own suite
rather than being folded into a faster one.

## 5. Investigation: ad6's frontend/backend seam, and rule-level forwarding  **[NEW finding, no source change]**

Prompted by a correction from the project owner (AD6_PLAN.md §4.4): integrating ad6 with
FaVe does not require ad6 to parse FaVe's native rule formats (Cisco IOS ACLs, IPv4 FIBs)
itself — FaVe already parses those and builds a neutral model; only a translator from
that model into ad6's own IR is needed. Investigated how separable that IR already is:

- `src/xml/genutils.py` (`GenUtils`) is a generic Config-tree element-factory module
  (`firewall`/`table`/`rule`/`action`/`address`/`port`/`proto`/`state`/`vlan`/`interface`/
  `node`/`network`/`route`/...), used by `src/parser/iptables.py`'s `IP6TablesParser`
  purely as a set of builders *after* it has finished parsing ip6tables CLI syntax.
  `KripkeUtils.ConvertToKripke` and everything downstream (`Instantiator`, CNF, solving)
  consume only the resulting XML tree via XPath and have no dependency on iptables syntax
  at all. So a new frontend — a FaVe-model-to-`GenUtils` translator, skipping the
  iptables-text step — needs no changes inside `kripke.py`/`instantiator.py`.
- Verified experimentally (a standalone synthetic test, not asserted from reading code)
  that `action type="jump" target="<key>"` can target an arbitrary declared node,
  including a **specific egress interface** directly — not only the shared "accept" node
  that `KripkeUtils._ConnectOutputs` floods to every one of a firewall's declared
  out-interfaces (the right model for a stateless filter chain, wrong for a router
  choosing a specific egress port per route). A 2-rule/2-interface model, each rule
  jumping straight to a different interface based on a dst-address match, correctly
  discriminated under SAT: forcing the destination to each rule's own match address made
  exactly one interface reachable and the other UNSAT. This gives real per-rule
  forwarding/routing semantics with **zero backend changes** — the missing piece for
  router-style devices (wl_ifi's central router, Stanford/i2's FIB) is only in how a new
  frontend chooses jump targets, not in `kripke.py`'s transition semantics.

No ad6 source changed for this item; it's a design investigation informing AD6_PLAN.md's
integration approach (§4.4).

## 6. FaVe-model translator + wl_ifi exact match  **[NEW]**

`src/parser/favemodel.py` + `fave_bridge.py`: the actual FaVe->ad6 translator the §4.4
investigation (item 5) called for, plus a CLI bridge (`fave/ad6/adapter.py`, on the FaVe
side, is the `AbstractVerificationEngine` that captures the model and drives this as a
subprocess -- ad6 never runs in-process inside FaVe, see that file's docstring). Builds a
`GenUtils`-shaped Config tree directly from FaVe's neutral per-device rule model (never
touching `IP6TablesParser`/Cisco-ACL text), covering: dst-IP forwarding via direct
interface jumps (§4.4's verified primitive), and ingress/egress ACL admission via a
per-port group of unconditional-jump rules (permit -> the shared forwarding stage; deny ->
a shared drop sink) — VLAN is used only to trace which port an ACL group belongs to, never
as a match field.

**Result: exact match to wl_ifi's `reachable.json` (54/54, 0 missing, 0 extra)** —
`fave/test/test_ad6_wl_ifi.py`, mirroring `test_apkeep_wl_ifi.py`. ~2.6s end to end (17
devices, 17 generators/probes, 289 queries).

Getting there surfaced real, worth-recording gotchas (all fixed in `favemodel.py`/
`fave_bridge.py`, none require touching `kripke.py`/`instantiator.py`):

- **A `/0` CIDR (`0.0.0.0/0`, FaVe's explicit "match any") silently breaks.**
  `XMLUtils.ConvertCIDRToVariables` truncates a CIDR's bit-vector to `Count*2` bits, which
  is **zero** for a `/0` prefix — producing an **empty** `<conjunction/>` as the rule's
  Gamma instead of a trivially-true one, which makes every rule (and everything reachable
  only through it) unconditionally unsatisfiable. Fixed by treating a match-all CIDR as
  "no condition" (omit the `<ip>` element) rather than asserting it — semantically
  identical, sidesteps the zero-bit corner case. `favemodel._is_constrained`.
- **`KripkeUtils._ConnectOutputs`'s `_EnhanceInterfaceRules` machinery is a trap for a
  translator that bypasses it.** An `<interface direction="in">` match condition gets
  rewritten to `constant(False)` unless something wires a backward transition into that
  interface's `_in` node — which this translator deliberately never does (§4.4's design:
  per-port isolation is structural, via separate query entry points, not via interface
  matching). Adding an `<interface>` condition anyway silently makes the rule permanently
  unreachable; the fix is to just not add it.
- **A device's own forwarding-table start is NOT a free INIT entry point once the topology
  is wired.** `KripkeUtils._ConvertNodesToImplications`'s "was this node entered" check
  only exempts a node with **zero** backward transitions (`Kripke.IterBTransitions`
  raising `KeyError`) — marking a node `INIT` does not override that if it also has a real
  predecessor (e.g. a neighbouring device's egress interface, once `wire_edges` connects
  the topology). The fix: give every FaVe generator its **own dedicated** 1-rule firewall
  that nothing else ever points into (`gen_entry_key`), and use *that* as every query's
  Source — never a device's own internal entry point directly. Found by tracing an
  admin.ifi->internal.ifi query that stayed UNSAT even though every individual edge along
  the path looked correct in isolation.
- **`KripkeUtils._CreateInitConstraints`'s chained-XOR has a real off-by-one for larger N**
  (wl_ifi's 17 generators). It builds the "exactly one of these fired" constraint via
  `for i in range(2, Length-3): ... elif i == Length-3: <close the chain>` — but
  `range`'s stop bound is exclusive, so `i == Length-3` is never reached, and the last few
  generators end up completely unconstrained (free to fire simultaneously with the one a
  query actually asked about). Surfaced as an over-approximation: `admin.ifi` incorrectly
  "reached" the isolated `cam.ifi`/`hpc_ic.ifi`/etc. subnets, because a solver assignment
  fired `source.cam.ifi`'s own generator to satisfy the destination side for free,
  unconstrained by the (broken) XOR. **Not fixed in ad6 core** — worked around per-query
  in `fave_bridge.py` (`_exclusivity_conjuncts`: explicitly assert every *other* generator's
  edge is false), which is correct regardless of whether the XOR bug is ever fixed
  upstream, and is the more principled fix anyway (a query should not depend on an
  incidental global invariant to mean what it says).

None of these needed changes inside `kripke.py`/`instantiator.py` — confirming §4.4's
finding that the existing backend is sufficient for a FaVe-model translator, modulo two
real (if obscure) bugs worth knowing about (the `/0` CIDR truncation and the init-XOR
off-by-one) that any future ad6 frontend will hit again if it isn't aware of them.

## 7. `/0`-CIDR bug fixed in core (was item 6's workaround)  **[FIX]**

Claas asked for the two bugs above to be fixed properly (test-first), not just worked
around — this item is the `/0` one (the easier of the two); the init-XOR off-by-one is
item 8.

**Fix:** `XMLUtils.ConvertCIDRToVariables` now returns `XMLUtils.constant()` immediately
when the parsed prefix length is 0, instead of building a `<conjunction>` from a
truncated-to-zero-length bit-vector (which produced a structurally valid but semantically
wrong empty conjunction — see item 6 for the original diagnosis).

**Tests added first (both failed against the pre-fix code, confirmed before patching):**
- `ad6/test/xml/xmlutilstest.py:testCIDRMatchAll` — unit test: `ConvertCIDRToVariables`
  on a `/0` CIDR (both IPv4 `0.0.0.0/0` and IPv6 `::/0`) must return `constant()`, not an
  empty conjunction.
- `ad6/test/core/instantiatortest.py:testMatchAllReachable` — regression at the solve
  level, and the sharper of the two: a rule matching `dst=0.0.0.0/0` must itself be
  reachable, **and** a second, otherwise-unrelated rule matching `dst=10.0.0.0/8` (never
  mentioning `0.0.0.0/0`) must ALSO stay reachable — this is the case that actually
  exercises `_ShortenPrefixes`'s prefix-sharing cross-contamination (item 6's real-world
  symptom); a test with only the `/0` rule present is not enough to catch it, since
  `_ShortenPrefixes` has nothing to splice a reference into when there is only one
  same-direction CIDR key. (Building this regression surfaced an unrelated, ad6-*working-
  as-designed* gotcha in the test itself: `KripkeUtils._HandleRule` gives same-table
  sibling rules an automatic fallthrough edge regardless of their own action, so the two
  independent rule/target pairs needed their own `<table>` each — putting them in one
  table added a spurious edge that briefly looked like a second manifestation of the bug.)

Why this one was safe to fix immediately, ahead of item 8's harder bug: contained,
single-function change, with a clear correct semantics (an empty AND is vacuously true)
and no plausible existing consumer relying on the old behaviour (`IP6TablesParser` never
emits an explicit `/0` — see item 6), so the risk/verification cost is low. Full
`make test` (48 tests) and the `fave/test/test_ad6_wl_ifi.py` differential (54/54 exact
match) both stay green after the change.

## 8. Init mutual-exclusion (`_CreateInitConstraints`) fixed in core — worse than first
diagnosed  **[FIX]**

The harder of the two bugs Claas asked to be fixed properly. Item 6 first characterised
this as "the last few of >~16 marked-INIT nodes are unconstrained" (matching wl_ifi's
17-generator symptom). **That undersold it.** Before writing the property test below, an
exploratory brute-force sweep (every pair, N=2..20) against the pre-fix code showed:

| N (marked-INIT nodes) | broken pairs |
|---|---|
| 2, 3 | none (handled by a separate, always-correct branch) |
| 4 | **all 6 pairs** — `range(2, Length-3)` is empty, so *zero* constraints were built at all |
| 6 | all pairs except `(T[0],T[1])` |
| 17 (wl_ifi) | all pairs except `(T[0],T[1])` |

So the bug was never "just the tail" — for every `Length>3`, only the very first pair was
ever actually constrained; everything else, including adjacent pairs like `(T[2],T[3])`,
could fire simultaneously. The `range(2, Length-3)` tail-off-by-one from item 6 is real,
but it was a symptom of the same construction being broken throughout, not the whole
story.

**Tests added first** (`ad6/test/core/initconstraintstest.py`, a new
`InitConstraintsSuite`): a property test — build N independent marked-INIT nodes, each
with a single own transition to its own dedicated target (the minimal shape
`_CreateInitConstraints` actually consumes), and assert **at most one** of the N
transitions can be simultaneously satisfiable (every individual one alone must be SAT;
every pair together must be UNSAT; "none fire" must stay SAT — this is an at-most-one
encoding, not exactly-one, matching the pre-existing N∈{2,3} behaviour). Run at N=2, 3, 4,
6, and 17 (wl_ifi's exact count); all three of N=4/6/17 fail against the pre-fix code,
confirming the table above.

**Fix:** replaced the entire `Length > 3` branch (the linear chain of auxiliary `xor_i`
variables) with exactly what the `Length in [2,3]` branch already did correctly — call
`_xor` directly on *all* `N` transition literals at once, an `O(N^2)` pairwise "not both"
encoding. The two branches are now unified into one `Length > 1` case. Verified this
generalises, not just patches N=17: the property test passes N=2 through 40 (property-based
sweep, not committed — too slow to run routinely), and a spot-check at **N=137** (FaVe's
wl_up scale) builds 18,632 clauses and CNF-converts in ~1.6s, with sampled pairs (including
adjacent, wraparound, and far-apart) all correctly mutually exclusive.

Why replace rather than repair the chain: the chain's own indexing (`'xor_'+str(i-2)`
apparently intended to carry a running "at least one seen so far" bit forward between
iterations) does not actually track that — `_xor` only ever asserts pairwise "not both",
never "this variable becomes true when an earlier one does" — so even a corrected loop
bound would not obviously produce a correct chain without a deeper redesign. The
`O(N^2)` pairwise form is the *already-correct, already-in-use* alternative for small N (2
and 3), and FaVe's benchmarks top out at N≈137 (wl_up) — 18.6k trivial 2-literal clauses,
negligible next to the models these tools already build. Revisit only if profiling ever
shows this is a real bottleneck at a much larger N.

`fave/ad6/adapter.py`'s companion workaround (`fave_bridge.py`'s `_exclusivity_conjuncts`,
asserting every other generator's edge false per query) is now **removed**, not just
redundant: `fave/test/test_ad6_wl_ifi.py` was re-run with it deleted, confirming the core
fix alone reproduces the exact 54/54 match — the workaround would otherwise mask a future
regression of this exact bug rather than let the differential test catch it.

## 9. Stateful `<->>` query-forcing mechanism built (AD6_PLAN.md §4.2); two non-ad6
wiring bugs found and fixed along the way; wl_ifi's real stateful checks characterized
but not yet oracle-confirmed  **[NEW]**

wl_up needs the stateful `<->>` 3-check semantics (AD6_PLAN.md §1.2/§1.4); wl_ifi's own
`cchecks.json` has 54 stateful checks too. Built the mechanism, tests first where the
logic was genuinely new (not just plumbing):

- `fave/ad6/adapter.py:_capture_acl` now captures the `related` match field (mirrors
  `apkeep/adapter.py:_RELATED`; `"0"`=NEW, `"1"`=ESTABLISHED) as a 5th tuple slot on every
  ACL entry.
- `ad6/src/parser/favemodel.py:_acl_rule` emits `GenUtils.state('ESTABLISHED'|'NEW')` when
  `related` is present on the captured rule.
- `ad6/fave_bridge.py:_state_literals` forces the matching state onto a query instance for
  a `related` condition. **Verified empirically before relying on it**
  (`ad6/test/core/instantiatortest.py:testStateLiteralForcingIsMutuallyExclusive`, a
  regression test added first): the literals MUST come from
  `XMLUtils.ConvertStateToVariables(value)`'s conjunction, flattened and appended as
  individual top-level clauses — not the raw `<state>value</state>` element run through
  `ConvertToVariables` (produces one variable named e.g. `"state_NEW"` that only gets
  canonicalised into the shared bit-vector space by `Instantiator._HandleOthers`'s
  build-time pass over variables the base model *already contains*; a value that never
  appears in any real rule would stay an unconnected, unconstrained atom — asserting it
  would be a silent no-op, not a real constraint), and not the whole `<conjunction>`
  appended as one nested child either (also a silent no-op / can even manufacture a
  spurious UNSAT — `instance[0]` is the base model's already-CNF'd clause list from
  `InstantiateBase`, so each top-level child must be its own flat literal). Confirmed via
  a synthetic ESTABLISHED-only rule: forcing ESTABLISHED still reaches it, forcing NEW or
  RELATED does not — the mutual exclusion the "state_i=b" bit-vector encoding is supposed
  to provide across different values genuinely holds, once the literals are wired in
  correctly.

**Two more bugs found while wiring this up, both in FaVe/adapter glue rather than ad6
core, both fixed:**

1. `check_compliance`'s real dispatch path (`InProcessFaVe` → `aggregator_service.py`'s
   `_handler`) converts every `cond` entry via `RuleField.from_json` before calling the
   engine, so `Ad6Adapter.check_compliance` actually receives a list of `RuleField`
   *objects*, not the plain strings or dicts a cursory reading of the existing (`cond=[]`
   always) tests would suggest. These aren't JSON-serialisable as-is for the
   subprocess-bridge payload — `json.dump` would (and, before the fix, did) crash inside
   the aggregator's own worker thread. Added `Ad6Adapter._cond_to_json` (`.to_json()` if
   present, else pass through) before building the payload.
2. `bench/reach_csv_to_checks.py`'s `_generate_cchecks` stores each check as
   `(probe, valid, cond)`, where `valid` (True = no `"!"` prefix = "must reach") is the
   OPPOSITE polarity of the `(source, negated, cond)` convention `check_compliance`
   actually expects everywhere else (`must_reach = not negated`). Loading `cchecks.json`'s
   tuples in place without flipping this bit inverted nearly every one of wl_ifi's 299
   checks into a reported violation — caught immediately (the violation count was
   obviously wrong, not subtly wrong) and fixed by flipping to `not valid` when building
   the `rules` dict for `check_compliance`.

**End-to-end exercise on wl_ifi's real compliance policy**
(`fave/test/test_ad6_wl_ifi_stateful.py`, loading `bench/wl_ifi/cchecks.json` — 299
entries, 54 stateful, matching AD6_PLAN.md §1.2's table exactly — directly into
`check_compliance`, not the synthetic all-pairs matrix `test_ad6_wl_ifi.py` uses):

- All 245 plain (`cond=[]`) checks pass — consistent with `test_ad6_wl_ifi.py`'s exact
  match against `reachable.json`.
- Of the 54 stateful checks (27 `<->>` pairs × {related:1, related:0}): all 27 related:1
  ("must reach with ESTABLISHED") checks pass; **all 27 related:0 ("must NOT reach with
  NEW") checks fail** (ad6 reports reachable).
- Traced one failing pair (`source.internal.ifi` → `probe.admin.ifi`) down to the actual
  captured ACL entry: `acl_out['464']` has
  `[7424, True, '10.0.12.0/23', '10.0.14.0/23', None]` — a **state-blind** permit
  (`related=None`). This is not a translation gap: wl_ifi's ACLs are parsed as-is from
  real Cisco IOS text (`bench/wl_ifi/acls.txt`), which never carries a `related`/
  `established` qualifier on this rule at all, so there is nothing for the adapter to
  carry through. Forcing ESTABLISHED vs NEW against a state-blind rule necessarily yields
  the *same* reachability answer; related:1 happens to want that answer, related:0
  doesn't — hence the clean, systematic 27-pass/27-fail split (not a handful of scattered
  failures, which would look more like a genuine bug).
- **`fave/bench/wl_up/rulesets/` (gitignored but present locally) DOES use
  `ctstate ESTABLISHED` for real** (`grep -rho "ctstate [A-Za-z,]*"` across every
  department ruleset), unlike wl_ifi's state-blind admin rule — so wl_up's own stateful
  checks may behave differently (more faithfully) than wl_ifi's did here. Also confirmed:
  no ruleset anywhere in this repo (ad6's own `bench/`, or FaVe's `wl_up`/`wl_tum`) ever
  uses a compound `ctstate A,B` value — so `XMLUtils.ConvertStateToVariables`'s multi-value
  case (which ANDs all requested bits together instead of OR-ing them — confirmed via
  `ConvertStateToVariables('ESTABLISHED,RELATED')` producing a vector requiring
  state_1=1 AND state_2=1 simultaneously, unsatisfiable for a real single-valued state) is
  a real, latent bug, but not on the critical path for any current benchmark. Logged as a
  §8 architecture-review item rather than fixed now (deferred scope, not required for
  wl_up/wl_ifi's actual rulesets).

**OPEN QUESTION, not resolved here:** is the 27-violation split a genuine, pre-existing
property of wl_ifi's real ACLs (reach.txt's `<->>` intent was never actually implemented
in acls.txt for these specific pairs, so a live NetPlumber run would report the *same* 27
violations against the *same* state-blind rule), or does NetPlumber's own
`check_compliance` resolve a `related` condition through some other mechanism this
adapter hasn't accounted for? `fave/test/test_ad6_wl_ifi_stateful.py` currently asserts
this as a **characterization** (pins the traced, understood 27/27 split down so a future
change is caught as a diff), not a differential — needs either a live NetPlumber
comparison or the benchmark owner's read on wl_ifi's real ACLs to resolve. wl_up next
(§4.2/§5.1), where the real `ctstate ESTABLISHED` rules may give a cleaner signal.

## 10. wl_up translator built via IP6TablesParser reuse, not a new hand-rolled frontend;
three bugs found and fixed (adapter-side IPv4/IPv6 gaps + a version literal), one logged
and worked around (CanonizeIP's trailing-"::" bug)  **[NEW]**

wl_up (AD6_PLAN.md §5.1) needed the stateful instantiator (§4.2, already built) applied to
a NEW translator: its 136 rule-bearing devices are FaVe `packet_filter`/`host` models
(`devices/packet_filter.py`), not wl_ifi's Cisco-ACL `router` -- different table naming
(`.input_filter`/`.output_filter`/`.forward_filter`/`.pre_routing`/`.routing` vs
`.acl_in`/`.acl_out`) and, unlike wl_ifi, IPv6 throughout.

**Key finding that avoided a much bigger rewrite:** each device's real ruleset
(`bench/wl_up/rulesets/*-ruleset`) is literal `ip6tables` command text, byte-identical to
ad6's own bundled `ad6/bench/up/*-ruleset` (already established, §3.2). So instead of
hand-translating FaVe's already-parsed Match/Action objects into GenUtils calls one field
at a time (reimplementing proto/port/state/icmp/tcp-flags/rt-header semantics FaVe's own
parser already handled), `favemodel.py:_build_ruleset_firewall` feeds each device's raw
text straight into ad6's own `IP6TablesParser` (already proven at scale on wl_tum's 3795
rules). Only two things are genuinely new: dst-LPM ROUTING (`.routing`'s `out_port` MATCH
field -- ip6tables text itself has no routing concept, that's FaVe's own derived FIB;
`fave/ad6/adapter.py:_translate_routing_rule` + `favemodel.py:_routing_table`, same
"specific route sorts before the dst=None default" discipline as wl_ifi's router
forwarding) and the to-self/in-transit DISPATCH a transit device (pgf) needs
(`favemodel.py:_dispatch_table`, `_is_transit` -- data-driven off whether a device has
any dst-specific route at all, not physical-port counting).

**Design snag, resolved:** `IP6TablesParser` resolves every chain's `-j ACCEPT` to ONE
shared `<fwkey>_accept_r0` sink regardless of chain. Correct for the accept/drop decision
itself; wrong for what happens after -- INPUT-accept means "deliver locally", OUTPUT/
FORWARD-accept means "continue to this device's own routing". Fixed by XPath-rewriting
OUTPUT's/FORWARD's own accept-jump targets (scoped by `<table name="...">`) to the
device's routing-table entry, leaving INPUT's alone.

**Mechanism insight, not a bug, that cost real debugging time before it was understood:**
`KripkeUtils.ConvertToKripke` unconditionally calls `_RedirectInputs`, which rewrites
every accept-jump reachable from a chain literally named "input" away from the shared
sink onto a dedicated `<input_entry_key>_accept` node. Found by querying the shared sink
directly for a trivially-satisfiable single-rule INPUT chain and getting UNSAT; traced via
`Kripke.IterFTransitions`/`IterBTransitions` on the built Kripke structure (not guessed)
to this redirect. `favemodel.py:query_destination_key` now targets
`<fwkey>_input_r0_accept` for a wl_up probe attachment, not the shared sink.

**Three real bugs, in the order they were found (each pinned down by tracing a specific
`InstantiateEndToEnd` query down a known-good topology chain node by node until the exact
break point was isolated -- not guessed):**

1. `fave/ad6/adapter.py`'s dst/src field matching (`_translate_fwd_rule`,
   `_translate_routing_rule`'s sibling check, `add_generator`) checked only
   `packet.ipv4.destination`/`packet.ipv4.source`. wl_up is pure IPv6
   (`packet.ipv6.*`) -- silently left `dst`/`src` as `None` rather than erroring, which
   for a switch's own forwarding rule meant "flood unconditionally" instead of "jump only
   for this specific destination", corrupting every path through it. Added
   `_DSTS = (_DST, _DST6)` / `_SRCS = (_SRC, _SRC6)` tuples, checked with `in` everywhere
   a single IPv4 name was compared before.

2. `_build_device_table`'s dst-address builder (`ad6/src/parser/favemodel.py`) hardcoded
   `version='4'` -- fine for wl_ifi's router (always IPv4), but this SAME fwd_rules
   mechanism is also what wl_up's own switches' `.1` tables go through (confirmed:
   switches get real per-dst forwarding tables via FaVe's own model, exactly like
   wl_ifi's, no special-casing needed once bug 1 was fixed) -- and those are IPv6. Passing
   an IPv6-shaped CIDR string into `GenUtils.address(..., version='4')` doesn't raise, it
   silently produces a wrong/uninterpretable condition. Fixed with `_ip_version(addr)`
   (`':' in addr`) instead of a hardcoded literal, used both here and in the new
   `_routing_table`/`_dispatch_table`.

3. `XMLUtils.CanonizeIP`'s IPv6 "::" expansion drops the boundary zero group when the
   compressed run is at the very END of the address (`Address.split('::')` gives an empty
   `Postfix`): `"2001:db8:abc:1::/64"` canonicalises to `"2001:db8:abc:1:0:0:0:/64"` -- a
   TRAILING COLON, one zero group short -- which later crashes
   `Instantiator._HandlePrefixes -> ConvertCIDRToVariables` with
   `ValueError: invalid literal for int() with base 16: ''` on the empty trailing segment.
   Confirmed directly: `CanonizeIP` on `"2001:db8:abc:1::0/64"` (explicit trailing zero)
   round-trips correctly; on `"2001:db8:abc:1::/64"` it does not. wl_up's own real
   rulesets never hit this -- every one of them writes an explicit trailing zero before a
   mask (`"2001:db8:abc::0/48"`, confirmed in `pgf.uni-potsdam.de-ruleset`), evidently a
   deliberate authoring convention that happens to dodge the bug -- but FaVe's own
   `routes.json`-derived subnet strings (fed through the new dst-LPM routing table) don't
   follow it. **Not fixed in ad6 core** here -- logged as a §8 architecture-review item
   alongside the multi-value `ctstate A,B` AND-instead-of-OR finding from item 9 (both are
   `CanonizeIP`/`ConvertCIDRToVariables` corners, worth revisiting together). Worked
   around in `favemodel.py` with `_ipv6_safe`, which inserts the exact same explicit zero
   the real rulesets already write by convention -- equivalent, not a behaviour change,
   same spirit as `_is_constrained`'s pre-existing `/0` hygiene workaround.

**Structural correctness confirmed** (`fave/test/test_ad6_wl_up.py`): 159 devices (136
ruleset-bearing + 23 switches), 137 generators/probes (AD6_PLAN.md §1.3's n=137), model
builds+instantiates in ~8s. Traced a full topology chain end to end
(`gensrc_source_pgf..._r0 -> pgf output -> pgf routing -> egress interface -> dmz switch
forwarding -> file's input chain -> file's accept`) node by node to confirm every hop
after the three fixes above.

**OPEN METHODOLOGY QUESTION for the full differential (not resolved here):** an
UNCONSTRAINED query against wl_up is close to vacuously "always reachable" -- every chain
has an unconditional `-m conntrack --ctstate ESTABLISHED -j ACCEPT`, and static
header-space analysis cannot distinguish a genuinely-established packet from one merely
claiming to be. Once `related:0`/state=NEW is forced (item 9's mechanism) AND the source
is properly CIDR-seeded, results become meaningfully differentiated -- but comparing
against `reachable.json` under strict equality (test_ad6_wl_ifi.py's own approach) is the
wrong bar for wl_up specifically: traced one concrete case
(`clients.hssport.uni-potsdam.de` -> `file.uni-potsdam.de`) where a real, operationally-
necessary rule (blanket admin SSH from the whole internal /48) grants reachability
`reachable.json`'s 29-role list for that target doesn't include, because reach.txt's
policy matrix never asked about that specific pair at all -- not a translation bug.
`cchecks.json`'s explicit tuples are the right comparison target instead (mirroring
wl_ifi's own `test_ad6_wl_ifi_stateful.py` characterization), deferred to a bench script:
the full 11902-entry file is a ~1-2 hour run at the observed ~0.5s/query.
