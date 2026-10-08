# Retired benchmarking code

Nothing here is invoked by `./test.sh`, by `bench/cell_run.py`, or by any
committed campaign protocol. It is kept because it records how measurements
were made before the current harness, and in one case which dependency choice
a comparison settled.

**Being here does not mean "broken", and it does not mean "works" either.**
The two kinds are mixed, so check before you run something:

- **The pre-V5 shell pipeline** — `run_fave_benchmarks*.sh`,
  `eval_fave_*.sh`, `run_fffuu_benchmarks.sh`, `eval_fffuu_benchmarks.sh`,
  the per-workload drivers (`tum*.sh`, `up*.sh`) and the six `.awk` statistics
  helpers they pipe through. This was how FaVe was benchmarked before cells;
  it is superseded by `bench/cell_run.py` and `bench/cell_queue.py`, which
  stamp limits, record a verdict and produce the artifacts a protocol cites.
  These scripts are intact and self-contained — they reference each other by
  `bench/legacy/…` — but they are not run by anything current and are not
  gated, so treat them as unverified.

- **`microbench_parsers.py`** — a 2019 experiment comparing three ip6tables
  parsing approaches. It **does not run** and has not since 2021; its module
  docstring says exactly what would have to be undone to revive it. Kept for
  its result, which is still in force: pybison won, and that is why FaVe's
  `iptables/parser.py` is a Bison parser and why `setup.sh` builds
  `pybison==0.6.4` from source.

To retire something else here, move it and leave a note at the top of the file
saying when, what it measured, and what stopped it working. A retired file with
no such note is indistinguishable from one that was simply abandoned.
