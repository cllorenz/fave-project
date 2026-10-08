# The V5 reportable campaign — results

Measured 2026-10-02 → 2026-10-08 on one machine (64,294 MB, 16 cores, **no
swap**; `MACHINE.txt`). Reportable cells are `limit_class=v5`: **24 h wall,
32 GB RSS**, stamped per cell (TODO item 31).

Every table here is **generated** — `python3 bench/campaigns/cell_table.py` —
not typed. Phase A's matrix was assembled by hand, which is how a `wl_cloud`
row came to say "refuses (structural)" for a cell that answered.

## 1. The matrix — what each engine says

```
python3 bench/campaigns/cell_table.py results_v5_20261002 \
    --over results_v5_o1afix --over results_v5_f3fix \
    --over results_v5_remeasure_20261006 \
    --over results_v5_i2_ad6_flow_20261008
```

| workload | NetPlumber | NDD-APKeep | BDD-APKeep | ad6 | VeriFlow-FR | VF-plain |
|---|---|---|---|---|---|---|
| wl_example | 0/10 | 0/10 | 0/10 | 0/10 | 0/10 | 0/10 |
| wl_ifi | 27/299 | 27/299 | 27/299 | 27/299 | 27/299 | 27/299 |
| wl_cloud | 58/71 ‡57 | 57/71 | *see §3* | 57/71 | 57/71 | 57/71 |
| wl_tum | — no checks | — | — | — | — | not run |
| wl_airtel1 | 0/256 | 0/256 | 0/256 | 0/256 | 0/256 | 0/256 |
| wl_airtel2 | 0/256 | 0/256 | 0/256 | 0/256 | 0/256 | 0/256 |
| wl_stanford | 75/240 | 75/240 | **DNF** (wall, 24 h) | 75/240 | 75/240 | 75/240 |
| wl_i2 | 11/72 | 11/72 | **DNF** (wall, 24 h) | 11/72 § | 11/72 | 11/72 |
| wl_up | 0/18811 | 0/18811 | 0/18811 | 0/18811 | 0/18811 | not run |

**Every engine agrees with every other, on every workload that finished.**

**§ `ad6 × wl_i2` is FLOW-grounded**; every other ad6 cell here is rank. They
may not be read down the same wall-clock column (`AD6_PLAN.md` §9.33.3) — the
sign of the effect depends on the query count, so neither grounding is "faster"
in general. Phase A ran this cell as `rank + lite_acyclic` and it tripped the
24 h limit at 23,667 MB with no verdict; §9.33.2, written two weeks *before*
that queue shipped, had already established that rank cannot carry i2 since the
plain model was deleted. Re-measured 2026-10-08 under
`--grounding flow --solver cadical195`: **63.3 min, 10,497 MB, 11 of 72**, set-
identical to the other three engines. The DNF is not withdrawn — it is a result
about rank — but it was never a statement about ad6 on this workload. Full
scoring in [`results_v5_i2_ad6_flow_20261008/FINDINGS.md`](results_v5_i2_ad6_flow_20261008/FINDINGS.md).

**‡ is not a disagreement.** NetPlumber's 58 is 57 distinct violations plus one
line printed twice — the same (source, probe) pair witnessed by two
*overlapping* header fragments, because HSA's union-of-wildcards is not
canonical. `cell_metrics.violations` counts report LINES. This is the only cell
in the suite with a duplicated line, and it read as a four-against-one engine
disagreement until 2026-10-07. **Open (owner):** whether that metric should
count distinct violated checks, which would move recorded numbers campaign-wide.

`wl_tum` has no check set; `—` is not `0`. `VF-plain` on `wl_tum`/`wl_up` is the
declared ablation and was deferred, never run.

## 2. Cost

| workload | NetPlumber | NDD-APKeep | BDD-APKeep | ad6 | VeriFlow-FR | VF-plain |
|---|---|---|---|---|---|---|
| wl_example | 2.2 s / 86 MB | 2.1 s / 1816 MB | 2.2 s / 366 MB | 2.4 s / 215 MB | 2.1 s / 67 MB | 2.1 s / 67 MB |
| wl_ifi | 2.1 s / 81 MB | 2.0 s / 1414 MB | 2.1 s / 399 MB | 4.2 s / 212 MB | 2.1 s / 66 MB | 2.1 s / 64 MB |
| wl_cloud | 2.3 s / 230 MB | 2.2 s / 2035 MB | *see §3* | 57.5 s / 2949 MB | 2.4 s / 187 MB | 2.3 s / 224 MB |
| wl_tum | 5.9 s / 538 MB | 4.3 s / 1939 MB | 4.3 s / 257 MB | 4.3 s / 188 MB | 4.3 s / 190 MB | — |
| wl_airtel1 | 5.2 s / 218 MB | 3.6 s / 2058 MB | 4.4 s / 878 MB | 34.8 s / 1527 MB | 4.2 s / 194 MB | 4.2 s / 194 MB |
| wl_airtel2 | 5.3 s / 367 MB | 3.7 s / 2072 MB | 4.4 s / 892 MB | 33.7 s / 1542 MB | 4.1 s / 198 MB | 4.2 s / 197 MB |
| wl_stanford | 5.0 s / 840 MB | 3.2 s / 2152 MB | 24 h / 3135 MB | 808.5 s / 8222 MB | 152.9 s / 1017 MB | 428.9 s / 1979 MB |
| wl_i2 | 62.2 s / 1868 MB | 32.1 s / 2570 MB | 24 h / 2883 MB | 3800.6 s / 10497 MB § | 116.5 s / 374 MB | 113.5 s / 399 MB |
| wl_up | 22.8 s / 3872 MB | 9.5 s / 2254 MB | 380.3 s / 1792 MB | 433.1 s / 13996 MB | 402.0 s / 610 MB | — |

Peak RSS is the whole session, so the JVM backends carry a ~1.4–2 GB floor that
is the runtime, not the workload.

## 3. The long cells

**`bdd × wl_cloud` — COMPLETED, 3.24 h**, 1,773 of 1,773 rules, `ap_num`
97,709, 186.9 MiB of BDD memory at `-Xmx8g`. The query is **0.785 s**: 99.99% of
the cell is the build, 87% of the build is merge. It reports **59 reachable
pairs, not the 53** of the 2026-09-25/27 runs — corroborated by the post-NAT-fix
BDD probe and by NDD independently. **The first completion on a correct binary**
(§5.3's S1/S4), and `reachable_pairs` is not the matrix's `violations/checks`.

**The two faithful probes** stand: compared at matched rule count, stanford
0.99×/0.98× and i2 1.02×/1.15× against their 2026-09-26 counterparts, all
inside 1.5×. Neither faithful cell earns a 24 h run.

## 4. `wl_berkeley` — the size series

23 switches, one LPM table each; rules distribute flat (one per prefix) and the
sampler is proportional to three decimals, so the shape is constant across k.

| cell | engine | wall | peak RSS | verdict |
|---|---|---:|---:|---|
| k=30 (459,202 rules) | NetPlumber | 210.0 s | 2,382 MB | 0/520 |
| k=10 (1,351,800) | NetPlumber | 3,083.4 s | 7,159 MB | 0/520 |
| **k=3 (4,476,240)** | NetPlumber | **16.05 h** | 23,333 MB | 0/520 |
| k=30 | NDD-APKeep | 28.3 s | 4,128 MB | 0/520 |
| k=10 | NDD-APKeep | 116.4 s | 7,953 MB | 0/520 |
| k=3 | NDD-APKeep | 339.6 s | 20,932 MB | 0/520 |
| **k=1 (13,402,846)** | NDD-APKeep | **1,129.6 s** | 44,681 MB | 0/520 |
| k=3 | BDD-APKeep | 775.7 s | 18,698 MB | 0/520 |
| **k=1** | BDD-APKeep | **3,405.0 s** | 47,433 MB | 0/520 |

**Both APKeep engines answer the full 13.4 M-rule model**; BDD is 3.01× NDD at
k=1 (2.28× at k=3, so it loses ground with size), and the whole difference is
the compliance check — rule load is a dead heat, 672.6 s against 687.0 s.

**NetPlumber reaches k=3 and stops there.** §5.2 said it "already deadlines at
459k rules"; that was the old *machine*, not a limit and not the code — an A/B
put `-DLEGACY_CHECKS` at 209.5 s against two default runs at 205.9 s and
208.2 s, inside the 1.1% spread between identical runs. Its load exponent is
flat at **2.45–2.50** and its memory linear at **1.00–1.04**, so k=1 projects to
**235 h and ~67 GB** — excluded on both axes, independently.

**Loops.** NetPlumber reports 1,113 loop detections at k=3 at exactly 9 nodes,
and there are **no loops**: `fib_walk.py` finds 0 looping regions at both k=3
and k=1 with an identical 514-of-529 matrix. The 9 are the workload's **9
hairpin diagonals** — the table-granular loop rule's documented false positive,
caught in the open on the one workload built to state hairpins.

## 5. Predictions

Declared before each run and never edited; scored in the directory that ran them.

| set | where | outcome |
|---|---|---|
| §7 P1–P6 (`wl_berkeley` k=1) | `../deltanet/eval/results_berkeley_ndd_20261002/FINDINGS.md` | P1–P3 held; **P4, P6 falsified**, P5 half |
| §7 P7 (`bdd × wl_cloud`) | `FINDINGS_phase_c.md` | **FALSIFIED** — 3.24 h, not 15–22 |
| §7 P8 (the probes) | `FINDINGS_phase_c.md` | held |
| §7 P9, P10, P11 | `MEASUREMENT_RUN_PLAN.md` §7.1 | P9 half; **P10 falsified**; P11 held |
| R1–R8 (re-measurement) | `results_v5_remeasure_20261006/FINDINGS.md` | **7 of 8 held** |
| G0–G5 (LPM guardrail) | `results_v5_lpm_guardrail_20261006/FINDINGS.md` | **G0, G2 falsified** |
| N1–N7, A1 (NetPlumber × berkeley) | `results_v5_berkeley_np_20261007/FINDINGS.md` | N1–N6 held, N7's number missed; **A1 falsified** |
| B5–B7 (BDD k=1) | this file, §4 | B5, B6 held; **B7 falsified** |
| F1–F5 (ad6 × wl_i2, flow) | `results_v5_i2_ad6_flow_20261008/FINDINGS.md` | **F1–F4 all held**; F5 is a reading rule |
| V1–V5 (the VLAN guardrail) | `results_v5_vlan_guardrail_20261008/FINDINGS.md` | **V1–V4 all held**; V5 is a reading rule |

**Falsified predictions are the campaign's most useful output.** P10 and §5.4's
`wl_cloud` case were both scored against claims the project had *already
withdrawn in its own code* — the same failure twice, a plan summary outliving
the body that supported it. P4 showed the growth exponent is not flat. A1
stopped a 10× speed-up being credited to the author's own change.

## 6. What this does not cover

* **One sample per cell.** The only variance figure in the campaign is the 1.1%
  spread between two identical NetPlumber runs at k=30.
* **The faithful-VLAN axis is narrower than it reads.** §6 defines phase A as
  including "faithful variants", and §5.1 calls them "separate cells, not the
  same workload" — but that sentence predates 2026-09-18, when the faithful
  model became the APKeep default. Checked against the artifacts (2026-10-08):
  every APKeep cell stamps `faithful_vlan: true`, the `wl_stanford` and `wl_i2`
  aggregator logs record per-port faithful VLAN admission, and the verdicts are
  the faithful ones (165 reachable on stanford, 61 on i2). **The matrix cells
  ARE the faithful cells** wherever the flag does anything, which is those two
  workloads. Only APKeep has the axis at all: NetPlumber and VeriFlow-FR
  translate the model's rules literally, and ad6's semantic path is deleted.
  The faithful-vs-plain contrast **was missing and is now RUN** (2026-10-08,
  `results_v5_vlan_guardrail_20261008/`): both arms of both workloads on one
  build, after `--no-vlan` was given the refusal and the denominator §5.4's LPM
  arm already had. **`wl_i2` 11/72 → 0/72** over 77,451 relaxed rewrites, so
  that check set sees VLAN by exactly 11 pairs; **`wl_stanford` 75/240 →
  75/240 unchanged** over 3,417 rewrites and 2,063 admission rules, so **its
  check set cannot see the VLAN dimension at all** — the same shape as G2's LPM
  finding, and comparable in magnitude. An unchanged verdict there says nothing
  about whether VLAN modelling matters: the same engine, build and flag move
  `wl_i2` by 11.
* **`bdd × wl_stanford` and `bdd × wl_i2` are the faithful cells**, and both are
  24 h did-not-finishes. That is the expected result, not a surprise:
  `APKEEP_BACKEND.md` records that the APKeep engine default moved to NDD
  *because* faithful-on-BDD completes on neither. The matrix prints them as
  bare DNFs, which reads as "BDD is slow" rather than "BDD cannot carry the
  faithful VLAN model at this size".
* **The incremental axis** (item 31): every cell is a build-from-zero.
* **`reachable.json` is not an oracle.** A cell is `measured`, not `correct`,
  wherever no expectation was declared. The only external oracle in the suite is
  `wl_cloud`'s six Z3-Datalog queries, all six reproduced.
