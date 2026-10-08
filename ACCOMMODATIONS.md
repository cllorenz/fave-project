# The accommodation registry

**What this is.** The one document the write-up cites for every way a verification
tool was helped to run FaVe's benchmark suite, or a workload was changed for it (TODO
item 31). The work's contribution is a unified, fair comparison. That needs every
departure from "the tool as published, on the workload as given" to be declared, with
what was done, what it costs, the evidence that it is right, and the stamp that records
it in each result cell.

**The owner's rule** (2026-09-29): to measure a tool at all, we either **implement a
feature** (an extension, stating what and how) or **run a preprocessed, limited
workload**. Preprocessing is a tweak of the workload, never a trait of the tool.

## Kinds

| kind | means | must state |
|---|---|---|
| **extension** | a capability we added inside the tool | what and how; whose design: the authors', the literature's, or ours |
| **adapter encoding** | something done to the input before the tool sees it | the encoding and its cost (e.g. an expansion factor) |
| **equivalence-preserving variant** | a changed workload that asks the same question | the evidence: an engine that runs both gives identical verdicts |
| **reducing variant** | a changed workload that asks a different question | that it is a new workload, with its own check set |
| **trait** | a property of the tool itself, not an accommodation | the semantics, and where it changes a verdict |
| **refusal** | input the tool's translation will not carry | the reason; refused, never approximated |

**Status of an entry:** *verified* means checked against code and measured in this
repository. *Seed* means carried over from a plan document and still to be classified;
it must not be cited as verified.

**`impl` is stamped by the engine, not by this document** (2026-10-02). Each
adapter declares `IMPL`, and a fork also declares the `UPSTREAM` it forked;
the aggregator logs it and `bench/cell_run.py` records it in every cell. The
headings below are therefore a reader's index to the values, not their source
-- if the two ever disagree, the engine's stamp is right and this file is
stale. `test/test_backend_provenance.py` fails a backend that declares none.

---

## VeriFlow-FR — `impl` = `reimpl-literature`

Our implementation from the NSDI'13 paper and the 2015 thesis alone, under a clean-room
protocol (`VERIFLOW_PLAN.md` §1, §3, §5). Every entry is *verified*. Stamps are logged
by the aggregator (`configuration_stamp`) and by the adapter at build
(`VeriFlowAdapter.build`). Sections are those of `VERIFLOW_PLAN.md`.

| entry | kind | what and how | cost / effect | evidence | stamp |
|---|---|---|---|---|---|
| Provenance | — | our code from the literature; no implementation read, copied, or run | — | §3 contamination record | `impl` |
| Bulk mode, check as query (Q21) | extension (ours) | FaVe loads everything, then asks checks. A check's packet set stands in for VeriFlow's "new rule"; its ECs are sliced and walked from the source. The thesis's per-update regime is not measured. | the incremental axis is open (item 31) | equal to NetPlumber on all nine workloads (§10, V3 and V3b) | `vf_mode` |
| **No U-turn (F6)** | **extension (ours)** | a packet is never forwarded back out the port it arrived on. Applied in both delivery walks (`walk`, `forward46`), in `ForwardingGraph::next_hops` — which also governs `table_edges`, `path_revisits` and `has_loop` — and **in the oracle**, so the reference still describes what the engine computes. **The thesis does not state the rule**, but every other engine in the comparison enforces it: NetPlumber in `Node::should_block_flow`, APKeep in `Checker.traverseFowardingGraph`. Needed because FaVe's single-table SWITCH models carry no explicit `in_port`/`out_port` drop rules, unlike `devices/packet_filter.py`'s multi-table `post_routing`, so without it a switch delivers self-addressed traffic back to its sender. | **28 spurious `source.X -> probe.X` violations of 18,811 removed on `wl_up`** — the other four engines all reported 0 — and ~27% of the runtime (652 s → ~400 s), which was spent exploring those branches | `wl_up × vf` 28 → 0, matching NetPlumber, ad6, BDD- and NDD-APKeep; NetPlumber's dumped flow tree for `source.web` reaches 30 probes and not `probe.web`; engine/oracle agreement (`veriflow_fr --test`, 44) | — |
| Device-local slicing (Q22) | literature (T §3.1.3) | at each table only its rules split the arriving set. The paper's network-wide slicing is kept as the ablation. | up to 10⁶× fewer ECs than network-wide | oracle; differential | `vf_slicing` |
| Revisit rule (Q4) | literature (T §3.1.3) | stop at a (table, arrival, packet set) already reached. `path`, NetPlumber's rule, is the ablation. | up to 9× less work than `path`; peak memory higher | oracle for both rules; router on a stick (item 33) | `vf_revisit` |
| 4 + 10 fields, generalised (D6) | extension (literature's rule, plus our design) | trie fields cut local ECs; exact-or-ANY fields are scanned by priority, finer rules excluded (T §3.2.2). **Ours:** exclusions at every table; a rewrite of a field an exclusion constrains first materialises the difference. | `wl_up` and `wl_tum` finish only with it | L9; verdict identity with plain on random networks and on every workload plain finishes | `vf_fields` |
| A graph node is a FaVe table (Q20) | adapter encoding | FaVe's tables and wiring are VeriFlow's devices and edges | none | differential | `vf_node` |
| IN_PORT is a matched field (Q7) | adapter encoding | a rule's ingress port qualifies it; its value at each hop is the arrival port | none | oracle with ingress-qualified rules | `vf_ports` |
| Several ingress ports per rule (Q16) | adapter encoding | one engine rule per port, at the same priority | factor 1.0 to 1.69 (`wl_stanford`) | V2 census | `vf_inport_expansion` |
| Field order | adapter encoding | FaVe's canonical field order is the trie's dimension order. The thesis measured order to matter (T Table 3.1). | not yet measured here | — | `vf_field_order` |
| LPM to priority (Q9) | adapter encoding | a declared-LPM table is longest-prefix-first, ties by index, as NetPlumber's `_lpm_ordered_batch` orders it; first-match tables by index | none | LPM guard: 13 of 13 right, 13 of 13 wrong when inverted | `vf_invert_lpm`, `vf_lpm_tables_ordered`, `vf_lpm_rules_ordered` |
| LPM inversion (MEASUREMENT_RUN_PLAN.md §5.4) | **reducing variant** | the guardrail arm: the same tables ordered SHORTEST-prefix-first, so the default route outranks every specific one. **Never a faithful run**, and `build_engine` refuses the flag on apkeep and ad6 rather than ignoring it — a silently-dropped inversion would leave the verdict unchanged for a reason that has nothing to do with the check set, which is precisely what the guardrail reads as "this check set is blind to LPM". | the point: the verdict SHOULD move | the two arms are run as separate declared cells and compared; `vf_lpm_tables_ordered` is the denominator, so an unchanged verdict on a workload that declared no LPM table cannot be mistaken for a passing guard | `vf_invert_lpm = true` |
| Negated check conditions (Q17) | adapter encoding | expanded into non-negated sets, as NetPlumber's `_expand_negations`; refused on a must-reach check | none in the suite (8 must-not-reach checks) | `test_veriflow_translate.py` | — |
| Rewrites: set, subnet, clear (§4.5, Q19) | extension | a whole field is set to a ternary value, `x` meaning wildcard, as NetPlumber's `STRICT_RW`. Clear-to-ANY (FaVe's in_port/out_port metadata) is beyond the thesis's actions. | none | rewriting oracle; differential | — |
| Router and packet-filter pipelines | adapter encoding | NetPlumber's skipped internal wires are mirrored. Its pre-routing mask quirk (one rule, `wl_ifi`) is **not**: the whole field is set, as the model says. | none measured | differential on `wl_ifi`, `wl_up`, `wl_tum`, `wl_example` | — |
| Probe paths | adapter encoding | accepted and ignored by compliance, as in NetPlumber | none | `test_veriflow_translate.py` | — |
| Internal budget | — | local ECs per check set; **0 in every reportable run**, since the suite limit is external (item 31) | — | — | `vf_budget` |
| Refusals | refusal | model types other than switch, router and packet filter; table misses; negated rule fields; rewrites to a non-interval; non-prefix ternary values; a prefix on a scan field | — | `test_veriflow_translate.py`, `opt46_unit.cc` | — |

## NetPlumber — `impl` = `authors+fave` (`net_plumber/FAVE_CHANGES.md`)

| entry | kind | status |
|---|---|---|
| **Table-granular loop rule.** A second pass through a table stops the flow, whatever its header (NetPlumber paper §4.2; loosened from HSA's port-granular check). It loses packets that legitimately pass a table twice. | trait | *verified* (item 33). It changes **no verdict on any of the nine workloads**: seven have no loop reports; on `wl_i2` (491 reports) and `wl_stanford` (83,710) VeriFlow-FR under the thesis's rule computes the same matrix. **The nine are the MATRIX workloads and do not include `wl_berkeley`** — see the row below, which is this trait's false positive caught in the open. |
| **…and what it reports on `wl_berkeley`** (2026-10-08) | trait, measured | **1,113 loop detections at k=3, at exactly 9 distinct nodes — and there are no loops.** `bench/deltanet/fib_walk.py`, a second implementation of the forwarding semantics with its own `LOOP` counter and a `2·devices+2` hop limit, reports **0 looping regions at BOTH k=3 and k=1**, with an identical 514-of-529 reached matrix. The 9 nodes are the **9 hairpin diagonals** the workload's protocol declares "permitted and unchecked": traffic that leaves a router and returns to it for delivery to its own border network — a second pass through one table, which is exactly what this rule cannot tell from a loop. **`wl_berkeley` is the workload built to state hairpins** (`RouterTraceBenchmark`; `--strict` turns its unreached diagonal into must-NOT-reach checks), so it exercises the trait on purpose. No verdict is affected: 0 of 520 at every size. |
| LPM by index (`_lpm_ordered_batch`): a declared-LPM table is ordered longest-prefix-first, because NetPlumber resolves priority by rule index | adapter encoding | *verified* (code). Stamped `np_invert_lpm` in every cell. |
| Invariant events are now PRESERVED per cell (`<stem>.inv.log`, counted into `loop_reports`/`blackhole_reports`) | harness | Until 2026-10-08 `cell_run.py` copied `aggregator.log`, `report.md` and the GC log and **discarded `inv.log`** — so this table's loop counts cited evidence no completed cell retained, and `wl_berkeley`'s 1,113 were recovered only because nothing had overwritten the file yet. `None` (no such log; every backend but NetPlumber) and `0` (it ran and reported nothing) are recorded as different facts. |
| **LPM inversion** (`--invert-lpm`): the same tables ordered SHORTEST-prefix-first, so the default route outranks every specific one — MEASUREMENT_RUN_PLAN.md §5.4's guardrail arm, asking whether a workload's CHECK SET can see rule priority at all | **reducing variant** | **never a faithful run**; off by default and stamped `np_invert_lpm` either way, because an absent stamp does not say "faithful", it says the build could not tell you. Each ordered table logs its rule count, so an unchanged verdict has a denominator and cannot be read as a passing guard on a workload that declared no LPM table. |
| Pre-routing rewrite mask built from the rewritten value (only its 1-bits are written) | adapter behaviour | *verified* (code); no effect measured on the suite |

## APKeep — `impl` = `authors+fave` (`apkeep/FAVE_CHANGES.md`)

| entry | kind | status |
|---|---|---|
| A VLAN in a destination FIB is carried only by the HSA-stage mechanisms and, for a rewrite, a router's routing table. Elsewhere the table is first-match: a VLAN match is carried, a VLAN rewrite is refused, and so are in-port-qualified rules on a first-match table. | extension scope + refusal | *verified* (item 33, `apkeep/FAVE_CHANGES.md` §10); suite unaffected |
| The `in.`/`mid.`/`out.` stage exemption is keyed on device names | adapter encoding | *verified* (code); a known limit, in the adapter's own words |
| Faithful-VLAN model, and `--no-vlan`, which is VLAN-blind and "not a like-for-like comparand" (`APKEEP_BACKEND.md`) | adapter encoding (reducing when `--no-vlan`) | seed |
| Ingress demultiplexing (`CLOUD_BENCH_PLAN.md` §2.8) | adapter encoding | seed |

## ad6 — `impl` = `first-party`

| entry | kind | status |
|---|---|---|
| `--lite-acyclic` mandatory on `wl_i2` (TODO item 0a) | adapter encoding | seed |

## Retired — `-o` in a filter chain (TODO item 13a), CLOSED 2026-10-06

Recorded here because it was **never recorded here**, which is the point.

From 2026-09-18 to 2026-10-06, FaVe refused an `-o` (egress-interface) match in
any filter chain and offered `FAVE_ALLOW_OUT_IFACE=1` to model it as **no
constraint instead** — a declared infidelity, over-permitting for `-j ACCEPT`
and over-restricting for `-j DROP`, in force for the five workloads whose
rulesets carry such a rule (`wl_example`, `wl_generic_fw`, `wl_shadow`,
`wl_tum`, `wl_up`). It was announced on stderr per device and written up in
TODO item 13a — **and it never reached this registry**, which item 31 created so
that the write-up could cite one document instead of five. A reader auditing the
comparison from this file alone would not have known it existed.

**It is retired, not reclassified.** The premise was wrong. The refusal rested
on "a filter chain runs before `routing`, so `out_port` is wildcard when the
rule is evaluated and `routing` overwrites the narrowing — the match constrains
nothing". The narrowing does its FILTERING before the rewrite, so the rule
applies to exactly the slice of the flow that will leave by that port. Measured
on the two `-o` workloads, whose rules have opposite polarity:

| engine | `wl_example` (`-o` ACCEPT) | `wl_up` (`-o` DROP ×2) |
|---|---|---|
| NetPlumber, ad6, VeriFlow-FR | correct | correct |
| BDD/NDD-APKeep, before 2026-10-06 | **lost the permit** | correct (by skipping) |
| BDD/NDD-APKeep, now | correct | correct |

Three backends always modelled it; APKeep's adapter dropped such rules, and now
resolves them against the FIB (`_lpm_destinations`): an `-o N` rule applies to
the destinations whose longest-prefix match egresses N.

**What remains, and it is small.** APKeep on a device with **no FIB** — a
terminal filter such as `wl_tum`'s `fw.tum`, which has no routing at all —
still cannot resolve the egress and drops the rule. That is now logged per
device with a count and the direction of the error. It is the only surviving
`-o` infidelity in the suite, it affects one backend on one device shape, and
`wl_tum` has no check set, so no verdict in the comparison rests on it.

## Workloads

| entry | kind | status |
|---|---|---|
| The Delta-net airtel workloads: a static snapshot of an update trace, with an invented reachability policy (`CLOUD_BENCH_PLAN.md` §2.1, §2.5) | workload construction | seed |
| `_reprioritise_fib_lpm` (LPM encoded into first-match order at generation time) | adapter encoding | seed; superseded by declared table semantics (`TABLE_SEMANTICS_PLAN.md`) |
