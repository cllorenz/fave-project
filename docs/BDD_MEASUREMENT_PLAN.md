# BDD-APKeep measurement campaign — 56 h budget

**Owner:** Claas Lorenz. Agreed 2026-09-25. Companions:
[`CLOUD_BENCH_PLAN.md`](CLOUD_BENCH_PLAN.md) §1.7.3,
[`APKEEP_NDD_EVAL.md`](APKEEP_NDD_EVAL.md) §2.6a/§2.6b, [`TODO.md`](../TODO.md) item 29.

## 0. Why this campaign exists

Two things happened on 2026-09-25 that invalidate the BDD half of the engine
comparison as it currently stands.

1. **`APKeeper.addPredicate` had a use-after-free.** `parta` was left
   unreferenced across allocating calls; JDD's GC could collect it mid-split, and
   the element loop then handed a dead node handle to `nat()`. Fixed
   (`apkeep/FAVE_CHANGES.md`), confirmed by experiment.
2. **`NATElement.updateRewriteTableIfPresent` swallows the consequences** in an
   upstream `// TODO Auto-generated catch block`, so a build continues over a
   half-updated AP partition. **This is still open and is the more serious of the
   two** — the crash was the *good* outcome; the bad one is a wrong answer.

Consequence: every BDD number in this tree was produced by a binary with both
defects present. On wl_cloud that demonstrably mattered — the build crashed at
11 min, and the documents called it "intractable" for months on that basis. With
the fix it reaches 96 % of rules in 4 h and was ~20–30 min from completing.

## 1. What the budget buys

Runs are **serial**. The repo has a contention incident on record (546 s vs 673 s
for the same tier), and these are the numbers most likely to be quoted.

| # | run | budget | question it answers |
|---|---|---:|---|
| 0 | Regression gate vs the patched jar | 1 h | did the two fixes break anything |
| 1 | **wl_cloud BDD, 6 h deadline** | 6 h | completion: `ap_num`, build **and query** time |
| 3 | Loud-catch probes: faithful-stanford + faithful-i2, 1 h each | 2 h | de-risk #4/#5 before spending 32 h |
| 4 | faithful-stanford BDD, 8 h, single run | 8 h | bound was ≥ 3.8 h — does it now complete? |
| 5 | faithful-i2 BDD, 24 h | 24 h | bound was ≥ 18.7 h, possibly an artifact |
| | **committed** | **41 h** | |
| | slack | 15 h | estimates are soft; re-runs come out of here |

## 2. The loud catch is part of the instrument, not a separate task

`updateRewriteTableIfPresent` is made to **rethrow** before any run below, so
every result in this campaign carries the guarantee that no corruption was
silently swallowed to produce it. `Element.updatePortPredicateMap` already
declares `throws Exception`, so the change is a `throws` clause on the two
declarations and deleting the catch.

**This makes run #1 more valuable, not riskier.** Under the old catch, corruption
in the final 4 % or in the query phase would have produced `status: "completed"`
with a silently wrong answer and no signal at all. If the rethrow fires instead,
that is a finding, and the existing `bdd_build_reffix2.*` artifacts already bank
the 96 %-at-4 h result.

Run #0 therefore gates **both** fixes at once. If it goes red because something
relied on the swallow, that is itself worth knowing before 41 h are spent.

## 3. Protocol — every run

Per `APKEEP_NDD_EVAL.md` §2.6b, and non-negotiable after this session:

- A **declared deadline**, enforced by the driver's watchdog, never an operator
  kill. `status` is `completed`, `deadline` or `error` — nothing else.
- `APKEEP_BUILD_PROFILE` on, trace committed.
- **stderr preserved and committed.** §2.6b's faithful runs did not do this, which
  is why it cannot now be established whether they were silently corrupt.
- Inputs and jar pinned by sha256 in the result.
- A trend read over **several windows**, never off a single sample. Windows that
  still span the whole run claim nothing.

Drivers: `fave/bench/cloud_bdd_measure.py` (#1), `fave/bench/faithful_bdd_measure.py`
(#3–#5, needs the same deadline/status/stderr treatment before use).

## 4. What is excluded, and why

- **#2 (wl_cloud NP + NDD controls) and #6 (wl_up 3-engine, repeats)** — dropped
  by the owner 2026-09-25: *"the numbers measured in this environment are
  indicative only"*. #6's entire purpose was to make §2.12's figures citable, so
  it loses its point under that ruling.
- **Repeats generally.** Single runs throughout, by the same ruling. Every result
  from this campaign inherits the standing §2.12 caveat: order-of-magnitude
  figures that justify engine choices, not benchmark-table numbers.
- **NDD re-runs.** Seconds, already exact, no new information.
- **ad6.** Current and complete.
- **The `lib_apkeep` per-query cache.** Would collapse §2.12's 146× and make the
  query-side comparison honest, but that is development, not measurement hours.

## 5. Recording

Each run appends its outcome here and updates its home section
(`CLOUD_BENCH_PLAN.md` §1.7.3 for #1; `APKEEP_NDD_EVAL.md` §2.6b for #3–#5).
§2.6b in particular must be revisited whatever happens: its bounds were derived
from builds produced by a binary with both defects present. The merge-activity
check below is the only evidence available that those runs were not globally
corrupt, and it is suggestive rather than conclusive.

| trace | merge first active | `merge_ms` | reading |
|---|---|---:|---|
| wl_cloud, corrupted | **never** | 0.0 min | merging entirely dead |
| wl_cloud, fixed | 11.0 min | 212.1 min | merging dominates |
| faithful-stanford | 0.5 min | 35.2 min | merged throughout — not globally corrupt |
| faithful-i2 | 0.5 min | 18.1 min | merged throughout — not globally corrupt |

## 6. Log

*(appended as runs land)*

- **2026-09-25 — campaign agreed.** Scope #0/#1/#3/#4/#5; #2 and #6 dropped.

- **#0 PASSED** (2026-09-25). fast 919; integration 164+11+16, 0 failures. Both
  item-29 fixes (the `addPredicate` ref protection and the loud catch) are clean
  against the whole suite -- nothing depended on the swallow.

- **#1 COMPLETED** (2026-09-26 00:10). **wl_cloud builds on BDD in 2 h 46 min.**
  `status: completed`, **zero exceptions with the loud catch active**, so nothing
  was swallowed to reach it. build 9 976.3 s / **query 1.96 s** / `ap_num`
  **90 153** / 1 773 of 1 773 rules / merge 143.3 min vs ppm 22.8 min (6.3x) /
  119 elements / table 180.6 MiB. The query is essentially free once the
  partition exists; the cost is entirely the build, and within it AP merge.
  §1.7.3 called this model intractable on BDD for months.
  **WAS OPEN, now CLOSED (2026-09-27):** `reachable_pairs` **53** where NDD
  returns **59** on the same model under the same driver. The six are the whole
  `internet` row, and the cause is a third upstream defect -- a NAT's rewrite
  outputs stop being atomic predicates once a rule reaches any other element.
  `CLOUD_BENCH_PLAN.md` §1.7.3, TODO item 29. Note that the cost figures on this
  line are therefore the **pre-fix** partition.

- **#3 BOTH PROBES CLEAN** (2026-09-26 01:19). One hour each, declared deadline,
  loud catch active, **zero exceptions in either**. faithful-stanford: 4 245 of
  9 491 rules, `ap_num` 13 759. faithful-i2: 86 709 of 154 974, `ap_num` 13 564.
  §2.6b's runs are therefore unlikely to have been silently corrupt, and #4/#5
  are de-risked.

  **CAVEAT DISCOVERED HERE -- the §2.6b baseline transfers for i2 and NOT for
  stanford.** The stanford faithful model is **9 491 rules today against §2.6b's
  7 278**: `OUT_STAGE_PLAN.md` step 3 removed the out-stage collapse and now
  emits the full stage. So #4 is a NEW measurement, not a re-measurement, and
  §2.6b's >= 3.8 h bound does not transfer to it. i2 is 154 974 vs 154 920
  (0.03 %), so that one does.

  **And on i2, where the comparison IS valid, the patched build looks materially
  different:** at 30 min it had `ap_num` 11 124 at 84 854 rules against §2.6b's
  20 930 at 82 003 -- roughly half the partition, at more rules, at 1.62 rules/s
  against 1.08, with AP/rule 0.94 against 2.16-2.60 and more merge activity in
  half the time. **That points at §2.6b's "unbounded superlinear partition growth
  with no plateau" -- the Σ-vs-Π headline -- being substantially an artifact of
  the use-after-free**, which degraded merging, and a partition that cannot merge
  only grows. One run against one run, and §2.6b's i2 build did merge somewhat,
  so this is a strong pointer rather than a finding. #5 is what settles it.

- **#4 DEADLINE** (2026-09-26 09:20). faithful-stanford, 8 h, **zero exceptions**.
  5 035 of 9 491 rules (53.1 %), `ap_num` 18 455, merge 421.6 min vs ppm 57.5
  (7.3×). Completion bound **≥ 56 h** (0.0120–0.0219 rules/s over the final
  15 min to 4 h); the rate DECAYED across the run, so these are true lower
  bounds. Not comparable to §2.6b's ≥ 3.8 h — different model, per the caveat
  above. Partition non-stationary: near-flat at 14–15 k for three hours, then
  +1 850 in the sixth while the rate halved.

- **#5 DEADLINE** (2026-09-27 09:21). faithful-i2, 24 h, **zero exceptions**.
  97 553 of 154 974 rules (62.95 %), `ap_num` 25 036.

  **The matched-rule-count comparison, which is what this campaign was for:**
  0.34× / 0.36× / 0.39× the §2.6b partition at 78 k / 80 k / 82 k rules. **The
  defect inflated §2.6b's `ap_num` curve ~2.6×.**

  **And the wall-clock inverts, which I had backwards.** Completion bound
  **234–270 h** (0.059–0.068 rules/s, stable across six windows) against §2.6b's
  ≥ 18.7 h. `merge_ms` 1 394.8 min vs `ppm_ms` 44.4 — **31.4×**, where §2.6b's
  run was PPM-dominated at 0.5×. Fixing the defect makes the partition ~3×
  smaller and the projected build ~13× longer, because the merge work that keeps
  the partition small IS the dominant cost. The #3 note above called the patched
  build "faster" on a 30-minute reading; that was the cheap `+fwd` phase.

- **CAMPAIGN COMPLETE** (2026-09-27). ~38 h of the 56 h budget, five runs, zero
  exceptions in any. Written up in `APKEEP_NDD_EVAL.md` §2.6c, with §2.6b marked
  SUPERSEDED.

- **THE 53-vs-59 GAP, DIAGNOSED AND FIXED** (2026-09-27, ~8 h). The one
  correctness question the campaign opened and did not close. The six pairs are
  the whole `internet` row; the cause is a **third** upstream defect (a NAT's
  rewrite outputs stop being atomic predicates once a rule reaches any other
  element, and `Element.forwardAPs` then intersects them away silently). Found by
  dumping the engine-neutral rule IR and replaying it on device subsets, which
  took a 2.8 h build down to a **70-rule, 0.4 s** repro; that harness is now
  `fave/bench/apkeep_ir_replay.py`. Fixed by `Network.refreshRewriteTables()`,
  pinned by `fave/test/test_apkeep_nat_rewrite.py`. `CLOUD_BENCH_PLAN.md` §1.7.3,
  TODO item 29.

- **AND IT REACHES THE FAITHFUL MODELS** (2026-09-27). An induced 4-router
  faithful-stanford subnetwork (3 985 rules) carries **634 stale rewrite outputs
  in 32 of its 72 NATElements**; a 2-router / 1 946-rule subset carries none, so
  it is a question of how many rules follow the NATs -- and the full models have
  far more. So runs #4 and #5 above built over partitions with the same defect.
  Rebuilding the 3-router subset with the patched jar then measured what that
  costs, and it is less than it sounds: stale outputs 634 -> **0**, `ap_num`
  **4 728 unchanged**, build 1 789.5 s -> 2 293.9 s (1.28x), and the reachable
  pair set **identical** (6 of 9). So the fix clears the staleness on the VLAN
  path but changes no answer and no partition size at this scale. wl_cloud's
  answers moved because **all five** of its gateway DNAT's outputs were stale and
  every internet-sourced path crosses that gateway; here 0.6 % of outputs are
  stale and none on a deciding path. Not measured: whether the full 16-router and
  154 974-rule models behave as the subsets do.

- **AND THE PATCHED wl_cloud BUILD NO LONGER FITS 5 h** (2026-09-27,
  `bench/wl_cloud/eval/natfix_full_after_deadline5h.*`). Declared 5 h deadline,
  `status: deadline`, **1 405 of 1 773 rules (79.2 %)**, `ap_num` 83 852,
  `merge_ms` 275.7 min vs `ppm_ms` 15.4 min = **17.9x** (the unpatched run of the
  same model in the same session: 7.3x). The tail rate puts completion **>= 9.6 h
  further**, i.e. **>= 14.6 h** against the unpatched 2 h 46 min. At matched rule
  counts in the same session the ratio is **3.35-3.41x** from rule 1 350 to 1 405
  and still climbing. Both full runs shared the box, so the ratio is the
  meaningful figure, not the absolute wall. The correctness verification
  therefore rests on the 343-rule prune, which is what it was built for.

  **Still open:** all three upstream defects are unreported upstream.
