# Surveying the Delta-net archive

What produced `CLOUD_BENCH_PLAN.md` **§2.14 (D8)** — the measurement that closed
the question of whether the Delta-net distribution holds any workload beyond the
two already built.

**The archive is not kept** (owner, 2026-09-18; 9.6 GB). So nothing here can be
re-run without Claas re-supplying `deltanet-NSDI17-dataset.tar.gz`,
sha256 `cc67472319e5d4791b96d8ceed1a5038af1ea719c360c3ce30040f3cc17f334b`.
The method is kept anyway, because §2.14 quotes a great many figures and the
alternative is that they rest on shell history — the exact debt §2.2's D0
records settling for the vendored traces themselves.

    ./survey.sh opmix  /path/to/deltanet-NSDI17-dataset.tar.gz /tmp/out
    ./survey.sh replay /path/to/deltanet-NSDI17-dataset.tar.gz /tmp/out

Nothing is extracted to disk: `tar --to-command` streams each member through a
reader, so a 16 GB member costs time and no space. One full decompression pass
was 5m43s (132 MB/s) on the 2026-09-25 box. tar is sequential, so reaching a
member costs everything *before* it rather than its own size.

## The two passes, and why there are two

`opmix.awk` counts the first character of every line and nothing else. No dict,
so no memory ceiling and no member is ever truncated. This is what answers
*insert-only, or removals too?*.

`replay.awk` maintains the live FIB — `(router, prefix) -> next_hop, field4` —
applying `+` and `-` in file order, and at EOF emits the terminal snapshot in
the trace's own `+<prefix>,<router>,<next_hop>,<field4>` format so that
`bench/deltanet/trace.py` consumes it unchanged. It holds one entry per live
rule, so it is the pass that can run out of memory; `CAP` aborts a member
cleanly (`exceeded_cap=1`) rather than inviting the OOM killer. At 45M keys it
completed `rf1755.csv` (peak 33.7M) and would not complete `inet.csv`
(peak ~124.7M).

Both deliberately avoid `trace.py`, which **refuses** a withdrawal by design —
and withdrawals are the whole subject.

## Validation

Neither reader was trusted before it reproduced something already pinned:

* `opmix`/`replay` on `airtel1-only-inserts.csv` reproduce every figure in
  `TRACES.md` — 38,100 inserts, 1,400 prefixes, 57 routers, 52 next-hops, the
  158-vs-155 edge split, zero D1 violations, and the 18-bucket prefix-length
  histogram bucket for bucket. An independent `mawk` reimplementation agreeing
  with the pinned Python derivation cross-checks both.
* Replaying an insert-only trace is the identity function, and it reproduces
  `airtel1-only-inserts.csv` **byte for byte**.

## What it found

| member | lines | inserts | withdrawals | terminal FIB |
|---|---:|---:|---:|---:|
| `airtel1-only-inserts.csv` | 38,100 | 38,100 | 0 | 38,100 |
| `airtel2-only-inserts.csv` | 38,100 | 38,100 | 0 | 38,100 |
| `airtel1.csv` | 14,155,633 | 7,328,721 | 6,826,912 | **38,100** |
| `airtel2.csv` | 505,249,128 | 292,715,964 | 212,533,164 | **46,259** |
| `berkeley.csv` | 25,635,804 | 12,817,902 | 12,817,902 | **0** |
| `berkley-ribs-…-random.csv` | 25,635,804 | 12,817,902 | 12,817,902 | 0 |
| `inet.csv` | 249,467,112 | 124,733,556 | 124,733,556 | 0 † |
| `rf1755.csv` | 67,465,738 | 33,732,869 | 33,732,869 | **0** |
| `rf3257.csv` | 148,985,840 | 74,492,920 | 74,492,920 | 0 † |
| `rf6461.csv` | 150,011,476 | 75,005,738 | 75,005,738 | 0 † |
| `rf1755.links.csv` | 33,735,177 | 33,732,869 | 0 | 33,732,869 |

† **inferred, not measured** — balanced op mix plus two fully-replayed members
sharing the signature. Their peak live-key count exceeds what `mawk` holds here.

Bolded terminal FIBs were replayed in full. `rf1755.links.csv` also carries
2,308 trailing `]<a>,<b>` lines: an undirected 87-node edge list, the only
topology stated anywhere in the archive outside Airtel's node naming.

The conclusion, in §2.14: the archive yields exactly the two workloads already
built. Every non-airtel member is a throughput trace that inserts a routing
table and withdraws all of it, and both derivations that let FaVe read a
Delta-net trace — the `5*plen+100` priority identity and `s<i>-<j>` as
`(switch, port)` — are Airtel-only.
