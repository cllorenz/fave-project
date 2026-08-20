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
