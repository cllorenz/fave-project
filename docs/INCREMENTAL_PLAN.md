# Incremental reverification — a plan

**Status: M1 IN PROGRESS (2026-10-09). Nothing measured yet.** Decisions D1–D9
are the owner's, taken in discussion on 2026-10-09 (§4). Of questions O1–O6, O1 and O2 are
decided; the rest carry a recommendation, not a decision (§9). §10 records what is
built: NetPlumber and VeriFlow-FR take updates and re-verify selectively, held
to the oracle; what remains of M1 waits on O1/O2 or on a protocol.
**Owner:** Claas Lorenz. **Branch:** `updates`. **Tracks:** TODO item 31, "the
incremental axis". Siblings: [`MEASUREMENT_RUN_PLAN.md`](MEASUREMENT_RUN_PLAN.md)
§10 (which names this as "a second campaign"), [`ACCOMMODATIONS.md`](ACCOMMODATIONS.md).

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
| APKeep-BDD (Java) | `Network.updateRule` (`Network.java:434`): `+`/`-` for every element type, then a loop check | `test_apkeep_lib.py` replays a Stanford trace with 4,526 removals against a loop golden |
| APKeep-NDD (Java) | **none** — from-zero `build`; `AtomForwarding` ignores the op | — |
| VeriFlow-FR (C++) | `Network::add_rule`/`remove_rule` return affected ECs; `remove_link` | `oracle_unit`, `rewrite_unit`; `remove_rule` only indirectly; `remove_link` untested |
| ad6 | none — a fresh bridge subprocess per check | — |

**Adapters — none can do it.** NetPlumber's incremental *adds* work because the
engine is live; its `delete_rules` cannot run (`adapter.py:972`: indexes `Rule`
objects as tuples, passes a table name as an index, removes only the first
negation expansion) and is unreachable. A second batch for a declared-LPM table
is refused (`LpmOrderingError`). APKeep builds once and, since `973736fb`,
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
model at build time. **NDD, the production default, is the easiest**, about
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

- **S1** insert every rule of the model one by one, then delete in reverse
  (APKeep's method; every rule is the update once, and the first half doubles
  as a build curve).
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

**Reported:** distributions, never means alone — median, p90, p99, maximum —
split by operation (insert, delete, link down, link up), with `affected` and
`precision` beside them; repetitions to be fixed by O4. Predictions are
declared in a `PROTOCOL.txt` before any run and never edited afterwards, as in
every campaign here.

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
- **O2. APKeep scope — DECIDED 2026-10-09.** APKeep-NDD is the NDD paper's
  system (APKeep's core, atom layer replaced by NDD); APKeep-BDD and APKeep-NDD
  work alike, incrementally. FaVe's `NddReachabilityEngine` is not that system
  and stays as a differential oracle ("NDD-flood"). Scoped in
  [`APKEEP_INCREMENTAL_SCOPE.md`](APKEEP_INCREMENTAL_SCOPE.md), whose §6 holds the
  questions still open.
- **O3. Oracle cost.** From-zero builds at every update are affordable only on
  the small workloads. *Recommendation:* every update on `wl_example`/`wl_ifi`;
  checkpoints every N updates and at the end of a stream elsewhere, N declared
  per workload in the protocol.
- **O4. Repetitions and limits.** *Recommendation:* 3 repetitions per stream on
  one machine, a declared per-update limit (a slow tail is a did-not-finish,
  not a hang) and a per-stream limit, stamped as in V5.
- **O5. `precision` as a headline.** It is where the engines' by-products
  differ (NetPlumber per (source, probe); VeriFlow-FR per walk footprint;
  NDD per device). *Recommendation:* report it beside every `t_total`.
- **O6. Equal-priority ties in APKeep** (§6.3). *Recommendation:* break ties in
  the translated priority, so incremental and from-zero builds agree by
  construction, and test it.

## 10. Order of work

**Progress (2026-10-09, branch `updates`):**

| step | state | commits |
|---|---|---|
| 1. replay seam, S1–S3, seeds | **done** — simpler than §6.1: `InProcessFaVe` builds each engine through the aggregator; the rules come from its stored models (`util/incremental.py`) | `bff573f7` |
| 2. NetPlumber | **done** — `take_affected` at the three probe hooks; adapter `insert_rule`/`delete_rule`/`set_link`; LPM tables take a rule back into its own slot only (O1) | `1ad4fe9a`, `240aa881`, `bff573f7` |
| 3. FaVe side | **done** — `VerdictCache`, selective re-verification, the from-zero oracle (a fresh engine behind a wrapper that withholds deleted rules and downed links) | `bff573f7` |
| 4. VeriFlow-FR | **done** — per-rule translation, walk footprints, LPM as on NetPlumber | `518e75cb`, `0430d036` |
| 5. NetPlumber LPM, APKeep | **waits on O1, O2** | — |
| 6. harness | **driver done**, `bench/incremental_run.py`, `dev`-stamped; limits (O4) and a protocol still to come | `5a518599` |

Held to the oracle in `test_incremental_{netplumber,veriflow}.py` on
`wl_example`, `wl_ifi` and `wl_cloud`: after every update, selective equals full
re-verification; at checkpoints, full equals from-zero. Both engines see the same
verdict changes on every stream. Disabling one probe hook (NetPlumber) or the
footprint states (VeriFlow-FR) fails every stream test.

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
