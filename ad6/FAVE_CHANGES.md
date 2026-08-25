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

## 11. `CanonizeIP` IPv6 "::" expansion fixed in core -- also worse than the trailing-only
case first logged (item 10), and a separate crash on no-compression at all  **[FIX]**

Item 10 logged this as a workaround (`favemodel.py:_ipv6_safe`) rather than a core fix, at
the same "review architecture once benchmarks work" gate as the other latent findings.
Claas asked for the same test-first treatment as the `/0` and init-mutual-exclusion bugs
(items 6-8) instead of leaving it as a documented workaround.

**Tests written first** (`ad6/test/xml/xmlutilstest.py:testIp6BoundaryCompression`, newly
wired into `xmlsuite.py` -- see below): round-trips `XMLUtils.ConvertToVariables` +
`ConvertCIDRToVariables` (the real call chain, not `CanonizeIP` in isolation) over five
IPv6 forms -- trailing `::` (`"2001:db8:abc:1::/64"`, item 10's original find), leading
`::` (`"::1/128"`), `::` alone (`"::/32"`), an already-working middle `::` (`"fe80::1/64"`,
the pre-existing `testIp6` fixture's own address, as a stays-green control), and no
compression at all (`"2001:db8:abc:1:2:3:4:5/128"`). **Confirmed the true scope before
fixing, same discipline as item 8:** the pre-fix code failed on THREE of the five, not
just the one already logged --

- Trailing `::` (item 10's original find): `"2001:db8:abc:1::/64"` → malformed
  `"2001:db8:abc:1:0:0:0:/64"` (one zero group short, trailing colon).
- Leading `::` (new): `"::1/128"` → malformed `":0:0:0:0:0:0:1/128"` (one zero group
  short, LEADING colon this time).
- `::` alone (new): `"::/32"` → malformed `":0:0:0:0:0:0:/32"` (TWO zero groups short,
  both a leading and a trailing colon).
- No compression at all (new, a different root cause in the same function): raises
  `UnboundLocalError: cannot access local variable 'Prefix'` -- `Address.split('::')` on a
  string with no `"::"` returns a 1-element list, so `Prefix,Postfix = ...` raises
  `ValueError` during unpacking (neither name gets bound), and the bare `except:
  Postfix = Prefix; Prefix = ''` handler itself then crashes referencing the
  never-assigned `Prefix`.

Root cause of the first three: `InLen = 8 - len(Prefix.split(':')) - len(Postfix.split(':'))`
undercounts by one for every side that is the empty string -- `''.split(':')` is `['']`
(length 1), not 0, so an empty Prefix or Postfix is silently counted as "one explicit
group" instead of zero.

**Fix:** replaced the `try/except`-driven split with an explicit `if '::' in Address`
check, and built the expanded address as a flat list of hex groups
(`PrefixGroups + ['0']*InLen + PostfixGroups`, using `[]` rather than `['']` for an empty
side) joined with `':'` in one step -- this can't produce a stray leading/trailing colon
by construction, unlike the old three-piece string concatenation. The no-compression case
is now its own explicit branch (`Address.split(':')` directly, no zero-run to expand),
removing the crash rather than routing it through the `::`-splitting logic at all.

**Also fixed while here:** `testCIDRMatchAll` (item 6's own regression test) had never
actually been wired into `xmlsuite.py`'s test list -- present in
`test/xml/xmlutilstest.py` since item 6, but not in the `tests = [...]` `xmlsuite.py`
references, so `make test` never ran it. Added both `testCIDRMatchAll` and this item's
`testIp6BoundaryCompression` to that list.

`favemodel.py`'s `_ipv6_safe` workaround (item 10) is now **removed**, not left as
redundant belt-and-suspenders -- same discipline as item 8's `fave_bridge.py`
`_exclusivity_conjuncts` removal: verified the core fix alone is sufficient first
(`XMLUtils.CanonizeIP`/`GenUtils.address` on the exact wl_up trailing-`::` CIDR that
originally motivated the workaround, confirmed correct output and no crash), then removed
the three call sites and the function itself, then re-ran `fave/test/test_ad6_wl_up.py`
and the full `test_ad6_wl_ifi*`/ad6 `make test` suites -- all still green with the
workaround gone.

## 12. Stateful instantiator is not a sound oracle for wl_up: two independent bugs, one
architectural  **[NEW finding, no source change -- GO/NO-GO flag raised, unresolved]**

Running wl_up's real `cchecks.json` compliance policy through the stateful instantiator
(§9) at even a small sample (`bench/wl_up/eval/wl_up_cchecks_diff.py`, 10 singleton/central
sources, 1092 of the full 11902 checks) produced 488 violations -- far beyond the
already-understood "unconstrained plain query is vacuous" gap (item 10). Traced to two
independent bugs, only one of them root-caused.

**Bug 1 (root cause understood, architectural, not a small fix): the `related:1`
(ESTABLISHED) half of every `<->>` check is vacuously true.** `src/parser/iptables.py`'s
`IP6TablesParser` parses `-m conntrack --ctstate ESTABLISHED` into a bare
`<state>ESTABLISHED</state>` match -- one exogenous, freely-choosable bit
(`XMLUtils.STATES`/`ConvertStateToVariables`) with no causal link to "a matching flow was
actually permitted in the reverse direction first." `fave_bridge.py`'s `_state_literals`
forcing mechanism (item 9) forces this bit directly onto a query, but that only asks the
solver "can you assert this bit AND find some other permit rule" -- always yes whenever a
device has an unconditional `-j ACCEPT` gated on nothing but that bit, which is true of
essentially every wl_up device (`ip6tables -A INPUT -m conntrack --ctstate ESTABLISHED
-j ACCEPT`, no `-s`). Verified directly: forced `related:1`, must-NOT-reach, for the 8
wl_up singleton/central sources against two org probes -- **all 8 report reachable=True**,
including one source (`adm.uni-potsdam.de`) independently confirmed correctly *blocked* on
the `related:0` side for the same probes. Zero source discrimination.

This is exactly the gap FaVe's own `fave/iptables/generator.py` "state shell interweaving"
(`_derive_general_state_shell`/`_get_block_intervals`/`_derive_conditional_state_shells`/
`_interweave_state_shell`) exists to close: it derives the ESTABLISHED-return leg from the
*actual* corresponding NEW-state permit rule in the opposite chain (direction/port-swapped,
match-intersected, spliced in at the right position in the rule order), so "ESTABLISHED" is
a *consequence* of an earlier permitted flow rather than a free bit any query can assert.
`IP6TablesParser` has no equivalent pass -- it is a literal, structural ip6tables-text-to-
Kripke translator with no state-causality modelling at all. This is not a wl_up quirk: it
would reproduce on any ip6tables ruleset using `-m conntrack --ctstate` (standard practice).
wl_ifi's own stateful checks (item 9) happened to dodge this because its Cisco ACLs are
genuinely state-blind (no ctstate match exists there to be mishandled) -- wl_up is the first
workload whose real rules actually exercise this path, and it fails.

**Bug 2 (NOT yet root-caused): a separate, address-specific bug in the `related:0` (NEW)
direction.** Of 8 structurally identical singleton hosts sharing one `/64`
(`2001:db8:abc:1::1`-`::8`: file/mail/web/ldap/vpn/dns/data/adm), every org device's real
ip6tables ruleset carries an unconditional `-A INPUT -s 2001:db8:abc:1::0/64 -j DROP` with
no later re-permit for that source -- so a state=NEW, src-seeded query from any of the 8
should be UNSAT. 7 of 8 report reachable=True anyway; only `adm` (`::8`) is correctly
blocked. Confirmed deterministic and address-specific, not query-order-dependent (reversing
the query order still leaves `adm` as the sole correctly-blocked case). Ruled out:
`_is_constrained`'s `/0` special-case (inapplicable -- real host addresses), state
contamination between queries in the same bridge-subprocess batch (ruled out by the
order-reversal test), and the just-fixed `CanonizeIP` "::" bug (none of these addresses
contain "::"). Prime remaining suspect, untested: `Instantiator._ShortenPrefixes`/
`_HandlePrefixes`'s CIDR canonicalization across the full 159-device model's shared
`src_ip6_*` variable space -- unlike bug 1, this has not been isolated to a specific
function yet.

**Consequence:** AD6_PLAN.md §1.4(b)'s original "ad6 already has the STATE field
end-to-end..., so this is query-orchestration work on top of existing machinery, not new
modelling" call is falsified by bug 1 -- making `related:1` checks meaningful needs
something functionally equivalent to the state-shell interweaving *inside* ad6's
translator, which is new modelling, not orchestration. **GO/NO-GO flag raised for Claas**
(AD6_PLAN.md §5.1's "STOP" block, §1.4(b), "Open decisions") -- not resolved as of this
writing. No source change in this item; nothing has been fixed.

## 13. Bug 2 root-caused and fixed; plain wl_up queries found equally vacuous;
GO/NO-GO resolved: NO-GO on wl_up via ad6, effort redirected to Stanford/i2

**Bug 2's real root cause -- not `_ShortenPrefixes` (that hypothesis was built, tested in
isolation with a targeted unit repro, and cleared before landing on the real cause).**
`ad6/fave_bridge.py`'s query source-address seeding (`_seed_conjunct`) forced the packet's
source into a CIDR via a bare named-alias SAT variable
(`XMLUtils.ConvertToVariables`'s `<ip>`-element form) instead of the canonical shared
bit-vector conjunction (`XMLUtils.ConvertCIDRToVariables`'s flattened
`ip<version>_src_<i>=<bit>` literals) -- the identical footgun class `_state_literals`
(item 9) already had to avoid for state-forcing, just never applied to address-seeding.
The alias only constrains anything if that *exact* address/CIDR string happens to already
be `Handled` (defined via an equality clause during `Instantiator.InstantiateBase`'s scan)
by some *other* rule referencing it verbatim elsewhere in the whole 159-device model.
Checked against the real ruleset corpus (`grep -rn -- "-s 2001:db8:abc:1::$i\b"` across
every `bench/wl_up/rulesets/*-ruleset`): true by coincidence for `::8` (`adm`, referenced
in an unrelated admin-SSH rule in `pgf.uni-potsdam.de-ruleset`), false for the other 7
singleton hosts, which their real rulesets only ever match via the broader `/64`.

**Fix:** `_seed_conjunct` -> `_seed_literals`, now builds and flattens via
`ConvertCIDRToVariables`, mirroring `_state_literals`'s existing discipline exactly;
call site changed `instance[0].append(...)` -> `instance[0].extend(...)`. Regression tests
added test-first, confirmed failing pre-fix (isolated via `git stash`/`pop`), passing
post-fix: `ad6/test/core/instantiatortest.py::testSrcCidrQuerySeedMustUseSharedBitVector`
(mechanism-pinning, standalone one-firewall repro) and
`fave/test/test_ad6_wl_up.py::test_stateful_checks_on_real_pairs` (extended to all 8
singleton hosts against a real probe). `ad6 make test` (9 suites) and
`fave/test/test_ad6_wl_up.py`/`test_ad6_wl_ifi.py`/`test_ad6_wl_ifi_stateful.py` (9/9) all
green. Committed `dfd543b0`.

**The fix generalizes -- this is not just an 8-host patch.** Re-running
`bench/wl_up/eval/wl_up_cchecks_diff.py`'s sample mode at full size (35/131 orgs sampled,
3342 checks, 1126 stateful) afterward found only **1 stateful violation total** (was ~45%
of a much smaller sample before the fix) -- strong evidence the fix holds at scale, not
just on the 8 hosts it was diagnosed from.

**But that same larger run surfaced something more important than confirming the fix:
PLAIN (non-stateful, no `related` condition at all) checks are almost totally broken
too.** Of 1713 plain "must NOT reach" checks in the sample, **1712 came back as false
violations (99.94%)**; all 503 plain "must reach" checks correctly passed. Root cause is
the same as item 12's bug 1: every wl_up device carries an unconditional
`-m conntrack --ctstate ESTABLISHED -j ACCEPT`, a free bit any unconstrained query can
satisfy regardless of source -- a plain check forces no state literal either way, so it
falls into exactly this trap. This had been flagged as a *theoretical* risk in
`AD6_PLAN.md` §5.1's prose ("an unconstrained existential query is close to vacuously
reachable") but never measured until now; the true number is not "close to" but total.
**Consequence: scoping wl_up's ad6 comparison down to non-stateful checks is not the safe
fallback it looked like -- the plain path is the MORE broken one, not the safer one.** The
only wl_up queries behaving soundly are `related:0` (state=NEW)-forced ones; `related:1`
stays vacuous (bug 1, unfixed, architectural) and plain queries are vacuous for the
identical underlying reason.

**Checked directly (not assumed) whether FaVe+NetPlumber has the same problem: no.**
`fave/bench/generic_benchmark.py`'s `GenericBenchmark` defaults `use_interweaving=True`,
which (via `util/bench_utils.py`'s `_add_packet_filter`) routes wl_up's real ip6tables
ruleset text through FaVe's *own* translator, `fave/iptables/generator.py` -- the
`_derive_general_state_shell`/`_derive_conditional_state_shells`/`_interweave_state_shell`
machinery derives the ESTABLISHED-accept leg from the actual corresponding NEW-permit rule
and splices it in as a real flow-space constraint at model-construction time, so there is
no free bit for a plain query to exploit. `ad6/src/parser/iptables.py`'s `IP6TablesParser`
has no equivalent pass. Corroborating evidence already in this codebase (cited, not
re-measured this session): `fave/bench/wl_up/eval/apkeep_up_diff.py`'s docstring records
an exact match, 0 diffs, 3660/3660, between APKeep and NetPlumber on wl_up's full 137x137
plain reachability matrix -- a *sparse* reachable set (`reachable.json` itself lists 3370
policy-intended reachable pairs), not anything close to ad6's near-universal answer. Two
independent real engines agreeing on a restrictive plain-reachability result is strong
evidence this is an ad6-specific gap, not a generic HSA/state limitation.

**Decision (Claas, 2026-08-21): NO-GO on wl_up via ad6, for both the stateful and plain
path.** Porting real state-shell interweaving into `ad6/src/parser/iptables.py` would mean
re-implementing, inside a 2014 codebase that has already produced four real core bugs in
two days, a mechanism FaVe already has working in `fave/iptables/generator.py` -- and doing
so would undercut the "generic tool, low integration cost" thesis this evaluation exists
to test. wl_up's correctness work moves to FaVe+NetPlumber (oracle) / FaVe+NDD-APKeep
(arbiter) instead of ad6. wl_tum's and wl_ifi's exact-match ad6 results stand unaffected
(wl_tum has no stateful checks; wl_ifi's real ACLs are genuinely state-blind, confirmed by
Claas -- item 9/10). Remaining ad6 effort redirects to Stanford/i2 (`AD6_PLAN.md` §5.2), an
orthogonal, still-open, non-stateful SAT-encoding-scale question with a trusted oracle
already in hand (NetPlumber==APKeep==165 on wl_stanford).

## 14. §5.2 scoping confirmed (LPM, not VLAN, is the real gate); a genuine LPM-tiebreak
bug found test-first and fixed in `Ad6Adapter`; scope corrected back toward the faithful
variants  **[FIX + finding]**

**Scoping check before any Stanford/i2 translator work: is the VLAN-admission-cross-product
risk `AD6_PLAN.md` §5.2 flags actually load-bearing for the in-scope target?** Checked
against the current code, not assumed. `fave/apkeep/adapter.py`'s `_capture_in_admit`/
`_gate_dead_ingress` (the fix that made APKeep converge exactly with NetPlumber at 165,
`[[stanford-forwarding-overapprox]]`) is a binary per-physical-port admission gate ("does
this ingress port have any admission rule at all"), not per-(port,VLAN) rewrite --
`[[apkeep-vlan-admission-tractability]]`'s intractability finding is specifically about the
coupled admission+egress-VLAN-*rewrite* cross-product, which that same memory states
outright is "NOT needed for wl_stanford... source spans all VLANs => admission
non-binding for all-pairs" at the current 165 target. That full-VLAN mode is gated behind
`_faithful_vlan`/`_i2_faithful` flags in `apkeep/adapter.py`, off by default. So §5.2's real
requirement for the 165-target benchmark is **LPM-at-scale forwarding + a cheap dead-port
gate**, not "LPM + VLAN admission" -- a smaller spike than the plan text implied.

**Built the LPM half of that spike test-first, on the actual reusable building block, before
writing any Stanford-specific code.** `ad6/src/parser/favemodel.py::_routing_table` is the
dst-egress-selection mechanism `AD6_PLAN.md` §5.1 built for wl_up and §5.2 earmarks for
reuse on Stanford/i2's FIB; its own docstring said "ad6 has no LPM" and excused this because
"wl_up's own routing table never has two overlapping-prefix routes on one device, confirmed
via the captured rules" -- an empirical fact about *that* benchmark, not a property of the
mechanism. `fave/ad6/adapter.py`'s `_translate_fwd_rule`/`_translate_routing_rule` (the
producers of the `prio` field `_routing_table`/`_build_device_table` sort by) assigned every
dst-specific route the *same* `prio` (0; only the no-dst default got 65535) -- a stable sort
over equal keys, so a tie between two overlapping-prefix routes resolved to whichever the
caller happened to append first, not to prefix length.

New test `ad6/test/parser/favemodeltest.py::RoutingTableLPMTest` (wired into `make test` as
the new `ParserSuite`) drove `_routing_table` directly (not a hand-rolled model) with a real
`/32` and a nested `/64` route, in both insertion orders, forcing the destination header to
an address inside both via the same `XMLUtils.CanonizeIP`/`ConvertCIDRToVariables` machinery
`fave_bridge.py`'s `_seed_literals` already trusts. **Confirmed failing pre-fix**: with
`[general, specific]` capture order the `/32` wrongly won (`general reached: True, specific
reached: False`); with the order swapped the `/64` happened to win by luck. Identical route
content, only order changed, different (and one wrong) answer -- the same bug class that
made vanilla NetPlumber misreport Stanford as 10/165 before its own reprioritisation fix
(`[[stanford-forwarding-overapprox]]`).

**Fix:** `fave/ad6/adapter.py` gets `_prefix_len(cidr)` (mask-length parser, defensive
32/128 fallback for a bare address) and `_lpm_prio(dst)` (`65535` for the no-dst default,
else `65535 - 1 - prefix_len(dst)`), so a longer prefix always sorts before a shorter one on
the same device regardless of capture order; both `_translate_fwd_rule` and
`_translate_routing_rule` now call it instead of the old binary split (both functions had
the identical pattern and the identical latent risk, so both were fixed together).
`_routing_table`'s docstring updated accordingly. Regression coverage, test-first: the
`ad6/`-side `RoutingTableLPMTest` (rebuilt with realistic `prio` values -- ad6's test tree
cannot import `fave/ad6/adapter.py`, separate PYTHONPATH roots/venvs, so the formula is
duplicated locally with a cross-reference) now asserts both insertion orders agree;
`fave/test/test_ad6_adapter_lpm_prio.py` pins `_lpm_prio`/`_prefix_len` directly (5 cases,
including a real bug in this test file's own first draft of `_prefix_len`'s bare-address
fallback, caught by its own `rpartition` edge case and fixed before landing). No regression:
`ad6 make test` (10 suites, including `clasp`/`minisat`, both of which needed
`apt-get install` after a container reset had silently dropped them alongside `bison`/
`flex`/`m4` -- see `[[env-integration-tier-deps]]`) and `fave/test/test_ad6_wl_ifi.py`/
`test_ad6_wl_ifi_stateful.py`/`test_ad6_wl_up.py`/`test_ad6_adapter_lpm_prio.py` (14/14) all
green -- the fix is prio-value-only and order-preserving wherever routes don't genuinely
overlap (wl_ifi/wl_up's case), so it cannot change either benchmark's already-verified
result.

**Scope correction (Claas): despite §5.3's "faithful-VLAN variants likely out of scope"
framing, work towards the faithful variants, not around them.** Recorded here as an
explicit reversal of that framing (`AD6_PLAN.md` §5.3 updated) -- the LPM fix above is a
prerequisite either way (both the plain-165 and the faithful-VLAN targets need correct
dst-FIB forwarding), but the admission-only gate this session confirmed sufficient for 165
is NOT the end state to design toward; the Stanford/i2 translator should be built with the
faithful (per-port,VLAN admission + egress rewrite) target in view from the start, not
scoped down to what the current 165 oracle happens to require. `AD6_PLAN.md` §5.2/§5.3
updated to reflect this.

## 15. §5.4 staged VLAN-spike plan; Stage 0 prerequisite fix (per-device ACL/VLAN capture,
was silently clobbering across devices)  **[FIX + plan]**

**Planned the faithful-VLAN spike as a staged, GO/NO-GO-gated protocol** (`AD6_PLAN.md`
§5.4): Stage A (synthetic expressibility test, zero real data, zero `ad6/src/core|xml|sat`
changes) gates Stage B (tractability on real Stanford data, reusing APKeep's own
`--routers` N=2/3/5/16 subset protocol, `fave/bench/faithful_bdd_measure.py`, for a direct
comparison). Two architectural findings frame it: `GenUtils.action()` has no `rewrite` type
anywhere in ad6's core (`GenUtils.vlan()` is match-only, evaluated once at build time) --
so a faithful model has to be the same structural "which Kripke entry-point node" trick §4.4
already used, not a header-rewrite mechanism; and `ad6/src/sat/satutils.py`'s `ConvertToCNF`
is naive distribution-based (no Tseitin), which explodes on *alternation depth*, not raw
node count -- a different blow-up mechanism than BDD's variable ordering, worth measuring
rather than assuming either way.

**Stage 0 -- a real, previously-unflagged blocker, found and fixed before any VLAN code.**
`fave/ad6/adapter.py`'s `_acl_device` (`Optional[str]`) and `_acl_in`/`_acl_out`
(`Dict[Optional[str], List]`, keyed by bare VLAN value only) were correct only for wl_ifi's
*one* admission-checked router -- Stanford is 16 independent `in.X`/`out.X` devices that can
reuse the same VLAN number for unrelated admission groups. Confirmed via `git stash` (same
discipline as every other fix this cycle): fed the pre-fix code a synthetic two-device
model with the same VLAN number ("10") on both, and the second device's capture silently
merged into the first's `acl_in['10']` list (`{'10': [devA-entry, devB-entry]}`, one flat
list instead of two separate per-device groups) -- and a scalar `_acl_device` simply forgot
device A's identity once device B was captured. This is a hard blocker for Stanford at *any*
fidelity, including the already-in-scope plain-165 target, not something specific to VLAN
faithfulness.

**Fix:** `_acl_device` -> `_acl_devices` (a `set`); `_acl_in`/`_acl_out` ->
`Dict[device, Dict[vlan, List]]`; `_vlan_to_eport` -> `Dict[device, Dict[vlan, port]]`
(`_capture_vlan_port` now takes `device` explicitly). `ad6/src/parser/favemodel.py`'s
`ir["acl_device"]` (singular) -> `ir["acl_devices"]`, threaded through
`_ingress_ports_for`/`entry_key`/`_build_device_table`. **A second, related latent bug found
in the same pass:** `_build_device_table`'s egress-ACL-table loop iterated the *entire*
`out_port_vlan` map (a global "device.port"->vlan dict, never keyed by device at all)
unfiltered -- harmless with exactly one acl device (every entry belonged to it by
construction) but would silently emit a spurious egress-ACL table for another device's port
once a second admission-checked device exists. Now filtered to the current device's own
ports (`_split(eport)[0] != device: continue`).

**Regression:** new `fave/test/test_ad6_adapter_multi_device_acl.py` (2 tests) -- pure
`Ad6Adapter` capture-layer unit tests (fake `Rule`/`RuleField`/`Forward` objects, no ad6
binary/subprocess/benchmark inputs needed), confirmed failing against the pre-fix code via
`git stash`/`pop` before landing, passing after. `fave/test/test_ad6_wl_ifi.py`'s
`test_acls_translated` updated for the new `_acl_devices` (set) shape. No regression: `ad6
make test` (10 suites) and `fave/test/test_ad6_wl_ifi.py`/`test_ad6_wl_ifi_stateful.py`/
`test_ad6_wl_up.py`/`test_ad6_adapter_lpm_prio.py`/`test_ad6_adapter_multi_device_acl.py`
(16/16) all green. Since no Stanford ad6 translator exists yet, this stage's regression
check is necessarily wl_ifi's (1 acl device) and wl_up's (0 acl devices) existing results,
not yet a Stanford rebuild -- the plain-165 rebuild `AD6_PLAN.md` §5.4 calls for becomes
possible once §5.2's translator itself is built.

Stage A (synthetic trunk+rewrite expressibility test, extending
`ad6/test/parser/favemodeltest.py`) and Stage B (real N=2/3/5/16 tractability measurement,
bare-metal only) are planned but not yet started -- full protocol, GO/NO-GO criteria, and
compute budgets: `AD6_PLAN.md` §5.4.

## 16. Stage A revised: structural VLAN entry-point duplication is not general mutation;
adopt an SSA/frame-axiom ad6-core extension instead  **[plan revision, no code yet]**

**Claas: the structural-duplication Stage A design (§15) does not actually solve
mutation.** ad6 has no notion of one header bit taking more than one value along a path --
every variable is a single global propositional constant. The structural approach ("which
VLAN a packet is on = which Kripke entry-point node it's wired into") only works when a
field changes *at most once* per path; a chain of rewrites (e.g. `b=* -> 1 -> 0 -> *`) needs
as many distinct values as rewrite points, and duplicating the downstream subgraph once per
combination of values blows up as `(distinct values)^(rewrite points)` in the worst case --
the identical failure shape (mechanistically different substrate, same combinatorics) that
made APKeep's BDD-based faithful-VLAN attempt intractable.

**Revised approach (not yet implemented): SSA construction over the Kripke graph.** Treat
the Kripke graph like a program's control-flow graph and a mutable field like a mutable
variable -- textbook static-single-assignment: one fresh per-node copy of the field's bits
at each node reachable from a rewrite (everything else keeps using today's shared global
bit-vector, so the cost is scoped to just the mutable field); a frame axiom on every
non-rewriting edge (`transition_uv -> (b@v <-> b@u)`); a rewrite axiom on a rewriting edge
(`transition_uv -> (b@v <-> c)`); a phi-style disjunction over predecessors at a join. This
composes with the per-edge implication shape `Instantiator._ConvertNodesToImplications`
already builds (`ad6/src/core/instantiator.py:330-382`) rather than requiring a wholly new
mechanism, but it is a genuine **ad6 core** change (`GenUtils` needs a real `rewrite`
action; `Kripke`/`Instantiator` need per-node field-copy allocation) -- a deliberate,
explicitly-flagged departure from this integration's "new frontend, zero backend changes"
discipline (§4.4) followed everywhere else so far. Scales with the number of Kripke nodes
reachable from a rewrite (linear in graph size) rather than the product of values across
rewrite points -- a materially better asymptotic story than the superseded draft, *if* it
can be built cheaply enough, which is exactly what the revised Stage A/B now exist to check.

**Also flagged in the same discussion**: `ad6/src/sat/satutils.py`'s naive
(non-Tseitin) `ConvertToCNF` is a candidate fix for Stage B *if* clause growth there turns
out to be dominated by CNF distribution rather than by the SSA encoding's own node count --
and, independent of this spike, a candidate general improvement for ad6 (§8.5, new) worth
scoping on its own once the benchmarks stabilize. Full revised protocol, GO/NO-GO criteria
per stage: `AD6_PLAN.md` §5.4/§8.5.

## 17. Stage A built and GO: SSA/frame-axiom mutation encoding, test-first, in ad6 core
**[NEW core feature]**

**Implemented the revised Stage A design (item 16) -- a genuine ad6 core extension, the
first change this integration makes outside the "new frontend only" discipline (§4.4).**
`GenUtils.action()` gains `rewrite_field`/`rewrite_value` kwargs riding on the same
`<action>` as the jump it accompanies; `KripkeNode` gains a `Rewrites` dict (`kripke.py`'s
`_HandleRule` reads it off the action); `XMLUtils.FieldBitName`/`ConvertFieldToVariables`
give every mutable field a per-NODE bit-vector naming convention (`"<field>#<node>_<i>"`,
"#" chosen because nothing else in this codebase's variable naming uses it, so it can never
collide with the existing global dst/src/port/vlan/state aliases); `Instantiator.
_CreateMutationConstraints(Kripke, MutableFields)` walks every edge and every declared
mutable field, emitting a rewrite axiom (`transition -> (field@target <-> constant)`) or a
frame axiom (`transition -> (field@target <-> field@source)`) otherwise, built and
CNF-converted per-edge exactly like `_ConvertNodesToImplications`'s own pattern;
`Instantiator.InstantiateBase` gains an opt-in `MutableFields=None` parameter (every
existing caller passes nothing new, so wl_ifi/wl_up/wl_tum are byte-for-byte unaffected).

**Verified the underlying CNF mechanism empirically before relying on it, not by trusting a
hand-trace.** A literal read of `SATUtils._ConvertBinaryForm`'s dispatch (falls through to
`return _ConvertBinaryForm(Formula[0])` for a bare `<implication>` tag) suggested a
non-degenerate `A -> (B AND C)` implication would have its conclusio silently dropped,
keeping only `A` -- which would be a live, fundamental soundness bug in machinery this whole
codebase depends on (`_ConvertNodesToImplications` builds exactly this shape for every real
edge with a real predecessor). Ran it directly instead of continuing to hand-trace:
`SATUtils.ConvertToCNF` on that exact shape correctly yields `(B OR NOT A) AND (C OR NOT
A)`. The hand-trace was wrong (missed that `_ResolveConstants` runs bottom-up and the
top-level `<conjunction>` wrapper unwraps around the implication before `_ConvertBinaryForm`
ever sees it) -- recorded here so the next person tracing this code doesn't have to redo it.

**Join handling needs no new exclusivity mechanism.** A node reachable from two
predecessors with different rewrite histories gets one independent implication per incoming
edge, each gated on its own transition literal -- if both were simultaneously true with
conflicting histories that's correctly UNSAT under the *existing* reachability discipline
(exactly like two conflicting forwarding paths already would be), and the solver remains
free to leave the non-taken predecessor's transition false, exactly as it already does for
plain reachability. No new "at-most-one-predecessor" constraint was needed or added.

**Test, test-first**: `ad6/test/core/instantiatortest.py::testMutationChainAndJoinSSAEncoding`
(wired into `InstantiatorSuite`) -- **not** `ad6/test/parser/favemodeltest.py` as item 16
assumed; this is pure core Kripke/Instantiator machinery with zero `favemodel.py`
involvement, so `instantiatortest.py` (home of the other core-mechanism regressions: the
`/0`-CIDR bug, state-literal forcing) is the honest location. Fixture: `entryA -> r1(rewrite
vlan=1) -> r2(rewrite vlan=0) -> r3(rewrite vlan=2) -> join` (a 3-deep rewrite chain) and
`entryB -> alt(no rewrite) -> join` (the join predecessor that never rewrites), `entryA`/
`entryB` both marked INIT so `Instantiator._CreateInitConstraints`'s EXISTING mutual
exclusion (§8) -- reused, not reinvented -- forces exactly one path when querying
`InstantiateEndToEnd` from either entry. Confirmed failing test-first via `git stash` on
just the 5 core files (`GenUtils.action() got an unexpected keyword argument
'rewrite_field'`), passing after.

**Result: GO.** Forcing `entryA`'s path, `join`'s vlan is SAT for exactly 2 and UNSAT for 1
or 3 -- the 3-deep chain resolved to precisely the value the rewrite history implies, not
silently dropped or stuck at an intermediate value. Forcing `entryB`'s path, `join`'s vlan
is SAT for two different arbitrary values (5 and 7) -- genuinely free, not accidentally
pinned. No regression: `ad6 make test` (10 suites) and every fave-side ad6 test (16/16)
green. In passing, found `testCycle`/`testShadow` are a **pre-existing order-dependent
MiniSAT flake** when run back-to-back outside `make test`'s own per-suite invocation --
confirmed present on the unmodified baseline too (not introduced here, and `make test`
itself is unaffected).

**What this does NOT cover**: only the core mechanism, on a hand-built synthetic fixture.
Wiring real Stanford VLAN-rewrite data into it (`Ad6Adapter._capture_mid_rewrite`/
`_capture_out_rewrite`, and `favemodel.py` actually calling `InstantiateBase(...,
MutableFields=...)`) plus the tractability measurement itself is Stage B, not yet started.
Full details: `AD6_PLAN.md` §5.4.

## 18. Stage B split into checkpointed sub-stages; B0 (the wl_stanford<->ad6 translator,
plain/no-VLAN) built from scratch, two real bugs found and fixed  **[NEW + FIX]**

**No wl_stanford<->ad6 translator existed at all before this** -- §5.1-§5.3's work never
built one (wl_ifi/wl_up/wl_tum only). "Stage B" (item 15/16) was written assuming the
translator already existed; split into checkpointed sub-stages per the user's explicit
incremental pacing: B0 (plain LPM+dead-port translator, DONE below) -> B1 (scale to 16
routers vs the 165 oracle) -> Stage A2 (a new core primitive, see below) -> B2 (VLAN-
faithful wiring) -> B3 (the N=2/3/5/16 measurement item 15/16 already designed).

**B0: built the translator, reusing `fave/apkeep/adapter.py`'s own proven Stanford
translator as a template (ported, not imported -- ad6 and APKeep deliberately never share
process/imports, `fave/ad6/adapter.py`'s own module docstring).** wl_stanford's devices are
`SwitchModel`s named `in.<router>`/`mid.<router>`/`out.<router>`, each with exactly one
table `"<device>.1"` -- already matched `Ad6Adapter.add_rules`'s existing `fwd_tables`
dispatch, so only new stage-keyed handling (`model.node.split('.',1)[0]`, the same dispatch
key APKeep's own translator uses) was needed, not new table-name matching. New:
`Ad6Adapter._capture_in_admit`/`_capture_out_perm`/`_collapse_out_stage` (direct ports of
APKeep's identically-named functions); `favemodel.py::_gate_dead_ingress` (drops a topology
edge into an unadmitted physical port, called inside `wire_edges`). B0 models NO VLAN at
all -- admission is a binary per-physical-port gate, matching the existing oracle-verified
165 target (`[[stanford-forwarding-overapprox]]`), which was already confirmed VLAN-
non-binding for the plain data plane (item 14).

**Bug 1: multi-port (ECMP) forwards silently truncated to one port.** `_out_port`
(singular) kept only `action.ports[0]`; real Stanford `mid.*` data genuinely has multi-port
routes (one `/23` forwarding to 15 ports simultaneously -- confirmed against the real
`routes.json`, not assumed). Fixed with a plural `_out_ports` and `_add_fwd_route` (one IR
entry carrying the WHOLE port list, deduped on `(device,dst,ports)` -- also collapses
wl_stanford's `in.*` stage, whose per-VLAN admission rules all share one identical
unconditional default route, from N redundant entries to 1).

**This is NOT "loop and emit one rule per port" -- that would silently be wrong.** ad6's
table evaluation is sequential first-match (`KripkeUtils._HandleRule`'s fallthrough
discipline): N separate rules sharing the identical dst condition would let only the FIRST
one ever fire, since a query matching that condition is captured by the earliest rule in
table order -- the other N-1 ports' reachability would be silently dropped (dead,
unreachable code), an under-approximation nobody would notice without differential testing.
Fixed instead with `favemodel.py::wire_fanout`: a multi-port route's rule jumps to one
dedicated `"<rule-key>_fanout"` node, which `wire_fanout` wires to every one of the route's
egress interfaces via several separate `Kripke.Put` calls -- the same many-to-one "no
condition to check, just connect" idiom `wire_edges` already uses for plain topology
connectivity (`Kripke._FTransitions[key]` is already a list, so several simultaneous True
outgoing edges from one node give real OR/multipath semantics for free). Also modelled a
genuine dst-only blackhole (e.g. `dst=224.0.0.0/3`, no forward action at all -- a real
discard, not a translation gap): previously a silent no-op (harmless for wl_ifi, which
apparently never has one that matters), now an explicit jump to `DROP_KEY`, gated by the
same soundness guard `apkeep/adapter.py` uses (only model as a drop when the match is
genuinely dst(+vlan)-only -- a discard qualified by src/proto/port stays a no-op, since a
dst-only drop can't express those without over-dropping traffic the real discard never
touches).

**Bug 2: a probe with more than one real topology attachment silently checked only the
first -- not caught by design, caught by triage of a real UNSAT.** The N=2 induced-slice
differential (`--routers bbra_rtr,rozb_rtr`, the same subset `fave/bench/
faithful_bdd_measure.py`'s own measurement uses) first came back UNSOUND: ad6 dropped
`rozb_rtr -> bbra_rtr`, a pair NetPlumber reaches. Root-caused by hop-by-hop tracing with a
concrete, hand-picked witness destination (`10.240.0.0/12` -- confirmed by direct IR
inspection to fall outside every one of rozb's own ~89 specific FIB routes, so it must hit
rozb's default route toward bbra, and to be covered by one of bbra's ~868 specific routes
leading to a probe-connected port): every intermediate hop was independently confirmed
reachable with this destination forced, INCLUDING the exact `mid.bbra_rtr` egress port the
witness address routes to -- yet the full end-to-end query still came back UNSAT. Root
cause: `_attachment` (singular) resolved a probe/generator name to the FIRST topology edge
found and stopped there. wl_ifi/wl_up probes each have exactly one real attachment, so this
was never wrong before; `probe.bbra_rtr` genuinely has 48 real attachment points in the N=2
slice alone (every access-facing `mid.X` egress port collapsed from its own `out.X` stage
funnels into one probe) -- the query was checking reachability of one arbitrary one of the
48 while the witness address correctly routed to a *different* one.

**Fix**: new `_attachments` (plural -- `_attachment` is now a thin single-result wrapper
over it, used unchanged by `_gen_firewall` since every generator, wl_stanford's included,
genuinely has exactly one attachment); `wire_probe_fanout` (mirrors `wire_fanout`'s idiom in
the other direction: many real attachment edges feed one dedicated aggregate Kripke node,
needing no Gamma/firewall of its own since `Kripke.IterBTransitions` only reads
`_BTransitions[key]`, not a registered `KripkeNode` -- confirmed by reading `Instantiator.
InstantiateEndToEnd`'s actual implementation, not assumed); `query_destination_key`'s
signature changed to take the probe's own name (was a pre-resolved device/port pair) so it
can decide internally whether to resolve directly or via the fanout node --
single-attachment probes (every other benchmark) are completely unaffected, zero added
Kripke nodes or behaviour change. `ad6/fave_bridge.py`'s query loop updated for the new
signature (one line simpler -- the pre-resolution it used to do is now internal).

**Test, test-first**: `fave/test/test_ad6_wl_stanford_plain.py` -- 9 unit tests (fake
`Rule`/`RuleField`/`Forward` objects mirroring `test_ad6_adapter_multi_device_acl.py`'s
style, no ad6 binary/subprocess/benchmark inputs) for the multi-port/blackhole/dedup/
admission-capture mechanisms, confirmed failing (7/9; the other 2 correctly still pass,
being unaffected pre-existing behaviour) via `git stash` on the two touched adapter/
favemodel files before landing; plus a structural + differential test on the real N=2
induced slice, reusing `fave/bench/apkeep_convergence.py`'s own `_filter_model`/
`_write_model`/`_emit_worker` machinery (a LIVE NetPlumber worker diff, not a recorded
snapshot -- same discipline as `fave/test/test_apkeep_stanford.py` and as this project's
own B1 plan). **Result: GO.** `out.*` correctly collapses away (4 devices for the N=2
slice); ad6 now agrees EXACTLY with NetPlumber on the induced 2-router subnetwork (0
over-approximation, 0 under-approximation). No regression: `ad6 make test` (10 suites) and
every existing fave-side ad6 test (16/16, wl_ifi/wl_up included) green.

**Environment note**: this session's sandbox was also missing `liblog4cxx.so.15` (needed
for `libnetplumber`'s own compiled `.so` to import at all, surfacing as `NetPlumberLibAdapter`
raising "libnetplumber is not built" even though the `.so` file itself was present) -- a
recurrence of the same container-reset pattern already documented in
`[[env-integration-tier-deps]]` for `bison`/`flex`/`m4`/`clasp`/`minisat` earlier this
session; restored via `apt-get install liblog4cxx-dev`, unrelated to any code change here.

**Not yet done**: B1 (scale to all 16 routers, live diff against the 165-pair oracle) and
everything from Stage A2 onward. Full details: `AD6_PLAN.md` §5.4.

## 19. B1: a real generator-attachment bug fixed, and a genuine PRE-EXISTING ad6 CORE
soundness gap found -- STOPPED, reported, not fixed  **[FIX + flagged finding, no core
change made]**

**B1: scaled item 18's translator to all 16 routers** (`fave/test/test_ad6_wl_stanford.py`,
mirrors `test_apkeep_stanford.py` exactly -- full model, live NetPlumber worker diff, not a
recorded snapshot). First run: 0 under-approximation, but a wide over-approximation matching
Stanford's well-known **5 dead-port sources** signature exactly (`bbrb_rtr,boza_rtr,
goza_rtr,roza_rtr,yozb_rtr` -- `[[stanford-forwarding-overapprox]]`), appearing as a spurious
source against almost every probe.

**Bug found and fixed: a generator's own attachment bypasses dead-port admission entirely.**
`_gen_firewall` resolves a generator's attachment via `_attachment`/`entry_key` directly,
never touching `ir["edges"]`/`wire_edges` -- so item 18's `_gate_dead_ingress` (which only
filters device-to-device topology edges) never sees a generator's own attachment edge at
all. Item 18's N=2 slice (`bbra_rtr,rozb_rtr`) happens to contain none of the 5 known
dead-port routers, so this was never exercised there. **Fixed:** new `_is_admitted(device,
port, ir)` helper, shared by `_gate_dead_ingress` and `_gen_firewall` (a dead-port generator
now jumps straight to `DROP_KEY` instead of the device's normal entry point). Test-first:
`ad6/test/parser/favemodeltest.py::GenFirewallDeadPortGateTest` (3 tests), confirmed failing
via `git stash` on just `favemodel.py` before landing.

**This fix did NOT change the observed over-approximation at all -- byte-for-byte identical
before and after.** That, not assumption, is what triggered digging for a second cause.
Traced with a concrete, isolated experiment (not a guess): with NOTHING forced at all (no
source, no init asserted), `probe.bbra_rtr`'s own destination key was already SAT -- some
self-consistent model satisfies "packet arrived" with zero real origin. Reproduced in a
**minimal repro using stock `GenUtils`/`Instantiator` primitives only, zero Stanford/Stage-0/
Stage-A/Stage-B code involved**: a bare 3-node cycle `A->B->C->A` (none marked INIT) plus a
genuine, separate generator `entry` that only ever jumps to its own unrelated sink --
`Instantiator.InstantiateEndToEnd(kripke, encoding, 'entry', 'A')` returns **SAT**: `entry`
"reaches" a cycle it has zero real connection to. Pinned as `ad6/test/core/
instantiatortest.py::testCycleReachabilityIsUnsoundWithoutRealOrigin` -- a
**characterization** of a known, unfixed gap, not a regression test for something resolved.

**Mechanism, confirmed by reading `Instantiator._ConvertNodesToImplications`, not assumed:**
it builds only one-directional, purely LOCAL per-edge implications (`transition -> (my_gamma
AND some-predecessor-edge-fired)`) -- the textbook SAT-encoded-reachability pitfall: a closed
loop of such implications is a self-consistent fixed point the solver can satisfy by setting
every edge in the loop true simultaneously, with no requirement that the loop was ever
entered from a genuinely-fired INIT. `InstantiateEndToEnd`'s two disjunctions (source's own
edge fired; destination's own arrival fired) are asserted as **independent** top-level
conjuncts, not one connected path constraint -- so a destination inside/downstream of such a
floating loop is trivially "reachable" from ANY forced source. `Instantiator.
InstantiateCycle`/`_CreateCycle` already exists as a DISTINCT ad6 feature (detecting a cycle
reachable from init) -- cycles were a recognized concern in ad6's design, just never
integrated into reachability's OWN soundness. Consistent with ad6's 2014 design target (one
firewall's own rule-chain, always acyclic by construction -- a table's fallthrough/jump
structure cannot loop back on itself): wl_ifi/wl_up's topologies happen to be acyclic too,
so this was never exercised before Stanford's real backbone (genuine redundant inter-router
links) -- and exactly why item 18's tiny 2-router slice (no cycle between just those two)
passed cleanly while B1's full-scale differential does not.

**Decision: STOPPED here, reported to Claas, no core change attempted -- same discipline as
the wl_up NO-GO.** This is orthogonal to VLAN fidelity and gates the PLAIN Stanford/i2
target too, not just Stage A2/B2/B3 -- bigger than anything the original plan anticipated. A
real fix is genuine core surgery (e.g. a rank/distance variable enforcing strict progress
along a real path, the standard technique for this class of pitfall) comparable in scope to
Stage A's own SSA work. Open options, not yet decided: (a) attempt the core fix as its own
gated stage; (b) NO-GO on exact-match Stanford/i2 via ad6 (mirrors wl_up's precedent); (c) an
unidentified narrower mitigation.

**No regression:** `ad6 make test` (10 suites, including the new cycle-soundness
characterization) and every pre-existing fave-side ad6 test (27/27) stay green.
`test_ad6_wl_stanford.py` itself has its structural assertion passing and its differential
assertion failing as expected -- documenting the open gap, not a regression. Full details:
`AD6_PLAN.md` §5.4.

## 20. Item 19's cycle-soundness gap FIXED, correctly and test-first -- but the resulting
exact wl_stanford differential is a NO-GO on wall-clock grounds, not correctness  **[FIX +
reported NO-GO, core change made]**

**Claas's own proposal, assessed and disproven empirically before building anything.**
Claas: ad6 already has cycle-detection machinery (`InstantiateCycle`/`_CreateCycle`) -- reuse
it, negated, baked into the base model. Checked both directions on the exact
`testCycleReachabilityIsUnsoundWithoutRealOrigin` fixture: **unnegated**, `_CreateCycle`
unconditionally forbids any edge into a node with zero outgoing edges -- which is every real
ACCEPT/DROP/probe node, so it also kills `entry -> unrelated_sink`'s genuine one-hop path
(confirmed: goes UNSAT). **Negated**, the formula reduces algebraically to "some fired edge
leads to a dead end" -- true of essentially every real satisfying assignment, spurious or
not (a genuine path also ends at a real sink), so it has zero discriminating power; worse,
mechanically, negating a conjunction of `_CreateCycle`'s own implications produces a
disjunction-of-conjunctions, which isn't CNF and which `SATUtils.ConvertToCNF`'s pipeline
can't consume without genuine Tseitin machinery it doesn't have -- confirmed by trying it
and hitting exactly that exception. Conclusion right, exact form wrong: `_CreateCycle`'s
own idea (a formula over the fired-transition graph) is the right direction, but a single
STATIC clause can't express "the witness the solver actually picked must be acyclic" --
that's a property of a concrete model, not the symbolic formula.

**Fix attempt 1 (CEGAR, `Instantiator.SolveGroundedEndToEnd`): solve, walk the concrete
model's fired transitions from Source, accept only if Destination is genuinely reached;
else block and re-solve.** Proven correct test-first
(`testSolveGroundedEndToEndRejectsUngroundedCycleWitness`: rejects the floating cycle,
accepts a direct path, accepts a genuine multi-hop path INTO the cycle from a real origin).
Profiled on a real 3-router wl_stanford slice: a single genuinely-unreachable pair needed
**117 iterations, ~45s** -- because the naive blocking clause (`_BlockWitness`, negating
EVERY fired transition) is hyper-specific to one exact model, so the solver kept
rediscovering trivial variants of the same floating loop with different irrelevant bits set
elsewhere. **Refinement attempt (`_BackwardSupport`): shrink the blocking clause to just
Destination's own backward-true-closure.** Correct and test-first
(`testBackwardSupportRestrictsBlockingToDestinationsOwnClosure`) but **empirically found
to help ~0%**: profiling showed the closure was 1,066 of 1,067 fired
transitions -- essentially everything -- because a table's fallthrough chain backward-
connects almost the whole table to any exit point once ANY real redundant link loops back to
that device. Real backbone topologies are exactly this case by design (that's what
redundant links are FOR), so "shrink to the closure" barely shrinks anything here.

**Fix attempt 2 (static rank/distance encoding, `Instantiator._CreateAcyclicConstraints`):
give every node a brand-new bounded binary "rank" field with no other role in the model, and
assert for EVERY edge that firing it requires Rank(Target) > Rank(Node).** Unlike
`_CreateCycle`'s negation, this has no structural escape hatch: a cycle of simultaneously-
true edges forces `Rank(A)>Rank(B)>Rank(C)>Rank(A)`, a numeric contradiction regardless of
any node's actual value -- so the WHOLE cycle's simultaneous-truth becomes outright UNSAT in
the base model itself, no query-side change, no CEGAR needed. Proven test-first on the
synthetic fixture with a PLAIN `solver.Solve` (no CEGAR at all) --
`testAcyclicRankConstraintRejectsFloatingCycleStatically`. **Bug found and fixed on the way,
by empirical isolation, not a hand-trace:** the natural encoding (`AuxVar <->
composite_formula`, using `XMLUtils.equality()`) produces a MALFORMED, non-CNF result
(a disjunction with a raw nested conjunction inside it) whenever that equality is nested
inside another equality -- `SATUtils._ResolveConstants`'s general (neither-operand-constant)
branch only produces a correct result when it's the OUTERMOST formula; nested, the inner
equality replaces itself in-place *while the outer equality's own child-iteration is still in
progress*, so the substructure never gets its own resolution pass, and the outer equality's
branch then deepcopies that still-composite operand straight into a disjunction. Fixed by
switching every eq_i/gt_i definition to a ONE-DIRECTIONAL implication
(`aux_var -> real_condition`, the same `implication()`+`conjunction()`-of-hand-built-flat-
disjunctions shape `_ConvertNodesToImplications`/`_CreateMutationConstraints` already use
safely) -- sound because eq_i/gt_i are brand-new variables with no other role, so the solver
already has full freedom to set one true whenever it ALSO picks bit values that satisfy it
(exactly what happens while constructing a genuinely increasing rank for a real witness); no
reverse direction is needed to prevent the one thing that matters, a gt_i true WITHOUT the
real bits agreeing. **But building this for EVERY edge of the whole graph measured ~425k
extra clauses for just 3 routers** (Width sized off the WHOLE node count) -- ~84s extra
build, ~41-154s extra solve for one previously-117-iteration query (MiniSAT vs pycosat),
worse in absolute terms than the CEGAR blowup it replaced.

**Fix attempt 3 (SCC-scoping, `Instantiator._ComputeSCCs`): only edges with both endpoints
in the SAME non-trivial strongly-connected component can ever be part of a cycle -- by
definition of what an SCC is -- so restrict the (expensive) rank comparator to just those
edges, and size `Width` off the largest cyclic SCC instead of the whole graph.** Kosaraju's
algorithm, iterative (no recursion-depth risk at real scale), test-first
(`testComputeSCCsFindsOnlyGenuineCyclesNotLongAcyclicChains`: a genuine 3-cycle and a
1-node self-loop are found non-trivial, a long acyclic chain is not merged into either;
`testAcyclicRankConstraintScopesToNonTrivialSCCsOnly`: the generated constraints never
mention a node that's only ever on an acyclic chain). Correct, and cut the 3-router slice's
extra clauses ~425k -> ~242k (~43%) -- but **far short of the hoped-for order of magnitude**,
because the non-trivial SCC turned out to contain **1,914 of 2,220 nodes (86%)** even for
just 3 routers: a backbone router's own FIB table is a straight fallthrough chain on its own,
but ANY genuine redundant loop back to that router makes its first rule reachable from its
last (via the loop) and its last already reachable from its first (via the ordinary
fallthrough), pulling the device's ENTIRE table into the SAME SCC. Real backbone networks
are built with redundant links for resilience, so this isn't a corner case -- it's the norm
for the routers that matter to this benchmark.

**Fix attempt 4, the one that shipped (lazy/hybrid, `Instantiator.SolveAcyclicEndToEnd`,
Claas's own direction after attempts 1-3): try a plain solve first, accept immediately if
grounded or outright UNSAT, and only lazily build (once per Kripke, cached via a `Cache`
dict the caller owns) + apply the SCC-scoped rank constraints if THAT witness turns out
ungrounded.** Correct test-first: fast path never touches the expensive machinery
(`testSolveAcyclicEndToEndTakesFastPathWhenAlreadyGrounded` -- asserts the Cache stays
EMPTY); escalation builds once and is reused, not rebuilt, across every later query
(`testSolveAcyclicEndToEndEscalatesOnlyOnceAndCachesAcrossQueries`, identity-checked); a
`Stats` output dict reports whether THIS SPECIFIC call escalated (bare cache-membership
can't distinguish "this query escalated" from "cache is warm from an earlier query" --
`testSolveAcyclicEndToEndReportsEscalationPerQueryViaStats`). `favemodel.instantiate_base`
no longer bakes the rank constraints in at all (moved from always-on to fully lazy);
`fave_bridge.py`'s one query call site (shared by every ad6 benchmark) now calls
`SolveAcyclicEndToEnd` with one `Cache` dict built once outside the query loop. **Verified
zero cost for every acyclic benchmark**: wl_ifi (289 queries), wl_up, wl_ifi_stateful,
wl_stanford's own B0 N=2 slice -- all 27 fave-side tests green, and a live progress trace
on wl_ifi confirmed literally every one of its 289 queries takes the fast path (as expected
-- it has no cycles to escalate for).

**Instrumentation added for future long runs, since none existed and it was needed
immediately:** `fave_bridge.py` gained `AD6_BRIDGE_PROGRESS=1` (one line per query: index/
total, source->probe, result, fast-path/escalated tag, elapsed seconds) and
`AD6_BRIDGE_PROGRESS_FILE=<path>` (line-buffered to a REAL file, `tail -f`-able live --
necessary because `Ad6Adapter.check_compliance` invokes this whole script via
`subprocess.run(..., stderr=subprocess.PIPE)`, which is only readable by the parent once the
entire, possibly many-hour, subprocess has already exited).

**The real-scale result, measured, not projected:** with progress logging on, a full,
uninstrumented-nothing-held-back run of the real 256-query, 16-router differential was
given a 6-HOUR budget. It did not finish. **74/256 queries (28.9%) completed**; 40 of those
(54%) needed escalation, at costs ranging **7.7s to 2,923s** (summing to ~21,474s -- ~99.4%
of the whole 6-hour budget was consumed by escalated solves, fast-path queries contributed
under a minute total). No crashes, no malformed CNF, every completed query returned a clean
answer -- the correctness work held up under real, sustained load, not just synthetic
fixtures. **PRIMARY finding, directly observed, high confidence: this differential does not
complete within 6 hours.** A naive linear extrapolation of the observed 54%-escalation-rate/
~537s-average puts a full run at roughly **20-21 hours** -- reported as a SECONDARY,
explicitly LOWER-confidence figure, since it is an extrapolation from a 29%-complete sample,
not an independent measurement.

**Decision (Claas): treat the 6-hour non-completion itself as the reportable NO-GO result
for the tool-comparison writeup, rather than re-running to actual completion.** "Revealing
the inability to scale is a genuine outcome" for a benchmark comparing a generic SAT/QBF
model checker against specialized engines. `fave/test/test_ad6_wl_stanford.py`'s
`test_reachability_matches_netplumber` is now SKIPPED BY DEFAULT (opt in with
`AD6_STANFORD_FULL_DIFFERENTIAL=1`, plus a generous external timeout) rather than left to
hang for hours in a normal test run -- a deliberately SEPARATE env var from
`FAVE_REQUIRE_BACKENDS`/`require_or_skip`'s "required" mode, so CI's backend-required tier
can never be accidentally forced into a many-hour run.

**What ships and is kept:** the correctness fix itself (`SolveGroundedEndToEnd`,
`_CreateAcyclicConstraints`, `_ComputeSCCs`, `SolveAcyclicEndToEnd`) is real, sound, test-
first, and is now ad6's production query path for every benchmark through this bridge --
the underlying reachability-unsoundness-on-cycles bug (item 19) IS fixed, generically, for
ANY TOPOLOGY, cyclic or acyclic, on the `InstantiateEndToEnd`/`SolveAcyclicEndToEnd`
primitive `fave_bridge.py` actually uses -- even though the resulting EXACT full
differential is impractically slow at Stanford's real scale. **Scope caveat, found by a
parallel session (`AD6_ENCODING_PLAN.md` §2.4, 2026-08-24) working the same root cause
from the 2015 paper's own formalization inward, not by this session:** the SAME
grounding gap is independently CONFIRMED to also affect `InstantiateReach`/
`InstantiateShadow` (ad6's own native anomaly-detection primitives, unrelated to the
FaVe bridge) and structurally suspected (not yet empirically confirmed) in
`InstantiateCross` -- neither is touched by this fix. `InstantiateCycle` is confirmed
SAFE (forward-anchored at real init edges, a structurally different and sound
construction). "Fixed, generically, for any topology" above means "for every topology
this ONE primitive can be asked about" -- not "every ad6 reachability-style primitive is
now sound." **No regression:** `ad6 make test` (10 suites, now including
`testAcyclicRankConstraintRejectsFloatingCycleStatically`,
`testComputeSCCsFindsOnlyGenuineCyclesNotLongAcyclicChains`,
`testAcyclicRankConstraintScopesToNonTrivialSCCsOnly`,
`testSolveAcyclicEndToEndTakesFastPathWhenAlreadyGrounded`,
`testSolveAcyclicEndToEndEscalatesOnlyOnceAndCachesAcrossQueries`,
`testSolveAcyclicEndToEndReportsEscalationPerQueryViaStats`) and every pre-existing
fave-side ad6 test (27/27) stay green. Full details: `AD6_PLAN.md` §5.4.
