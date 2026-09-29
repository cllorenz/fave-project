# Delta-net NSDI'17 traces — the scoped extract

The two airtel files are the **entire** in-repo raw data for the Delta-net
workloads (`CLOUD_BENCH_PLAN.md` §2). They are vendored rather than extracted on
demand, because at 9.6 GB the source archive does not belong in a repository.
*(Revised 2026-09-29: the archive is no longer "not kept on the working
machine" either — the owner keeps it in the checkout root, gitignored, so that
larger members can be DERIVED from it by script instead of vendored. See
"Derived, not vendored" below.)*

| file | size | what | in git |
|---|---:|---|---|
| `airtel1-only-inserts.csv` | 1.2 MB | insert-only forwarding-rule trace | vendored, `SHA256SUMS` |
| `airtel2-only-inserts.csv` | 1.2 MB | insert-only forwarding-rule trace | vendored, `SHA256SUMS` |
| `berkeley-inserts.csv` | 386 MB | `berkeley.csv`'s insert block | **derived**, gitignored, `DERIVED.SHA256SUMS` |

Format is `+<prefix>,<router>,<next_hop>,<priority>`, e.g.

    +100.3.0.0/16,s10-1,s2-9,180

**What the traces CONTAIN is not documented here.** Every figure about them —
the census, the prefix-length profile, the topology names, the fourth field —
is derived from the files themselves by `../census.py` into
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
archive member that is no longer here. *(It is again — re-supplied 2026-09-25,
kept since 2026-09-29.)*

### The archive came back, and the scope held (2026-09-25)

Claas re-supplied it; the sha256 below matched exactly. Every one of the nine
un-vendored members was then streamed out and measured without extracting
anything to disk. The result, in full in `CLOUD_BENCH_PLAN.md` §2.14:

* **No other member yields a workload.** Every non-airtel trace withdraws
  exactly as many rules as it inserts — `berkeley.csv` and `rf1755.csv` were
  replayed in full and both terminate at an **empty** FIB, and `inet.csv`,
  `rf3257.csv` and `rf6461.csv` carry the identical signature. They are
  throughput traces, built to be replayed at speed rather than to arrive at a
  state. The one insert-only member, `rf1755.links.csv`, replays to itself:
  33,732,869 rules, 885× `wl_airtel1`.
* **The two derivations these files support are theirs alone.** The fourth
  field is `5 * plen + 100` only here — `trace.py` refuses every other trace,
  which is what that assertion was written to do — and only here do node names
  encode `(switch, port)`, so only here can a port-annotated topology be derived
  without inventing an interface.
* **Each file here is its full trace's OPENING insert block** (measured
  2026-09-28, `../archive_survey/opening.sh`): the 38,100 lines before the
  first withdrawal of `airtel1.csv` / `airtel2.csv`, identical as sets, in a
  different row order. So both were produced the same way — the forwarding
  state before any failure is injected.
  *(Superseded reading, 2026-09-25: "`airtel1-only-inserts.csv` is exactly the
  terminal FIB of `airtel1.csv` … `airtel2-only-inserts.csv` is not … so the two
  files were not produced the same way." The first half holds as a fact —
  airtel1's churn returns to its opening state, compared after sorting — and
  airtel2's terminal FIB does hold 46,259 rules; but neither file was ever
  derived from a terminal FIB, and the conclusion drawn from the mismatch was
  wrong.)*

The scope decision therefore stands on measurement rather than on size alone,
and a third re-supply would be needed to re-derive any of it.

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

## Derived, not vendored (2026-09-29)

`berkeley-inserts.csv` is the insert block of the archive's `berkeley.csv` —
every line before its first withdrawal, which `CLOUD_BENCH_PLAN.md` §2.14
measured to be the trace's whole insert set. At 386 MB it is not vendored (owner,
2026-09-29): the archive is kept instead and the file is re-derived from it by

    fave/bench/deltanet/archive_survey/insert_block.sh \
        deltanet-NSDI17-dataset.tar.gz berkeley.csv \
        fave/bench/deltanet/traces/berkeley-inserts.csv

which refuses if any insert follows the cut. So git does NOT reveal a change to
this file, which is the usual guarantee here; the pin replaces it.

**It has its own manifest, `DERIVED.SHA256SUMS`, and that is deliberate.**
`util/raw_data.verify_raw` reads `SHA256SUMS` and fails on any listed file that
is absent, so listing a gitignored file there would make every checkout without
the archive — CI included — refuse the vendored airtel traces too. Check the
derived file by hand after re-deriving it:

    (cd fave/bench/deltanet/traces && sha256sum -c DERIVED.SHA256SUMS)

Nothing reads it yet: no workload is registered for it, and `trace.py` names
the two airtel files explicitly and would refuse this one on D1 anyway.

