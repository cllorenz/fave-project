# Delta-net NSDI'17 traces — the scoped extract

These two files are the **entire** in-repo raw data for the planned Delta-net
workload (`CLOUD_BENCH_PLAN.md` §2). They are vendored rather than extracted on
demand: the source archive is not kept, because at 9.6 GB it does not belong in
a repository or on the working machine.

| file | size | what |
|---|---:|---|
| `airtel1-only-inserts.csv` | 1.2 MB | insert-only forwarding-rule trace |
| `airtel2-only-inserts.csv` | 1.2 MB | insert-only forwarding-rule trace |

Format is `+<prefix>,<router>,<next_hop>,<priority>`, e.g.

    +100.3.0.0/16,s10-1,s2-9,180

**What the traces CONTAIN is not documented here.** Every figure about them —
the census, the prefix-length profile, the topology names, the fourth field —
is derived from the files themselves by `../deltanet_census.py` into
[`../TRACES.md`](../TRACES.md), and pinned byte for byte by
`fave/test/test_deltanet_census.py`.

That split is not bookkeeping. This file previously carried three measurements
taken by hand at vendoring time, and all three were wrong — the fourth field's
value range, the span of prefix lengths, and a prefix count stated of one trace
when it held for both. Nothing read them, so nothing could contradict them.
`TRACES.md` records what each one should have said. The rule
(`CLOUD_BENCH_PLAN.md` §1.8) is the same one `oracle.json` earned for
`wl_cloud`: a figure with a derivation behind it, or no figure.

So this file states only what the data cannot state about itself: scope, and
where it came from.

## Why only these two

Owner scope decision 2026-09-18. The archive holds 11 CSVs totalling ~40 GB, and
several members are individually larger than a working disk (`airtel2.csv`
16.0 GB, `inet.csv` 14.4 GB, `rf3257.csv`/`rf6461.csv` 4.8 GB each). An
insert-only trace replays to a well-defined final FIB with no deletions, which
is what the planned static-snapshot phase needs.

The cost of that scope is stated in `TRACES.md`: an insert-only trace that never
overwrites a rule cannot exercise withdrawal at all, so the churn axis needs an
archive member that is no longer here.

## Provenance

Source archive `deltanet-NSDI17-dataset.tar.gz`,
sha256 `cc67472319e5d4791b96d8ceed1a5038af1ea719c360c3ce30040f3cc17f334b`,
members owned by `ali/ali`, dated 2016-09, re-tarred 2019-10.

**The download URL was recorded as lost, and is not.** The Delta-net paper's
reference [14] gives the data sets' home as
<https://github.com/delta-net/datasets> (found 2026-09-22; not verified as still
live). The archive's sha256 above is what actually matters for re-derivation.
`SHA256SUMS` here covers both traces so that a re-supplied archive can be
checked against what this repository already has; `util/raw_data.verify_raw`
checks them before anything reads them.

## What these files are

A. Horn, A. Kheradmand and M. R. Prasad, *Delta-net: Real-time Network
Verification Using Atoms*, NSDI'17, describes the data:

* the network is **AS 9498 (Airtel)** emulated as 16 Open vSwitches under ONOS
  and SDN-IP, with Quagga border routers advertising the prefixes;
* `airtel1-only-inserts.csv` matches the paper's published *consistent data
  plane snapshot* on all three figures it states for it — 38,100 rules, 158
  links, 68 nodes. It is that snapshot, not an anonymous trace;
* the Airtel 1 and Airtel 2 data sets differ by failure regime: single
  inter-switch link failures with recovery, versus all 2-pair link failures.

`../TRACES.md` holds the derived comparison, including the two figures that do
NOT line up. Nothing about the paper is derivable from the CSVs, which is why it
is stated here and checked in `fave/test/test_deltanet_census.py` rather than
mixed into the census.
