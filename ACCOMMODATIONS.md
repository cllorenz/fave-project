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
| Device-local slicing (Q22) | literature (T §3.1.3) | at each table only its rules split the arriving set. The paper's network-wide slicing is kept as the ablation. | up to 10⁶× fewer ECs than network-wide | oracle; differential | `vf_slicing` |
| Revisit rule (Q4) | literature (T §3.1.3) | stop at a (table, arrival, packet set) already reached. `path`, NetPlumber's rule, is the ablation. | up to 9× less work than `path`; peak memory higher | oracle for both rules; router on a stick (item 33) | `vf_revisit` |
| 4 + 10 fields, generalised (D6) | extension (literature's rule, plus our design) | trie fields cut local ECs; exact-or-ANY fields are scanned by priority, finer rules excluded (T §3.2.2). **Ours:** exclusions at every table; a rewrite of a field an exclusion constrains first materialises the difference. | `wl_up` and `wl_tum` finish only with it | L9; verdict identity with plain on random networks and on every workload plain finishes | `vf_fields` |
| A graph node is a FaVe table (Q20) | adapter encoding | FaVe's tables and wiring are VeriFlow's devices and edges | none | differential | `vf_node` |
| IN_PORT is a matched field (Q7) | adapter encoding | a rule's ingress port qualifies it; its value at each hop is the arrival port | none | oracle with ingress-qualified rules | `vf_ports` |
| Several ingress ports per rule (Q16) | adapter encoding | one engine rule per port, at the same priority | factor 1.0 to 1.69 (`wl_stanford`) | V2 census | `vf_inport_expansion` |
| Field order | adapter encoding | FaVe's canonical field order is the trie's dimension order. The thesis measured order to matter (T Table 3.1). | not yet measured here | — | `vf_field_order` |
| LPM to priority (Q9) | adapter encoding | a declared-LPM table is longest-prefix-first, ties by index, as NetPlumber's `_lpm_ordered_batch` orders it; first-match tables by index | none | LPM guard: 13 of 13 right, 13 of 13 wrong when inverted | `vf_invert_lpm` (guard-only; never set in a result) |
| Negated check conditions (Q17) | adapter encoding | expanded into non-negated sets, as NetPlumber's `_expand_negations`; refused on a must-reach check | none in the suite (8 must-not-reach checks) | `test_veriflow_translate.py` | — |
| Rewrites: set, subnet, clear (§4.5, Q19) | extension | a whole field is set to a ternary value, `x` meaning wildcard, as NetPlumber's `STRICT_RW`. Clear-to-ANY (FaVe's in_port/out_port metadata) is beyond the thesis's actions. | none | rewriting oracle; differential | — |
| Router and packet-filter pipelines | adapter encoding | NetPlumber's skipped internal wires are mirrored. Its pre-routing mask quirk (one rule, `wl_ifi`) is **not**: the whole field is set, as the model says. | none measured | differential on `wl_ifi`, `wl_up`, `wl_tum`, `wl_example` | — |
| Probe paths | adapter encoding | accepted and ignored by compliance, as in NetPlumber | none | `test_veriflow_translate.py` | — |
| Internal budget | — | local ECs per check set; **0 in every reportable run**, since the suite limit is external (item 31) | — | — | `vf_budget` |
| Refusals | refusal | model types other than switch, router and packet filter; table misses; negated rule fields; rewrites to a non-interval; non-prefix ternary values; a prefix on a scan field | — | `test_veriflow_translate.py`, `opt46_unit.cc` | — |

## NetPlumber — `impl` = `authors+fave` (`net_plumber/FAVE_CHANGES.md`)

| entry | kind | status |
|---|---|---|
| **Table-granular loop rule.** A second pass through a table stops the flow, whatever its header (NetPlumber paper §4.2; loosened from HSA's port-granular check). It loses packets that legitimately pass a table twice. | trait | *verified* (item 33). It changes **no verdict on any of the nine workloads**: seven have no loop reports; on `wl_i2` (491 reports) and `wl_stanford` (83,710) VeriFlow-FR under the thesis's rule computes the same matrix. |
| LPM by index (`_lpm_ordered_batch`): a declared-LPM table is ordered longest-prefix-first, because NetPlumber resolves priority by rule index | adapter encoding | *verified* (code) |
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

## Workloads

| entry | kind | status |
|---|---|---|
| The Delta-net airtel workloads: a static snapshot of an update trace, with an invented reachability policy (`CLOUD_BENCH_PLAN.md` §2.1, §2.5) | workload construction | seed |
| `_reprioritise_fib_lpm` (LPM encoded into first-match order at generation time) | adapter encoding | seed; superseded by declared table semantics (`TABLE_SEMANTICS_PLAN.md`) |
