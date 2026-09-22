# The Delta-net traces — what the vendored data actually contains

**GENERATED — do not edit.** Regenerate with `python3 -m
bench.wl_deltanet.deltanet_census` from `fave/`;
`test/test_deltanet_census.py` pins this file byte for byte against a
fresh derivation from `deltanet-traces/`. Scope, provenance and the
reason only two of the archive's eleven CSVs are here are in
[`deltanet-traces/README.md`](deltanet-traces/README.md), which states
what cannot be derived; everything below is derived.

Background and the D1-D5 build plan: `CLOUD_BENCH_PLAN.md` §2.

## The two traces

| trace | inserts | prefixes | routers | next-hops | names | edges |
|---|---:|---:|---:|---:|---:|---:|
| airtel1-only-inserts.csv | 38,100 | 1,400 | 57 | 52 | 68 | 158 |
| airtel2-only-inserts.csv | 38,100 | 1,400 | 57 | 52 | 68 | 155 |

"names" is the union of the router and next-hop columns: the two are
different sets, and §2.3's topology question is about the difference.

| trace | sha256 |
|---|---|
| airtel1-only-inserts.csv | `b80766782dafa682d4da748125ed6bbbaa3b3bb1ac39d7ad89e1028d8c948fa1` |
| airtel2-only-inserts.csv | `a2c233554f511e1bebbe2ac12ee739708aff8ddcd432b71825c24897d7b85341` |

## D1 — the fourth field is a priority encoding LPM

    priority = 5 * prefix_length + 100

Exactly, on every row of both traces — **76,200 of 76,200**, no exception.
Longer prefix, higher priority, which is how Delta-net and any
OpenFlow-style flat table linearise longest-prefix match into a
priority-ordered rule list.

**The column therefore carries no information of its own** — everything
it states is already in the prefix. A converter reads the prefix and
ignores the column, and `deltanet_trace.parse_trace` asserts the
identity on every row so that a trace encoding something ELSE in that
field is refused rather than silently misread.

The evidence, and at the same time the LPM depth profile:

| prefix length | priority | rules in airtel1 | rules in airtel2 |
|---:|---:|---:|---:|
| /14 | 170 | 29 | 29 |
| /15 | 175 | 80 | 80 |
| /16 | 180 | 809 | 809 |
| /17 | 185 | 408 | 408 |
| /18 | 190 | 713 | 713 |
| /19 | 195 | 1,435 | 1,435 |
| /20 | 200 | 2,809 | 2,809 |
| /21 | 205 | 2,374 | 2,374 |
| /22 | 210 | 4,085 | 4,085 |
| /23 | 215 | 3,496 | 3,496 |
| /24 | 220 | 21,248 | 21,248 |
| /25 | 225 | 56 | 56 |
| /26 | 230 | 81 | 81 |
| /27 | 235 | 74 | 74 |
| /28 | 240 | 51 | 51 |
| /29 | 245 | 87 | 87 |
| /30 | 250 | 56 | 56 |
| /32 | 260 | 209 | 209 |

18 lengths, 14..32 — **/31 is the one absent**, which is why the field
takes 18 distinct values over a 19-length span and not 19.

### Three figures this replaces

All three were measured by hand at vendoring time and stated in
`deltanet-traces/README.md` and `CLOUD_BENCH_PLAN.md` §2:

| stated | derived | what happened |
|---|---|---|
| fourth field takes 18 values in **180-220** | 18 values in **170-260** | the count was right, the range was not |
| prefix lengths **14-25** | **14-32** | 14-25 is 12 lengths, and the same sentence says 18 values |
| **1,400** prefixes (airtel2) | **1,400**, and airtel1 the same | right, but stated of one trace only |

Nothing read them, which is why nothing caught them: no converter
existed yet. Had D1 been guessed from the stated `180-220` instead of
measured, the guess would have placed 9 of the 18 actual priorities
outside its own range.

## The names, and what is not a router

Names are `s<i>-<j>`. The router column and the next-hop column do not
span the same set, and both asymmetries are a modelling decision for D3
rather than a defect:

| trace | routers | next-hops | union | next-hops with NO rules | routers no-one forwards to |
|---|---:|---:|---:|---:|---:|
| airtel1-only-inserts.csv | 57 | 52 | 68 | 11 | 16 |
| airtel2-only-inserts.csv | 57 | 52 | 68 | 11 | 16 |

A next-hop carrying no rules of its own is a **sink**: a packet
forwarded there reaches a device with an empty table. In `airtel1-only-inserts.csv` they are

    s11-2 s12-2 s12-3 s12-4 s13-2 s16-2 s3-2 s4-2 s5-2 s6-2 s7-2

and what the model should do with them — drop, treat as an egress
edge port, or refuse the trace — is D3, not D2.

**Interfaces are absent entirely.** A row names a router and a next-hop
and neither end's port, while FaVe's router model is port-based. That,
not the fourth column, is the converter's real open question.

## Replay is order-independent — the trace has no update semantics

| trace | inserts | distinct (router, prefix) | overwrites |
|---|---:|---:|---:|
| airtel1-only-inserts.csv | 38,100 | 38,100 | 0 |
| airtel2-only-inserts.csv | 38,100 | 38,100 | 0 |

No insert ever overwrites a `(router, prefix)` an earlier one set, and
the files contain no withdrawal (the parser refuses one). So no rule
supersedes another, replay order cannot matter, and **the final FIB is
the file**. §2.1 planned D2 as a replay; the measurement makes it a
census.

It also bounds what D5 can claim. An insert-only, collision-free trace
measures incremental FIB *construction*, never churn: nothing is
withdrawn and nothing is revised. The archive members that would test
churn are not in the repository (§2).

## The two traces are one network routed two ways

Identical as SETS, not merely equal in count — measured that way
because two 57-element sets are not thereby the same 57 names:

| the two traces agree on | identical |
|---|:---:|
| the 1,400 prefixes | yes |
| the 57 router names | yes |
| the 52 next-hop names | yes |
| the directed edge set | NO — 158 vs 155 |

The edge set is the one that differs, and that IS the routing change.
Per rule:

|  | rules |
|---|---:|
| `(router, prefix)` keys in both | 36,300 |
| … of those, a DIFFERENT next-hop | 3,300 |
| keys only in airtel1-only-inserts.csv | 1,800 |
| keys only in airtel2-only-inserts.csv | 1,800 |

So the pair is a ready-made **differential**: one topology, one prefix
set, two forwarding states, and every reachability difference between
them is attributable to the routing change alone. It is a sharper
cross-engine test than either snapshot on its own — three engines
agreeing on one model is weaker evidence than three engines agreeing on
the DELTA between two. `CLOUD_BENCH_PLAN.md` §2.3.

## Checked against the paper that published the data set

Horn, Kheradmand and Prasad, *Delta-net: Real-time Network
Verification Using Atoms*, NSDI'17 — Table 2, Table 4 and §4.3.2.
These figures are NOT derived from the traces; they are what a third
party stated about them, so they are held as named constants and
compared, never blended into the derivation.

| the paper states | published | derived here | agrees |
|---|---:|---:|:---:|
| nodes (Table 2) | 68 | 68 | yes |
| rules in the ONOS data-plane snapshot (Table 4) | 38,100 | 38,100 | yes |
| queries posed on that snapshot, = its links (§4.3.2) | 158 | 158 | yes |

**All three identify `airtel1-only-inserts.csv` as the very snapshot §4.3.2 reports on.**
That is a stronger footing than the workload was planned to have: the
MODEL is now corroborated by a published third-party description, even
though no reachability VERDICT is (see below).

`airtel2-only-inserts.csv` matches on rules and nodes and carries **155** links, not 158. The
paper publishes one snapshot, so nothing states what its edge count
should be; §2.3 is where that difference is put to use.

Two figures do NOT line up, and are recorded rather than reconciled:

| the paper states | published | derived here |
|---|---:|---:|
| unique IP prefixes advertised (§4.2) | 1,600 | 1,400 |
| max links in the topology (Table 2) | 260 | 158 |

The first is a genuine open question — 16 switches advertising 100
prefixes each gives the paper's "1,600 unique (but possibly overlapping)"
and the traces carry 1,400. The second is not a discrepancy: 260 is the
topology's capacity and 158 is how many links the snapshot's rules
actually use.

The paper also settles two things this repository recorded as unknown:
the data set's home, `https://github.com/delta-net/datasets` (reference [14]) —
`deltanet-traces/README.md` had the download URL as never recorded —
and the `s<i>-<j>` naming. The topology is AS 9498 (Airtel) emulated as
**16 Open vSwitches**, and the paper splits a switch into several graph
nodes when its rules match on several input ports ("we report the number
of graph nodes rather than the number of switches"). So `i` is the
switch and `j` the per-input-port node, 16 switches becoming 68 nodes,
and the sinks above are graph nodes that terminate a link without
carrying rules of their own.

## What the data does not contain

Pure L3 forwarding: no ACLs, no rewrites, no transport fields. Any
compliance property has to be invented, so this workload is a reuse of
the DATA and not a reproduction of the EXPERIMENT — §2.1 says so.

**The distinction the section above sharpens: the MODEL is externally
corroborated, the VERDICTS are not.** The paper states how many rules,
nodes and links this snapshot has, and the derivation matches all three,
so a mis-parse of the traces would now be caught by something outside
this repository. It publishes no reachability answer — its own results
are query TIMES (Table 4), not sat/unsat — so every correctness result
from this workload remains a consensus between implementations in this
tree. That is §0's first gap, and only `wl_cloud` closes it. A result
here must not be written as though the paper had blessed it.

