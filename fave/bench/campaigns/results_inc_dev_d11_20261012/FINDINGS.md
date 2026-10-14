# Findings: D11, one indicative run of the whole grid (dev), 2026-10-12/13

`PROTOCOL.txt` was committed (`f7838736`) before any cell ran. The code is that
commit; after the run, `updates` was rebased onto `ai`, and the tag
`archive/updates-before-ai-rebase` keeps it. The run is indicative only:
limit_class dev, one repetition, eight cells at a time on this machine.

- `cells/`: the raw records, one directory per cell. Only each cell's small
  files are in git. The full records (387 MB) are archived outside git
  (`summary/ARCHIVE.txt`, owner 2026-10-14).
- `summary/`: made by `summarize.py`, written after the run. It holds every
  cell's timing distributions (overall, by operation type, along the stream),
  memory along the stream and during the run, verdict flips and refusals, plus
  each distinct stream and initial-verdict set once.
- `run.log`: the runner's log, with every deviation and finding as a dated
  DECLARED, FINDING or CORRECTION line, written when it happened.
- `analyze.py`: written after the run, it reads `cells/` and writes:
  - `cells.tsv`: one row per cell;
  - `scores.json`: P1–P7 with their details;
  - `tables.md`: the A cells' medians.

The run started 2026-10-12T08:20Z and the runner exited 2026-10-13T23:16Z,
after **38.9 h** (projected: about 55 h). All 433 cells have an outcome:

| outcome | cells |
|---|---:|
| `measured` | 291 |
| `did_not_finish` | 131 |
| ↳ stopped by the 2 h wall cap | 103 |
| ↳ stopped by the memory limit | 28 |
| `error` | 8 |
| `refused` | 3 |
| `oracle_failed` | **0** |

Every full checkpoint the oracle reached agreed: selective = full = from
zero, on every engine.

## Deviations

1. **This session ran work on the machine during the run**, against the
   protocol's "nothing else of this session runs on this machine meanwhile".
   - From about 2026-10-13T05:20Z to 05:33Z, the S4 fix's tests and checks
     ran in the worktree: two pytest modules in one process with a JVM, for
     4.5 min, plus the type check and lint.
   - The rebase onto `ai`, about 09:20–09:30Z, was git only.
   - Cells running in those windows carry the interference.
2. **The HEAD of the main tree was detached** at `f7838736` on 2026-10-13,
   after about 09:33Z, so that the `updates` branch could be rebased without
   changing a file the run loads. The checkout's files never changed.

## Predictions

| | prediction | outcome |
|---|---|---|
| P1 | no `error`, no `oracle_failed` | **falsified**: 8 `error`, all `wl_ifi` S4 (four C cells and four E cells, every engine), all at edit 125 with `KeyError: '103'` in `devices/router.py`. **One harness defect, not an engine one** (finding 1). `oracle_failed`: none |
| P2 | 90–150 cells stopped by the wall cap; none by the memory limit | **falsified**: 103 stopped by the wall cap, inside the range, but **28 by the memory limit** (finding 3) |
| P3 | every E cell reaches a full checkpoint | **falsified**: 30 of 40 did. Of the other 10, four are P1's crashes. Four were stopped by memory (`wl_up` VeriFlow-FR S2; `wl_stanford` NetPlumber and VeriFlow-FR S2; `wl_up` NetPlumber S4). Two were stopped by the wall cap before their first checkpoint (`wl_up` VeriFlow-FR and BDD-APKeep S4, at 100 and 66 of 1,000 edits) |
| P4 | finishes within 72 h | **held**: 38.9 h |
| P5 | ablation: witness + dead ends re-checks ≤ coarse and ≤ each mode alone | **held** on all 39 groups whose four cells completed. The other 36 of the 75 groups could not be compared: at least one of their four cells was capped, crashed, or not in the grid |
| P6 | batch "all": summed `t_recheck` ≤ batch 1 | **held** on all 19 comparable workload × engine pairs, by 2× (`wl_example` NetPlumber) to 600× (`wl_airtel1` BDD-APKeep) |
| P7 | A medians within 0.5–2× of the latest earlier dev record, ≥ 90% of pairs | **held**, barely: 39 of 43 pairs (90.7%). It is weak evidence: most earlier records are 50- or 200-update prefixes, so the medians compare different parts of a stream. For example, `wl_airtel1` × BDD-APKeep S2 earlier covered 200 updates and 4 re-checks; here it covered 15,800 and 42,215. That explains its 5.8×, and NDD-APKeep's 5.0× |

## Findings

1. **S4 can delete every entry of an applied router ACL** (P1).
   - **What happened:** `stream_s4` kept only one rule line per device. On
     `wl_ifi`, seed 1, its deletes had removed all six entries of
     `access-list 103` by edit 125, while `ip access-group 103 out` still
     applies it. The router model then has no ACL to look up.
   - **Remedy:** the owner chose to fix the harness. `b517a80f` on `updates` (first
     `7dc8d72a`, before the rebase) turns such a delete into a modify.
   - **Effect on the streams:** at seed 1, only `wl_ifi`'s stream changes,
     from edit 125. A regression test pins the invariant.
2. **Three engines measured nothing on `wl_tum`** (9 `measured` cells, all
   hollow).
   - **What happened:** `wl_tum` has no checks. VeriFlow-FR, BDD-APKeep and
     NDD-APKeep build their model at the first check, so every update of S1–S3
     was refused ("... before the model was built"). The cells end as
     `measured` with 100% of their operations refused. The S4 cells with the
     same cause end as `refused`.
   - **Its cost:** the protocol's "wl_tum: t_update only" holds only for
     NetPlumber.
   - **Before the campaign:** either build these engines' model without a
     check, or leave them out of `wl_tum`. In any case, a stream whose every
     operation is refused should end as `refused`, not `measured`.
   - **A misleading message:** a refused S4 cell prints "THE ORACLE FAILED",
     although its outcome is `refused` and it has no oracle.
3. **Memory sizing was too tight for long streams** (P2).
   - **The rule:** `make_queue.py` sized each cell at 1.3× the largest peak
     earlier dev cells had seen.
   - **Why it fell short:** those cells mostly ran 50-update prefixes, and
     RSS grows over a stream.
   - **Which cells:**
     - NetPlumber at 2 GB on `wl_up` and `wl_stanford`: S2, its batch
       variants, S4, and both oracle variants.
     - NDD-APKeep at 9 GB on `wl_stanford`: all A, B and D cells.
     - Several VeriFlow-FR oracle cells.
   - **Margins:** most were stopped within 1–5% of their limit (for example,
     2,101 MB against 2,048 MB).
   - **For the campaign:** size from this run's peaks, which cover the long
     streams. Where a cell was stopped, extrapolate its RSS growth to the
     whole stream.
4. **Single refused operations are known behaviour, not new.**
   - **Where:**
     - `wl_example` APKeep S1: 6 of 44.
     - `wl_up` APKeep and NDD-APKeep: under 3%.
     - `wl_stanford` NetPlumber and VeriFlow-FR S1: 139 of 17,584 ("no such
       rule").
   - **Why known:** the earlier dev records show the same counts on their
     prefixes.
   - **How they are recorded:** each refused operation is kept with its
     reason, never dropped.
5. **Re-checks under the footprints, and batching, behave as M1 found.**
   - **Footprints:** witness + dead ends cuts the re-checks to between half
     and a tenth of coarse on large workloads. On `wl_cloud` VeriFlow-FR S1 the
     cut is 38×: 3,779 against 145,014.
   - **Batching:** batch "all" cuts the summed re-check time by up to three
     orders of magnitude.

## What it says for the campaign (D10)

The A-cell medians are in `tables.md`. For each engine × workload, it gives
whether the full streams fit a cap:

- **NetPlumber:** completes every stream on every workload, except the
  memory-stopped `wl_stanford` S2. That one would complete with more memory.
- **VeriFlow-FR:**
  - completes `wl_example`, `wl_ifi` and `wl_cloud`, and S3 on both airtels;
  - its airtel S1 and S2 need about 3–10 h;
  - on `wl_up`, `wl_stanford` and `wl_i2`, a full stream needs between
    hundreds and thousands of hours (120–200 s per update on the last two).
    Those cells stay partial streams in the campaign as well, unless a
    prefix is declared.
- **BDD-APKeep:** completes everything except `wl_up` (125–176 ms per update
  on S1 and S2; 131 s on S3).
- **NDD-APKeep:**
  - completes everything except `wl_up`, `wl_stanford` and `wl_i2`;
  - `wl_i2` S3 completes; S1 and S2 need about 1.6 s per update;
  - `wl_stanford` needs more than 9 GB.

Before the campaign protocol is written, decide:
- prefixes against caps for the slow cells;
- the `wl_tum` model build (finding 2);
- memory from this run's peaks (finding 3).
