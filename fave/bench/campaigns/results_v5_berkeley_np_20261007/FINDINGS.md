# NetPlumber on `wl_berkeley` at the reportable limit

Run 2026-10-07, from `ab43c5c1`. Protocol and predictions N1–N4 in
`PROTOCOL.txt`, declared before the run and unedited.

## §5.2 was wrong, and not for the reason I qualified it with

> *"NetPlumber is out of this series — rule load scales at size^2.2–2.6 and it
> already deadlines at 459k rules."*

| cell | rules | wall | rule load | compliance | peak RSS | verdict |
|---|---:|---:|---:|---:|---:|---|
| k=30 | 459,202 | **210.0 s** | 205.9 s | **0.036 s** | 2,382 MB | 0/520 ✓ |
| k=10 | 1,351,800 | **3,083.4 s** | 3,075.8 s | **0.13 s** | 7,159 MB | 0/520 ✓ |

The cell that "already deadlines" takes **three and a half minutes**, and
NetPlumber answers 1.35 M rules in 51 minutes — 2.4% of the limit it was said
to exceed.

All four predictions held, and **N1 and N2 were badly pessimistic**: N1
projected 70–80 min for a cell that took 210 s, N2 projected 10.4 h for one that
took 51 min. Both were extrapolated from the 2026-09-29 series, and that is
precisely what the A/B below shows cannot be done.

| # | prediction | score |
|---|---|---|
| N1 | k=30 completes in 24 h, 0 of 520 | **HELD** (210.0 s, ~20× faster than projected) |
| N2 | k=10 completes in 24 h, 0 of 520 | **HELD** (3,083.4 s, ~12× faster than projected) |
| N3 | peak RSS under 16 GB at k=10 | **HELD** (7,159 MB) |
| N4 | compliance under 1 s at both sizes, cost ~100% load | **HELD** emphatically — 0.036 s and 0.13 s, i.e. **0.017% and 0.004% of wall** |

## The A/B: the speed-up is the MACHINE, not the `LEGACY_CHECKS` retirement

k=30 went from "did not finish in 3,600 s" (2026-09-29) to 210 s. Two things had
changed — the engine (`4bdbe622` retired the probe-condition technique) and the
machine. **A1 predicted the retirement was the cause. A1 is FALSIFIED.**

Same box, same inputs, one variable, `limit_class=dev`:

| arm | binary | rule load | wall |
|---|---|---:|---:|
| the v5 cell | default | 205.9 s | 210.0 s |
| **arm A** | **`-DLEGACY_CHECKS`** | **209.5 s** | 216.1 s |
| arm B (control) | default | 208.2 s | 212.3 s |

**The two DEFAULT runs differ by 2.3 s (1.1%).** The treatment adds 1.3 s on top
of their mean — **inside the noise the control itself establishes.** Retiring
the probe-condition technique bought **≤1.3% on `wl_berkeley`**, not 10×.

Running the control was the part that mattered. "216 against 210" alone invites
the reading that the treatment cost 3%; with a second default run at 208.2 the
spread across *identical* configurations is 1.1% and the treatment disappears
into it. **A two-arm A/B would have produced a number and no way to judge it.**

**The −24% measured on `wl_stanford` stands as the honest size of the
retirement**, and the saving is now known to be *workload-dependent*: it scales
with flows arriving at probes, which `wl_stanford`'s 83,710 loop reports have
and `wl_berkeley`'s 23 leaf probes do not.

So §5.2's claim was never about a 1 h limit, and never about the code. **It was
about the old machine.** The qualification added on 2026-10-07 — "under a 1 h
limit" — is itself not the main point, and is corrected.

## The guard did not guard anything

Building arm A failed: `-DLEGACY_CHECKS` **has never compiled**. Both guarded
bodies close their function twice, which is invisible while the guard is off.
The owner asked for the code to be guarded rather than deleted *so it could be
revived*; it could not be. Fixed in `d68a871d`, found only by trying to use it.

## Where NetPlumber actually stops

Two points on this box give a load exponent of **2.504** and memory that is
**linear** (1.004):

| | projected load | projected peak RSS |
|---|---:|---:|
| k=3 (4.48 M rules) | ~61,700 s = **17.1 h** | ~24 GB |
| k=1 (13.4 M rules) | ~962,000 s = **267 h ≈ 11 days** | **~74 GB** |

k=3 fits 24 h but not comfortably — an exponent of 2.7 puts it past. k=1 is
excluded on **both** axes independently, and the memory axis is the sturdier
one: linear scaling measured over a 2.94× step, agreeing with the older series.

**The exponent rests on two points.** That is the thinnest basis in this
document and it is stated rather than buried.
