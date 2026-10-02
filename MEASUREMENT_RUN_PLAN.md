# The reportable measurement campaign — a run book

**What this is.** The ordered list of the measurements that are open **and worth
running**, written so that a session with **no prior context** can execute it top
to bottom on the 64 GB machine, unattended.

**Who executes it.** A fresh Claude session, from `fave/`, venv active. The
owner's half (the two gitignored inputs, §0) is already taken care of.

**Three owner constraints shape this plan, and each one changed it:**

1. **"Only experiments that are outdated in a meaningful way."** The first
   version of this plan re-measured the whole matrix on the grounds that every
   existing number is `limit_class=dev`. That was wrong, and §5.0 is the triage
   that replaces it: **being dev-class is not by itself a reason to re-run.**
   The triage cuts the long-cell budget from ~72 h to ~26 h.
2. **The runtime environment is not stable** — a container, in a VM, on a shared
   server. §6.1 is what that changes: resumability, a progress trail on every
   long cell, and the rule that **a crash is not a did-not-finish**.
3. **"Running out of memory is a faithful result."** §8.2. An OOM is recorded as
   the cell's outcome and is not retried smaller. It is a bound on the engine,
   and bounds are results.

**The discipline this repo runs on, and this campaign keeps.** Every prediction
is declared **before** its run (§7) and is **never edited afterwards**; a wrong
one is scored as wrong and the reasoning behind it is examined, because that is
where the method errors have been found (`CLOUD_BENCH_PLAN.md` §2.15 has two).
A missing `report.md` is not a clean verdict. A killed run has not been shown
not to finish — it has been shown to have been killed.

---

## 0. Inputs and machine

**The two gitignored inputs — the owner is handling these.** Verify on arrival,
do not assume:

    cd fave/bench/deltanet/traces && sha256sum -c DERIVED.SHA256SUMS

| file | size | needed for |
|---|---:|---|
| `fave/bench/deltanet/traces/berkeley-inserts.csv` | 386 MB | `wl_berkeley`, every size |
| `deltanet-NSDI17-dataset.tar.gz` | 9.6 GB | only if the CSV's hash fails — re-derive with `bench/deltanet/archive_survey/insert_block.sh` |

`fave/bench/wl_berkeley/routes.json` is **generated per size — do not copy it.**

**The machine: 64 GB.** That is enough for everything here, including the one
cell whose feasibility was unknown:

| at k=1 (13,402,846 rules) | estimate | headroom on 64 GB |
|---|---:|---|
| aggregator peak RSS (JVM in-process, so the heap is inside this) | ~43 GB | |
| benchmark process (streamed) | ~1–2 GB | |
| **run total** | **~45 GB** | **~19 GB** |
| generation, in its own process, **runs before, not beside** | ~16 GB | fine |

Sized from the exponent **0.727** fitted to three measured sizes, not from a
linear scaling. `-Xmx 20g`: the live set is *sublinear* (one-heap exponents
0.573 / 0.582, fit 0.575 → ~12.5 GB at k=1), so 20g is ~63% occupancy. The
older sizing's 20–24g came from scaling linearly and is superseded.

**Record the machine before anything runs:** `nproc`, `free -m`, `swapon
--show`, `df -h /dev/shm`, `df -h .`, `java -version`, `git rev-parse HEAD`,
kernel version. **Whether there is swap matters** — the 32 GB box had none, so
an overshoot was the OOM killer rather than a slowdown, and it changes how
`--memory-floor` must be set (§8.2).

---

## 1. Bring-up, and the gate before any measurement

This container ships bare (session memory note `sandbox-bringup.md`); a new one
will too.

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
6. **The gate.** All three green before any number is recorded:
   `./test.sh fast`, `./test.sh integration`, `./test.sh e2e`, with
   `FAVE_REQUIRE_BACKENDS=1` on `integration` so a silently-skipped backend
   cannot read as a pass.
7. **Record the two jar hashes** (`sha256sum apkeep/target/apkeep-1.0.0.jar
   ndd/target/ndd-1.0.1-jar-with-dependencies.jar`). §5.0's triage is keyed to
   them; a rebuild on the new machine will change them, so the comparison is
   against the **source commit**, not the hash (§5.0).

**Do not proceed past a red gate.** Items 34–36 were each a gate that had been
green while running nothing.

---

## 2. The limit class

Item 31, 2026-10-01 (owner): **`limit_class=v5`, reportable — 24 h wall-clock
per cell and 32 GB**, on a machine of about 40 GB or more. **64 GB qualifies**,
so this campaign is `v5` and its results are reportable. Stamp it on every cell
along with the machine description.

Enforcement is **external and identical for every engine**: a harness wall-clock
timeout plus a peak-memory monitor. **Not `RLIMIT_AS`** — it misfires on the
JVM. Engine-internal budgets (VeriFlow-FR's `--vf-budget`) are **0** in every
reportable run.

> **One deliberate exception, on the owner's instruction.** `wl_berkeley` k=1 is
> expected to need ~45 GB — above the 32 GB cell limit. It is run anyway, with
> its memory limit stamped as the machine's rather than 32 GB, because *"you can
> try runs with an expected to be larger footprint"*. The cell is reportable
> with that stamp; it is not reportable as a 32 GB cell.

---

## 3. P1 — the harness — **BUILT 2026-10-02, before the move**

Item 31's one unchecked box, *"Build the harness mechanism and the stamps;
testable here under the dev class"*, is discharged. **Nothing in this section is
left to do on the new machine**; it is here so the next session knows what it
has.

| file | what |
|---|---|
| `bench/cell_metrics.py` | the measurement primitives, **extracted** from `engine_run.py` so both runners measure with one implementation, plus `machine()`, `limit_stamps()` and `outcome()` |
| `bench/cell_run.py` | ONE CELL: any workload, any of the four backends, under the two declared stopping rules, with every stamp |
| `bench/cell_queue.py` | a campaign of cells, consecutive and **resumable** |
| `test/test_cell_metrics.py`, `test/test_cell_run.py` | 40 tests, fast tier, no backend, ~4 s |

**The extraction is verified behaviour-preserving, not asserted.**
`test_stored_gc_and_violations_re_derive` re-derives **every GC summary and
violation count stored in the five committed result directories** — 34 figures,
including the ones `CLOUD_BENCH_PLAN.md` §2.15 quotes — and requires them to
come out identical. It also fails if the glob finds fewer than 20, so it cannot
pass by matching nothing.

**Every stopping rule has been made to fire**, which is what §3 asked for:
wall-clock, the RSS cap, the memory floor, a clean exit, a non-zero exit, and an
outside signal. The last is the one that matters on an unstable machine, and it
has its own test: **an outside SIGTERM produces `status: interrupted`,
`limit_tripped: none`, `outcome: interrupted`** — not a deadline, so the queue
re-runs it instead of the campaign recording a did-not-finish that never
happened.

**What a cell records:** the five item 31 stamps (`limit_class`, `limit_wall_s`,
`limit_rss_mb`, `limit_tripped`, `machine`), the engine's own last source commit
(which is what §5.0's staleness test S1 keys on — a jar hash changes on every
rebuild), `outcome`, a 60-second progress trail, peak RSS per process, swap,
the GC summary, the counted verdict, and the input hashes.

**Three things the build found that the plan had not predicted.** Each would
have cost hours at hour 0 of the campaign, which is the whole argument for
building it before the move:

1. **The aggregator was starting on the wrong interpreter.**
   `scripts/start_aggr.sh` defaults to a bare `python3`
   (`PYTHON="${PYTHON:-python3}"`), so without `PYTHON` exported it ran outside
   the venv and died with `No module named 'filelock'` — which surfaces four
   frames later as `could not connect to fave`, naming nothing. `test.sh`
   exports it; nothing else did. `cell_run` now pins it to its own
   `sys.executable`, so a cell uses one interpreter throughout.
2. **The `-o` opt-in list was incomplete.** TODO item 13a's
   `FAVE_ALLOW_OUT_IFACE` was copied from `test.sh`'s `run_bench`, which opts in
   `wl_up` and `wl_tum` — correct for the five workloads it runs, wrong as a
   suite-wide default. A first smoke run died on `wl_example`. Measured across
   `bench/`: **five** workloads carry such a rule (`wl_example`,
   `wl_generic_fw`, `wl_shadow`, `wl_tum`, `wl_up`). It is now a measured
   default, overridable per cell with `--allow-out-iface`, and stamped either
   way.
3. **A clean benchmark reliably leaves a zombie behind.** The orphan sweep
   counted it, so every clean cell reported a leak — and the one time a real
   orphan appeared, nobody would have looked twice. The sweep now skips
   zombies (dead already, holding nothing), waits a grace period so a tidy
   `_teardown` is not mistaken for a leak, and **labels** what it kills:
   "something outlived the run" is not a finding, "the aggregator outlived the
   run" is.

**Provenance — CLOSED 2026-10-02.** `impl` was `null` for three of the four
backends when the harness was first built, because only VeriFlow-FR stamped
one. All four now declare it through an `IMPL` attribute the base class reads,
and a fork also names the upstream it forked:

| backend | `impl` | `upstream` |
|---|---|---|
| NetPlumber | `authors+fave` | hassel-public master `697b35c9` |
| APKeep, `--apkeep-engine bdd` | `authors+fave` | XJTU-NetVerify/apkeep `7b71bff4` |
| APKeep, `--apkeep-engine ndd` | `authors+fave` | XJTU-NetVerify/NDD `c8414b43` |
| ad6 | `first-party` | — (a fork of nothing) |
| VeriFlow-FR | `reimpl-literature` | — |

The aggregator logs `engine.configuration_stamp()` next to the backend name and
`cell_run.py` parses it back, so a cell records **the engine's whole stamp
verbatim** under `backend_stamp` — a backend that starts declaring something new
needs no change in the harness to have it recorded. Verified live on all five
engine configurations.

`test/test_backend_provenance.py` keeps it closed: a new backend that declares
no provenance fails, an `authors+fave` backend that names no upstream fails, and
— the one that would otherwise rot — **a backend that types a provenance literal
into its own `configuration_stamp` fails**, which is how VeriFlow-FR used to do
it and why the other three could go on declaring nothing without anything
noticing.

**Verified end to end on this machine**, not only in unit tests: a real
`wl_airtel1` NDD cell runs to `outcome: correct`, 0 violations of 256,
`verdict_valid`, with input hashes **identical** to the stored 2026-09-29
`engine_run.py` result — so the two runners agree on the same workload. A
two-cell queue was then run, interrupted, and restarted: done cells skipped, a
cell with a trail and no result re-run, a cell a declared limit stopped left
alone.

**What to run it as:**

    python3 bench/cell_run.py wl_stanford --backend apkeep --apkeep-engine ndd \
        --limit-class v5 --limit-wall 86400 --limit-rss 32768 \
        --memory-floor 2000 --out results/v5/stanford_ndd.json

    python3 bench/cell_queue.py --queue campaign.json --out-dir results/v5

`--dry-run` on the queue prints what it would run and what it would skip, which
is the right first command after any restart.

---

## 4. P2 — repairs that gate specific cells

**Both are done — 2026-10-02, before the move. Neither is left for the new
machine.** What each turned out to be is worth reading, because in both cases
the defect as filed was not the defect as found.

**P2a's workload is nevertheless POSTPONED** (owner, 2026-10-02): the repair
stands, `wl_generic_fw` is measured in no cell. The repair and the measurement
are separate decisions, and only the second is deferred — a workload that
silently generates nothing is a trap whoever next touches it falls into, so
fixing it was worth doing even though no number comes from it now.

### P2a — `wl_generic_fw` (TODO item 32): three defects, not one — FIXED, workload POSTPONED

Filed as *"converts its checks with a script that does not exist"*. True, and
the least of it.

1. **The missing converter.** `_post_preparation` ran
   `bench/wl_generic_fw/reach_csv_to_checks.py`; the script is
   `bench/reach_csv_to_checks.py`. **It is now deleted, not repaired** — it was
   a lossy duplicate of `GenericBenchmark._convert_policy_to_checks`, which has
   already run by that point, and correcting the path would have made the
   workload worse: the call omits `--roles` (a subnet-standing role loses its
   self-check), `--strict` (which decides whether a filled diagonal means
   anything), `-m` (so `--inventory-mapping` falls back to a `fave/inventory.
   json` that does not exist, where the base passes this workload's own
   `bench/empty.json`) and `--cchecks` (so conditional checks land in
   `fave/cchecks.json`, **inside the source tree** — the defect item 37 fixed
   in `inventorygen.py`).
2. **A four-year-old flag regression, found while fixing the first.**
   `6408fcb1` (2021-12-10) converted this benchmark to argparse and inverted
   `-n/--no-internet`'s default on the way: before it, `use_state_snapshots`
   started `False` and `-n` set it `True`; after it the default was `True`, so
   **every default run behaved as though `-n` had been passed.** With
   `use_internet` false the policy translator rejects the default policy's
   `Internet` role (*"Error: Role Internet is unknown"*), so no reachability
   matrix and no `roles.json` were produced, and `topogen.py` and `policygen.py`
   then failed too. The workload has not been generatable since 2021.
3. **Every one of those failures was silent.** `os.system`'s status is a value
   and every caller discarded it. `generic_benchmark.run_step` now raises, and
   `wl_generic_fw` uses it; it is deliberately not retrofitted onto every
   `os.system` in that file, because several steps fail harmlessly by design
   (the base calls `topogen.py`/`routegen.py` for workloads that have none).

**Measured after the fix:** `checks.json` comes out **7 must-reach and 3
must-NOT-reach**, exactly the V0 feature survey's recorded figures, with no
source-tree pollution. The workload now runs: NetPlumber and VeriFlow-FR both
answer **1 violation of 10**, agreeing line for line.

> **One finding handed back, not chased.** That violation is
> `! source.WebServer -> probe.Internet, related:0` — a must-NOT-reach that is
> reached. Both engines agree, so it is the workload's content, not an engine
> artifact, and `wl_generic_fw` has no oracle. Filed under item 32; it wants
> the owner's reading of the ruleset, not a harness change.

> **DECISION (owner, 2026-10-02): the workload is POSTPONED.** The repair
> stands and is not reverted — `wl_generic_fw` is generatable again, and the
> regression that hid it for four years is gone — but **it is measured in no
> cell of this campaign**, and it is out of §5.1's matrix. The reason is the
> finding above: its expected verdict is unknown, so a number from it is a
> column a reader cannot interpret, and publishing one would be the
> "state the denominator" failure in another form. It returns to the matrix
> when the violation has been adjudicated, which is a question about the
> workload's own ruleset and not about any engine.

### P2c — ad6's encoding choices (TODO item 0a): already discharged, and the item was stale

Filed as *"ad6's `wl_stanford` driver hardcodes `Minisat22`, with no acyclic
option, and stamps none of it ... CODE work"*. **That driver does not exist.**
`a51b8124` (Phase 5b) deleted `bench/ad6_faithful_measure.py` along with the
semantic translation, and Phase 6 gave the production path what the driver had
had privately: `--solver`, `--grounding` and `--lite-acyclic` are aggregator
arguments, and `Ad6Adapter.configuration_stamp()` reports all three — with
`lite_acyclic_applies` stating what was **used**, not what was asked for.
Verified live through `cell_run.py`: `--engine-options "--solver cadical195
--grounding rank"` reaches the adapter and the run's own log carries it.

**What remained was not code but a decision that nothing forced.** Taking
whatever the adapter defaults to (`minisat22`, rank) is precisely item 0a's
*"undocumented habit"* — stamped afterwards, never decided. So **`cell_run.py`
now refuses a reportable (`--limit-class v5`) ad6 cell that does not declare
both.** A `dev` cell is not gated, because a dev number is not reportable
anyway; and the gate is ad6-only, because the other three backends' choices
have explicit flags with declared defaults that are stamped either way.

**The campaign's declared ad6 configuration**, in force for every ad6 cell:
`--grounding rank --solver cadical195`, with `--lite-acyclic` added on `wl_i2`
where it is mandatory. Rank because it is the only property-agnostic option and
the only one that scales in query count; flow appears, if at all, as a declared
small-n ablation on `wl_stanford` alone.

### One more the building turned up

`--limit-wall 0` used to read as *"no deadline"* to the sampling loop, so a cell
given one would run unbounded and its result would look like a cell that simply
completed. Item 31 requires every run to carry a declared limit — a run that was
merely killed has not been shown not to finish — so a non-positive wall limit is
now refused.

**Item 0a is a declared GATE before any headline number.** Its live question for
this campaign is **which grounding constraint** ad6 uses: rank and flow are *not
interchangeable* (rank is property-agnostic; flow is reachability-specific and
forces `--fresh-per-query`) and *do not cost the same* (7.0× on wl_stanford N=16
under a matched configuration). **A table that mixes them mixes encodings.**
Rank is the default and the only one that scales in query count. Fix rank for
every ad6 cell in the table; flow appears only as a declared small-n ablation.

**Not a prerequisite: P2d, the `bench` tier's missing verdict gate** (TODO 1s).
`cell_run.py` counts violations itself and compares across engines, which is
stronger. Noted because the campaign produces exactly the oracle data that
closes it — and because of the trap it records: `reachable.json` is **not** an
independent oracle (same generator, same input as `checks.json`), and being
all-reachable it can only catch under-approximation, so gating on it would
certify an over-approximating backend as correct.

---

## 5. What to run, and what not to

### 5.0 The triage — what counts as "meaningfully outdated"

**A cell is re-run only if at least one of these holds:**

* **S1 — the engine changed in a way that can move the number.** Not a rebuild:
  jar hashes change on every build. The test is a **commit touching the engine's
  source** between the result and now.
* **S2 — the workload model changed** (rule count, generator, or translation).
* **S3 — the result is not a valid verdict**: no `report.md`, no `completed task
  check_compliance`, or no stopping rule declared before the run.
* **S4 — never measured.**
* **S5 — the configuration cannot go in a table** (e.g. ad6 mixing rank and flow).
* **S6 — the cell is cheap**, under ~10 minutes. Re-running costs less than
  reasoning about whether to.

**Explicitly NOT a reason to re-run: being `limit_class=dev`.** A dev-class run
that completed far inside the reportable limit measured the same thing; only its
wall-clock is machine-specific, and S6 re-anchors that for every cell where it
is cheap to. For an expensive cell the question is whether the **conclusion**
moves, and §5.3 answers it with a 1-hour probe instead of a 24-hour re-run.

**The engine source history, which is what S1 is keyed to:**

| engine | last source commit | what it was |
|---|---|---|
| `apkeep/` | **a7eb8ad2, 2026-10-01** | VLAN in a destination FIB only where a mechanism carries it (item 33) |
| | a860391e + a38c42a9, 2026-09-27 | the third upstream defect: a NAT's rewrite outputs stop being atomic predicates |
| `net_plumber/` | 23265ec2, 2026-09-30 | item 33: the loop rule kept and declared |
| `ndd/` | d902e0ac, 2026-09-25 | item 28 step 3 |
| `ad6/` | f038b62c, 2026-09-22 | a rule matching both transport ports means AND |
| `fave/veriflow/`, `fave/aggregator/` | cdd5a996, 2026-10-01 | V4 |

**The triage, applied:**

| cell | last result | verdict | decision |
|---|---|---|---|
| `ndd` × `wl_berkeley` k=10/3/2 | 2026-10-02, jars **cd3e8bfd / 34b4ab65 = current** | **not stale** | **not re-run as results.** k=10 and k=3 are re-run inside the drill *as the same-machine anchor* — see below |
| `bdd`/`ndd` × `wl_airtel1`/`2` | 2026-09-29, jar 66cb88d0 | S1, S6 | re-run — minutes |
| `np` × `wl_berkeley` | deadline at k=30 | not stale | not re-run |
| `bdd` × `wl_cloud` | 79.2% of rules at 5 h, bound ≥ 14.6 h, jar 92923bef (2026-09-27) | **S1 and S4** — never completed on a correct binary | **one full run, 24 h limit** (§5.3) |
| `bdd` × faithful-stanford | 53.1% at 8 h (2026-09-26) | S1, but see below | **1 h probe only** (§5.3) |
| `bdd` × faithful-i2 | 62.9% at 24 h (2026-09-26) | S1, but see below | **1 h probe only** (§5.3) |
| `ad6` × `wl_up` flow | > 6 h, no `report.md` | owner decision | **not re-run** — the bound already establishes the crossover |
| everything in §5.1 | various | S6 | re-run — each is minutes |

> **The `wl_berkeley` anchor is not a re-run of a good result.** The k=1 growth
> exponent is only meaningful against sizes measured on the **same machine** —
> that is the confound that cost a k=10 rerun when the series mixed two heaps,
> and mixing two machines is the same error. The drill re-measures k=30, k=10
> and k=3 on the new box as k=1's anchor. It costs ~10 minutes of run time.

### 5.1 The cheap matrix — minutes per cell, re-run under S6

Engine configurations: `np` NetPlumber · `bdd` BDD-APKeep · `ndd` NDD-APKeep ·
`vf` VeriFlow-FR 4+10 (headline) and `vf-plain` (ablation) · `ad6` (rank).

| workload | rules | checks | np | bdd | ndd | vf | ad6 |
|---|---:|---:|---|---|---|---|---|
| `wl_example` | 37 | 7/3 | ✓ | ✓ | ✓ | ✓ 218 ECs | ✓ |
| `wl_ifi` | 223 | 54/245 | ✓ | ✓ | ✓ | ✓ | ✓ |
| `wl_airtel1` | ~42,000 | 210/46 | ✓ | ✓ | ✓ | ✓ | ✓ |
| `wl_airtel2` | ~42,000 | 210/46 | ✓ | ✓ | ✓ | ✓ | ✓ |
| `wl_stanford` (P7a) | 14,821 | 240 | 6.4 s | ✓ | ✓ | 303 s | 1,835 s rank |
| `wl_i2` | 78,047 | 72 | 788 s | ✓ | ✓ | 254 s | ✓ (`--lite-acyclic` mandatory) |
| `wl_up` | 7,836 | 11,902 | 33 s | ✓ | 0.5 s | 788 s | 688 s rank |
| `wl_tum` | 5,116 | **0** | 10 s | ✓ | ✓ | 612 s | ✓ |
| `wl_cloud` | 1,741 | 5/66 | ✓ | **§5.3** | ✓ | ✓ 14,684 ECs | **refuses** (structural) |

**`wl_generic_fw` is NOT in this matrix — POSTPONED (owner, 2026-10-02).** It
is repaired and generatable again (§4, P2a), but its one violation is
unadjudicated, so a cell from it would be a column nobody can read. See §10.

Two notes that change how cells are read:

* **`wl_tum`'s `checks.json` is empty.** It checks nothing. Its cross-engine
  comparison is ONE existential pair (`source.tum` reaches `probe.tum`), since
  its only source and probe share a name. Do not report it as a verdict cell.
* **`vf-plain` does not finish on `wl_up` (2.6e11 ECs predicted) or `wl_tum`
  (1.74e10).** Those are the ablation's *declared* did-not-finishes and are the
  point of it. Run `vf-plain` where plain finished before — `wl_ifi`,
  `wl_cloud`, `wl_example`, `wl_airtel1`, `wl_i2`, `wl_stanford` — plus those
  two once each, to record the limit trip with its EC bound.

**Faithful-VLAN variants are separate cells**, not the same workload:
faithful-stanford (9,491 rules) measures 165 reachable pairs where P7a's
artificial all-to-all policy measures 240; faithful-i2 is 154,974 rules.

### 5.2 `wl_berkeley` — the size series' last size

Three sizes are measured on 32 GB, all answering **0 of 520** with
`verdict_valid`, at `-Xmx16g` on one heap:

| k | rules | rule load s | compliance s | aggregator peak MB | live heap MB |
|---:|---:|---:|---:|---:|---:|
| 10 | 1,351,800 | 76.3 | 28.23 | 7,949 | 3,414 |
| 3 | 4,476,240 | 249.5 | 122.94 | 19,283 | 6,782 |
| 2 | 6,707,829 | 336.5 | 192.48 | 25,969 | 8,582 |

**k=1 (13,402,846 rules) has never been attempted** — it needs ~43 GB against a
~29 GB ceiling on the 32 GB box. On 64 GB it fits with ~19 GB spare.

**Run it as the §2.15 protocol:**

1. Write `bench/deltanet/eval/results_berkeley_ndd_<date>/PROTOCOL.txt`
   **before running**: machine RAM, cores, swap, heap chosen, and §7's
   predictions.
2. `python3 bench/deltanet/eval/berkeley_drill.py --out <dir> --budget 50400
   --jvm-xmx 20g --memory-floor 2000`
   It does k=30 (anchor), k=10 mutated + plain, k=3, k=1, generating each size
   once in its own process and reusing the inputs.
3. `python3 bench/deltanet/eval/berkeley_table.py <dir>`
4. **If k=1 completes:** one BDD run at k=1 as the second engine
   (`engine_run.py wl_berkeley --engine bdd --keep-every 1 --reuse-inputs
   --jvm-xmx 20g ...`), then decide whether `wl_berkeley`'s full-size result is
   the headline. **If it OOMs, that is the result** (§8.2) — do not retry it
   smaller.

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
  doing exactly that.

### 5.3 The long BDD cells — one full run, two probes

This is where the triage saves the most. The three cells were going to be three
24-hour runs. **Two of them are decided by arithmetic already in the tree:**

| | 1 h probe | the long run | gained in between |
|---|---|---|---|
| faithful-stanford | 4,245 / 9,491 (44.7%) | 5,035 (53.1%) at **8 h** | **+790 rules in 7 h** |
| faithful-i2 | 86,709 / 154,974 (56.0%) | 97,553 (62.9%) at **24 h** | **+10,844 rules in 23 h** |

Both take nearly half the model in the first hour and then crawl: the build is
**merge-dominated** (`merge_ms`/`ppm_ms` = 7.3× on stanford, **31.4×** on i2)
and the merge work that keeps the partition small is itself the dominant cost.
faithful-i2's fixed-binary projection is **234–270 h**. A 24-hour re-run would
re-confirm "does not finish" against a **~10× margin**, and the only change
since is a cost multiplier measured at **1.28×** on a 3-router subset (where it
changed no answer and no partition size). **1.28× cannot move a 10× margin.**

**So:**

* **`bdd` × `wl_cloud` — one full run, 24 h limit.** The only one of the three
  that is both stale (S1: jar 92923bef, 2026-09-27, against apkeep's a7eb8ad2 of
  2026-10-01) and *reachable*: 79.2% of rules at 5 h with a tail-rate bound of
  **≥ 14.6 h**. It is also the workload with the only external oracle in the
  suite, and it has never completed on a correct binary.
  `python3 bench/cloud_bdd_measure.py --engine bdd --deadline-s 86400
  --status-every-s 60 --out bench/wl_cloud/eval/bdd_v5_<date>.json`
* **faithful-stanford and faithful-i2 — a 1-hour probe each**, compared at
  **matched rule count** against `probe_stanford_1h.json` / `probe_i2_1h.json`,
  which are already in the tree.
  `python3 bench/faithful_bdd_measure.py --bench stanford --deadline-s 3600
  --status-every-s 60 --out bench/wl_stanford/eval/probe_stanford_1h_v5.json`
  (and `--bench i2`).
  * **Within ~1.5× on rules and `ap_num` → the recorded result stands**, cited
    with its date, its jar and the 1.28× caveat. No full run.
  * **Outside that → the cell is meaningfully outdated**, and *then* it gets a
    24-hour run. Declare which, in the probe's `PROTOCOL.txt`, before running.

**Why a probe is also the right shape for an unstable machine:** a 1-hour window
is far likelier to survive than a 24-hour one, and these two cells' whole
information content is in the first hour anyway.

### 5.4 The LPM guardrail — cheap, mechanical, and open on three workloads

A FIB workload must **prove its evidence can see LPM** (owner, 2026-09-22). The
check: **invert the ordering so the shortest prefix wins, and re-run.** If the
verdict does not change, the workload's gating evidence is blind to rule
priority. `wl_deltanet` failed exactly this and needed a dedicated guard.

**Open for `wl_stanford`, `wl_i2` and `wl_cloud`** — whether each *check set* is
sensitive to an inversion has never been measured (S4), and on `wl_cloud` the
re-prioritisation is called "load-bearing". Two cells each, minutes apiece.

---

## 6. Execution order, and the wall-clock

**Serialise everything whose number is reported.** Peak RSS and wall-clock are
meaningless if two heavy cells share the machine, and the long cells' *rate* is
itself the result.

| phase | what | wall-clock |
|---|---|---|
| **0** | §1 bring-up + green gate; record the machine and the jars | 1–2 h |
| ~~P1~~ | ~~§3 the harness~~ — **BUILT 2026-10-02, before the move** | **0** |
| ~~P2~~ | ~~§4 P2a + P2c~~ — **DONE 2026-10-02, before the move** | **0** |
| **A** | §5.1 cheap matrix + faithful variants + §5.4 LPM guardrail | 6–10 h |
| **B** | §5.2 `wl_berkeley` drill through k=1 | 2–4 h |
| **C** | §5.3: two 1-hour probes, then the one 24 h `wl_cloud` run | ~26 h |
| **D** | tables, `PROTOCOL.txt` results, plan/registry/TODO updates, commits | 2–4 h |

**Total ≈ 2 days**, against ≈ 4–5 before the triage, and now without P1 or P2:
**the new machine starts at phase 0 and goes straight to A.** Phases A and B
produce reportable results on day 1.

**Order rationale.** Cheapest-first: phase A drives every engine path through
the new harness on cells that finish in minutes, so a harness defect costs
minutes rather than a day. B before C because `wl_berkeley` k=1 is the cell
whose feasibility is least certain. **The probes in C run before the 24-hour
run**, so if either says "re-run after all", that is known before the day is
committed.

### 6.1 The environment is not stable — what that changes

A container, in a VM, on a shared server. The 2026-09-29 sandbox death is in
`CLOUD_BENCH_PLAN.md` §2.15's open list with no cause found. Plan for it:

* **A resumable queue.** Each cell writes its result JSON on completion; on
  restart the runner **skips cells that already have a valid result** and
  resumes at the first that does not. The campaign must survive being started
  three times.
* **`setsid nohup` for everything**, so a dying session does not take a run with
  it. A dying *container* still does — which is what the next point is for.
* **A progress trail every 60 s on every cell over ~10 minutes.**
  `cloud_bdd_measure.py` already writes `.status.jsonl` with `bound_h` computed
  off the tail rate. **A crash at hour 20 then still yields a usable lower
  bound** instead of nothing.
* **A crash is NOT a did-not-finish.** This is the distinction the whole
  stopping-rule discipline rests on:
  * killed by the **declared limit** → `status: deadline` / `memory`,
    `limit_tripped: wall|rss`. **Reportable.**
  * killed by the **environment** → `status: interrupted`, `limit_tripped:
    none`. **Not reportable, and re-run.** Recording one as the other would
    manufacture a false did-not-finish, which is the exact error
    `AD6_PLAN.md` §9.34.3 records.
* **Commit as you go**, small and logically connected. A campaign that commits
  only at the end loses everything a crash takes.
* **Order long cells last and singly**, so a crash costs one cell.

---

## 7. Predictions, declared in advance

Scored after the runs; **not edited**. Each names what would falsify it.

1. **`wl_berkeley` k=1 completes on NDD at `-Xmx20g`** on 64 GB, verdict 0 of
   520, `verdict_valid`. *Falsified by:* any other verdict, or a limit trip.
   Confidence: moderate — ~45 GB of ~64 GB is a 30% margin, and the 0.727
   exponent is fitted to three points, not four.
2. **Aggregator peak RSS 41–46 GB.** *Falsified by:* outside that band.
3. **Live heap after GC 11.5–13.5 GB** (exponent 0.575 → 12.5 GB).
4. **The live-set exponent across k=2 → k=1 is 0.50–0.65** — the sublinear
   result holds past 6.7M rules. *Falsified by:* outside that band, which would
   matter more than the run itself, since the k=1 extrapolation rests on the
   exponent being flat across the top of the series.
5. **Rule load ~11 min, compliance ~6 min at k=1.** Low confidence: the k=3→k=2
   load exponent (0.74) against k=10→k=3's (1.05) is the one ragged figure in
   the series and nothing explains it yet.
6. **The re-anchored k=10 and k=3 rows on the 64 GB box land within 15% of the
   32 GB box's**, since neither was memory-bound there. *Falsified by:* a larger
   move — which would invalidate reading the two machines' series together.
7. **`bdd` × `wl_cloud` completes within 24 h**, between 15 and 22 h.
8. **Both faithful probes land within 1.5× of their 2026-09-26 counterparts**,
   so neither faithful cell is re-run. *Falsified by:* either probe outside
   1.5×, which triggers its 24-hour run.
9. **`vf` (4+10) completes every one of the nine; `vf-plain` does not finish on
   `wl_up` or `wl_tum`.**
10. **`ad6` refuses `wl_cloud`** for the structural reason in §1.7.2, rather than
    failing or answering.
11. **At least one of the three LPM inversions (§5.4) does not change the
    verdict**, as `wl_deltanet`'s did not. *Falsified by:* all three flipping.

---

## 8. When a cell does not finish

### 8.1 The stopping rule

* **A killed run is not a did-not-finish** unless the stopping rule was declared
  *before* it started. Either the cell has a declared deadline, or it has a
  profiler trace from which a completion lower bound is computed off the tail
  rate — and the result says **which**.
* **Record** `limit_tripped` ∈ {wall, rss, none}, the elapsed time, and the
  engine's own progress lower bound.
* **Confirm `report.md` exists** and the log carries `completed task
  check_compliance` before believing any count. `grep -c '^- ' report.md` on an
  absent file returns `0`, indistinguishable from "0 violations" — that is how a
  6-hour ad6 run was first misread.
* **Clean up after a killed cell**: an external SIGTERM orphans the aggregator.
* **Never compare totals across different query counts.** State the denominator.
* **A cell that fails for an engine reason is recorded and the campaign
  continues.** Do not stop the queue to debug one engine; note it and move on.

### 8.2 Running out of memory is a faithful result

Owner, 2026-10-02. An OOM is **the cell's outcome**, recorded with its peak RSS
and the machine's size. It is **not** retried with a smaller heap or a smaller
workload, and it is not an environmental failure. *"NDD-APKeep does not fit
64 GB at 13.4M rules"* is a publishable bound.

**Prefer the harness's memory floor to the kernel's OOM killer.** Set
`--memory-floor` low (~2000 MB) rather than conservatively: the floor is there
to **record** the peak, not to protect the run. The harness kills at the floor
and writes the peak RSS it measured; the OOM killer writes a dmesg line and may
take something other than the aggregator. Same faithful outcome, one of them
with a number attached.

**Distinguish the two in the record**, because only the first is the engine's:

* the aggregator hit the floor or was OOM-killed → **`status: memory`**, the
  engine's result;
* the container or VM died → **`status: interrupted`** (§6.1), re-run.

---

## 9. Where the results go

* **Per campaign**: `bench/deltanet/eval/results_<campaign>_<date>/` with
  `PROTOCOL.txt` **first** (declared before the runs), then one JSON per cell,
  its stdout, its aggregator log, its GC log, its status trail, and the report.
  The BDD build cells keep their existing homes (`bench/wl_*/eval/`).
* **Tables**: `berkeley_table.py` for the size series; `summarize_runs.py` for
  the airtel table; a new one for the suite matrix.
* **Prose**: `CLOUD_BENCH_PLAN.md` §2.15 (`wl_berkeley`), `APKEEP_NDD_EVAL.md`
  §2.6 (BDD cells), `VERIFLOW_PLAN.md` §10 (V5), `AD6_PLAN.md` (ad6).
* **`ACCOMMODATIONS.md`**: every *seed* entry this campaign touches gets
  classified and moved to *verified*, or stays a seed and is **not cited**.
* **`TODO.md`**: item 31's boxes, and item 0a's eight if discharged.
* **This file**: §7's predictions scored, and the §5.0 triage updated with what
  the probes said.

---

## 10. What this campaign does NOT cover

Stated so that nobody reads its absence as an oversight.

* **The incremental axis** (item 31). APKeep and VeriFlow are update-optimised;
  measuring them only from zero judges them on a regime they never claimed. It
  needs a per-update latency metric and APKeep incremental wiring
  (`delete_rules` exists only on `NetPlumberAdapter`), and `wl_state_snapshots`
  — the suite's only update stream — is unseeded (P2b). A second campaign.
* **Delta-net as a backend** (open owner question). No code is published; it
  would be a second independent implementation.
* **The five non-airtel Delta-net traces.** They replay to an empty FIB, and
  D8's blockers stand (the fourth field's meaning; no ports in the names).
* **`ad6` × `wl_up` under flow.** Owner decision: the > 6 h bound already
  establishes the crossover.
* **A 24 h re-run of either faithful BDD cell**, unless §5.3's probe says
  otherwise. That is the triage's single biggest saving and its most reversible
  decision.
* **`wl_generic_fw`** — postponed by the owner, 2026-10-02. It is repaired and
  runs (§4, P2a), and it is deliberately measured in no cell: the one violation
  it reports is unadjudicated and the workload has no oracle, so a cell from it
  would carry a number with no expectation to read it against. The repair is
  kept because the alternative is a workload that silently generates nothing;
  the measurement waits on the owner's reading of `default/ruleset` against
  `default/policy.txt`. **The findings are not postponed with it** — they are in
  TODO item 32 and in §4 above, including the four-year flag regression, which
  is the kind of thing that is only ever found once.
* **Variant naming** (item 31) — extending `SOURCE.json` to record preprocessing
  and verdict-identity evidence. Needed before the write-up, not before the runs.
