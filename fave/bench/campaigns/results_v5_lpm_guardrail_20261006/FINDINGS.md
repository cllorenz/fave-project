# The LPM guardrail — MEASUREMENT_RUN_PLAN.md §5.4, answered

Run 2026-10-06 15:14–15:24 UTC, 12 cells, from `cf2ec3a6`. Predictions in
`PROTOCOL.txt`, declared before the run and not edited. One question each for
three workloads: **can this workload's check set see rule priority at all?**

## The result

| workload | engine | faithful | inverted | reordered | guard |
|---|---|---|---|---|---|
| `wl_stanford` | np | 75/240 | **230/240** | 16 tables, 3,844 rules | **passes** |
| `wl_stanford` | vf | 75/240 | **230/240** | 16 tables, 3,844 rules | **passes** |
| `wl_i2` | np | 11/72 | 11/72 | 9 tables, **77,451 rules** | **FAILS** |
| `wl_i2` | vf | 11/72 | 11/72 | 9 tables, **77,451 rules** | **FAILS** |
| `wl_cloud` | np | 58/71 | 58/71 | **0 tables, 0 rules** | **not applicable** |
| `wl_cloud` | vf | 57/71 | 57/71 | **0 tables, 0 rules** | **not applicable** |

Both engines agree, arm for arm, on every workload — including the one
disagreement they already had (`wl_cloud` 58 np against 57 vf, F4-R), which is
unchanged by inversion and so is not about rule priority.

## `wl_i2`'s gating evidence is blind to longest-prefix-match

**77,451 rules across 9 tables were reordered so that the shortest prefix wins,
and not one of the 72 checks noticed.** The same 11 violations, on two
independent engines. This is `wl_deltanet`'s failure exactly (owner,
2026-09-22), and it is the finding this experiment existed to be able to make.

It is not a small inversion that happened to miss. `wl_i2`'s FIB is the `out`
stage and carries the 3,731 rules that sat shadowed by a containing prefix for a
month while the old repair hardcoded `mid.` (`AD6_PLAN.md` §5.5) — the structure
an inversion acts on is present and abundant. The check set simply does not
probe it.

**What this does and does not mean.** It does not mean `wl_i2`'s 11/72 is wrong;
every engine agrees on it. It means that verdict would have been reached just as
readily against a model that forwards by its default route, so `wl_i2` cannot be
cited as evidence that an engine resolves longest-prefix-match correctly. Any
claim of that shape has to rest on `wl_stanford`.

**Not fixed here.** The repair is a check set that distinguishes nested
prefixes, which is new measurement input and the owner's call, not a defect to
patch. Recorded as an open item.

## `wl_stanford` passes, and by a wide margin

75 → **230 of 240**. The inverted model is one where the default route outranks
every specific one, and the check set sees 155 additional violations. It also
runs very much faster — np 5.1 s → 2.8 s, vf 152.0 s → 2.7 s — because when the
default wins everywhere, the forwarding collapses and there is almost nothing
left to slice. That is a property of the broken model, not a result.

`wl_stanford` is therefore the suite's one workload whose evidence is
demonstrably LPM-sensitive, which matches its history: re-prioritising its FIB
once lifted NetPlumber's reachable-pair count 10 → 165.

## `wl_cloud` was never an open case — §5.4 is wrong about it

**`wl_cloud` declares no LPM table at all.** Zero tables and zero rules
reordered, on both engines, which is G0's falsifier and makes its unchanged
verdict evidence about nothing.

This is not an oversight in the workload. `bench/wl_cloud/cloud_preparation.py`
states it as a decision and gives the reason: 45 of the dataset's devices hold
**one table mixing forwarding and filtering** — `lin.dc1_leaf0` permits
`10.0.4.0/25` on tcp/332, drops the rest of `10.0.4.0/25`, then forwards
everything else. Those two rules share a prefix and disagree, so longest-prefix
cannot resolve them under any backend; only their order can. The table is
first-match, written in destination-prefix terms.

It also records that the repair which used to run there was **measured a
complete no-op**: with it removed the generated routes are byte-identical, 1,741
rules, because the colliding rules tie on prefix length and the default sorts
last anyway.

So §5.4's "on `wl_cloud` the re-prioritisation is called *load-bearing*" cites a
claim the project had already withdrawn in the code — the second time this
campaign has scored a prediction against a withdrawn claim (the first was
prediction 10 and `CLOUD_BENCH_PLAN.md` §1.7.2). §5.4 is corrected to list two
open workloads, not three.

## Scores

| # | prediction | score |
|---|---|---|
| G0 | every inverted cell reorders at least one table | **FALSIFIED on `wl_cloud`** — 0 of 0, on both engines. Held on `wl_stanford` (16, as predicted from `test_table_semantics`) and `wl_i2` (9, as predicted). |
| G1 | `wl_stanford`'s verdict moves | **HELD** — 75 → 230 of 240 |
| G2 | `wl_i2`'s verdict moves | **FALSIFIED** — 11/72 in both arms, against 77,451 reordered rules. The falsification is the finding. |
| G3 | no prediction declared for `wl_cloud` | correctly declined; it turned out to be inapplicable rather than either answer |
| G4 | np and vf agree arm for arm | **HELD** — identically on all six pairs |
| G5 | no inverted cell errors or times out | **HELD** — 12 of 12 `measured` |

### §7's prediction 11, tested for the first time

> *"At least one of the three LPM inversions does not change the verdict, as
> `wl_deltanet`'s did not. Falsified by: all three flipping."*

**HELD** — `wl_i2` did not change. §7.1 scored P11 "NOT TESTED, and it could not
have been": the queue carried no inversion cells and no mechanism existed to run
them. It is now tested.

It holds, but it is worth being precise about what holding means here. P11 was
written as a prediction about how many inversions would flip; it reads as
reassurance. What it actually records is that one of the three workloads has
gating evidence that cannot see rule priority, and that a second was never a
candidate. **One of three passes.**

## A defect this experiment found in itself

The first run reported `vf_lpm_tables_ordered` as 32 for `wl_stanford` and 18
for `wl_i2` — double NetPlumber's 16 and 9 — because the translator counted
every declared table it considered, including empty ones. Wrong in the generous
direction, in the one figure whose job is to stop a null result being believed.

It was caught because the **rule** counts agreed to the unit between two
independent engines (3,844 and 77,451), which a genuinely different table set
would not produce. Corrected in `a964da7b` and confirmed against both real
workloads: VeriFlow now reports 16/3,844 and 9/77,451, identical to
NetPlumber's, with the verdicts reproducing exactly (230/240 and 11/72).

**These results are not re-scored on that correction.** Every conclusion above
rests on zero-versus-non-zero and on the rule counts, and neither moves.
