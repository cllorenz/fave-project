# Incremental axis — indicative calibration, 2026-10-10

**Indicative, not reportable** (`limit_class=dev`, one repetition, the machine as
memory cap). Protocol: [`PROTOCOL.txt`](PROTOCOL.txt), committed before the run.
Every number below is generated from the raw records in `cells/` and `oracle/`
(`bench/incremental_table.py` → [`table.md`](table.md), [`summary.json`](summary.json));
nothing is typed. Streams: the first 200 updates of S1, S2 (20%, seed 1) and S3
(shorter streams whole), batch 1. Times in ms. Machine: 16 cores, 62 GB, no swap
(stamped in each `cell.json`).

## Predictions, checked

| | prediction | outcome |
|---|---|---|
| P1 | every stream without refusals agrees across engines | **failed on `wl_example` S1 and S2, explained** — below; all other 7 streams agree on every update |
| P2 | every oracle run passes | **held**: 6 of 6 (sample, full and from-zero halves) |
| P3 | APKeep refuses nothing on `wl_ifi`/`wl_airtel1`, 2 on `wl_example` S1 | **held** |
| P4 | precision: NetPlumber > VeriFlow-FR and > APKeep where a verdict changes | **held** on all 7 such streams |
| P5 | `wl_airtel1` S2 median `t_total`: NetPlumber, APKeep < 50 ms; VeriFlow-FR < 2 s | **held**: 0.43, 3.51, 635 ms |
| P6 | APKeep median `t_update` on `wl_ifi`, `wl_example` < 50 ms | **held**: 0.43–4.33 ms |

## P1: the `wl_example` disagreement is a translation difference, not an update defect

On `wl_example` S2, deleting `pgf.forward_filter` rule 0 (anti-spoofing: drop
packets from the internet with an internal source) makes NetPlumber and
VeriFlow-FR report `! source.internet → probe.office (NEW)` violated; APKeep does
not. On S1, deleting `pgf.routing` 49152 does the same for
`! source.dmz → probe.internet (NEW)`. Both engines pass their own oracle on these
streams, and **built from zero** the modified models give the same split
(NetPlumber == VeriFlow-FR ≠ APKeep, on exactly that check).

The cause is `-o` (an `out_port` match) in the FORWARD chain. FaVe's packet
filter model runs the filter chain *before* `routing`, so `out_port` is still a
wildcard there: NetPlumber and VeriFlow-FR let the `out_port = pgf.1` slice of a
flow through rule 6 (`-o pgf.1 -s office → ACCEPT`), and `routing` then sends it
by destination — to `office`. APKeep resolves `-o` against the FIB
(`_lpm_destinations`), as netfilter does, where routing decides the interface
first. `docs/ACCOMMODATIONS.md` records all three as correct on `wl_example`;
that holds for the shipped model only, because rule 0 drops the spoofed traffic
first. **Open for the owner**: which semantics FaVe's packet filter means.

## What else the calibration shows

- **Selectivity.** NetPlumber re-checks 0.2–4% of the checks per update on
  `wl_ifi`/`wl_airtel1`; APKeep's element footprints 3–24%; VeriFlow-FR's source
  footprints 14–18% on `wl_ifi` but **100% on `wl_airtel1` S1/S2** — every source
  reaches every switch, so it re-checks all 256 checks on every route update
  (≈ 630 ms each) although none changed.
- **No verdict changes in 200 route updates** on `wl_airtel1` S1 and S2:
  existential reachability survives single route deletions there. The campaign's
  airtel streams need longer prefixes of the stream (or S3) for precision to mean
  anything.
- **APKeep link updates are slow**: `wl_airtel1` S3 median 556 ms, all of it the
  whole-model re-translation (the FIB path covers rules only). NetPlumber: 2.9 ms.
- APKeep's route updates on `wl_airtel1` take the per-rule FIB path: median
  `t_update` 1.2–1.4 ms.

## Not covered

`wl_up`, `wl_stanford`, `wl_i2`, `wl_cloud`, `wl_berkeley`; batches > 1; seeds
other than 1; repetitions. NDD-APKeep does not exist yet.
