# Incremental reverification — a plan

**Status: M1 and M2 BUILT (2026-10-11); D11 RUN (2026-10-12/13, §10 step 9); next the campaign protocol (D10).**
Decisions D1–D9 are the owner's, taken in discussion on 2026-10-09 (§4), as are
O1–O6 (§9). §10 records what is built: NetPlumber, VeriFlow-FR, BDD-APKeep and
NDD-APKeep take updates and re-verify selectively, held to the oracle (APKeep at
its witness + dead-ends footprint, the default since 2026-10-11); the harness is
done. Only indicative (dev) runs have run (§10), the last the D11 grid; no
reportable measurement exists until the campaign's `PROTOCOL.txt` with
predictions is written. §8.2 (2026-10-14) designs device removal, owner questions Q-R1–Q-R4 answered; built the same day on NetPlumber, on ad6 from its buffers, and by emptying on VeriFlow-FR and BDD-/NDD-APKeep; NDD-Flood refuses it by name. D-R6 (a structurally changed re-send replaces the device) built 2026-10-15 on NetPlumber and ad6.
**Owner:** Claas Lorenz. **Branch:** `updates` (merged into `ai`). **Tracks:** TODO item 31, "the
incremental axis". Siblings: [`MEASUREMENT_RUN_PLAN.md`](MEASUREMENT_RUN_PLAN.md)
§10 (which names this as "a second campaign"), [`ACCOMMODATIONS.md`](ACCOMMODATIONS.md).

> **Naming (2026-10-16):** the engine this document calls NDD-Flood was called "NDD" (selected by `--apkeep-engine ndd`) before 2026-10-16. Since then `--apkeep-engine ndd` selects NDD-APKeep, and NDD-Flood is `--apkeep-engine ndd-flood`. Names of earlier result cells and files (e.g. `wl_tum_ndd`) keep the old name and mean NDD-Flood.

---

## 1. What this is for

Every FaVe benchmark today builds the whole model from zero and verifies it
once. NetPlumber, VeriFlow and APKeep were each published as engines that
re-verify **after a change** — a rule inserted or deleted, a link taken down —
by adapting their model and re-checking only what the change touched, and their
papers headline how fast that is. FaVe's own TNSM'21 paper promises the same
for FaVe: "continuous reverification … after configuration changes" (Sec. I,
p.2), with an aggregator that "calculates an increment and feeds it into the
verification engine" (Sec. V, p.9, Fig. 4). **Neither promise has ever been
measured here**, and the code path behind FaVe's was never finished (§2).

The owner's framing (2026-10-09): *"The purpose of engines with incremental
support is faster reverification and that should be made available in the
applications that use these engines. FaVe should know of the affected parts of
the network model and only affected compliance checks should be reverified."*

So this plan has two goals, in this order:

1. **Make incremental reverification work in FaVe** — engines that apply a
   change, report what it affected, and a FaVe that re-verifies only the
   affected compliance checks, provably giving the same verdicts as a rebuild.
2. **Measure it fairly across engines** — per-update cost, as the aggregate of
   update and re-verification (D2), on declared update streams (D7).

Reproducing the three papers' numbers is **not** a goal (D5).

## 2. Where the implementation stands (2026-10-09)

Evidence-backed; file:line references are as of commit `79fd4825`.

**Engines — mostly capable inside.**

| engine | incremental inside the engine | tested |
|---|---|---|
| NetPlumber (C++) | rule and link add/remove propagate flows along pipes (`net_plumber.cc` `_add_rule`, `remove_rule` → `~RuleNode`, `add_link`, `remove_link`) | C++ unit tests on pipes and flow statistics, not verdicts |
| BDD-APKeep (Java) | `Network.updateRule` (`Network.java:434`): `+`/`-` for every element type, then a loop check | `test_apkeep_lib.py` replays a Stanford trace with 4,526 removals against a loop golden |
| NDD-Flood (Java) | **none** — from-zero `build`; `AtomForwarding` ignores the op | — |
| VeriFlow-FR (C++) | `Network::add_rule`/`remove_rule` return affected ECs; `remove_link` | `oracle_unit`, `rewrite_unit`; `remove_rule` only indirectly; `remove_link` untested |
| ad6 | none — a fresh bridge subprocess per check | — |

**Adapters — none can do it.** NetPlumber's incremental *adds* work because the
engine is live; its `delete_rules` cannot run (`adapter.py:972`: indexes `Rule`
objects as tuples, passes a table name as an index, removes only the first
negation expansion) and is unreachable. A second batch for a declared-LPM table
is refused (`LpmOrderingError`; lifted by O1, §10). APKeep builds once and, since `973736fb`,
refuses every change after the build; ad6 refuses the two it got wrong
(`29fdadd9`). VeriFlow-FR rebuilds from scratch on any change, and its
deletions raise.

**Aggregator — deletion was never finished.** `_sync_diff` sends engines only
the added part; the removal half is commented out (`aggregator_service.py:774`).
`__sub__` on firewalls, switches and routers returns the pending adds and
ignores the old model. `remove_rule` is broken in both device models, and the
`_deletes` buffer is written but never read. A device `del` is ignored. Nothing
re-checks after a change; `check_compliance` evaluates whatever check set the
client sends.

**Modelling engines — indices are not stable.** The packet filter spaces its
indices internally (`2·idx·rules_size + rule.idx`, `iptables/generator.py:420`,
`:500`) and then renumbers the interwoven table densely on output
(`_interweave_state_shell`, `:511`). One rule inserted shifts every later index,
so a rule-level diff sees the whole table as changed.

**Harness and workloads.** No phase, metric or stamp for an update exists. No
workload contains churn: `wl_airtel1/2` and `wl_berkeley` are the opening
insert blocks of their traces. `wl_state_snapshots` was retired to
`bench/legacy/` (`79fd4825`, D8).

**One latent engine defect found on the way:** in NetPlumber, adding a rule at
an index that is already occupied stores the new rule under the id
`(table<<32)+index`, then frees the old rule — which has the same id — and so
erases the new rule's entry from `id_to_node` (`net_plumber.cc:1052–1056`,
`free_rule_memory` `:237`). The new rule then cannot be found or removed. FaVe
never reuses an index today; incremental updates will.

## 3. What the papers mean by "incremental", in brief

| | NetPlumber (NSDI'13) | VeriFlow (NSDI'13) | APKeep (NSDI'20) |
|---|---|---|---|
| timed per update | flow propagation + probe evaluation | find affected ECs, build their graphs, query | model update + loop check, one number |
| checked | probe policies | loops, black holes | loops |
| update stream | snapshot diff (Google WAN); 7% delete/re-add (Stanford); load 90%, time 10% | 90k BGP updates → FIB changes, dst-IP only | snapshot inserted rule by rule, then deleted in reverse; Delta-net traces |
| headline | median 0.05–0.77 ms, mean 2–6 ms; link-up 1.5–4.8 s | mean 0.38 ms; link failure 1.15 s | mean 6–127 µs |

None of them re-checks reachability compliance per update, which is FaVe's
question; a FaVe result is a new measurement, and is presented as one. All
three report means dominated by a tail (NetPlumber's mean and median differ by
up to 47×), so distributions are reported here, not means alone (§7).
TNSM'21 measures only build-from-zero plus one verification.

## 4. Decisions (owner, 2026-10-09)

- **D1. Default invariant checks are part of the update cost.** If an engine's
  authors check an invariant by default — or the engine needs it to work at
  all, as NetPlumber's propagation needs its loop guard to terminate — it is
  charged to the update, with a brief note. Invariant checks are **never added**
  to engines that do not run them by default.
- **D2. The compared per-update number is the aggregate, update +
  re-verification.** Where an engine spends its traversal does not matter to
  FaVe: NetPlumber traverses eagerly at update time, VeriFlow-FR lazily at query
  time (its update is the trie plus the affected ECs; its cycle guard, Q4's
  revisit rule, lives in the query), APKeep in between. The parts are shown; the
  sum is compared. Update latency alone would credit a lazy engine with work it
  only postponed.
- **D3. Selective re-verification is a goal.** FaVe learns from the engine what
  an update affected and re-verifies only the compliance checks that belong to
  it. For NetPlumber: the reachability trees that changed, by root and leaf.
  APKeep's and VeriFlow-FR's by-products need investigation (done, §6.3).
- **D4. Granularity is open.** One update per re-verification is the ideal;
  batches or windows (e.g. hourly) if FaVe or an engine cannot keep up. This
  plan makes it a measured parameter (§7).
- **D5. Reproducing the papers is not a goal.** Invariant results are kept as
  by-products where they come for free.
- **D6. NetPlumber's probe-condition mechanism stays retired** (`LEGACY_CHECKS`,
  commit `4bdbe622`); D3's tree reporting replaces it.
- **D7. Update streams S1–S3 first** (§7): insert-then-reverse-delete, random
  delete/re-add, link down/up. The full airtel traces (real churn) stay out of
  scope for now, to be discussed later. There is no real firewall change
  history, so firewall edit streams (milestone 2) are synthetic and say so.
- **D8. `wl_state_snapshots` is retired** to `bench/legacy/`, not repaired: it
  measures runtime state tracking, which TNSM'21 replaced.
- **D9. Two milestones.** M1, the engine layer, first; M2, the FaVe layer —
  the owner's three stability requirements (§8) plus aggregator deletion.
- **D10. M2 before the campaign (owner, 2026-10-11).** M1 is built, but its
  campaign waits: M2 is done first, starting with the packet-filter spike
  (§8), and the campaign then covers both milestones, S4 included. It runs on
  **another machine** (64 GB, enough cores) — so the tree here is not frozen
  for it, and the calibration that precedes its protocol (O4.5) is repeated
  there: the dev calibrations on this machine size nothing on that one.
- **D11. One indicative run of the whole grid, after M2 is built (owner,
  2026-10-11).** Every experiment of the campaign (O4's grid: all workloads,
  engines and streams S1–S4, batch sizes included) runs **once** on this
  machine, `limit_class=dev`, before the campaign. It replaces a projection of
  the campaign's size: its numbers, not an extrapolation from 200-update
  calibrations, are what the grid is cut by. Under its own `PROTOCOL.txt` with
  predictions, which decides whether cells run in parallel and whether the O3
  oracle runs are part of it. Order: M2 → this run → the campaign elsewhere.
- **D12. VeriFlow-FR's footprint: scope first (owner, 2026-10-11).** All three
  engines' footprints are FaVe's design, and only APKeep's is refined, so
  `t_total` would partly measure FaVe's effort per engine. Before deciding
  whether VeriFlow-FR gets witness and dead ends, a scoping pass:
  [`VERIFLOW_FOOTPRINT_SCOPE.md`](VERIFLOW_FOOTPRINT_SCOPE.md). **Decided the
  same day:** all proposed parts (witness, dead ends, per-pair reporting, the
  concrete packet), built after the M2 packet-filter spike and before the D11
  run; a per-target re-walk stays out. Order: M2 spike → VeriFlow-FR footprints
  → rest of M2 → D11 run → campaign.
- **D13. The grid's workloads (owner, 2026-10-11)**, for the D11 run and the
  campaign. S1–S3 at batch 1 and S2 at batches 10/100/all on: `wl_example`,
  `wl_ifi`, `wl_cloud`, `wl_airtel1`, **`wl_airtel2`** (kept by the owner against
  my recommendation; smoke-run 2026-10-11, 10 S2 updates on NetPlumber and
  VeriFlow-FR, oracle equal throughout), `wl_up`, `wl_stanford`, `wl_i2`; all
  four incremental engines, except BDD-APKeep on `wl_stanford`/`wl_i2`, recorded
  as **no cell** (from-zero DNF in V5). `wl_tum`: `t_update` only (no checks).
  S4 (M2): `wl_ifi`, `wl_cloud`, `wl_up`, `wl_tum` (§8). **Not run:** ad6 and
  NDD-Flood (no incremental path; a per-update rebuild is their V5 from-zero
  cost, which the break-even share already cites); `wl_berkeley` (may join the
  campaign as a size point after the D11 numbers).
- **D14. Every measurement is driven through FaVe (owner, 2026-10-09,
  restated 2026-10-16).** Updates enter through the aggregator, as an end user's
  would, never directly at an engine or adapter: only that makes the engines'
  numbers comparable from an end user's perspective. Direct engine interaction
  stays allowed for limited experimentation (feature development, bug fixing).
  The 2026-10-09 ruling ("our goal is to run the incremental benchmarks through
  FaVe") was not carried into §6, so S1-S3 were applied at the adapter and D11
  measured them so; only S4 went through the aggregator. Consequence: S1-S3 are
  redefined as FaVe-level changes before the campaign, and D11's S1-S3 numbers
  are engine-level, indicative only.
  *Built 2026-10-16 (owner: "build the switch-command deletion with batches -
  test first"):* FIB routes now leave and return through FaVe's control-plane
  command, `switch_command`, the one every benchmark already fills its FIBs
  with (`switch.py -a -r`, a batch per table).
  - **Client:** `switch.py -d -r` and `-u -r` send a batch as one
    `remove_rule` / `update_rule` (a delete needs node, table and index); a
    batch names one node.
  - **Devices:** a rule is named by its sender's index, not its list position
    (switch and router deleted by position before). `removal_keys` says which
    engine rules a sender's rule became -- a packet filter's route `i` is
    keep 2i and drop 2i+1 of `.routing` -- in one pass per table;
    `drop_rules` takes them out and records `(table, index)` in `_deletes`.
  - **Aggregator:** `_remove_commanded` refuses the whole batch untouched for
    an unknown device or index, or a table it numbered itself; else one
    `delete_rule` per engine rule, and the stored model, the stable indexer
    (`StableIndexer.drop`) and the LPM index (now reference-counted per
    prefix) forget them. `update_rule` is that delete, then the add path.
  - **Adds to a built lazy engine:** VeriFlow-FR and APKeep record
    `add_rules` until their first check builds the model and refused every
    later one; an engine now says so (`takes_updates()`, default False;
    NetPlumber stays on `add_rules`), and the aggregator then sends a
    command's rules as `insert_rule`, as S4's re-send already did.
  - **Found on the way, both fixed:** (1) a packet-filter route inserted keep
    first passes through a keep without its drop, which APKeep cannot express
    (`UntranslatedSemantics`); inserts now go drop first
    (`insertion_order`), deletes keep first, so every state between is a
    route an engine can express. (2) An add at an index the table still holds
    -- left by a partly refused delete -- was appended in the stored model
    while the engine refused it, so the two diverged; such an add is now
    refused untouched (a modify is `update_rule`). No workload's routes repeat
    an index (checked over all, `wl_berkeley`'s 4.48 M included), so no build
    changes.
  - **An engine refusal mid-batch** (APKeep's structural one, §6.3) leaves the
    rules deleted before it gone from engine and model alike, the rest in
    both, and propagates; a route can so end half deleted, which is a
    discard route.
  - **Tested:** 21 new fast-tier tests (aggregator, devices, client);
    `test_incremental_route_commands.py` (integration) holds every engine to
    the oracle with seeded route streams -- selective = full after every
    command, = a from-zero build of the model the aggregator holds at
    checkpoints -- on `wl_example` (every route, one by one and in batches of
    3) and `wl_cloud` (5 %, 87 routes, one by one and in batches of 10);
    BDD-APKeep only on `wl_example`. 14 passed; APKeep refuses 2 commands
    (deleting and re-adding `pgf`'s default route). Two mutations (the engine
    never told of a delete; of an insert) fail it.
  *S1-S3 through FaVe, built 2026-10-16 (owner: "continue with S1-S3
  through FaVe"; `util/fave_streams.py`, `bench/incremental_run.py`).* The
  units are what a user changes: a **configuration rule line** (iptables `-A`,
  a router's `access-list` entry), changed by editing the file and re-sending
  the device (the stable-index diff of §8.1, as S4); a **route** of
  `routes.json`, by `switch.py -d -r` / `-a -r`; a **link** of the topology,
  policies or sources, by `topology.py -d -l` / `-a -l`. S1 deletes every rule
  in reverse build order (configuration lines, as the devices are created,
  then routes) and inserts them in build order; S2 a seeded fraction; S3 each
  link down and up. A batch is sent as the fewest messages that keep its
  order (consecutive updates of one kind, direction and device), then
  re-checked once. Per batch the records add `messages` and split the time
  into `t_model_s` (re-sends regenerating the device), `t_diff_s` and
  `t_update_s` (the rest of FaVe and the engine), so `t_total` is a user's
  change to an updated verdict. The stream is the same file for every engine,
  so `incremental_compare.py` compares cells as before. `--at-adapter` keeps
  M1's path, for development only; every cell stamps `driven`.
  - **What changed underneath:** a built lazy engine takes link changes as
    `set_link` (the aggregator called `remove_link`/`add_link`, which
    VeriFlow-FR and APKeep refuse after the build), with the aggregator's and
    the engine's adjacency kept by the aggregator. And **every message is all
    or nothing**: a rule command, a link command or a configuration re-send
    that the engine refuses midway is undone (the deletes inserted again, the
    inserts deleted, the stable indexer restored), so a refusal changes
    nothing anywhere and the stream's state is exactly FaVe's. Before, a
    refusal could leave a route half deleted, or a re-send's engine state
    ahead of the stored model and the indexer.
  - **The oracle** builds the workload's current state from zero
    (`FaveWorkload.zero_prefix`: configurations as edited, routes present,
    links up) -- no engine-level withholding.
  - **Units and sizes:** `wl_up` 3,252 configuration lines (136 files) and 318
    routes; `wl_tum` 3,794 lines and 249 routes; the other grid workloads are
    switches, routes only (`wl_airtel1` 39,500).
  - **Tested:** 8 fast unit tests (`test_fave_streams.py`, a fake FaVe), 6
    for the link path and the undo; `test_incremental_fave_streams.py`
    (integration) holds all four engines to the oracle on `wl_example` (S1,
    S2 in batches of 3, S3) and `wl_cloud` (S2 5 %, S3 in batches of 3):
    18 passed, 2 skipped (BDD-APKeep, `wl_cloud`); APKeep refuses 2 messages
    of `wl_example` S1 (`pgf`'s default route). Every engine sees the same
    number of verdict changes in every stream. A mutation that keeps the
    bookkeeping but never tells a lazy engine of a link fails it. The D11
    numbers for S1-S3 stay engine-level and indicative.

- **D15. The campaign grid, cut (owner, 2026-10-16).** `wl_example` and
  `wl_ifi` leave the campaign entirely: they answer functional questions, not
  performance ones (S4 then runs on `wl_cloud`, `wl_up`, `wl_tum`).
  `wl_airtel2` stays although it resembles `wl_airtel1`: either it shows
  unexpected differences between two workloads of similar size, or it supports
  the hypothesis that equally sized workloads need similar effort. **The
  footprint ablation is reduced (owner, 2026-10-16):** coarse against witness +
  dead ends (the default) on every workload, for the three engines with
  footprint modes; witness alone and dead ends alone only as indicative cells,
  once, on `wl_cloud` and `wl_airtel1`. Basis, D11: witness + dead ends
  re-checked least in 39 of 39 complete groups and was fastest in 27; the
  other 12 within 1-14 %, each a sub-second cell or an S3 cell where dead ends
  cannot act. Supersedes §7's four-footprint table.

- **D16. The indicative run through FaVe (owner, 2026-10-16).** D11's
  S1-S3 numbers are engine-level (D14) and the engines changed since
  (NDD-APKeep B+C+D, VeriFlow-FR's footprint defaults and bounded cache,
  stable indices), so the grid runs once more, through FaVe, before the
  campaign protocol: **12 h wall cap per cell, 4 cells in parallel**,
  `limit_class=dev`, one repetition; the grid of D13 as cut by D15;
  configuration lines stay units of S1/S2 on `wl_up` and `wl_tum` (owner:
  "keep the config lines"); **`wl_tum` with its 8,497 checks** (its
  benchmark runs the derived policy since 2026-10-15). It is preceded by a
  **calibration through FaVe**: the first 50 updates of each cell kind, to
  size the memory limits and ground the predictions. Both wait for the
  VeriFlow-FR `wl_tum` incremental run (TODO item 59) and the integration
  tier; nothing else heavy runs beside them.

- **D17. One campaign: a from-zero phase and an incremental phase sharing
  the model initialization and the first compliance check (owner,
  2026-10-17/19).** The from-zero campaign (V5's measurements) and the
  incremental one converge: each cell initializes the model and verifies
  compliance once, measured and documented as the from-zero campaign does,
  and the update stream continues from that state. The differences are
  settled one after another:
  1. *Shared structure* (2026-10-19): APKeep builds one element per ingress
     port and elides no pass-through filter, for every build -- the from-zero
     model is the one updates go to (`d4172206`; cost in
     `results_apkeep_structure_cost_20261018/FINDINGS.md`). Demultiplexing
     and proper IPv6 handling stay.
  2. *The first check* (2026-10-19, option b): a plain check (tracking off,
     VeriFlow-FR's early exit on) is the from-zero measurement; a separately
     timed footprint pass (one tracked check over the same model) follows as
     the incremental phase's setup. The model is never rebuilt.
  3. *Timing* (2026-10-19): per cell, for every engine, `t_start_s` (engine
     construction, JVM start), `t_load_s` (every modelling element through
     the aggregator -- topology, routes, probes with their links, the
     generators WITHOUT their links), `t_build_s` (the generators' links:
     NetPlumber's traffic propagation; the lazy engines' build, forced
     before the check), `t_check_s` (the plain first check) and
     `t_footprint_s` (the footprint pass). Model initialization is
     `t_load_s`, the build `t_build_s` (owner: NetPlumber's propagation
     belongs to the build, as FaVe's benchmarks add the generator links
     last). V5's `check_compliance_s` for a lazy engine is `t_build_s +
     t_check_s`. Inputs are generated once per workload per campaign, their
     hashes recorded, outside cell time (V5 regenerated them in each cell).
  4. *Process layout* (2026-10-19, option a): both phases in-process
     (`InProcessFaVe`, NetPlumber as `libnetplumber`; the client of a re-send
     in its worker, TODO item 60), one driver for every engine and timers
     read directly. Bridge cells, once per workload x engine, run V5's live
     layout (`cell_run.py` + `benchmark.py`: aggregator process, NetPlumber
     over RPC) for build and first check, measuring what transport and RPC
     add, so the campaign's from-zero numbers can be set against V5's.
  5. *Memory* (2026-10-19): V5's sampler (`cell_run.py`, session RSS every
     second) for every cell, plus per phase of item 3 the cell process's
     start, peak and end RSS (its peak counter reset at each boundary,
     `/proc/self/clear_refs`) and phase marks in the sampler's trail; after
     each phase, outside the timers, a JVM engine's live heap after a full
     collection. Every cell runs under V5's limit class (32 GB RSS, 2 GB
     available-memory floor); packing uses a reservation (the expected peak
     from the calibration), not the limit, and a floor stop is recorded as a
     machine stop, not a did-not-finish. The wall limit is decided with
     difference 8.
  6. *Verdicts* (2026-10-19): the count is DISTINCT violated checks, from the
     per-check verdicts (closes V5's open question, RESULTS.md's `wl_cloud`
     58 against ‡57; the bridge cells keep V5's line count beside it);
     `verdict_valid` = every check answered through the barrier, every build
     message applied, the rounds recorded; `correct`/`wrong_verdict` where a
     workload declares its violations; the adapters' build metrics (APKeep's
     cost metrics with the VLAN denominators) in the head. **No anomaly
     detection** (owner): the anomaly check is not run anywhere in the
     campaign (the bridge cells skip `benchmark.py`'s step); NetPlumber's
     blackhole check is compiled out already (`CHECK_BLACKHOLES`, unset in
     `net_plumber/build/sources.mk`); its loop stop is propagation semantics
     (termination) and stays, its counter (`loop_reports`) is recorded.
  7. *Provenance* (2026-10-19): per cell the hashes of the jars,
     `libnetplumber` and `libveriflow_fr` as loaded, the input-file hashes,
     `jvm_xmx`, `impl`/`upstream`/engine options at the top level, a GC log
     for every JVM cell, the in-process aggregator's log at INFO; per
     campaign `MACHINE.txt` and `ARTIFACTS.txt` as in V5, written at
     declaration and checked again when the queue ends (a hash that changed
     is a finding).
  8. *Parallel cells* (2026-10-19, option a): 4 cells in parallel, each
     pinned to its own 4 of the 16 cores (`taskset`), a JVM cell's GC
     threads set to its 4 cores; a contention sample -- one cell per engine
     x 2 workloads repeated serially, alone and unpinned -- gives a
     contention factor per engine, documented beside the results. Basis:
     APKeep's build + first check, serial against 4 in parallel, median
     ratio 1.04 (0.88-1.22) over 12 pairs (calibration vs the structure-cost
     run).
  9. *Repetitions and limits* (2026-10-19): **12 h** wall limit for every
     cell (owner, superseding O4.1's 24 h); a cell that reaches it is
     recorded as a timeout with its completed prefix ("n of N", O4.2) and is
     not repeated. **Ten repetitions** (O4.4); every cell's from-zero phase is
     one sample, so the from-zero measurement needs none of its own. Per-
     update guard 1 h (O4.3). Seeds: three on `wl_airtel1` and `wl_up`
     (`wl_ifi` left the grid, D15). The warm-up split (first 100 updates)
     and the break-even share stay; the latter now against the campaign's
     own from-zero phase. Estimated ~37 days at 4 jobs on this machine (the
     campaign machine's calibration decides, D10).

## 5. What is measured, per update

For an update `u` applied to a built model with a cached verdict per check:

| quantity | what | from |
|---|---|---|
| `t_update` | apply `u` until the engine's state reflects it, including its default invariant checks (D1) | engine call |
| `affected` | the checks `u` could change, as the engine reports them (§6.3) | engine by-product |
| `t_recheck` | re-verify exactly `affected`, merge into the cached verdicts | FaVe |
| **`t_total`** | **`t_update + t_recheck` — the compared number (D2)** | |
| `precision` | `|affected|` against the number of checks whose verdict actually changed | oracle checkpoints |
| increment size | engine rules added and removed for `u` (1 for a plain rule; more under negation expansion, ingress-port expansion or, in M2, interweaving) | adapter |

**Soundness is checked, not assumed.** Selective re-verification is a claim
that `affected` never misses a check whose verdict changed. At checkpoints the
cached verdicts after selective re-verification must equal (a) a **full**
re-verification of every check on the same engine state and (b) a **from-zero
build** of the same final model on the same engine. A mismatch is a defect and
stops the stream; over-approximation is allowed and shows up as `precision`.

## 6. Milestone 1 — the engine layer

*Superseded for measurements by D14 (2026-10-16): measured streams go through
FaVe. What follows describes M1 as built.*

Updates are applied **directly at the adapter**, bypassing the aggregator, which
cannot delete (§2). This isolates the engines, needs no modelling-engine work,
and proves the selective re-verification design before M2 builds on it.

### 6.1 The replay seam

Record once, replay against any engine:

1. Run the workload's real benchmark through `InProcessFaVe.replay`
   (`util/in_process_driver.py`) against a **recording engine** — a generalised
   `bench/feature_survey.py` `RecordingEngine`, which already snapshots what
   `add_rules` receives — and store the call sequence, the final model per
   device and the parsed check set.
2. Replay that sequence into any backend to build it, then drive the stream
   through the new incremental interface (§6.2).

Rules are identified by `(node, tid, idx)`; `tid` is unique network-wide and
idx per table (enforced by VeriFlow-FR's translator, `translate.py:418`).

### 6.2 The incremental engine interface

Added to `AbstractVerificationEngine`, defaulting to `UpdateRefused`:

- `insert_rule(rule)`, `delete_rule(node, tid, idx)`, `set_link(sport, dport, up)`;
- `take_affected()` → the checks, as `(source, probe)` pairs, that the updates
  since the last call could have changed — or "all" where an engine cannot say,
  which is sound and makes `precision` honest.

A modify is a delete followed by an insert.

### 6.3 Per engine

**NetPlumber — feasible and cheap.** Every flow carries its root source
(`node.h:51`), and every change to the flows at a probe passes through one of
three hooks — add, modify, delete — in `SourceProbeNode`
(`source_probe_node.cc:98`, `:136`, `:186`); they are where the retired
`update_check` sat. Recording `(flow->source, probe)` there, unconditionally,
gives a sound superset of the checks whose verdict can change, because a check's
verdict depends only on the flows at its probe from its source. That covers
in-place shrinking by `subtract_infuences`, influence handed back on deletion,
and flows that disappear and return. Exposed as `take_affected` over pybind and
RPC; with several worker instances, FaVe takes the union.
Also needed: a working single-rule delete (iterate the negation expansions
`n_idx = 0, 1, …` until a key is missing); the index-reuse defect fixed (§2);
LPM priorities that leave room for later routes (O1).

**VeriFlow-FR — feasible, moderate, mostly Python.** One FaVe rule can be
translated alone against the existing field layout and port map, with a running
rule id and an inverse map `(node, tid, idx) → [engine rule ids]` (ingress-port
expansion makes several). A rule that needs a new field, a new port, or breaks
a scan field forces a rebuild, which is counted, not hidden. First-match
priority is `-idx` and already leaves room; LPM needs
`plen·2^40 − idx`, which orders exactly like today's dense scheme.
**The affected-check criterion is a footprint**, not the affected ECs: "the
check's packet set does not meet any affected EC" is unsound under rewrites,
and every router and packet-filter pipeline rewrites `in_port`/`out_port`
metadata. Instead, each check's walk records the states it visited — (table,
arrival port, box), boxes after rewrites — and the edges it forwarded on. A rule
update at table T affects a check only if a recorded state at T has a
compatible arrival and a box that meets the rule's match; a link update only if
the walk forwarded on it. Deletions use the footprint from before the update.

**APKeep — open (O2).** BDD forwarding-only workloads: feasible, about 1.5–2.5
weeks (return the delta BDDs from `updateRule`, a fresh `Evaluator` writer per
batch, public `addLink`/`removeLink`, a per-rule line map with reference counts,
and a gate refusing anything outside plain dst-LPM). BDD on the full workloads
(ACLs, VLAN, the `wl_stanford` collapse, first-match tables, ingress demux) only
by redesign, about 4–6 weeks: much of the translation is decided over the whole
model at build time. **NDD-Flood, the production default, is the easiest**, about
1–2 weeks: each device's forwarding is computed from that device's rules alone,
so an update recomputes one device and invalidates the cached per-source
floods. Two engine traps either way: equal-priority ties are resolved
differently on insert and on remove (`Element.java:68` vs `:176`), so a tie must
be broken in the priority or refused; and APKeep's built-in loop check is part
of `updateRule` and so of `t_update` (D1).

**ad6 — rebuilds per update, recorded as a result.** As already planned
(`CLOUD_BENCH_PLAN.md` §2.1): its `t_update` is a full rebuild, `affected` is
"all".

### 6.4 FaVe's side

A verdict cache per check, keyed `(source, probe, condition)`; a selective
re-verification that re-asks only `affected` and replaces those entries; and
the oracle of §5. Checks on a probe or source added by the update are new and
always verified; checks on a removed one are dropped.

### 6.5 Workloads for M1

| workload | rules | checks | full re-check (VF-FR) | role |
|---|---:|---:|---:|---|
| `wl_example`, `wl_ifi` | 40, 240 | 10, 299 | ms | development; oracle at every update |
| `wl_cloud` | 1,749 | 71 | 0.27 s | rewrites (NAT); the external oracle workload |
| `wl_airtel1/2` | 42,016 | 256 | ~1.1 s | LPM-heavy, rewrite-free; sampled (O1) |
| `wl_up` | 7,973 | 18,811 | 393 s | where selective re-verification matters most; checkpoints only |
| `wl_stanford`, `wl_i2` | 14,396, 78,056 | 240, 72 | 150 s, 111 s | rewrites and LPM; sampled; after O1 |

`wl_tum` has no check set and can only measure `t_update`. `wl_berkeley` is a
size series; it joins once the rest works.

## 7. Streams, batches and statistics

- **S1** delete every rule of the model in reverse order, then insert them
  in order (APKeep's method — insert all, then delete in reverse — with the
  halves swapped because the build is the full model; the insert half doubles
  as a build curve from empty).
- **S2** delete a random k% of rules, then re-add them (NetPlumber's method;
  updates against a full network).
- **S3** take each link down, then up again, one at a time.

Every random choice comes from a **seed that is stamped** into the result.
Placement matters for selective re-verification — a default route or a core
link touches many checks, a host route few — so streams are reported with the
size of what each update affected, not only its time.

**Batching (D4) is a parameter.** Each stream runs at batch sizes 1, 10, 100, …
and the whole stream: updates are applied one by one, their affected sets
united, and one selective re-verification follows. The curve shows where
batching starts to pay for each engine. Batches are counted in updates; the
synthetic streams carry no time.

**Reported:** generated from the raw per-update records (§9, after O5), distributions, never means alone — median, p90, p99, maximum —
split by operation (insert, delete, link down, link up), with `affected` and
`precision` beside them; repetitions to be fixed by O4. Predictions are
declared in a `PROTOCOL.txt` before any run and never edited afterwards, as in
every campaign here.

**APKeep's footprint (owner, 2026-10-11).**
- **Main tables:** BDD-APKeep and NDD-APKeep run at their default footprint,
  witness + dead ends (`APKEEP_FOOTPRINTS.md`), stamped in every cell's
  `head.json`.
- **Ablation:** one table compares the four footprints -- coarse (`--footprint
  coarse`), witness, dead-ends, and both (the default). It covers the
  campaign's workloads and streams S1-S3, both APKeep engines where they
  build, at batch size 1, and reports re-checks summed, their change against
  coarse, and median and p90 `t_recheck` and `t_total`.
- **Purpose:** it shows what each mode contributes: witness covers the
  reachable checks and link updates; dead ends covers the unreachable checks.
- **Fallback:** if campaign time is short, the ablation runs on the dev
  workloads (`wl_example`, `wl_ifi`, `wl_airtel1`, `wl_cloud`) under the
  campaign's protocol, and the table says so.
- **Predictions:** declared with the campaign's, before the run.

## 8. Milestone 2 — the FaVe layer

The owner's three stability requirements, in dependency order, plus deletion:

1. **Modelling engines emit update-stable models**: within a margin of
   updates, the same rule keeps the same table index. For the packet filter
   that means keeping its internal spacing on output instead of renumbering, a
   gap scheme for inserted rules, and re-spacing as a declared, counted event
   when a gap runs out. In stateful chains a change to a state-checking rule
   legitimately moves block boundaries and rewrites a run of shell rules; how
   wide that run is gets measured. **First step: a feasibility spike** on the
   packet filter. The switch and router models and the workload generators
   are audited for the same property.
2. **The aggregator computes precise diffs cheaply**: per (device, table, idx)
   with a content hash per rule, bounded by the size of the device re-sent —
   not model-wide (an earlier model-wide diff was too costly). Plus the
   unfinished deletion path: `_sync_diff`'s removal half, `__sub__`,
   `remove_rule`, device `del`.
3. **Adapters leave unchanged rules alone.** NetPlumber's adapter already maps
   one FaVe rule to its engine rules (`_calc_rule_index`, 4,096 slots per rule
   for negation expansion); its stability is inherited from requirement 1.

Then **S4**: synthetic firewall edits — insert, delete or modify one rule at a
sampled position — on `wl_up`, `wl_tum`, `wl_ifi`, `wl_cloud`, measured end to
end from a configuration change to an updated verdict, which is TNSM'21's claim.

### 8.1 M2 design after the spike (2026-10-11, autonomous; choices DECIDED by the owner 2026-10-15)

The spike (`results_m2_spike_20261011/FINDINGS.md`) settled the mechanism;
this is how it is built. Choices marked *(choice)* were taken without the owner
and listed for confirmation; the owner's answers follow the list.

1. **`util/stable_index.py`, a `StableIndexer`.** Per (device, table) it holds
   the last emission `[(idx, content key)]` and emits a new rule list with
   stable indices: alignment by content (`difflib`, no autojunk), matched
   rules keep their index, a run of new rules spreads over its gap, and a run
   that does not fit relabels the smallest window around it to half the
   nominal spacing (the spike's R4c). The first emission spaces a table at
   `budget / (2(n+1))`. Relabels are counted, never hidden. The content key
   is (table, in-ports, match, actions); `raw_line_no`, which shifts with
   every inserted line, is metadata no engine reads.
2. **In the aggregator, opt-in** *(choice)*: `AggregatorService(...,
   stable_indices=True)`, off by default, so every from-zero path (V5's numbers) stays
   byte-identical. It applies to device models that
   arrive WHOLE (packet filter, host, ALG, router, switch-with-tables); switch
   rules arriving as control-plane commands keep the indices their sender
   chose.
3. **Index budget per engine and table** *(choice)*: `max_rule_index(table)`
   on the engine interface -- NetPlumber 2^20−1 (`_RULE_IDX_MAX`), APKeep
   69,999 in ACL and HSA stage tables (priority `70000 − idx`), VeriFlow-FR
   2^40−1 (LPM priority `plen·2^40 − idx`); ad6 only sorts by index. The
   indexer spaces within it. A table's rules are aligned in INDEX order,
   which is their priority -- not in list order, which differs in 138 of
   `wl_up`'s 1,134 tables (`ad6/translate.py:711`).
4. **The diff** (owner's requirement 2): per (device, table), the old and new
   emissions as `{idx: key}`; a rule whose index left, or whose key changed
   under the same index, is deleted; one whose index is new, or whose key
   changed, is inserted. Deletes go first (an engine must never see two rules
   at one index). Cost: one alignment per table of the device re-sent.
5. **Applied through the M1 engine calls** (`delete_rule`, `insert_rule`),
   which already take one FaVe rule each; the aggregator's commented-out
   deletion path stays as it is. A change the engines cannot take per rule --
   a whole-translated table (`pre_routing`, `post_routing`), ports, wiring, a
   table appearing or vanishing -- is refused (`UpdateRefused`) and counted;
   none of S4's edits makes one.
6. **The stored model** after an update is the new emission, so
   `model_rules`, reporting and the next diff all see the indices the engines
   hold (today `setdefault` keeps the FIRST model forever).
7. **S4** (`incremental_run.py --stream s4`): a seeded stream of one-line
   edits -- insert a copy of a rule line, delete one, modify one -- at a
   position sampled over every rule line of the workload's editable configs
   (`wl_up`: 136 packet filters; `wl_tum`: one; `wl_ifi`: the router's ACL
   lines; `wl_cloud`: its switch rule lists, re-sent as a switch with its
   table). Each edit regenerates the device through the same code the build
   used and goes through the aggregator. Recorded per edit: `t_model`
   (regenerate), `t_diff` (align + diff), `t_update` (engine), `t_recheck`,
   the engine-rule changes and relabels. `t_total` is the sum -- a
   configuration change to an updated verdict.

**Owner, 2026-10-15.**
- **The aligner in the aggregator, within each engine's limits (1 with 3).**
  Kept as built. *"If a workload requires more table entries than an engine
  can process, a clear refusal would be the most honest outcome."* Built:
  `_check_index_budget` refuses (`UpdateRefused`, naming the table, its rule
  count and the budget) a table with more rules than the engine has index
  slots, BEFORE the indexer or the engine is touched -- on a new device, a
  re-send and a replacement alike. ad6 declares its real bound (2^63 − 1: it
  only sorts by index) instead of inheriting NetPlumber's 2^20 − 1.
  **One numbering for every engine.** Spacing each table in its own engine's
  budget gave the same rule different indices on NetPlumber (2^20 − 1),
  VeriFlow-FR (2^40 − 1) and APKeep, so update streams -- built from the
  indices -- no longer hashed alike and cells stopped comparing across
  engines (the integration tier's cross-engine tests caught it). So the
  aggregator numbers every table in the tightest room any engine has for it
  (`common_index_budget`: 69,999 for router ACLs, APKeep's; 2^20 − 1
  elsewhere, NetPlumber's; pinned below every engine's limit by a test), and
  an engine's own limit decides only refusal -- and the room of a table that
  outgrows the common one, which then numbers differently there. A
  control-plane command into a table the aggregator numbered from a whole
  model is refused too: the sender's indices do not order against the
  indexer's. No grid workload does either: switches are created empty and
  commanded, and every table fits its budget. The one model that does is the
  snapshot packet filter, whose state tables start with a default rule at
  65535 and take `add_state` commands; only the retired
  `bench/legacy/wl_state_snapshots` uses it, and it now needs
  `--no-stable-indices`.
- **On by default (2).** *"I do not see the latest measurements ... as
  important as the longer term perspective. Hence, after remeasuring a few
  of the fast running cells, I would turn stable indices on as default."*
  `AggregatorService` and `InProcessFaVe` default to `stable_indices=True`;
  `--no-stable-indices` reproduces V5's generator indices, and the `backend:`
  stamp carries `stable_indices`, so a cell says which it ran. Re-measured
  (`bench/campaigns/results_stable_default_20261015/`): 21 fast V5 cells, each
  with and without; every pair has the same outcome, violation count and lines,
  none was refused, and wall time and peak RSS agree (two single-run memory
  differences were the sampler's: equal medians over 5 repetitions per arm).
- **Making the refusal clear in a from-zero build** needed one more piece: a
  build's messages carry no barrier, so a failed device was only logged.
  `InProcessFaVe.replay` now raises on one, and `cell_run.py` makes a verdict
  with a refused device invalid (TODO item 57).

### 8.2 Removing a device — DESIGN (2026-10-14); BUILT on every engine but NDD-Flood (2026-10-14/15); D-R6 BUILT on NetPlumber and ad6 (2026-10-15)

**Owner's framing (2026-10-14):** *"Adding and deleting whole devices should work
just like adding and removing rules or links. … In its simplest form, removing a
device would mean that all comprised tables (including contained rules), all
internal wiring, and all external links are removed through the regular update
mechanisms for these primitives. Since this might be quite costly due to
reverification, one would want to remove everything in one go and reverify
afterwards."* This section turns that into a design. It was prompted by TODO
item 53, where fast tests pinned the three broken adapter methods, and it
extends §8.1 rather than replacing it: §8.1's diff takes rule changes; this
section adds what §8.1 refuses.

**What is there today, read 2026-10-14.**
- **A re-sent device, with stable indices** (§8.1, opt-in
  `stable_indices=True`): `_sync_stable` diffs per (device, table) and applies
  the difference through `delete_rule`/`insert_rule`, deletes first. A table
  appearing or vanishing, other ports or wiring, and a changed whole-translated
  table are refused (`UpdateRefused`). **Without** stable indices, `_sync_diff`
  still sends only the ADDED part; its removal half stays commented out
  (`# TODO: fix deletion...`), as §8.1 item 5 decided.
- **A device `del`** is refused by name (`NotImplementedError`, item 53). Before
  that, a non-link topology delete carried no model and raised
  `AttributeError`. Generator and probe deletes reach the engine.
- **A switch rule removed with `switch.py -d`/`-u`** is refused by name too
  (item 53). It used to land in the switch's `_deletes`, which nothing reads.
- **The NetPlumber adapter's `delete_rules`, `delete_tables` and `delete_wiring`
  are broken and reachable only from the uncalled `_delete_model`.**
  `delete_rules` indexes a `Rule` as a tuple and passes a table name as an
  index. `delete_tables` only ever removes index 0, and indices start at 1.
  `delete_wiring` guesses a port's table by stripping a dotted suffix. All
  three are pinned as `*_KNOWN_DEFECT` in `test_netplumber_adapter_more.py`.
- **Only NetPlumber has every primitive.** NetPlumber's `remove_table`
  frees every rule in the table (`net_plumber.cc` `free_table_memory`), and
  `remove_rule` and `remove_link` propagate. Per adapter (`fave/*/adapter.py`,
  APKeep and ad6 corrected 2026-10-14):

  | engine | rule delete | link remove | table/element remove | selective re-check |
  |---|---|---|---|---|
  | NetPlumber | `delete_rule` | `remove_link` | engine `remove_table`; the adapter's `delete_tables` is broken | `track_affected`/`take_affected` |
  | BDD-APKeep, NDD-APKeep | `delete_rule` | none: the adapter's `remove_link` raises `UpdateRefused`, since the model is built from the recorded topology; `set_link(up=False)` takes a link down | none: `Network.java` removes rules (`removeOneRule`), never an element or a topology edge | yes |
  | VeriFlow-FR | `delete_rule` | none in the adapter (the engine's `remove_link` is untested, §2); `set_link(up=False)` takes a link down | n/a: tables are per-switch rule sets | yes |
  | NDD-Flood | none: a from-zero build, refused by name | — | — | — |
  | ad6 | none (the contract's default refuses) | none: `remove_link` raises `UpdateRefused` | none; but every check rebuilds from the capture buffers `_tables` and `_raw_edges` (a whole device is removed there since 2026-10-14) | n/a |

**Design.**
- **D-R1. Removing a device is §8.1's diff against an empty model.** Every
  rule of every table goes through `delete_rule`, as §8.1 item 4 already does
  for a rule that left. What §8.1 refuses is added here as primitives of
  their own: a table vanishing, wiring removed, ports removed, and the links
  into and out of the device. Removal does not need stable indices: everything
  goes, so no index has to survive. The stored model and the indexer's last
  emission for the device are dropped with it, so a later `add` of the same
  name starts from zero.
- **D-R2. Order removals to make them cheap.**
  1. The links INTO the device. In NetPlumber, a device's flows are then
     retracted once, at its entry, and everything after has no flows left to
     retract downstream.
  2. Its rules, then its internal wiring.
  3. Its tables.
  4. The links OUT of it, then its ports from `port_to_model`.

  In NetPlumber, step 3's `remove_table` frees the table's rules itself, so
  step 2's rule deletes may be skippable there; whether that is cheaper than
  per-rule deletes is measured, not assumed.
- **D-R3. One re-verification at the end.** The whole removal runs inside one
  `track_affected(True)` window: every primitive applied, then one
  `take_affected()` and a selective re-check of the affected checks (M1's
  mechanism, §6.2). **Caveat for NetPlumber:** it propagates flow changes on
  every primitive, so batching saves the CHECKS, not the propagation. D-R2's
  ordering is the lever there.
- **D-R4. A missing primitive is refused by name, never skipped.** Where an
  engine lacks a primitive — APKeep and VeriFlow-FR have no `remove_link`,
  NDD-Flood has none — the aggregator raises an `UpdateRefused` naming the
  engine and the primitive, before anything is touched, as §8.1 item 5 does.
  A from-zero engine may instead declare that it rebuilds; that is a declared
  accommodation (`ACCOMMODATIONS.md`), not a silent fallback.
- **D-R5. The three broken adapter methods go.** `delete_rules`,
  `delete_tables` and `delete_wiring` are replaced by the composed path, and
  their `*_KNOWN_DEFECT` tests become tests of it.
- **D-R6. The same primitives lift §8.1's refusals, later** (built
  2026-10-15 as a replacement, below). Once a table, its
  wiring and its ports can be removed (and added) one at a time, a re-sent
  device whose tables, ports or wiring changed can be diffed instead of
  refused. That is a follow-up, not part of this section's first build.

**Correctness: the oracle we already have.** `util/incremental.py`'s from-zero
oracle generalises directly. On every engine that has the primitives, removing
a device and re-checking the affected checks must give the verdicts that a
build from zero WITHOUT that device gives. Check by check, as M1's and M2's
tests already do. That also exercises `remove_link` on VeriFlow-FR's engine,
which §2 lists as untested.

**Owner questions — all answered 2026-10-14.**
- **Q-R1. Scope.** Whole-device removal first, and D-R6 (lifting §8.1's
  refusals for tables, ports and wiring in a re-send) after? Or both in one
  piece of work? *Recommendation: device removal first. It is self-contained,
  replaces the refused `del`, and its oracle is cheap; D-R6 reuses its
  primitives.* **Owner, 2026-10-14: device removal first; D-R6 after.**
- **Q-R2. Which engines.** Only NetPlumber has every primitive. APKeep
  (both) and VeriFlow-FR can delete rules but cannot remove a link, and
  APKeep cannot remove an element. They could instead EMPTY the device: every
  rule deleted, the elements and links left. An emptied APKeep element drops
  everything (an ACL keeps its default deny, `ACLElement.java`; a forward
  element sends to its `default` port), so for reachability it should equal
  an absent device, except for a check that starts or ends at its ports; the
  oracle decides. It would be a declared accommodation, and re-adding the same
  name needs the leftover elements reused. *Recommendation: NetPlumber first,
  as the full design. Then APKeep and VeriFlow-FR by emptying, declared and
  held to the oracle, rather than building link and element removal into
  their engines now.* **Owner, 2026-10-14: NetPlumber first; then APKeep and
  VeriFlow-FR by emptying, declared and held to the oracle.** Found after the
  answer: both implement `set_link(up=False)`, so emptying also takes the
  device's links down, in D-R2's order, rather than leaving them up.
- **Q-R3. From-zero engines** (NDD-Flood, ad6). Both refuse today. ad6
  rebuilds its model for every check from its capture buffers (`_tables`,
  `_raw_edges`), so removing a device there means dropping it from those
  buffers: a real removal, not an accommodation, and small. NDD-Flood builds
  once from zero, so removal there means a full rebuild. *Recommendation: ad6
  removes from its buffers, held to the same oracle; NDD-Flood keeps refusing
  by name.* **Owner, 2026-10-14: ad6 removes from its buffers; NDD-Flood
  refuses.**
- **Q-R4. Generators and probes.** They are removed today on their own
  (`delete_generator`/`delete_probe`, fixed in item 53; VeriFlow-FR inherits
  the contract's `NotImplementedError` for both). When a removed device
  was a probe's or a generator's only neighbour, does the check stay
  (vacuously failing or passing), or does the client have to retract it?
  *Recommendation: the check stays and is re-verified, and its new verdict is
  reported, not dropped. Flagging it as vacuous needs a report field that does
  not exist yet; item 52's marking is the natural place for one.* **Owner,
  2026-10-14: the check stays, is re-verified and its verdict reported; a
  vacuous marking is left to item 52.**

**Built on NetPlumber (2026-10-14).** "What is there today" above is the state
before this build.
- **The path.** `topology.py -d -n <device> -t <type>` reaches
  `AggregatorService._remove_device`. It refuses a device it does not hold, or
  one of another type, with a `ValueError`. It then hands the engine the
  stored model and its external links as one `remove_device(model, links)`, a
  new contract method that every engine but NetPlumber refuses by name
  (`UpdateRefused`, D-R4). Only after the engine returns does the aggregator
  forget the links, the ports, the stored model, the indexer's last emission
  (`StableIndexer.forget`), the commanded tables and the declared-LPM index
  (D-R1). A refusal leaves all of it as it was.
- **NetPlumber's `remove_device`** removes, in D-R2's order, the links into the
  device, its internal wiring, its tables and the links out of it. Then it
  forgets the device's ports, table indices, rule ids and links. It replaces
  `delete_rules`, `delete_wiring` and `delete_tables` (D-R5), and their
  `*_KNOWN_DEFECT` tests became tests of it.
- **D-R2, measured** on wl_up, removing its largest device, the packet filter
  `pgf` (2,201 rules):

  | order | time |
  |---|---|
  | links in first (built) | 1.0 s |
  | tables first | 4.3 s |
  | links in first, then each rule deleted before `remove_table` | 1.05 s |

  So the ordering is the lever, as D-R2 predicted. Per-rule deletes buy
  nothing: they end in the same rule destructor, and `delete_rule` refuses
  pre-/post-routing tables anyway. Removing the device does not delete
  rules one at a time. Removing all 86 of wl_cloud's switches one after
  another took 0.04 s in every order. Indicative, one run each.
- **D-R3** needs no code: the removal is ONE aggregator message, and the
  caller takes the affected set once after it.
- **The oracle** (`test/test_incremental_device_removal.py`, integration
  tier; the helper is `test/incremental_oracle.py` `remove_each`). Each device
  of a workload is removed. Then three things must hold:
  - the selective re-check equals a full one;
  - the full verdicts equal a from-zero build of the workload's inputs
    without the device (its entry, routes and links dropped);
  - re-adding the device, as `replay` adds it, brings every verdict back.

  Verdicts cannot see leaked engine state: with its links cut, a device whose
  tables stay answers like an absent one. So NetPlumber's own dump
  (`dump_plumbing_network`) and the adapter's bookkeeping must also hold
  nothing of the device.

  | workload | devices removed | verdict changes |
  |---|---|---|
  | wl_example | 2 of 3 (`pgf` is every port its probe's test path names) | 10 |
  | wl_ifi | 17 of 17 | 222 |
  | wl_cloud | 86 of 86 | 242 |
  | a tiny two-switch workload | 2 of 2 | 3 |

  Four mutations were run against it, each caught: an engine removal that
  does nothing, tables kept, links in kept, and an empty affected set. Kept
  tables and kept links in were caught only by the residue check.
- **Probe test paths.** The from-zero copy drops the device's ports from probe
  test paths, since the aggregator resolves a path at build. NetPlumber never
  reads one: the legacy probe condition is compiled out. In the incremental
  engine, the probe keeps its path; per Q-R4 its check stays and is
  re-verified.

**Built on VeriFlow-FR, BDD-APKeep and NDD-APKeep by emptying (2026-10-14).**
Q-R2's accommodation, declared in `ACCOMMODATIONS.md`.
- **VeriFlow-FR** (`VeriFlowAdapter.remove_device`): in D-R2's order, it takes
  the links into the device down, deletes every rule the device holds, then
  takes the links out of it down. It uses `set_link` and `delete_rule`, so
  their footprints decide what is affected. The device's tables, ports and
  internal wiring stay.
- **APKeep** (`APKeepAdapter.remove_device`): every rule batch of the device is
  translated with its tables empty, and the engine is brought to that
  translation as for any other update (`_apply_translation`). Its elements
  stay, **and so do its links**. That departs from the refinement recorded
  under Q-R2, and follows the owner's answer instead.
  - The reason, measured on wl_example: APKeep's translation decides element
    structure from the topology. With `dmz`'s and then `office`'s links
    down, `pgf` had one ingress left, and the translation stopped splitting
    it per ingress (`pgf.fwd`, `pgf.fwd.in1` became `pgf`). APKeep cannot
    create that element, so the removal was refused (`structural`).
  - With the links left up, nothing changes structure. An emptied element
    drops everything, which the oracle confirms.
- **The name cannot be added again** on either engine. VeriFlow-FR refuses
  `add_tables` for an emptied device; APKeep refuses every add after the
  build. Both refuse by name (`UpdateRefused`). Re-adding would mean
  reusing the leftover tables or elements, as Q-R2 noted. Not built.
- **The oracle** (same module, `remove_each(readd=False)`): the removals
  ACCUMULATE. Each is compared with a from-zero build without every device
  removed so far. The residue check asks for rules left on the device, and
  on VeriFlow-FR also for links or generator starts into it.

  | engine | tiny | wl_example | wl_ifi | wl_cloud |
  |---|---|---|---|---|
  | VeriFlow-FR | 2 of 2 | 2 of 3 | 15 of 17 | 86 of 86 |
  | BDD-APKeep | 2 of 2 | 2 of 3 | 15 of 17 | not run (a 3.24 h build, ×86) |
  | NDD-APKeep | 2 of 2 | 2 of 3 | 15 of 17 | 86 of 86, ~2 min |

  - No removal was refused.
  - The skipped devices are those whose removal, after the earlier ones,
    would leave a probe's test path empty.
  - Mutations caught: on VeriFlow-FR, a no-op, links kept, rules kept and
    an empty affected set; on APKeep, a no-op, only the first table of each
    batch emptied, and an empty affected set.
  - APKeep's residue check reads the adapter's record of what the engine
    holds (`_live`), not the JVM.
**Built on ad6 from its buffers (2026-10-14/15).** Q-R3: a real removal, not an
accommodation.
- **`Ad6Adapter.remove_device`** drops the device's tables, their declared
  semantics, its wiring and its external links from the capture buffers that
  every check rebuilds the model from. A link the buffers do not hold is
  refused before anything is dropped. The name can be added again, and its
  first batch is accepted as on a fresh adapter.
- **No selective re-check:** ad6 reports no affected set, so every check is
  re-verified (the contract's `None`).
- **The oracle** (same module, `remove_each`, with re-adding as on
  NetPlumber). The residue check asks the buffers for the device's tables,
  semantics, wiring and any link at its ports.

  | workload | devices removed | verdict changes | time |
  |---|---|---|---|
  | wl_example | 2 of 3 (`pgf`, as on NetPlumber) | 10, as on NetPlumber | 6 s |
  | wl_ifi | 17 of 17 | 222, as on NetPlumber | 345 s |
  | wl_cloud | 3 of 86, a sample (`core.dc0_core`, `lin.dc0_leaf0`, `gw.internet`) | 21 | 2,408 s |
  | a tiny two-switch workload | 2 of 2 | 3, as on NetPlumber | 1 s |

  Every check rebuilds the model, five per removal, so the module runs
  wl_ifi as a sample (the router and two switches, ~1 min) and wl_cloud not
  at all. The full runs above were one-off, 2026-10-15, one run each.
- **A translator bug it found.** wl_ifi without its router failed: the
  router's rewrite was the only one of `vlan`, so the sources' `vlan`
  constraint stayed a match on the generator's own rule, and the declared
  field widths were collected from device rules only. ad6 refused the
  undeclared `<fieldmatch>`. Fixed: generator rules count too
  (`Ad6Adapter._build_literal`, a unit test in `test_ad6_adapter_unit.py`).

  Mutations caught on tiny and wl_example: a no-op, links kept, links in
  kept, and tables kept. Each was caught by the residue check and, without
  it, by the verdicts alone, or loudly: with a removed device's links kept,
  ad6's translator refuses a port that belongs to no device.
- **Not built here:** a switch rule delete (`switch.py -d`/`-u`) is still
  refused by name; it is not a device removal. NDD-Flood refuses
  (`_require_updatable`).

**D-R6 — owner questions, answered 2026-10-15.** What §8.1 refuses in a
re-send with stable indices is a table appearing or vanishing, other ports or
wiring, and a change to a whole-translated table (`pre_routing`,
`post_routing`). On the workloads that means a device gaining or losing an
interface, or its address changing; no S4 edit makes one (D11 refused none).
- **Q-R5. Mechanism.** Replace the device — §8.2's removal, then the new
  model added as a new device and its links added again, one update — or
  diff per table, leaving unchanged tables in the engine? *Recommendation:
  replace; it reuses what is built, and its cost is measured.* **Owner:
  replace the device.**
- **Q-R6. A link at a dropped port.** *Recommendation: refused by name; the
  topology owns links, so the client deletes the link first.* **Owner:
  refused by name.**
- **Q-R7. Engines that only empty** (VeriFlow-FR, APKeep) cannot add an
  emptied name again, so cannot replace. *Recommendation: keep refusing
  there.* **Owner: keep refusing.**

**D-R6 built on NetPlumber and ad6 (2026-10-15).**
- **The path.** `AggregatorService._sync_stable` names the structural change
  and hands it to `_replace_device`. That refuses, before anything is
  touched, a link at a port the re-send drops (naming it), an engine whose
  `REMOVES_DEVICES` is false (a new contract attribute: true on NetPlumber and
  ad6, false on the emptying engines and by default), and an invalid
  declared-LPM table. Then: `_remove_device` (§8.2), the new model spaced and
  added as a new device, its links added again through the same bookkeeping
  as a topology `add` (`_record_link`). A table the control plane filled
  (a packet filter's routing table) arrives empty in a configuration
  re-send; it keeps its rules at the sender's indices and stays commanded,
  as in a diff. `update_stats` carries `replaced` with the reason.
- **The oracle** (`test/test_incremental_device_replacement.py`,
  `incremental_oracle.replace_each`). Each device is re-sent with one
  unlinked port more, then as it was; both are replacements. After each:
  selective equals full re-verification, and full equals a from-zero build of
  the inputs with the entry as sent. At the end every verdict is back.
  Verdicts cannot see an old device left beside the new one, so on NetPlumber
  the engine's own dump must also hold no table the adapter does not know and
  no link twice.

  | engine | tiny | wl_example | wl_ifi | wl_cloud |
  |---|---|---|---|---|
  | NetPlumber | 2 of 2 | 3 of 3 | 17 of 17 (1.5 s) | 86 of 86 (28 s) |
  | ad6 | 2 of 2 | 3 of 3 | a sample: `ifi`, `external.ifi` (54 s) | not run |

  VeriFlow-FR refuses, naming the engine, with the stored model unchanged.
  Mutations caught: links not added again, and the commanded routing table
  dropped, by the verdicts; the old device never removed, by the dump check
  only.
- **Cost, measured** on wl_up's `pgf` (2,201 rules, 50 links), NetPlumber,
  one run each: a replacement takes 4.5 s; building all of wl_up from zero
  takes 4.7 s; an unchanged re-send 0.25 s. Replacing re-propagates every rule
  of the device, so a structural change to a large device costs about a
  build. Q-R5's alternative, a per-table diff, is the lever if that matters.
- **Found on the way:** pytest collects every `TestCase` whatever its name, so
  `test_incremental_device_removal.py`'s `_Emptying` base ran VeriFlow-FR's
  tests a second time, ungated. Bases are now `__test__ = False`.


## 9. Open questions (recommendations, not decisions)

- **O1. LPM priorities that leave room — DECIDED 2026-10-09.** NetPlumber's
  rule index is 32 bits and the `<<12` negation slots are an adapter-only
  convention (`_calc_rule_index`); the engine ranks by the whole index
  (`net_plumber.cc:381–411`). LPM routes need no negation, so a declared-LPM
  table uses the **full 32-bit index, banded by prefix length**; a new route
  takes any free slot in its band (equal-length prefixes are disjoint, so order
  within a band never matters). The validator must refuse a negated destination
  so that premise is enforced. VeriFlow-FR the same. No 64-bit widening. Latent
  bug found on the way: `_RULE_IDX_MAX` is `2^24−1` but must be `2^20−1`.
  *Built 2026-10-10:* within a band a route takes the slot of its own model
  index rather than "any free slot" — every slot is then a function of the
  rule alone, build and update agree by construction, and ties keep the order
  the old dense scheme gave them. A band holds ~33M slots; what binds first is
  the model index itself (≤ `_RULE_IDX_MAX`, part of the adapter's local key).
  *Checked on `wl_berkeley` (2026-10-10)*, the largest tables in the suite:
  4,476,240 routes in 23 declared-LPM tables, every one a destination prefix
  with **no negation** (the switch route format cannot express one,
  `devices/switch.py` `fieldify`), at most 195,357 per table and model index
  ≤ 195,357 — within `_RULE_IDX_MAX` (2^20−1) and a band (~33M). (A first
  attempt replayed the workload into NetPlumber and hit its 6 h timeout before
  printing; counted from `routes.json` instead, 7 s.)
- **O2. APKeep scope — DECIDED 2026-10-09.** NDD-APKeep is the NDD paper's
  system (APKeep's core, atom layer replaced by NDD); BDD-APKeep and NDD-APKeep
  work alike, incrementally. FaVe's `NddReachabilityEngine` is not that system
  and stays as a differential oracle ("NDD-Flood"). Scoped in
  [`APKEEP_INCREMENTAL_SCOPE.md`](APKEEP_INCREMENTAL_SCOPE.md), whose §6 holds the
  questions still open. **Design decided 2026-10-10 (option B):** one core --
  the fork's elements, made independent of the packet-set type -- over two
  atom layers, the NDD one ported from the reference; differential against the
  reference on one benchmark; provenance stated per part. Built: scope §8.
- **O3. Oracle cost — DECIDED 2026-10-09.** Half (a) after every update costs a
  full check per update: ~5 h on `wl_airtel1`, ~15 days on `wl_up`, ~40 days on
  `wl_i2` (VeriFlow-FR, S2 at 20%). So:
  1. **Timed runs carry no oracle.** `precision` is computed from the selective
     re-check itself (verdicts that changed among those re-checked), which is the
     true count whenever the selective re-check is sound. The full check between
     updates (today's `--precision`) also warmed engine caches inside the timing.
  2. **Every measured stream is checked across engines:** each update's set of
     changed checks (distinct checks, not lines) must agree across every engine
     that ran the stream incrementally. A disagreement is a defect and voids the
     stream's selective numbers until explained.
  3. **One untimed oracle run per measured cell**, same seeded stream, same
     engine build: half (a) after every update on a seeded random sample of k
     checks; full (a) and (b) every N updates and at the end. **Budget: the
     cell's own limit**; k and N declared in the protocol. Checkpoints alone can
     be masked — a missed change undone by a later update (S2 re-adds) leaves
     a correct cache by the checkpoint — so the result is stated as a sample.
  4. Tests keep both halves after every update on the small workloads.
- **O4. Repetitions and limits — DECIDED 2026-10-09.** *Scope (owner, same
  day):* measurements on this branch are **indicative**, stamped
  `limit_class=dev`, one repetition, and capped by **the machine** (64 GB, no
  swap) rather than V5's 32 GB, which was a portability rule for reportable
  cells. The complete campaign, repetitions included, is run separately; the
  settings below are for it, and the harness carries them as parameters.
  1. **Per-stream (cell) limit = V5's class:** 24 h wall, 32 GB RSS, stamped per
     cell; the O3 oracle run has the same budget.
  2. **A stream stopped by a limit reports its completed prefix** ("n of N"),
     quantiles over the prefix, stamped did-not-finish at update n, never
     extrapolated. Prefixes are order-biased (a stopped S1 has only deleted).
  3. **Per-update limit 1 h** (update + re-check), a hang guard that ends the
     stream as in 2. Reported beside it: the **break-even share**, the updates
     whose `t_total` exceeds the same engine's V5 from-zero build + full check on
     that workload.
  4. **Ten repetitions per seed** (owner), the count stamped; per-repetition
     quantiles and their spread reported, never a pooled mean; the first 100
     updates reported separately so warm-up shows. Seed variance (S2's choice
     of rules) on `wl_ifi` and `wl_airtel1` only, three seeds each.
  5. **A reduced grid:** batch 1 everywhere; batches 10, 100 and the whole stream
     on S2 only. A dev-stamped **calibration** (the first ~200 updates of each
     stream) precedes the protocol, so its grid and predictions rest on data.
  RSS is recorded after every batch, so a reference-count leak shows as growth.
- **O5. Precision and selectivity — DECIDED 2026-10-09.** Two ratios, from the
  timed run itself (O3): **selectivity** = checks re-checked / all checks (the work
  saved against a full re-check) and **precision** = checks whose verdict changed /
  checks re-checked (how much of the re-check was needed). Aggregated as the
  ratio of the stream's sums, with the per-update distribution of re-checked
  counts beside it (the ratio is dominated by large updates). The unit is the
  check, not the (source, probe) pair; a changed witness under an unchanged
  verdict is not a change. **Void, not caveated,** when the stream fails its
  cross-engine comparison or its oracle run. Reported beside `t_total` in every
  row, not as a separate headline.
- **Raw data is kept (owner, 2026-10-09).** Every statistic here is derived, so a
  different one can be computed later without a re-run. A cell keeps, per update
  and gzip'd JSON lines: its position, op and the rule key or link; its batch;
  `t_update`, `t_recheck`; the affected (source, probe) pairs as the engine
  reported them; the changed checks with old and new verdict; RSS after the
  batch; a monotonic timestamp. Plus the stream itself, the initial verdicts and
  the stamps. Re-checked checks follow from the affected pairs and the stamped
  check set, so they are not stored twice. Quantiles, ratios and tables are
  generated from these files, never typed and never the only record.
- **O6. Ties and identity in APKeep — DECIDED 2026-10-09.**
  * A FaVe rule's group of APKeep rules (one per out-port, per ingress class…) is
    inserted and deleted as ONE update with one re-check after it; within a
    group, ties need no breaking — APKeep resolves equal priority as "last
    inserted wins" (`Element.java:73–91`), which leaves only the intermediate
    state of a group delete wrong, and FaVe never observes it. Emission order
    within a group must be deterministic.
  * Ties ACROSS FaVe rules are broken where matches can overlap: today NAT,
    where every rewrite rule sits at 65535 (`NATElement.java:125`).
  * Each APKeep rule string carries a reference count (the adapter merges
    identical strings, `_dedup`); it is removed only with its last FaVe owner.
  * NAT rule identity is fixed in the fork (`Rule.equals` = priority + port,
    `NATElement.rule_map` keyed by port).
  * The APKeep adapter refuses multi-port rules: FaVe means "to all ports"
    (NetPlumber does that), APKeep would keep only the last. None exist in the
    six workloads counted (`wl_stanford`, `wl_i2`, `wl_berkeley` not counted).
  * **Tables are first-match unless DECLARED LPM** (owner): FaVe's contract,
    held by NetPlumber and VeriFlow-FR, and since 2026-10-09 by the APKeep
    adapter's plain forwarding tables too (`TABLE_SEMANTICS_PLAN.md` §6.3). A
    last-match source is converted by its producer. The HSA stage tables are
    still claimed by device prefix.

## 10. Order of work

**Progress (2026-10-09, branch `updates`):**

| step | state | commits |
|---|---|---|
| 1. replay seam, S1–S3, seeds | **done** — simpler than §6.1: `InProcessFaVe` builds each engine through the aggregator; the rules come from its stored models (`util/incremental.py`) | `bff573f7` |
| 2. NetPlumber | **done** — `take_affected` at the three probe hooks; adapter `insert_rule`/`delete_rule`/`set_link`; LPM tables take a rule back into its own slot only (O1) | `1ad4fe9a`, `240aa881`, `bff573f7` |
| 3. FaVe side | **done** — `VerdictCache`, selective re-verification, the from-zero oracle (a fresh engine behind a wrapper that withholds deleted rules and downed links) | `bff573f7` |
| 4. VeriFlow-FR | **done** — per-rule translation, walk footprints, LPM as on NetPlumber | `518e75cb`, `0430d036` |
| 5a. NetPlumber and VeriFlow-FR LPM (O1) | **done** — 32-bit bands (NetPlumber `_lpm_index`, VeriFlow-FR `plen·2^40 − idx`), a late route lands where a build puts it; the validator refuses a negated destination; `_RULE_IDX_MAX` = 2^20−1. Tested by moving every declared route of `wl_stanford` to an index the build never saw: verdicts unchanged, and an insert path that forgets the band fails it on both engines | this branch |
| 5b. BDD-APKeep | **done** — `APKEEP_INCREMENTAL_SCOPE.md` §7: a shadow re-translation per update (per rule for plain FIBs), its difference applied through `updateRule`/`setLink`; footprints in the fork; element structure fixed at build, updates that would change it refused and counted (2 of 50 on `wl_example` S1, none elsewhere). Held to the oracle on `wl_example`, `wl_ifi`, `wl_airtel1` (sample); agrees with NetPlumber update by update on `wl_ifi`. Not on `wl_cloud` (a 3.24 h build) | this branch |
| 5c. NDD-APKeep | **done** — owner decision B: the fork's elements over NDD's per-field atoms (`APKEEP_INCREMENTAL_SCOPE.md` §8). From zero, check by check, equal to NDD-Flood on all eight workloads with checks (and to BDD-APKeep where that finishes), including faithful `wl_stanford`/`wl_i2` and `wl_cloud`; per port equal to the authors' reference on `wl_airtel1`; every BDD-APKeep stream held to the oracle on NDD-APKeep too, plus `wl_cloud`. Found: an NDD library atomization bug (fields sharing label variables) and unbounded dead molecules | this branch |
| 5d. Finer footprints | **done; the default since 2026-10-11** (owner; coarse selectable, ablation in §7; paper account `APKEEP_FOOTPRINTS.md`) — `witness` (a reachable check watches only its witness path, one packet per hop after the last rewrite) and `dead-ends` (an unreachable check ignores moves into a dead end), `APKEEP_INCREMENTAL_SCOPE.md` §9; held to the oracle on every stream with the modes on, both engines. Indicative: with both, `wl_cloud` S1 re-checks 5,330 → 10, `wl_airtel1` S1 → 0, verdicts unchanged ([findings](../fave/bench/campaigns/results_inc_dev_footprints_20261010/FINDINGS.md)). Port order left as is and F not adopted, both documented (`APKEEP_INCREMENTAL_SCOPE.md` §9) | this branch |
| 6. harness | **done but the protocol** — raw per-batch records (`incremental_run.py`), a cell under stamped wall/RSS/per-update limits with repetitions (`incremental_cell.py`, the per-update limit as a stall guard in `cell_run.run_cell`), statistics only from the records (`incremental_report.py`), the cross-engine check (`incremental_compare.py`), the oracle run (`--oracle-sample k --oracle-every N`) | `5a518599`, this branch |
| 7. M2 spike (§8 step 1) | **done 2026-10-11** ([findings](../fave/bench/campaigns/results_m2_spike_20261011/FINDINGS.md)) — stable indices need the last emission: a ruleset alone cannot say which rule "was" where. **Stable renumbering by alignment** (per table: align by content, matched rules keep their index, new runs take free indices, a full gap relabels the smallest window to half the nominal spacing) holds one firewall edit at or near the floor: 500 random edits on `wl_up` pgf all at the floor (2 engine rules, against a dense median of 2,521); 200 head-of-chain inserts 4,528 changes against 304,538. **Design taken (autonomous, for the owner to confirm):** the aligner lives in the AGGREGATOR, which already holds every device's model, so generators and router/switch models stay unchanged; it is OPT-IN on the incremental path (from-zero runs and V5's numbers untouched); its index budget is declared per engine (NetPlumber 2^20−1, APKeep ACL < 70,000). Found: an `ESTABLISHED -j DROP` rule crashed the generator (fixed, `3202461d`) | `dca21368`..`17e1b123` |
| 5e. VeriFlow-FR footprints (D12) | **done 2026-10-11** (`VERIFLOW_FOOTPRINT_SCOPE.md`, all proposed parts) — witness with one concrete packet per hop carried back through the rewrites, dead ends with a fall-through fate for deletions, per-(source, probe) reporting; `--footprint` as on APKeep, **both modes the default since 2026-10-15 (owner), coarse the ablation row**. Every VeriFlow-FR oracle stream with the modes on; negative controls caught (an unpinned carried packet only by its unit test, not by the oracle streams). Indicative ([findings](../fave/bench/campaigns/results_inc_dev_vf_footprints_20261011/FINDINGS.md)): verdicts unchanged everywhere; with both modes `wl_airtel1` S1 51,200 → 0 re-checks and 607 → 0.92 ms per update, `wl_cloud` S1 13,210 → 10 | `647a97f3`, `32b869d9` |
| 8. M2 built (§8.1) | **done 2026-10-11** — `util/stable_index.py`; the aggregator's opt-in stable path (re-sent device → `delete_rule`/`insert_rule` of what changed, refusals before anything is touched, control-plane tables kept or seeded); `max_rule_index(table)` per engine; `InProcessFaVe.resend_device`/`resend_switch`; S4 (`util/incremental.S4Configs`, `stream_s4`; `incremental_run.py --stream s4` with `t_model`/`t_diff`/`t_update`/`t_recheck`). Under the oracle on all four engines: `wl_example`, `wl_ifi` (router ACLs), `wl_up` (packet filters), `wl_cloud` (switch tables; NetPlumber, VeriFlow-FR, NDD-APKeep), `wl_tum` edits go through rule by rule. Found on the way: a pf's routing table is filled by the control plane and arrives EMPTY in a configuration re-send -- kept, not deleted. The old aggregator deletion path (device `del`, a switch's `remove_rule` command) is untouched and still unfinished | `12ff85dc`..`e96f6b89` |
| 9. D11 run | **done 2026-10-13** ([findings](../fave/bench/campaigns/results_inc_dev_d11_20261012/FINDINGS.md), [A-cell table](../fave/bench/campaigns/results_inc_dev_d11_20261012/tables.md)) — 433 cells in 38.9 h, each capped at 2 h; 291 measured, 131 did not finish (103 cap, 28 memory), 8 error, 3 refused, **no oracle mismatch**. Found: S4 could delete all of an applied router ACL (the 8 errors, `wl_ifi`; harness fixed for the campaign, owner, `m2`); on `wl_tum` (no checks) VeriFlow-FR and both APKeeps never build their model, so their cells measure nothing; memory sized from 50-update prefixes is too tight for whole streams. Open before the campaign protocol: prefixes or caps for the slow cells, the `wl_tum` build, memory from D11's peaks | `71934eb4` |

Held to the oracle in `test_incremental_{netplumber,veriflow}.py` on
`wl_example`, `wl_ifi` and `wl_cloud`: after every update, selective equals full
re-verification; at checkpoints, full equals from-zero. Both engines see the same
verdict changes on every stream. Disabling one probe hook (NetPlumber) or the
footprint states (VeriFlow-FR) fails every stream test.

**Indicative calibration (2026-10-10, dev):**
[`results_inc_dev_20261010/FINDINGS.md`](../fave/bench/campaigns/results_inc_dev_20261010/FINDINGS.md)
— three engines × `wl_example`/`wl_ifi`/`wl_airtel1` × S1–S3, 200 updates each,
protocol first. All six oracle runs pass; 7 of 9 streams agree across engines on
every update. The other two exposed a **model defect updates reach**: `-o` in
`pgf`'s FORWARD chain, which the routing table's consistency rules failed to
tie to the routed egress (the shipped model masks it). **Decided and fixed
2026-10-10 (owner, A1): `-o` means netfilter's routed egress**
(`docs/ACCOMMODATIONS.md`, "Retired — `-o`", correction); both streams now agree
across engines, and no shipped verdict changed.

**Found on the way, fixed:** a NetPlumber flow created by re-propagation left
`processed_hs` uninitialised, and a later deletion crashed on it
(`0b7f9b32`; `wl_cloud`, the 130th deletion of S2). No V5 cell deleted anything.
NetPlumber's makefile tracks no header dependencies: `make clean` after a header
change, or the binary is inconsistent.

**First observation for O5 (development runs, one sample each, not results):**
NetPlumber's (source, probe) pairs are far more precise than VeriFlow-FR's
source-granular footprints -- on `wl_ifi` S2+S3, 780 against 8,605 checks
re-asked for the same 732 verdict changes.

The original order, kept for reference:

1. The recording engine and replay driver (§6.1), with S1–S3 generators and
   stamped seeds.
2. NetPlumber: `take_affected` hooks, single-rule delete, the index-reuse fix,
   `insert_rule`/`delete_rule`/`set_link` in the adapter.
3. FaVe: verdict cache, selective re-verification, the oracle — first on
   NetPlumber, on `wl_example`/`wl_ifi`/`wl_cloud`/`wl_up`.
4. VeriFlow-FR: per-rule translation, footprint criterion, LPM priorities.
5. After O1–O2: NetPlumber LPM, APKeep.
6. Harness: metrics, stamps, limits; then a `PROTOCOL.txt` with predictions,
   and only then a measurement.

Milestone 2 starts with its packet-filter spike once M1's selective
re-verification passes its oracle.

## 11. What this does not cover

- The full airtel traces (real churn), until the owner reopens them (D7).
- Runtime state tracking (D8).
- Reproducing the papers' tables (D5).
- Distributed NetPlumber; one engine instance per run.
