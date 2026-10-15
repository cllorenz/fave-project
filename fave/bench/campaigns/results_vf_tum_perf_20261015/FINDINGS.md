# Why VeriFlow-FR takes 3 h 20 min on wl_tum — findings and one measured variant (2026-10-15)

Asked by the owner after the NDD-APKeep investigation
([`../results_ndd_tum_perf_20261015/FINDINGS.md`](../results_ndd_tum_perf_20261015/FINDINGS.md)).
WORKLOAD.md records VeriFlow-FR at 11,994 s on wl_tum's 8,497 checks
(2026-10-14), against 142 s for BDD-APKeep. In-process, one run at a time,
nothing else heavy on the machine, change tracking off, VeriFlow-FR's defaults
(D6's 4+10 fields, Q4's `state` revisit rule, Q22's device-local slicing, no
budget). The variant is an **experiment in an out-of-tree worktree**; the main
tree is unchanged. Patch: [`early_exit.diff`](early_exit.diff).
Scripts: `../results_ndd_tum_perf_20261015/vf_diag.py` (every walk recorded),
`vf_who.py` and `vf_split.py` (walks mapped to sources, fields, tables),
`vf_one.py` (one walk alone), `vf_time.py` (all checks, timed apart from the
build). Raw outputs: `raw/`.

## Results

| run | checks (s) | local ECs | peak RSS | violated |
|---|---|---|---|---|
| stock (`vf_diag.py`) | **11,944** | 806 M | ~57 GB (sampled by hand) | 0 |
| early exit (variant) | **8,141** | 592 M | 3.4 GB | 0 |

The stock run repeats 2026-10-14's 11,994 s. Build: 0.45 s, once.

## Not the repeated walks

The driver (`VerdictCache.ask`) asks the checks in **313 rounds**: a round may
hold one check per (source, probe), which NetPlumber's violation reporting
needs. VeriFlow-FR walks every query set of every round anew: **2,158 walks
for 559 distinct query sets**. That was the first suspicion, and it is wrong.
The repeats are the cheap walks; an answer cache valid until the next update
would save at most 52 s (0.4 %). Not built further.

## Where the time is

| checks | walks | time | local ECs |
|---|---|---|---|
| `source.vlanN` → `probe.internet` (246) | 246, every one > 10 s | 11,881 s (99.5 %) | 806 M |
| `source.internet` → hosts and VLANs | 1,912 | 62 s | 0.3 M |

- **The outbound checks have no condition** (`s=source.vlan109 && EF
  p=probe.internet`): the packet set fixes the VLAN and the source subnet and
  leaves destination, protocol and ports open. The inbound checks fix
  `related`, protocol and port.
- **The local ECs are a cartesian product** (L7, T p.37): at each table, every
  trie field (here source, destination, destination port; the other seven are
  4+10 scan fields) is cut at every candidate rule's boundaries, and every
  combination is a local EC, walked on separately. The firewall's
  `fw.tum.forward_filter` (5,230 rules) cuts an open destination × port set
  into a grid, and each cell continues through `fw.tum.routing` and
  `vlans.tum.1` to the destination VLAN — where most of the 57 M slices of the
  worst walk are counted (`vlans.tum.1` 25.5 M, `fw.tum.routing` 24.8 M,
  `forward_filter` 2.0 M).
- **The worst walk** (`vlan109` → internet, a /24 source) is 954 s alone;
  the twelve worst are 3,700 s.

This is VeriFlow as specified, not a defect: VERIFLOW_PLAN Q22 already names
the explosion inside one firewall table "a genuine limitation of range-based
ECs" and a finding, and rules that it is "never approximated away; merging ECs
across ranges, in particular, would be APKeep's idea, not VeriFlow's". A
coarser exact partition (cutting a field only within the slab where candidates
differ) would cut the count, but it changes the EC definition (L7) and is the
owner's to decide; it was not built.

## The memory: the `state` revisit rule's visited set

The worst walk alone (`vf_one.py`), under both revisit rules (Q4):

| revisit | time | peak RSS | local ECs | states expanded | delivered |
|---|---|---|---|---|---|
| `state` (default, the thesis's) | 962 s | **55.7 GB** | 57,316,377 | 54,695,824 | 247 tables |
| `path` (NetPlumber's) | 751 s | **224 MB** | 57,316,377 | 54,695,824 | the same 247 |

On this walk the visited set **never prevents an expansion** (the same states
expanded): every state's packet set is a distinct grid cell. It costs 55 GB
and 22 % of the time and buys nothing here. The whole run's ~57 GB peak is
this walk's. Q4 chose `state` (owner, 2026-09-30) because `path` loses a real
delivery on router-on-a-stick; this is a finding for that decision, not a
change. A machine with less than 56 GB would not finish the stock run.

## Variant: early exit (verdicts need only the asked probes)

A walk enumerates every local EC to compute every table it delivers to, but a
check only asks whether ITS probe is delivered. BDD-APKeep's traversal already
stops at the first hit (NDD findings). The variant (`early_exit.diff`):

- `local_deliveries` takes, per start, the tables asked; once all are
  delivered, the start's walk stops (C++, a `Found` unwind).
- The adapter passes the asked probe tables per start only with **tracking
  off** and `FAVE_VF_EARLY_EXIT=1`. With tracking on, the incremental
  machinery reads each walk's complete delivered set and footprint (§4.1, §4.2
  dead ends), so the full walk stays; making early exit sound there would need
  a footprint argument per probe — not attempted.

Measured: **11,944 → 8,141 s (−32 %)**, local ECs 806 M → 592 M, peak RSS
→ 3.4 GB; 1,979 of 2,158 walks stopped early; 0 of 8,497 violated, the same
verdict for every check (stock: all 0 as well). Why the time gain is only a third
was not measured (no per-walk record in this run); presumably the depth-first
order reaches `probe.internet` only after much of the grid. The memory gain is
the large one: the walks stop before the visited set grows.

Verification on the variant (`raw/variant_tests.log`, `FAVE_VF_EARLY_EXIT=1`,
generated inputs and libnetplumber copied into the worktree): C++ 52 tests;
`test_veriflow_adapter` 2, `test_veriflow_differential` 4 (+1 opt-in wl_i2
skipped), `test_veriflow_airtel` 6 (+6 skipped: wl_airtel2 not generated, as
in the main tree), `test_veriflow_census` 3, `test_incremental_veriflow` 19
(these run with tracking on, so early exit is inactive there — they show the
variant leaves that path unchanged). The first test run skipped most modules
for missing inputs; the log keeps it.

## For the owner to decide

1. **Early exit** (variant, tracking off only): −32 % on wl_tum's checks and
   57 GB → 3.4 GB. Changes no EC and no answer; it does change the VeriFlow-FR
   numbers measured so far, and makes the full-check regime differ from the
   incremental one (which keeps full walks).
2. **The `state` revisit rule's memory** (Q4): on wl_tum it holds every grid
   cell and deduplicates none. Options: keep (document the memory), or bound it
   (e.g. remember states only at tables reached more than once on a path) —
   not built.
3. **The EC definition** (L7, Q22): unchanged, as ruled; a coarser exact
   partition is listed only as the one remedy for the time.
4. The 313 rounds re-walk query sets (0.4 % here): not worth a cache on
   wl_tum.
