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
