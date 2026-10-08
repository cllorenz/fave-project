# The VLAN guardrail — both arms, one build

Run 2026-10-08, declared in [`PROTOCOL.txt`](PROTOCOL.txt) before it started.
Five cells on an idle campaign machine, serialised, all from commit `6084dec0`.

| cell | arm | verdict | rewrite rules | admission rules | stage tables |
|---|---|---|---:|---:|---:|
| `wl_i2 × ndd` | faithful | **11 of 72** | 77,451 | 390 | 18 |
| `wl_i2 × ndd` | `--no-vlan` | **0 of 72** | 77,451 | 390 | 18 |
| `wl_stanford × ndd` | faithful | **75 of 240** | 3,417 | 2,063 | 41 |
| `wl_stanford × ndd` | `--no-vlan` | **75 of 240** | 3,417 | 2,063 | 41 |
| `wl_ifi × np` | `--no-vlan` | **refused** (dev) | — | — | — |

## The predictions, scored

| | declared | measured | |
|---|---|---|---|
| **V1** | `wl_i2 --no-vlan` → 0 of 72 | 0 of 72 | **held** |
| **V2** | `wl_stanford --no-vlan` → 75, unchanged | 75 of 240 | **held** |
| **V3** | denominator > 0, arm-identical; i2 = 77,451 | exact | **held** |
| **V4** | the refusal survives the whole path | refused, no verdict | **held** |
| **V5** | a reading rule | applied below | — |

## What the two workloads say

**`wl_i2`'s check set CAN see VLAN, by exactly 11 pairs.** Relaxing the
dimension moves the verdict from 11 violations to 0 — the positive control
that proves the arm relaxes something real, and that an unchanged verdict
elsewhere is a fact about the check set rather than about the flag.

**`wl_stanford`'s check set CANNOT see it at all.** 3,417 VLAN rewrite rules
and 2,063 admission rules across 41 stage tables were relaxed, and **not one of
240 checks moved**. So no claim about VLAN fidelity is supported by that
workload's verdict, on any engine. It is the same shape as §5.4's G2 — where
`wl_i2`'s 77,451 reordered rules left the verdict untouched — and close in
magnitude: 5,480 VLAN-carrying rules here against 77,451 there.

The two results are the point of running both. A guardrail that only ever
returns "blind" cannot distinguish a blind check set from a broken arm; one
that only ever returns "sees it" cannot either. **This arm returns both, on the
same engine, the same build and the same flag.**

## V5 applied — how not to read this

An unchanged `wl_stanford` verdict is a statement about **that workload's 240-
pair all-to-all policy**, and about nothing else. In particular it is *not*
evidence that VLAN modelling is unnecessary: the same engine, same build and
same flag changes `wl_i2`'s answer by 11 pairs. A faithful model is what makes
`wl_i2` answer 11 instead of 0, and 11 is the answer NetPlumber, ad6 and
VeriFlow-FR independently agree on. Read backwards, this result would retire
the very modelling it just measured the value of.

## The denominator, and why it is not decoration

`faithful_vlan: false` alone cannot distinguish "relaxed 77,451 egress
rewrites" from "this workload never had a VLAN stage" — and the second reads as
a passing guard. §5.4 hit exactly that on `wl_cloud`, which declares no LPM
table. Every cell above now carries three recorded fields, and the two arms of
each comparison carry **identical** counts, which is the check that the counter
is not itself gated on the flag it is supposed to measure.

**An independent cross-check fell out of it.** `wl_i2`'s 77,451 rewrite rules
is the number ad6's faithful encoding reports as `out_rw_rewrites`
(`AD6_PLAN.md` §5.5) — two unrelated codebases counting the same thing from the
same model, agreeing to the digit. V3 named it in advance.

## The refusal, end to end

`wl_ifi × netplumber --no-vlan` records `status: error`, no verdict, and the
aggregator's stderr carries the reason:

```
backend configuration error: --no-vlan is not implemented for netplumber:
only APKeep models VLAN behind a flag. It is the VLAN guardrail arm, and a
run that quietly ignored it would report an unchanged verdict -- which that
guardrail reads as 'this check set is blind to VLAN'. ...
```

Before 2026-10-08 that cell would have reported **27 of 299, unchanged** — a
textbook passing guard, produced by a backend that never applied the flag. It
is a `dev` cell and is never reportable; it exists because a unit test on
`build_engine` does not show that the refusal survives `cell_run` → aggregator
→ `build_engine`.

## Two method notes

**Both arms were re-run, including the faithful ones.** The phase A cells
already said 11/72 and 75/240, but they predate the counters and so carry no
denominator, and a guardrail whose arms come from two builds is not a
controlled comparison. Re-running cost 13.3 s and both reproduced phase A's
verdict exactly — which is itself a small regression result for the build.

**Three cells failed to start on the first attempt, and nothing was recorded.**
`--engine-options "--no-vlan"` is rejected by argparse: a value beginning with
`-` is read as another flag unless it contains a space, which is why
`"--grounding flow --solver cadical195"` works and a single token does not. The
protocol declared the space form. Re-run with `--engine-options=--no-vlan`.
Nothing was measured and no artifact was written — argparse exits before the
harness starts — so unlike the interpreter defect this one cost nothing but a
minute. **The durable fix is a first-class `--no-vlan` flag on `cell_run.py`,
symmetric with `--invert-lpm`**, so the arm is a declared argument rather than
a free-text string that has to be quoted exactly right. Not done here: it is a
harness change, and the cells were already running under the declared protocol.
