# The reportable measurement campaign — a run book

**What this is.** The ordered list of every measurement that is open, written so
that a session with **no prior context** can execute it top to bottom on the
larger machine, unattended. TODO item 31 decided the limits and said *"every V5
measurement waits for"* a larger machine; this is what to run when it arrives.

**Who executes it.** A fresh Claude session, from `fave/`, venv active. §0 is the
only part that needs the owner, and it is needed **before** the session starts.

**The discipline this repo runs on, and this campaign keeps.** Every prediction
is declared **before** its run (§7) and is **never edited afterwards**; a wrong
one is scored as wrong and the reasoning behind it is examined, because that is
where the method errors have been found (`CLOUD_BENCH_PLAN.md` §2.15 has two).
A missing `report.md` is not a clean verdict. A killed run has not been shown
not to finish — it has been shown to have been killed (§3 guardrails).

---

## 0. What only the owner can do, before the session starts

**Three inputs are NOT in git** and cannot be re-derived from the clone. Without
them the `wl_berkeley` half of this campaign (§5.4) cannot run at all.

| file | size | why it is not in git | needed for |
|---|---:|---|---|
| `deltanet-NSDI17-dataset.tar.gz` | **9.6 GB** | `.gitignore:14`; third-party dataset | re-deriving the trace below |
| `fave/bench/deltanet/traces/berkeley-inserts.csv` | **386 MB** | `.gitignore:21`; derived, 12,817,902 rows | `wl_berkeley`, every size |
| `fave/bench/wl_berkeley/routes.json` | ~110 MB | generated per size | regenerated; **do not copy** |

**Copy the first two to the new machine.** The CSV alone is enough — the archive
is only needed if the CSV's hash fails. Verify on arrival:

    cd fave/bench/deltanet/traces && sha256sum -c DERIVED.SHA256SUMS

If that fails, re-derive from the archive with
`bench/deltanet/archive_survey/insert_block.sh` (`CLOUD_BENCH_PLAN.md` §2.15,
"The extraction").

**Machine to ask for.** Sized from three measured `wl_berkeley` sizes, not guessed:

| | need | from |
|---|---|---|
| RAM | **≥ 64 GB minimum, 96–128 GB for margin** | aggregator peak RSS scales at exponent 0.727 → ~43 GB at k=1, plus ~16 GB generation (separate process, runs before) |
| | ≥ ~40 GB is *separately* required | item 31 fixes the reportable memory limit at 32 GB only on a machine that can host it with headroom |
| cores | ≥ 8 | generation parallelism; the engines are largely single-threaded |
| disk | ≥ 200 GB free | 9.6 GB archive + 11 GB repo + per-size workload artifacts + result directories |
| swap | **note whether there is any** | the 32 GB box had none, so an overshoot was the OOM killer rather than a slowdown. It changes how `--memory-floor` must be set |

A **128 GB / 16-core** box runs everything here with room to spare and is the
recommendation. 64 GB runs everything but leaves k=1 at ~67% occupancy.

---

## 1. Bring-up, and the gate before any measurement

This container ships bare (see the session memory note `sandbox-bringup.md`); a
new one will too.

1. `./test.sh doctor` — **first command.** Its repair line is accurate for the
   apt half. Its pip half mislabels the tier for `lxml`/`pycosat`/`python-sat`.
2. `sudo -E apt-get update && sudo -E apt-get install -y <doctor's line>` plus
   `poppler-utils`. `-E` matters if egress is proxied.
3. `python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt`, then
   also `lxml==6.1.2 pycosat==0.6.6 python-sat==1.9.dev15 JPype1==1.7.1
   yappi==1.7.6` and `pip install --no-binary :all: pybison==0.6.4` (the
   prebuilt wheel segfaults).
4. If Maven egress is proxied it needs **`~/.m2/settings.xml` with explicit
   `<proxy>` entries** — it ignores `http_proxy`, and fails with no useful
   message.
5. Build, in this order, invoking the **scripts** and not a bare `mvn` (they pin
   `JAVA_HOME` to java-11; runtime is java-21):
   `make -j -C net_plumber/build all` → `sudo make -C net_plumber/build install`
   → `net_plumber/python/build_libnetplumber.sh` → the two jar scripts.
6. **The gate.** All three must be green before any number is recorded:
   `./test.sh fast`, `./test.sh integration`, `./test.sh e2e`.
   `FAVE_REQUIRE_BACKENDS=1` on `integration` turns availability skips into
   failures — use it, so a silently-skipped backend cannot read as a pass.
7. **Record the machine** into the campaign directory before anything runs:
   `nproc`, `free -m`, `swapon --show`, `df -h /dev/shm`, `df -h .`,
   `java -version`, `git rev-parse HEAD`, and the kernel version.

**Do not proceed past a red gate.** Items 34–36 were each a gate that had been
green while running nothing; the cost of believing a vacuous gate here is a
campaign of numbers nobody can report.

---

## 2. The limit class — decided by a rule, not by judgement

Item 31, 2026-10-01 (owner):

* **`limit_class=v5`, reportable** — **24 h wall-clock per cell** (one engine,
  one workload, from zero: model build plus the full check set) and **32 GB**,
  *if the machine has about 40 GB or more*. Otherwise the memory limit is the
  machine's memory minus headroom, and that figure is stamped.
* **`limit_class=dev`, never reportable** — anything else. A dev
  did-not-finish says "longer than the dev limit here", nothing more.

**Decide once, at the top of the campaign, and stamp it on every cell.** With
the recommended machine this is `v5`, 24 h / 32 GB.

Enforcement is **external and identical for every engine**: a harness wall-clock
timeout plus a peak-memory monitor. **Not `RLIMIT_AS`** — it misfires on the
JVM. Engine-internal budgets (VeriFlow-FR's local-EC budget, `--vf-budget`) are
**off**: 0 in every reportable run.

---

## 3. P1 — the harness, which does not exist yet

**This is the one piece of code the campaign cannot start without**, and it is
item 31's one unchecked box: *"Build the harness mechanism and the stamps;
testable here under the dev class."* Verified 2026-10-02: **no occurrence of
`limit_class`, `limit_wall`, `limit_rss` or `limit_tripped` exists anywhere in
the tree.**

**Do not write it from scratch.** `bench/deltanet/eval/engine_run.py` is ~90% of
it already: declared `--deadline` and `--memory-floor` stopping rules, per-process
peak RSS and swap, JVM GC summary, input hashes with drift, violations **counted**
from `report.md`, `verdict_valid` requiring both the report and exactly one
`completed task check_compliance` line. It is bound to the Delta-net family in
exactly three places:

1. its bootstrap calls `bench.deltanet.workload.build(name)`; the other
   workloads are `bench/<wl>/benchmark.py`;
2. it reads `reach.txt` and `SOURCE.json` unconditionally — absent for several
   workloads;
3. `--backend` only shapes `FAVE_ENGINE_OPTIONS` for `apkeep`.

**The work: generalise it into `bench/cell_run.py`,** keeping `engine_run.py`'s
behaviour for the Delta-net workloads (its results are quoted in
`CLOUD_BENCH_PLAN.md` §2.13 and §2.15 and must stay re-derivable).

* **Workload dispatch**: Delta-net family via `workload.build`, everything else
  via the workload's `benchmark.py`. Delta-net-only stamps become optional.
* **Backends**: `net_plumber`, `apkeep` (`--apkeep-engine bdd|ndd`), `veriflow`
  (`--vf-fields 4+10|plain`), `ad6`. One flag per engine config.
* **Item 31's five stamps on every cell**: `limit_wall`, `limit_rss`,
  `limit_class`, `machine`, `limit_tripped`.
* **Plus the result-cell schema** item 31 specifies: `impl` (provenance —
  `authors+fave` / `first-party` / `reimpl-literature`, **stamped by the
  backend, never typed by hand**), the engine's own commit, the accommodations
  in force, the workload variant, and an outcome that distinguishes *correct*
  from *did not finish within the declared limit* from *wrong verdict*.
* **A progress lower bound for every did-not-finish cell**, because a cell that
  trips the 24 h limit is only reportable if it carries one:
  * ad6 — **set `AD6_BRIDGE_PROGRESS_FILE`** for any run expected to exceed an
    hour. Without it a 6-hour run yielded a bound and nothing else, not even
    which query it reached (`AD6_PLAN.md` §9.34.3).
  * APKeep — the profiler trail (`ap_num`, `merge_ms`/`ppm_ms`, rules loaded).
  * VeriFlow-FR — predicted ECs per table.
* **`setsid nohup`** for everything long: a dying session must not take a run
  with it.
* **An externally killed benchmark orphans its aggregator** (SIGTERM bypasses
  `run()`'s `finally`, so `_teardown` never runs, and the pidfile fallback does
  not cover a backend that starts no net_plumber). The harness must clean up
  after a killed cell, or the next cell measures a polluted machine.

**Test it here, under `limit_class=dev`, before the move.** Every stopping rule
has a cheap way to be made to fire: a 5-second deadline on `wl_ifi`, a
memory floor just under the current free memory, a deliberately absent
`report.md`. A limit that has never fired is not a limit.

> **Recommendation: build P1 on the current machine, now.** It is dev-class
> testable here in full, it carries over in git, and it is the single largest
> risk to an unattended run — a harness debugged at hour 0 of a 4-day campaign
> costs the campaign.

---

## 4. P2 — repairs that gate specific cells

Each is small, and each makes a cell meaningless if skipped.

| # | what | gates | source |
|---|---|---|---|
| P2a | **`wl_generic_fw` converts its checks with a script that does not exist.** `_post_preparation` runs `bench/wl_generic_fw/reach_csv_to_checks.py`; the script is `bench/reach_csv_to_checks.py`. `os.system`'s status is ignored, so the step fails silently and the run continues with whatever `checks.json` the base class wrote. Also hard-codes `python3` where the base class uses `PYTHON`. | every `wl_generic_fw` cell | TODO 32 |
| P2b | **`wl_state_snapshots` is not reproducible** — it draws addresses and ports from `random` with no seed. It is the suite's only state-update stream. | the incremental axis, if attempted | TODO 32 |
| P2c | **ad6's `wl_stanford` driver hardcodes `Minisat22`**, with no acyclic option, and stamps none of it. Discharging item 0a's uniformity items there is **code work**, not documentation. | every reportable ad6 `wl_stanford` cell | TODO 0a |
| P2d | **The `bench` tier does not gate on correctness** — `benchmark.py` exits 0 whatever `report.md` says. Every check in all four tier workloads is `EF`, so one reachability oracle plus the per-check negation flag adjudicates the whole tier. **Note the trap:** `reachable.json` is *not* an independent oracle (same generator, same input as `checks.json`), and being all-reachable it can only catch under-approximation — gating on it would certify an over-approximating backend as correct. | reading any verdict as a pass | TODO 1s |

**P2d is not a prerequisite for the campaign** — `cell_run.py` counts violations
itself and compares across engines, which is the stronger check. It is listed
because the campaign will produce exactly the oracle data that closes it.

**Item 0a is a declared GATE before any headline number**, and it is broader than
P2c: eight configuration choices to be discharged or explicitly restated, of
which the live one for this campaign is **which grounding constraint** ad6 uses
— rank and flow are *not interchangeable* (rank is property-agnostic; flow is
reachability-specific and forces `--fresh-per-query`) and *do not cost the same*
(7.0× on wl_stanford N=16 under a matched configuration). **A table that mixes
them mixes encodings.** Rank is the default and the only one that scales in
query count; flow belongs in a small-n sweep only.

---

## 5. The matrix — every open cell

Five engine configurations × the reachability suite. **Every existing number in
the repository is `limit_class=dev` and not reportable**, so this is a
re-measurement of the whole matrix, not a gap-fill. The dev figures below are
quoted only to size the run and to predict the outcome.

Engine configurations: `np` NetPlumber · `bdd` BDD-APKeep · `ndd` NDD-APKeep ·
`vf` VeriFlow-FR 4+10 (headline) and `vf-plain` (ablation) · `ad6` (rank).

### 5.1 The cheap matrix — minutes per cell

| workload | rules | checks | np | bdd | ndd | vf | ad6 |
|---|---:|---:|---|---|---|---|---|
| `wl_example` | 37 | 7/3 | ✓ | ✓ | ✓ | ✓ 218 ECs | ✓ |
| `wl_generic_fw` | 22 | 7/3 | **P2a** | P2a | P2a | P2a | P2a |
| `wl_ifi` | 223 | 54/245 | ✓ | ✓ | ✓ | ✓ | ✓ |
| `wl_airtel1` | ~42,000 | 210/46 | ✓ | ✓ | ✓ | ✓ | ✓ |
| `wl_airtel2` | ~42,000 | 210/46 | ✓ | ✓ | ✓ | ✓ | ✓ |
| `wl_stanford` (P7a) | 14,821 | 240 | 6.4 s | ✓ | ✓ | 303 s | 502.8 s flow / 1,835.4 s rank |
| `wl_i2` | 78,047 | 72 | 788 s | **§5.3** | ✓ | 254 s | ✓ (`--lite-acyclic` mandatory) |
| `wl_up` | 7,836 | 11,902 | 33 s | ✓ | 0.5 s | 788 s | 688.4 s rank; **flow does not finish** |
| `wl_tum` | 5,116 | **0** | 10 s | ✓ | ✓ | 612 s | ✓ |
| `wl_cloud` | 1,741 | 5/66 | ✓ | **§5.3** | ✓ | ✓ 14,684 ECs | **refuses** (§1.7.2, structural) |

Two notes that change how cells are read:

* **`wl_tum`'s `checks.json` is empty.** It checks nothing. Its cross-engine
  comparison is ONE existential pair (`source.tum` reaches `probe.tum`), since
  its only source and probe share a name. Do not report it as a verdict cell.
* **`vf-plain` does not finish on `wl_up` (2.6e11 ECs predicted) or `wl_tum`
  (1.74e10).** Those two are the ablation's *declared* did-not-finishes and are
  the point of the ablation, not failures.

**Run `vf-plain` only where plain finished before** — `wl_ifi`, `wl_cloud`,
`wl_example`, `wl_airtel1`, `wl_i2`, `wl_stanford` — plus the two that do not,
once each, to record the limit trip with its EC bound.

### 5.2 The faithful-VLAN variants

`wl_stanford` faithful-VLAN (9,491 rules) and `wl_i2` faithful (154,974 rules)
are **separate cells**, not the same workload: faithful-stanford measures 165
reachable pairs where P7a's artificial all-to-all policy measures 240.

### 5.3 The long cells — hours to a declared 24 h

These are the cells item 31 named as *"the open long cells"*, plus the two the
BDD campaign left bounded. All are BDD-APKeep except the last.

| cell | last measured | expectation under 24 h |
|---|---|---|
| **`bdd` × `wl_cloud`, post-fix** | 1,405 of 1,773 rules in 5 h, `ap_num` 83,852, tail rate → **≥ 14.6 h** | **completes**, 15–22 h |
| **`bdd` × faithful-stanford** | 5,035 of 9,491 (53%) at 8 h — and that was **pre-fix**, which is 2.8–3.4× cheaper on `wl_cloud` | **does not complete**; record rules loaded + `ap_num` |
| **`bdd` × faithful-i2** | 97,553 of 154,974 (63%) at 24 h; fixed binary projects **234–270 h** | **does not complete**; 60–75% of rules |
| **`ad6` × `wl_up`, flow** | `timeout 21600` fired at > 6 h, no `report.md` | **not re-run** — owner decision: the bound already establishes the crossover |

**The BDD cells are the campaign's wall-clock.** Three cells at up to 24 h each
is ~3 days on its own. They are also the cells whose *rate* is the result, so
they **must not share the machine** with anything else (§6).

**Why these numbers moved, and why that must be said in the write-up:** fixing
the third upstream defect (`Network.refreshRewriteTables()`) made the partition
**~2.6× smaller** and the projected build **~13× longer**, because the merge
work that keeps the partition small is itself the dominant cost. Every §2.6c
figure predates that fix.

### 5.4 `wl_berkeley` — the size series' last size

`wl_berkeley` is a derived workload: the Delta-net `berkeley` insert block as a
static snapshot, `--keep-every k` subsampling it. Three sizes are measured on
32 GB and all answer **0 of 520** with `verdict_valid`:

| k | rules | rule load s | compliance s | aggregator peak MB | live heap MB |
|---:|---:|---:|---:|---:|---:|
| 10 | 1,351,800 | 76.3 | 28.23 | 7,949 | 3,414 |
| 3 | 4,476,240 | 249.5 | 122.94 | 19,283 | 6,782 |
| 2 | 6,707,829 | 336.5 | 192.48 | 25,969 | 8,582 |

All at `-Xmx16g`, one heap across the series. **k=1 (13,402,846 rules) has never
been attempted** — it needs ~43 GB of aggregator against a ~29 GB ceiling on the
32 GB box.

**Run it as the §2.15 protocol, in this order:**

1. Write `bench/deltanet/eval/results_berkeley_ndd_<date>/PROTOCOL.txt`
   **before running**: machine RAM, cores, swap, the heap chosen, and the
   predictions from §7.
2. The drill, which generates each size once in its own process and reuses the
   inputs:
   `python3 bench/deltanet/eval/berkeley_drill.py --out <dir> --budget 50400
   --jvm-xmx 20g --memory-floor 3000`
   It does k=30 (anchor), k=10 mutated + plain, k=3, k=1. **Its k=30/k=10 rows
   re-anchor this machine's timings against the 32 GB box's** — that re-anchor
   is what made the k=3 heap choice before the run, and is worth the time.
3. `python3 bench/deltanet/eval/berkeley_table.py <dir>`
4. **If k=1 completes:** one BDD run at k=1 as the second engine
   (`engine_run.py wl_berkeley --engine bdd --keep-every 1 --reuse-inputs
   --jvm-xmx 20g ...`), then decide whether `wl_berkeley`'s full-size result is
   the headline.

**`-Xmx 20g`, not the 24g the older sizing says.** The live set is *sublinear*
in rules (one-heap exponents 0.573 and 0.582, fit 0.575 → ~12.5 GB at k=1), so
20g is ~63% occupancy. The earlier 20–24g came from scaling linearly.

**NetPlumber is out of this series** — rule load scales at size^2.2–2.6 and it
already deadlines at 459k rules.

**Gotchas that have each cost a run:**

* Set `-Xmx` explicitly; the JVM default is a quarter of RAM and its OOM reads
  like an engine limit.
* **`--mutate` cannot be combined with `--reuse-inputs`** (refused). A mutated
  run regenerates its own inputs, which must then be regenerated plain.
* `bench/wl_berkeley/` holds whatever size was generated last (stamped
  `keep_every` in `SOURCE.json`); `--reuse-inputs` refuses a mismatch.
* `bench/wl_berkeley/np.conf` lowers NetPlumber's per-rule logging, which is
  what keeps a 64 MB `/dev/shm` a non-issue (high-water 1 MB measured). Keep it
  if `/dev/shm` is small on the new machine too.
* **"RSS minus committed heap" is not the Python side** and is not a quantity at
  all: committed heap is reserved address space, not touched pages, so raising
  `-Xmx` alone can drive it negative. This plan's own method was corrected for
  doing exactly that (`CLOUD_BENCH_PLAN.md` §2.15).

### 5.5 The LPM guardrail — cheap, mechanical, and open on three workloads

A FIB workload must **prove its evidence can see LPM** (owner, 2026-09-22). The
check: **invert the ordering so the shortest prefix wins, and re-run.** If the
verdict does not change, the workload's gating evidence is blind to rule
priority. `wl_deltanet` failed exactly this and needed a dedicated guard.

**Open for `wl_stanford`, `wl_i2` and `wl_cloud`** — whether each *check set* is
sensitive to an inversion has never been measured, and on `wl_cloud` the
re-prioritisation is called "load-bearing". Two cells each (correct order,
inverted), minutes apiece. Run them: a headline table resting on a check set
that cannot see LPM is worth less than the cost of finding out.

---

## 6. Execution order, and the wall-clock

**Serialise everything whose number is reported.** Peak RSS and wall-clock are
both meaningless if two heavy cells share the machine, and the long BDD cells'
*rate* is itself the result, so they cannot be parallelised either.

| phase | what | wall-clock |
|---|---|---|
| **0** | §1 bring-up + green gate; record the machine | 1–2 h |
| **P1** | §3 the harness, if not already built | 3–5 h |
| **P2** | §4 P2a + P2c | 1–2 h |
| **A** | §5.1 the cheap matrix + §5.2 faithful variants + §5.5 LPM guardrail | 6–10 h |
| **B** | §5.4 `wl_berkeley`, the drill through k=1 | 4–8 h |
| **C** | §5.3 the three long BDD cells, serialised | **up to 72 h** |
| **D** | tables, `PROTOCOL.txt` results, `CLOUD_BENCH_PLAN.md` / `ACCOMMODATIONS.md` / TODO updates, commits | 2–4 h |

**Total ≈ 4–5 days**, dominated by phase C. Phases A and B produce reportable
results on day 1–2; **C is where the campaign is left running unattended.**

**Order rationale.** A before B before C, cheapest-first: phase A exercises every
engine path through the new harness on cells that finish in minutes, so a harness
defect costs minutes rather than a day. B before C because `wl_berkeley` k=1 is
the one cell whose *feasibility* is unknown — if it fails, there is time to react
while C has not yet consumed three days.

**Commit as you go**, small and logically connected, per the owner's standing
permission. A campaign that commits only at the end loses everything a crash
takes.

---

## 7. Predictions, declared in advance

Scored after the runs; **not edited**. Each names what would falsify it.

1. **`wl_berkeley` k=1 completes on NDD at `-Xmx20g`**, verdict 0 of 520,
   `verdict_valid`. *Falsified by:* any other verdict, or a limit trip.
2. **Its aggregator peak RSS is 41–46 GB** (exponent 0.727 from three sizes).
   *Falsified by:* outside that band.
3. **Its live heap after GC is 11.5–13.5 GB** (exponent 0.575 → 12.5 GB).
   *Falsified by:* outside that band.
4. **The live-set exponent across k=2 → k=1 is 0.50–0.65**, i.e. the sublinear
   result holds past 6.7M rules. *Falsified by:* outside that band — which would
   matter more than the run itself, since the k=1 extrapolation rests on the
   exponent being flat across the top of the series.
5. **Rule load ~11 min and compliance ~6 min at k=1.** Low confidence: the
   k=3→k=2 load exponent (0.74) against k=10→k=3's (1.05) is the one ragged
   figure in the series, and nothing explains the spread yet.
6. **`bdd` × `wl_cloud` completes within 24 h**, between 15 and 22 h.
   *Falsified by:* a limit trip.
7. **`bdd` × faithful-i2 does not complete**, reaching 60–75% of 154,974 rules
   at 24 h. *Falsified by:* completion, or outside that band.
8. **`bdd` × faithful-stanford does not complete within 24 h.** Low confidence —
   it was at 53% at 8 h *pre-fix*, and the fix's cost multiplier is known only
   on `wl_cloud` (2.8–3.4×) and on a 3-router subset (1.28×). The spread between
   those two is the whole uncertainty.
9. **`vf` (4+10) completes every one of the nine; `vf-plain` does not finish on
   `wl_up` or `wl_tum`.**
10. **`ad6` refuses `wl_cloud`** for the structural reason in §1.7.2, rather than
    failing or answering.
11. **At least one of the three LPM inversions (§5.5) does not change the
    verdict**, as `wl_deltanet`'s did not. *Falsified by:* all three flipping.

---

## 8. When a cell fails

* **A killed run is not a did-not-finish** unless the stopping rule was declared
  *before* it started. Either the cell has a declared deadline, or it has a
  profiler trace from which a completion lower bound is computed off the tail
  rate — and the result says **which**.
* **Record what tripped**: `limit_tripped` ∈ {wall, rss, none}, the elapsed
  time, and the engine's own progress lower bound.
* **Confirm `report.md` exists** and the log carries `completed task
  check_compliance` before believing any count. `grep -c '^- ' report.md` on an
  absent file returns `0`, indistinguishable from "0 violations" — that is how a
  6-hour ad6 run was first misread.
* **Clean up after a killed cell**: an external SIGTERM orphans the aggregator.
* **Never compare totals across different query counts.** State the denominator.
* **A cell that fails for an environmental reason is re-run, not recorded.** A
  cell that fails for an engine reason is recorded, and the campaign continues —
  do not stop the queue to debug one engine, note it and move on.

---

## 9. Where the results go

* **Per campaign**: `bench/deltanet/eval/results_<campaign>_<date>/` with
  `PROTOCOL.txt` **first** (declared before the runs), then one JSON per cell,
  its stdout, its aggregator log, its GC log, and the report.
* **Tables**: `berkeley_table.py` for the size series;
  `summarize_runs.py` for the airtel table; a new one for the suite matrix.
* **Prose**: `CLOUD_BENCH_PLAN.md` §2.15 for `wl_berkeley`,
  `APKEEP_NDD_EVAL.md` §2.6 for the BDD cells, `VERIFLOW_PLAN.md` §10 for V5,
  `AD6_PLAN.md` for ad6.
* **`ACCOMMODATIONS.md`**: every *seed* entry this campaign touches gets
  classified and moved to *verified*, or stays a seed and is **not cited**.
* **`TODO.md`**: item 31's boxes, and item 0a's eight if discharged.

---

## 10. What this campaign does NOT cover

Stated so that nobody reads its absence as an oversight.

* **The incremental axis** (item 31). APKeep and VeriFlow are update-optimised;
  measuring them only from zero judges them on a regime they never claimed. It
  needs a per-update latency metric and APKeep incremental wiring
  (`delete_rules` exists only on `NetPlumberAdapter`). **`wl_state_snapshots` is
  the suite's only update stream and is unseeded (P2b).** This is a second
  campaign.
* **Delta-net as a backend** (open owner question). No code is published; it
  would be a second independent implementation.
* **The five non-airtel Delta-net traces.** They replay to an empty FIB, and
  D8's blockers stand (the fourth field's meaning; no ports in the names).
* **`ad6` × `wl_up` under flow.** Owner decision: the > 6 h bound already
  establishes the crossover.
* **Variant naming** (item 31) — extending `SOURCE.json` to record preprocessing
  and verdict-identity evidence. Needed before the write-up, not before the runs.
