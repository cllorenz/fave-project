# BDD-APKeep measurement campaign — 56 h budget

**Owner:** Claas Lorenz. Agreed 2026-09-25. Companions:
[`CLOUD_BENCH_PLAN.md`](CLOUD_BENCH_PLAN.md) §1.7.3,
[`APKEEP_NDD_EVAL.md`](APKEEP_NDD_EVAL.md) §2.6a/§2.6b, [`TODO.md`](TODO.md) item 29.

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
