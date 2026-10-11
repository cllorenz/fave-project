# VeriFlow-FR footprints — a scoping pass

**Status: SCOPING, no code (2026-10-11).** Asked for by the owner (decision C on
the plan's question 3, 2026-10-11): before deciding whether VeriFlow-FR gets
APKeep's witness and dead-end footprints, find out what that means for its walk,
what it could save, and what it costs. **Owner:** Claas Lorenz. **Branch:**
`updates`. Siblings: [`APKEEP_FOOTPRINTS.md`](APKEEP_FOOTPRINTS.md) (the APKeep
design this mirrors), [`INCREMENTAL_PLAN.md`](INCREMENTAL_PLAN.md) §6.3, §7,
[`VERIFLOW_PLAN.md`](VERIFLOW_PLAN.md). Every claim carries a file:line;
estimates are estimates.

## 1. Why the question arises

The compared per-update number is `t_total = t_update + t_recheck` (D2), and
`t_recheck` is set by which checks the footprint reports. All three
footprints are FaVe's design: NetPlumber's (source, probe) hooks (`240aa881`),
APKeep's walk footprints in the fork, now refined by witness and dead ends
(default since 2026-10-11), and VeriFlow-FR's walk footprints, still coarse. A
VeriFlow-FR row that pays for a footprint FaVe never refined measures FaVe's
effort, not the engine. VeriFlow-FR is FaVe's own reimplementation, so changing
it touches no upstream code.

## 2. What VeriFlow-FR does today

- **One walk per query set answers every probe of every source sharing it.**
  The walk is exhaustive: it slices each table into local ECs and follows
  every one to its end (`queries.cc` `walk` :360, `walk46` :269); `delivered`
  is the set of tables where packets are consumed (:341, :435). Defaults:
  `revisit="state"`, `fields="4+10"` (`adapter.py:97–99`), so the campaign runs
  the V3b walk `walk46`, with excluded boxes.
- **The footprint is everything the walk touched:** every (table, arrival,
  box) state (:278, :371) and every port it emitted on (:262, :444)
  (`struct Footprint`, `queries.h:121`).
- **A rule update** marks a source if the rule could be a candidate at any
  recorded state at its table (`footprint_hits_rule`, `queries.cc:516`;
  `adapter.py:338`). **A link update**, up or down, marks it if the walk
  emitted on the port (`adapter.py:424`).
- **Granularity is the source.** A marked source reports *every* probe
  (`take_affected`, `adapter.py:447`), and its re-check is a full walk.

So there are two layers of coarseness, and they cost different things:
**which sources** are marked costs walks, which is time. **Reporting every probe**
of a marked source costs only the re-check *count*, the selectivity column.
The walk is the same either way.

## 3. What a finer footprint could save at best

From the 2026-10-10 dev calibration's raw records
(`fave/bench/campaigns/results_inc_dev_20261010/footprint_bound/`; 200 updates
per stream; the records predate the `-o` fix, so these are estimates). `srcs` is
the walks done. `srcs_chg` is the sources with at least one changed verdict,
which is the fewest walks any sound source-granular footprint can do. `chk|src`
is their checks.

| workload | stream | re-checks | changed | walks | walks needed | re-checks at source granularity | t_update | t_recheck |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `wl_airtel1` | S1 | 51,200 | 0 | 3,200 | 0 | 0 | 0.25 s | **125.7 s** |
| | S2 | 51,200 | 0 | 3,200 | 0 | 0 | 0.35 s | **127.3 s** |
| | S3 | 34,272 | 1,804 | 2,142 | 962 | 15,392 | 0.11 s | 85.5 s |
| `wl_ifi` | S1 | 2,670 | 81 | 136 | 37 | 753 | 0.01 s | 0.19 s |
| | S2 | 2,981 | 126 | 157 | 56 | 1,139 | 0.01 s | 0.25 s |
| | S3 | 5,624 | 606 | 300 | 240 | 4,622 | 0.00 s | 0.46 s |

Reading it:
- **`wl_airtel1` S1/S2 is the case that matters.** Every update marks all 16
  sources. A route update meets a state of every walk, likely (not verified)
  because each walk crosses every router with its destination unconstrained.
  No verdict changes. The ideal is
  zero walks; APKeep with both modes reached 0 and 4 re-checks on the same
  streams. VeriFlow-FR's `t_total` there is ~0.63 s per update, and almost all
  of it is avoidable.
- On `wl_ifi` the walks could fall 2.8–3.7× (S1/S2) and only 1.25× on S3.
- **Per-probe reporting changes the counts, not the time.** At best it would
  turn 2,670 re-checks into 81 on `wl_ifi` S1, but every marked source is still
  walked in full.

## 4. Design

Per source, its walk delivers some checked probes (**delivered**) and not
others (**undelivered**). A check's verdict depends only on whether its
probe's table is in `delivered`. The footprint becomes one per (source, probe):

**4.1 Witness, for a delivered probe.**
- The walk keeps a stack of hops: table, arrival, the EC or share box that took
  the hop, and the port it left by.
- At the first delivery to a checked probe's table, per start, it copies the
  stack.
- A rule update at table T hits the witness if:
  - T is a hop;
  - the rule's in-port is compatible with the hop's arrival;
  - and its match meets the hop's set.
- A link **down** hits it if the link's port is a witness egress port. A link
  **up** never hits it.

*Sound because:*
- **Rule updates.** Under first-match, a packet changes its best rule at a table
  only if the inserted or deleted rule matches it. If no update meets a hop's
  set, every packet of the set keeps its rule, its rewrite and its port, so the
  witness path survives.
- **Links.** A new link only adds branches.
- **Revisits.** Under `revisit=state` a re-walk may meet the same (table,
  arrival, box) state earlier on another branch. That continuation is the same
  deterministic one, so the delivery is still found. Under `revisit=path` the
  witness has no repeated table.

Under the assumptions of `APKEEP_FOOTPRINTS.md` §1 (A1–A3), this is the same
argument as APKeep's.

**Finer than APKeep's, possibly.** VeriFlow-FR's rewrites set a field to a
constant. The pre-image of a concrete packet is therefore one choice per
rewritten field within the hop's box. One packet `p` could be carried on *every* hop,
not only after the last rewrite (`APKEEP_FOOTPRINTS.md` §5, "Rewrites").
Under V3b `p` must also avoid the hop's excluded boxes. Proposed as a second
step: the box per hop first (a superset of the hop's real set, so sound), and
the packet once the box version is held to the oracle.

**4.2 Dead ends, for an undelivered probe.** Its footprint stays the explored
one. A change cannot open a path into a dead end, so such changes are ignored:
- **Insert a dropping rule:** no out-ports, not consuming. These packets go
  nowhere.
- **Insert a consuming rule at a table that is not the probe's:** the packets
  end there.
- **Insert a forwarding rule whose out-ports have no link after the batch:**
  the ports join the watched set, as in APKeep.
- **Delete a rule:** its packets fall to the next candidates. This is a dead end
  only if every lower candidate meeting `rule ∩ state` is one of the above.
  That needs a small C++ helper over `table_candidates`.
- **Links:** a link **down** never opens a path. A link **up** hits if the walk
  emitted on its port, or if the port is a watched one.

**4.3 Reporting per (source, probe).** `take_affected` returns only the pairs
that were hit. The re-check still walks each marked source in full. So this
changes selectivity and precision, not `t_recheck`. It is needed so that
VeriFlow-FR's counts mean the same thing as the other engines'.

**4.4 Not proposed: a walk per target.** Re-walking only toward the hit probes,
with an early stop, would also cut `t_recheck` within a marked source. But it is
a new query mode, not a footprint: it would change the work VeriFlow-FR's
from-zero numbers measure (`VERIFLOW_PLAN.md` D6, the thesis's bulk device
walk). Out of scope unless asked.

**4.5 Modes, as on APKeep.** `--footprint coarse|witness|dead-ends|witness,dead-ends`,
stamped in every cell. The default is decided by the owner after the evidence,
and the ablation table gets VeriFlow-FR rows.

## 5. Tests and evidence, mirroring APKeep's

- **Unit tests** in C++ (`oracle_unit` style) for the hop stack and the
  delete-dead-end helper, and in Python for the per-pair footprints. These cover
  both walks (`walk`, `walk46`) and both revisit rules.
- **Oracle streams.** The existing streams in `test_incremental_veriflow.py`
  (`wl_example`, `wl_ifi`, `wl_cloud`), with every mode on: selective ==
  full == from-zero.
- **Negative controls**, two plausible bugs that must fail the tests:
  - a witness test on links up instead of down;
  - every port treated as a dead end.
- **One indicative measurement**, with its protocol and predictions committed
  before it runs, on the dev workloads, scored as the APKeep modes were.

## 6. Estimate (not measured)

APKeep's modes were 863 lines including tests (`3209124f` +618/−61,
`55ba3c09` +245/−10), built in one session. VeriFlow-FR has more to cover:
- two walks;
- V3b exclusions;
- the pybind surface;
- a new C++ helper for dead ends on delete.

The estimate:
- **4.1 witness (boxes) + 4.3 per-pair reporting + links split:** about one
  session.
- **4.2 dead ends:** about half a session to one.
- **The concrete packet:** about half.
- **Protocol, measurement, findings, docs:** about half to one.

In all **about 3–4 sessions**. Like everything on the engine layer, it must be
done before the D11 run, and nothing in M2 depends on it.

## 7. For the owner

1. **Go/no-go**, and which parts: 4.1 + 4.3 alone carry the `wl_airtel1` case;
   4.2 adds the undelivered probes; the concrete packet is a refinement.
2. **When:** before M2's packet-filter spike, after it, or interleaved. It has
   to be done before the D11 run in any case.
3. **4.4 stays out**, unless you want per-target re-walks examined separately.
