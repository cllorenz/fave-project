# Findings from the V5 campaign, as they were made

Recorded while the campaign runs. §8.1: a cell that fails for an engine reason
is recorded and the campaign continues — the queue is not stopped to debug one
engine.

## F1 — NDD-APKeep and NetPlumber disagree on `wl_example`, the simplest workload

**Status: open, the campaign's most important finding so far. Falsifies P13.**

| engine | verdict |
|---|---|
| NetPlumber | **0** violations of 10, `verdict_valid` |
| NDD-APKeep | **1** violation of 10, `verdict_valid` |

The violation is a **must-reach that fails**:

    - `source.office` does not reach `probe.internet`

Both cells completed cleanly — `status: completed`, `exit 0`, `report: True`,
one `check_compliance` task each. This is not a crash and not a limit trip; it
is two engines computing different reachability on the same model. NDD is the
more restrictive of the two, so either NDD under-approximates reachability or
NetPlumber over-approximates it.

**Why it matters more than its size suggests.** `wl_example` is the suite's
smallest workload — 37 rules, 10 checks — which makes a disagreement there a
tractable bug rather than a scale artifact, and makes it the right place to
adjudicate from.

**Why nothing caught it.** `test_backend_differential.py` compares the backends
on `wl_ifi`, `wl_airtel1`, `wl_airtel2` and `wl_up`. **`wl_example` is not in
it.** That module's own docstring records the same lesson from last time: *"This
gate was `wl_ifi` only, and that is precisely how APKeep came to
over-approximate `wl_up` silently for months."* The gate was widened then, and
the suite's simplest workload was still left out of it.

**One thread worth pulling, for whoever adjudicates.** `wl_generic_fw` was
postponed by the owner on 2026-10-02 because it reported exactly one
unadjudicated violation, and commit `e371a0ad` concluded that since
`wl_generic_fw` has a *byte-identical* policy matrix and check set to
`wl_example` yet reported 1 where `wl_example` reported 0, the violation "is in
that workload's ruleset alone". That conclusion rests on `wl_example`'s 0 being
engine-independent. It is not: NDD reports 1 here. The two violations may be
unrelated — `wl_generic_fw`'s is `! source.WebServer -> probe.Internet` and
this is `source.office -> probe.internet` — but the inference that halved that
search assumed a denominator this cell has just moved.

**Not pursued in-campaign**, because adjudicating it means running cells, and
§6 requires everything whose number is reported to be serialised. Phase A runs
all six engine configurations over `wl_example`, so the full cross-engine
verdict table for this workload arrives as campaign output — which is exactly
the evidence needed, and is the campaign doing its job.

## F2 — `wl_tum` cells end `outcome: error`, and that is correct

`wl_tum` has no `checks.json` (§5.1: "it checks nothing"), so no
`check_compliance` task runs, `verdict_valid` is false and the outcome is
`error` — the harness saying "finished without a readable verdict". §5.1
already says not to report `wl_tum` as a verdict cell. Recorded so that a
reader does not mistake six `error` cells for six failures. Its measurement
numbers (wall-clock, peak RSS) are valid and are what the cell is for.
