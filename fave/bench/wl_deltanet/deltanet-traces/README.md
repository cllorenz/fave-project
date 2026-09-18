# Delta-net NSDI'17 traces — the scoped extract

These two files are the **entire** in-repo raw data for the planned Delta-net
workload (`CLOUD_BENCH_PLAN.md` §2). They are vendored rather than extracted on
demand: the source archive is not kept, because at 9.6 GB it does not belong in
a repository or on the working machine.

| file | size | what |
|---|---:|---|
| `airtel1-only-inserts.csv` | 1.2 MB | insert-only forwarding-rule trace |
| `airtel2-only-inserts.csv` | 1.2 MB | insert-only forwarding-rule trace |

Format is `+<prefix>,<router>,<next_hop>,<N>`, e.g.

    +100.3.0.0/16,s10-1,s2-9,180

Measured on `airtel2-only-inserts.csv`: **38,100 inserts, 57 routers, 52
next-hops, 1,400 distinct prefixes**, prefix lengths 14–25 (so genuine LPM). The
fourth field takes 18 distinct values in 180–220 and **its meaning is not
established** — settling that is step D1, before any converter is written.

## Why only these two

Owner scope decision 2026-09-18. The archive holds 11 CSVs totalling ~40 GB, and
several members are individually larger than a working disk (`airtel2.csv`
16.0 GB, `inet.csv` 14.4 GB, `rf3257.csv`/`rf6461.csv` 4.8 GB each). An
insert-only trace replays to a well-defined final FIB with no deletions, which
is what the planned static-snapshot phase needs.

## Provenance

Source archive `deltanet-NSDI17-dataset.tar.gz`,
sha256 `cc67472319e5d4791b96d8ceed1a5038af1ea719c360c3ce30040f3cc17f334b`,
members owned by `ali/ali`, dated 2016-09, re-tarred 2019-10.

**The download URL was never recorded.** If these files ever need re-deriving
from the archive, the archive has to be supplied again — see
`CLOUD_BENCH_PLAN.md` §1.8. `SHA256SUMS` here covers both traces so that a
re-supplied archive can be checked against what this repository already has.
