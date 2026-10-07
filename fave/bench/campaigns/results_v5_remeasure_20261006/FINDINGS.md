# The re-measurement — what the investigation's fixes changed

28 cells, 2026-10-06 14:51–15:15 UTC, from `cf2ec3a6`. Predictions R1–R8 in
`PROTOCOL.txt`, declared before the run and not edited. Phase A's results in
`../results_v5_20261002/` are untouched and are the "before" column.

## Verdicts

Three cells moved. Every other one of the 28 is identical to phase A.

| cell | phase A | now | why |
|---|---|---|---|
| `wl_up × vf` | 28 / 18,811 | **0 / 18,811** | Q23 — VeriFlow-FR had no no-U-turn rule |
| `wl_cloud × vf` | `error` | **57 / 71** | O3c — `expand_negated` emitted non-prefix vectors |
| `wl_cloud × vfplain` | `error` | **57 / 71** | same |

Five more changed **outcome class without changing a number**: all five `wl_tum`
cells, `error` → `measured`. `wl_tum` dispatches no `check_compliance` task
because it has no check set, and the old `verdict_valid` required that task — so
the one workload that exists to be timed reported five engine failures.

## Where the engines now stand

**Every engine agrees with every other on all nine workloads.**

This section first said otherwise, and the correction is recorded rather than
edited away. It read: *"The single remaining disagreement is `wl_cloud`:
NetPlumber 58/71 against 57/71 from NDD-APKeep, ad6, `vf` and `vfplain`. Four
independent engines against one, on the only workload in the suite with an
external oracle."*

**That disagreement does not exist.** Asked which check NetPlumber differs on,
the set difference is empty in both directions. Its 58 is **57 distinct
violations plus one line printed twice**:

```
- `source.dc1_leaf6_host0` reaches `probe.dc0_leaf1_host1` with
    - packet.upper.dport=xxxxxxxxxxxx0xxx
- `source.dc1_leaf6_host0` reaches `probe.dc0_leaf1_host1` with
    - packet.upper.dport=xxxxxxxxxxxxxxx0
```

Same source, same probe, two **overlapping** header-space fragments —
`xxxx0xxx` and `xxxxxxx0` both admit dport 0. HSA represents a set as a union
of wildcard expressions and that union is not canonical, so one violated check
can be witnessed by more than one fragment. `cell_metrics.violations` counts
report LINES, so NetPlumber scores 58 where an engine that emits one line per
violated check scores 57.

Every `.report.md` in both campaign directories was scanned: **`wl_cloud × np`
is the only cell in the suite with a duplicated violation line**, and it is
exactly the cell where the engines appeared to disagree.

So F4-R was a **metric artefact**, and it is one this project's own rule names:
*"Never compare totals across different query counts. State the denominator."*
The denominator was stated; the NUMERATOR was counted differently by different
engines, and nothing checked that. The LPM guardrail had already ruled out rule
priority as a cause — correctly, and for a question that turned out not to
exist.

**Open, and deliberately not changed here:** `cell_metrics.violations` counts
lines. Counting distinct violated checks would be the faithful metric, and it
would change recorded numbers across the campaign, so it is a decision for the
owner and not a patch — see the open items.

## Scores

| # | prediction | score |
|---|---|---|
| R1 | `wl_up × vf` 28 → 0 | **HELD** — 0 of 18,811 |
| R2 | every other vf/vfplain verdict unchanged | **HELD** — all 14, cell for cell |
| R3 | `wl_cloud` stays np 58 against vf 57 | **HELD** |
| R4 | every np verdict unchanged | **HELD** — all nine. This was the one that would have retracted the claim that retiring the probe-condition technique is verdict-neutral. |
| R5 | np wall-clocks do not increase, and fall on the flow-heavy cells | **HELD as declared, WRONG ON ITS NAMED CELLS** — see below |
| R6 | all five `wl_tum` cells come back `measured` | **HELD** |
| R7 | `wl_up × vf` falls to ~400 s (falsified above 550 s) | **HELD** — 402.0 s, from 639.3 s |
| R8 | nothing moves to a worse outcome class | **HELD** — three moved the other way |

### R5 held by its falsifier and missed by its reasoning

Declared: wall-clock should fall on `wl_up` (22.0 s) and `wl_i2` (65.1 s), stay
flat on `wl_example`, and be falsified by *"a flat profile across all nine"*.

Measured, against a run-to-run drift of about +2% visible on the cells nothing
touched:

| cell | phase A | now | |
|---|---|---|---|
| `wl_stanford` | 6.5 s | **5.0 s** | **−24%**, not predicted |
| `wl_i2` | 65.1 s | 62.2 s | −5%, predicted |
| `wl_up` | 22.0 s | 22.8 s | **+4%**, predicted to fall |
| `wl_example` | 2.1 s | 2.2 s | +2%, predicted flat |

The profile is not flat, so the declared falsifier did not fire. But the cells
were named wrongly, and the reason is worth recording: **I used wall-clock as
the proxy for "flow-heavy", and the retired work was per flow EVENT.**
`wl_up × np` is slow because it answers 18,811 checks, not because it propagates
many flows; `wl_stanford` carries 83,710 loop reports and is where the flow
events actually are. Picking the proxy correctly would have named `wl_stanford`
first and `wl_up` not at all.

The saving is real and larger than it looks: against the +2% drift,
`wl_stanford` is about −26% and `wl_i2` about −7%.

## Not re-measured, and why

* **The three 24 h did-not-finishes** — `wl_i2 × ad6`, `wl_stanford × bdd`,
  `wl_i2 × bdd`. No fix reaches them; they stand. This is why the
  re-measurement cost 24 minutes and not 72 hours.
* **Retiring TODO item 13a** changed `fave/iptables/generator.py` and reaches
  nothing: phase A already ran the three `-o` workloads under
  `FAVE_ALLOW_OUT_IFACE=1`, and the retirement kept that path verbatim as the
  only path. Checked against the diff.
* **The APKeep cells O1a reached** are in `../results_v5_o1afix/`; the
  `wl_cloud × vf/vfplain` cells O3c reached are in `../results_v5_f3fix/`. Both
  are re-run here anyway, so that one directory holds one build.

## Two aborted attempts

This directory is the third attempt. Both earlier ones are recorded in
`PROTOCOL.txt` with what they showed, rather than quietly restarted:

1. The `verdict_valid` fix shipped with `check_anomalies` as its witness, which
   only NetPlumber dispatches — it marked six VeriFlow-FR cells `error`. Nine
   cells, deleted. The witness is now `report`, the aggregator's own task,
   verified by re-deriving all 51 phase A cells through `read_verdict` itself.
2. **The tree was edited while the queue ran.** A cell imports the working tree,
   so `wl_stanford_vf` ran on a half-written adapter. 22 cells, deleted — all
   22, not the 6 after the edit, because keeping the rest would have put two
   builds in one directory.

The rule that follows: **while a measured queue is running, the tree is
read-only.** §6 serialises the cells against each other; it did not occur to it
to serialise them against the person editing the engines.
