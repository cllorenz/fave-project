# ad6 × wl_i2 under the flow grounding — the result

Run 2026-10-08, declared in [`PROTOCOL.txt`](PROTOCOL.txt) before it started.
One cell, `limit_class=v5` (24 h wall, 32 GB RSS), on the campaign machine
(64,294 MB, 16 cores, no swap) with nothing else running.

```
status      completed          limit_tripped  none
outcome     measured           verdict_valid  true
violations  11 of 72           wall           3,800.6 s  (63.3 min)
peak RSS    10,497 MB          engine         ad6 f038b62c (2026-09-22)
stamp       {impl: first-party, translation: literal, grounding: flow,
             solver: cadical195, lite_acyclic: false}
```

**The cell the campaign recorded as a 24-hour did-not-finish answers in 63
minutes.** The phase A cell is not withdrawn: `rank + lite_acyclic` genuinely
does not finish on this model, at 23,667 MB and no verdict, and that stands as
a result about the rank encoding. What is corrected is the reading — that DNF
was never a statement about ad6 on `wl_i2`.

## The predictions, scored

| | declared | measured | |
|---|---|---|---|
| **F1** | completes, `verdict_valid` | completed, none tripped, valid | **held** |
| **F2** | 11 of 72, and *the set* | 11, set-identical to three engines | **held** |
| **F3** | < 7,200 s (est. 3,500–4,500) | **3,800.6 s** | **held** |
| **F4** | 8,000–16,000 MB | **10,497 MB** | **held** |
| **F5** | a reading rule, not a prediction | applied below | — |

F2 was scored **by set difference, empty both ways**, against every other
engine that answers this workload — not by matching the count, which is the
weaker test a count-only prediction would have permitted:

```
atla → kans, seat        chic → hous, kans, losa, salt, seat
newy32aoa → kans, seat   wash → kans, seat
```

identical to `results_v5_remeasure_20261006/wl_i2_np.report.md`,
`results_v5_20261002/wl_i2_ndd.report.md` and
`results_v5_remeasure_20261006/wl_i2_vf.report.md`. Four independent engines,
one set. It also matches `AD6_PLAN.md` §5.5's archived 11 and §9.33's live-
aggregator run, so the flow encoding reproduces its own earlier answer on a
different machine a month later.

**Still consensus, not ground truth.** `bench/wl_i2/reachable.json` is the same
all-reachable policy mesh as `wl_stanford`'s and cannot adjudicate (§9.28.6);
this cell is `measured`, not `correct`, and carries no `--expect-violations`.

## Where the hour goes, and why it is the interesting number

| | n | total | mean | max |
|---|---:|---:|---:|---:|
| SAT (reachable) | 61 | 1,801.2 s | 29.5 s | 188.6 s |
| **UNSAT (unreachable)** | **11** | **1,513.1 s** | **137.6 s** | **315.1 s** |

The 11 unreachable pairs are **15% of the queries and 46% of the solve time**,
at 4.7× the mean cost of a reachable one. Refutation is categorically harder: a
SAT answer is cheap because a model exists to exhibit, where UNSAT must exclude
every path. That asymmetry is not new here — it is what `AD6_PLAN.md` §5.5 read
as the *signal* on 2026-09-10, when `chic→salt` went from a 63 s SAT to no
answer in 20,302 s under the port-scoped admission fix, and the slowdown was
evidence of a flipped verdict rather than of a regression.

Query time is 3,314.2 s of the 3,795.2 s `check_compliance`; the remaining
~481 s is the build. Rule load is 1.6 s over 18 `switch_command`s.

## F5 applied — this number may not sit beside the rank cells

§9.33.3 is explicit and this file obeys it: every other ad6 cell in the campaign
is **rank**-grounded, and §7.5's 21.7× — flow at its best against rank at its
worst — is what happens when the grounding is left out of the comparison. So:

* `bench/campaigns/cell_table.py` now keys a cell by **its own stamps** rather
  than its filename, and the `†` footnote prints the `engine_options` that
  produced every overriding cell. The matrix row for `wl_i2 × ad6` names
  `--grounding flow --solver cadical195` without anyone having to type it.
* `RESULTS.md` §2 carries the grounding on this row in prose.

**The sign of the flow-vs-rank effect depends on the query count**, so neither
is "faster": flow is 3.65× faster on `wl_stanford` (240 queries) and >31.4×
slower on `wl_up` (11,902, did not finish). On `wl_i2` it is not a preference at
all — §9.33.2 — it is the only grounding that fits the machine.

## Two method notes

**A void first launch, deleted.** The cell was first started with a bare
`python3`, i.e. the system interpreter, and died in 0.032 s on
`ModuleNotFoundError: No module named 'filelock'` — having *written a result*:
`status: error`, `outcome: error`, `verdict_valid: false`, `checks: 72`. Nothing
in that artifact says the interpreter was wrong. It was removed before the real
launch, and `cell_run.py` now refuses such a cell before anything is spawned
(commit `314263ea`): `CHILD_IMPORTS` declares what each backend's children need,
located rather than imported. On the system interpreter the guard names
`filelock` for every backend, plus `jpype` for apkeep and `pysat` for ad6.

**`git_head` is stamped when a cell FINISHES, not when it starts** — and that is
pre-existing, not specific to this cell. `cell_run.py` builds its result dict
after `run_cell` returns, so both `when` and `git_head` are end-of-run values.
This cell stamps `314263ea`, a commit made *during* its run (the guard above),
and phase A's own `wl_i2_ad6` stamps `8c4fb32b`, committed roughly 13 hours into
its 24-hour run. The measurements are unaffected in both cases — the commits
touch `bench/cell_run.py` and the investigation's documents, nothing the engine,
the aggregator or the benchmark reads — but **a cell's `git_head` is not
evidence of the tree that produced it**, which is the one thing item 31 wants it
for. `when` as a finish time is fine and is what `cell_table`'s "newest wins"
should order on. Raised for the owner; not changed here, because it would move
what every future cell records.
