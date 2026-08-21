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
