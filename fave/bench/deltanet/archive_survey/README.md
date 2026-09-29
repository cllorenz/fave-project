# Surveying the Delta-net archive

What produced `CLOUD_BENCH_PLAN.md` **§2.14 (D8)** — the measurement that closed
the question of whether the Delta-net distribution holds any workload beyond the
two already built.

**The archive is not part of the repository** (owner, 2026-09-18; 9.6 GB), and
`.gitignore` names it so that a copy in the checkout cannot be committed. Claas
re-supplied it on 2026-09-25 for this survey, and since 2026-09-29 the owner
KEEPS it in the checkout root, because `berkeley-inserts.csv` is derived from it
rather than vendored (`../traces/README.md`). A checkout elsewhere may still
lack it, which this file cannot know. Re-running anything here needs
`deltanet-NSDI17-dataset.tar.gz` with
sha256 `cc67472319e5d4791b96d8ceed1a5038af1ea719c360c3ce30040f3cc17f334b` —
check the hash before trusting a copy, since that is what identifies it.
The method is committed regardless, because §2.14 quotes a great many figures and the
alternative is that they rest on shell history — the exact debt §2.2's D0
records settling for the vendored traces themselves.

    ./survey.sh opmix  /path/to/deltanet-NSDI17-dataset.tar.gz /tmp/out
    ./survey.sh replay /path/to/deltanet-NSDI17-dataset.tar.gz /tmp/out
    ./survey.sh phase  /path/to/deltanet-NSDI17-dataset.tar.gz /tmp/out
    ./survey.sh revisions /path/to/deltanet-NSDI17-dataset.tar.gz /tmp/out
    ./opening.sh       /path/to/deltanet-NSDI17-dataset.tar.gz /tmp/out
    ./insert_block.sh  /path/to/deltanet-NSDI17-dataset.tar.gz berkeley.csv out.csv

Nothing is extracted to disk: `tar --to-command` streams each member through a
reader, so a 16 GB member costs time and no space. One full decompression pass
was 5m43s (132 MB/s) on the 2026-09-25 box. tar is sequential, so reaching a
member costs everything *before* it rather than its own size.

## The first two passes, and why there are two

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

"Inserts a routing table and withdraws all of it" was a description of the
BALANCE when it was written: `opmix` counts ops and cannot see their order. The
`phase` pass below measures the order, and it holds exactly.

## The third pass: `phase` (2026-09-28)

`phase.awk` records where the last insert and the first withdrawal fall, so it
answers whether a trace's inserts form a contiguous block (lines 1..N, first
`-` at N+1) or are interleaved with its withdrawals. That is what decides
whether the full insert set is a state the trace actually passes through — the
state after line N — or merely the union of rules that were live at different
times. It also records whether field 4 is monotone across the inserts, and a
histogram of how many routers carry a rule for each prefix. It keeps dicts over
prefixes and routers only, never over rules, so no member is truncated; the
price is that it cannot count insert revisions, which `replay` does.

**Validated before use**: on `airtel1-only-inserts.csv` it reproduces
`TRACES.md`'s 38,100 inserts, 57 routers and 1,400 prefixes, and its histogram
sums back to 38,100 rules over 1,400 prefixes; two six-line synthetic traces,
one blocked and one interleaved, are told apart (`inserts_after_first_
withdrawal` 0 against 2), as are a monotone and a non-monotone field 4.

Full pass 2026-09-28, 19m02s (it reads every member, the 505M-line
`airtel2.csv` included):

| member | inserts = lines 1..N | first `-` | `+` after it | field 4 falls on | routers | prefixes | routers per prefix |
|---|---:|---:|---:|---:|---:|---:|---|
| `berkeley.csv` | 12,817,902 | N+1 | 0 | 50.0% of steps | 23 | 584,944 | **22** (534,078×) or **21** (50,866×) |
| `inet.csv` | 124,733,556 | N+1 | 0 | 50.0% | 315 | 481,876 | 3–308, mean 258.8 |
| `rf1755.csv` | 33,732,869 | N+1 | 0 | 50.0% | 87 | 635,810 | 3–76, mean 53.1 |
| `rf3257.csv` | 74,492,920 | N+1 | 0 | 50.0% | 161 | 635,810 | 1–151, mean 117.2 |
| `rf6461.csv` | 75,005,738 | N+1 | 0 | 50.0% | 138 | 635,810 | 50–136, mean 118.0 |
| `rf1755.links.csv` | 33,732,869 | — | — | 50.0% | 87 | 635,810 | 3–76, mean 53.1 |
| `airtel1.csv` | — | **38,101** | 7,290,621 | 4.4% | 59 | 1,400 | — |
| `airtel2.csv` | — | **38,101** | 292,677,864 | 3.4% | 60 | 1,400 | — |

(`berkley-ribs-…` is out of scope; for the record its insert half matches
`berkeley.csv` on every column here.)

What it establishes:

* **In every non-airtel member the inserts are one contiguous block**, and the
  first withdrawal is the very next line. The state after line N is therefore
  one the trace passes through: its peak, holding every inserted rule.
* **Field 4 is not a timestamp or sequence number** outside airtel: it falls on
  half of all steps, which is what an unordered per-rule value does. In
  `airtel1-only-inserts.csv` it never falls (170 → 260, sorted by priority).
* **`rf1755.links.csv`'s inserts are `rf1755.csv`'s**, now on eight shared
  fingerprints including the order-sensitive count of falling steps
  (16,864,401) and a 42-bucket histogram — still not a row-by-row comparison.
* **Both full airtel traces open with a 38,100-line insert-only block** before
  their first withdrawal — the size of both vendored files.
* **Delivery is legible in `berkeley` and not in the Rocketfuel traces.** In
  `berkeley` every prefix is carried by all routers but one or two; in
  `rf1755` a prefix is carried by as few as 3 of 87.

## The opening check: `opening.sh` (2026-09-28)

`phase` found both full airtel traces opening with a 38,100-line insert-only
block, the size of both vendored files. `opening.sh` tests the obvious reading:
it takes each full trace's lines **before its first withdrawal** — so the
block's length is measured, not assumed — and compares them, sorted, with the
sorted vendored file. `--occurrence` stops tar after the two members, so it
costs ~1.5 min (1m16s on 2026-09-28) rather than a full pass.

| | opening block | rows only in it | rows only in vendored | sorted sha256 (both) | file order |
|---|---:|---:|---:|---|---|
| airtel1 | 38,100 | 0 | 0 | `5036ba2e…` | different |
| airtel2 | 38,100 | 0 | 0 | `21024e37…` | different |

**Each vendored `-only-inserts.csv` is its full trace's opening insert block**,
as a set: the forwarding state before the first failure is injected. Only the
row order differs, which no FIB can observe. airtel1's `5036ba2e…` is the
sorted-form hash §2.14 recorded for its terminal FIB (the raw vendored file,
unsorted, is `b8076678…` in `../traces/SHA256SUMS`).

This is the mechanism §2.14 said it could not name: the vendored airtel2 file
was never a trimmed terminal FIB but the opening state all along, and both
files were made the same way. That airtel1's churn happens to return to its
opening state, and airtel2's does not, is measured; why is not. (Recovering
each single-link failure before the next, as the paper describes airtel1,
would be consistent with it, but nothing here tests that.)

## The fourth pass: `revisions` (2026-09-28)

`phase` shows the insert block is contiguous; it does not show that the block
holds each `(router, prefix)` once, and without that the peak state is smaller
than the insert set. `replay` answers it only up to its 45M-key cap, so it never
did for `inet`, `rf3257` or `rf6461`. `revisions` answers it with no ceiling:
every `+` line before the first withdrawal becomes `router,prefix,next_hop`,
`sort -u` (disk-backed, 3 GB buffer) gives the distinct rules, and `uniq` on the
key columns gives the distinct keys; `revisions = block lines - distinct keys`.
Validated on a synthetic trace with a same-key insert to a new next hop and an
exact repeat (2 revisions, correctly), and against the two members `replay`
completed.

Full pass 2026-09-28, 9m41s (inet's 5.9 GB sort is 221 s of it):

| member | insert block | distinct keys | revisions |
|---|---:|---:|---:|
| `berkeley.csv` | 12,817,902 | 12,817,902 | 0 (replay: 0) |
| `rf1755.csv` | 33,732,869 | 33,732,869 | 0 (replay: 0) |
| `rf3257.csv` | 74,492,920 | 74,492,920 | **0** — first measurement |
| `rf6461.csv` | 75,005,738 | 75,005,738 | **0** — first measurement |
| `inet.csv` | 124,733,556 | 124,733,556 | **0** — first measurement |
| airtel1/2 opening blocks, both `-only-inserts` | 38,100 each | 38,100 | 0 |

So **in every non-airtel member the peak state is exactly the insert set**:
every inserted rule is live at line N, and none has been replaced.

One defect in the run, fixed after it: the pass read every line of the block,
not only `+` lines, so `rf1755.links.csv` reported 33,735,177 block lines —
its 33,732,869 inserts plus its 2,308 trailing `]a,b` edge lines. It too had
0 revisions, and that carries over to the inserts alone: the edge lines are
distinct from each other and from every rule, and dropping distinct lines
cannot create a duplicate. The filter is now in `survey.sh`; the run was not
repeated for it.

## Extracting a snapshot: `insert_block.sh` (2026-09-28)

Not a survey pass but the step after one: it writes one member's insert block —
every line before its first withdrawal, in the trace's own format and order —
to a file, and REFUSES (deleting the output) if any insert follows the cut, so
a trace that interleaves cannot be mistaken for one that does not. Tested on a
synthetic archive with one blocked and one interleaved member before use.
First used for `berkeley.csv` (12,817,902 lines, sha256 `96d57987…`), extracted
into `bench/wl_berkeley/` and moved on 2026-09-29 to
`fave/bench/deltanet/traces/berkeley-inserts.csv` (owner): gitignored, re-derived
from the kept archive by this script, and pinned in `traces/DERIVED.SHA256SUMS`;
`CLOUD_BENCH_PLAN.md` §2.15.

## Measuring a snapshot: `snapshot_survey.py` (2026-09-28)

    python3 snapshot_survey.py <snapshot.csv> [--switch-prefix]

Adjacency and its symmetry, per-prefix delivery points and loops, chain
lengths, how delivery is laid out in address order, and nested prefix pairs
that a model could get observably wrong — for any file in the trace format,
without `trace.py`'s airtel-only assertions. Validated against every figure
`TRACES.md` and `test_deltanet_lpm.py` pin for airtel1 (`--switch-prefix` groups
airtel's `s<i>-<j>` nodes by switch for that). Results for `berkeley`:
`CLOUD_BENCH_PLAN.md` §2.15.

