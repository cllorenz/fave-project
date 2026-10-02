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

## F3 — VeriFlow-FR cannot run `wl_cloud`: a ternary value it has no model for

**Status: open. Falsifies P9.**

`wl_cloud_vf` ends `status: error` at 1.6 s, in the compliance check:

    ValueError: not a prefix: x1xxxxxxxxxxxxxx

VeriFlow-FR's model is range/prefix-based, and this is a **ternary** value — a
16-bit field with one bit set and the rest wildcard. The engine has no
representation for it and refuses, which is the honest failure: it did not
answer and it did not approximate.

Prediction **P9** said "`vf` (4+10) completes every one of the nine workloads".
That is now false. The falsification is recorded; the prediction is not edited
(§7).

**Why this is more than one cell failing.** `fave/bench/feature_survey.py`'s V0
survey concluded that **no rule in the suite carries a ternary value, so every
field value is an interval** — a finding item 31 records and leans on, because
it is what makes range-based engines comparable on this suite at all. A ternary
value reaching VeriFlow-FR on `wl_cloud` contradicts that in one of two ways,
and they have different consequences:

* the survey missed a ternary value that is in the workload, so its conclusion
  is wrong and anything resting on it needs re-checking; or
* the value is **manufactured by an adapter encoding** rather than present in
  the workload — `CLOUD_BENCH_PLAN.md` §2.8's ingress demultiplexing is the
  candidate, and a 16-bit one-hot-looking mask is the shape a VLAN or port
  demultiplexer would produce. Then the survey stands, and what needs declaring
  is an adapter encoding that changes the *kind* of value an engine is handed.

Either way it belongs in `ACCOMMODATIONS.md`, and which one it is decides
whether `wl_cloud × vf` is a tool limitation or a FaVe encoding artefact. Not
resolved here: it needs the owner's reading, and resolving it means running
cells beside the queue.

## F4 — NDD-APKeep and NetPlumber disagree on `wl_cloud` too, by one violation

**Status: open. Same direction as F1.**

| engine | violations of 71 |
|---|---|
| NetPlumber | **58** |
| NDD-APKeep | **57** |

The single line NetPlumber reports and NDD does not:

    - `source.dc1_leaf6_host0` reaches `probe.dc0_leaf1_host1` with …

a **must-NOT-reach that NetPlumber finds reached** and NDD does not.

**F1 and F4 are the same discrepancy, not two.** Read as reachability rather
than as violation counts, both say NDD-APKeep computes **less** reachability
than NetPlumber:

* `wl_example` — a *must-reach* (`office → internet`) that NDD reports as
  **not reached**, so NDD sees less;
* `wl_cloud` — a *must-NOT-reach* (`dc1_leaf6_host0 → dc0_leaf1_host1`) that
  NetPlumber reports as reached and NDD does not, so again NDD sees less.

The violation counts move in opposite directions (NDD finds one more on
`wl_example`, one fewer on `wl_cloud`) purely because the two checks have
opposite polarity. One coherent hypothesis covers both: **NDD-APKeep
under-approximates reachability relative to NetPlumber.** That is the shape to
test, and it is the opposite of the failure mode `test_backend_differential.py`
was widened to catch in 2026-09 (APKeep *over*-approximating `wl_up`).

`wl_cloud` is also **the one workload in the suite with an external oracle**,
which makes it the right place to adjudicate — and phase C runs BDD-APKeep over
it for 24 h, so a third engine's verdict on this exact workload is already in
the campaign.
