# Investigation of the campaign's disagreements

Owner's instruction (2026-10-03): drill into the differences; fix what is
straightforward, test it, re-run the affected cells; where there is no easy
fix, describe the problem and set out the options with their trade-offs.

Started during the campaign rather than after it, in the wall-clock
`wl_i2_ad6` is burning, and **restricted to work that does not contend** —
reading code and artifacts already on disk. §6 forbids running a cell beside a
measured one. Everything needing a run is queued below.

---

## F1 — `wl_example`: NDD alone fails `source.office → probe.internet`

### What is established

**The model handed to each engine is identical.** All five `wl_example` cells
record `allow_out_iface: True` and emit the `-o` warning exactly once, and the
accommodation is applied in `iptables/generator.py:generate()` — on the FaVe
side, once, before any backend sees a rule. So this is not a case of two
engines being asked different questions.

**The disagreement is one check of ten**, and the other nine agree across
NetPlumber, NDD, VeriFlow-FR 4+10, `vf-plain` and ad6:

    [3] s=source.office && EF p=probe.internet        ← NDD says NOT reached

### Three hypotheses, all refuted from data already on disk

1. **"NDD mishandles checks with no field constraint."** Check 3 is the only
   unconstrained check in `wl_example`. *Refuted:* `wl_stanford` is **240/240**
   unconstrained and `wl_i2` **72/72**, and NDD agrees with NetPlumber exactly
   on both (75/240, 11/72).
2. **"NDD mishandles universal probes."** `probe.internet` is `wl_example`'s
   only universal probe; the other two are existential. *Refuted:* `wl_ifi`'s
   probes are **17/17 universal** and NDD agrees there (27/299).
3. **"The engines were given different `-o` treatment."** *Refuted:* identical
   `allow_out_iface` and identical warning counts across all five cells.

### What is distinctive, and the live hypothesis

Check 3 is **the only check in the workload whose satisfaction depends on the
rule whose `-o` match was stripped**:

    ip6tables -A FORWARD -o 1 -s 2001:db8::200/120 -j ACCEPT

With `-o 1` modelled as no constraint this reads "accept anything from the
office subnet", which is what makes `office → internet` reachable for the other
four engines. Every other check is carried by a rule that never had an `-o`:
the `ESTABLISHED` accept (checks 0, 6, 8), the `--dport 80` accept (2, 4) and
the `--dport 22` accept (5).

Reaching `probe.internet` from `office` also needs the **default route** —
`pgf` priority 65535, empty match, `fd=pgf.1` — because the destination is the
complement of the two /120s. `office → dmz` (checks 4, 5, which NDD passes)
uses the specific route instead.

So two candidates remain, and they are distinguishable by experiment:

* **H4** — NDD mis-handles the rule left behind when the `-o` match is removed
  (an accept whose match set is wider than any other rule's).
* **H5** — NDD mis-handles the lowest-priority default route with an empty
  match, i.e. the complement set routed to `pgf.1`.

H5 has a problem already visible: check 6 (`source.dmz → probe.internet`,
`related:1`) also needs that default route and NDD **passes** it. That does not
kill H5 — the arriving packet set differs — but it makes H4 the better bet.

### The experiments that settle it — QUEUED, not run

Each needs a backend run and so waits for the campaign:

1. **`wl_example` × NDD with `FAVE_ALLOW_OUT_IFACE` unset.** If the `-o` rule
   is then refused or kept rather than widened, and the disagreement moves,
   H4 is confirmed and the fault is in what NDD does with the widened rule.
2. **`wl_example` × BDD-APKeep.** BDD and NDD are forks of *different*
   upstreams (`7b71bff4` and `c8414b43`). BDD agreeing with NetPlumber puts the
   fault in NDD specifically; BDD agreeing with NDD puts it in the shared
   APKeep-side adapter, which is a different repair. **This cell is already in
   the phase A queue** and will answer the question for free.
3. A minimal two-rule, two-route reduction, as a regression test, once the
   mechanism is known.

### Why no fix is proposed yet

Nothing here identifies a defective line. A "fix" chosen now would be a guess
at which of two engines is wrong, on a workload with no oracle — and F4-R is
the standing warning against reading a direction out of too few engines.

---

## F6 — `wl_up`: VeriFlow-FR reports 28 diagonal violations

Mechanically characterised already: **28 of 28 are `source.X → probe.X`, zero
off-diagonal**. A forwarding defect would not land only on the diagonal.

Whether a filled diagonal is a violation at all is a **declared option of the
check generator** — `_convert_policy_to_checks` takes `--roles` ("a role whose
single node stands for a subnet loses its self-check") and `--strict` ("which
decides whether a filled diagonal means anything"), per commit `381caf5e`.

So the question is not "which engine is wrong" but **"what does a self-check
mean, and did `wl_up`'s check set intend to contain 28 of them"** — and that
is the owner's to answer, because both readings are defensible:

* if the diagonal is meaningful, VeriFlow-FR is reporting a real
  self-reachability the other two engines miss;
* if it is not, the diagonal should never have entered `wl_up`'s check set, and
  NetPlumber and NDD pass those 28 by accident rather than by analysis.

Options are set out in full below once the campaign's remaining `wl_up` cells
(ad6, bdd) are in — a third and fourth engine on the same 28 checks changes
which reading is cheap to defend.

---

## F3 — `wl_cloud` × VeriFlow-FR: `not a prefix: x1xxxxxxxxxxxxxx`

### The refusal is correct and should not be "fixed"

`veriflow_fr/src/veriflow.cc:54`, in `prefix_to_interval`: a ternary string
with a concrete bit *after* a wildcard run is not a prefix, therefore not an
interval, and is refused. `literature_unit.cc` pins it deliberately — *"A
ternary value that is not a prefix is no interval, and is refused."*

That is right, and it is the behaviour a faithful reimplementation should have.
VeriFlow-FR is interval-based by construction; making it accept this value
would mean approximating, and an approximation here would be **APKeep's idea,
not VeriFlow's** — which `VERIFLOW_PLAN.md` §4.6 already refuses to do for
exactly this reason. **So there is no fix to apply on the engine side.** The
open question is where the value comes from.

### What the value is

16 bits wide, and `packet.ether.vlan` is the one 16-bit field at offset 0 of
`wl_cloud`'s mapping (`cloud_tf.py` `CLOUD_MAPPING` / `_FIELD_SIZES`,
`netplumber/mapping.py`). The shape — one concrete bit at position 1, every
other bit wildcard — is a **single-bit test inside the VLAN field**, not a VLAN
id, which would be a concrete value in the low 12 bits.

`wl_cloud`'s source is SMT-LIB bitvector relations (`cloud-tf/*.smt2`,
`(_ BitVec 16)` for the VLAN slot), where a single-bit test is the natural
thing to write and converts straight to this mask.

### Narrowing, from disk

The two candidate origins in F3 are distinguishable, and one side is already
cleared. Scanning `wl_cloud`'s generated `routes.json`, `topology.json` and
`sources.json` with the survey's own `classify_vector` finds **no ternary value
at all**. Ingress demultiplexing (`CLOUD_BENCH_PLAN.md` §2.8) is a
topology/source-side encoding, so had it manufactured this value it would be
visible there. It is not.

That leaves the rules derived from the transfer functions at run time, which
are not on disk — so **the evidence so far favours "the value is in the
workload", and therefore that `feature_survey`'s "no rule in the suite carries
a ternary value" is over-generalised** rather than that an adapter invented it.

Not yet conclusive: confirming it means generating `wl_cloud`'s rules, which is
a run. **Queued:** `python3 bench/feature_survey.py --bench bench/wl_cloud`
after the campaign, which answers it directly — the survey's classifier already
labels this exact string `ternary`, so if the rules carry it the survey will
say so.

### Why this matters beyond one cell

The survey's conclusion is load-bearing: item 31 cites it as what makes
range-based engines comparable on this suite at all. If `wl_cloud` carries a
ternary value, then VeriFlow-FR's refusal is a **tool limitation honestly
reported** and belongs in `ACCOMMODATIONS.md` as such — `wl_cloud × vf` is a
cell no range-based engine can have, which is a finding about the workload and
the tool family, not a defect in either.

---

# F1 — SOLVED. Root cause, and a fix that is straightforward

## The decisive cell

`wl_example × BDD` landed and settles it:

| engine | violations of 10 | family |
|---|---|---|
| NetPlumber | 0 | — |
| VeriFlow-FR 4+10 | 0 | — |
| `vf-plain` | 0 | — |
| ad6 | 0 | — |
| **NDD-APKeep** | **1** | APKeep |
| **BDD-APKeep** | **1** | APKeep |

BDD and NDD report the *same* line. They are forks of **different upstream
repositories** (`XJTU-NetVerify/apkeep 7b71bff4` and `XJTU-NetVerify/NDD
c8414b43`), so what they share is not engine code — it is **FaVe's own APKeep
adapter**, `fave/apkeep/adapter.py`. That moves the fault to first-party code.

## The root cause

Two layers of FaVe implement **opposite** accommodations for the same declared
infidelity.

**Layer 1 — `iptables/generator.py`.** `-o` maps to an `out_port` *match* field
(line 69, `"o": "out_port"`). The `-o` match is refused outright unless
`FAVE_ALLOW_OUT_IFACE` is set, and the refusal message states the semantics
precisely:

> FaVe's packet filter runs its filter chains BEFORE routing
> (`forward_filter → routing → post_routing`), so `out_port` is still unset
> when the rule is evaluated and is then overwritten by the routing table —
> **the match would constrain nothing**, silently, and the resulting error
> would **over-PERMIT for `-j ACCEPT`** and over-RESTRICT for `-j DROP`.

So the declared behaviour under the accommodation is: **the `-o` match is
inert; the rule applies to everything; an ACCEPT over-permits.** NetPlumber,
VeriFlow-FR and ad6 all consume the model that way, which is why all three
answer "reaches".

**Layer 2 — `apkeep/adapter.py`, in `emit()` (line ~2195).**

    if handle_quals and t[8] is not None:   # out_port-qualified -> skip
        continue

`t[8]` is `out_qual`, set from that same `out_port` match (built at line 1089).
The adapter **drops the rule entirely**, reasoning that it is "redundant with
routing: their dst never egresses the qualified port".

That reasoning would hold if `out_port` were a constraint routing enforces. In
FaVe's filter-before-routing pipeline it is not — layer 1 says so explicitly.
**Dropping an `-o`-qualified ACCEPT is over-RESTRICTIVE, which is the error the
generator attributes to DROP, not ACCEPT.** The two layers are not merely
different; they are opposite in both directions.

## Why it produces exactly this violation

`wl_example`'s `pgf` ruleset:

    ip6tables -P FORWARD DROP
    …
    ip6tables -A FORWARD -o 1 -s 2001:db8::200/120 -j ACCEPT   ← dropped by the adapter

That is the **only** rule permitting the office subnet to reach anything beyond
the two internal /120s. With it skipped, the `-P FORWARD DROP` policy stands and
`source.office` cannot reach `probe.internet` — the exact line both APKeep
engines report. Every other check in the workload is carried by a rule that
never had an `-o` (the `ESTABLISHED` accept, the `--dport 80` accept, the
`--dport 22` accept), which is why only one check of ten moves.

## The fix

Under the accommodation an `-o`-qualified filter rule must be emitted
**port-agnostically** — the qualifier treated as inert — rather than skipped.
That is what makes APKeep agree with the other three engines and with FaVe's
own stated semantics. The generator already refuses `-o` unless the
accommodation is active, so every such rule reaching the adapter is by
construction under it.

**NOT APPLIED YET, deliberately.** The BDD block of phase A is still running,
and changing the adapter now would leave the campaign's APKeep cells measured
half on one semantics and half on the other. The patch is applied in the
investigation slot, after phase A closes.

## What must be re-run, and the risk to watch

The affected cells are APKeep × the workloads carrying `-o` — `wl_example`,
`wl_up`, `wl_tum` (the generator's own comment names exactly these three):

    wl_example_ndd  wl_example_bdd  wl_up_ndd  wl_up_bdd  wl_tum_ndd  wl_tum_bdd

All are cheap (seconds to ~11 min). **The risk worth stating in advance:**
`wl_up` currently has NetPlumber and NDD *agreeing* at 0 violations while the
adapter skips its `-o` rules. Emitting those rules port-agnostically changes
what APKeep sees on `wl_up`, and it is not obvious a priori that agreement
survives — if `wl_up`'s `-o` rules are DROPs, applying them to everything is
the over-restriction the generator warns of, and NDD could move away from
NetPlumber. **Declared before the re-run:** the fix is judged by whether APKeep
matches the other engines across all three workloads, not by `wl_example`
alone. If `wl_up` breaks, the right conclusion is that item 13a's accommodation
is wrong for DROP rules too — not that this patch should be reverted to hide it.

---

# F1 — the "solution" above is WRONG. Corrected by experiment, 2026-10-05

**The section headed "F1 — SOLVED" is refuted.** The fix it proposed was
applied, tested and reverted. It did not work, and it did damage:

| cell | before | after the patch | other engines |
|---|---:|---:|---|
| `wl_example_ndd` | 1/10 | **1/10 — unchanged** | np/vf/ad6: 0/10 |
| `wl_example_bdd` | 1/10 | **1/10 — unchanged** | np/vf/ad6: 0/10 |
| `wl_up_ndd` | 0/18811 | **3025/18811** | np: 0/18811 |
| `wl_up_bdd` | 0/18811 | **3025/18811** | np: 0/18811 |
| `wl_tum_ndd` | 0/— | 0/— unchanged | — |
| `wl_tum_bdd` | 0/— | 0/— unchanged | — |

So the `out_port`-qualified skip at `apkeep/adapter.py:2195` is **not the cause
of F1**, and the patch is reverted.

### What the failed experiment nevertheless established

It was not wasted; it bought three facts that narrow the problem.

1. **The missing ACCEPT is not why `office` cannot reach `internet`.** Emitting
   that rule port-agnostically put it back into APKeep's model and the verdict
   did **not** move. Whatever blocks the path in the APKeep model is downstream
   of the filter rule — the routing or the probe attachment, not the permit.
   This refutes a hypothesis that looked airtight on a reading of the code.
2. **The skip is load-bearing, and for a reason nobody had written down.**
   `wl_up`'s two `-o` rules are `-o 1 -d 2001:db8:abc::0/48 -j DROP`, and that
   /48 is `wl_up`'s **entire address space** (136 of its 137 sources). They are
   anti-spoofing: *do not emit traffic claiming our own prefix out of the
   uplink.* Strip the qualifier and they read "drop everything addressed to
   us", which is the 3025 violations. Any future change here must keep that
   case working; the skip's comment ("redundant with routing") does not say so.
3. **ACCEPT and DROP need opposite treatments.** Skipping is wrong for an
   `-o` ACCEPT (it removes a permit) and right-by-accident for an `-o` DROP
   (it drops a restriction that would otherwise over-apply). No single rule —
   neither "skip" nor "ignore the qualifier" — is correct for both, which is
   why there is no one-line fix here.

### A separate finding this turned up: item 13a's premise looks wrong

`iptables/generator.py`'s `OutInterfaceUnsupported` message justifies the whole
accommodation by asserting that FaVe evaluates filter chains before routing, so
`out_port` "is still unset when the rule is evaluated and is then overwritten by
the routing table — the match would constrain nothing".

If that were true of NetPlumber, NetPlumber would over-restrict on `wl_up`
exactly as the patch did. **It does not.** NetPlumber answers 0 violations on
`wl_up` (anti-spoofing does not touch internal traffic) *and* reports
`office → internet` as reachable on `wl_example` (the ACCEPT applies). It gets
both the DROP and the ACCEPT case right, which is not the behaviour of an
engine for which the match "constrains nothing".

So item 13a's stated justification does not describe FaVe's own primary engine.
That matters beyond this bug: the accommodation is declared in
`ACCOMMODATIONS.md` terms as a known infidelity affecting **all** backends, and
on this evidence it is a limitation of the **APKeep adapter alone**. The three
workloads it is invoked for (`wl_example`, `wl_up`, `wl_tum`) may not need it at
all on NetPlumber, VeriFlow-FR or ad6.

### Status

**F1 is OPEN. Root cause unknown.** What is known: it is in the shared APKeep
adapter (BDD and NDD, forks of different upstreams, agree exactly); it is not
the unconstrained check, not the universal probe, not a differing
accommodation flag, and not the `out_port` skip. The next candidate — supported
by fact 1 above but **not tested** — is the FIB side: `wl_example`'s default
route (`pgf`, priority 65535, empty match, `fd=pgf.1`) is what carries
`office → internet`, and `office → dmz`, which APKeep gets right, uses a
specific route instead.

---

# Options, per finding

Nothing below is applied. Each option is stated with what it costs and what it
gives up, and every one of them is the owner's call because each trades
fidelity against comparability in a different place.

## F1 — APKeep disagrees with four engines on `wl_example` (root cause OPEN)

**O1a — Finish the diagnosis before deciding anything.** Test the FIB
hypothesis: dump what the adapter emits for `wl_example` (`+ fib` / `+ filter`
rule strings) and check whether the default route — `pgf` priority 65535, empty
match, `fd=pgf.1` — reaches APKeep at all. Cost: hours, no runs of consequence.
*For:* every other option is a guess until this is known, and this session has
already spent one wrong guess. *Against:* nothing, except that it defers the
decision.
**Recommended. It is cheap and it is the only option that cannot be wrong.**

**O1b — Exclude `wl_example` from the APKeep columns of the comparison.** Cite
it as a known open disagreement. *For:* honest, costs nothing, and the workload
is a toy whose purpose is illustration. *Against:* the disagreement is almost
certainly not confined to `wl_example` — it is the *smallest* workload, which is
why it is visible there; the same defect on `wl_up` or `wl_cloud` would be one
line among thousands. Suppressing the one place it is tractable is the opposite
of what the suite is for.

**O1c — Treat the majority (4 engines) as the verdict and mark APKeep wrong.**
*For:* it is what the evidence says, and it keeps the table complete.
*Against:* **a majority is not an oracle** — F4-R is this campaign's own lesson
about reading a direction from too few engines, and `wl_example` has no oracle
at all. It would also publish "APKeep is wrong" without knowing why, which is
exactly the claim a reviewer will ask about.

## F1-adjacent — item 13a's premise appears false for NetPlumber

**O13a-1 — Re-derive the accommodation per backend.** Test whether `-o` is
actually inexpressible on NetPlumber, VeriFlow-FR and ad6, rather than assuming
it from the generator's comment. If it is expressible, `FAVE_ALLOW_OUT_IFACE`
should not be required for them, and `ACCOMMODATIONS.md` should record a
**per-backend** limitation instead of a suite-wide one. Cost: small — three
workloads, cheap cells. *For:* the current declaration over-states the
infidelity, and item 31's whole point is that an accommodation is declared
accurately or not at all. *Against:* it reopens a decision that was closed, and
the three affected workloads' numbers would need re-stating.
**Recommended; this is the most under-valued finding of the investigation.**

**O13a-2 — Leave it, and note the discrepancy.** *For:* zero cost. *Against:*
`ACCOMMODATIONS.md` then carries a declared infidelity whose justification is
contradicted by the engine it is declared against, which is worse than an
undeclared one — a reader who checks it finds it wrong.

## F3 — `wl_cloud × VeriFlow-FR`: a ternary value it cannot represent

**There is no fix, and that is the finding.** The refusal is correct and
deliberate (`veriflow.cc:54`, pinned by `literature_unit.cc`): a ternary value
that is not a prefix is not an interval. Making it accept would be
approximating, which is APKeep's idea and not VeriFlow's — `VERIFLOW_PLAN.md`
§4.6 already refuses that trade.

**O3a — Declare `wl_cloud × vf` an empty cell with a stated reason**, in
`ACCOMMODATIONS.md`, as a *reducing* limitation of range-based engines.
*For:* truthful, and a genuine comparative result — "this workload is outside
the model class of interval-based verifiers" is a finding about the tool
family, not a failure of the harness. *Against:* leaves a hole in the matrix.
**Recommended.**

**O3b — First settle whether the value is workload content or adapter-made.**
Run `python3 bench/feature_survey.py --bench bench/wl_cloud`. Minutes. The
on-disk evidence (no ternary in the generated routes, topology or sources)
already points at workload content, which would mean `feature_survey`'s "no
rule in the suite carries a ternary value" is over-generalised and that
item 31 leans on an over-generalised finding. *For:* O3a's wording depends on
the answer. *Against:* none. **Do this before O3a.**

## F6 — VeriFlow-FR reports 28 diagonal self-reachability violations on `wl_up`

All 28 are `source.X → probe.X`, zero off-diagonal, so this is a semantic
disagreement about self-reachability, not forwarding.

**O6a — Decide the diagonal at the check generator and regenerate.**
`_convert_policy_to_checks` already has `--strict`, which exists to decide
"whether a filled diagonal means anything". Settle it there and the question
stops being per-engine. *For:* fixes the class, not the instance; the option
already exists. *Against:* changes `wl_up`'s check count again — and `wl_up`'s
denominator has already moved once (11,902 → 18,811, F5), so every figure
quoting it moves a second time. **Recommended, but it must be done before any
`wl_up` number is published, not after.**

**O6b — Declare VeriFlow-FR's self-reachability semantics in
`ACCOMMODATIONS.md`** and leave the check set alone. *For:* cheapest; no
denominator churn. *Against:* it records a disagreement as a property of one
tool when it is really an unanswered question about the workload — and the
other two engines pass those 28 checks by not asking, rather than by analysis.

**O6c — Get a third and fourth opinion first.** ad6 and BDD both ran `wl_up` in
phase A; their verdicts on those 28 checks are already on disk and were not
examined. *For:* free, and it decides whether VeriFlow-FR is the outlier or the
only engine answering the question. *Against:* none.
**Do this first — it is free and it may settle O6a vs O6b outright.**

## F7 — ad6 answered `wl_cloud`, which §5.1 says it refuses

**O7a — Correct §5.1's matrix and re-check §1.7.2's structural claim.** The
matrix cell says "refuses (structural)"; ad6 answered, agreeing with NDD
line-for-line. *For:* a documented refusal that does not happen is exactly the
claim a reviewer checks, and the agreement suggests nothing was being protected
against. *Against:* requires finding out whether §1.7.2's reason was fixed or
mis-scoped — archaeology.
**Recommended; the matrix is cited and is currently wrong.**

---

# The two free options, executed 2026-10-05

## O6c — done. VeriFlow-FR is alone, 1 against 4.

ad6's and BDD's `wl_up` verdicts were already on disk and unexamined:

| `wl_up` (18,811 checks) | violations | diagonal | off-diagonal |
|---|---:|---:|---:|
| NetPlumber | 0 | 0 | 0 |
| NDD-APKeep | 0 | 0 | 0 |
| BDD-APKeep | 0 | 0 | 0 |
| ad6 | 0 | 0 | 0 |
| **VeriFlow-FR 4+10** | **28** | **28** | **0** |

Four engines across three independent families — header-space (NetPlumber),
APKeep (BDD and NDD), and SAT (ad6) — report none. VeriFlow-FR alone reports
28, all diagonal.

**This shifts the recommendation from O6a to O6b.** With only NetPlumber and
NDD it was open whether VeriFlow-FR was the one engine *asking* the question;
at 1-against-4 the likelier reading is that **VeriFlow-FR's self-reachability
semantics differ from every other engine in the suite**, which is a property of
that engine and belongs in `ACCOMMODATIONS.md`. Changing the check generator
(O6a) would move `wl_up`'s denominator a second time (F5) to accommodate one
engine's reading — a high price on thin grounds.

Stated with the caveat this campaign earned the hard way: **a majority is not
an oracle** (F4-R). Four engines agreeing is evidence, not proof. But the
asymmetry in cost between O6a and O6b is large, and the evidence now points one
way rather than being balanced.

## O3b — done, and it REVERSES this document's earlier lean on F3

`python3 bench/feature_survey.py --bench bench/wl_cloud`:

    packet.ipv4.destination   {'exact': 14, 'prefix': 1668}
    packet.ipv4.source        {'prefix': 358}
    packet.ipv6.proto         {'exact': 1131}
    packet.upper.dport        {'exact': 382}
    packet.upper.sport        {'exact': 353}

**No ternary value anywhere, and no VLAN field at all** — across all 1,741
rules and 86 tables.

Earlier in this document I wrote that the evidence "favours the value being
workload content, and therefore that `feature_survey`'s 'no rule in the suite
carries a ternary value' is over-generalised". **That was wrong**, and it was
wrong because absence from `routes.json`/`topology.json`/`sources.json` is weak
evidence where the survey is direct evidence. The survey classifies this exact
string as `ternary` and would have reported it.

So:

* `feature_survey`'s conclusion **stands** for `wl_cloud`;
* `x1xxxxxxxxxxxxxx` is **manufactured between the rules and VeriFlow-FR**, not
  present in the workload — the VLAN field does not even appear in what the
  survey records the engines as being handed;
* F3 therefore resolves to **fork-branch 2**: an adapter encoding that changes
  the *kind* of value an engine is handed, which `ACCOMMODATIONS.md` requires to
  be declared with its cost (item 31's rule 2: "Adapter encodings are
  preprocessing too").

**This also downgrades O3a.** `wl_cloud × vf` is *not* "a workload outside the
model class of interval-based verifiers" — the workload is pure prefix/exact.
It is **FaVe handing VeriFlow-FR a value the workload never contained**, which
is a defect in FaVe's encoding and is very likely fixable. The next step is to
find what inserts a VLAN slot into a workload that has no VLANs; `wl_cloud`'s
mapping does carry `packet.ether.vlan` at offset 0 (`cloud_tf.py`
`CLOUD_MAPPING`) while no rule constrains it, which is where to start.

**Revised recommendation for F3: do not declare an accommodation yet.** It
would record as a tool limitation something the evidence now says is ours.

---

# O1a — executed. The retraction was wrong; the original diagnosis stands.

Run with the FIB translation and filter emission instrumented (temporary,
env-gated, reverted afterwards; adapter is pristine).

## The default-route hypothesis is refuted

`wl_example`'s `pgf` FIB is complete, default route included:

    KEPT  pgf dst=2001:db8::100/120 egress=2 plen=120
    KEPT  pgf dst=2001:db8::200/120 egress=3 plen=120
    KEPT  pgf dst=None              egress=1 plen=0     <- the default route

So the candidate named at the end of the previous section is wrong. Routing is
not where `office → internet` is lost.

## What the emitted filter shows

`pgf.fwd`, as APKeep receives it, with the skip in place:

    accept  proto6 src=…::101 sport=80       related=1     (return HTTP)
    accept  proto6 src=…::101 sport=22 dst=…::200/120 related=1  (return SSH)
    __drop__ everything                      related=1
    accept  proto6 dst=…::101 dport=80                     (HTTP to web)
    accept  proto6 src=…::200/120 dst=…::101 dport=22      (SSH office->web)
    __drop__ everything                                    (-P FORWARD DROP)

**The `-o 1 -s 2001:db8::200/120 -j ACCEPT` is absent.** An office packet bound
for the internet matches neither `--dport` accept and falls to the final drop.
That is precisely the reported violation.

## Why the earlier experiment looked like a failure — a method error, mine

Removing the skip emits the rule at priority 9999994, above the final drop:

    accept  proto0-255 src=2001:db8::200/120 dst=any       <- the permit, restored

and the verdict count stayed at **1/10**, from which the previous section
concluded the skip was not the cause. **That conclusion was wrong**, and the
mistake is worth naming because it is the one this repo already legislates
against in another form: *I compared totals instead of lines.*

| | violation reported |
|---|---|
| skip in place (phase A) | `` `source.office` does not reach `probe.internet` `` |
| skip removed | `` `source.dmz` does not reach `probe.office` `` |

**The count is the same and the check is different.** The patch *did* fix the
violation it was aimed at. It introduced a second, unrelated one — and 1 = 1
hid the swap completely. §8.1 says "never compare totals across different query
counts"; this is the same error with the query count held constant, which makes
it harder to see, not easier.

## What actually breaks when the skip is removed

Removing it emits a *second* out-qualified rule that the ruleset does not
contain literally — a mirrored, state-related DROP, at the **highest** priority:

    OUTQUAL t0=__drop__ out_qual=1 dst=2001:db8::/32   (related=1)

This is the reverse direction FaVe synthesises for
`-A FORWARD -i 1 -s 2001:db8::0/32 -j DROP`. Emitted port-agnostically, it
drops *all* related traffic to the internal /32 — which is what fails
`source.dmz → probe.office, related:1`, and, at `wl_up`'s scale with its
anti-spoofing pair over its own /48, is the 3025 violations.

## So the real defect, stated precisely

`-o N` means "will egress interface N". FaVe evaluates filter chains **before**
routing, so at filter time the egress is unknown, and the adapter has exactly
two bad choices — drop the rule (loses an ACCEPT) or ignore the qualifier
(over-applies a DROP). **Both are wrong, which is why neither one-line change
works.**

The information needed is already in the adapter: `self._filter_fib[dev]` holds
`(dst, egress, plen)` for every route. The egress of a packet is a function of
its destination, so an `-o N`-qualified filter rule is **equivalent to the same
rule with its destination intersected with the set of prefixes that route to
port N under LPM.** For `wl_example`:

* `-o 1 -s office ACCEPT` → `src=office, dst = 0/0 minus {::100/120, ::200/120}`
  — office reaches the internet, and nothing else is permitted;
* the mirrored `-o 1 -d 2001:db8::/32 DROP` → `dst = 2001:db8::/32 minus those
  two /120s` — the internal traffic it was wrongly killing is no longer in it.

Both cases come out right from one rule, and `wl_up`'s anti-spoofing becomes
"drop traffic to our own /48 that would leave via the uplink", which is what it
means.

**This is a real fix, not a workaround, and it is not a one-liner**: it needs
LPM complement arithmetic over the FIB (subtracting more-specific prefixes from
a less-specific one), per out-qualified rule. It is tractable — the FIB is small
and already materialised — but it is a change with its own blast radius across
`wl_example`, `wl_up` and `wl_tum`, and it should be built with the minimal
`wl_example` reduction as its regression test.

**Status: F1 root cause CONFIRMED. A correct fix is designed but NOT written.**

---

# O3c — SOLVED and FIXED. It was never VLAN.

## The value is made by FaVe's own negated-condition expansion

`veriflow/translate.py`'s `expand_negated` emitted, per fixed bit of the
negated value:

    'x' * (offset + i) + flipped_bit + 'x' * rest

i.e. **wildcards, one concrete bit, wildcards**. Sliced to a 16-bit field with
the flip at index 1 that is `x1xxxxxxxxxxxxxx` — the error string exactly:

    port 332      = 0000000101001100
    bit 1 flipped = x1xxxxxxxxxxxxxx
    error string  = x1xxxxxxxxxxxxxx

**My VLAN identification earlier in this document was wrong.** 16 bits matched
`packet.ether.vlan` and I stopped there; `packet.upper.dport` is also 16 bits,
and it is the one actually involved. The coincidence of width was the whole
basis of that reading, which is not enough.

`wl_cloud` is the **only** workload in the suite with negated field conditions
— 8 checks over `port` and `protocol`; every other workload has zero. That is
why only `wl_cloud × vf` died, and why the defect survived this long.

## The fix

The pieces now fix the earlier bits — the standard complement decomposition:

| | old | new |
|---|---|---|
| piece | `{w : w[i] ≠ v[i]}` | `{w : w[0..i-1] = v[0..i-1], w[i] ≠ v[i]}` |
| union | complement | complement (same) |
| prefixes? | **no** | **yes** |
| disjoint? | no (overlapping, so ECs are double-counted) | **yes** |

Verified algebraically on a 4-bit case: union equals the complement, pieces are
pairwise disjoint, every piece is a prefix. `fast` 864 passed, `integration`
PASSED including every differential.

`test_a_negated_field_expands_to_single_bit_sets` pinned the old strings and is
replaced by `..._expands_to_prefixes`, which pins the three properties instead
— union, disjointness, prefix-ness — because the strings are what went wrong.

## The result: both cells recovered

| `wl_cloud × veriflow` | before | after |
|---|---|---|
| `vf` (4+10) | `status: error`, no verdict | **57/71, `verdict_valid`, 2.39 s** |
| `vf-plain` | `status: error`, no verdict | **57/71, `verdict_valid`, 2.24 s** |

**P9 is no longer falsified by `wl_cloud`.** It was falsified by a FaVe defect,
not by VeriFlow-FR failing to complete a workload.

## And it settles F4-R, which phase C was supposed to settle

| `wl_cloud`, 71 checks | violations |
|---|---|
| **NetPlumber** | **58** |
| NDD-APKeep | 57 |
| ad6 | 57 |
| VeriFlow-FR 4+10 | 57 |
| `vf-plain` | 57 |

VeriFlow-FR's report is **line-for-line identical to NDD's**. The one line only
NetPlumber reports:

    - `source.dc1_leaf6_host0` reaches `probe.dc0_leaf1_host1` with …

Four engines from three independent families — APKeep (NDD), SAT (ad6) and
interval/Delta-net (VeriFlow-FR) — do not find that reachability. **NetPlumber
is the outlier on `wl_cloud`, and the evidence is now much stronger than the
two-engine reading F4 got wrong.**

This is the adjudication phase C's 24-hour BDD run was scheduled to provide,
obtained instead from a 2.4-second cell, because fixing F3 unblocked the engine
that could give it. It is worth noting against §5.3's triage: the long run was
chosen as the way to settle this, and a defect fix settled it for nothing.

## What the external oracle can and cannot do here

`wl_cloud` is cited as the suite's only workload with an external oracle.
`bench/wl_cloud/oracle.json` holds **6 queries**, all sourced at the internet
(`source: 1500000`), carrying the dataset's own sat/unsat verdicts.
`dc1_leaf6_host0 → dc0_leaf1_host1` is an internal-to-internal pair and **is
not among them**. So the oracle does not adjudicate this disagreement, and the
four-to-one reading stands on engine agreement alone — which, per F4-R, is
evidence and not proof.

---

# O13a-1 — executed. `-o` is expressible on three of the four backends.

Item 13a declares `-o` unmodellable and gates it behind `FAVE_ALLOW_OUT_IFACE`
for the whole suite, justified by: *"`out_port` is still unset when the rule is
evaluated and is then overwritten by the routing table — the match would
constrain nothing."* That is a claim about every backend, and it is testable
against data the campaign already produced.

## The experiment, which the campaign already ran

The suite's two `-o` workloads carry rules of **opposite polarity**, so between
them they separate the three possible behaviours:

* `wl_example` — one `-o` **ACCEPT** (`-o 1 -s 2001:db8::200/120 -j ACCEPT`),
  the sole permit for `office → internet`;
* `wl_up` — two `-o` **DROPs** (`-o 1 -d 2001:db8:abc::0/48`) over `wl_up`'s own
  entire address space (136 of 137 sources), i.e. anti-spoofing.

Predicted signature of each behaviour:

| behaviour | `wl_example` | `wl_up`, off-diagonal |
|---|---|---|
| **skip** the `-o` rule | **1 violation** (`office → internet` lost) | 0 |
| **ignore the qualifier** (apply to all) | 0 | **thousands** (internal traffic dropped) |
| **model `-o`** | 0 | 0 |

The middle row is not a guess: removing the skip from the APKeep adapter
produced exactly that — **3025 violations of 18,811** on `wl_up`. The failed
fix is the calibration for what "the match constrains nothing" looks like.

## Observed

| engine | `wl_example` | `wl_up` | off-diagonal | behaviour |
|---|---:|---:|---:|---|
| NetPlumber | 0/10 | 0/18811 | 0 | **models `-o`** |
| ad6 | 0/10 | 0/18811 | 0 | **models `-o`** |
| VeriFlow-FR | 0/10 | 28/18811 | **0** | **models `-o`** |
| NDD-APKeep | **1/10** | 0/18811 | 0 | **skips** |
| BDD-APKeep | **1/10** | 0/18811 | 0 | **skips** |

VeriFlow-FR's 28 are all diagonal (F6) and unrelated to `-o`; its off-diagonal
count is 0, which is the figure this test reads.

NetPlumber, ad6 and VeriFlow-FR are in neither failing row: they keep the
ACCEPT (so they do not skip) and do not over-apply the DROP (so they do not
ignore the qualifier). Only one behaviour is left.

**Mechanism, for NetPlumber:** `netplumber/adapter.py` builds a rule's match
with `rvec = self._build_vector(rule.match)`, and `out_port` is a field of the
mapping like any other. So an `-o`-qualified rule constrains the `out_port`
dimension of the header space, carving out the slice that will leave by that
port rather than applying to everything or vanishing.

## What follows

1. **Item 13a's stated premise is false for three of the four backends.** It
   describes the APKeep adapter, which cannot express an `-o`-qualified filter
   rule, and generalises that to the suite.
2. **`FAVE_ALLOW_OUT_IFACE` is an opt-in to an infidelity those three do not
   have.** `iptables/generator.py` refuses `-o` *before* any backend is chosen,
   so NetPlumber, ad6 and VeriFlow-FR are made to opt into a loss of fidelity
   none of them suffers. The refusal should be **backend-conditional**, or the
   message should stop claiming the match constrains nothing.
3. **`ACCOMMODATIONS.md` currently over-states it.** Item 31's rule is that an
   accommodation is declared accurately or not at all; this one is declared
   suite-wide and is APKeep-only. A reader who checks it against NetPlumber
   finds it contradicted.
4. **It makes F1 sharper, not just differently worded.** `wl_example`'s
   disagreement is not "four engines against two on an unmodellable match" — it
   is **three engines modelling `-o` correctly and APKeep's adapter dropping the
   rule**, with the correct behaviour demonstrated three times over in the same
   campaign. The O1a design (intersect the rule's destination with the prefixes
   routing to that port) is how APKeep would join them.

**Not done here:** a purpose-built discriminating check — e.g.
`office → dmz` on a port no other rule permits, which separates "models `-o`"
from "ignores it" on `wl_example` alone. The two-workload argument above does
not need it, but it would be the cheapest single confirmation and it needs the
workload's policy changed, not just a check added.

---

# O1a — IMPLEMENTED AND VERIFIED, 2026-10-06

`_lpm_destinations` / `_restrict_dst` in `apkeep/adapter.py`: an `-o
N`-qualified filter rule is resolved against the device's FIB — restricted to
the destinations whose longest-prefix match egresses N — instead of being
skipped. Results in `../results_v5_o1afix/`.

| cell | phase A | with the fix | the other engines |
|---|---:|---:|---|
| `wl_example_ndd` | 1/10 | **0/10** | 0/10 (np, ad6, vf, vf-plain) |
| `wl_example_bdd` | 1/10 | **0/10** | 0/10 |
| `wl_up_ndd` | 0/18811 | **0/18811** | 0/18811 (np, ad6, bdd) |
| `wl_up_bdd` | 0/18811 | **0/18811** | 0/18811 |
| `wl_tum_ndd` / `_bdd` | 0/— | 0/— | unchanged (no FIB; skip stands) |

**F1 is CLOSED.** All five engine configurations now agree on `wl_example`.

**The `wl_up` row is the one that matters.** It is unchanged, and the first
attempt at this fix turned it into 3025 violations — so holding at 0 is what
separates a fix from another plausible wrong answer. `./test.sh fast` 864
passed; `FAVE_REQUIRE_BACKENDS=1 ./test.sh integration` passed, including the
cross-engine differentials on `wl_up` and `wl_ifi`.

## What this leaves open

* **The campaign's recorded `wl_example` APKeep cells are now superseded.** Six
  phase A cells were measured on the old semantics. The rest of phase A is
  unaffected — `-o` appears only in `wl_example`, `wl_up` and `wl_tum`.
* **Item 13a is now wrong in the other direction too.** O13a-1 showed its
  premise false for NetPlumber, ad6 and VeriFlow-FR; this closes the gap for
  APKeep as well. `FAVE_ALLOW_OUT_IFACE` now gates an infidelity **no backend
  has**, and the accommodation can be retired rather than re-scoped — but that
  is a decision, not a repair, and `wl_tum`'s FIB-less terminal filter is the
  one case still genuinely unresolvable.
* **`wl_tum` is untested by this.** It has no checks and no FIB, so neither the
  old path nor the new one is exercised by a verdict there.

---

# F6 — O6b's premise is WRONG. The 28 are not a VeriFlow-FR quirk.

O6b was "declare VeriFlow-FR's self-reachability semantics in
`ACCOMMODATIONS.md` and leave the check set alone". Checking what the 28 checks
actually *are*, before writing that entry, refutes it.

**`wl_up` has 130 diagonal checks, 129 of them must-NOT-reach.** VeriFlow-FR
violates **28**. A blanket "a role reaches itself" semantics would violate all
129, so this is selective, and the selection is exact:

| | min hosts in the role | role spans a subnet |
|---|---|---|
| **violated (28)** | **1** — the sole member | yes |
| unviolated (102) | 2 or 3 | yes |

**All 28 are hosts that are the sole member of a role standing for a whole
/120** — and that is not an accident of the data, it is a condition FaVe's own
check generator tests for by name. `bench/reach_csv_to_checks.py`:

    keep_self = (args.strict
                 and source_role == target_role
                 and source_role != _INTERNET
                 and len(sources) == 1 and len(targets) == 1
                 and _abstracts_a_subnet(role_attributes.get(source_role, {})))

`--roles` exists so that *"a role whose single node stands for a whole subnet
**may carry a self-check**, one standing for a single device may not"*, and
`_abstracts_a_subnet` is true iff the declared address is a **proper subnet**
— more than one address, not the whole space. `wl_up` runs `strict=True` and
passes both `--roles` and `--cchecks`.

So for exactly these 28 roles FaVe **deliberately makes the diagonal
meaningful**, and the policy's diagonal being empty turns it into a
must-NOT-reach. The check is an assertion the workload intends, not a
degenerate artefact — which is the opposite of what O6b assumed.

## What the disagreement actually is

A role whose single node abstracts a /120 emits from, and receives on, a
**whole subnet**. Two different addresses inside it can plainly talk to each
other, so "this role reaches itself" is *true of the model FaVe built*.
VeriFlow-FR reports that. NetPlumber, ad6, BDD and NDD do not.

So this is not a tool quirk to declare away. It is a genuine disagreement about
a check the workload meant to ask, and on the face of it **VeriFlow-FR's answer
is the one consistent with `_abstracts_a_subnet`'s own premise** — the other
four may be collapsing a subnet-abstracting role to a single address.

## Revised options

* **O6d — find out which engines are right, first.** Check how each backend
  models a single-node subnet-abstracting role: as the /120, or as one address.
  If the other four collapse it to one address, they are under-approximating
  and VeriFlow-FR is correct; if VeriFlow-FR expands something the others
  deliberately do not, the reverse. Cheap: it is a question about the model
  each adapter builds, answerable the way O1a was. **Recommended — nothing
  below can be chosen honestly without it.**
* **O6e — if VeriFlow-FR is right:** the 28 are real violations of `wl_up`'s
  policy and the headline `wl_up` row changes from "all engines agree, 0
  violations" to "four engines miss 28". That is a finding about the four, and
  a significant one.
* **O6f — if the other four are right:** VeriFlow-FR over-approximates
  subnet-abstracting roles, and *that* is the `ACCOMMODATIONS.md` entry — but
  it is a different entry from the one O6b proposed, naming an
  over-approximation rather than a semantic preference.
* **O6b as originally written is withdrawn.** It would have recorded a
  disagreement about a deliberate check as a stylistic difference between
  tools, which is exactly the "declared accurately or not at all" failure item
  31 is about.

---

# F6 — SOLVED. VeriFlow-FR ignores a probe's test path; NetPlumber does not.

**The owner's hypothesis was right: the fault is in VeriFlow-FR's adapter.**

## The revisit hypothesis is refuted first

`wl_up × vf` re-run under NetPlumber's own traversal rule:

| `vf_revisit` | violations | wall |
|---|---:|---:|
| `state` (the thesis's rule, default) | 28/18811 | 639 s |
| `path` (NetPlumber's rule) | **28/18811** | 2884 s |

Identical. So item 33's table-granular loop trait is **not** the cause, and the
reading that had NetPlumber under-approximating is wrong. *(Incidental, and
undocumented until now: `path` costs **4.5×** `state` on this workload.)*

## The cause

`veriflow/translate.py` states:

> A probe's test path is accepted and **does not affect compliance**, as in
> NetPlumber, whose check_compliance reads the flows arriving at a probe.

**The "as in NetPlumber" is false.** `netplumber/adapter.py::add_probe` compiles
the test path into a path expression and passes it to `add_source_probe`:

    elif test_path:
        test_expr = {"type": "path", "pathlets": test_path}

What NetPlumber ignores is a probe's **filter fields** — `filter_expr = None`,
commented out deliberately. It does **not** ignore the **test path**. The
docstring conflates the two, and VeriFlow-FR implemented the wrong half.

## Why that produces exactly these 28

Every `wl_up` probe carries `.*(p=pgf.uni-potsdam.de.1);$` — the flow must
arrive **via the gateway's port 1**.

* **Only the diagonal differs** because inter-subnet traffic traverses the
  gateway anyway, so dropping the condition changes nothing for it. Only
  self/intra-subnet flows hairpin locally without passing `pgf.1`.
* **The 8 DMZ servers:** `src=::3, dst=::3` hairpins at the DMZ switch back to
  web's own port, never touching `pgf.1`. The firewall permits it because all
  45 FORWARD rules to a DMZ destination are source-unconstrained or scoped to
  the whole `/48` (23 carry no `-s` at all), so a DMZ server satisfies the
  source condition for reaching itself.
* **The 20 client subnets, and why NOT the department servers:** every
  department declares `XClients`, `XPrivateServers` and `XPublicServers` on the
  *same* `/120`, and the clients device is `…::100/120` — the whole `/120`. So
  the route for that `/120` points at the **clients** port, and a packet to
  `file.api` (`::5`) lands at `clients.api`'s input filter, firing
  `probe.clients.api`. The same route sends `file.api → file.api` to the
  clients port too, so `probe.file.api` never fires. That asymmetry is why the
  servers are clean and the clients are not.
* **`clients.wifi`** has no entry in `roles.json` at all (`Wifi <--> Wifi` is
  the only filled diagonal in the 71×71 matrix), so it carries no diagonal
  self-check and cannot differ.

## Two defects, and they are separable

1. **VeriFlow-FR ignores probe test paths** (`veriflow/translate.py`), against a
   stated-but-false claim about NetPlumber. This is what makes VeriFlow-FR
   report 28 where four engines report 0. **It is a correctness defect in a
   backend and it is ours, not the literature's.**
2. **The workload's model permits self-reach at all** — coarse FPL translation
   (source-unconstrained DMZ rules) and overlapping `/120` role declarations.
   That is a `wl_up` modelling question, independent of any engine, and it is
   the owner's to decide: it also means `wl_up`'s 28 diagonal must-NOT-reach
   checks are asserting something the model cannot honour.

Fixing (1) makes VeriFlow-FR agree with the other four and is a bug fix.
Fixing (2) is a workload decision and would change what the checks mean.
**They should not be conflated**, and (1) does not depend on (2).
