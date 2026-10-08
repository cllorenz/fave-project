# Repository conventions

Small rules that keep the measurement record readable. They are written down
because every one of them was violated at least once, and each violation cost
something.

**These apply to directories and files created from now on.** Nothing already on
disk is renamed to match — see "Never rename a result directory" below, which is
the most load-bearing rule here.

## Result directories

```
results_<class>_<subject>_<YYYYMMDD>/
```

- **`<class>`** — the limit class the cells were run under: `v5` (24 h wall,
  32 GB RSS, reportable) or `dev` (never reportable). Delta-net eval runs predate
  the classes and omit this field.
- **`<subject>`** — what distinguishes this run from the main campaign: the thing
  measured (`vlan_guardrail`, `lpm_guardrail`, `i2_ad6_flow`), or `remeasure` /
  a defect id (`f1fix`, `o1afix`) for a re-run.
- **`<YYYYMMDD>`** — the date the run started. **No hyphens, always present.**

Hyphens are banned in the date because both forms were used and the result was
`results_berkeley_ndd_20261002` and `results_berkeley_ndd_2026-10-02` sitting
next to each other in `fave/bench/deltanet/eval/` — two different runs whose
names differ only by punctuation. The date is mandatory because `results_v5_f1fix`
and `results_v5_o1afix` cannot be ordered without opening them.

A superseded directory keeps its name and gains a `SUPERSEDED.txt` saying what
replaced it and why. `superseded_shm64/` predates this and is the exception.

## Per-cell artifacts

One cell writes a group of files sharing a stem:

```
<workload>_<engine>.json          the result record -- verdict, cost, stamps
<workload>_<engine>.report.md     the verdict FaVe produced
<workload>_<engine>.aggregator.log
<workload>_<engine>.status.jsonl  the progress trail, one line per interval
<workload>_<engine>.stdout
<workload>_<engine>.gc.log        JVM engines only
<workload>_<engine>.ad6_progress.log   ad6 only
```

`<engine>` is one of `np`, `ndd`, `bdd`, `ad6`, `vf`, `vfplain` — the keys in
`bench/campaigns/cell_table.py`, which is what makes a cell appear in the matrix.
**An arm of a guardrail gets its own stem** (`wl_i2_ndd_faithful`,
`wl_i2_ndd_novlan`), because two arms are two cells and the table must be able to
tell them apart. `cell_table.py` keys on the *stamps inside* the JSON, not on the
filename, so a descriptive stem does not drop a cell from the matrix.

## A run directory also carries its own protocol and findings

- **`PROTOCOL.txt`** — written and committed **before the run starts**, including
  the falsifiable predictions. A prediction added afterwards is not a prediction.
- **`FINDINGS.md`** — written after, scoring each prediction held or failed.

## Never rename a result directory

Once a result directory is committed, its name is part of the record:

- committed `PROTOCOL.txt` files name the exact commands that reproduce the run;
- `bench/campaigns/RESULTS.md` prints the `cell_table.py` invocation that
  generates the matrix, `--over` directory names included;
- artifacts cite each other, and other documents cite them.

Renaming to match a newer convention would make all of that silently wrong, and
editing the artifacts to agree would be rewriting evidence to suit a later tidy-up.
Fix the convention forward; leave the record alone. **The same rule is why
`bench/cell_run.py`, `bench/reach_csv_to_checks.py` and the other scripts named in
committed protocols stay where they are**, even though `bench/` would read better
reorganised: those paths are recorded in protocols as runnable commands.

## Where things live

| | |
|---|---|
| reference documents | `docs/` — see [`INDEX.md`](INDEX.md) |
| the live QA backlog | `../TODO.md` (root) |
| measurement harness | `fave/bench/` — the scripts protocols name |
| one-off analysis and oracles | `fave/bench/analysis/` |
| retired benchmarking code | `fave/bench/legacy/` — the pre-V5 shell pipeline and retired experiments; see its `README.md` |
| campaign results | `fave/bench/campaigns/` — start at `RESULTS.md` |
| Delta-net eval results | `fave/bench/deltanet/eval/` |
