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
