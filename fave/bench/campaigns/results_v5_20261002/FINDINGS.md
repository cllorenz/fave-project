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

> **CORRECTED by F4-R below, 2026-10-02.** The closing claim of this section —
> that F1 and F4 are one discrepancy with NDD under-approximating — is **wrong**,
> and ad6's cell refuted it two hours later. The section is left as written,
> because the reasoning that was wrong is the point of recording it.

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

## F5 — the §5.1 table cannot be read against these cells, for two different reasons

Not a defect; a calibration note, and the evidence that §5.0's S6 ("re-run the
cheap cells") was the right call rather than a precaution.

**Reason 1 — `wl_up`'s row states a denominator that no longer exists.**

| | §5.1 | measured here |
|---|---:|---:|
| `wl_up` checks | 11,902 | **18,811** |

TODO item 0a already records the move (11,911 → 18,811, when
`reach_csv_to_checks.py`'s denied-cell branch was fixed to cover every endpoint
of a multi-device role) and annotates the documents that quote the old figure.
§5.1's own table was not among them. So **every `wl_up` wall-clock in that row
is a different question from the one measured here**, and item 0a's second
clause — *state the denominator, never compare totals across different query
counts* — forbids reading one against the other. The plan's `wl_up` row needs
the same annotation its siblings got.

**Reason 2 — at an identical denominator, this machine is simply faster, and
very unevenly so.**

| cell | §5.1 | here | checks | ratio |
|---|---:|---:|---:|---:|
| `wl_stanford` np | 6.4 s | 6.50 s | 240 both | **1.0×** |
| `wl_i2` np | 788 s | 65.1 s | 72 both | **12.1×** |
| `wl_stanford` vf | 303 s | 149 s | 240 both | 2.0× |
| `wl_i2` vf | 254 s | 129 s | 72 both | 2.0× |

VeriFlow-FR is a flat ~2× on both workloads, which is what a faster box looks
like. NetPlumber is 1.0× on `wl_stanford` and **12×** on `wl_i2`, which is not.

The hypothesis that fits: `wl_stanford` np at 6.4 s is dominated by fixed
start-up and has little to speed up, while `wl_i2` is 78,047 rules and the
reference figures were taken in the dev container — **4 cores, 19 GB** (item
31). NetPlumber's rule load scales at size^2.2–2.6 (§5.2), so `wl_i2` is the
one cheap-matrix cell plausibly memory-bound there and not here, on a box with
64 GB and no swap. That is checkable and is not checked here.

**What follows either way:** the two machines' numbers must not be mixed in one
table, and a 12× that lands on exactly one engine-workload pair is not a
uniform machine speed-up that can be divided out. This is the same confound
§5.2 flags for `wl_berkeley` — which is why phase B re-anchors k=30/10/3 on
this box rather than reusing good results from the old one.

## F4-R — the correction: on `wl_cloud` it is NetPlumber that is the outlier

**This refutes F4's conclusion, not its data.**

F4 argued that F1 and F4 were one discrepancy, NDD-APKeep computing less
reachability than NetPlumber. Two engines agreed with NDD, so that is not what
is happening.

| `wl_cloud` | violations of 71 |
|---|---|
| NetPlumber | **58** |
| NDD-APKeep | 57 |
| ad6 | 57 |

**ad6's report is line-for-line identical to NDD's.** ad6 is first-party and
SAT-based; NDD is APKeep-derived. They share no verification code, so their
agreeing exactly is independent confirmation rather than a common-mode result.
The disputed line is NetPlumber's alone:

    - `source.dc1_leaf6_host0` reaches `probe.dc0_leaf1_host1` with …

So on `wl_cloud` **NetPlumber reports a reachability two independent engines do
not find**, which points at NetPlumber over-approximating — the *opposite*
engine and the *opposite* direction from F4's conclusion.

The two findings are therefore separate, and each has its own lone outlier:

| workload | np | ndd | vf | ad6 | outlier |
|---|---|---|---|---|---|
| `wl_example` | 0 | **1** | 0 | 0 | **NDD** — fails a must-reach the others pass |
| `wl_cloud` | **58** | 57 | — | 57 | **NetPlumber** — finds a reach the others do not |

What was wrong with F4's reasoning is worth naming, because it is cheap to
repeat: with only two engines, "they disagree" and "one of them is wrong in a
particular direction" look the same, and reading a direction out of two points
invites exactly this. Three engines made the question decidable. Neither row is
adjudicated — a majority is not an oracle — but each now has a *named suspect*
rather than a shared one.

`wl_cloud` is the one workload with an external oracle, and phase C runs
BDD-APKeep over it for 24 h, so a fourth engine's verdict is already scheduled.

## F6 — VeriFlow-FR reports 28 self-reachability violations on `wl_up`

**Status: open.**

| `wl_up` (18,811 checks) | violations |
|---|---|
| NetPlumber | 0 |
| NDD-APKeep | 0 |
| VeriFlow-FR 4+10 | **28** |

**All 28 are on the diagonal** — every one is `source.X reaches probe.X` for
the same role X, verified mechanically (28 diagonal, 0 off-diagonal):

    - `source.clients.api.uni-potsdam.de` reaches `probe.clients.api.uni-potsdam.de`
    - `source.clients.asta.uni-potsdam.de` reaches `probe.clients.asta.uni-potsdam.de`
    …

That they are *exactly* the diagonal and nothing else makes this a semantic
disagreement about **whether a role reaches itself**, not a forwarding defect:
a wrong forwarding answer would not land only on the diagonal, 28 times, and
nowhere else.

This is live ground, not new ground. The `wl_generic_fw` repair (commit
`381caf5e`) records that `_convert_policy_to_checks` takes `--roles` (*"a role
whose single node stands for a subnet loses its self-check"*) and `--strict`
(*"which decides whether a filled diagonal means anything"*). So whether a
filled diagonal is a violation at all is a **declared option of the check
generator**, and VeriFlow-FR is answering the diagonal differently from the
other two engines.

Which makes it an accommodation question rather than a bug report until
someone decides it: either VeriFlow-FR's self-reachability semantics differ and
belong in `ACCOMMODATIONS.md`, or the diagonal should not be in `wl_up`'s check
set and the other two engines are passing it by accident. **Note it also moves
`wl_up` from "all three agree" to "two agree", which is a headline cell.**

## F7 — ad6 did **not** refuse `wl_cloud`. P10 is falsified.

Prediction P10: *"ad6 **refuses** `wl_cloud` for the structural reason in
`CLOUD_BENCH_PLAN.md` §1.7.2 — rather than failing, or answering."*

ad6 **answered**: 57 violations of 71, `outcome: measured`, 57.5 s, with no
refusal anywhere in its output. §5.1's matrix likewise carries "**refuses**
(structural)" in the ad6 × `wl_cloud` cell.

Scored false and not edited (§7). Two things follow, and the second is the one
that matters:

1. §5.1's matrix cell is wrong and the plan needs correcting.
2. **The structural reason in §1.7.2 either no longer holds or never blocked
   this workload** — and since ad6's answer agrees line-for-line with NDD's, it
   is not obviously a wrong answer that a refusal was protecting anyone from.
   Whatever §1.7.2 describes has either been fixed since it was written or was
   mis-scoped. That is worth knowing independently of this campaign, because a
   documented refusal that does not happen is the kind of claim a reviewer
   checks.
