# Phase B — `wl_berkeley` through k=1

Run 2026-10-06 15:34–16:10 UTC, from `fca3c073`. 35.8 minutes against a 14 h
budget. Predictions P1–P6 in `PROTOCOL.txt`, declared 2026-10-02 and unedited.

## The headline

**NDD-APKeep answers `wl_berkeley` at full size.** 13,402,846 rules, **0
violations of 520**, `verdict_valid`, in 18m50s wall.

| k | rules | load s | compliance s | aggregator MB | live heap MB |
|---:|---:|---:|---:|---:|---:|
| 30 | 459,202 | 18.5 | 6.9 | 4,043 | 2,437 |
| 10 | 1,351,800 | 76.5 | 36.3 | 7,797 | 3,511 |
| 3 | 4,476,240 | 217.3 | 115.8 | 20,553 | 6,688 |
| **1** | **13,402,846** | **687.0** | **428.1** | **44,115** | **13,668** |

k=1 had never been attempted: it needs ~43 GB against the old box's ~29 GB
ceiling. On 64 GB it fits with 17.9 GB still available at the low-water mark.

**The verdict is not vacuous.** The mutated k=10 control (`s22 ---> s23`)
returned exactly **1 of 520** — `` `source.s22` does not reach `probe.s23` `` —
so the check set detects a single changed rule. Worth stating explicitly in the
same campaign that found `wl_i2`'s check set blind to 77,451 reordered rules.

**Generating in its own process was load-bearing, not tidiness.** `gen_k1`
peaked at 13.5 GB. In the same process as a 44 GB JVM that is 57 GB of 64, and
the series' earlier method did exactly that.

## Scores

| # | prediction | score |
|---|---|---|
| P1 | k=1 completes at `-Xmx20g` on 64 GB, 0 of 520, `verdict_valid` | **HELD** |
| P2 | aggregator peak RSS 41–46 GB | **HELD** — 44,115 MB = 43.1 GB |
| P3 | live heap after GC 11.5–13.5 GB | **HELD** — 13,668 MB = **13.35 GB**, 1.1% inside the top of the band |
| P4 | live-set exponent k=2 → k=1 is 0.50–0.65 | **FALSIFIED** — see below |
| P5 | load ~11 min, compliance ~6 min | **HALF HELD** — load 11.45 min; compliance **7.14 min**, 19% over |
| P6 | re-anchored k=10 and k=3 within 15% of the 32 GB box | **FALSIFIED on one figure of eight** — see below |

### P4, which §7 said would matter more than the run itself

> *"Falsified by: outside that band — which would matter more than the run
> itself, since the k=1 extrapolation rests on the exponent being flat across
> the top of the series."*

| span | exponent | |
|---|---:|---|
| k=10 → k=3, same machine | **0.538** | inside |
| k=3 → k=1, same machine | **0.652** | outside, by 0.002 |
| k=2 → k=1, **across machines** | **0.672** | outside |

k=2 was never measured on this box — the drill's sizes are 30/10/3/1 — so P4 as
literally written can only be computed across two machines and two heaps, which
is the confound P6 exists to guard against. **It is outside the band either
way**, and only just.

**The exponent is not flat; it drifts upward** — 0.538 then 0.652 across the top
of the series. The sublinear result itself is not in doubt (every exponent is
far below 1.0, and the live set at 29× the rules is 5.6× the heap). What is now
in doubt is extrapolating *past* k=1 on a flat exponent. That no longer matters
for this cell, because k=1 was measured rather than projected — but it would
have mattered if the measurement had not been possible, and that is the
prediction's whole point.

### P6, and a confound in its own design

Seven of eight re-anchored figures land within 15%. One does not:

| | 32 GB `-Xmx16g` | 64 GB `-Xmx20g` | |
|---|---:|---:|---|
| k=10 rule load | 76.3 s | 76.5 s | +0.3% |
| **k=10 compliance** | **28.2 s** | **36.3 s** | **+28.5%** |
| k=10 aggregator peak | 7,949 MB | 7,797 MB | −1.9% |
| k=10 live heap | 3,414 MB | 3,511 MB | +2.8% |
| k=3 rule load | 249.5 s | 217.3 s | −12.9% |
| k=3 compliance | 122.9 s | 115.8 s | −5.8% |
| k=3 aggregator peak | 19,283 MB | 20,553 MB | +6.6% |
| k=3 live heap | 6,782 MB | 6,688 MB | −1.4% |

By its own criterion P6 is falsified, and its consequence — *"which would
invalidate reading the two machines' series together"* — applies to the
compliance column at k=10 and nowhere else.

Two things to say about it rather than around it. The moved figure is the
**shortest measurement in the comparison** (28 s), where JIT warm-up and GC
placement are proportionally largest; every figure above 100 s is within 13%.
And the two machines **did not hold the heap constant** — `-Xmx16g` against
`-Xmx20g` — which §5.2's table presents as "all at `-Xmx16g` on one heap" and
the re-anchoring necessarily departs from, since 16g cannot hold k=1. So P6
compares two variables and attributes the result to one. That is a flaw in the
prediction's design, not an excuse for its failure: a cleanly-posed P6 would
have re-anchored at `-Xmx16g`.

## What this does NOT establish

* **One run, one engine.** No repetition, so none of these timings carries a
  variance estimate; the 28.5% above is the only evidence in the set about how
  much a figure moves without a cause.
* **BDD-APKeep at k=1 is not run.** §5.2 makes it conditional on k=1
  completing, which it now has, and the plan is explicit that the driver does
  not start it: it is a new measurement whose budget the owner has not seen,
  and phase C's `wl_cloud` run outranks it. **Open follow-up.**
* **NetPlumber is out of this series** by design — rule load scales at
  size^2.2–2.6 and it already deadlines at 459k rules, this table's *smallest*
  size.

## The aborted first start

Recorded in `PROTOCOL.txt`: the drill died 0.1 s in, at k=30 generation,
because `berkeley_drill.py` launched a shell script without exporting `PYTHON`
and the generator ran on the system interpreter. An **environment** failure
(§8.1), re-run, saying nothing about any engine at any size. Its `gen_k30.json`
is deleted and cited nowhere.
