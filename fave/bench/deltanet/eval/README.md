# Delta-net engine measurements

Scripts that turn a benchmark run into a recorded, re-derivable result
(`CLOUD_BENCH_PLAN.md` §1.8), and the results they produced. Run everything from
`fave/` with the venv active, `PYTHONPATH=.`, and `net_plumber/build` on `PATH`.

Every result directory holds a `PROTOCOL.txt` declared BEFORE its runs: what
was run, the stopping rules, and the predictions. Read it first.

## Tools

| script | what it does |
|---|---|
| `engine_run.py` | one workload, one engine, one run: verdict from `report.md` (counted), `check_compliance` and rule-load (`switch_command`) seconds from the aggregator log, input hashes and drift, peak RSS and swap per process, JVM GC summary. Stopping rules: `--deadline`, `--memory-floor`. Options: `--mutate[-cell]`, `--keep-every`, `--reuse-inputs`, `--jvm-xmx`. |
| `summarize_runs.py` | the airtel table of §2.13 from `engine_run.py` results |
| `berkeley_series.py` | `wl_berkeley` size series, every engine, sizes k=1000..1 |
| `berkeley_drill.py` | `wl_berkeley` on NDD only: each size generated once in its own process, then run on the reused inputs with an explicit heap |
| `berkeley_table.py` | the §2.15 tables from either of the two above; refuses runs that are not a valid 0/520 (plain) or 1/520 (mutated) |

## Results

| directory | what |
|---|---|
| `results_2026-09-29/` | BDD-APKeep on both airtel traces (§2.13) |
| `results_berkeley_2026-09-29/` | `wl_berkeley` size series, NetPlumber / NDD / BDD (§2.15) |
| `results_berkeley_ndd_2026-09-29/` | the NDD drill, k=30..3 (§2.15) |
| `results_berkeley_slim_2026-09-30/` | k=3 after each harness-slimming step: runs 1–3 (§2.15) |
| `results_berkeley_ndd_2026-10-02/` | the 32 GB machine: k=10 re-anchor, then k=3 and k=2, all completed (§2.15). `limit_class=dev`, not reportable |

**The campaign these tools serve next:** `MEASUREMENT_RUN_PLAN.md` in the repo
root -- every open cell across all five engine configurations, ordered for an
unattended run on the larger machine. `engine_run.py` is the harness that plan's
§3 generalises; its Delta-net results stay re-derivable from it.

**Sizing a larger machine:** `CLOUD_BENCH_PLAN.md` §2.15, "The 32 GB machine
(2026-10-02)" — three measured sizes and the exponents fitted to them. k=1 needs
~43 GB of aggregator; the 19 GB record is the subsection above it.
