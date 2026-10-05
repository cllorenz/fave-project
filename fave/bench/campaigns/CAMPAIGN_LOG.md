# V5 reportable campaign — running log

Kept by the session executing `MEASUREMENT_RUN_PLAN.md` unattended while the
owner is out of office, with a 64 h experiment budget
(2026-10-02 ~14:30Z → 2026-10-05 ~06:45Z). Every decision taken that the plan
did not already fix is here, so that none of it has to be inferred from a
result afterwards.

## Phase 0 — bring-up and the gate. DONE 2026-10-02.

The container shipped bare, as §1 predicted. `.yolobox.toml`'s `[customize]
packages` block — which exists to prevent exactly that — is commented out in
its entirety; worth the owner's attention, because every fresh sandbox will pay
the same bring-up cost.

Gate, all green before any number was recorded:

| | |
|---|---|
| `./test.sh doctor` | PASSED (3 advisory absences) |
| `./test.sh fast` | PASSED — 859 passed, 3 skipped |
| `FAVE_REQUIRE_BACKENDS=1 ./test.sh integration` | PASSED |
| `./test.sh e2e` | PASSED — veriflow == netplumber, 27 violation lines |

Machine and artifacts: `MACHINE.txt`, `ARTIFACTS.txt`. 16 cores, 62 GB, **no
swap**, `/dev/shm` 64 MB.

### Three defects found in phase 0 and the first minutes of phase A

**1. `build_libnetplumber.sh` leaves a `-fPIC` NetPlumber in `build/`.** It
cleans the tree and rebuilds the core with `-fPIC` to link the `.so`, so
`build/net_plumber` no longer matches the `/usr/bin` copy `make install` placed
there one step earlier. Its comment says PIC "does not affect the net_plumber
binary", which is true of behaviour and not of wall-clock — and §1.8's
invocation contract puts `build/` **first** on `PATH`. All 9 NetPlumber cells
would have measured a PIC build against a table of `-O3` numbers, undeclared.
Undone after the `.so` is linked; both binaries are `f09dc34b`.

**2. A workload is allowed to check nothing, and `wl_tum` does.** `cell_run`'s
summary line indexed `result['checks']` directly; `wl_tum` has no `checks.json`
at all (§5.1: "it checks nothing"), so the cell ended in `KeyError` — *after*
its result JSON was written. The data survived; the summary and the exit status
did not, which is the worst shape for it, because the log then shows a
traceback for a cell that is fine. Fixed with `.get`, which cannot move a
number. `wl_tum`'s `outcome: error` is **not** a defect and is left alone: with
no checks there is no `check_compliance` task, so `verdict_valid` is false and
the harness is correctly saying "no readable verdict" — §5.1's "do not report
it as a verdict cell".

**3. A 64 MB `/dev/shm` was failing cells as if the engine had died.** The one
that cost real time, and the one most worth reading. `wl_stanford_np` ended
`status=error` after 91.2 s — against the **6.4 s** §5.1 records — with
`ConnectionResetError: Connection reset by peer`. net_plumber had died.

It was the machine. FaVe writes every runtime log under `/dev/shm/np`, and one
large cell exceeds 64 MB on its own: `wl_i2` held a 33 MB `stdout.log` while
`inv.log` rotated through three 10 MB backups — ~73 MB in a single run.
`/dev/shm` was observed at **100% with a cell still running**. `./test.sh
doctor` had warned about this and the warning was read as advisory.

*The fix, and why this one.* The container cannot remount `/dev/shm`
(privileges), so `/dev/shm/np` is a symlink to `/var/tmp/np-logs` on the 70 GB
disk, re-established by the driver on every start because a container restart
recreates `/dev/shm` empty. It changes **where the bytes land and nothing about
what is logged** — lowering log levels, as `wl_berkeley`'s own `np.conf` does,
would change instrumentation cost and therefore wall-clock, which is a reported
number here. The driver now refuses to start with under 10 GB behind that path.

*Verified, not assumed:* `wl_stanford_np` re-ran at **6.496 s** against the
historical **6.4 s**, `verdict_valid: True`. That the cell returned to its
recorded value is independent evidence both that the diagnosis was right and
that moving the logs to disk does not distort the measurement (~1.5%, noise).

**4. A failed cell inherited another engine's provenance.** Same cell, separate
defect. `wl_stanford_np` recorded `impl: reimpl-literature` with
`backend: netplumber` — VeriFlow-FR's value on a NetPlumber row. Its aggregator
died before stamping, so the harness read the `backend: veriflow` line an
earlier **e2e test run** had left in `/dev/shm/np`, and reported it with
`impl_source: backend configuration stamp`. Item 31 asks for provenance stamped
rather than hand-typed so "a table cannot mislabel a row"; a stale log defeats
that just as well and more quietly, because the value is genuine and merely
belongs to someone else. `backend_stamp` now takes the backend the cell asked
for and reports nothing when the log names a different one.

The eight cells run before the fix are in `superseded_shm64/` with their
README — not deleted, because they are the evidence, and a result thrown away
without a reason cannot be told from one never taken. All eight, not just the
two that visibly failed: `/dev/shm` hit 100% during the sequence and the six
that completed cannot be *shown* to have been unaffected.

## Phase A — the cheap matrix, 51 cells. RUNNING from 2026-10-02 15:03Z.

Queue `v5_phase_a_main.json`; results in `results_v5_20261002/`; protocol
declared in that directory before the first cell.

`wl_up_vfplain` and `wl_tum_vfplain` are **deferred to the end of the
campaign** with their declared 24 h limits untouched — see the phase A protocol
for the full reasoning. In short: §5.1 declares both to be did-not-finishes, so
the two of them are 48 h inside a phase §6 budgets at 6–10 h, and
`VERIFLOW_PLAN.md` §4.6 stamps the EC bound *before* enumerating, so their
content lands in the first minutes. Only their position in the order moved.

## Budget reckoning, 2026-10-03 05:10Z — and what gets dropped

49 h of the 64 h budget remain. Phase A is at 42/51 after 14 h, and **one cell
is responsible for almost all of it**: `wl_i2_ad6` has run 13.2 h and is at
query **16 of 72**, projecting ~59 h. The other 42 cells total **0.8 h**
between them.

**Decision: `wl_i2_ad6` runs to its declared 24 h wall** (~15:55Z today) and is
recorded as a did-not-finish. Killing it now would save ~11 h and produce
nothing reportable: §8.1 is explicit that a run is a did-not-finish only
against a limit declared before it started, and the v5 limit class is 24 h
precisely because that is what APKeep and Delta-net report against. "Did not
finish in 13.2 h" is not comparable with the literature; "did not finish in
24 h" is. The progress trail carries the lower bound either way.

Note this is itself a result against the plan: §5.1's matrix marks ad6 × `wl_i2`
as **✓ (`--lite-acyclic` mandatory)**, i.e. expected to complete.

**What this costs, and the order things get dropped in.** Remaining after
`wl_i2_ad6`: 8 BDD cells, then phase B (~5 h), then phase C (~29 h). That is
close to the whole remaining budget.

1. **Phase E — the two deferred `vf-plain` cells — is dropped.** It was already
   the lowest-value item (24 h apiece to upgrade "did not finish in N h" to
   "within 24 h", with the EC bound already stamped in the first minutes). The
   driver's own guard will skip it for want of 25 h, and that is the right
   outcome. They are recorded as NOT RUN, claiming no did-not-finish.
2. **Phase C's `wl_cloud` 24 h run is KEPT**, and its value has gone up since
   it was scheduled: F4-R makes `wl_cloud` the workload where NetPlumber is the
   lone outlier against NDD and ad6, so BDD-APKeep is a **fourth independent
   engine on exactly the disputed cell**. It now serves the investigation the
   owner has asked for, not only the triage.
3. **The owner's investigation of the findings is started NOW**, in the
   wall-clock `wl_i2_ad6` is burning, limited to work that does not contend:
   reading code and the artifacts already on disk. §6's serialisation rule
   forbids running cells beside a measured one, and nothing here does. Anything
   needing a run is queued for after the campaign.

## Status 2026-10-05 05:00Z — phase A at 50/51, and what the budget bought

**Still running, nothing stopped.** `wl_i2_bdd` is the last cell of phase A,
12.85 h into its declared 24 h limit.

**Three cells consumed the campaign.** Of 49.0 h of measured wall over 50
cells, **48 h is three cells** and the other 47 total about one hour:

| cell | | §5.1 said |
|---|---|---|
| `wl_i2_ad6` | **24.00 h, `did_not_finish`, wall** | ✓ (`--lite-acyclic` mandatory) |
| `wl_stanford_bdd` | **24.00 h, `did_not_finish`, wall** | ✓ |
| `wl_i2_bdd` | 12.85 h so far, still running | ✓ |

**That is the campaign's largest single result.** §5.1 is "the cheap matrix —
**minutes per cell**", and §6 budgets phase A at 6–10 h. Three of its cells are
24-hour did-not-finishes, every one of them marked ✓ (expected to complete) in
the matrix. The triage in §5.0 was built on that matrix being right about which
cells are cheap; on this machine it is wrong about three of them, and the error
is not small — it is the difference between 10 h and 72 h.

**Consequences for the rest of the plan, stated plainly.**

* **Phases B and C did not run and will not.** 110 minutes of the 64 h budget
  remain and the driver's guards need 5 h for B and 26 h for C. Those guards
  are doing the right thing: starting `wl_cloud`'s 24 h run with two hours left
  would produce a cut-off run, and §8.1 is explicit that such a run has not been
  shown not to finish. **No `wl_berkeley` k=1, no `wl_cloud` BDD, no faithful
  probes.** None of them is recorded as anything; they were never started.
* **The F1 fix is written and NOT applied.** Applying it now means running
  APKeep cells beside `wl_i2_bdd`, which §6 forbids for a measured cell.
* The investigation slot is in the driver on disk but not in the *running*
  driver (atomic rename), so it will not fire by itself.

**What happens next without intervention:** `wl_i2_bdd` runs to completion or
to its 24 h wall (~16:00Z today), the driver skips B, C and phase E on its
guards, and stops. That is ~9 h past the 64 h budget, and it is the correct
behaviour under the owner's "do not stop anything prematurely" — the cell was
started inside the budget and its limit was declared before it began.
