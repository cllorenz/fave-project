# ad6 → FaVe backend: a generic SAT/QBF model checker for comparison

**Status:** §1 theory DONE + §1.4 GO confirmed by owner (2026-08-20); §3.1/§3.3 DONE
(`make test` green, deps pinned); §4.1 decided + §4.4 major integration-architecture
correction from owner review, incorporated same day (wl_ifi reinstated, ad6 needs a new
FaVe-model translator, not a backend refactor). **The translator is now built and proven:
wl_tum (ad6-native format) and wl_ifi (via the new translator, forwarding+ACL) both
EXACTLY MATCH their NetPlumber/reachable.json oracles.** wl_up is **NO-GO, resolved
2026-08-21g**: even after fixing a real query-seeding bug (commit `dfd543b0`), plain
(non-stateful) wl_up queries turned out to be as vacuously reachable as the still-broken
stateful `related:1` ones — both are the same architectural gap (no state-shell
interweaving in `IP6TablesParser`) that FaVe's own NetPlumber pipeline already avoids via
`fave/iptables/generator.py`. wl_up's correctness work moves to FaVe+NetPlumber/
FaVe+NDD-APKeep; remaining ad6 effort redirects to **Stanford/i2 (§5.2)**. **Stanford's
faithful-VLAN spike (§5.4) is now PROVISIONAL GO (2026-08-27)**: the full 16-router
faithful-VLAN model builds and solves completely in ~12.7 min (measured on yolobox, not
yet bare-metal), `reachable_pairs`=165 exactly matching the NetPlumber-proven plain
oracle, with sub-exponential clause growth — a completed result where faithful BDD-APKeep's
own uncapped full build never finished. "Provisional" pending a bare-metal wall-clock
confirmation and one still-open, non-blocking discrepancy against APKeep's own N=3/N=5
faithful numbers (§5.4 B3). **i2 (§5.5): C0 GO (structural build confirmed, 18
devices/77,460 rules/0 ACLs). C1 is now GO too (2026-09-05): the full 72-pair
differential completed, WITH the real acyclic-safety fix active (an experimental lite
encoding), and exactly matches the oracle — 72/72, 0 missing, 0 extra. But note C3
REOPENED 2026-09-09: matching that oracle is guaranteed for any relaxed encoding (it is
an all-reachable mesh), so C1's GO does NOT license skipping faithful VLAN — and
FaVe+NetPlumber, cross-checked on i2 for the first time, reports 11 of the 72 pairs
UNREACHABLE. A three-query faithful experiment RAN 2026-09-09 (untag off) and did NOT corroborate them: control agrees, both discriminators come out reachable, so the disagreement localises to one engine and the admission-x-rewrite hypothesis is falsified; see §5.5 "C3 ANSWERED". C2
(tractability) is a separate, still-open concern, and solver-choice-sensitive:
Glucose4 took ~15.3 hours for 72 pairs; Cadical195 (2026-09-06), same encoding, same
exact oracle match, completed in ~3.56 hours — ~4.3x faster, and only ~13x slower per
query than Stanford's ~16 minutes for its full 256-pair matrix (was ~57x with Glucose4).
Still correct but not yet practical either way, and per-query cost remains highly
variable (sub-second to 31-80 minutes depending on solver). **UPDATE 2026-09-08: there
IS a pattern, but it is NOT topological distance — that first read was wrong, corrected
same day.** Per-query timing (`query_log`, new) found `losa`↔`newy32aoa` (LA/NYC) is the
hardest pair in both directions, and queries involving `hous` are consistently fast — but
a same-day follow-up (`bench/ad6_i2_query_distance.py`, no solving, pure graph metrics)
found hop-count, OR-gate fan-in, and forward/backward-reachable-set size ALL fail to
predict this (correlations 0.17, -0.10, -0.04) — the "geographic/topological distance"
story doesn't survive being checked against the actual graph. The pattern itself (the
`losa`↔`newy32aoa` bidirectional extreme) is real and reproducible, its cause is not; see
§5.5 for the full, corrected write-up. The earlier root cause behind why this needed a
lite encoding at all
still stands: `_CreateAcyclicConstraints`'s general (lxml/Tseitin-based) path OOMs
before even reaching DIMACS conversion — confirmed 2026-08-28, RSS grows ~0.14
MB/qualifying-edge, projecting ~22GB for the full 140,613-edge set, root-caused to
genuine memory blowup (not a sandbox artifact) in the per-edge CNF-conversion step. The
giant single SCC (99.3% of nodes) is why so many edges need it at all. Full detail in
§5.5. Owner: Claas
Lorenz. Companions:
[`APKEEP_NDD_PLAN.md`](APKEEP_NDD_PLAN.md), [`APKEEP_NDD_EVAL.md`](APKEEP_NDD_EVAL.md),
[`APKEEP_BACKEND.md`](APKEEP_BACKEND.md); tracked as item 11 in [`TODO.md`](TODO.md).
This plans integrating **ad6** — the author's
SAT/QBF model checker for IPv6 firewalls/networks (`ad6/`, SECRYPT'15) — as a **fourth
verification family** alongside NetPlumber (HSA), APKeep(BDD), and APKeep(NDD), for a
*controlled* cross-family comparison.

---

## 0. Thesis — why a generic model checker is worth the effort

The point is **not** to show a generic solver is slower than a specialised one (a foregone
conclusion), but to characterise **why**, **by how much**, and **where the trade-off
inverts** — and to place BDD-APKeep as the analytical bridge between the two worlds.

- **The solution space is 2-D, not a line.** Two orthogonal axes:
  - *Representation of packet sets:* explicit/ternary (HSA/NetPlumber) → symbolic-BDD
    (APKeep) → symbolic per-field (NDD) → clausal SAT/QBF (ad6).
  - *Algorithm:* topology graph-traversal over precomputed equivalence classes
    (HSA/AP/NDD — the domain-specific reachability algorithm) vs generic fixpoint /
    constraint solving (ad6: Kripke + SAT/QBF).
  In this space ad6 is generic on **both** axes; **BDD-APKeep is a deliberate hybrid** —
  a *symbolic set representation borrowed from model checking* (BDD) driving a
  *domain-specific* AP-graph algorithm. (Precise: APKeep's BDDs represent packet-header
  *sets*, not a transition relation; there is no symbolic fixpoint over a state space.
  Say "symbolic set representation," never "symbolic model checking.")

- **Two-factor cost model for "why slower" (theory + measurement).**
  - **Factor A — query amortisation.** NP/APKeep/NDD exploit topology structure so one
    source-flood answers all destinations: all-pairs ≈ **O(n) floods** (n = endpoints/
    roles). ad6 issues independent solves; the FPL `<->>` operator needs **3 checks per
    ordered pair**, so worst case **O(3·n²) solves**. Even at equal per-unit cost, the
    generic path does ~n× more work units because it cannot reuse a source across
    destinations. (Note: ad6's raw `_run_reach` is already **O(n)** per direction — one
    SAT instance per Kripke node — so the n² is a property of the *policy-compliance*
    semantics, not of reachability per se. Pin this down in §1.)
  - **Factor B — per-unit cost.** A SAT/QBF solve over the whole encoded model vs a graph
    flood over precomputed equivalence classes. **Factor B grows with model size (rules).**

- **The headline hypothesis (large network, small n).** Stanford/Internet2 are large in
  *rules* but small in *roles* (n). Since build ∝ rules and query-count ∝ n², the generic
  approach may be **uncompetitive on wl_up (large n) yet competitive on Stanford/i2 (small
  n)** despite those being "bigger" — an intuition-flipping result. The offset is that
  Factor B *grows* on the bigger models, so which wins is genuinely unknown → **worth
  measuring; the two benchmark classes cleanly separate the axes.**

- **Expressiveness × performance is the real trade-off.** ad6 can check properties the DS
  tools *structurally cannot express* (temporal / QBF-quantified properties, firewall
  anomaly classes). The genericity you pay for buys expressiveness — the write-up must show
  **both** sides, not just a speed race.

- **BDD-APKeep as the instrumented bridge.** The BDD-APKeep build profiler already splits
  time into `encode_ms`+`insert_ms`+`ppm_ms`+`merge_ms`+`split_count` (BDD/AP
  *representation-maintenance* — the "MC-flavoured" part) vs the graph flood (the
  *domain-specific* part). §2.6b showed representation-maintenance is what explodes on the
  faithful models and traversal stays cheap. So we can quantify, with existing traces, how
  much of the specialisation payoff lives in shrinking the representation layer.

---

## 1. Theory first (cheap, de-risks the engineering) — DO THIS FIRST

Rationale: the theory tells us which measurements are decisive and whether the
incremental-SAT lever (§6) is worth building *before* any code revival.

**UPDATE 2026-08-20: §1.1–1.3 DONE (code + thesis archaeology, no ad6 code changed).**

### 1.1 The two-factor cost model, precisely

Notation: `n` = roles/endpoints in the all-pairs comparison unit (wl_ifi 17+17,
wl_stanford 16, wl_i2 9, wl_up 137); `R` = ruleset size (Factor B driver); `k` = per-pair
check multiplicity implied by the FPL operator (see §1.2).

- **NP / APKeep / NDD:** build cost `B(R)` once (HSA transfer functions / BDD-AP / NDD
  atoms). Query cost is **O(n)**, not O(n²): one flood per source enumerates reachability
  to **all** destinations simultaneously as a side effect of graph traversal — this is
  exactly the "one-flood-answers-all-destinations" property already exploited by the
  wl_up/wl_stanford/wl_i2 benchmarks (`[[apkeep-ndd-baseline-and-gonogo]]`). Total:
  `B(R) + n·C_flood(R)`.
- **ad6 (as coded today):** build cost `B'(R)` = CNF encoding of the whole Kripke model
  (Tseitin-style, done once in `Instantiator.InstantiateBase`, includes the `_xor`-chain
  init constraints — §1.2). Each **pairwise** query is one **independent** SAT solve with
  **no cross-query reuse**: a SAT solve returns one satisfying assignment (or UNSAT) — a
  single Boolean — never "which other destinations are also reachable" as a byproduct.
  That is the sharp form of Factor A: it is not an instantiation-overhead problem (per-query
  instantiation is cheap, confirmed in §1.2), it is an **information-extraction-per-solve**
  problem — one graph flood yields `n` answers, one SAT solve yields 1. Total:
  `B'(R) + k·n²·C_solve(R)`.
- **Factor B** (`C_flood(R)` vs `C_solve(R)`): grows with model size on both sides, but by
  different mechanisms — graph flood cost is dominated by representation maintenance
  (BDD/AP merge/PPM, per §2.6b); SAT solve cost is dominated by clause count and solver
  heuristics (restarts, VSIDS) over the *whole* encoded ruleset per solve, even though only
  two endpoints differ between queries — nothing in current ad6 warm-starts a solve from a
  prior one (this is precisely the gap §6's incremental-SAT lever targets).
- **Headline hypothesis restated:** `k·n²·C_solve(R)` beats `B(R)` only when `n` is small
  enough that the O(n²) query term stays below the specialised engines' representation-build
  cost — i.e. Stanford/i2 (small `n`, but `R` large: i2 has ~77k FIB routes, meaning
  `C_solve(R)` is *also* large there — see §1.3 for why this is not a clean win either).

### 1.2 ad6's actual decision problems (from the code, not assumption)

Read `src/core/instantiator.py` + `main.py` in full. Table of every query primitive ad6
actually has:

| primitive | scope | # SAT solves | decides |
|---|---|---|---|
| `_run_reach` (`InstantiateReach`, all nodes) | per **Kripke node** (≈ per rule/interface state, not per role) | O(\|nodes\|) | "is this node reachable from the **currently active init set**" — multiple simultaneous active interfaces are amortised into **one** query per destination node (see below) |
| `_run_long_path_reach` | per Kripke node, **memoized** | ≤ O(\|nodes\|), often fewer — a SAT witness records which transitions actually fired, so nodes on that witness path are marked reachable without a further solve | same as above, with free amortisation across nodes proven reachable by an earlier witness |
| `_measure_end_to_end` (`InstantiateEndToEnd`) | per **ordered role pair** (src, dst) | exactly **1 solve per pair**, O(n²) total | plain existential reachability src→dst; **no** backward-flag, **no** must-not-reach enforcement — this is the plan's Factor-A target primitive |
| `_run_cross` (`InstantiateCross`) | global | O(1) | does any `accept`-annotated node's predicate overlap any `drop`-annotated node's predicate (global anomaly, not per-pair) |
| `_run_cycle` | global | O(1) | forwarding-loop existence |
| `_run_shadow` / `_run_long_path_shadow` | per rule | O(#rules), 1 solve/rule (or pruned) | rule-shadowing detection |

**Correcting §0's assumption — the FPL `<->>` operator is NOT ad6-native.** Grepped
`ad6/` end to end: no `FPL`, no `<->>`, no backward-flag concept anywhere in the SAT/Kripke
code. `<->>` is **FaVe's own policy language** (thesis Ch. 4/7, `A <->> B` = "stateful
reachability"), and the **3-checks-per-pair** claim is confirmed verbatim in the thesis
(§7.2, p.163): *"the rule Internet `<->>` WebServer results in three checks: one for the
unrestricted access ..., one for answers ... marked back=1, and one for forbidden
initializations ... marked back=0."* `--->` and `<-->` are 2 checks; the `default`
(unannotated) pair is 1 check (must-not-reach). This is FaVe's compliance-translation
target semantics that a fully faithful ad6 integration needs to reproduce, and ad6
currently has no instantiator for it (no backward-flag literal, no negative/must-not-reach
gate beyond `_measure_end_to_end`'s print-only diagnostic).

**CORRECTION 2026-08-20 (Claas): `<->>` is required, not optional — my first pass here was
wrong.** I had claimed the existing benchmark corpus never exercises `<->>`, generalising
from `[[apkeep-backend-followup]]`'s audit — but that audit only covered wl_stanford/wl_i2.
Claas caught that wl_up genuinely needs `<->>`. Verified directly against the checked-in
model files rather than trusting the old audit further:

| benchmark | FPL operators in `reach.txt` | checks with a `related:` condition in `cchecks.json` |
|---|---|---|
| wl_up | 30× `<->>`, 3× `<-->` | **3302 / 11902** |
| wl_ifi | 4× `<->>` | **54 / 299** |
| wl_stanford | 1× `<-->` | 0 / 240 |
| wl_i2 | 1× `<-->` | 0 / 72 |

So only wl_stanford/wl_i2 are pure k=1 existential reachability; **wl_up (§5.1's flagship
ad6-home-turf benchmark) and wl_ifi both require the stateful 3-check semantics** — and,
corrected in §4.4 below, wl_ifi is very much in scope (my initial "moot regardless" note
here was wrong: it was based on ad6 needing to parse wl_ifi's Cisco-ACL text itself, which
is not how the FaVe-adapter integration actually works). `cchecks.json` entries already
show the exact FaVe encoding:
for a `<->>` pair the same (src,dst) gets a plain check plus two more sharing a
`test_fields=["related:1"]` / `["related:0"]` condition (must-reach for related/established
return traffic; must-NOT-reach for a fresh/`NEW` connection initiated by the callee) — i.e.
FaVe's own compliance layer already stores the 3-check breakdown per pair explicitly; the
"query count" per benchmark is simply the total entry count in `cchecks.json`, no `k·n²`
estimation needed once the file exists.

**The good news: ad6 already has the connection-state vocabulary end to end, so this is
scoped work, not a new field to invent.** Cross-checked `policy_translator/policy.py:597-637`
(FaVe's own `<->>`→iptables compiler): a `<->>` rule literally compiles to an iptables rule
carrying `state: 'RELATED,ESTABLISHED'` — a real `-m conntrack --ctstate` condition. ad6's
`IP6TablesParser` (`ad6/src/parser/iptables.py:44-45,139-140`) already parses
`--state`/`--ctstate` into a `GenUtils.state(...)` rule field, and
`ad6/src/xml/xmlutils.py:136-141` already encodes it as a 4-way one-hot bit-vector
(`STATES = {NEW:0, ESTABLISHED:1, RELATED:2, UNTRACKED:3}`, via `ConvertStateToVariables`,
wired into `Instantiator._HandleOthers`). So a `<->>` pair's three checks are: (1) the plain
`InstantiateEndToEnd(src,dst)` query as today; (2) the same query plus an extra conjunct
asserting `state ∈ {ESTABLISHED, RELATED}` on the dst→src direction, expected SAT; (3) the
same reversed query with `state = NEW` asserted, expected **UNSAT**. **What's missing is
narrowly the query-orchestration layer** — a stateful sibling of `InstantiateEndToEnd` that
appends a state-literal conjunct (mirroring how `DisjSrc`/`DisjDst` are already appended) —
not a new field/semantics. This should be pulled into §4.2's scope as required work, driven
directly off `cchecks.json`'s `(dst, must_reach_bool, [conditions])` tuples so the ad6 query
generator and FaVe's own compliance semantics can't drift apart.

**Cost-model consequence — this widens, not narrows, the expected Factor-A gap on wl_up/
wl_ifi.** For NP/APKeep/NDD, "related" is just another matched header/state field inside the
*same* flood — the flood already computes reachability across the whole header space
(including all state values) in one pass, so the extra checks are cheap reads of an
already-computed result, not extra floods: still ~O(n) per source. For ad6, each of the
3 checks is a **separate, independent SAT solve** (a fresh state-literal assertion forces a
fresh solve, no warm-start) — so wl_up's true query count is close to 3× what a pure
existential comparison would suggest (**empirically: 11902**, not 137²=18769×1 — the actual
`cchecks.json` count already reflects the true instance count and should be used directly
instead of a `k·n²` estimate). This makes wl_up an even sharper worst case for ad6 than
originally modelled.

**SECOND CORRECTION 2026-08-20, since REVISED AGAIN — see §4.4.** I initially wrote here
that wl_ifi is unusable as an ad6 target because ad6's own `IP6TablesParser` can't parse
its Cisco IOS ACL syntax, and moved it into the same feasibility-gated bucket as
Stanford/i2. **Claas caught the underlying mistake: that's the wrong question.** FaVe
parses wl_ifi's ACLs itself and builds a neutral model; the ad6 adapter translates *that*
model into ad6's IR directly, never touching `IP6TablesParser` or Cisco ACL text at all —
so ad6's native-parser format is irrelevant to whether wl_ifi is in scope. §4.4 has the
full investigation (ad6's `GenUtils` module is already a clean, generic IR builder
decoupled from iptables-text parsing; a synthetic test confirmed rule-level jumps to a
specific egress interface work natively, giving real forwarding semantics with no backend
changes) and the corrected recommendation: **wl_ifi is reinstated, and is in fact the
better first target for building the FaVe→ad6 translator** (small, fast, and exercises
ACL+forwarding+VLAN — broader coverage than wl_tum). wl_tum's differential result stays
valid and valuable, but as a validation of the *backend/solving* path via ad6's own native
frontend (its ruleset happened to already be in ad6's native format) — a narrower,
complementary result, not the general integration path. Benchmark ordering (corrected
again in §4.4): **wl_ifi (build the translator) → wl_up (add the stateful instantiator) →
Stanford/i2 (add LPM-at-scale + VLAN admission, §5.2's real remaining question)**, wl_tum's
result carried along as the backend-correctness anchor throughout.

**One-source→all-dests feasibility: partially, not for free.** `InstantiateReach`'s
node-disjunction is composable — nothing stops building one instance whose top-level
disjunction ORs several destination nodes' backward-transition formulas ("does S reach ANY
role in set Y"), in O(1) instead of O(\|Y\|). But a single SAT witness only proves *that*
one target fired, not *which* one — so this composition helps coarse role-set reachability
questions (mirrors what `_run_reach` already does for "reachable at all"), not recovery of
the individual pairwise matrix. The matrix still needs either O(n²) independent solves or
the §6 incremental-SAT-with-assumptions lever to approach O(n). Per-query **instantiation**
itself is cheap regardless: `InstantiateEndToEnd`/`InstantiateReach` only append small
literal disjunctions to an already-CNF'd base (`SATUtils.ConvertToCNF` runs once, inside
`InstantiateBase`, not per query) — `main.py`'s existing instantiation-vs-solving timing
split (§2.1) already isolates this, confirming the plan's assumption that solve time, not
instantiation, is where Factor A bites.

### 1.3 Per-benchmark regime table (predicted, pre-measurement)

| benchmark | n (roles) | R (rule/route count) | true query count (`cchecks.json`) | predicted dominant factor | ad6 outlook |
|---|---|---|---|---|---|
| wl_ifi | 17+17 ⇒ ~34 | small (`ifi.csv`/`acls.txt`, dozens of rules) | 299 (54 stateful) | neither — cheap on both axes | **REINSTATED (§4.4):** not ad6-native *text* format, but that's irrelevant — the FaVe adapter emits ad6's IR directly, never touching ad6's own parser. Best translator-development target: small, fast, and exercises ACL+forwarding+VLAN together |
| wl_up | 137 | large — `ad6/bench/up/up-gw-alt-ruleset` alone is 6606 lines, dozens of per-department rulesets on top | **11902 (3302 stateful)** | **Factor A dominates hardest of all four** — true query count (11902) is ~0.6× n², not the naive n²≈18.8k, because FaVe's compliance translation doesn't check every ordered pair at k=3 uniformly, but it's still ~86× wl_ifi's count with a widened per-pair cost (§1.2 correction: `<->>` pairs cost ad6 3 independent solves vs ~free extra reads for NP/APKeep/NDD) — worst case for ad6, and worse than §0 originally modelled | ad6's own bundled `bench/up/run_large.sh` builds `bench/up/large.xml` with `--anomalies end_to_end` over an all-pairs target list (internet + gateway + wifi-clients + 8 DMZ hosts + 21 subnets × 6 subhosts) that sums to **exactly n=137** — the *same* role count as FaVe's wl_up. This is almost certainly the "known ~36 min baseline" referenced in §3.2 — **but note `_measure_end_to_end` as coded only issues the plain (non-stateful) check, so that historical ~36 min number was NOT exercising `<->>` either; a faithful re-measurement will need the stateful instantiator built first and will very likely take substantially longer** |
| wl_tum | very small (single firewall `fw.tum`, essentially a 1-Kripke-endpoint model per `policies.json`) | large (`ad6/bench/tum/tum-ruleset` = 3795 lines; FaVe's `wl_tum` cites "3.8k stateful rules") | **Factor B alone** — n² term is negligible, this isolates raw per-solve/per-flood cost vs ruleset size | cleanest single-axis measurement: if ad6 loses here it's pure representation/solve cost, not query amortisation |
| wl_stanford | 16 (240 all-pairs checks) | IPv4 LPM FIB, not iptables — **not yet ad6-encodable** (§5.2 risk); `ap_num` ~21.6k on the faithful VLAN variant | small n keeps Factor A cheap even at k=3; Factor B depends entirely on the (unbuilt) IPv4/VLAN encoding | feasibility gate, not a cost question, until §5.2's encoding exists |
| wl_i2 | 9 (72 checks) | ~77k dst-IP FIB routes | tiny n²=81 but potentially huge `C_solve(R)` per query — the sharpest test of the "intuition-flipping" hypothesis | **the decisive case**: if a plain per-rule SAT encoding of dst-IP LPM forwarding stays roughly linear in clause count (unlike BDD's monolithic blowup — `[[stanford-forwarding-overapprox]]`/`[[apkeep-vlan-admission-tractability]]` found NDD/BDD blow up on field-*independent* VLAN admission, not on LPM alone), ad6 could plausibly be **competitive or fast** here purely because it only issues 81 solves total — same feasibility caveat as Stanford (§5.2) |

wl_tum's exact role count and wl_stanford/i2's true ad6-side rule count (FIB entries, not
firewall lines) are asserted from file sizes/prior memory, not re-derived from a running
ad6 encoding — first cheap validation step in §3 (`make test` + a dry run against
`bench/tum`) should confirm these before trusting the table for planning purposes.

### 1.4 GO/NO-GO gate — recommendation (owner decision required)

Recommend (this whole section revised again 2026-08-20 — see §4.4 for the full correction;
what follows is the CURRENT state, not the history):
- **(a) Benchmark/build scope:** **wl_ifi (build the FaVe→ad6 translator) → wl_up (add the
  stateful instantiator) → Stanford/i2 (add LPM-at-scale + VLAN admission, §5.2)**, carrying
  wl_tum's already-proven backend/solving result along as the correctness anchor throughout.
  wl_ifi is *not* gated behind a feasibility spike — §4.4 found ad6's `GenUtils` IR layer
  and its rule-level interface-jump mechanism already express everything wl_ifi needs.
- **(b) `<->>` stateful query semantics — REQUIRED for wl_up.** wl_up needs it (§1.2); wl_ifi
  also has stateful checks in its `cchecks.json` and, per §4.4, is genuinely in scope for
  them too — not moot. Pull the stateful instantiator (3 checks: plain,
  `state∈{ESTABLISHED,RELATED}` reverse-must-reach, `state=NEW` reverse-must-NOT-reach) into
  §4.2's required scope, driven off `cchecks.json`'s `(dst, must_reach, [conditions])`
  tuples. ~~De-risked: ad6 already has the `STATE` field end-to-end (parser + bit-vector
  encoding), so this is query-orchestration work on top of existing machinery, not new
  modelling~~ — **FALSIFIED 2026-08-21, see §5.1's GO/NO-GO flag: forcing the `STATE` bit
  has no causal link to an actual permitted reverse flow, so `related:1` checks are
  vacuously true wherever a device has an unconditional ESTABLISHED accept (essentially all
  of wl_up). Making this sound needs something like `fave/iptables/generator.py`'s
  state-shell interweaving inside ad6's translator — genuinely new modelling, not
  orchestration.** It is not skippable for a faithful wl_up (or wl_ifi) comparison, and it
  makes ad6's per-pair cost worse (3 independent solves, not 1) than the original plan
  assumed. wl_tum's oracle is a single reachability check (not an FPL role-mesh — confirmed
  against `policies.json`), so it doesn't need the stateful instantiator and can stay the
  simplest validation of the plain path. **RESOLVED 2026-08-21g — GO/NO-GO decided: NO-GO
  on wl_up via ad6, for both the stateful AND plain path; see §5.1's resolution and "Open
  decisions" below.** wl_up's second bug (§5.1) was root-caused and fixed, but a follow-on
  measurement then found *plain* (non-stateful) wl_up queries are equally vacuous (1712/1713
  false violations, sample), for the same structural reason as bug 1 — so scoping wl_up's ad6
  comparison down to "just drop `<->>`" is not the safe fallback it looked like; there is no
  sound subset of wl_up left for ad6 without porting real state-shell interweaving into its
  translator, which Claas judged not worth the investment. Remaining ad6 effort redirects to
  Stanford/i2 (§5.2), which needs none of this (0 stateful checks in either).
- **(c) Incremental-SAT lever (§6):** build **after** the (now-stateful) wl_up baseline, not
  before. §6 is only worth the effort if wl_up's O(n²)-ish query cost is shown to actually
  dominate wall-clock (more likely now that each `<->>` pair costs 3 solves) rather than
  build cost — confirm by measuring first. **RESOLVED 2026-08-24/25 — CONFIRMED, see §6
  below and `AD6_ENCODING_PLAN.md` §§3.4–3.9**: measured against the real wl_up model and
  its full 11,902-query `cchecks.json`, not a proxy. Query cost dominates decisively; the
  lever collapses it from an extrapolated ~2.25h to 16.6s (ad6's own Minisat family, via
  its native incremental API) or ~71–102s (Z3), exact-match-correct throughout.
- **(d) Stanford/i2 feasibility — the genuinely remaining open question.** Not a parsing
  question (§4.4 retired that framing) — a SAT-encoding-*scale* question: does LPM-at-scale
  and VLAN-admission-cross-product stay tractable in ad6's Kripke/CNF representation the
  way NDD's atom partitioning stays tractable in BDD's, or does it blow up the way faithful
  BDD-APKeep did (`[[apkeep-vlan-admission-tractability]]`)? Genuinely unknown, still its
  own spike, still correctly gated after wl_ifi/wl_up prove the translator itself. Both
  remain genuinely k=1 (no `related:` conditions in their `cchecks.json`), so they don't
  need the stateful instantiator.

(§3 is already done; this gate governed §4's scope, which Claas has now reviewed and
corrected directly — see §4.4.)

---

## 2. Metric & methodology alignment (shared with the controlled-environment effort)

- **2.1** Unify every tool on **build cost + per-query cost × query count** (ad6's "base
  model once, reused across runs" fits this exactly). ad6 already emits instantiation-time
  vs solve-time separately and computes median/stdev (+ `yappi`) — reuse that.
- **2.2** Define the **query unit** explicitly: per ordered pair, with the `<->>` 3×
  constant stated; document whether one-source→all-dests is achievable (feeds §6).
- **2.3** Cross-family fairness: NP is C++, APKeep is JVM, ad6 is Python+native SAT
  binaries (minisat/clasp) or `pycosat`. Report total wall **and** a warmed/steady
  component; separate the language-runtime tax from the algorithm.
- **2.4** SAT-solver variance: clasp/minisat use restarts/heuristics → high variance. Fix
  seeds where possible, run N repeats, report median + spread. Prefer one primary solver;
  keep the others as a sensitivity check.
- **2.5** Peak RSS per tool (not just internal table bytes), matching §2.6b's lesson.

---

## 3. Revive & harden ad6

- **3.1** Code-quality pass: `ad6/` is 2014 proof-of-concept. Inventory deps (`lxml`,
  `yappi`, `pycosat`, external `minisat`/`clasp` binaries), get `make test` green, modernise
  where needed **without changing semantics** (vendoring hygiene: separate commits +
  a `FAVE_CHANGES`-style changelog, mirroring the APKeep/NDD discipline).
- **3.2** Reproduce the **known baseline**: the prior one-off end-to-end reachability run on
  a wl_up variant (~36 min). This is the correctness/perf anchor. Identify *exactly which*
  wl_up variant it used — if it differs from today's wl_up, that reintroduces the
  "explain-the-difference" problem we hit with Stanford; resolve it now, not later.

  **UPDATE 2026-08-20 (Claas): unsure whether that ~36 min run used the current wl_up —
  checked what's checkable.** All **138 shared per-host/department ruleset files** are
  currently **byte-identical** between `ad6/bench/up/*-ruleset` and
  `fave/bench/wl_up/rulesets/*-ruleset` (incl. the gateway, `pgf.uni-potsdam.de-ruleset`).
  Provenance is reassuring but not conclusive: wl_up's own git history literally begins as
  "AD6-Benchmark" (`d062246a` "Rename AD6-Benchmark to UP-Benchmark", 2019-10-25) — the two
  benchmarks share a common ancestor by design, not coincidence. However,
  **`fave/bench/wl_up/rulesets/` is gitignored** (`fave/.gitignore:7`) — these are
  regenerated/copied artifacts, not tracked, so git history cannot prove they've stayed in
  sync continuously. Tracked history shows FaVe's side was last touched 2020-01-27 ("Remove
  rulesets from up wl", i.e. untracked from that point on), while `ad6/bench/up`'s copy was
  independently **regenerated in 2022** ("Regenerate most classbench files as the initial
  rulesets were too small", `415d3fc6`; "Add rulesets for large UP benchmark", `fe52e727`) —
  so the current byte-identical match likely reflects a later manual sync, not continuous
  identity. **Practical resolution: don't try to forensically date the old ~36 min run.**
  Since the ruleset *content* driving today's wl_up backend comparisons is confirmed
  identical to `ad6/bench/up` right now, just **re-run `ad6/bench/up/run_large.sh` fresh**
  and treat that as the current, verified baseline going forward — this sidesteps the
  provenance question entirely. **Still open, not yet checked:** ruleset content matching
  does not by itself prove **topology wiring** matches — `ad6/bench/up/large.xml` (built by
  `gen_large.py`, present only in ad6, not committed) is an independent XML/Kripke topology
  encoding from FaVe's JSON-based `topology.json`/`routes.json`. A structural sanity check
  (host count, link count, active-interface set) between the two once `large.xml` is
  generated is a cheap, worthwhile addition to this step before trusting a fresh
  measurement as "the same network."
  **Also newly relevant to this step (see §1.2 correction):** `_measure_end_to_end` as
  coded only issues the plain non-stateful check, so whatever the historical ~36 min number
  measured, it was *not* exercising `<->>` — a faithful re-measurement needs the stateful
  instantiator (§4.2) built first, and should be expected to take meaningfully longer than
  36 min once it does.
- **3.3** Pin the ad6 env (Python deps + SAT-solver binaries + versions) in the shared
  `Dockerfile` alongside NP/APKeep/NDD.

---

## 4. Integrate with FaVe

- **4.1 Integration level — DECIDE (assess, don't assume).** Two paths:
  - **(A) `AbstractVerificationEngine` backend** — an ad6 adapter implementing the same
    seam APKeep uses (`add_generator/add_link/add_probe/add_rules/.../check_*`), building
    ad6's Kripke model from FaVe's `add_*` calls.
  - **(B) Model translation** — emit ad6's native inputs (ip6tables rulesets + network/
    Kripke config) from the FaVe model and drive `main.py`. ad6 is natively
    ip6tables-driven (`src/parser/iptables.py: IP6TablesParser`), and it ships
    `bench/up` + `bench/tum` rulesets that already share the UP/TUM lineage, so (B) may be
    the lower-friction path. First read: (B) for reach, (A) only if we want live/incremental.

  **DECIDED 2026-08-20: (B).** Confirmed the ruleset-sharing claim directly rather than
  assuming it. There are *two* IPv6-lineage claims to untangle here — checked both:
  - `ad6/bench/tum/tum-ruleset` vs `fave/bench/wl_tum/rulesets/tum6-ruleset` (the
    IPv6/NAT64-mapped, `64:ff9b::/96`, conversion): same rule count (3795) but NOT
    byte-identical — different address family per rule, as expected.
  - `ad6/bench/tum/tum-ruleset` vs `fave/bench/wl_tum/rulesets/tum-ruleset` (FaVe's own
    **default** wl_tum input): **byte-identical (`diff -q` confirms).** `wl_tum/benchmark.py`
    defaults to `-4`/`--ipv4` (`RULESET = 'bench/wl_tum/rulesets/tum-ruleset'`); the IPv6
    conversion is an opt-in `-6` mode, not what NP/APKeep/NDD are actually compared on by
    default. **Corrected: feed ad6 the plain IPv4 `tum-ruleset` it already ships — zero
    ruleset translation needed for wl_tum, not the IPv6 form as I first assumed.**

  **"Open gap" walked back after checking FaVe's own model, not just ad6's.** I'd flagged
  ad6's 2-interface `tum.xml` stub (vs the ruleset's dozens of VLAN sub-interfaces,
  `eth1.110` etc.) as a gap to fix. Checked FaVe's own `bench/wl_tum/topology.json`
  first: it is **equally minimal** — one `packet_filter` device, interfaces `["eth0",
  "eth1"]`, **zero links**. FaVe's own wl_tum oracle question doesn't route through any
  declared interface either: `sources.json` wires `source.tum` directly to
  `fw.tum.forward_filter_in` (raw injection into the FORWARD chain, bypassing admission),
  and `policies.json` wires `fw.tum.forward_filter_accept` (the FORWARD chain's synthesized
  ACCEPT exit) directly to `probe.tum` — both are structural ports NetPlumber's
  `packet_filter` device type exposes, unrelated to any physical/VLAN interface. So
  ad6's matching primitive is exactly analogous and needs no interface work either: mark
  the ruleset's first FORWARD rule (`tum_fw_forward_r0` — `IP6TablesParser` always keys a
  chain's entry rule `r0`) as the sole init, and check reachability of the synthesized
  `tum_fw_accept_r0`. **Verified 2026-08-20 (§4.3, below): this now runs and matches the
  NetPlumber oracle exactly.** ad6's bundled `tum.xml` topology is genuinely unused by
  this query on both sides — not a gap, just unexercised structure neither backend needs
  here.
- **4.2** Wire the reachability query so ad6 answers the **same source→probe matrix** as
  NP/APKeep/NDD, **including the stateful `<->>` 3-check form (REQUIRED for wl_up and
  wl_ifi, see §1.2/§1.4/§4.4).** Build a stateful sibling of `InstantiateEndToEnd` that
  asserts a `state`/`ctstate` literal (ad6 already has the field: `XMLUtils.STATES`,
  `ConvertStateToVariables`, `IP6TablesParser`'s `--ctstate`) alongside the existing
  DisjSrc/DisjDst conjunction, driven directly off each benchmark's `cchecks.json`
  `(dst, must_reach, [conditions])` tuples so ad6's query semantics can't drift from FaVe's
  own compliance translation. wl_stanford/wl_i2 stay on the plain (non-stateful) path.

  **BUILT + partially characterized 2026-08-21.** The mechanism is now wired end to end:
  - `fave/ad6/adapter.py:_capture_acl` now captures the `related` match field (`"0"`=NEW,
    `"1"`=ESTABLISHED — mirrors `apkeep/adapter.py:_RELATED`; FaVe's own state-shell,
    `fave/iptables/generator.py:_derive_general_state_shell`/`_calculate_blocks`, never
    emits a compound value, so this 1:1 mapping is exact) into a 5th tuple slot on every
    ACL entry (`[idx, permit, src, dst, related]`).
  - `ad6/src/parser/favemodel.py:_acl_rule` emits a `GenUtils.state('ESTABLISHED'|'NEW')`
    condition on the rule when `related` is present.
  - `ad6/fave_bridge.py:_state_literals` forces the matching state onto a query instance
    for a `{"name": "related", "value": "0"|"1"}` entry in `cond`. **Load-bearing
    correctness detail, verified empirically before relying on it (see
    `ad6/test/core/instantiatortest.py:testStateLiteralForcingIsMutuallyExclusive`):** the
    literals must come from `XMLUtils.ConvertStateToVariables(value)`'s FLATTENED
    conjunction children appended individually, not the raw `<state>value</state>` element
    (which only gets canonicalised into the shared bit-vector space by
    `Instantiator._HandleOthers`'s **build-time** pass over variables the base model
    *already contains* — a value like "NEW" that never appears in any real rule would stay
    an unconnected, unconstrained atom and silently fail to conflict with an
    ESTABLISHED-only branch), and NOT the whole `<conjunction>` appended as one nested
    child (a silent no-op / spurious-UNSAT trap — `instance[0]` is the base model's
    already-CNF'd clause list from `InstantiateBase`, so each top-level child must be its
    own flat literal).
  - **A second wiring bug found and fixed along the way, unrelated to ad6 itself:** the
    real `check_compliance` dispatch path (`InProcessFaVe` → `aggregator_service.py`'s
    `_handler`) converts every `cond` entry via `RuleField.from_json`, meaning `cond`
    reaches `Ad6Adapter.check_compliance` as a list of `RuleField` *objects* — not JSON-
    serialisable as-is for the subprocess-bridge payload. Added
    `Ad6Adapter._cond_to_json` (`RuleField.to_json()`, passed through unchanged if already
    a dict) before the `json.dump`.
  - **End-to-end exercise on wl_ifi's REAL compliance policy** (not the synthetic all-pairs
    matrix `test_ad6_wl_ifi.py` uses) — `fave/test/test_ad6_wl_ifi_stateful.py`, loading
    `bench/wl_ifi/cchecks.json` (299 entries, 54 stateful, matching §1.2's table exactly)
    straight into `check_compliance`. **Third gotcha, also unrelated to ad6:**
    `cchecks.json`'s own tuples are `(probe, valid, cond)` — `valid` (`bench/
    reach_csv_to_checks.py:_generate_cchecks`, True = no `"!"` prefix = "must reach") is
    the OPPOSITE polarity of the `(source, negated, cond)` convention every backend's
    `check_compliance` (and `bench/compliance_checker.py`'s own `_parse_check`) actually
    expects. Loading the tuples in place inverted almost every one of the 299 checks into
    a reported violation before this was caught and fixed (flip to `not valid`).
  - **Result, once both wiring bugs were fixed:** all 245 plain (`cond=[]`) checks pass —
    consistent with `test_ad6_wl_ifi.py`'s exact match. Of the 54 stateful checks (27
    `<->>` pairs × {related:1, related:0}), the 27 related:1 ("must reach with
    ESTABLISHED") checks all pass; **all 27 related:0 ("must NOT reach with NEW") checks
    fail** (ad6 reports reachable). Traced one pair (`source.internal.ifi` →
    `probe.admin.ifi`) to its actual captured ACL entry: `acl_out['464']` has
    `[7424, True, '10.0.12.0/23', '10.0.14.0/23', None]` — a **state-blind** permit
    (`related=None`). This is not a translation gap: wl_ifi's ACLs are parsed as-is from
    real Cisco IOS text (`bench/wl_ifi/acls.txt`), which never carries a `related`/
    `established` qualifier on this rule at all, so there is nothing for the adapter to
    carry through. Forcing ESTABLISHED vs NEW against a state-blind rule necessarily
    yields the *same* reachability answer; related:1 happens to want that answer,
    related:0 doesn't — hence the clean, systematic 27-pass/27-fail split (not a handful
    of scattered failures, which would look more like a bug).
  - **OPEN QUESTION, not resolved here — needs Claas or a live NetPlumber differential:**
    is this 27-violation split a genuine, pre-existing property of wl_ifi's real ACLs
    (reach.txt's `<->>` intent was never actually implemented in acls.txt for these
    pairs, so NetPlumber would report the *same* 27 violations against the *same*
    state-blind rule), or does NetPlumber's own `check_compliance` resolve a `related`
    cond through some other, topology/role-based mechanism this adapter hasn't accounted
    for? `fave/test/test_ad6_wl_ifi_stateful.py` currently asserts this as a
    **characterization** (pins down the traced, understood 27/27 split so a future
    change is caught as a diff), not a differential — do not read its current green
    status as "wl_ifi's stateful checks are proven correct."
- **4.3 Differential correctness gate:** ad6 vs NetPlumber (the oracle) on **wl_tum + wl_ifi
  + wl_up** (wl_ifi reinstated 2026-08-20, see §4.4 — it is not ad6-ingestible *as raw ACL
  text*, which is irrelevant since the FaVe adapter never feeds it raw text);
  **soundness is the hard gate** (ad6 must never drop an NP-reachable pair). Same discipline
  as the APKeep/NDD differentials.

  **wl_tum DONE 2026-08-20 (commit pending), MATCH.** `ad6/test/differential/tumdifftest.py`
  (wired into `test/test.py` via `differentialsuite.py`): built the model from
  `bench/tum/tum-ruleset` + `bench/tum/tum.xml` exactly as ad6 ships them, init at
  `tum_fw_forward_r0`, query reachability of `tum_fw_accept_r0`. **ad6 says reachable=True,
  NetPlumber (oracle, via `fave/bench/apkeep_tum_diff.py --emit netplumber`) also says
  True — exact match, single-pair.** ~30s (dominated by CNF instantiation over 3794 rules;
  a fresh `sys.setrecursionlimit` is needed — `main.py` already does this, a bare script
  driving `Instantiator` directly must do it too, or `_GetOutputsRecurse`'s ~3800-deep
  recursion over the FORWARD chain's fall-through transitions blows Python's default
  limit). wl_up (stateful, §4.2) is next.

- **4.4 MAJOR CORRECTION 2026-08-20 (Claas): wl_ifi's "not ad6-ingestible" framing was
  wrong — I'd mis-scoped the integration architecture itself.** Claas: *"Since FaVe parses
  this, it is not necessary for ad6 to be able to do this on its own. FaVe parses the
  configuration and creates the network model. The ad6-adapter will then transform the
  network model to a suitable format for the ad6 backend."* I had judged wl_ifi (and by
  extension Stanford/i2) against whether **ad6's own `IP6TablesParser`** could read Cisco
  IOS ACL text — the wrong question. The adapter never needs to feed ad6 raw ACL/FIB text
  at all; it consumes FaVe's *already-parsed* neutral model (the same per-rule
  representation the APKeep/NDD adapters already consume) and emits whatever ad6 needs
  directly. `IP6TablesParser` is just *one possible frontend* ad6 happens to ship, not a
  hard boundary on what the adapter can produce.

  **Investigated the actual frontend/backend coupling before revising anything (2026-08-20)
  — better news than expected.** `src/xml/genutils.py` (`GenUtils`) is *already* a clean,
  generic Config-tree IR builder — `firewall`/`table`/`rule`/`action`/`proto`/`address`/
  `port`/`state`/`vlan`/`interface`/`node`/`network`/`route`/... — used by
  `IP6TablesParser.parse()` purely as a set of element factories after it has finished
  parsing iptables CLI syntax. `KripkeUtils.ConvertToKripke` (`kripke.py`) and everything
  downstream (`Instantiator`, CNF, solving) consume *only* this `GenUtils`-shaped XML tree
  via XPath — they have **zero knowledge of, or dependency on, iptables syntax**. So the
  "major refactoring... separating frontend from backend" Claas anticipated turns out to be
  **~90% already done** by ad6's own existing design: `GenUtils` *is* the seam. What's
  needed is not surgery inside `kripke.py`/`instantiator.py`, but a **new frontend module**
  — call it a FaVe-model-to-`GenUtils` translator — that walks FaVe's neutral model (roles,
  ACL rules, routes, VLANs) and calls the *same* `GenUtils` factory functions
  `IP6TablesParser` already calls, skipping the iptables-text step entirely. This is a
  substantially smaller undertaking than a "major refactor" of ad6 itself.

  **One real open question needed an experimental answer, not a guess: can a rule route to
  a *specific* egress interface (real forwarding/routing), or only to the generic shared
  "accept" node that `_ConnectOutputs` floods to *every* declared egress interface of the
  firewall (fine for a stateful filter like wl_tum, wrong for a router like wl_ifi's
  central router or Stanford/i2's FIB)?** Built a minimal synthetic test (2 rules, 2
  declared interfaces, each rule's `action type="jump"` targeting a *specific* interface
  key directly instead of the shared accept node) and ran it — not assumed:
  - Both `ifA_out`/`ifB_out` are existentially reachable (expected — SAT semantics, each
    for a different destination header).
  - **Forcing dst = the address rule 0 matches: `ifA_out` SAT, `ifB_out` UNSAT. Forcing
    dst = rule 1's address: the reverse.** Confirmed discrimination is real, not "everything
    reaches everything."

  **Conclusion: `action type="jump" target="<any-declared-node-key>"` already gives
  per-rule egress-interface selection natively — real forwarding/routing semantics — with
  *zero* ad6 backend changes.** This directly de-risks the core modelling concern for
  wl_ifi (central-router dst-IP forwarding) and meaningfully de-risks Stanford/i2 too
  (though their VLAN-admission-cross-product *scale* question, §5.2, is separate and still
  open — that's a SAT-encoding-size question, not an expressiveness one, and this finding
  doesn't resolve it).

  **Revised recommendation (supersedes §1.4(a)/(e) and the wl_ifi-dropped calls in
  §1.2/§1.3/§4.3/TODO.md — corrected below):** wl_ifi is reinstated as Claas suggested — a
  small, fast benchmark (dozens of rules, not thousands) exercising ACL permit/deny
  (`address`/`proto`/`port` Gamma, already used by `IP6TablesParser` — no new primitive)
  *and* forwarding (direct interface-jump, just verified) *and* VLAN matching (`GenUtils.vlan`
  already exists) — a better **adapter-development** guide than wl_tum, whose success only
  validated the backend/solving path via ad6's own native ip6tables frontend (a valid,
  complementary, but narrower result — wl_tum's ruleset happened to already be in ad6's
  native format; wl_ifi's isn't, so it forces building the actual translator). Build order:
  **wl_ifi first** (small enough to iterate fast on the new translator), generalising the
  same translator to wl_up (adds the stateful `<->>` instantiator, §4.2) and then
  Stanford/i2 (adds LPM-at-scale + VLAN admission, §5.2's genuine open question) once the
  translator itself is proven on wl_ifi.

---

## 5. Extend to all benchmarks

- **5.1** wl_up, wl_tum, **wl_ifi** (reinstated 2026-08-20, §4.4) — via the FaVe→ad6
  translator. **wl_ifi DONE (§4.3): exact match, forwarding+ACL.** wl_tum's
  backend/solving path is already proven (via ad6's own native frontend). wl_up remaining,
  needs the stateful `<->>` instantiator (§4.2) added on top of the same translator.

  **BUILT 2026-08-21, but a structurally NEW translator path, not an extension of wl_ifi's
  router/ACL one.** First surprise: wl_up's FaVe device model is `packet_filter`/`host`
  (136 of its 159 devices), NOT wl_ifi's Cisco-ACL `router` — a fundamentally different
  device class with its own table naming (`.input_filter`/`.output_filter`/
  `.forward_filter`/`.pre_routing`/`.routing`, from `devices/packet_filter.py`, not
  `.acl_in`/`.acl_out`). **Second, much better, surprise:** each of these 136 devices'
  actual rule CONTENT (`bench/wl_up/rulesets/*-ruleset`) is literal `ip6tables` command
  text — confirmed byte-identical to ad6's own bundled `ad6/bench/up/*-ruleset` (§3.2's
  earlier provenance check) — i.e. the exact same "already in ad6's native format, no
  translation needed" situation wl_tum was in, just per-device instead of one firewall.
  So the translator does NOT hand-build GenUtils calls for proto/port/state/icmp/etc from
  FaVe's re-parsed Match objects (which would have meant reimplementing a large slice of
  `ip6tables` semantics from scratch); it feeds each device's raw ruleset text straight
  into ad6's own `IP6TablesParser` (`Ad6Adapter.load_bench_metadata` reads
  `topology.json` for the device→ruleset-path/own-address map; `favemodel.py:
  _build_ruleset_firewall` calls `IP6TablesParser.parse` directly). What's genuinely NEW
  adapter work is only: (a) dst-LPM ROUTING (`.routing`'s `out_port` MATCH field —
  ip6tables text has no notion of routing at all, that's FaVe's own derived FIB;
  `_translate_routing_rule` + `favemodel._routing_table`, same sequential
  specific-before-default discipline as wl_ifi's router forwarding), and (b) the
  to-self/in-transit DISPATCH a transit device (pgf) needs (`favemodel._dispatch_table`,
  data-driven off whether a device has any dst-specific route at all — `_is_transit` —
  rather than counting physical ports).

  **One real design snag, resolved:** `IP6TablesParser` resolves every chain's
  `-j ACCEPT` to ONE shared `<fwkey>_accept_r0` sink regardless of which chain
  (INPUT/OUTPUT/FORWARD) reached it. Correct for the accept/drop decision itself, wrong
  for what happens AFTER accept — INPUT-accept means "deliver locally", OUTPUT/
  FORWARD-accept means "continue to this device's own routing". Fixed by rewriting
  OUTPUT's/FORWARD's own accept-jump targets (XPath, scoped by table) to the device's
  routing-table entry instead, leaving INPUT's untouched.

  **Three real bugs found and fixed while building this, in increasing order of how long
  they took to pin down** (full traces in `ad6/FAVE_CHANGES.md` §10 and
  `[[ad6-theory-gate-findings]]`):
  1. `fave/ad6/adapter.py`'s dst/src field matching hardcoded `packet.ipv4.*` — wl_up is
     pure IPv6 (`packet.ipv6.*`). Silent: no error, just an always-`None` dst, so a
     switch's own forwarding rule quietly became an unconditional flood instead of a
     dst-conditioned jump. Added `_DSTS`/`_SRCS` tuples checked everywhere a single IPv4
     name was checked before (`_translate_fwd_rule`, `_translate_routing_rule`,
     `add_generator`).
  2. `_build_device_table`'s dst-address builder hardcoded `version='4'` unconditionally
     — used by wl_ifi's router (always IPv4) AND, once fixed above, by wl_up's own
     switches (their `.1` tables go through this SAME shared fwd_rules mechanism, IPv6).
     Silently corrupted an IPv6 CIDR condition rather than raising. Fixed with a small
     `_ip_version(addr)` sniff (`':' in addr`) instead of a hardcoded literal.
  3. `XMLUtils.CanonizeIP`'s IPv6 "::" expansion drops the boundary zero group when the
     compressed run is at the very END of the address (`Postfix == ""`):
     `"2001:db8:abc:1::/64"` canonicalises to the malformed `"...:0:/64"` (a trailing
     colon), which later crashes `int('', 16)` in `ConvertCIDRToVariables`. Originally
     worked around in `favemodel.py` (`_ipv6_safe`); **fixed in ad6 core 2026-08-21,
     test-first, at Claas's request — see §8.2b below.** Worse than first logged: leading
     `::` and `::` alone were ALSO broken (same root cause), plus a separate
     `UnboundLocalError` crash for an address with no `::` compression at all.

  **A genuine, load-bearing mechanism insight (not a bug):** `KripkeUtils.ConvertToKripke`
  always calls `_RedirectInputs`, which rewrites every accept-jump reachable from a chain
  literally named "input" away from the shared `<fwkey>_accept_r0` sink onto a dedicated
  `<input_entry_key>_accept` node instead — found the hard way (a trivially-satisfiable
  single-rule INPUT chain returned UNSAT against the shared sink; traced via
  `Kripke.IterFTransitions`/`IterBTransitions` to this redirect). This is exactly the
  mechanism that makes multi-chain accept-sharing safe in ad6's own native model; it only
  applies to chains named "input" (FORWARD/OUTPUT are NOT redirected this way, which is
  why they needed the explicit routing-retarget above). `favemodel.query_destination_key`
  targets `<fwkey>_input_r0_accept`, not the shared sink, for a wl_up host being probed.

  **Structural correctness confirmed** (`fave/test/test_ad6_wl_up.py`): 159 devices (136
  ruleset-bearing + 23 switches), 137 generators/probes (matches §1.3's n=137), model
  builds and instantiates in ~8s, a full 137-query batch against one probe in ~67s
  (~0.5s/query — confirms §1.3's "Factor A/B dominate hardest of all four" prediction; the
  full `cchecks.json`, 11902 entries, is a ~1-2 hour run, a bench script not a routine
  test).

  **OPEN METHODOLOGY QUESTION, resolved-in-part by Claas already for the state-blindness
  angle (see below) but with a wl_up-specific wrinkle still worth flagging:** an
  UNCONSTRAINED existential query against wl_up is close to vacuously "always reachable"
  — every ip6tables chain here has an unconditional `-m conntrack --ctstate ESTABLISHED
  -j ACCEPT`, and static header-space analysis (ad6, or any HSA-style tool) cannot
  distinguish a genuinely-established connection's packet from one merely claiming to be
  (session state isn't a real per-packet header field) — so a plain check needs
  `related:0`/state=NEW forcing (already built, §4.2) to say anything meaningful, unlike
  wl_ifi where this only mattered for the 54 explicitly-stateful checks. Once forced and
  src-seeded, results become properly differentiated (confirmed on hand-picked pairs,
  `test_ad6_wl_up.py`) — but comparing against `reachable.json` under STRICT EQUALITY
  (test_ad6_wl_ifi.py's approach) is the wrong bar for wl_up specifically: its real
  rulesets carry operationally-necessary rules reach.txt's policy matrix never modelled
  as role-to-role reachability (e.g. dmz-file's `-s 2001:db8:abc::0/48 --dport 22 -j
  ACCEPT` grants SSH to file.uni-potsdam.de from every internal /48 subnet, including
  clients.hssport.uni-potsdam.de, which reachable.json's 29-role list for that target
  does not contain) — traced and confirmed real (clients.hssport's own seeded src CIDR
  genuinely falls inside that /48), not a translation artefact. `cchecks.json`'s explicit
  tuples are the right comparison target instead, same as wl_ifi's own characterization
  approach (`test_ad6_wl_ifi_stateful.py`) — deferred to a bench script given the ~1-2
  hour full run.

  **STOP — GO/NO-GO FLAG (2026-08-21): the stateful instantiator is not a sound oracle for
  wl_up, and the gap is architectural, not a small bug.** Found running
  `bench/wl_up/eval/wl_up_cchecks_diff.py`'s sample mode (10 singleton/central sources, 1092
  checks) against the real `cchecks.json` policy: 488 violations, far beyond the
  already-understood "unconstrained plain query is vacuous" gap above. Traced to TWO
  independent bugs:

  1. **The `related:1` (ESTABLISHED) half of every `<->>` check is vacuously true — root
     cause understood, not a small fix.** `ad6/src/parser/iptables.py`'s `IP6TablesParser`
     parses `-m conntrack --ctstate ESTABLISHED` into a bare `<state>ESTABLISHED</state>`
     match: one exogenous, freely-choosable bit (`XMLUtils.STATES`/`ConvertStateToVariables`)
     with **no causal link** to "a matching flow was actually permitted in the reverse
     direction first." `ad6/fave_bridge.py`'s `_state_literals` forcing mechanism (§4.2)
     forces this bit directly onto a query — but that just asks the solver "can you assert
     this bit AND find some other permit rule," which is *always* yes whenever a device has
     an unconditional `-j ACCEPT` gated only on that bit (true of essentially every wl_up
     device: `ip6tables -A INPUT -m conntrack --ctstate ESTABLISHED -j ACCEPT`, no `-s`).
     Verified directly: forced `related:1`, `negated=True` (must-NOT-reach) for the 8
     singleton/central sources (`adm`/`data`/`dns`/`file`/`ldap`/`mail`/`vpn`/`web`
     `.uni-potsdam.de`) against `probe.print.cs`/`probe.file.cs` — **all 8 report
     reachable=True**, including `adm`, the one source independently confirmed correctly
     *blocked* on the `related:0`/NEW side. Zero source-address discrimination. This is
     exactly the problem `fave/iptables/generator.py`'s "state shell interweaving"
     (`_derive_general_state_shell`/`_derive_conditional_state_shells`/
     `_interweave_state_shell`) exists to solve: derive the ESTABLISHED-return leg from the
     *actual* corresponding NEW-state permit rule in the opposite chain
     (direction/port-swapped, match-intersected, spliced in at the right position) so
     ESTABLISHED is a *consequence* of an earlier permitted flow, not a free bit anyone can
     assert. `IP6TablesParser` has no equivalent pass — it is a literal, structural
     ip6tables-text-to-Kripke translator with no state-causality modelling at all. Net effect
     for wl_up: every device carries this unconditional ESTABLISHED accept, so ad6's
     `related:1` ("must reach with ESTABLISHED forced") answer carries **zero verification
     information** for this benchmark — true for every pair, correct or not.
  2. **A second, independent, still-not-root-caused bug in the `related:0` (NEW) direction.**
     Of 8 structurally identical singleton hosts sharing one `/64`
     (`2001:db8:abc:1::1`–`::8`: file/mail/web/ldap/vpn/dns/data/adm), every org device's real
     ip6tables ruleset carries an unconditional `-A INPUT -s 2001:db8:abc:1::0/64 -j DROP`
     with no later re-permit for that source — so a state=NEW, src-seeded query from any of
     the 8 should be UNSAT. 7 of 8 report reachable=True anyway; only `adm` (`::8`) is
     correctly blocked. Confirmed deterministic and address-specific, not query-order-
     dependent (reversing the query order leaves `adm` as the sole correctly-blocked case
     regardless of position). Root cause NOT yet found. Ruled out: `_is_constrained`'s `/0`
     special-case (inapplicable — these are all real host addresses), state contamination
     across queries in the same bridge-subprocess batch (ruled out by the order-reversal
     test), and the just-fixed `CanonizeIP` "::" bug (none of these 8 addresses contain "::").
     Prime remaining suspect, untested: `Instantiator._ShortenPrefixes`/`_HandlePrefixes`'s
     CIDR canonicalization across the full 159-device model's shared `src_ip6_*` variable
     space.

  **Why this matters beyond wl_up:** finding 1 is not a wl_up quirk — it is a property of
  `IP6TablesParser` plus the query-forcing mechanism (§4.2) exactly as built, and would
  reproduce on *any* ip6tables ruleset using `-m conntrack --ctstate` (standard practice, not
  a wl_up peculiarity — wl_ifi's Cisco ACLs happened to dodge this because they are genuinely
  state-blind, see above). **§1.4(b)'s original call — "ad6 already has the STATE field
  end-to-end..., so this is query-orchestration work on top of existing machinery, not new
  modelling" — is FALSIFIED by this finding.** Making `related:1` checks mean anything needs
  something functionally equivalent to `fave/iptables/generator.py`'s state-shell
  interweaving *inside* ad6's translator: a genuinely new, nontrivial modelling component, not
  query orchestration on top of what already exists.

  **Claas's read (2026-08-21):** given this, the oracle approach may not be viable without
  "conceptually significant work on ad6's frontend," and continuing the wl_up integration as
  currently scoped may not be worthwhile. **GO/NO-GO DECISION NEEDED FROM CLAAS** before any
  further wl_up work (including the deferred full `cchecks.json` run, the planned 5-org
  sample, and root-causing bug 2 above). Options on the table, not yet chosen:
  - **NO-GO / stop here** — wl_up's stateful checks are out of reach without a much bigger
    investment; leave wl_up at its current structural/characterization-only state
    (`test_ad6_wl_up.py`) and do not pursue the full differential.
  - **GO, scoped down** — restrict wl_up's ad6 comparison to the non-stateful (`cond=[]`,
    still gated on the already-known vacuous-plain-query caveat) checks, or treat `related:1`
    results as always-uninformative and only trust `related:0` once bug 2 is root-caused.
  - **GO, invest** — port something equivalent to the state-shell interweaving into
    `ad6/src/parser/iptables.py` (or a FaVe-side pre-processing pass ahead of
    `Ad6Adapter.load_bench_metadata`) so `related:1` stops being vacuous, before resuming the
    differential.

  **RESOLVED 2026-08-21g — bug 2 root-caused and fixed; a bigger, decisive finding
  surfaced immediately after; Claas decided NO-GO on wl_up via ad6 (both stateful and
  plain), effort redirected to Stanford/i2 (§5.2).**

  **Bug 2's real root cause (not `_ShortenPrefixes` — that hypothesis was tested in
  isolation and cleared): `ad6/fave_bridge.py`'s query source-address seeding
  (`_seed_conjunct`) forced the packet's source via a bare named-alias SAT variable
  (`XMLUtils.ConvertToVariables`'s `<ip>`-element form) instead of the canonical shared
  bit-vector conjunction (`XMLUtils.ConvertCIDRToVariables`'s flattened
  `ip<version>_src_<i>=<bit>` literals) — the exact same footgun class `_state_literals`
  already had to avoid for state-forcing, just never applied to address-seeding. The alias
  only constrains anything if that *exact* address/CIDR string happens to already be
  `Handled` by some *other* rule referencing it verbatim elsewhere in the whole 159-device
  model — true by coincidence for `adm` (referenced in an unrelated admin-SSH rule
  elsewhere) and false for the other 7 singleton hosts, which are only ever matched via the
  broader `/64` in their real rulesets. Fixed by seeding via `ConvertCIDRToVariables`
  instead (commit `dfd543b0`); regression tests added test-first
  (`ad6/test/core/instantiatortest.py::testSrcCidrQuerySeedMustUseSharedBitVector`,
  `fave/test/test_ad6_wl_up.py::test_stateful_checks_on_real_pairs` extended to all 8
  hosts), confirmed failing pre-fix, passing post-fix; `ad6 make test` (9 suites) and
  `fave/test/test_ad6_wl_up.py`/`test_ad6_wl_ifi.py`/`test_ad6_wl_ifi_stateful.py` (9/9)
  stay green.

  This is a genuine, general fix, not just an 8-host patch: re-running
  `bench/wl_up/eval/wl_up_cchecks_diff.py`'s sample mode at full size (35/131 orgs, 3342
  checks, 1126 stateful) afterward found only **1 stateful violation total** (was ~45% on
  the earlier small sample) — the fix holds at scale.

  **But that same larger run surfaced something more important than the fix: PLAIN
  (non-stateful, no `related` condition) checks are almost totally broken too — 1712 of
  1713 "must NOT reach" plain checks came back as false violations (99.94%), while all 503
  "must reach" plain checks correctly passed.** This is the same root cause as bug 1 (every
  wl_up device's unconditional `ctstate ESTABLISHED → ACCEPT` is a free bit any query can
  satisfy for free, with no state forced either way) — already flagged as a *theoretical*
  risk in this section's prose ("an unconstrained existential query... is close to
  vacuously reachable"), but never measured until now, and the real number is far starker
  than "close to" — it is total. **Consequence: "reduce to non-stateful policy" is not a
  safe fallback scope for wl_up on ad6 — the plain path is the MORE broken one, not the
  safer one.** The only wl_up queries currently behaving soundly are `related:0`
  (state=NEW)-forced ones; `related:1` stays vacuous (bug 1, unfixed, architectural) and
  plain queries are vacuous for the identical reason.

  **Did FaVe+NetPlumber avoid this? Yes, by construction, not coincidence — Claas's own
  question, checked directly in the code rather than assumed.** `bench/generic_benchmark.py`'s
  `GenericBenchmark` defaults `use_interweaving=True`, which routes wl_up's real ip6tables
  ruleset text through FaVe's *own* translator (`fave/iptables/generator.py`, the
  `_derive_general_state_shell`/`_derive_conditional_state_shells`/`_interweave_state_shell`
  machinery) instead of a bare structural parser — it derives the ESTABLISHED-accept leg
  from the actual corresponding NEW-permit rule and splices it in as a real flow-space
  constraint at model-construction time, so there is no free bit for a plain query to
  exploit. `ad6/src/parser/iptables.py`'s `IP6TablesParser` has no equivalent pass — this is
  bug 1's whole root cause, restated at the model-construction level. Corroborating
  evidence already in this codebase (not re-measured this session, but from the same
  pinned environment): `bench/wl_up/eval/apkeep_up_diff.py`'s docstring records an
  **exact match, 0 diffs, 3660/3660**, between APKeep and NetPlumber on wl_up's full
  137×137 plain reachability matrix (`[[apkeep-ndd-baseline-and-gonogo]]`) — a *sparse*
  reachable set (`reachable.json` itself lists 3370 policy-intended reachable pairs), not
  anything close to ad6's near-universal answer. Two independent real engines agreeing on a
  restrictive plain-reachability answer is strong evidence this is an ad6-specific gap, not
  a generic HSA/state limitation.

  **Decision (Claas, 2026-08-21): NO-GO on wl_up via ad6, for both the stateful and plain
  path.** Porting real state-shell interweaving into `ad6/src/parser/iptables.py` would
  mean re-implementing, inside a 2014 codebase that has already produced four real core
  bugs in two days, a mechanism FaVe already has working in `fave/iptables/generator.py` —
  and doing so would undercut the whole "generic tool, low integration cost" thesis this
  evaluation exists to test. wl_up's correctness work moves to **FaVe+NetPlumber as the
  oracle, FaVe+NDD/APKeep as the arbiter** (already proven, already exact-matching,
  nothing new to build) — not to ad6. wl_tum's and wl_ifi's exact-match ad6 results stand
  unaffected (neither needed interweaving: wl_tum has no stateful checks at all; wl_ifi's
  real ACLs are genuinely state-blind, confirmed by Claas). Remaining ad6 effort redirects
  to **§5.2, Stanford/i2** — a completely orthogonal question (LPM-at-scale + VLAN admission,
  zero `<->>`/connection-state involved in either benchmark) with a trusted oracle already
  in hand (NetPlumber==APKeep==165 on wl_stanford, `[[stanford-forwarding-overapprox]]`).

- **5.2 Stanford, Internet2 — the small-n hypothesis test (§0). The genuinely remaining
  feasibility risk, corrected 2026-08-20 (§4.4): NOT a parsing-format question (FaVe's
  adapter never depends on ad6's own parser, so "IPv4 vs IPv6-native" is moot) — a
  SAT-encoding-*scale* question.** Does LPM-at-scale forwarding + the VLAN-admission
  cross-product stay tractable in ad6's Kripke/CNF representation, the way NDD's atom
  partitioning tames it in BDD's (`[[apkeep-vlan-admission-tractability]]`), or does it blow
  up the way faithful BDD-APKeep did on the same workloads? Genuinely unknown, still its
  own spike, still gated at §1.4/§4.4.

  **Scoping check 2026-08-21h, before any Stanford/i2 translator code: is VLAN-admission
  cross-product actually the gate for the in-scope (165) target, or only for the faithful
  variant?** Checked against the current code: `apkeep/adapter.py`'s `_gate_dead_ingress`
  (the fix that made APKeep converge exactly with NetPlumber at 165) is a binary per-port
  admission gate, not per-(port,VLAN) rewrite — `[[apkeep-vlan-admission-tractability]]`'s
  own intractability finding is about the coupled admission+egress-rewrite cross-product,
  which that memory states is "NOT needed for wl_stanford... admission non-binding for
  all-pairs" at 165. So the 165-target spike's real requirement is **LPM-at-scale + a cheap
  dead-port gate**, not "LPM + VLAN admission" — smaller than this section previously
  implied. See below, though, for why this narrower framing is not where the ambition
  should stop.

  **A real LPM gap found and fixed test-first before any Stanford-specific code, on the
  reusable building block itself.** `ad6/src/parser/favemodel.py::_routing_table` (built
  for wl_up, §5.1, and earmarked above for reuse here) only ever received a binary
  0-vs-65535 `prio` from `fave/ad6/adapter.py`'s `_translate_fwd_rule`/
  `_translate_routing_rule` — "dst-specific before the no-dst default", not true
  longest-prefix-match; exact for wl_up only because it happens to have no two
  overlapping-prefix routes on one device. `ad6/test/parser/favemodeltest.py`'s new
  `RoutingTableLPMTest` fed the same two overlapping routes (a `/32` and a nested `/64`) in
  both insertion orders and confirmed the outcome flipped — the identical bug class that
  made vanilla NetPlumber misreport Stanford as 10/165 before its own fix. **Fixed:**
  `adapter.py` now computes a real `_lpm_prio(dst)` (longer prefix always sorts first,
  regardless of capture order); both producer functions use it. Full writeup, both
  regression tests (`ad6/test/parser/favemodeltest.py`,
  `fave/test/test_ad6_adapter_lpm_prio.py`), and the "no wl_ifi/wl_up regression" check:
  `ad6/FAVE_CHANGES.md` §14.

  **Scope correction (Claas, 2026-08-21h): despite the narrower 165-target scoping above,
  work TOWARDS the faithful variants of the benchmarks, not around them.** The
  admission-only gate this session confirmed sufficient for the plain 165 result is not the
  design target — build the Stanford/i2 translator with the faithful (per-port/VLAN
  admission + egress rewrite) case in view from the start, per §5.3 below (reversed from
  its previous "likely out of scope" framing).
- **5.3 Faithful-VLAN Stanford/i2 variants — IN SCOPE, target, not a stretch goal (corrected
  2026-08-21h, reversing this section's prior "likely out of scope" framing).** The prior
  framing reasoned ad6 "is not a forwarding/VLAN data-plane tool" and treated the plain
  165-target result as the finish line; Claas's explicit instruction is the opposite: the
  ad6 evaluation should work towards the faithful variant, not settle for the
  admission-non-binding special case. Concretely this means the eventual Stanford/i2
  translator should model per-(port,VLAN) admission and egress-VLAN rewrite as first-class
  structure (mirroring how `apkeep/adapter.py`'s `_capture_vlan_port`/rewrite-tracing or
  ad6's own existing `<vlan>` `GenUtils` element could represent it), not just the dst-IP
  FIB dead-port special case that happens to reach 165 — even though
  `[[apkeep-vlan-admission-tractability]]` found the BDD/NDD analogue of the full
  admission+rewrite cross-product intractable at 16-router scale. Whether ad6's SAT/CNF
  encoding hits the same wall or fares differently is exactly the open, unresolved question
  this redirected effort now exists to answer — not an assumption to make either way before
  trying.

- **5.4 Faithful-VLAN spike protocol, staged: expressibility → tractability, GO/NO-GO gated
  at each stage (planned 2026-08-21i).** Mirrors this project's own discipline (theory gate
  before code, small-n before full-n) and APKeep's own incremental-scale protocol so the two
  results are directly comparable in §7.

  Three findings frame the whole spike, the first **corrected 2026-08-21j** after Claas
  pointed out a real gap in the second one below: **ad6's model has no notion of a header
  bit taking more than one value along one path.** Every ad6 variable is a single global
  propositional constant — fine for matching (every rule's condition is checked against one
  fixed header) but wrong for mutation: a rewritten bit needs *different* values on either
  side of the hop that rewrites it, and a chain of rewrites (e.g. `b=* → 1 → 0 → *` along one
  path) needs as many distinct values as there are rewrite points. **The §5.4 draft below
  this correction (structural entry-point duplication, "which VLAN a packet is on = which
  Kripke node it's wired into") is not a general fix for this — it is a restricted special
  case that only works when a field changes at most once per path and the model is willing
  to enumerate every reachable value as a separate subgraph.** It does not extend to a
  multi-hop rewrite chain without duplicating the downstream subgraph once per combination
  of values along the chain (`(distinct values)^(rewrite points)` in the worst case) — the
  same shape of explosion that sank APKeep's BDD-based faithful-VLAN attempt, just via
  CNF/graph size instead of AP count. **Revised Stage A below replaces it** with the
  standard general technique for this class of problem: treat the Kripke graph like a
  program's control-flow graph and the mutable field like a mutable variable, and apply
  textbook **SSA construction** (static-single-assignment: one fresh variable per
  "definition site," frame axioms to carry a value across an edge that doesn't touch it,
  phi-style disjunctions at a join of several predecessor histories). This scales with the
  number of Kripke nodes downstream of a rewrite (linear in graph size), not with the
  product of values across rewrite points — a materially better story *if* it can be built
  cheaply enough (an open question of its own, see Stage B below).

  Second, `ad6/src/xml/genutils.py`'s `GenUtils.action()` has no `rewrite` type at all (zero
  hits for "rewrite" across `ad6/src/core|xml|sat`); `GenUtils.vlan()` is match-only,
  evaluated once per node's own Gamma at build time (`ad6/src/core/kripke.py`'s
  `_HandleVlans`) — nothing lets a rule's action change a downstream node's VLAN assertion
  today. The SSA encoding above is precisely what a real `rewrite` action needs to compile
  to. Third, `ad6/src/sat/satutils.py`'s `ConvertToCNF` is naive distribution-based (no
  Tseitin auxiliaries) — it explodes on *alternation depth* of nested OR-of-AND-of-OR
  structure, not on raw rule/node count, a **different blow-up mechanism than BDD's variable
  ordering**. Today's one-flat-rule-per-condition style keeps this cheap; the SSA encoding's
  frame/rewrite implications are the same shallow shape ad6 already builds per edge
  (`Instantiator._ConvertNodesToImplications`, `¬transition ∨ (equality ∧
  disjunction-of-predecessors)`, `ad6/src/core/instantiator.py:330-382`) so they shouldn't by
  themselves introduce new alternation depth — but this needs confirming, not assuming (see
  Stage A/B below). **If naive CNF conversion turns out to be the actual bottleneck once
  real numbers exist, switching `ConvertToCNF` to a Tseitin transformation (introduce one
  auxiliary variable per subformula instead of distributing) is the standard, well-understood
  fix** — it trades a larger variable count for a *linear* (not exponential) clause count in
  formula size, which is the textbook remedy for exactly this failure mode. Flagged as a
  candidate Stage B mitigation below, not undertaken speculatively before it's shown to be
  needed.

  **Stage 0 — prerequisite fix, DONE 2026-08-21i, before any VLAN code at all.**
  `Ad6Adapter._acl_device` was a single scalar (correct only for wl_ifi's one
  admission-checked router); `_acl_in`/`_acl_out` were flat `{vlan: [...]}` dicts with no
  device dimension; `_vlan_to_eport` was flat `{vlan: port}`. Stanford is 16 independent
  `in.X`/`out.X` devices that can reuse the same VLAN number for unrelated admission groups —
  **confirmed via a test fed the pre-fix code (`git stash`, same discipline as every other
  fix this cycle): a second device's capture silently merged into the first's `acl_in['10']`
  list instead of staying separate, and `_acl_device` simply forgot the first device once a
  second was seen.** This blocks even the already-in-scope plain-165 result at >1 admission
  device, independent of VLAN fidelity. Fixed: `_acl_device`→`_acl_devices` (a set),
  `_acl_in`/`_acl_out`→`Dict[device, Dict[vlan, ...]]`, `_vlan_to_eport`→
  `Dict[device, Dict[vlan, port]]`; `favemodel.py`'s `ir["acl_device"]`→`ir["acl_devices"]`,
  threaded through `_ingress_ports_for`/`entry_key`/`_build_device_table`. **A second,
  related latent bug found and fixed in the same pass**: `_build_device_table`'s egress-ACL
  loop iterated the *entire* (still globally "device.port"-keyed) `out_port_vlan` map
  unfiltered by device — harmless with exactly one acl device (every entry belonged to it by
  construction) but would emit a spurious egress-ACL table for another device's port once a
  second admission-checked device exists; now filtered to `device`'s own ports. Regression:
  new `fave/test/test_ad6_adapter_multi_device_acl.py` (2 tests, confirmed failing on the
  pre-fix code, passing after) — pure `Ad6Adapter` capture-layer unit tests, no ad6
  binary/subprocess/benchmark inputs needed. No regression: `ad6 make test` (10 suites) and
  `fave/test/test_ad6_wl_ifi.py`/`test_ad6_wl_ifi_stateful.py`/`test_ad6_wl_up.py`/
  `test_ad6_adapter_lpm_prio.py`/`test_ad6_adapter_multi_device_acl.py` (16/16) all green.
  Since no Stanford ad6 translator exists yet, this stage's regression check is wl_ifi's
  (1 acl device) and wl_up's (0 acl devices) existing results, not yet a Stanford rebuild —
  the plain-165 rebuild becomes possible once §5.2's translator itself is built.

  **Stage A — expressibility, synthetic, no real data, DONE 2026-08-21k (SSA/frame-axiom
  encoding, GO).** Unlike the superseded structural-duplication draft, this is a genuine
  **ad6 core extension** (`ad6/src/xml/genutils.py`, `ad6/src/xml/xmlutils.py`,
  `ad6/src/core/structure.py`, `ad6/src/core/kripke.py`, `ad6/src/core/instantiator.py`), not
  a frontend-only trick — a deliberate, explicitly-flagged departure from every other change
  this integration has made so far (§4.4's "new frontend, zero backend changes" discipline).
  That departure is the point: this stage is as much about characterizing what it *costs*,
  architecturally, to teach a generic SAT model-checker real mutation, as it is about getting
  VLAN specifically to work — a genericity-cost data point in its own right for §7.

  Implementation (all opt-in — every existing caller passes nothing new and is byte-for-byte
  unaffected):
  - `GenUtils.action('jump', target=..., rewrite_field=<name>, rewrite_value=<int>)` — rides
    on the SAME `<action>` as the jump it accompanies (a rewrite only ever takes effect
    together with the edge it's on; there is no standalone "rewrite but don't transition"
    rule shape), avoiding any change to `kripke.py`'s single-`<action>`-per-rule assumption.
  - `KripkeNode.Rewrites` (new, default `{}`): `_HandleRule` reads `rewrite_field`/
    `rewrite_value` off a rule's action into `Node.Rewrites[field] = value`.
  - `XMLUtils.FieldBitName(field, node, index)` / `ConvertFieldToVariables(field, node,
    value, width)`: the per-NODE bit-vector naming convention (`"<field>#<node>_<i>"`, using
    "#" — a separator nothing else in this codebase's variable naming uses, so it can never
    collide with the existing global dst/src/port/vlan/state aliases) and a query-forcing
    helper mirroring `ConvertVLANToVariables`, just node-scoped instead of global.
  - `Instantiator._CreateMutationConstraints(Kripke, MutableFields)` (`MutableFields`:
    `{field: bit_width}`, e.g. `{"vlan": 12}`): for every edge and every declared mutable
    field, emits either a REWRITE axiom (`transition_uv → (field@v ↔ constant)`, if the
    source node's `Rewrites` declares this field on this edge) or a FRAME axiom
    (`transition_uv → (field@v ↔ field@u)`, otherwise — including every fallthrough edge,
    which by construction never rewrites) — each built and CNF-converted per-edge exactly
    like `_ConvertNodesToImplications`'s own proven pattern (confirmed empirically before
    relying on it: a non-degenerate `A → (B ∧ C)` implication run through
    `SATUtils.ConvertToCNF` correctly yields `(B ∨ ¬A) ∧ (C ∨ ¬A)`, not the silently-dropped-
    conclusio result a superficial trace of `_ConvertBinaryForm`'s dispatch suggests — see
    `ad6/FAVE_CHANGES.md` §17 for the check). A join (multiple predecessors, potentially
    different field histories) needs **no new exclusivity mechanism**: each incoming edge
    independently asserts its own implication, gated on its own transition literal, so two
    predecessors with conflicting histories being simultaneously true is already correctly
    UNSAT under the *existing* reachability discipline — exactly like two conflicting
    forwarding paths already would be — and the solver remains free to leave the
    non-taken predecessor's transition false, exactly as it already does for reachability.
  - `Instantiator.InstantiateBase(..., MutableFields=None)`: new opt-in parameter, appends
    `_CreateMutationConstraints`'s output into `Encoding[0]` before the final CNF pass.

  Test (in `ad6/test/core/instantiatortest.py::testMutationChainAndJoinSSAEncoding`, wired
  into `InstantiatorSuite` — **not** `ad6/test/parser/favemodeltest.py` as originally
  planned: this is pure core Kripke/Instantiator machinery with zero `favemodel.py`
  involvement, so the honest home is alongside `instantiatortest.py`'s other core-mechanism
  regressions (the `/0`-CIDR bug, state-literal forcing), not the FaVe-translator-specific
  file). Two Kripke paths into a shared node: `entryA→r1(rewrite vlan=1)→r2(rewrite
  vlan=0)→r3(rewrite vlan=2)→join` (a 3-deep rewrite chain — the `b=*→1→0→*` case a global
  variable cannot express at all) and `entryB→alt(no rewrite)→join` (the join, with one
  predecessor that never rewrites anything). `entryA`/`entryB` both marked INIT so
  `_CreateInitConstraints`'s EXISTING mutual exclusion (§8) — reused, not reinvented —
  guarantees forcing one path's entry via `InstantiateEndToEnd` excludes the other's.
  **Confirmed test-first** (`git stash` on just the 5 core files, same discipline as every
  other fix this cycle): errors immediately (`GenUtils.action() got an unexpected keyword
  argument 'rewrite_field'`) without the implementation; passes with it. **Result: GO** —
  forcing `entryA`'s path, `join`'s vlan is SAT for exactly 2 and UNSAT for 1 or 3 (the chain
  resolved correctly, not silently dropped or stuck at an intermediate value); forcing
  `entryB`'s path, `join`'s vlan is SAT for two different arbitrary values (5 and 7),
  confirming it stayed genuinely free rather than being accidentally pinned. No regression:
  `ad6 make test` (10 suites, InstantiatorSuite now 8 tests) and all fave-side ad6 tests
  (16/16) green. (Also found, unrelated to this mechanism: `testCycle`/`testShadow` are a
  **pre-existing order-dependent flake** when run back-to-back outside `make test`'s own
  invocation — confirmed present on the unmodified baseline too, not introduced here; `make
  test` itself is unaffected and stays the authoritative check.)

  **Scoping note — what Stage A does NOT yet cover:** this proves the CORE mechanism only,
  on a hand-built synthetic fixture. Wiring it to real Stanford VLAN rewrite data (the
  `Ad6Adapter._capture_mid_rewrite`/`_capture_out_rewrite` capture, and `favemodel.py`
  actually calling `InstantiateBase(..., MutableFields=...)` with captured rewrites) is
  **not built** — that, plus the actual tractability measurement, is Stage B's job, next.

  **Stage B — tractability, real Stanford data, incremental scale (gated strictly on Stage
  A's GO, not yet started).** Real scale (`fave/bench/wl_stanford/stanford-json/`): 252
  in-stage VLAN-admission-checked ports, **147 trunk** (>1 VLAN, up to 128 on one port) vs
  105 access; 511 distinct VLAN values; per-router trunk-port counts 4–20. Reuse APKeep's
  own faithful-VLAN subset protocol and exact router lists for direct comparability
  (`fave/bench/faithful_bdd_measure.py` + `bench.apkeep_convergence._filter_model`,
  `--routers`): N=2 (`bbra_rtr,rozb_rtr`: ap_num 2574, build 34s), N=3 (+`roza_rtr`: 2661,
  110s), N=5 (+`soza_rtr,sozb_rtr`: 5697, 940s), full N=16 doesn't complete in 54 min
  (`APKEEP_NDD_EVAL.md:533-559`) — measure ad6's instantiate/solve split, CNF clause count,
  peak RSS at the same N. **Budget:** no hard cap through N=5, but >~20 min on one point is
  an early-warning signal to pause before N=16; attempt N=16 only if the N=2→5 growth,
  log-fit, projects under **60 minutes**; hard-stop there regardless. If it blows up,
  characterize *how* — for the SSA encoding the relevant dimensions are **number of
  rewrite-reachable Kripke nodes** (how far downstream of a rewrite the fresh per-node
  copies propagate), **join count/fan-in** (how many phi-disjunctions get introduced), and
  **chain depth** (rewrite points per path), varied independently on the fixed N=2 pair —
  a different set of dimensions than the superseded structural draft's "trunk-port count vs
  VLANs-per-trunk," since the cost driver is graph reachability from a rewrite, not per-VLAN
  subgraph duplication. A finding either way, not a dead end. **Candidate mitigation, only
  if warranted by the actual numbers:** if clause growth here is dominated by naive CNF
  distribution rather than by the encoding's own node/variable count, switching
  `ad6/src/sat/satutils.py::ConvertToCNF` to a Tseitin transformation is the standard fix
  (linear clause growth in formula size, at the cost of more variables) — try this only
  after Stage B's numbers show naive conversion, not the SSA encoding itself, is the
  bottleneck; building it speculatively first would confound the two questions. **Environment
  guardrail:** Stage A's correctness checks are fine on yolobox; Stage B's wall-clock/RSS
  numbers are only trusted on the controlled bare-metal environment (existing cross-cutting
  guardrail) — a yolobox run may catch a gross build error but is never the tractability
  verdict. **Oracle:** none at any scale for the faithful variant (APKeep's own attempt never
  completed even at N=16 either) — Stage B's correctness rests on Stage A's synthetic proof
  plus the existing plain-165 result as a sanity floor (a faithful-mode disagreement with 165
  on a VLAN-non-binding pair is a bug in the new code, not a VLAN-fidelity finding).
  **GO/NO-GO:** GO — headline §7 result — iff N=16 completes in budget on bare-metal with
  sub-exponential clause growth; NO-GO — reported with the dominant-dimension
  characterization, not a retry at larger budget.

  Full staged design (research + review trail): plan file from this session's planning
  turn, folded into this section; critical files, **now including ad6 core (revised
  2026-08-21j — the superseded structural draft was frontend-only)**:
  `ad6/src/core/instantiator.py`, `ad6/src/core/kripke.py`, `ad6/src/xml/genutils.py` (the
  new SSA/frame-axiom mechanism and `rewrite` action), `ad6/src/sat/satutils.py` (Tseitin,
  only if Stage B shows it's warranted), `fave/ad6/adapter.py`, `ad6/src/parser/favemodel.py`,
  `ad6/test/parser/favemodeltest.py`, `fave/apkeep/adapter.py` (read-only template),
  `fave/bench/faithful_bdd_measure.py`, `fave/bench/apkeep_convergence.py`.

  **Sequencing correction, 2026-08-24: "Stage B" above was written before any Stanford↔ad6
  translator existed at all — none of §5.1-§5.3's work ever built one.** Split into
  checkpointed sub-stages before touching VLAN fidelity: **B0** (plain LPM+dead-port
  translator, small N-router slice, DONE below) → **B1** (scale to 16 routers vs the 165
  oracle, DONE — see below, resolved 2026-08-27) → **Stage A2** (a `fieldmatch` core
  primitive Stage A alone turns out not to cover — DONE 2026-08-27, GO, see below) → **B2**
  (VLAN-faithful wiring, DONE 2026-08-27, see below — a genuine finding, not yet a
  tractability result) → **B3** (the N=2/3/5/16 measurement above, not yet started, and now
  needs the finding below resolved first). Full staged design: this session's plan file,
  folded in below.

  **B2 — DONE 2026-08-27, real Stanford VLAN-admission/rewrite data wired through Stage
  A/A2's mechanism.** Ported (not imported) `apkeep/adapter.py`'s own P7b Stanford-faithful
  capture methods onto ad6's own primitives: `_capture_mid_rewrite`/`_capture_out_reset`/
  `_capture_in_admission` (`fave/ad6/adapter.py`, opt-in `Ad6Adapter(..., faithful_vlan=
  True)`) plus a new `_fold_mid_rewrites` (ad6-specific — folds the out-stage's vlan=0
  reset into the mid-stage's rewrite value, needed because B0's own `_collapse_out_stage`
  already discards the out-stage before favemodel.py ever sees the IR); `favemodel.py`'s
  `_build_device_table` emits `fieldmatch`/`rewrite_field` accordingly, `_gen_firewall`
  rewrites a source's own known vlan onto its injection edge, `instantiate_base` threads
  `MutableFields={'vlan':12}`. Deliberately mirrors APKeep's own device-level
  admitted-VLAN-union simplification (not a genuinely per-port trunk/access model), per this
  section's own "reuse APKeep's protocol for direct comparability" instruction. **A real bug
  found and fixed test-first** in `_fold_mid_rewrites`: ad6's own `_out_ports` returns a
  full "device.port" string (unlike apkeep/adapter.py's, which pre-splits to a bare port
  number), so the fold's lookup silently missed every real reset pair until the port string
  was split consistently with the map's own keys — caught by
  `fave/test/test_ad6_wl_stanford_faithful.py`'s own regression test. Two test layers (39
  total, all green, no regression): 15 fake-Rule unit tests fave-side
  (`test_ad6_wl_stanford_faithful.py`) plus 6 real-build tests ad6-side
  (`ad6/test/parser/favemodeltest.py::FaithfulVlanWiringTest`, including a 3-device
  rewrite→downstream-admission chain proving the mechanism composes across routers, not
  just Stage A2's own single-hop synthetic fixture). A real N=2 slice
  (`bbra_rtr,rozb_rtr`) built and solved successfully against real data — result identical
  to B0's already-NetPlumber-proven plain result.

  **GENUINE FINDING (confirmed at the raw-data level, `bench/wl_stanford/stanford-json/
  sources.json` itself — not an ad6-specific bug): wl_stanford's real sources never declare
  a `packet.ether.vlan` field at all.** So a source's own vlan stays a genuinely free SSA
  variable at the point it enters `in.X`'s new admission check — and a free variable
  trivially satisfies "vlan ∈ admitted set" for any non-empty admitted set. The new
  admission mechanism is real, sound, and proven correct (fake-Rule tests + the synthetic
  3-device chain), but **vacuous for every source-originated compliance query on this
  benchmark as it is actually shaped today** — it only bites TRANSIT traffic (router-to-
  router, gated by an upstream `mid.X` rewrite pinning a concrete value before a downstream
  `in.Y` checks it). **Not an artifact of ad6's SAT semantics**: NetPlumber/APKeep's own
  HSA/BDD header-space model gives an unconstrained field the identical "mere possibility
  counts" interpretation (an injected header space spanning every value, intersected with an
  admitted-VLAN condition, stays non-empty as long as the admitted set is non-empty) — so
  **APKeep's own faithful-VLAN build necessarily has the same vacuousness for
  source-originated queries**, since both adapters read the identical FaVe
  `GeneratorModel.fields` for the same `sources.json`. This is a property of the benchmark
  data and the "no access-port VLAN-assignment step modelled" gap shared by both backends'
  current faithful attempts, not a defect specific to this port. **Not silently worked
  around** — flagged for a decision, same discipline as the wl_up NO-GO and B1's
  cycle-soundness gap: a significant finding is a decision point, not something to patch
  around unprompted. What a fix would need (not attempted): model the real access-port
  behaviour missing from both engines' current faithful builds — a locally-injected,
  physically-untagged frame gets its VLAN ASSIGNED by the ingress port's own static
  (per-physical-port) configuration, the same information B0/B1's already-built (but, for
  wl_stanford's `SwitchModel` shape, currently dead — no `.pre_routing` table exists there)
  `_capture_iport_vlan`/`in_port_vlan` mechanism was designed to carry, if it were also
  wired to a per-port REWRITE instead of only a structural ACL-group selector. Full
  write-up: `ad6/FAVE_CHANGES.md` §22.

  **RESOLVED 2026-08-27 (discussed with Claas): the "vacuous" framing above was an
  overstatement, not a genuine gap — no fix needed before B3.** Claas's correction: NetPlumber's
  own header-space propagation gives an unconstrained field the SAME "starts as a wildcard,
  gets pinned the moment it hits a matching/rewriting rule, propagates unchanged otherwise"
  semantics — flows become progressively more specific along a path, never magically
  changing except at an explicit rewrite. Re-examined the SAT encoding against that
  standard: `Instantiator._CreateMutationConstraints` already enforces EXACTLY this
  invariant structurally (one axiom per edge, rewrite-or-frame, no third option for how
  `field@node` gets a value), and existential SAT search over that structure computes the
  same thing HSA's flow-splitting-and-intersecting does — "does there exist a consistent
  witness path" is the SAT-native form of "does the propagated header space stay
  non-empty." A free field trivially satisfying a non-empty admitted set is therefore the
  CORRECT existential answer ("does some concrete packet get through"), not an unsoundness
  or an escape hatch — NetPlumber, fed the identical `sources.json`, would compute the
  identical thing. Also re-examined the actual scope: the real captured `mid.X` rewrites
  pin vlan to a fixed value regardless of what arrived, so the "field is free" situation
  only ever applies at a path's FIRST admission check — every check downstream of a
  rewrite is genuinely, provably gated (exactly what `FaithfulVlanWiringTest`'s 3-device
  chain test already demonstrated: `in.r2` admits {9} vs {3} correctly discriminates on
  `mid.r1`'s rewritten value). So the earlier "vacuous for every source-originated query"
  characterization was too broad — only the first hop is unconstrained, which correctly
  mirrors that nothing in the real data constrains which VLAN a host's own access port
  assigns; every hop after a rewrite remains meaningful. **No access-port VLAN-assignment
  step needed** — proceed to B3 as built.

  **B3 — DONE 2026-08-27, provisional GO (numbers measured on yolobox, not bare-metal —
  see the environment caveat below before treating this as final).** New driver
  `fave/bench/ad6_faithful_measure.py`, mirroring `bench/faithful_bdd_measure.py`'s own
  CLI/structure (same `--routers` flag, same induced-subnetwork reuse via
  `apkeep_convergence._filter_model`) for direct comparability, but reporting ad6's own
  instantiate/DIMACS-build/solve split, CNF clause count, and peak RSS instead of BDD
  `ap_num`/JVM heap — driving `favemodel`/`IncrementalSession` directly (not through the
  production subprocess bridge) for instrumentation access, the same discipline
  `ad6_encoding_bench/axis8d_stanford_netplumber_diff.py` already established for
  measurement-only scripts.

  | N | routers | Kripke nodes | clauses | build+DIMACS | query | wall | peak RSS | reachable (non-self) |
  |---|---|---|---|---|---|---|---|---|
  | 2 | bbra,rozb | 1,196 | 138,556 | 6.4s | 0.2s | 9.5s | 627 MB | 2 |
  | 3 | +roza | 1,435 | 171,088 | 7.0s | 10.4s | 21.3s | 797 MB | 4 |
  | 5 | +soza,sozb | 1,875 | 246,814 | 10.5s | 31.8s | 48.0s | 1,152 MB | 16 |
  | 16 | full | 5,463 | 711,100 | 31.5s | 713.7s | **764.0s** | 3,322 MB | **165** |

  Clause count grows roughly polynomially (138k → 711k, ~5.1× for an 8× router increase),
  not the exponential/superlinear blow-up that sank faithful BDD-APKeep (§0/`APKEEP_NDD_EVAL.md`:
  its own full uncapped faithful build ran 54 minutes, applied 70% of rules, `ap_num`
  22,249 and still climbing — **did not complete**). ad6's full N=16 faithful model
  **completed in ~12.7 minutes**, well inside the plan's own 60-minute attempt budget, and
  its `reachable_pairs` (165) is **exactly** the plain/dead-port-gated oracle B1 already
  proved matches NetPlumber exactly (0 diffs, 165/165) — i.e. at real full scale, faithful
  VLAN admission changes nothing beyond the already-proven-correct plain model for this
  benchmark's actual query set.

  **A real discrepancy found and root-caused (partially) before trusting any of this: N=3/N=5
  don't match APKeep's own committed faithful numbers** (`bench/wl_stanford/eval/
  faithful_bdd_pop_N{2,3,5}.json`): N=2 matches exactly (2 vs 2), but N=3 gives 4 (APKeep: 3)
  and N=5 gives 16 (APKeep: 7) — a gap that GROWS with N, not noise. Investigated with a
  live NetPlumber arbiter (Claas's suggestion) rather than guessing: re-ran the SAME N=3/N=5
  induced slices with `faithful_vlan=False` (ad6-plain) and diffed against a live NetPlumber
  worker on those exact slices (`_emit_worker`, the same live-oracle discipline B0/B1 already
  use) — **0 diffs at both N=3 and N=5**. Combined with ad6-faithful giving the IDENTICAL
  reach matrix to ad6-plain at every N tested (2, 3, 5, and 16): the "extra" pairs are
  genuinely, topologically real (NetPlumber-confirmed), not an ad6 forwarding bug, and ad6's
  faithful-VLAN admission is not silently failing to restrict something it should on these
  slices — it restricts nothing on ANY tested slice, consistent with the full-scale result.
  **Working hypothesis, not confirmed further**: APKeep's own full-scale faithful build never
  completed (the uncapped run above), so its N=2/3/5 numbers are the ONLY faithful data it
  ever produced, on artificially INDUCED (regenerated-ruleset) subnetworks — plausible that
  those slices' own regenerated admitted-VLAN sets at the slice boundary diverge from the
  full topology's real ones in a way that doesn't reflect true Stanford behaviour, rather
  than ad6 under-restricting. Not verified against APKeep's own induced-slice VLAN capture
  directly — flagged as an open, non-blocking discrepancy, not chased further this round.

  **ENVIRONMENT CAVEAT (existing cross-cutting guardrail, restated): this entire table was
  measured on yolobox (sandboxed), not bare-metal.** Per `AD6_PLAN.md`'s own guardrail, a
  yolobox run confirms the model builds/solves correctly and gives directional signal, but
  is never the tractability GO/NO-GO verdict Stage B3 asks for. §5.4's own gate: "GO... iff
  N=16 completes in budget on bare-metal with sub-exponential clause growth." N=16 DID
  complete, well under budget, with polynomial (not exponential) clause growth — **on
  yolobox**. Calling this **provisional GO**, pending a bare-metal re-run to confirm the
  wall-clock numbers before treating it as the final §7 headline result.

  **Stage A2 — DONE 2026-08-27, GO.** Stage A built the rewrite/frame-axiom SSA mechanism
  but only wired the QUERY side of reading a per-node value
  (`XMLUtils.ConvertFieldToVariables`); nothing let a rule's own Gamma (match condition)
  reference a mutable field's live per-node SSA value — every existing match primitive,
  `GenUtils.vlan()` included, resolves to one GLOBAL alias shared by the whole model. This
  is a real gap for the actual Stanford admission shape: "mid.X rewrites the egress VLAN to
  N; in.Y's ACL only admits the packet onward if its CURRENT (incoming) VLAN tag is in some
  admitted set" — an admission rule whose match needs to read what a DIFFERENT (upstream)
  rule just wrote, which a single global alias structurally cannot express once VLAN is
  genuinely mutable. New: `GenUtils.fieldmatch(field, value, negated=False)` (the match-side
  counterpart to `action(..., rewrite_field=, rewrite_value=)`);
  `XMLUtils.FieldMatchAliasName`/`ParseFieldMatchAliasName` (a per-NODE deferred-resolution
  alias, `"fieldmatch#<field>#<node>#<value>"`, mirroring the existing
  `ConvertToVariables`-then-`_Handle*`-expansion pattern every other match primitive uses,
  except node-scoped since the same field=value condition at two different nodes is
  genuinely two different conditions); `kripke.py::_HandleRule`'s new `FieldMatchFilter`
  branch (groups same-field values into an OR, different fields into an AND, same
  discipline as the existing Vlan/State filters — and routes even a LONE `<fieldmatch>`
  through the multi-element Gamma path instead of the single-element shortcut, since that
  shortcut's dispatch has no node-key parameter to build a node-scoped alias with);
  `Instantiator._HandleFieldMatches` (the new build-time expansion pass, wired into
  `InstantiateBase`'s existing `_Handle*` loop, resolving a `fieldmatch` alias against the
  SAME per-node bit-vector `_CreateMutationConstraints` already threads through — so match
  and rewrite always agree on what "the value at this node" means; raises rather than
  silently leaving an unresolved fieldmatch as a free variable if its field isn't declared
  in `MutableFields`, the same silent-blowup class item 6-14's bugs all were). Mechanism
  correctness follows directly from what Stage A already proved: `_CreateMutationConstraints`
  defines `field@V` as "the value observed once arrived at V, via whichever edge fired", and
  a node's own Gamma already gates its own outgoing transition — so `fieldmatch` inside V's
  Gamma checking `field@V==value` is exactly the admission semantic needed, no new machinery
  beyond the alias/dispatch above.

  Test-first (`ad6/test/core/instantiatortest.py::testFieldMatchGatesOnMutatedSSAValue`,
  wired into `InstantiatorSuite`; confirmed failing via `git stash` on the 4 core/xml files
  before landing): three entries rewrite `vlan` to 5, 6, 7 on their way into a SHARED
  admission gate whose Gamma is `fieldmatch(vlan,5) OR fieldmatch(vlan,7)`. vlan=5/7 (the
  admitted set) reach the shared sink; vlan=6 does not — even though the only structural
  difference between the three paths is which value the UPSTREAM rewrite chose, proving the
  match reads the live per-node SSA value flowing in, not a stale/global alias (which
  couldn't even express this: one global `vlan` variable can't hold 5, 6 AND 7 at once).
  **No regression**: `ad6 make test` (10 suites, `InstantiatorSuite` now 20 tests) and the
  real fave-side ad6 tests (`test_ad6_wl_ifi(.py/_stateful.py)`,
  `test_ad6_adapter_lpm_prio.py`, `test_ad6_adapter_multi_device_acl.py`,
  `test_ad6_wl_stanford_plain.py` — 33/33) green. Full write-up: `ad6/FAVE_CHANGES.md` §21.
  **Not yet done**: B2 (wiring real Stanford VLAN-admission/rewrite data through this —
  `Ad6Adapter._capture_mid_rewrite`/`_capture_out_rewrite`/`_capture_in_admission`,
  `favemodel.py` calling `InstantiateBase(..., MutableFields=...)` and emitting
  `fieldmatch` on admission rules) and B3 (the actual N=2/3/5/16 tractability measurement) —
  reported here before proceeding, same incremental-checkpoint pacing as B0/B1. **B3's
  wall-clock numbers will only be trustworthy on the bare-metal environment (existing
  cross-cutting guardrail) — this session's environment is yolobox (sandboxed), confirmed
  via the `yolobox` skill, so any timing taken here would not be the tractability verdict,
  only a build-error smoke check.**

  **B0 — plain translator, N=2 slice (`bbra_rtr,rozb_rtr`), DONE 2026-08-24, GO.** No
  wl_stanford↔ad6 translator existed; built one reusing `fave/apkeep/adapter.py`'s own
  proven Stanford translator as a template (ported algorithms, not imported — ad6 and
  APKeep deliberately never share process/imports). wl_stanford's devices are `SwitchModel`s
  named `in.<router>`/`mid.<router>`/`out.<router>`, each with one table `"<device>.1"` —
  already matched `Ad6Adapter.add_rules`'s existing dispatch, so only new stage-keyed
  handling (`model.node.split('.',1)[0]` ∈ `{in,mid,out}`, APKeep's own dispatch key) was
  needed. New: `Ad6Adapter._capture_in_admit`/`_capture_out_perm`/`_collapse_out_stage`
  (ports of APKeep's identically-named functions — per-physical-port dead-ingress admission,
  ignoring VLAN entirely for B0; `out.*`'s port-permutation stage collapsed into direct
  `mid.X`↔neighbour edges, since ad6's dst-based table has no in-port condition to key an
  `out.*` table on); `favemodel.py::_gate_dead_ingress` (drops a topology edge into an
  unadmitted port, called inside `wire_edges`).

  **Two real bugs found and fixed, both independent of VLAN fidelity — would have bitten
  the already-in-scope plain target too:**
  - **Multi-port (ECMP) forwards silently truncated to one port.** `_out_port` (singular)
    kept only `action.ports[0]`; real Stanford `mid.*` data genuinely has multi-port routes
    (one `/23` forwarding to 15 ports at once). Fixed with a plural `_out_ports` +
    `_add_fwd_route` (one IR entry carrying the WHOLE port list, deduped). Critically, this
    is **not** "loop and emit one rule per port": ad6's table evaluation is sequential
    first-match (`KripkeUtils._HandleRule`'s fallthrough discipline), so N separate rules
    sharing one dst condition would let only the FIRST ever fire, silently dropping the
    other N-1 ports' reachability. Fixed instead with `favemodel.py::wire_fanout`: a
    multi-port route jumps to one dedicated `"<rule-key>_fanout"` node, wired to every
    egress interface via several `Kripke.Put` calls — the same many-to-one "no condition to
    check, just connect" idiom `wire_edges` already uses, giving genuine OR/multipath
    semantics for free (`Kripke._FTransitions[key]` is already a list). A genuine dst-only
    blackhole (e.g. `224.0.0.0/3`, no forward action at all) also needed modelling —
    previously silently dropped (harmless for wl_ifi, never exercised there) — now an
    explicit jump to `DROP_KEY`, with the same soundness guard `apkeep/adapter.py` uses
    (only model as a drop when the match is genuinely dst(+vlan)-only).
  - **A probe with more than one real topology attachment silently checked only the FIRST
    one — not found by design, found by triage of a real UNSAT.** The N=2 differential's
    first run was UNSOUND: ad6 dropped `rozb_rtr→bbra_rtr`, which NetPlumber reaches. Hop-by-
    hop tracing (forcing a concrete, hand-picked witness destination — `10.240.0.0/12`,
    confirmed by direct IR inspection to be outside every one of rozb's own specific routes
    and covered by one of bbra's, so it must fall to rozb's default route toward bbra) showed
    EVERY intermediate hop reachable, including the exact `mid.bbra_rtr` egress port the
    witness address routes to — yet the full query still came back UNSAT. Root cause:
    `_attachment` (singular) resolved a probe to only the FIRST topology edge it's wired to;
    `probe.bbra_rtr` genuinely has 48 real attachment points in the N=2 slice alone (every
    access-facing `mid.X` egress port collapsed from its own `out.X` stage funnels into one
    probe), and the query was checking reachability of one arbitrary one of them while the
    witness address correctly routed to a *different* one. wl_ifi/wl_up probes only ever
    have exactly one attachment, so this was never exercised before. Fixed: new
    `_attachments` (plural, `_attachment` now a thin single-result wrapper over it),
    `wire_probe_fanout` (mirrors `wire_fanout`'s fanout idiom in the other direction — many
    real attachments feeding one dedicated aggregate node), and `query_destination_key`
    changed to take the probe's own name (not a pre-resolved device/port) so it can decide
    internally whether to use the fanout node or resolve directly — single-attachment probes
    (every other benchmark) are completely unaffected, zero added Kripke nodes.

  **Result: GO.** `fave/test/test_ad6_wl_stanford_plain.py` — 9 unit tests (fake
  `Rule`/`RuleField`/`Forward` objects, confirmed failing pre-fix via `git stash` on the two
  adapter/favemodel files) plus a structural + differential test on the real N=2 induced
  slice (reusing `fave/bench/apkeep_convergence.py`'s own `_filter_model`/`_write_model`/
  `_emit_worker` machinery for a live NetPlumber diff, not a recorded snapshot, mirroring
  `test_apkeep_stanford.py`'s own discipline): `out.*` correctly collapses to 4 devices for
  this slice, and ad6 now agrees EXACTLY with NetPlumber (0 over-approximation, 0
  under-approximation) on the induced 2-router subnetwork. No regression: `ad6 make test`
  (10 suites) and every existing fave-side ad6 test (16/16, including wl_ifi/wl_up) green.
  (Environment note: this session's sandbox was also missing `liblog4cxx.so.15`, needed for
  `libnetplumber`'s own `.so` to import at all — a recurrence of the same
  `[[env-integration-tier-deps]]` container-reset pattern hit earlier this session for
  `bison`/`flex`/`m4`/`clasp`/`minisat`; restored via `apt-get install liblog4cxx-dev`.)

  **Not yet done**: B1 (scale to all 16 routers, live diff against the 165-pair oracle) and
  everything from Stage A2 onward (VLAN fidelity, the tractability measurement) — per the
  user's explicit incremental-checkpoint pacing, reported here before proceeding.

  **B1 — scale to 16 routers, DONE 2026-08-24, but STOP: a genuine ad6 CORE soundness gap
  found, orthogonal to VLAN fidelity, gates everything downstream.** `fave/test/
  test_ad6_wl_stanford.py` mirrors `test_apkeep_stanford.py` exactly (full 16-router model,
  live NetPlumber worker diff, not a recorded snapshot). First run: 0 under-approximation
  (ad6 never drops a real NetPlumber-reachable pair) but a wide over-approximation, matching
  Stanford's well-known **5 dead-port sources** signature exactly
  (`bbrb_rtr,boza_rtr,goza_rtr,roza_rtr,yozb_rtr` — `[[stanford-forwarding-overapprox]]`)
  appearing as a spurious source against almost every probe.

  **Real bug #1, found and fixed: a generator's own attachment bypasses dead-port admission
  entirely.** `_gen_firewall` resolves a generator's attachment via `_attachment`/
  `entry_key` directly — never touching `ir["edges"]`/`wire_edges`, so B0's
  `_gate_dead_ingress` (which only filters device-to-device topology edges) never sees a
  generator's own edge at all. B0's N=2 slice (`bbra_rtr,rozb_rtr`) contains none of the 5
  known dead-port routers, so this was never exercised there. **Fixed:** new `_is_admitted`
  helper shared by `_gate_dead_ingress` and `_gen_firewall` (a dead-port generator now jumps
  straight to `DROP_KEY`); test-first in `ad6/test/parser/favemodeltest.py::
  GenFirewallDeadPortGateTest`, confirmed failing via `git stash` before landing. This fix
  is real, correct, and kept — but **the exact same over-approximation persisted, byte-for-
  byte identical, after this fix**, revealing a second, deeper cause.

  **Real finding #2, NOT a translator bug, NOT fixed — a pre-existing ad6 CORE limitation:
  `Instantiator.InstantiateEndToEnd`'s reachability query is unsound for any topology
  containing a cycle.** Root-caused by direct experiment, not assumption: with nothing
  forced at all (no source, no init), `probe.bbra_rtr`'s own destination key was already
  SAT — i.e. some self-consistent assignment satisfies "packet arrived" with zero real
  origin. Reproduced in a **minimal, fully isolated repro using stock `GenUtils`/
  `Instantiator` primitives only** (zero Stage 0/A/§5.4-Stage-B/Stanford-specific code
  involved) — pinned as `ad6/test/core/instantiatortest.py::
  testCycleReachabilityIsUnsoundWithoutRealOrigin`: a bare 3-node cycle `A->B->C->A` (no
  node marked INIT) plus a genuine, separate generator `entry` that only ever jumps to its
  own unrelated sink — `InstantiateEndToEnd(kripke, encoding, 'entry', 'A')` returns **SAT**,
  i.e. `entry` "reaches" a cycle it has no real connection to whatsoever.

  **Mechanism:** `Instantiator._ConvertNodesToImplications` builds only one-directional,
  purely LOCAL implications per edge (`transition -> (my_gamma AND some-predecessor-edge-
  fired)`) — a textbook SAT-encoded-reachability pitfall: a closed loop of such implications
  is a self-consistent fixed point the solver can satisfy by setting every edge in the loop
  true simultaneously, with no requirement that the loop is ever entered from a genuinely-
  fired INIT. `InstantiateEndToEnd`'s two disjunctions (source's own edge fired; destination's
  own arrival fired) are asserted as **independent** top-level conjuncts, not as one connected
  path constraint, so a destination inside (or reachable from) such a floating loop is
  trivially "reachable" from **any** forced source, real connection or none. `Instantiator.
  InstantiateCycle`/`_CreateCycle` already exists as a distinct ad6 feature for detecting a
  cycle reachable from init — confirming cycles were a recognized concern in ad6's original
  design, but never integrated into reachability's own soundness. Consistent with ad6's 2014
  design target (one firewall's own rule-chain, always acyclic by construction — a table's
  fallthrough/jump structure cannot loop back on itself): wl_ifi/wl_up's topologies happen to
  be acyclic too, so this was never exercised before. Stanford's real backbone genuinely has
  redundant/looped inter-router links — explaining exactly why B0's tiny 2-router slice
  (no cycle between just `bbra_rtr`/`rozb_rtr`) passed cleanly while B1's full-scale
  differential does not.

  **This is orthogonal to VLAN fidelity and gates the PLAIN target too** — it is not a Stage
  A2/B2/B3 concern, it is more fundamental than anything the original plan anticipated. A
  real fix is genuine core surgery (e.g. a rank/distance variable enforcing strict progress
  along a real path, the standard technique for this class of pitfall) — comparable in scope
  to Stage A's own SSA work, deliberately **not attempted without discussing with Claas
  first**, mirroring the wl_up NO-GO discipline: a significant architectural finding is a
  decision point, not something to patch around unprompted. Open options, not yet decided:
  (a) attempt the core fix, its own gated GO/NO-GO stage; (b) NO-GO on exact-match Stanford/
  i2 reachability via ad6 (mirrors wl_up's precedent), report the finding and redirect; (c)
  some narrower mitigation not yet identified. **No regression**: `ad6 make test` (10 suites,
  including the new `testCycleReachabilityIsUnsoundWithoutRealOrigin` characterization) and
  every pre-existing fave-side ad6 test (27/27 — wl_ifi/wl_ifi_stateful/wl_up/lpm_prio/
  multi_device_acl/B0's own wl_stanford_plain) stay green. `fave/test/test_ad6_wl_stanford.py`
  itself (new, B1's own test) has its structural assertion passing and its differential
  assertion **failing as expected** — it documents the open gap, not a regression, until
  resolved one way or the other.

  **B1 follow-up (2026-08-25): the cycle-soundness gap is FIXED, correctly and test-first —
  but the resulting exact wl_stanford differential is a NO-GO on wall-clock grounds, not
  correctness.** Full attempt-by-attempt narrative: `ad6/FAVE_CHANGES.md` §20. Summary:

  - **Claas's own proposal** (reuse `_CreateCycle`, negated, baked into the base model) was
    assessed and empirically disproven first: unnegated it kills every real terminal node
    (any edge into a 0-outgoing node is unconditionally forbidden); negated it reduces
    algebraically to "some fired edge leads to a dead end" — true of virtually every real
    witness, spurious or not, so it has zero discriminating power — and mechanically produces
    a disjunction-of-conjunctions `SATUtils.ConvertToCNF` can't consume without genuine
    Tseitin machinery it doesn't have. The right *direction* (reuse the fired-transition
    graph), wrong exact form (a single static clause can't express "the concrete witness the
    solver picked must be acyclic" — that's a property of a model, not the symbolic formula).
  - **CEGAR** (`Instantiator.SolveGroundedEndToEnd`: solve, walk the concrete witness, block
    and re-solve if ungrounded) is correct, test-first, but combinatorially intractable on
    real data: 117 iterations / ~45s for ONE query on a 3-router slice. A refinement (shrink
    the blocking clause to just Destination's own backward-closure) helped ~0%, because that
    closure turned out to be ~100% of the fired transitions on real FIB-table-heavy data.
  - **ROOT OF THE WHOLE PROBLEM, established 2026-09-11 by reading the source paper
    (`secrypt15.pdf`, Lorenz & Schnor, SECRYPT'15): THE GAP IS IN THE PUBLISHED FORMALISM,
    NOT IN ad6's IMPLEMENTATION OF IT.** The paper's Kripke encoding is

        trans(C) = forall (t,c,u) in delta. ( y(t,c,u) -> ( (c <-> trans(t, gamma(t)))
                                             /\ (trans(t,init) \/ exists (s,b,t) in delta. y(s,b,t)) ) )

    and `Instantiator._ConvertNodesToImplications` emits exactly that, term for term
    (`Implicant` = y(t,c,u); `Equality` = (c <-> gamma(t)); `Disjunction` = the
    exists-clause over `IterBTransitions`, with the INIT case as `constant(True)`).
    **Nothing was lost in implementation.** The flawed step is the paper's own following
    sentence: *"A solution for trans(C) represents a path through the model starting at an
    initial state."* It does not. The support term `exists (s,b,t) in delta. y(s,b,t)` is
    purely LOCAL -- "some incoming transition variable is true" -- with no requirement that
    the predecessor itself be grounded, so a cycle discharges it self-referentially. Same
    for `reach_constraint(C,t) = exists (s,b,t) in delta. y(s,b,t) \/ trans(t,init)`, which
    the paper describes as enforcing "the existence of an incoming transition": a loop
    containing `t` provides one.

    **Minimal counterexample** (nodes A=INIT, P, B, C, D, E; all gammas true; edges
    A->P, B->C, C->D, D->B, C->E; note `pred(B) = {D}` only, A does not feed B):

        t_AP -> True     (A is INIT)      t_BC -> t_DB      t_CD -> t_BC
        t_CE -> t_BC                      t_DB -> t_CD

    The end-to-end query A->E asserts `t_AP /\ t_CE`. Setting all five edge variables true
    satisfies every implication -- `t_CE -> t_BC -> t_DB -> t_CD -> t_BC` closes on itself
    -- yet **A cannot reach E**: A goes only to P, and E is fed by a cycle A never touches.
    The source-side conjunct is discharged by ANY out-edge of A (here the dead end), the
    destination-side conjunct by ANY support chain (here a cyclic one), and nothing ties the
    two together. Connectivity is a TRANSITIVE property and no amount of per-node local
    implication expresses it.

    **The paper contains its own corroboration.** Its cyclicity anomaly adds
    `forall (s,b,t) in delta. (y(s,b,t) -> exists (t,c,u) in delta. y(t,c,u))` and explains:
    *"The first part of the constraint ensures that every transition on the path has a
    successor which means that they form a loop."* The cycle DETECTOR is built on the fact
    that `trans(C)` admits loop-shaped solutions -- so the formalism itself establishes that
    those models exist, and `reach_constraint` adds nothing that excludes a loop which
    happens to contain the target.

    **Why it was sound in the paper's own domain, and only broke here.** SECRYPT'15 scopes
    reachability to RULE reachability inside a SINGLE firewall ("is this rule ever hit?"),
    where the transition graph is a rule chain -- effectively a DAG, no cycles to exploit.
    The gap is latent there, not wrong. It becomes live only when the construction is LIFTED
    to network end-to-end reachability with redundant links: wl_up never exposed it, while
    i2's Kripke graph is one SCC over 99.3% of nodes. Note also that the end-to-end form is
    NOT in the paper at all -- `reach_constraint` pins only the destination side, and
    `InstantiateEndToEnd`'s source-side disjunct is a FaVe-era addition. That addition is
    what makes "both endpoints pinned, therefore a path between them" feel inevitable, and
    it is exactly the step that does not follow.

    **One deliberate deviation, in the SAFE direction:** the paper has
    `trans(t,init) \/ exists...`, so an INIT node WITH predecessors would still get the init
    disjunct; the code takes the INIT branch only when there are ZERO predecessors (see
    `favemodel.gen_entry_key`'s docstring). Strictly fewer models than the paper, so it
    cannot cause false reachability.

    **CONSEQUENCE:** the rank encoding is not compensating for something ad6 lost -- it is
    REPAIRING A GAP IN THE PUBLISHED FORMALISM under a domain lift. That reframes its 84%-of-
    variables cost as the price of a necessary correction, and makes OPTIMISING it the right
    avenue rather than hunting for a simpler mechanism that was never there.
  - **OPTIONS FOR A CHEAPER GROUNDING CONSTRAINT (surveyed 2026-09-11, owner request).**
    First, the negative result, so nobody hunts for something that does not exist:
    **connectivity is a TRANSITIVE property and no purely local constraint expresses it.**
    The sound options are essentially four -- a level/rank witness, a FLOW witness,
    external propagation, or lazy loop formulas. Ranked by expected value here:

    1. **Single-unit s-t FLOW (recommended, being built behind a flag).** Add a flow
       variable `f_e` per edge with `f_e -> y_e`; the source emits exactly one unit and
       accepts none, the destination accepts exactly one and emits none, and every other
       node has at-most-one in-flow, at-most-one out-flow, and `(some in) <-> (some out)`.
       In-degree and out-degree both <= 1 makes the flow subgraph a disjoint union of
       simple paths and cycles; the source (in-deg 0, out-deg 1) therefore starts a path
       that cannot branch and can only terminate where out-deg 0 is permitted, i.e. at the
       destination. **Disjoint cycles may still carry flow and are harmless** -- the path
       component is a genuine grounded s->t walk over true edges, which is exactly the
       soundness `trans(C)` lacks. Complete too: any real path can carry the unit.
       BOTH the at-most-one and the conservation halves are load-bearing -- conservation
       alone still admits "source's flow runs into cycle A while the destination is fed by
       a disjoint cycle B", the same disconnection failure as the rank-free encoding.
       Estimated cost on i2: ~320k variables and ~1.2M clauses against the rank encoding's
       measured 6,121,649 and 14,253,423 -- roughly 19x and 12x. **Arithmetic, not
       measurement, until the flag lands.** It REPLACES the rank block rather than adding
       to it. The catch: it is PER-QUERY (s and t appear in it), so it cannot live in the
       shared base encoding and must require `--fresh-per-query`.
    2. **External propagator (IPASIR-UP) -- available in this PySAT build.** Verified:
       `Cadical195` exposes `connect_propagator` ("Attach an external propagator through
       the IPASIR-UP interface"), `observe` and `enable_propagator`. This is the
       SAT-modulo-acyclicity route (Gebser/Janhunen/Rintanen): ZERO CNF cost, with an
       incremental union-find/DFS deciding groundedness inside the propagator. Highest
       ceiling and most work; the real risk is Python callback overhead per assignment,
       mitigated by `observe`-ing only the ~125k SCC-qualifying edge variables.
    3. **Lazy loop formulas -- CEGAR done correctly.** The earlier CEGAR failed for a
       DIAGNOSED reason, not a fundamental one: `_BlockWitness` negated every fired
       transition (hyper-specific to one model) and `_BackwardSupport` shrank that to
       1,066 of 1,067 edges (no help). The principled lemma is different in kind: for an
       unfounded set U, add `OR over edges (s,t) with t in U and s not in U of y_(s,t)` --
       "to use any of this, something must enter it from outside" -- which blocks the whole
       loop FAMILY at once instead of one model. The witness machinery to compute U already
       exists and builds its index in 0.26 s. Worst-case number of loop formulas is
       exponential; in practice for reachability it is usually small.
    4. **Shrinking `Width` below the SCC bound** only ever REMOVES models, so it is sound
       as a reachability PROVER (SAT means genuinely reachable) and useless as a refuter --
       which is the direction wl_i2 currently needs.

    **A trap worth naming, because it is the obvious idea:** re-encoding rank in
    UNARY/ORDER form to get a trivial comparator does not work here. Order encoding needs
    one variable per LEVEL, and the levels must cover the longest chain of true edges --
    the real i2 witness path was 395 nodes -- so ~500 levels x 78,524 nodes is far worse
    than the 6.12M variables it would replace. The binary encoding is the right choice;
    what is expensive is the PER-EDGE comparator auxiliaries (measured: 48.8 variables and
    113.6 clauses per edge, over 125,468 edges).
  - **A static rank/distance encoding** (`Instantiator._CreateAcyclicConstraints`: a
    brand-new bounded "rank" field per node, `fired -> Rank(Target) > Rank(Node)` for every
    edge) is genuinely sound — no structural escape hatch, unlike `_CreateCycle`'s negation —
    proven via a PLAIN solve (no CEGAR at all) on the synthetic fixture. Found and fixed a
    real `SATUtils._ResolveConstants` limitation along the way (a nested-equality pattern
    silently produces malformed non-CNF output; fixed by switching to one-directional
    implications, the same safe shape `_ConvertNodesToImplications` already uses). But
    unscoped, building it for every edge measured ~425k extra clauses for 3 routers alone.
  - **SCC-scoping** (`Instantiator._ComputeSCCs`, Kosaraju's, iterative): only edges inside
    the same non-trivial strongly-connected component can ever be part of a cycle, by
    definition — correct, cut clauses ~43%, but far short of hoped-for order-of-magnitude:
    the non-trivial SCC covered **86% of nodes** even at 3-router scale, because any real
    redundant link back to a router pulls that router's ENTIRE fallthrough-chain table into
    one SCC. This is the *norm* for a resilience-engineered backbone, not a corner case.
  - **Shipped: a lazy/hybrid design** (`Instantiator.SolveAcyclicEndToEnd`, Claas's own
    direction): plain solve first, escalate to the (SCC-scoped) rank constraints — built
    once, cached, reused — only when a witness is found ungrounded. Correct test-first
    (fast path never touches the expensive machinery; escalation builds once and is reused
    across queries, identity-checked; a `Stats` output distinguishes "this query escalated"
    from "the cache happens to be warm"). Verified **zero cost** for every acyclic benchmark
    (wl_ifi 289/289 fast-path, wl_up, wl_ifi_stateful, B0's N=2 slice — 27/27 fave-side tests
    green). `favemodel.instantiate_base` no longer bakes the rank constraints in; the one
    shared `fave_bridge.py` query call site now owns a `Cache` dict for the whole run.
  - **Real-scale result, measured, not projected**: with new progress instrumentation
    (`fave_bridge.py`'s `AD6_BRIDGE_PROGRESS`/`AD6_BRIDGE_PROGRESS_FILE` — added because none
    existed and `Ad6Adapter.check_compliance`'s `subprocess.run(..., stderr=PIPE)` makes
    stderr invisible until a possibly-many-hour subprocess already exited), the full
    256-query, 16-router differential was given a 6-hour budget. **It did not finish**:
    74/256 (28.9%) completed, 40 of those (54%) needed escalation at 7.7s–2,923s each
    (~99.4% of the 6-hour budget). No crashes, no malformed output — every completed query
    returned a clean, correct answer. **PRIMARY finding (directly observed, high
    confidence): the differential does not complete within 6 hours.** A linear extrapolation
    of the observed rate suggests **~20–21 hours** for a full run — reported as a SECONDARY,
    explicitly LOWER-confidence figure, since it's an extrapolation from a 29%-complete
    sample, not an independent measurement.
  - **Decision (Claas): the 6-hour non-completion itself is the reportable NO-GO result** —
    "revealing the inability to scale is a genuine outcome" for a generic-vs-specialized
    tool comparison. Not re-run to actual completion. `fave/test/test_ad6_wl_stanford.py`'s
    differential test is now skipped by default (`AD6_STANFORD_FULL_DIFFERENTIAL=1` to opt
    in, plus a generous external timeout — a deliberately separate env var from
    `FAVE_REQUIRE_BACKENDS`, so CI's backend-required tier is never accidentally forced into
    a many-hour run).
  - **What's kept**: the correctness fix itself is real, sound, test-first, and is now ad6's
    production query path for every benchmark sharing this bridge — the underlying
    reachability-unsoundness-on-cycles bug is fixed, generically, for any topology, on the
    `InstantiateEndToEnd`/`SolveAcyclicEndToEnd` primitive `fave_bridge.py` actually uses —
    even though the resulting EXACT full Stanford differential is impractically slow at
    this scale. **Scope caveat (found by a parallel session, `AD6_ENCODING_PLAN.md` §2.4,
    working the paper's own formalization independently of this session's work):** the SAME
    grounding gap is confirmed to also affect ad6's own native `InstantiateReach`/
    `InstantiateShadow` primitives (structurally suspected, not confirmed, in
    `InstantiateCross`) — none of which this fix touches; `InstantiateCycle` is confirmed
    safe. No regression: `ad6 make test` (10 suites, 6 new tests this round) and every
    pre-existing fave-side ad6 test (27/27) stay green.
  - **Second scope caveat, NEW 2026-08-25, still open, not yet reported anywhere else
    (`AD6_ENCODING_PLAN.md` §2.5):** a DISTINCT bug, opposite failure direction (spurious
    UNSAT, not spurious SAT) and a different mechanism (an implementation bug in
    `Instantiator._ConvertNodesToImplications`'s translation of the paper's `trans(C)`
    disjunction, not a gap in the formula itself) — confirmed still present in current
    `ad6/src/core/instantiator.py:556-608`, untouched by this fix. The `XMLUtils.INIT in
    Node.Props` check (line 584) is only ever reached when a node has **zero** incoming
    edges; the moment a node has any real incoming edge, the code wrongly drops the "OR
    init" disjunct and requires one of those incoming edges to fire instead — even when the
    node genuinely is INIT. Effect: an init/entry node that also sits on a genuine incoming
    path (plausible on a real backbone with redundant links back to an entry router — the
    Stanford topology's own shape) can report **false UNSAT** for a query that is actually,
    structurally reachable. Minimal isolated repro:
    `ad6_encoding_bench/bug_init_node_incoming_edge.py`. Not yet fixed; likely a small,
    targeted change (consult the INIT prop unconditionally, not only in the
    zero-predecessor fallback branch) but not attempted without discussion first, same
    discipline as the rest of this section.
  - **Third item, NEW 2026-08-27, a robustness bug, not a soundness gap
    (`AD6_ENCODING_PLAN.md` §3.10) — FIXED 2026-08-27:** while prototyping the
    incremental lever (§6, below) against this exact real 16-router topology,
    `Instantiator.SolveAcyclicEndToEnd`'s escalation path (the SAME code this fix ships)
    **silently crashed — no exception, no traceback, the process just vanished** —
    root-caused to a C-stack overflow: `sys.setrecursionlimit(10**6)` (set at import in
    both `main.py` and `fave_bridge.py`) lets a deep recursive operation over the
    ~450k-clause rank-constrained instance run past the shell's default 8MB `ulimit -s`,
    segfaulting instead of raising a Python exception. `fave_bridge.py` runs as a
    subprocess inheriting its parent's ulimits, so **any real cyclic-topology run (this
    Stanford differential included) is at risk of this exact silent crash** if the parent
    process's stack limit is at the OS default. **Fixed**: `ad6/src/bigstack.py`
    (`run_with_big_stack`) runs the entry point's `main()` in a new thread with an
    explicit 256MB stack (portable — honoured by Python's threading module independent
    of the launching shell's own ulimit), wired into `fave_bridge.py`'s `__main__` block
    (the real production entry point; `main.py`'s demo CLI left unchanged — lower-value,
    would need a larger refactor of its inline `__main__` block, not attempted here).
    Test-first: `ad6/test/core/instantiatortest.py::testRunWithBigStackIsATransparentWrapper`
    (confirmed failing pre-fix via a temporary module removal), confirms the wrapper is
    behavior-preserving (same return value, same raised exception) for the ordinary case;
    the exact crash itself was NOT reproduced as a fast synthetic unit test (calibration
    attempts at a minimal cyclic topology large enough did not finish in reasonable
    time — CEGAR's own cost dominates before the stack does, at any scale small enough to
    stay a fast test) — the fix's justification is the real A/B-tested Stanford run
    itself. No regression: `ad6 make test` (10 suites, 18 instantiator tests, up from 17)
    and a real `fave_bridge.py` end-to-end smoke test via `Ad6Adapter`/`InProcessFaVe`
    stay green.
  - **Fourth item, NEW 2026-08-27 — the wall-clock NO-GO is RESOLVED
    (`AD6_ENCODING_PLAN.md` §3.10), for the primitive tested, confirmed against the live
    NetPlumber oracle, not just ad6's own prior answers:** baking the SAME SCC-scoped rank
    constraints this fix uses into a **persistent** incremental solver's base ONCE, then
    answering all 256 real Stanford source→probe pairs as single assumption-checks (no
    CEGAR needed — the rank encoding is sound by construction), completed the **entire
    real 256-pair all-pairs matrix in ~16-23 minutes** (measured twice: 971.09s and,
    under heavier concurrent load, 1361.07s) — vs. this section's own measured
    6-hour/28.9%-complete result and ~20-21h extrapolation for a full run. Directly
    illustrated on the two specific pairs already known to be expensive under ad6-real
    (2164.64s and 2259.70s each): the SAME pairs took ~102.7s and ~0.15s respectively here
    — the second nearly free, because it reused clauses learned solving the first.
    **Closed the loop**: fed all 256 answers through the SAME live-NetPlumber
    oracle-comparison `test_ad6_wl_stanford.py` itself uses (not `reachable.json`, not a
    recorded snapshot) — **EXACT MATCH, 0 diffs across all 16 roles**
    (`ad6_encoding_bench/axis8d_stanford_netplumber_diff.py`). **Since applied to
    production** (see §6, below): `ad6/fave_bridge.py` now uses this architecture for
    every query, not just Stanford's.

- **5.5 Internet2 (i2) — staged plan, C0-C4, GO/NO-GO gated at each stage (planned
  2026-08-27, following Stanford's §5.4 PROVISIONAL GO).** i2 is the other benchmark §5.2
  named for the "IPv4 forwarding at scale" feasibility question, but it is NOT "Stanford but
  bigger" — a read-only research pass (fork investigation, 2026-08-27) found its problem
  shape is materially different, which is why it gets its own staged plan rather than
  reusing §5.4's stages directly.

  **What's different from Stanford:**
  - **No mid stage.** i2 decomposes each of its 9 routers into `in.X`/`out.X` only (18
    devices total; `bench/wl_i2/i2-json/config.json`'s `table_types: ["in","out"]`,
    corroborated by a comment in `bench/np_preparation.py` ~line 197). VLAN is not a
    multi-hop "stays pinned along a path" problem the way Stanford's admission+rewrite was
    — it is a same-hop joint constraint: `out.X` rewrites VLAN as a function of destination
    (`rw=vlan:M` in `routes.json` entries), `in.X` independently admits a VLAN set at
    ingress. `apkeep/adapter.py` already has a distinct, i2-specific faithful path for
    exactly this shape (`_i2_faithful`/`_build_i2_faithful`, ~adapter.py:326,1284-1334) —
    structurally unlike Stanford's `_capture_mid_rewrite`/`_capture_out_reset`/
    `_capture_in_admission` trio we ported in §5.4 Stage B2.
  - **The scale risk is route-table size, not VLAN.** `bench/wl_i2/i2-json/routes.json` has
    77,841 entries vs Stanford's 8,792 — this, not device/router count (i2 is smaller: 9
    routers/18 devices vs Stanford's 16/32), is the actual stress case §5.2 was written for.
  - **No router-subsetting tool exists for i2** the way `apkeep_convergence._filter_model`
    gave Stanford its N=2/3/5/16 induced-slice protocol —
    `bench/faithful_bdd_measure.py` explicitly raises `SystemExit("i2 router subsetting is
    not implemented yet")` for `--bench i2`. §5.4's N-scaling approach does not carry over
    directly.
  - **APKeep's own faithful-VLAN build for i2 has never completed.** Both captured
    profiles in `bench/wl_i2/eval/` (`faithful_bdd_capped_profile.jsonl`, 170 samples;
    `faithful_bdd_uncapped_profile.jsonl`, 109 samples) are still `"phase":"running"` after
    28 and 54 minutes respectively, stalled at 52-53% of 154,920 rules with the BDD atomic-
    predicate count (`ap_num`) still climbing past 21,012 — `bench/wl_i2/eval/
    faithful_sizing.py`'s own docstring predicts why: a joint (dst × VLAN) BDD atom space is
    a cross-product (`Pi ~= dst_atoms x VLAN_classes`) vs. an NDD-style per-field sum
    (`Sigma = dst_atoms + VLAN_classes`). **There is no working faithful-i2 reference to
    replicate** — unlike Stanford, where APKeep's own faithful numbers (despite the open
    N=3/N=5 discrepancy) at least completed and gave a target to match.
  - **Rule ingestion is NOT a new problem.** i2's `routes.json` tuples
    (`[node, priority?, priority?, match_list, rewrite_list, out_ports]`) already flow
    through the same generic `Rule`/`Forward`/`Rewrite`/`Match` objects both
    `apkeep/adapter.py` and `fave/ad6/adapter.py`'s `add_rules()` consume for Stanford — no
    new parsing/translation layer is needed structurally. Confirmed: no `test_ad6*i2*` test
    exists yet, and today's `Ad6Adapter(faithful_vlan=True)` would silently no-op i2's
    faithful capture (its `mid`/`out` stage-name checks just never match i2's `in.X`/
    `out.X`-only devices) rather than error — plain mode (`faithful_vlan=False`) is
    structurally ready to try.

  **Stages (each gates the next; no stage attempted before the previous is GO):**
  - **C0 — Ingestion sanity.** Build i2 through `Ad6Adapter(faithful_vlan=False)` via
    `InProcessFaVe`, confirm the Kripke model builds without crashing, sanity-check
    device/rule counts land near expectation (18 devices, tens of thousands of encoded
    rules from 77,841 routes). Cheap gatekeeper, mirrors §5.4 Stage A's own "does this even
    build" discipline before investing further.
  - **C1 — Plain-mode correctness gate.** Differential vs `bench/wl_i2/reachable.json` (the
    SAME oracle `test/test_apkeep_i2.py` already validates FaVe+APKeep against — full mesh,
    all 9x8=72 source-probe pairs reachable, 0 missing/0 extra required). Same soundness
    discipline as wl_tum/wl_ifi/wl_stanford's own B1 gates: no measurement is trusted before
    an exact oracle match.
  - **C2 — Plain-mode tractability at full scale.** Generalize `bench/ad6_faithful_measure.py`'s
    instrumentation (build/DIMACS/query time split, clause count, peak RSS) to i2's full
    77,841-route model in plain mode — the actual LPM/dst-FIB stress test. Since no
    router-subsetting tool exists for i2 (see above), run full-scale directly first (device
    count is small, so this is tractable to attempt without a small-n on-ramp); only build a
    route-sampling fallback harness for a scaling curve if the full-scale run proves
    intractable. Same yolobox-numbers-are-directional-only guardrail as §5.4 B3 applies.
  - **C3 — Faithful-VLAN necessity check (GO/NO-GO).** Before attempting any new joint
    dst×VLAN encoding, check whether plain mode (VLAN-admission-blind) already reproduces
    the C1 oracle exactly. If so — and C1 already passing on plain mode is itself evidence
    of this — that means i2's VLANs may not gate reachability the way Stanford's did, and
    faithful-VLAN modeling for i2 gets marked **out of scope** with this rationale
    documented, ending the spike at C3 rather than chasing a problem APKeep itself has not
    solved. If plain mode is found insufficient, proceed to C4.
    **CRITERION UNSOUND AS WRITTEN -- see "C3 REOPENED" and its WORKLOAD-PARITY
    companion (both 2026-09-09) immediately below. This gate cannot be answered with
    `reachable.json` at all: dropping the VLAN gate can only ADD reachability, and an
    all-reachable 72/72 mesh with zero expected-unreachable pairs has no power to detect
    over-approximation. C3 is not closable as a documentation decision, and C4 is not a
    contingency branch.**
  - **C4 — (conditional on C3 finding plain mode insufficient).** Scope a new, i2-shaped
    joint-constraint encoding: a single-hop `out.X` rewrite/`in.X` admission gate, reusing
    Stage A2's `fieldmatch` primitive (`ad6/src/xml/genutils.py:fieldmatch`,
    `ad6/src/core/instantiator.py:_HandleFieldMatches`) but WITHOUT §5.4's multi-hop SSA
    path-pinning machinery, since i2 has no mid-stage rewrite chain to track. Explicitly
    test, not assume, whether SAT's existential search sidesteps the (dst x VLAN)
    cross-product blowup stalling APKeep's BDD approach — SAT never needs to materialize an
    explicit joint predicate space the way BDD/NDD atom enumeration does, which could be a
    genuine comparative finding for §7's write-up rather than a risk to route around.

  **C3 REOPENED 2026-09-09 — its GO/NO-GO test is INVALID, and there is now
  counter-evidence. Planned experiment below (owner-approved).**

  C3 as written above gates faithful-VLAN work on "does plain mode already reproduce
  the C1 oracle exactly?" — and C1/C2 answered yes (72/72, `oracle_match: true`,
  `bench/wl_i2/eval/ad6_i2_*.json`). **That inference does not hold.** Plain mode is
  VLAN-admission-blind, i.e. it RELAXES a constraint, and relaxing a constraint can
  only ADD reachability. `bench/wl_i2/reachable.json` is a COMPLETE all-reachable
  mesh with zero expected-unreachable pairs (the same caveat already recorded in this
  document for the acyclic-safety question). So an all-reachable oracle scores any
  relaxed encoding at 100% **by construction**: plain mode reproducing it is
  guaranteed, not informative, and cannot license marking faithful VLAN out of scope.
  `bench/ad6_i2_measure.py:101` hardcodes `faithful_vlan=False` citing exactly this
  reasoning in its docstring; that comment needs correcting too.

  **Counter-evidence (2026-09-09).** FaVe+NetPlumber, run in-process through
  `NetPlumberLibAdapter` + `InProcessFaVe` on the same `i2-json` inputs
  `test_apkeep_i2` uses, reports **11 of the 72 pairs UNREACHABLE**: `chic` →
  `{hous, kans, losa, salt, seat}` and `atla`/`newy32aoa`/`wash` → `{salt, seat}`.
  A direct reading of `routes.json` (no engine) shows the router-level topology is
  fully connected AND a port-level walk over the real FIB with match fields IGNORED
  reaches all 72 — so those 11 are blocked by FIELD constraints, specifically the
  in-stage VLAN admission (390 `vlan=V` rules) x out-stage `rw=vlan:V` rewrite
  coupling, with probes existential on `vlan=0`. That is precisely the dimension
  plain mode drops. **NetPlumber has never been cross-checked on i2** (see
  [`TODO.md`](TODO.md) item 1s: `apkeep_vs_netplumber.py` measures time only;
  `test_backend_differential` is wl_ifi-only), so this is the first faithful signal
  on this workload, and it is unexplained in either direction.

  **Planned experiment — full faithful model, three queries (owner decision
  2026-09-09).** Deliberately NOT an induced sub-topology: a subset removes paths, so
  UNSAT on a subset would not prove unreachability in the full model, and the owner
  chose to avoid introducing that error potential before trying the real thing.
  Query set picked from the recorded Cadical195 per-query log
  (`ad6_i2_cadical195_lite_72pairs_complete_v2.json`, `query_log`):

  | query | ad6 plain | NetPlumber | role |
  |---|---:|---|---|
  | `source.hous → probe.salt` | 1.11 s (fastest of 72) | reachable | agreement control |
  | `source.chic → probe.salt` | 3.43 s | **unreachable** | discriminator |
  | `source.chic → probe.seat` | 4.50 s | **unreachable** | discriminator |

  Two of the eleven disagreement pairs are among ad6's five fastest plain queries, so
  the discriminating cases are also the cheap ones. Success criterion: do ad6-faithful
  and NetPlumber agree on all three? If ad6-faithful also returns unreachable for
  `chic → salt`/`chic → seat`, plain mode is insufficient for i2 → **C3 is NO-GO and
  C4 is on**. If ad6-faithful still says reachable, the disagreement localises to one
  of the two engines and needs root-causing before either is trusted.

  **Risks to hold in view when reading the result:**
  - **Recorded times are SAT times and are lower bounds at best.** If NetPlumber is
    right, the two discriminators flip to UNSAT under faithful VLAN, and proving UNSAT
    exhausts the search space rather than getting lucky — routinely orders of
    magnitude dearer. This workload has never exercised a genuine UNSAT on i2 (all 72
    recorded queries are `sat: true`), so per-query cost in that regime is unknown.
  - **The fixed cost is per-run, not per-query:** ~405 s (`build_s` 358 + acyclic 16 +
    dimacs 3.8 + lite_dimacs 19.2 + solver_load 8.2). Three queries therefore cost
    roughly 7 min + solving; cutting the query count buys time, never memory.
  - **Memory is the binding constraint.** Plain-mode `peak_rss_mb` is **13,432 MB**,
    and it is build/DIMACS-dominated, hence query-count-independent; the faithful
    encoding adds admission + rewrite constraints and will exceed it. The box is
    therefore being raised **16 GB → 20 GB** for this run (owner, 2026-09-09). Even
    so, headroom is thin — instrument RSS and expect the possibility of an OOM before
    the first query.
  - **Do not extrapolate full-set runtime from these three.** The recorded plain
    distribution is min 1.11 s / median 133 s / max 1688.8 s, a ~1500x spread, and
    this set is drawn deliberately from the fast tail.

  **Prerequisites** (tracked as checkboxes in [`TODO.md`](TODO.md) item 1s): a
  `faithful_vlan` switch on `bench/ad6_i2_measure.py` (currently hardcoded `False` at
  line 101) and an explicit pair-list selector (`--pair-filter` exists but only does
  self/exclude-self).

  **C4 PART 1 DONE 2026-09-09 -- the out-stage egress-VLAN rewrite is modelled.**
  `Ad6Adapter._capture_out_rewrite` + `_out_rw` + an `ir["out_rw"]` emission scoped to
  the devices surviving the out-stage collapse, consumed by
  `favemodel._build_device_table`'s rewrite lookup (now merging `mid_rw` and `out_rw`
  -- a device is only ever one stage). Built test-first at both layers and confirmed
  failing beforehand by A/B: `fave/test/test_ad6_wl_i2_faithful.py` (17 tests, capture
  + IR) and `ad6/test/parser/favemodeltest.py::FaithfulVlanOutRewriteWiringTest` (6
  tests, a REAL Kripke/CNF build+solve whose fixture varies the rewrite PER
  DESTINATION, so it exercises the joint (dst, VLAN) coupling rather than a per-device
  tag, with a VLAN-unconstrained source as i2 really has). Full writeup:
  `ad6/FAVE_CHANGES.md` §25.
  **Validated on the real model, IR build only:** all **77,451** rewrites captured
  across 9 devices (matching `routes.json` exactly), **0** failing to key onto a real
  route -- so the `(dst, egress_port)` join is exact at scale, the bug class that
  first hit `_fold_mid_rewrites` where every lookup missed silently. 41,200 rewrite to
  vlan 0. Plain-mode IR is unchanged (no `out_rw` key; `fwd_rules` identical at 77,460
  in both modes), so the recorded plain figures stay reproducible. `_capture_mid_rewrite`
  is confirmed inert on i2 (`mid_rw` empty, no mid stage) and `gen_vlan` empty.

  **C4 PART 2 DONE 2026-09-09 -- the probe untag is modelled, OPT-IN and DEFAULT OFF.**
  `Ad6Adapter(probe_untag=True)` + `_probe_vlan` capture in `add_probe` (read from the
  probe model's `test_fields`, NOT `filter_fields` -- verified by instrumenting a real
  replay: i2's probes carry `test_fields={'packet.ether.vlan': ['0']}` with
  `filter_fields` AND `match` both empty, so reading either would have captured nothing
  silently), `ir["probe_vlan"]`/`ir["probe_untag"]`, and
  `favemodel.probe_vlan_literals()` wired into `fave_bridge.py`'s per-query
  `extra_vars`. Enforced at QUERY time by forcing the destination node's own per-node
  SSA bits (`XMLUtils.ConvertFieldToVariables`), the same idiom `_seed_literals`/
  `_state_literals` use and the same shape as `apkeep/adapter.py`'s `target_vlan=`;
  a model-side gate is NOT an option, because a node existing only as a transition
  endpoint makes `_CreateMutationConstraints` raise `KeyError` on its own
  `Kripke.GetNode`. 22 new tests, all confirmed failing beforehand and A/B'd after;
  validated on the real model (all 9 probes at `vlan=0`, each resolving to its
  `probe_fanout_probe_<role>` aggregate -- every i2 probe has 18-36 attachments, so the
  aggregate node, not an interface, is what gets untagged). Full writeup:
  `ad6/FAVE_CHANGES.md` §26.

  **PROBE-UNTAG PARITY FINDING 2026-09-09 -- this is why the default is off, and it
  narrows what the 11-pair disagreement can be.** Implementing the untag surfaced that
  **neither comparison backend enforces this condition on i2**:
  - **NetPlumber computes it and discards it.** `netplumber/adapter.py:1009` builds the
    header space from `model.test_fields`, then two `XXX: deactivate using flow
    expressions due to possible memory explosion in net_plumber` guards route around
    it: with `test_fields` present and no `test_path`, `test_expr` becomes literally
    `{"type": "true"}` (line 1053), and `add_source_probe` is called with that plus a
    match vector built from `model.match` -- **empty** for every i2 probe. The header
    space never leaves Python.
    - **OWNER CORRECTION 2026-09-11 -- this is NOT a NetPlumber defect, and earlier
      wording here implying it weakens NetPlumber's verdicts is wrong.** The commented-out
      flow analysis is an ARTIFACT OF A DELIBERATE MODE CHANGE, not a workaround for a
      correctness problem: NetPlumber originally verified compliance by BACKWARD flow plus
      path-pattern matching, where an incoming flow could be filtered and its path
      analysed; the mode of operation was later changed to full flow-tree analysis, and
      the (then-unused) probe-side filtering was deactivated because certain flows proved
      prohibitively costly on reaching probe nodes. Accepting any flow at a probe is
      moreover the RIGHT semantics for this model: **probes are not part of the network,
      so no meaningful flow handling -- VLAN rewriting on an egress port, for instance --
      should happen there.** So "NetPlumber does not enforce the untag" remains true and
      is still the reason `probe_untag` defaults off for WORKLOAD PARITY; it is not
      evidence of a NetPlumber fault, and the 11-pair disagreement cannot be attributed
      to it.
  - **APKeep passes `None`.** `apkeep/adapter.py:1460` gates `tvlan` on
    `self._stanford and self._faithful_vlan`, so wl_stanford gets the untag and i2 does
    not -- even though `test_apkeep_ndd_fwd.py:166`'s docstring lists "probe untag"
    among what the faithful i2 run models. That docstring overstates the code.

  Two consequences. **(1) The 11-pair NetPlumber disagreement cannot be attributed to
  the untag** -- NetPlumber does not enforce it either -- so it must come from the
  in-stage admission x out-stage rewrite coupling, which is exactly what C4 part 1
  implemented. **(2) Enforcing the untag unconditionally would make ad6 the STRICTEST
  of the three engines**, reintroducing a parity gap in the opposite direction from the
  one C4 exists to close. Hence the separate default-off flag: ON is the
  scientifically faithful model (the real access ports do untag, and `probes.json`
  records it), OFF matches how the other two engines are actually run. The IR always
  reports what the probes DECLARE (`probe_vlan`) and separately whether it was ENFORCED
  (`probe_untag`), so a stamped result cannot be misread about which model produced it.

  **What this means for the three-query experiment: run it with the untag OFF first.**
  That is the like-for-like configuration against NetPlumber's 11, and it is now
  buildable (admission + rewrite, no untag). A second run with the untag ON then
  measures the untag's own contribution as a separate, deliberate delta rather than a
  hidden assumption -- and if the two disagree, that is itself a reportable result about
  what NetPlumber's memory-explosion workaround costs in fidelity.

  **C3 EXPERIMENT PREPARED 2026-09-09 -- driveable end to end, NOT YET RUN.**
  `bench/ad6_i2_measure.py` gained `--faithful-vlan`, `--probe-untag`, `--pairs
  SRC>PROBE,...` and `--dry-run`; its module docstring now carries the whole recipe
  (dry-run -> control-only probe -> untag off -> untag on) plus how to read each
  outcome, so the run does not depend on this document being open. **The recipe
  requires `--lite-acyclic`** -- found when the control run was actually launched, and
  a genuine gap in the first version of the recipe: the general
  `_CreateAcyclicConstraints` does not complete on i2 (one giant non-trivial SCC over
  99.3% of nodes, so it never gets wl_stanford's "orders of magnitude" cut), the lite
  path emits the identical clause set (`testAcyclicRankConstraintLiteMatchesGeneral\
Encoding`) in ~15-21 s, and all four recorded i2 artifacts carry `lite_acyclic: true`,
  so it is also what keeps a faithful run comparable with the plain figures. The
  flag's own "EXPERIMENTAL, opt-in only" help text is about not promoting it to a
  default path, not about avoiding it here. Built test-first:
  `fave/test/test_ad6_i2_measure.py`, 34 `fast`-tier tests, confirmed failing
  beforehand.
  **Three guards, each against a silent wrong answer rather than a crash.** (1) An
  unknown router name in `--pairs` raises, naming the offender and listing the real
  names -- `--pair-filter` could only ever narrow a fixed 81-pair product, but a
  free-text list can name a router that does not exist, and a typo that merely selected
  nothing would cost the whole run; the list is resolved immediately after the ~6 s IR
  build, so it costs the replay instead. (2) `--probe-untag` without `--faithful-vlan`
  is refused: `probe_vlan_literals()` returns `[]` on a plain IR, so the run would stamp
  `probe_untag: true` while measuring the untagless model. (3) `_forced_literals()`
  refuses any forced variable name absent from the base encoding -- the
  `IncrementalSession._index_for` hazard in the open, since an invented index is
  otherwise unconstrained and the untag would be satisfiable by construction; the
  ad6-side `test_the_forced_variables_exist_in_the_base_encoding` makes the same check
  against a real encoding, this makes it a hard failure in the measurement path too.
  **The untag needed wiring into this script separately from `ad6/fave_bridge.py`:**
  the script drives PySAT directly (which is what lets it swap solvers and instrument
  the build/DIMACS/solve split), so the bridge's own `extra_vars` plumbing never runs
  here.
  **Result stamping.** `faithful_vlan`, `probe_untag`, `out_rw_rewrites` and
  `probe_vlan` (what the probes DECLARE, separate from what was ENFORCED) go into every
  result, so an artifact identifies which of the three models produced it without
  reference to the command line.
  **Dry-run validation against the real model:** plain unchanged (18 devices, 77,460
  `fwd_rules`, `out_rw_rewrites: 0`, 81 queries -- the recorded artifacts stay
  reproducible), faithful `out_rw_rewrites: 77451`, both faithful modes resolving the
  three pairs in ~6-8 s at ~257 MB, and the untag confirmed as **12 all-negated per-bit
  literals** on each probe's `probe_fanout_probe_<role>` aggregate.
  **MEMORY ENVELOPE MEASURED 2026-09-09 (control-only step (b), sandbox, 20 GB box) --
  the faithful encoding does NOT fit as the script stands, and the reason is a fixable
  one.** Run: `--faithful-vlan --lite-acyclic --pairs hous>salt,... --max-queries 1
  --solver cadical195`. It was stopped deliberately at `acyclic_constraints_built`
  (t=750 s) with 18,067 MB RESIDENT (not a high-water artefact -- a 5 s `ps` sampler
  confirms current RSS) against 18,367 MB available, with DIMACS conversion and solver
  bootstrap still ahead; those two cost plain mode +5.2 GB, so the run needed ~23-24 GB.
  **What faithful mode does and does not add** -- at the same phase, `kripke_nodes` is
  IDENTICAL (78,078) and `acyclic_extra_clauses` is IDENTICAL (14,201,913), so the
  graph and the acyclic clause set are untouched; the entire delta is
  `_CreateMutationConstraints` (12 VLAN bits x 78,078 nodes of per-node SSA copies plus
  frame axioms): `build_s` 358 -> 700 s, and pre-DIMACS resident 8,271 -> 18,067 MB.
  **The 5 s RSS trajectory decomposes the +10.2 GB climb into two halves, and the first
  is avoidable.** t=706->725 s, `combined = deepcopy(encoding)` in `measure()`:
  **+5.4 GB**. t=725->750 s, the lite acyclic step's 14.2M clause tuples: +4.8 GB. That
  deepcopy is dead weight -- it is immediately followed by `del encoding`,
  `instantiate_base` returns a fresh per-call lxml tree that nothing else references,
  and on the `--lite-acyclic` path `combined` is never mutated at all (lite clauses are
  kept separate and resolved to DIMACS ints after the base encoding's index exists), so
  `combined = encoding` is semantically identical. It went unnoticed because in plain
  mode the base encoding is small enough not to matter; faithful mode's mutation
  constraints make it the largest object in the process. Removing it would put
  pre-DIMACS resident near 12.7 GB and leave ~5.8 GB for DIMACS + bootstrap, i.e.
  plausibly INSIDE the 20 GB box -- **estimated, not yet measured**, and the faithful
  instance's own larger variable/clause count will push that delta above plain's
  5.2 GB. Note the same function does `combined[0].extend(deepcopy(acyclic_constraints))`
  on the non-lite path, a second unnecessary copy, irrelevant on i2 only because i2
  cannot use that path. Note also that the
  cross-cutting ENVIRONMENT GUARDRAIL binds the TIMINGS, not the verdicts: SAT/UNSAT is
  what this experiment is for and is environment-independent, so a sandboxed run can
  decide C3 even though its wall-clock figures would not be quotable.

  **C3 ANSWERED 2026-09-09 -- THE THREE-QUERY EXPERIMENT RAN, UNTAG OFF, AND IT DOES
  NOT CORROBORATE NETPLUMBER. Decision-table case 2: the disagreement localises to one
  engine and NEITHER is trustworthy on wl_i2 until it is root-caused.**
  Run (sandbox, 20 GB box, after the deepcopy fix above made it fit):
  `--faithful-vlan --lite-acyclic --pairs hous>salt,chic>salt,chic>seat --solver
  cadical195 --checkpoint-every 1`. `status: completed`, wall 2,697 s, peak 18,416 MB,
  encoding 7,274,800 vars / 17,683,953 clauses / 78,078 Kripke nodes.

  | query | role | ad6 faithful | NetPlumber | solve |
  |---|---|---|---|---:|
  | `source.hous -> probe.salt` | agreement control | reachable (SAT) | reachable | 614.4 s |
  | `source.chic -> probe.salt` | discriminator | **reachable (SAT)** | unreachable | 63.4 s |
  | `source.chic -> probe.seat` | discriminator | **reachable (SAT)** | unreachable | 1,246.9 s |

  **The control agreeing is what makes the discriminators readable at all** -- it rules
  out case 3 (a faithful encoding broken outright), which is exactly why it was ordered
  first.

  **ARTIFACT + A DEFECT IT EXPOSED.** Archived as
  `bench/wl_i2/eval/ad6_i2_faithful_untagoff_3pairs_sandbox.json` ("sandbox" in the name
  marks the timing caveat; the verdicts are not environment-dependent). **That file
  carries `oracle_match: false`, which is WRONG and must not be read as ad6 failing the
  differential.** C1's oracle diff ran unconditionally against `reachable.json`'s full
  72-pair mesh, and `reach_matrix` reports a pair as unreachable when it was simply never
  queried -- so the 69 pairs this run did not ask about counted as failures. The
  corrected verdict is **`oracle_match: true` over 3 pairs compared, `oracle_full_set:
  false`**: all three answers are consistent with the oracle, which is unsurprising since
  the oracle is an all-reachable mesh and all three came out reachable. `_oracle_diff` +
  `_is_full_sweep` now scope the differential to the pairs actually answered and stamp
  which question the verdict answers (11 new tests; the fullness test is decided from the
  queries answered, not the flags passed, because `--pair-filter exclude-self` narrows
  nothing the differential compares and a flag-based test would stamp a complete sweep as
  partial). Verified not to move any archived verdict: the 72-pair plain run recomputes
  identically. **The artifact itself is left exactly as the process wrote it** -- same
  policy as `ad6_i2_kissat404_lite_freshpq_partial36of72.json`'s `running:querying`
  status: artifacts are not doctored, the record explains them.

  **WHAT THIS FALSIFIES.** This section's own leading hypothesis was that the 11-pair
  disagreement comes from "the in-stage admission x out-stage rewrite coupling, which is
  exactly what C4 part 1 implemented" (see the PROBE-UNTAG PARITY FINDING's consequence
  (1) above). That is now measured and WRONG: with all 77,451 egress rewrites captured
  and the in-stage admission gate active, ad6 still reaches both pairs. Combined with
  the earlier finding that neither comparison backend enforces the probe untag on i2 --
  and this run had it OFF, so the comparison is like-for-like -- **both candidate
  explanations for NetPlumber's 11 are now eliminated.** Do not re-derive either; the
  next hypothesis has to come from somewhere else.

  **WHAT MAKES THIS DECIDABLE RATHER THAN A STANDOFF.** All three answers are SAT, and a
  SAT answer is a WITNESS. Extract the satisfying assignment for `chic -> salt` (the
  cheap pair at 63.4 s), read the path and the per-hop VLAN off it, and check it against
  `bench/wl_i2/i2-json/routes.json` by hand. Either the witness is a legal path, in
  which case NetPlumber's 11 are a NetPlumber fault, or it violates the FIB, in which
  case ad6's faithful encoding is still too weak and the witness names where. This is a
  finite check on one concrete path, not another engine-level comparison, and it is the
  recommended next step. `bench/ad6_i2_measure.py` does not extract models today, so it
  needs a small addition.

  **ROOT-CAUSING PLAN, agreed with the owner 2026-09-10 -- NP FLOW-TREE LEAVES AS A
  DIFFERENTIAL LOCALIZER, sharing one primitive with the witness check.** Owner's idea;
  the analysis and sequencing below is what it turned into after checking what exists.

  **This technique is already proven in this project, on a structurally identical
  problem.** `APKEEP_BACKEND.md` "Baseline validation" (2026-07-10) root-caused
  wl_stanford's `bbra->rozb` false positive exactly this way: NP's `dump_flow_trees`
  showed `source.bbra` reaching `mid.bbra` with 869 branches of which 868 die at the
  `mid.bbra -> out.bbra` transition, while APKeep -- which collapses the out stage --
  forwards past that point. Two things carry over. (1) The method note is emphatic that
  the flow dump "is now the reliable per-hop oracle ... replacing static rule inspection,
  which produced five successively-disproven mechanisms here" -- five wrong mechanisms
  from reading rules, one right one from reading flows. That is a strong prior for
  preferring this over more `routes.json` reading on i2. (2) Its unresolved caveat is
  precisely the i2 question: decoding NP's packed header vectors was unreliable and the
  rule-text reading self-contradictory, ending in **"do not assert a specific VLAN value
  until this is decoded."** So on i2, treat NP's flow STRUCTURE as the oracle and NP's
  header VALUES as untrusted.

  **What exists.** `dump_flow_trees(dir, simple)` end to end (`jsonrpc.py:755` ->
  `rpc_handler.cc:529` -> `net_plumber.cc:1808`); in simple mode `_traverse_flow_tree`
  recurses and appends ONLY leaves, as bare `{"node": <node_id>}`. The id->identity
  mapping exists as `fave/test/check_flows.py::_get_inverse_fave` over `fave.json`
  (`id_to_table`/`id_to_rule`/`id_to_generator`/`id_to_probe`), and
  `_get_flow_tree_leaves` already walks trees to leaves. ad6's device keys are
  `_fwkey(device)` = the FaVe name with `.`/`-` -> `_`, so DEVICE-level correspondence is
  exact and free -- and device level is the granularity "ad6 forwarded past an NP leaf"
  needs.

  **Four things that need care.**
  1. **Simple mode discards the header space** (only full mode carries `flow` at leaves).
     Combined with the caveat above, that is fine: use simple mode for structure and do
     NOT plan on NP's VLAN values at all.
  2. **A leaf conflates "delivered" with "dropped"** -- `_traverse_flow_tree` emits a
     leaf whenever `n_flows` is empty, so a terminal is a probe arrival OR a dead end,
     undistinguished. A leaf whose id is in `id_to_probe` is an arrival; everything else
     is a dead end. Without that split, "ad6 forwards past an NP leaf" is trivially true
     at every probe.
  3. **The engines are not symmetric, and this reframes the comparison.** NP computes a
     full forward closure; ad6 answers one existential question at a time, so there is no
     cheap way to ask ad6 for its whole reachable node set (78,078 nodes). So this is NOT
     a symmetric set diff: **NP's leaf set is a hypothesis GENERATOR and ad6 gets one
     targeted query per candidate.** `IncrementalSession.Query`/the measure script's
     `or_gate(b_trans)` already accept an arbitrary node key as destination; only
     `query_destination_key`'s probe assumption is in the way, which is a small addition.
  4. **The cost lands favourably because of the warm-solver effect measured above.** Many
     targeted queries in ONE session is exactly the regime where per-query cost collapses
     (439x cold-to-warm on the identical query), so a batch of node probes is cheaper per
     answer than the three-query run was. Pay the ~771 s build once.

  **THE SHARED PRIMITIVE, and why these are one piece of work rather than two.** Both the
  witness check and the leaf comparison need the same thing: *given a solve, which
  FaVe-identified nodes did the flow traverse?* Model extraction produces it, the leaf
  comparison consumes it. It is the ad6 counterpart of the `witnessPath`/`witnessFwd`
  instrumentation the wl_stanford investigation added to APKeep's checker. Transition
  variables are named `<source>_true_<target>` / `<source>_false_<target>`
  (`XMLUtils.CreateTransition`), so a SAT model's positive literals over those names ARE
  the edges taken; node keys map back to FaVe devices through an IR-derived exact map
  (`_fwkey`/`iface_key`/`_gen_fwkey`/`_probe_fanout_key` inverted, longest-prefix, no
  guessing).

  **Sequencing (cheapest and most decisive first).**
  (a) The shared primitive: witness path in FaVe identities.
  (b) The near-free intersection: take the EXISTING `chic->salt` witness, map its path to
      devices, and check whether it passes THROUGH a device that is an NP leaf. If so the
      divergence localizes to one (device, rule) readable straight out of `routes.json` --
      no new ad6 queries, no full-tree dump.
  (c) One live NP i2 run with `simple=True` for the leaf sets (~552 s, ~1 GB per the
      earlier in-process measurement).
  (d) Targeted per-node ad6 queries in one warm session, only where (b)/(c) are ambiguous.
  (e) Full trees only if VLAN values turn out to be unavoidable -- and then the packed
      vector decode is a prerequisite, not an afterthought.

  **Detail to resolve before writing leaf-parsing code:** `check_flows.py:213` reads an
  aggregated `flow_trees.json`, but nothing in this repository writes that file -- the C++
  writes per-source `<node_id>.flow_tree.json`. So leaf parsing is a small adapter over
  the per-source files, not straight reuse of `_get_flow_trees`.

  **FUTURE OPTION (owner, 2026-09-10) -- decode NP's leaf header spaces and compare
  VALUES, not just structure. DELIBERATELY NOT part of the current witness check; owner
  decision, recorded so it is not rediscovered.** The idea: extend the reduced (simple)
  flow-tree dump to carry the header-space objects that reach each leaf. NP's own
  `mapping` says what each bit MEANS (e.g. "bit 6 of the IPv4 destination"), from which
  the corresponding ad6 variable name is derivable, so values become comparable rather
  than only topology. Three notes on feasibility, in increasing order of importance:

  1. **The decode table is already exposed.** `check_flows.py::_get_inverse_fave` already
     returns `"mapping": fave["mapping"]`, so the bit->field semantics need no new
     plumbing on the FaVe side. Worth pairing with the prior attempt's caveat though: what
     defeated the wl_stanford investigation was decoding the PACKED 48-bit vectors, not
     the field semantics. `mapping` supplies the half that was missing; it does not by
     itself make the vector decode reliable.
  2. **`hs_diff` is only hard for the comparison we do NOT need.** An HSA header space is
     a union of (match, minus-list) pairs. Testing whether a single ad6 witness assignment
     lies inside it is plain membership -- cheap, and unaffected by subtracted subspaces.
     It is set-vs-set EQUALITY that gets awkward. For the question at hand the membership
     direction is the one that matters, so the owner's "less trivial but still doable"
     is, for our direction, closer to trivial.
  3. **The don't-care asymmetry is the real one, and it makes the comparison
     ONE-DIRECTIONAL.** ad6's witness is a total assignment -- a POINT; NP's leaf is a
     SET with don't-care bits. So: "ad6's witness point is NOT in NP's leaf space" is a
     SOUND divergence finding (ad6 admits a header NP does not), and that is exactly the
     direction the i2 disagreement runs. The converse -- concluding ad6 cannot produce
     some header NP has -- does NOT follow from one witness and must not be asserted.
     **There is an escape hatch, and the warm-solver effect makes it cheap:** a bit's
     don't-care status is decidable by asking ad6 whether BOTH values are satisfiable
     under the same source/destination assumptions -- 2 queries per bit, so 24 for the
     12-bit VLAN field, in ONE warm session where per-query cost has collapsed (see the
     439x cold/warm measurement above). That converts a point into a per-bit
     free/forced classification and removes the asymmetry for any field worth the
     effort. Not needed for a membership check; needed the moment a VALUE claim is made.

  **WITNESS CHECK DONE 2026-09-10 -- step (a)+(b) of the plan above. The primitive
  works, the divergence is localized to ONE hop without any NetPlumber run, and every
  model-side explanation checked so far comes up CLEAN.** Run: the same three pairs,
  `--faithful-vlan --lite-acyclic --witness`, cadical195; `status: completed`, wall
  2,950 s, peak 18,454 MB. Extraction cost ~46 s and ~38 MB on top of the solve; the
  transition index is 155,199 vars, **2.13%** of 7,274,800, built in 1.7 s -- the
  transition-only restriction was worth it (a full inversion would be 47x larger beside
  a 17 GB instance). The scoped oracle diff also had its first real exercise:
  `oracle_match: true, oracle_pairs_compared: 3, oracle_full_set: false`.

  | pair | solve | witness device walk | edges/nodes |
  |---|---:|---|---:|
  | `hous->salt` | 660.7 s | source.hous -> in.hous -> out.hous -> in.kans -> out.kans -> in.salt -> out.salt -> probe.salt | 140/141 |
  | `chic->salt` | 72.8 s | source.chic -> in.chic -> out.chic -> in.kans -> out.kans -> in.salt -> out.salt -> probe.salt | 248/249 |
  | `chic->seat` | 1,407.8 s | source.chic -> in.chic -> out.chic -> in.kans -> out.kans -> in.salt -> out.salt -> in.seat -> out.seat -> probe.seat | 618/619 |

  **ZERO MODEL SLACK on all three, which validates the primitive's riskiest assumption.**
  Every walk uses EVERY true transition edge (n nodes = n-1 edges), so the true-edge set
  contained exactly one path and `witness_path`'s search was not picking a route out of a
  thicket. The acyclic constraints are doing their job. The control walk is also a real
  Internet2 route (Houston -> Kansas City -> Salt Lake) on a pair BOTH engines call
  reachable, so the extraction is validated against known-good ground truth rather than
  only against itself.

  **LOCALIZED TO ONE HOP, for free.** The discriminator's walk differs from the
  mutually-agreed control ONLY in its first hop (`in.chic -> out.chic` vs
  `in.hous -> out.hous`); the five-hop tail `in.kans -> out.kans -> in.salt -> out.salt
  -> probe.salt` is IDENTICAL and NetPlumber itself accepts that tail for Houston
  traffic. And `chic->seat` routes THROUGH salt, so one defect at the Chicago->Kansas
  entry would explain BOTH discriminators -- which is consistent with NetPlumber calling
  both unreachable, and with `chic` being the worst offender in its 11 (`chic -> {hous,
  kans, losa, salt, seat}`). This is what the NP-leaf comparison was supposed to buy;
  the shared tail delivered it without a NetPlumber run.

  **BOTH MODEL-SIDE EXPLANATIONS CHECKED, BOTH CLEAN.** (1) Along the witness path, every
  out-stage rewrite lands on a VLAN the downstream in-stage admits -- 0 violations on all
  four hops (`out.chic->in.kans` 2,547 routes on vlans 10/20/30; `out.hous->in.kans`
  2,157 on vlan 0; `out.kans->in.salt` 883; `out.salt->in.seat` 1,019). (2) Port-scoped:
  `in.kans.400022` admits exactly vlans 10/20/30, precisely what `out.chic` rewrites to
  toward kans. So the crossing is legal whether admission is read per-device or
  per-port. **This also weakens the VLAN-choice hypothesis below**: the rewrites land on
  admitted values anyway, so the solver never needs to "choose" an illegal tag.

  **NEW FINDING, found while checking (2) -- ad6's faithful admission gate is a
  CROSS-PRODUCT OF TWO PROJECTIONS, and every single i2 admission rule is affected.**
  i2's `routes.json` in.X rules are port-scoped: the 6th positional field is `in_ports`,
  e.g. `["in.atla", 1, 1, ["vlan=1"], ["fd=in.atla.100000"], ["in.atla.100028",
  "in.atla.100007"]]`. ad6 keeps the two dimensions SEPARATELY -- `ir["in_admit"]`
  (which ports have any admission rule, `favemodel.py:497/512`) and `ir["in_vlans"]`
  (which vlans the DEVICE admits, consumed at `favemodel.py:322` as
  `admitted_vlans = ir["in_vlans"][device]`) -- and gates on their product rather than
  on the real (port, vlan) relation. Measured over the real model: **390 of 390
  (device, vlan) admission pairs are scoped to a STRICT SUBSET of their device's ports
  -- 100%**. Worst cases are on `in.chic` itself, where a vlan admitted on **1 of 36**
  real ports is granted on all 36 (vlans 981, 980, 717, 716, 713, 70, ... each +35
  ports). **This is NOT the cause of the chic->salt divergence** -- that crossing is
  legal port-scoped, as (2) shows -- but it is a genuine, structural over-approximation
  of exactly the kind that manufactures false reachability, it is the strongest remaining
  candidate for the OTHER pairs among NetPlumber's 11, and it should be fixed on its own
  merits regardless of how this investigation ends.

  **CONSEQUENCE FOR THE PLAN: step (c), the live NetPlumber flow-tree dump, is now
  REQUIRED rather than optional.** The model as ad6 loads it PERMITS the witness path at
  every gate ad6 models, so the divergence is in something NetPlumber enforces that ad6
  does not represent at all -- and the flow dump is what says WHERE NetPlumber's Chicago
  flow dies. The wl_stanford precedent found precisely this shape: a downstream in-port
  that HAS a matching rule yet where no pipe forms, i.e. a header-overlap failure
  invisible to rule-level reasoning. Expect the same class of answer here, and note that
  the earlier "we may not need the dump" reading is now retired.

  **STEP (c) DONE 2026-09-10 -- THE NETPLUMBER FLOW DUMP LOCALIZED IT, AND IT REVERSES
  TWO EARLIER CONCLUSIONS OF MINE. NetPlumber is RIGHT on the Chicago pairs; ad6
  over-approximates through a specific, fixable defect.**

  Tooling: `bench/np_i2_flow_dump.py` (drives i2 through `NetPlumberLibAdapter`, writes
  `fave.json` from the engine's id tables since `InProcessFaVe` runs no aggregator, dumps
  reduced flow trees) and `bench/np_i2_flow_leaves.py` (resolves leaves to FaVe
  identities, splits delivered from dead-end). Build 576 s, peak 1,838 MB, dump 2.1 s, 9
  flow trees / 24 MB. 18 tests.

  **INDEPENDENT CROSS-VALIDATION OF THE 11.** The dump reproduces the 11 unreachable
  pairs EXACTLY -- `chic -> {hous, kans, losa, salt, seat}` and `atla`/`newy32aoa`/`wash`
  `-> {salt, seat}` -- via a completely different NetPlumber output path than
  `get_compliance_results()`. So the 11 are a reproducible property of NetPlumber's
  computation on this model, not an artefact of the compliance path.

  **WHERE CHICAGO'S FLOWS DIE.** `source.chic` traverses chic/atla/wash/newy32aoa fully
  (in + out + probe each), REACHES `in.kans` and `in.hous` and dies there, NEVER touches
  `out.kans`/`out.hous`, and never touches losa/salt/seat at all -- consistent, since
  those lie beyond kans/hous. So the in-STAGE admission rejects what arrives from
  Chicago. Note that bulk out-stage dead ends are NORMAL and not a signal: `source.salt`
  and `source.hous` have FULL reachability and still show hundreds (a branch whose dst
  has no onward route from that router).

  **THE MECHANISM, VERIFIED FROM `routes.json` WITH NO ENGINE.** `out.chic.220045 ->
  in.kans.400029`: **2,545 routes rewrite to vlan 10, and that specific arrival port
  admits {11, 20, 21, 30, 31, 32, 40, 60, 70} -- NOT 10.** Only 2 routes (vlan 20, vlan
  30) are admitted, and the dump shows exactly 2 branches reaching `in.kans`. Across the
  whole model only two crossings have any per-port rejection (`out.chic->in.kans` 2,545
  rejected / 2 accepted; `out.kans->in.chic` 19 / 5,674), and **2,555 of those 2,564
  rejections -- 99.6% -- are ACCEPTED by ad6's per-device model.** Every one of those is
  a crossing ad6 permits and NetPlumber blocks.

  **CORRECTION 1 (mine): the cross-product finding recorded above as "NOT the cause of
  the chic->salt divergence" IS the cause.** That verdict came from my own check
  aggregating admission per DEVICE -- "vlans 10/20/30 are admitted somewhere on in.kans"
  -- which reproduced the exact error I had just criticised in ad6. Per ARRIVAL PORT the
  join fails. `ir["in_vlans"]` being `Dict[str, set]` is not merely a fidelity gap to fix
  on its own merits; it is the defect that manufactures the chic reachability ad6
  reports.

  **CORRECTION 2 (mine): "both model-side explanations checked, both clean" was wrong**
  for the same reason. The witness path is NOT legal in the model as the model actually
  reads; it is legal only under ad6's relaxed admission.

  **WHAT THIS SETTLES AND WHAT IT DOES NOT.** Settled: for the Chicago pairs, NetPlumber
  is corroborated and ad6's SAT answer is a false positive with a named cause, so
  §5.5's decision-table "case 2" reading is superseded on those pairs. NOT settled: the
  remaining SIX pairs (`atla`/`newy32aoa`/`wash` -> {salt, seat}) are NOT explained by
  this mechanism -- no other crossing has a per-port rejection, and `atla` for instance
  REACHES seat's tables yet never delivers to `probe.seat`. The structural dump is
  exhausted for those; they are where the owner's deferred header-space decode (recorded
  above) stops being optional.

  **CONSEQUENCE: fixing `in_vlans` to a per-(port, vlan) relation is now the top
  priority** -- it is a correctness defect with a measured blast radius (2,555
  wrongly-permitted crossings), and it must land before any further ad6 i2 reachability
  number is quoted.

  **DONE 2026-09-10 -- PER-(PORT, VLAN) ADMISSION LANDED. Code fixed and pinned by
  tests; the reachability consequence is NOT yet measured.**

  Capture side (`fave/ad6/adapter.py`): `_capture_in_admission` now reads each in-stage
  rule's own `in_ports` and records `_in_vlans: {device: {port: {vlans}}}`, published as
  `ir["in_vlans"] = {device: {port: [vlans]}}`. Encoding side
  (`ad6/src/parser/favemodel.py`): each admitted port gets its OWN two-rule ingress
  admission gate -- `fw_<dev>_iadm<port>_r0` carrying just that port's VLAN disjunction
  (several `<fieldmatch>` on one field OR together, `KripkeUtils._HandleRule`), then an
  unconditional `fw_<dev>_iadm<port>_denyall` -> DROP. `entry_key` routes every
  topology edge (`wire_edges`) AND every attached generator (`_gen_firewall`) into that
  gate, so it cannot be bypassed; the gate hands off to the port's own ingress-ACL
  group when it has one, else straight to the forwarding table, so admission and ACL
  compose in series rather than one replacing the other.

  Three things the construction needed and the tests now pin. (1) The trailing denyall
  MUST be unconditional: `_HandleRule` wires each rule's FALSE edge to the next rule in
  DOCUMENT order, not to the next rule of its own group, so a conditional last rule
  would leak that port's REJECTED traffic into the next group. (2) A port carrying no
  admitted VLAN at all resolves to `DROP_KEY` -- `_gate_dead_ingress` already filters
  such an EDGE via `in_admit`, but a generator attaches without passing through that
  filter. (3) An admission naming no `in_ports` falls the WHOLE device back to the
  device-wide disjunction, because under-approximating a port-agnostic rule would turn
  this over-approximation into a false UNSAT -- strictly worse. No shipped benchmark
  has one (all 2,265 wl_stanford and all 390 wl_i2 in-stage rules name their ports), so
  that branch defines the semantics rather than serving a workload.

  **Verified at full i2 scale, no engine and no solve** -- the built IR + emitted table
  reproduce the root-cause evidence exactly: 223 admitted ports (identical to
  `in_admit`'s 223, so no real edge falls to DROP), 596 (port, VLAN) pairs, `in.kans`
  device union 40 VLANs, and port `400029`'s gate carrying exactly
  `{11,20,21,30,31,32,40,60,70}` -- **not 10**, while `out.chic.220045`'s rewrites are
  `{10, 20, 30}`. `in.kans` emits 51 rules (25 ports x 2 + 1 fwd) and its fwd rule
  carries **0** fieldmatches, i.e. the device-wide fallback correctly does not also
  fire.

  **THE MEMORY ENVELOPE IS UNCHANGED, measured not assumed.** The i2 Kripke is **78,524**
  nodes against the recorded 78,078 -- **+446 (+0.57%)**, exactly the predicted 223 ports
  x 2, with `iadm_nodes` confirming all 446 are the new gates. At 12 VLAN bits per node
  the mutation constraints therefore grow by ~5,352 variables on 7,274,800, so the ~20 GB
  envelope the deepcopy removal bought (§5.5 "MEMORY ENVELOPE MEASURED") still holds and
  the three-query faithful run needs no re-sizing. (Sandbox timings, directional only:
  IR 10.5 s, config 2.9 s, `ConvertToKripke`+wiring 570.9 s.)

  **The archived encodings stay reproducible.** `favemodel._in_vlans_for` still reads
  the pre-fix flat `{device: [vlans]}` shape as the device-wide gate, so an archived IR
  builds the encoding it was measured against; the adapter never emits that shape any
  more (pinned by `test_nothing_emits_the_old_flat_shape_any_more`). Deliberately NO new
  adapter flag: the old behaviour is a defect, not a configuration, and a third boolean
  would multiply the mode matrix for a mode nobody should run.

  **i2 THREE-QUERY RUN MADE 2026-09-10, PORT-SCOPED: the control answers FASTER and the
  discriminator becomes INTRACTABLE. Suggestive of the flip, but NOT proof.** Ran the
  recipe's step (c) verbatim (`--faithful-vlan --lite-acyclic --solver cadical195
  --checkpoint-every 1`, untag off) against a 6 h `timeout`. Build 771.5 s, peak RSS
  18,501.7 MB (pre-fix 18,416.0 -- as predicted, and it survived; ~1.6-1.9 GB of swap
  absorbed the tail).

  | pair | pre-fix | port-scoped |
  |---|---|---|
  | `hous->salt` (agreement control) | SAT, 614.4 s | **SAT, 425.8 s** |
  | `chic->salt` (discriminator) | SAT, **63.4 s** | **no answer in 20,302 s** |
  | `chic->seat` (discriminator) | SAT, 1,246.9 s | not reached |

  **The asymmetry is suggestive -- and WEAKER than this section first claimed (corrected
  2026-09-11).** The control got 1.4x FASTER while the discriminator went from a 63 s SAT
  to undecided after 5h38m. This block originally called that "the signature of a verdict
  that has FLIPPED"; the skip-acyclic probe below then showed the relaxed problem is still
  SAT and answers `chic->salt` in 55 s, and that the acyclicity block is 84% of the
  variables -- so the no-answer is substantially explained by ENCODING HARDNESS rather than
  by a flip, and the timing argument alone was over-read. The flip is now well evidenced,
  but by the grounded-witness probe, not by this timing asymmetry. The original reasoning
  was: the pre-fix 63 s was cheap precisely
  because a satisfying model existed to exhibit, and refuting is a categorically harder
  job than exhibiting. It is CONSISTENT WITH `chic->salt` now being UNSAT -- i.e. with
  ad6 and NetPlumber agreeing on the Chicago pairs -- and it is NOT proof: an undecided
  query is undecided, and a SAT answer that merely became much more expensive to find
  would look identical from the outside.

  So the decision table's case 1 ("control SAT, discriminators UNSAT -> NetPlumber's 11
  corroborated") is now the LEADING reading rather than the established one, and §5.5's
  recorded "case 2" is superseded either way: the pre-fix all-three-SAT result was
  produced by the projected admission gate and cannot stand.

  **SETTLED (to the level of strong evidence, not formal proof) 2026-09-11 BY A
  SKIP-ACYCLIC GROUNDED-WITNESS PROBE. The fix removes exactly the grounded paths it
  should and keeps the one it should.** Ran `--faithful-vlan --skip-acyclic
  --fresh-per-query --witness --solver cadical195`: the whole three-query run COMPLETED in
  932.9 s on a 9,061.4 MB peak, against the full encoding's 20,302 s with no answer and
  18,501.7 MB.

  | pair | pre-fix (per-device, full enc.) | port-scoped (relaxed) |
  |---|---|---|
  | `hous->salt` (control) | grounded, 141 nodes, real route | **grounded, 395 nodes, real route** |
  | `chic->salt` | **grounded, 249 nodes** via `chic->kans->salt` | **NO grounded walk**, 7,656 ungrounded edges |
  | `chic->seat` | **grounded, 619 nodes** via `chic->kans->salt->seat` | **NO grounded walk**, 15,417 ungrounded edges |

  Both pre-fix Chicago witnesses ran THROUGH `in.kans` -- exactly the crossing where
  `out.chic.220045` delivers `vlan=10` into a port admitting
  `{11,20,21,30,31,32,40,60,70}`. The port-scoped gate closed that hop, and the solver can
  now satisfy the relaxed formula only with a floating cycle: 19x and 39x the control's
  edge count, none of it forming a source->destination walk.

  **One half of this is formally solid.** The control's witness is ZERO-SLACK (394 edges
  for 395 path nodes -- every true edge lies on one simple path), and a simple path admits
  a valid rank assignment, so relaxed-SAT with a zero-slack grounded witness SOUNDLY
  IMPLIES full-encoding SAT. The converse does not hold: an ungrounded witness means "this
  model is not a real path", not "no real path exists" -- the solver might have found a
  grounded one with different ordering or luck. So `chic->salt` being UNSAT on the full
  encoding is now the strongly-evidenced reading, supported by four independent strands
  (the route/VLAN arithmetic; NetPlumber's flow dump dying at `in.kans`/`in.hous`; the
  grounded path disappearing under the fix; the control's surviving intact), but it is not
  a proof. Only a full-encoding UNSAT is that.

  **METHOD CORRECTION -- `--skip-acyclic` is sound as a one-directional UNSAT test and
  PRACTICALLY NEAR-VACUOUS for refutation.** The rank encoding is purely additive, so
  UNSAT-on-the-relaxation would imply UNSAT outright; but floating cycles satisfy the
  relaxation, so it will essentially never RETURN unsat. The evidence for that was already
  in `ad6/FAVE_CHANGES.md` §20, which records that the floating-cycle bug was DISCOVERED
  because ungrounded witnesses made unreachable pairs look reachable -- the additivity was
  read correctly and the corollary missed. What the flag is actually good for, unanticipated
  and now the recommended use, is a cheap GROUNDED-WITNESS SEARCH: SAT + zero-slack
  grounded walk soundly implies real reachability, and SAT + ungrounded blob is strong
  evidence of unreachability at 1/20th the wall and half the memory.

  **Why the relaxation is so much cheaper, measured:** the rank/acyclic block is 84% of all
  variables (6,121,649 of 7,304,828) and 80% of all clauses (14,253,423 of 17,761,983).
  Dropping it took the control from 425.8 s to 3.5 s (~120x). So the faithful i2 model is
  NOT inherently intractable -- the cost is concentrated in the acyclicity encoding, which
  reframes §5.5's tractability question and is directly relevant to `--lite-acyclic` being
  mandatory here.

  **RESOLVED 2026-09-11 BY THE FLOW ENCODING -- decision-table CASE 1, control SAT and
  BOTH discriminators UNSAT.** With `--faithful-vlan --skip-acyclic --fresh-per-query
  --flow-path --solver cadical195` (the single-unit s-t flow grounding constraint,
  `Instantiator._CreateFlowPathConstraints`, which is sound AND complete -- see §5.4 B1):

  | pair | verdict | flow | rank (lite-acyclic) |
  |---|---|---|---|
  | `hous->salt` (control) | **SAT** | 124.9 s | 425.8 s |
  | `chic->salt` (discriminator) | **UNSAT** | **78.4 s** | no answer in 20,302 s |
  | `chic->seat` (discriminator) | **UNSAT** | **324.8 s** | not reached |

  Whole run 1,374.3 s on a 9,093.5 MB peak. `oracle_missing` is exactly
  `{salt: [chic], seat: [chic]}` and `oracle_match: false` -- CORRECT and expected:
  `reachable.json` encodes the all-reachable 72/72 POLICY EXPECTATION, and both NetPlumber
  and now faithful ad6 say the network does not implement it. **So §5.5's C3 question is
  answered: plain mode is insufficient for i2, and NetPlumber's 11 are corroborated by an
  independent engine on the Chicago pairs.** The recorded "case 2" (all three SAT) was an
  artefact of the per-device admission projection.

  **Cost of the grounding constraint, measured:** 1,092,512 clauses built in 2.192 s,
  against the rank encoding's 14,253,423 -- **13x fewer**, and the estimate recorded above
  (~1.2M) was close. Peak RSS 9,093.5 MB against 18,501.7.

  **VALIDATION DONE 2026-09-11 -- THE FLOW ENCODING REPRODUCES THE RANK ENCODING EXACTLY
  ON wl_stanford, IN BOTH DIRECTIONS.** Full 16-router faithful model under `--flow-path`:
  `reachable_pairs` **165**, identical to the rank encoding's, and the REACH MATRICES are
  identical across all 16 probes -- not merely the totals, which two encodings can match
  while disagreeing about which pairs. That is 256 queries of which **91 are UNSAT**, i.e.
  precisely the refutation direction an UNSAT claim depends on, against an answer
  NetPlumber independently proved. N=2 agrees the same way (2 of 4, identical matrix).

  | | rank | flow |
  |---|---|---|
  | `reachable_pairs` / matrix | 165 | **165, identical matrix** |
  | variables | 322,496 | **83,088** |
  | clauses | 851,631 | **313,555** (+68,180/query) |
  | query_s (256 queries) | 2,039.7 | **63.2** (32x) |
  | wall_s | 2,131.7 | **98.2** (21.7x) |

  **The 21.7x in this table is an UNMATCHED comparison and is retired -- see §7.5.**
  Both rows are minisat22, but the rank row also carries the GENERAL acyclic encoding
  while wl_i2 is forced onto the lite one. Re-run 2026-09-11 with both sides on
  cadical195 and the rank side on `--lite-acyclic`: **7.0x wall, 9.3x query, 1.4x peak
  RSS**, all runs still answering 165. Quote that, or the 11.6x best-of-each figure;
  never this one.
  | peak RSS | 4,173.5 MB | **1,442.0 MB** |

  And that is DESPITE the flow path paying 256 fresh solver bootstraps where the rank path
  reuses one persistent solver with assumptions -- an expected handicap that turned out not
  to matter. **So the wl_i2 `chic->salt` UNSAT now rests on a validated encoding rather
  than on its construction argument alone**, and the flow constraint is the cheaper
  mechanism on both workloads by every axis measured.

  **Superseded note, kept for the reasoning:** A brand-new encoding
  returning exactly the predicted answer is the moment for most scepticism, not least.
  What is established: the flow constraint is COMPLETE by construction (any genuine simple
  walk carries the unit), which is the property an UNSAT claim rests on and the one an
  over-constraint would break; it is tested against the rank encoding's OWN fixture; and
  the control's SAT is itself a structural check that the flow graph contains the real
  `hous->kans->salt` path, i.e. that edge enumeration picks up the topology edges
  `wire_edges` adds after `ConvertToKripke` (had it missed them, EVERY query would have
  been spuriously UNSAT). What is NOT established is agreement between flow and rank on a
  LARGE sample -- currently one point (the control, SAT under both). **The owed check:
  full wl_stanford N=16 under `--flow-path`, which must reproduce `reachable_pairs = 165`
  -- a 256-query differential against an answer NetPlumber independently proved, including
  91 genuinely UNREACHABLE pairs, i.e. exactly the direction that needs validating.** It
  requires adding the flag to `bench/ad6_faithful_measure.py` as well.

  **NEW DIVERGENCE FOUND BY THE FULL SWEEP, 2026-09-11: `atla`/`newy32aoa`/`wash` -> `kans`
  are UNSAT in faithful ad6 and are NOT among NetPlumber's 11.** ad6 is stricter here --
  the opposite direction from everything §5.5 chased before. Investigated structurally
  (IR + raw `routes.json` only, no solve, alongside the running sweep):

  * **All three share ONE cause.** `out.atla -> in.kans` has no direct link, so this is
    multi-hop. `in.kans`'s only live inbound crossings are `out.chic` (writes vlan 10 ->
    REJECTED), `out.hous` (vlan 0, admitted) and `out.salt` (vlan 0, admitted). For the
    115 sampled kans-bound destinations that `hous` reaches `kans` on, `atla`'s paths
    traverse only `out.atla`/`out.chic`/`out.wash`/`out.newy32aoa` -- **never `out.hous` or
    `out.salt`**. The eastern region's sole gateway to Kansas is Chicago, and that gateway
    is the already-known blocked crossing.
  * **ad6's IR is FAITHFUL to `routes.json`, verified directly.** `in.kans.400029` really
    admits `{11,20,21,30,31,32,40,60,70}`; `vlan=10` is admitted on `in.kans` but only on
    ports `400025/400026/400019/400022/400007`; `out.chic` egressing `220045` really writes
    vlan 10 on 2,545 routes. So the UNSATs are CORRECT FOR THE MODEL.
  * **A striking configuration detail:** `out.chic.220046 -> in.kans.400019` and
    `out.chic.220047 -> in.kans.400022` are physical links whose arrival ports DO admit
    vlan 10 -- and carry ZERO routes in the snapshot. All 2,547 of Chicago's kans-bound
    routes leave via `220045`, the one link whose far end rejects their VLAN.
  * **Hypothesis tested and REFUTED:** that the out-stage rewrite is per-in-port the way
    the in-stage admission was. It is not -- 0 `(table, dst)` pairs have more than one
    rewrite VLAN and 0 appear with different `in_ports`, over all 77,451 out rules.

  **ESTABLISHED 2026-09-11 (owner pointed at the recorded history; it was already
  diagnosed once): THE FaVe-BACKEND LPM FIX IS SCOPED TO `mid.*` AND wl_i2's FIB IS ON
  `out.*`, SO wl_i2's NetPlumber RUNS ARE NOT LPM-CORRECTED.** This is the SAME bug that
  collapsed wl_stanford's NetPlumber count from ~165 to 10 (commit `f1768c50`,
  `APKEEP_STANFORD_NP_SPEC.md` Phase 1d): FaVe's fork made `--load` key NP priority by the
  rule's stored id/file position instead of vanilla's `index=0` front-insertion, dropping
  the load-side reversal that made vanilla NetPlumber do LPM. The fix,
  `bench/np_preparation.py:_reprioritise_mid_lpm`, reassigns rule indices by descending
  prefix length -- but it does so only for devices whose name starts with `mid.`:

      for dev, positions in by_dev.items():
          if not dev.startswith('mid.'):
              continue

  **wl_i2 has ZERO `mid.*` rules** (stages are `['in','out']`, its FIB is the `out.*`
  stage), so the fix is a no-op there. The plan's own gate recorded the reason as benign --
  *"0a (wl_ifi/wl_i2 -- no overlapping prefixes, reversal is a no-op) stays green"* -- and
  **that premise is false for wl_i2**: measured, `routes.json`'s order leaves **3,731
  rules** shadowed by an EARLIER rule whose prefix strictly contains them (277-589 per
  out-table). `np_preparation.py` writes that file (line 421), so it is exactly what
  NetPlumber ingests.

  **Concrete, single-destination proof on the very link this section turns on:**

      destination 140.112.0.0
        NetPlumber (first match by index): idx=15  140.112.0.0/12 -> out.chic.220040  rw=vlan:281
        ad6 (longest prefix match)       : idx=69  140.112.0.0/14 -> out.chic.220045  rw=vlan:10

  Different egress port AND different egress VLAN -- and `220045` is precisely the link
  into `in.kans.400029` whose admission rejects vlan 10. A real router does
  longest-prefix-match, so **ad6 is right and the FaVe-backend NetPlumber i2 results are
  computed on a non-LPM forwarding model.**

  **CONSEQUENCE, and it reaches further than the three new pairs: every FaVe+NetPlumber
  wl_i2 number in this plan -- INCLUDING THE 11 UNREACHABLE PAIRS THIS WHOLE SECTION HAS
  BEEN CHASING -- was produced on a forwarding model that is wrong for 3,731 rules.** The
  ad6-vs-NetPlumber agreement on the five Chicago pairs is therefore much weaker evidence
  than it appeared: two engines agreeing while one of them mis-forwards is not
  independent corroboration. **Fix first, re-measure, then re-read every §5.5 conclusion
  that rests on NetPlumber's i2 output.** The fix is small and already proven in this
  repo: widen `_reprioritise_mid_lpm` from a `mid.`-prefix test to "any FIB-bearing stage"
  (or drop the device-name test entirely -- re-prioritising a table with no overlapping
  prefixes is a no-op by construction), with the wl_stanford 165 result as the regression
  gate.

  **FIX LANDED AND RE-MEASURED 2026-09-11 -- ad6 AND NETPLUMBER NOW AGREE EXACTLY ON ALL
  11 PAIRS.** `_reprioritise_fib_lpm` now re-prioritises the DECLARED FIB tables
  (`config.json`'s `fib_table_types`: `["mid"]` for wl_stanford, `["out"]` for wl_i2), both
  datasets were regenerated, and NetPlumber was re-run on the corrected wl_i2 dataset
  (`np_i2_flow_dump.py`, build 588.1 s, peak 1,938.5 MB).

  | | NetPlumber BEFORE (non-LPM) | NetPlumber AFTER (LPM) | ad6 (flow-path, port-scoped) |
  |---|---|---|---|
  | unreachable pairs | 11 | **11** | **11** |
  | `chic` -> {hous,kans,losa,salt,seat} | yes | yes | yes |
  | eastern trio -> **salt** | yes | **NO** | no |
  | eastern trio -> **kans** | no | **YES** | yes |

  **The LPM fix moved exactly the three pairs that were in dispute, and moved them onto
  ad6's answer.** `atla`/`newy32aoa`/`wash` -> `salt` became reachable; -> `kans` became
  unreachable. Set difference against ad6 is now EMPTY in both directions.

  **What this settles.** (a) The route-ordering gap WAS the whole of the remaining
  ad6-vs-NetPlumber disagreement on wl_i2. (b) The three pairs ad6 alone reported
  (`eastern -> kans`) were CORRECT, and NetPlumber's old `eastern -> salt` was the
  artifact -- so the structural trace that predicted this (the eastern region's only
  gateway to Kansas is Chicago, and `out.chic.220045` writes vlan 10 into a port admitting
  {11,20,21,30,31,32,40,60,70}) was right. (c) **The agreement is now genuine corroboration
  rather than two engines agreeing while one mis-forwards** -- the qualification this
  section was carrying since the scoping gap was found.

  **And it is independent corroboration in the strong sense:** ad6 reaches the answer by
  SAT over a port-scoped admission relation with a single-unit s-t flow grounding
  constraint; NetPlumber reaches it by HSA flow propagation. Nothing is shared but the
  dataset. ad6's IR is HASH-IDENTICAL across the reordering (verified: `fwd_rules`,
  `in_vlans`, `out_rw`, `edges`, `devices`), because ad6 recomputes LPM itself -- so the
  ad6 side of this comparison did not move at all, and the 72-pair sweep result stands
  exactly as run.

  **ANSWERED 2026-09-11 -- `eastern -> seat` IS THE SAME CHICAGO CROSSING. There was
  never a second mechanism, and all 11 pairs now have ONE cause.** Established with a
  third witness, independent in implementation and method (see the epistemic note below for
  what that does and does not buy): `bench/i2_structural_oracle.py` computes the reachability
  matrix straight from the shipped JSON, sharing no code with ad6 or NetPlumber. **It
  reproduces the 11 pairs EXACTLY**, so the agreement is now three-way.

  **WHAT THE i2 "ORACLE" ACTUALLY IS, EPISTEMICALLY — owner clarification 2026-09-12, and
  it must accompany every use of the 11-pair result.** *"The oracle that you compare the
  result with has not been externally provided but is an agreement of NetPlumber and ad6.
  There have been multiple rounds of correction for both tools (more for ad6 than for
  NetPlumber) and the oracle has been manually inspected finally. This way, some confidence
  has been gained."*

  **There is no external ground truth for wl_i2's data plane.** `reachable.json` is policy
  INTENT emitted by the same generator as `checks.json` (TODO.md item 1s), so it cannot
  serve; the 11-pair result is the project's own construction. Confidence in it is EARNED
  by process, not derived from an authority, and rests on three legs of unequal strength:

  1. **Convergence of two independently-implemented engines** — ad6 by SAT/QBF over a
     port-scoped admission relation with a flow grounding constraint, NetPlumber by HSA
     flow propagation, sharing nothing but the dataset. Real, but reached only AFTER
     multiple rounds of correction to BOTH: many on the ad6 side (per-(port, VLAN)
     admission replacing a per-device projection, the out-stage rewrite, the LPM tiebreak,
     query seeding, the `/0` CIDR and IPv6 canonicalisation bugs, the grounding gap
     itself), and at least one decisive one on the FaVe/NetPlumber side (`_reprioritise_fib_lpm`
     reading the declared `fib_table_types`, which moved exactly the three disputed pairs).
  2. **A third witness by a different METHOD** — `bench/i2_structural_oracle.py`, direct
     structural simulation from the shipped JSON, exhaustive over IPv4 via prefix atoms,
     sharing no code with either engine. Independent in implementation and technique, but
     **written after the fact by the same project, not a pre-registered prediction**: its
     author already knew which answer would count as success.
  3. **Manual inspection against the RAW data** — the trace to a single misconfigured
     Chicago→Kansas link (`220045→400029` admits {11,20,21,30,31,32,40,60,70}, no 10, while
     carrying 2,547 routes of which 2,545 are tagged vlan 10), verified by hand against
     `routes.json`/`topology.json`.

  **Why leg 3 is load-bearing rather than a sanity check.** The stopping rule for legs 1-2
  was *the tools agree* — which is exactly the condition a SHARED error would also satisfy.
  Iterated mutual correction, where each round is motivated by a disagreement and halted by
  agreement, is structurally vulnerable to co-adapting two tools onto a common mistake. Leg
  3 is the only step that checks against something other than another tool's output, and it
  is strong precisely because it is a far more constrained claim than "the numbers matched":
  a co-adapted shared error would ALSO have to produce a coherent single-link explanation
  that survives inspection of the raw JSON.

  **So the phrasing to use, and to avoid.** Say: *corroborated by two engines and a
  structural witness, root-caused to one misconfiguration in the raw data, after iterated
  correction of both engines.* Do NOT say *"three independent engines confirm"* — the
  implementations are independent, the PROCESS that produced the agreement was not.

  **The oracle is exhaustive over IPv4, not a sample.** Two destination addresses behave
  identically iff they pick the same LPM winner at every device, and that equivalence is
  refined exactly by the binary trie over the union of all prefixes: `atom(p) = range(p)`
  minus the ranges of all deeper prefixes. wl_i2's 10,020 distinct prefixes yield **9,673
  atoms covering the whole address space**. This matters: sampling prefix representatives
  (`net`, `net|1`) instead reports **7** seat-delivering addresses, an over-count that
  double-counts two /31 atoms. Only the atom enumeration gives the real number. The
  oracle also confirms there is **no ECMP anywhere in wl_i2** (fanout histogram
  `{1: 77451}`), so every walk is a single chain.

  **First, a probe-semantics fact that had not been stated and that drives everything:**
  `probe.X` is tapped on **every** egress port of `out.X` and fires iff `vlan == 0`. The
  tap is PARALLEL -- a probe port may also carry a topology link, in which case the packet
  is both observed and forwarded. So "`s` reaches `probe.d`" means "some packet from `s`
  egresses `d` untagged", i.e. is delivered to a locally attached subnet at `d`.

  **Why seat is the hard destination: `|A_seat| = 5`.** Of all 9,673 atoms, exactly FIVE
  are delivered untagged at seat when sent from anywhere but seat -- `64.57.19.16`,
  `64.57.19.18`, `64.57.19.20`, `64.57.19.22`, `64.57.27.33`, all i2 backbone
  infrastructure in `64.57.16.0/20`. Compare `|A_salt| = 6,503`, `|A_hous| = 7,269`,
  `|A_chic| = 4,610`. Nearly every address is delivered untagged at some *earlier* device,
  so seat -- a leaf of the backbone -- keeps almost nothing for itself. With only five
  candidates there is no room for an alternate route to survive.

  **And all five die at the same place.** From `atla`, `newy32aoa`, `wash` AND `chic`, the
  fate of every one of the five is `BLOCKED@in.kans.400029(vlan=10; admits={11,20,21,30,
  31,32,40,60,70})` -- **100%, no exceptions**. `atla` for instance routes `64.57.19.16/29`
  out `120021` into `in.chic`, and Chicago puts it on `220045` with `vlan=10`. That is
  precisely the crossing that already explained `chic`'s five and the eastern trio's
  `-> kans`. **So the "six unexplained eastern pairs" were never a separate phenomenon:**
  three of them (`-> salt`) were a NetPlumber LPM artifact and are now reachable, and the
  other three (`-> seat`) are the Chicago crossing reached two hops later.

  **Why `-> salt` escaped and `-> seat` could not.** The eastern region does have a
  southern bypass around Kansas, but it carries exactly one atom: `64.57.27.129` travels
  `atla -> hous -> losa -> salt` entirely on `vlan=0`. The reason is a single-prefix
  routing split at `out.atla`: `64.57.27.0/24` goes to Chicago on `120021`, while the more
  specific `64.57.27.128/27` goes south to Houston on `120019`. Of salt's 6,503 candidate
  atoms, that ONE is enough to make `eastern -> salt` reachable. None of seat's five falls
  in the `/27`, so the bypass does not exist for them. **That single `/27` carve-out is
  the entire difference between the two verdicts.**

  **The root configuration fault, re-verified against raw `routes.json`/`topology.json`.**
  Chicago has THREE physical links to Kansas:

  | link | far-end admits | routes carried |
  |---|---|---|
  | `out.chic.220046 -> in.kans.400019` | `{10, 20, 30}` | **0** |
  | `out.chic.220047 -> in.kans.400022` | `{10, 20, 30}` | **0** |
  | `out.chic.220045 -> in.kans.400029` | `{11,20,21,30,31,32,40,60,70}` -- **no 10** | **2,547** (2,545 on vlan 10) |

  Chicago sends all of its Kansas-bound traffic down the one link whose far end does not
  admit the VLAN it tags with, while both links that *would* admit it carry no routes at
  all. Only the 2 stragglers on vlan 20/30 get through. **One misconfigured link explains
  all 11 unreachable pairs.**

  Artifacts: `bench/i2_structural_oracle.py` (with `--explain SRC DST`),
  `bench/wl_i2/eval/i2_structural_oracle_atoms.json`.

  **THE FIX, DESIGNED 2026-09-11 (owner review rejected my first design; the data proved
  the owner right).** My first proposal was to select FIB tables by SHAPE -- "a table is a
  FIB iff no rule matches any field other than `ipv4_dst`". The owner objected that a
  packet-filtering table can have exactly that shape, and that reordering a table which
  mixes passing and denying rules changes its filtering semantics. **Checked against the
  data, and the objection is stronger than the argument:** wl_stanford's `mid.*` tables --
  the ones the CURRENT fix already reorders -- hold 3,372 forwarding rules AND **472 rules
  with no action at all (drops)**, and **all 472 overlap a forwarding rule at a different
  prefix length** (`drop 224.0.0.0/3`, `127.0.0.0/8`, `10.0.0.0/8`, `0.0.0.0/8`, each
  against `forward 0.0.0.0/0`). Reordering them is safe today only because those drops
  happen to be MORE SPECIFIC than the default they shadow, so prefix-length order
  coincides with the intended deny-before-permit precedence. That is a property of this
  dataset, not an invariant. Worse, my predicate inspected MATCH FIELDS ONLY and never
  looked at actions -- it was blind to exactly the case raised.

  **Design, revised:**

  1. **Each benchmark DECLARES its FIB stages, in `config.json` beside the existing
     `table_types`** -- `"fib_table_types": ["mid"]` for wl_stanford, `["out"]` for wl_i2.
     Both `config.json` files are git-tracked and nothing regenerates them (the
     `gen_wl_*_inputs.sh` scripts consume them), so the declaration is stable. No shape
     inference anywhere in the selector.
  2. **Fail closed.** `prepare_benchmark` ERRORS when `fib_table_types` is absent, and
     errors when a declared type is not in `table_types`. Declaration alone would merely
     relocate the original bug -- someone adds a benchmark and forgets to declare -- so
     omission has to be loud. That is exactly the property `dev.startswith('mid.')` lacked.
  3. **Assert the transform is semantics-preserving**, per declared FIB table: partition
     its rules into forwarding and non-forwarding, and REFUSE the reorder if it would flip
     the relative order of any overlapping cross-class pair. This does not infer whether a
     table is a filter; it verifies the reorder is safe on whatever was declared. Stanford's
     472 drop/forward overlaps pass (drops are more specific); i2's out tables are 77,451/
     77,451 forwarding, so the check is vacuous there.
  4. **Blast radius: the two raw-table benchmarks only, by construction.** FaVe normally
     works from DEVICE MODELS (routers, packet filters) where a device may hold some
     FIB-like tables and some not; wl_stanford and wl_i2 are special in being composed
     from RAW TABLES. Measured: 8 benchmarks subclass `GenericBenchmark` but only these 2
     call `prepare_benchmark`. So the declaration is threaded through
     `prepare_benchmark`'s own signature and `GenericBenchmark` is NOT touched -- the
     device-model benchmarks (wl_ifi, wl_up, wl_tum, wl_example, wl_shadow,
     wl_generic_fw) are unaffected because they never enter this path, not because of a
     default value that would have to be argued safe.
  5. **De-duplicate:** `bench/stanford_priority_check.py:_reprioritise_lpm` is a SECOND
     copy of the same `mid.`-scoped logic. Point it at the shared helper -- that
     duplication is part of why this recurred.

  **SUPERSEDED FRAMING, kept because the reasoning is still the route to the finding:** The two engines order the SAME FIB differently:
  `Ad6Adapter._lpm_prio` recomputes priority as `65534 - prefix_length` (sequential
  first-match, deliberately added so the more specific route sorts first --
  `RoutingTableLPMTest`), whereas `netplumber/adapter.py` passes
  `_calc_rule_index(rule.idx, ...)`, i.e. the rule index carried in `routes.json`, as the
  NetPlumber rule id. **Measured: `routes.json`'s own order violates LPM for 3,731 rules**
  -- 277 to 589 per out-table -- where a rule is shadowed by an EARLIER rule whose prefix
  strictly contains it (e.g. `140.112.0.0/12` before `140.112.0.0/14`). For those
  destinations a first-match-by-index engine and an LPM engine select different routes.
  A real router does LPM, so ad6's semantics are the correct ones and NetPlumber's are
  correct only if the input is already LPM-ordered, which it is not. **Stated as the
  leading hypothesis, not as established:** the rule-id derivation is confirmed from the
  adapter, but NetPlumber's own C++ matching semantics were not traced.

  **METHOD NOTE, recorded because the first version of this check was WRONG:** an
  adjacent-pairs-only scan reported ZERO overlapping inversions and would have killed this
  hypothesis. Shadowing is not an adjacency property -- the containing rule can sit
  anywhere earlier in the table. The correct scan (walk file order, probe every supernet of
  each new prefix against what was already seen) finds 3,731.

  **FULL 72-PAIR SWEEP DONE 2026-09-11 (flow-path, port-scoped): ad6 finds EXACTLY 11
  unreachable pairs, NetPlumber finds EXACTLY 11, and they agree on 8.** Whole sweep 81
  queries in 4,201.4 s on a 9,183.0 MB peak; mean 42.1 s/query, and the refutations cost
  6.1x the satisfiable queries (152.3 s vs 24.8 s). `reachable_pairs` 61 of 72,
  `oracle_full_set: true`.

  | | pairs |
  |---|---|
  | BOTH unreachable (8) | `chic` -> {hous, kans, losa, salt, seat}; `atla`/`newy32aoa`/`wash` -> seat |
  | NetPlumber only (3) | `atla`/`newy32aoa`/`wash` -> **salt** |
  | ad6 only (3) | `atla`/`newy32aoa`/`wash` -> **kans** |

  **The disagreement is a clean 3-for-3 SWAP on the same three eastern sources**: both
  engines block those flows, at a DIFFERENT router. Chicago's five agree exactly, and so
  does the eastern trio toward `seat`. Two engines independently arriving at the same
  COUNT (11) with the difference confined to one destination-swap is the signature of a
  route-SELECTION difference, not of one engine over- or under-approximating -- and it is
  exactly what the `_reprioritise_mid_lpm` scoping gap above predicts. The structural
  trace already showed why: the eastern trio's only gateway to `kans` is Chicago, and
  which egress Chicago picks for a given prefix is precisely what the two orderings
  disagree about (destination `140.112.0.0`: `220040`/vlan 281 under index order,
  `220045`/vlan 10 under LPM).

  **So the six "unexplained eastern pairs" are now half-explained and half-superseded:**
  `-> seat` is real and agreed by both engines; `-> salt` is one side of the swap and
  should be re-read only after the LPM fix lands and NetPlumber's i2 baseline is
  re-measured. Do not treat either half as settled until then.

  **MEASURED FOR wl_stanford, AND IT CORRECTS THIS SECTION'S OWN BLAST-RADIUS CLAIM.**
  Full N=16 faithful re-run with the fix: **`reachable_pairs` 165 of 256, IDENTICAL to
  the archived `eval/ad6_faithful_N16.json`.** So wl_stanford's archived faithful
  REACHABILITY result is CONFIRMED by the fix, not superseded -- only its encoding-size
  and timing numbers are (see below). An earlier version of this block said "every
  archived wl_stanford faithful number is superseded as well"; that was wrong, and the
  reasoning behind it was wrong in an instructive way.

  **The "223/223 and 252/252 ports are narrower than their device union" statistic
  OVERSTATES the behavioural blast radius, and is not the figure to quote.** A narrowed
  port only matters if some route actually DELIVERS a VLAN that port rejects, and only
  matters *behaviourally* if the device-wide union would have ADMITTED it. Measured on
  both models:

  | | per-port rejections | of those, wrongly admitted by the device union | distinct crossings |
  |---|---|---|---|
  | wl_i2 | 2,564 | **2,555 (99.6%)** | 2 |
  | wl_stanford | 183 of 4,046 crossings (4.5%) | **7 (3.8%)** | 1 |

  On wl_stanford the projection was very nearly harmless: 176 of its 183 rejections were
  already rejected by the device union too (the VLAN is admitted nowhere on that
  device), leaving 7 wrongly-admitted crossings on a single `mid.bbra_rtr -> in.*`
  crossing -- and those 7 change no pair's verdict on a mesh that is 165/256 reachable
  either way. On wl_i2 it was catastrophic by the same measure. **Same defect, two
  orders of magnitude apart in effect** -- which is why the i2 verdict still has to be
  measured rather than inferred from wl_stanford's null result, and equally why
  wl_stanford's null result is not evidence that the i2 pairs will not flip.

  **COST, sandbox and therefore directional only (the ENVIRONMENT GUARDRAIL binds
  these).** wl_stanford N=16 faithful, archived vs port-scoped: `kripke_nodes` 5,463 ->
  5,967 (+504 = 252 ports x 2, exactly as predicted), variables 271,592 -> 322,496
  (+50,904), clauses 711,100 -> 851,631 (+140,531), peak RSS 3,321.6 -> 4,173.5 MB.
  **Query time 713.7 -> 2,039.7 s over the same 256 queries -- 2.9x.** That last figure
  is the one to carry into planning the i2 run: if i2's per-query cost scales similarly,
  the three-query faithful run goes from ~614 s/query to roughly 1,800 s/query, i.e.
  from ~45 minutes to over two hours. The memory envelope is unaffected (i2 +446 nodes,
  +0.57%); the WALL budget is not. **Measured on i2 afterwards, this extrapolation turned
  out to be wrong in BOTH directions** -- the control got faster (425.8 s vs 614.4 s) and
  the discriminator got worse than 320x. Per-query cost did not scale by a factor; it
  reorganised, which is what a flipped verdict looks like. Do not carry a single
  cross-workload query-time factor into an i2 estimate again.

  **CORRECTION, method rather than result (2026-09-10).** The i2 run's variable-count
  delta was predicted here as "~5,352 extra variables" from the mutation constraints
  alone (12 VLAN bits x 446 nodes). Measured: **+30,028** -- the acyclic rank encoding
  over the new nodes (+51,510 of the +78,030 clauses) and the gates' own Tseitin
  variables account for the rest. Still negligible against 7.3 M, but 5.6x the estimate.

  **NEW ASYMMETRY, deliberately not fixed here.** `fave/apkeep/adapter.py:_capture_in_
  admission` still carries the identical projection, and its `_in_vlans` feeds a
  different consumer (APKeep's own input format, `adapter.py:1257-1328`), so fixing it
  is a separate change with its own encoding semantics. Until it lands, an
  ad6-vs-APKeep faithful-VLAN comparison on wl_stanford is NO LONGER like-for-like --
  which is exactly the comparability §5.4 Stage B ported the projected version to
  preserve. Tracked in TODO.md. **In practice, though, the measured gap on wl_stanford
  is 7 crossings and 0 reachability pairs** (table above), so the comparison is
  currently unlike-for-like in principle and equal in outcome -- a reason to fix APKeep
  for correctness, not a reason to distrust the existing wl_stanford comparison. The mistake being corrected here is not that the
  simplification was coarse; it is that it was assumed to be merely coarse rather than
  unsound in the unsafe direction.

  **LEADING HYPOTHESIS, NOW LARGELY SUPERSEDED -- do not record this as a finding.** i2's
  sources are VLAN-unconstrained (`sources.json`: `ipv4_dst=0.0.0.0/0`, no VLAN field),
  and an ad6 query is existential, so the solver may be free to CHOOSE an arriving VLAN
  that satisfies each in-stage admission gate -- whereas in the real network the
  arriving tag is fixed by the link. If so the admission gate is satisfiable by
  construction and reachability survives any amount of faithful rewrite modelling,
  which would fit every observation here. `FaithfulVlanOutRewriteWiringTest`'s fixture
  already models the VLAN-unconstrained source deliberately ("as i2 really has"), so the
  test suite would not have caught this. The witness check above confirms or kills it
  immediately; until then it is a guess.

  **COST, DIRECTIONAL ONLY (sandbox -- the ENVIRONMENT GUARDRAIL binds these figures,
  though not the verdicts above). Faithful costs ~1.26x plain per query, and the number
  this section previously implied (~550x) was an artefact of comparing a cold solver
  against a warm one.** Measured like-for-like, same pair, each as the FIRST query of
  its own run: plain 487.6 s, faithful 614.4 s -- **1.26x**. The encoding delta is
  +932,910 variables and +2,800,824 clauses over plain (the mutation constraints: 12
  VLAN bits x 78,078 nodes, 0.43% off the predicted variable count), so a modest
  per-query factor is consistent with the encoding growth. 45 minutes of wall bought
  three queries against a ~771 s fixed build cost.

  **WARM-SOLVER POSITIONAL EFFECT -- this invalidates how this section chose the three
  pairs, and it casts doubt on every per-pair reading of the archived query logs.**
  `hous->salt` is recorded at **1.11 s** in `eval/ad6_i2_cadical195_lite_72pairs_
  complete_v2.json`, and this section selected it as the cheap agreement control on that
  basis ("1.11 s (fastest of 72)"). It is index **50 of 72** in that run. The same pair,
  same PLAIN encoding, same solver, run as the first query of its own session: **487.6
  s** -- a **439x** cold/warm factor for an identical query. The other two experiment
  pairs are index 49 (`chic->salt`, 3.43 s) and 57 (`chic->seat`, 4.50 s), so all three
  were drawn from late positions in one persistent incremental session. **Consequences:**
  (a) the three pairs are not an intrinsically "fast tail" -- this section's own caveat
  about not extrapolating from them is right in outcome and wrong in mechanism; (b) the
  archived per-query `elapsed_s` values are NOT independent measurements of pair
  difficulty, so "the per-pair hardness pattern is solver-specific" (recorded further
  down from the Kissat404 comparison) needs re-examination -- it may be substantially a
  warm-up artefact. What is NOT affected: the solver-to-solver comparison itself, since
  every run used the same encoding AND the same query order, so position bias applies
  equally to all of them. **One nuance argues against the simplest warm-up story and is
  unexplained:** the archived per-quarter means are 170.0 / 182.8 / 288.7 / 128.2 s, not
  monotonic, and the three pairs sit in the SLOWEST quarter while being among the
  fastest queries in the run. So whatever makes them cheap once the solver has context is
  specific to them, not a general position trend. Learned-clause reuse is the hypothesis;
  it is untested.

  **MEMORY, corrected.** The deepcopy fix above does not lower the faithful whole-run
  peak -- the completed faithful run peaks at **18,416 MB during SOLVING**. What it
  removes is a 4.79 GB spike at the BUILD phase (`acyclic_constraints_built` 18,220 ->
  13,428 MB) that would otherwise have sat underneath DIMACS, bootstrap and the solve;
  that stacking is what made the first attempt unrunnable, and its removal is why this
  run fit. In PLAIN mode the same fix is worth **859 MB** of whole-run peak (12,572.6 vs
  the archived 13,431.9 MB), the smaller figure being exactly why it went unnoticed for
  so long. An earlier note in this session quoting ~2.1 GB for plain compared a
  `solver_loaded` checkpoint against an archived whole-run peak and should be ignored.

  **LATENT BUG, reported not fixed (out of scope, not reachable today).** In faithful
  mode any multi-port (ECMP) route makes the build raise `KeyError: '<rule>_fanout'`:
  `wire_fanout` creates that node with transitions only and no `KripkeNode`, while
  `_CreateMutationConstraints` calls `Kripke.GetNode` on every node with outgoing
  transitions. Reproduced in a 3-device synthetic IR. Measured as unreachable today, not
  assumed: the faithful wl_stanford IR has `max_ports == 1` at both N=2 and N=16 (zero
  multi-port routes), i2's out rules carry exactly one `fd=` each, and plain mode never
  builds mutation constraints. `wire_probe_fanout`'s own aggregate is safe -- it is only
  ever a transition target, never a source key. **The docstring correction this paragraph asked for is DONE**
  (2026-09-09, commit `251d8c9c`; the 11-pair finding itself was deliberately kept out of
  the code comment and lives here instead — owner decision, so the record cannot drift
  from the code). What it said, for the record — **line numbers now stale**, the
  `faithful_vlan=False` hardcode is line 132 and the result stamp line 163: line 25
  ("no VLAN modelling needed per §5.5's own C3 gate") and lines 92-95 ("whether
  faithful-VLAN modelling is even needed for i2 is gated on whether plain mode already
  matches the oracle, so this script never turns faithful_vlan on") both assert the
  inference this block invalidates, so the script currently tells its reader the
  opposite of C3's actual status. Its `"faithful_vlan": False` result stamp (line 132)
  is correct and becomes load-bearing once faithful runs exist alongside plain ones.

  **WORKLOAD-PARITY FINDING 2026-09-09 (companion to the block above, found
  independently the same day) -- the adapter-level mechanism behind that disagreement,
  and what it costs the cross-family comparison.** The block above establishes that C3's
  test is invalid and that NetPlumber disagrees on 11 pairs. Reading the model and both
  adapters answers *why* ad6 cannot see the dimension those 11 pairs turn on:
  - **The model is dst x VLAN on both sides of the stage split.**
    `bench/wl_i2/i2-json/routes.json` holds 77,841 rules: 390 `in.X` matching `vlan=N`
    and nothing else (admission), and 77,451 `out.X` matching `ipv4_dst` and carrying TWO
    actions -- e.g. `["rw=vlan:10", "fd=out.atla.120030"]`, the dst FIB AND a per-route
    egress-VLAN rewrite. `probes.json` carries the access-port untag (`vlan=0`) filter. So
    this section's earlier framing -- "i2's out-tables are a clean dst-IP FIB ... no VLAN
    modelling needed" -- is right about the MATCH side and wrong about the ACTION side:
    all 77,451 routes rewrite.
  - **NetPlumber consumes those rewrites unconditionally**
    (`netplumber/adapter.py:452-501` builds HSA rewrite+mask vectors; there is no
    faithful/collapse flag anywhere on that path), which is the mechanism behind the
    11-pair disagreement above. The NetPlumber-native transfer functions in the same
    directory confirm it independently: the out-stage tables
    (`i2-json/{11,21,...,91}.tf.json`) hold 8,383-8,864 rules EACH, all `"action": "rw"`
    with a real rewrite/mask vector.
  - **ad6 drops both halves, and the `faithful_vlan` flag is NOT the only reason.** The
    390 admission rules never become routes at all: a vlan-only match leaves
    `dst is None`, so `_translate_fwd_rule` returns early (`fave/ad6/adapter.py:326`);
    only `_capture_in_admit` survives, recording -- in its own words -- "only WHICH ports
    have any admission rule ... no VLAN modelling at all". The 77,451 `rw=vlan:M` actions
    are dropped in BOTH modes: `fave/ad6/adapter.py` has `_capture_mid_rewrite`,
    `_capture_out_reset` and `_capture_in_admission` but **no `_capture_out_rewrite`** --
    precisely what `apkeep/adapter.py:470` does have (faithful-gated, `out` stage). i2 has
    no mid stage, so `_capture_mid_rewrite` never fires either, and the IR's
    `in_port_vlan`/`out_port_vlan` maps are gated on the VLAN appearing in an ACL table --
    i2 has 0 ACLs, so both are empty. **This sharpens the prerequisite list above: a
    `faithful_vlan` switch alone is not sufficient for i2.** Turning it on today would add
    in-stage admission with no matching egress rewrite -- an incoherent model rather than
    a faithful one -- so `_capture_out_rewrite` must be written first, and that is exactly
    what C4 was scoped for.
  - **The comparison target already runs faithful.**
    `fave/test/test_apkeep_ndd_fwd.py:166` calls `_matrix(..., faithful=True)` ("out.*
    dst-FIB + rw=vlan NAT + in.* VLAN admission + probe untag") and is exact against
    `reachable.json`. That is the instance BDD-APKeep CANNOT finish (ap_num >= 19k,
    unfinished at 28 min -- see the faithful-profile bullet above); NDD builds it in ~15s.
    So NDD's i2 figure is on the hard instance and every ad6 i2 figure in this section is
    on the collapsed one.

  **Consequence for §2/§7, independent of how the experiment above turns out.** Any
  cross-family i2 statement pairing an ad6 number with a NetPlumber or APKeep/NDD number
  is not like-for-like, and the bias runs in ad6's favour -- it is solving the smaller
  problem. That specifically includes the 2026-09-06 framing "Cadical195 is now only ~13x
  slower per query, not ~57x" recomputed against Stanford. What it does NOT touch: the
  solver comparison itself (Glucose4 vs Cadical195 vs Kissat404) -- all runs used the
  byte-identical encoding, so those RELATIVE results stand; they are simply relative on an
  easier instance than the other families are measured on. Either C4 lands and the i2
  numbers are re-measured, or they are relabelled "ad6 plain-mode i2 (dst-IP only)"
  wherever they appear -- what is not available is a dst-only ad6 result sitting in the
  same table as dst x VLAN results from the other three families.

  **C0 DONE 2026-08-27 — GO, structural expectations confirmed exactly.** Built i2 through
  `Ad6Adapter(faithful_vlan=False)` via `InProcessFaVe` (`bench/ad6_i2_measure.py`, new,
  mirrors `bench/ad6_faithful_measure.py`'s instrumentation): **18 devices** (9 `in.X` + 9
  `out.X`, no `mid` — confirms `_build_ir`'s `mid`-detection correctly no-ops i2's
  `_collapse_out_stage` collapse, since no device is named `mid.*`), **9 sources / 9
  probes**, **77,460 fwd_rules** (vs. 77,841 raw routes — the small gap is ordinary
  same-(dst,ports) dedup, not data loss), **0 ACL entries** (confirms i2 is a clean dst-IP
  FIB with no ACL modelling needed, as §5.5's header predicted), replay+IR-build in ~5s.
  `ir["faithful_vlan"]` correctly absent (plain mode only, as intended — C3 gates whether
  faithful mode is ever attempted).

  **C1/C2 attempted 2026-08-27, INCONCLUSIVE on the full differential — but a decisive,
  unplanned finding surfaced along the way that changes the outlook for C2/C3.** Driving
  `bench/ad6_i2_measure.py` (same direct `src.*`-package instrumentation
  `ad6_faithful_measure.py` uses, not the subprocess bridge) through
  `favemodel.instantiate_base` → `Instantiator._CreateAcyclicConstraints` → DIMACS → 72-query
  solve:
  - **Kripke build alone: 78,078 nodes, ~351-414s (yolobox; directional only, per the
    cross-cutting guardrail).** This step completed cleanly and reproducibly across repeated
    runs.
  - **`_CreateAcyclicConstraints` (the SCC-scoped cycle-soundness rank encoding, §6/B1
    Option 2's "orders of magnitude" cost reduction for wl_stanford) did not complete within
    ~7-14 minutes of wall-clock in this environment**, on two independent attempts.
  - **Root-caused, not left as a mystery: i2's topology structurally defeats the SCC-scoping
    optimization.** A targeted probe (build + `Instantiator._ComputeSCCs` only, no
    constraint-building) found **one single non-trivial SCC containing 77,511 of 78,078
    nodes (99.3%)**, with **140,613 of 155,199 total Kripke edges (90.6%) qualifying** for
    the (expensive) per-edge rank comparator, and a comparator `Width` of **17 bits** (vs.
    Stanford's presumably small per-SCC width — Stanford's campus topology is tree/DAG-like
    enough that SCC-scoping cut its edge set "by orders of magnitude," per B1's own
    docstring). **Internet2's 9-router backbone is a dense, largely-bidirectional mesh** (matching
    `reachable.json`'s full 9x8 mesh oracle) — at the Kripke-graph level (which treats any
    edge either direction can fire as a graph edge, regardless of which packets actually use
    it) that mesh collapses almost the entire model into one giant cyclic component, so
    SCC-scoping provides almost no reduction here — essentially the opposite of the
    property (`testComputeSCCsFindsOnlyGenuineCyclesNotLongAcyclicChains`) that made it cheap
    for Stanford. This is a genuine topology-shape difference from Stanford, on top of the
    ones §5.5's header already named (no mid stage, route-table-size-dominated, no faithful
    reference) — a fourth, and arguably the most consequential for tractability.
  - **Infra note, corrected 2026-08-28:** the original "10-14 minute mystery kill" was
    initially suspected to be a sandbox process-lifetime governor unrelated to memory
    (`free` showed 13-14 GiB free at those specific moments). That theory is now RETIRED.
    Two clean isolation probes (a pure CPU-bound busy loop with flat memory, and a
    controlled-rate memory-growth loop with light CPU) each ran far past the 10-14 min
    window with zero issue — 29.3 min of accumulated CPU time, and 11GB of steadily-grown
    RSS respectively — ruling out both a CPU-time breaker and a low absolute-RSS ceiling.
    The real mechanism, confirmed directly below, is genuine OOM: it just happened to bind
    at different absolute RSS/time values across runs depending on what else was resident
    in the sandbox at the time. `bench/ad6_i2_measure.py`'s per-phase checkpointing (writes
    partial JSON + stderr progress after each build stage) remains valuable for exactly
    this reason — it is what let this be root-caused instead of staying a mystery.
  - **RESOLVED 2026-08-28 — NO-GO at this scale, root-caused as genuine memory blowup, not
    a sandbox artifact.** `Instantiator._CreateAcyclicConstraints` gained an optional
    `ProgressCallback` parameter (backward-compatible, default `None`, all existing callers/
    tests unaffected — 6/6 `Acyclic`/`SCC` unit tests still pass) so `bench/ad6_i2_measure.py`
    could checkpoint the edge loop itself, not just its start/end. Re-running the full
    build with this instrumentation reproduced the kill cleanly: RSS grows **linearly at
    ~0.14 MB per SCC-qualifying edge** (measured from edge 997 at 3.06GB to edge 82,363 at
    14.44GB), and the process was confirmed genuinely OOM-killed — exit 137, host
    `available` memory measured at ~20MB immediately before the kill, fully recovered to
    14GB free immediately after — at **82,363 of 140,613 qualifying edges (58.6%)**.
    Linear extrapolation to the full edge set projects **~22GB just for this phase's
    constraint list** (before DIMACS conversion or solving even begin, which would add
    more on top). This is a real, quantified intractability of the current per-edge
    lxml/Tseitin CNF-conversion approach at i2's scale (140,613 qualifying edges, a
    consequence of the giant-SCC finding above), not a sandbox limitation and not
    "merely slow" — 22GB does not fit this yolobox (15GB total) and would strain even a
    well-provisioned bare-metal box once DIMACS conversion and solving are added. **C2 is
    NO-GO for i2 with the current SCC-scoped rank encoding as-is.** A fix would need either
    a fundamentally cheaper per-edge clause-construction path (the generic
    `SATUtils.ConvertToCNF` machinery is the likely source of the per-edge overhead, not
    the CNF clause count itself) or a different acyclic-safety strategy for i2's
    mesh-shaped topology than the one that worked for Stanford's tree-like one.
  - **C2 construction fix landed and validated 2026-08-28 — `Instantiator.
    _CreateAcyclicConstraintsLite`.** Hand-derives the IDENTICAL clause set
    `_CreateAcyclicConstraints` produces (traced by hand through `SATUtils.ConvertToCNF`'s
    actual transformation rules: every implication here reduces to negate-antecedent +
    distribute-over-an-at-most-2-literal-disjunction consequent, no Tseitin aux vars
    beyond the eq_i/gt_i already built explicitly — always exactly `6*Width-1` clauses per
    edge) as plain `(name, negated)` tuples, bypassing `lxml`/`SATUtils.ConvertToCNF`
    entirely. Proven equivalent, not just plausible, by
    `testAcyclicRankConstraintLiteMatchesGeneralEncoding` (exact clause-SET equality
    against the general encoding on the same genuine-cycle fixture
    `testAcyclicRankConstraintScopesToNonTrivialSCCsOnly` uses). Measured on real i2:
    full 140,613-edge set (14,201,913 clauses — exactly `101 = 6×17-1` per edge, confirming
    the hand-derivation precisely) builds in **~15-20s, peaking ~8.5GB** (was: OOM before
    60% done, ~22GB projected). `bench/ad6_i2_measure.py --lite-acyclic` wires this in;
    downstream DIMACS conversion resolves the lite clauses' variable names through the
    same `index_for` registry the query loop already uses (can't splice raw literal
    tuples into the lxml-based `Encoding[0]` list the general path extends).
  - **A second, separate bottleneck surfaced once construction was fixed: SOLVING the
    resulting instance (6.3M variables, 14.9M clauses) does not resolve even the first
    query in any practical time.** First attempt: 79+ minutes, no result, host memory
    exhausted into heavy swap thrashing (Minisat22, single-threaded). Root-caused the
    memory side of this too: checkpoints straddling solver construction show **~91% of
    pre-solve memory (11.1 of 12.16GB) is Python-side state that Minisat22 never
    touches** (the base `encoding`/`combined` lxml tree and its deepcopy, the `config`
    tree, the raw `variables`/`dimacs_clauses` Python lists) — `Minisat22(bootstrap_with=
    ...)` itself only added ~1GB. `favemodel.instantiate_base`'s own docstring confirms
    `config` is provably dead after it returns (builds `kripke`, `structure.py`'s
    self-contained dict-based structure, with no back-reference into `config`), and
    `pysat/solvers.py`'s `Minisat22.new()` just iterates `bootstrap_with` calling
    `add_clause` per entry, retaining no reference to the list itself — so all of this is
    safe to explicitly `del`+`gc.collect()` (lxml parent/child links are reference
    cycles; plain `del` alone isn't enough) right after each is last used, well before
    the solver is ever created. Landed in `bench/ad6_i2_measure.py`; a same-shape rerun
    with this fix in place stayed at a healthy ~11GB RSS / several GB host headroom with
    no swap growth well past the point the first attempt was already thrashing —
    confirms the release genuinely helps, even though the immediate before/after delta at
    each individual deletion point was modest (the win is cumulative, from never holding
    everything simultaneously, not from any single large free).
  - **Whether i2's SAT instance is fundamentally hard at this scale, or just needs a
    better-suited solver, is the open question — plan below, not yet executed as of this
    writing.** Confirmed the query loop's solving *architecture* is already right, not
    naive: it's structurally the same "bake base+acyclic constraints in once, DIMACS
    once, one persistent incremental Minisat22 instance, per-query OR-gate + assumption
    solve" pattern `src/solver/incremental.py`'s `IncrementalSession` formalizes for
    `fave_bridge.py` — which itself superseded `Instantiator.SolveAcyclicEndToEnd`'s
    lazy CEGAR-style escalation after empirically beating it (0 mismatches, rescued
    wl_stanford's own B1 wall-clock NO-GO, ~100-490x faster on wl_up). So re-introducing
    lazy escalation would be a regression, not a fix. But `IncrementalSession`'s own
    docstring calls the bake-in-unconditionally approach cheap "on an essentially-acyclic
    real topology like wl_up/wl_ifi/wl_tum" — i2, with 90.6% of ALL Kripke edges
    qualifying for the expensive comparator (vs. Stanford's much smaller genuinely-cyclic
    fraction), is a more extreme case than anything this architecture has been validated
    against. **Plan: systematically compare SAT backends before concluding i2 is
    intractable outright**, since the current `Minisat22` (PySAT's 2.2-vintage default)
    is a real, cheaply-testable variable, not yet controlled for:
    1. **Isolate the variable.** Add a `--solver` flag to `bench/ad6_i2_measure.py`
       selecting from a small `{name: pysat.solvers class}` registry, default `minisat22`
       (byte-for-byte unchanged behavior) — every other input (lite-acyclic encoding,
       DIMACS clauses, query order) stays identical, so any outcome difference is
       attributable only to the backend.
    2. **Shortlist, not the full PySAT catalogue.** `Minisat22` (baseline), `Glucose4`
       (widely-used glue-clause CDCL), `Cadical195`, `Kissat404` (both modern,
       competition-grade, heavy preprocessing/inprocessing) — four solvers spanning
       different solving generations/strategies, not an exhaustive sweep.
    3. **Cheap probe before expensive commitment.** Don't run the full 81-query set per
       candidate up front — build+construct+DIMACS+load+**first query only**, each capped
       at a short budget (~15-20 min; if a backend is dramatically better it should show
       *some* sign well inside that window, not need hours to prove itself). Only a
       candidate clearing this gate graduates to a full-query-set attempt.
    4. **Sequential, not parallel** — this yolobox has ~15GB total RAM; running multiple
       multi-GB solver processes concurrently would reintroduce the exact swap-thrashing
       risk just fixed.
    5. **Metrics per candidate:** resolved-within-cap (bool), wall-clock, peak RSS,
       solver-load time separated from solve time, and — for any two that both resolve —
       cross-check they agree on the SAT/UNSAT verdict (a disagreement would mean a bug in
       the PySAT invocation, since it's the identical CNF either way, not a real result
       difference).
    6. **Decision gate:** a candidate that resolves quickly escalates to the full query
       set as the new C1/C2 measurement. If none resolve within the short probe, that
       itself is informative — i2's hardness isn't solver-choice-sensitive, and the next
       lever has to be the encoding/formula itself, not the backend.

  **EXECUTED 2026-08-28 — sobering result: the query-1 probe was necessary but not
  sufficient, and doesn't generalize.** `--solver`/`--max-queries` landed in
  `bench/ad6_i2_measure.py` (registry of 4 PySAT backends, default `minisat22` unchanged).
  First-query-only probes: **Kissat404 DISQUALIFIED outright** — PySAT emits `RuntimeWarning:
  Kissat does not support assumptions. The assumptions parameter will be ignored`
  (confirmed in Kissat's own PySAT docstring, the only one of the four with this
  restriction) — its apparent win (0.334s, `oracle_match: True` on a 1-query slice) is a
  worthless artifact: with assumptions ignored, every query just resolves the same
  unconstrained base formula, and a constant "yes" trivially matches
  `reachable.json`'s all-reachable, zero-negative-pairs oracle by construction, exactly the
  discriminating-power gap already flagged for the `--skip-acyclic` orientation check
  above. Of the three genuinely assumption-supporting backends, **Glucose4 (0.704s) and
  Cadical195 (2.386s) both resolved query 1 fast** — Minisat22 (baseline) had not resolved
  it in 90+ minutes.

  Escalating the two valid winners to the full 81-query set did NOT reproduce the win:
  **both Glucose4 and Cadical195 resolved query 1 then hung identically** — no further
  per-query progress checkpoint (fires at query 10 or completion) within a 30-minute cap
  on either, timed out (`exit 124`) with the process still pegged at 99.9% CPU throughout,
  no memory pressure (healthy 3+ GB free both times, so this is pure SAT search time, not
  another memory blowup). So the query-1-only probe measured something real but not
  representative: SOME later query (or the cumulative effect of many incremental
  `solve(assumptions=...)` calls adding OR-gate clauses without ever removing old ones —
  the session never resets between queries) reintroduces hardness that isn't
  solver-specific after all. **Not yet root-caused which:** per-query checkpointing
  currently only fires every 10th query, so it's unknown whether one specific
  source/destination pair among queries 2-9 is uniquely hard, or whether difficulty climbs
  gradually with each additional query's incremental state. Next diagnostic step (not yet
  done): checkpoint every query (not every 10th) for a few queries past the first to
  localize this precisely, the same "instrument before re-theorizing" discipline that
  root-caused the C2 memory blowup.

  **LOCALIZED 2026-08-28, and corrects the framing above: not an infinite hang, genuinely
  slow and highly variable per-query solving.** Added `--checkpoint-every` to
  `bench/ad6_i2_measure.py` (checkpoints every query, records the exact `(source, probe)`
  pair) and re-ran (Glucose4, lite-acyclic, 30-min cap). Query 1 is `(atla, atla)` — a
  SELF-pair (`sources`/`probes` both alphabetically sorted, `atla` sorts first in both) —
  resolving trivially in 0.76s regardless of backend; the earlier "query 1 is fast"
  finding was an artifact of accidentally probing the one trivial query, not a real
  cross-router one. Query 2, the first genuine cross-router query, took **~11.7 minutes**;
  query 3 took **~2.5 minutes**; query 4 was still unresolved when the 30-minute cap
  fired. So this is real, highly variable, multi-minute-per-query SAT search time, not a
  stuck/infinite state — extrapolated across the 72 non-trivial pairs, a full run
  plausibly needs many hours total, which is why the earlier 2-hour-capped full runs
  (Sec 5.5, solver-comparison result above) never completed: they simply needed
  more time, not that anything was actually hung. This narrows the open question from
  "does it ever finish" to "how many hours does it actually need, and does that scale
  further with a bigger topology" — still unanswered, and still independent of which of
  Glucose4/Cadical195 is used (both showed the same order-of-magnitude per-query cost on
  their own capped attempts).

  **C1 RESOLVED 2026-09-05 — full 72-pair differential completed and EXACTLY matches the
  oracle, with the acyclic-safety fix genuinely active.** Three staged runs (Glucose4,
  `--lite-acyclic`, `--checkpoint-every 1`), each isolating one variable:
  1. **The 9 self-pairs alone, 30-min cap**: all 9 completed in 112s total (~12.5s/query
     average) — confirms self-reachability really is trivial, independent of the rest of
     the instance (`fave/bench/wl_i2/eval/` has no separate artifact for this one, it was
     a quick sanity check, not archived).
  2. **The 72 real cross-router pairs, 12h cap**: got to 68/72 before the cap fired --
     genuinely still working, not stuck (confirmed via `--checkpoint-every 1`'s per-query
     log). Kept as `eval/ad6_i2_glucose4_lite_72pairs_partial68of72.json` for reference.
  3. **Same 72 pairs, 16h cap**: **completed all 72** in 55,073s (~15.3h) --
     `oracle_match: true`, `oracle_missing: {}`, `oracle_extra: {}`, `reachable_pairs: 72`.
     Peak RSS 12.78GB, swap never touched. Archived as
     `eval/ad6_i2_glucose4_lite_72pairs_complete.json`.

  This is a materially stronger result than the earlier `--skip-acyclic` orientation
  check (which matched 72/72 too, but with the floating-cycle safety machinery OFF, so a
  match there couldn't rule out that failure mode at all -- see that finding's own
  caveat above). Here the real acyclic rank constraints were active throughout, and the
  result still matches exactly -- positive evidence the fix doesn't introduce false
  negatives (over-constraining) at full scale, on top of the clause-level equivalence
  `testAcyclicRankConstraintLiteMatchesGeneralEncoding` already proved. **C1 is
  accordingly GO for i2**, on the experimental lite encoding + Glucose4.

  **C2 (tractability) stays a real, separate, still-open concern: this is correct, but
  far too slow for practical use.** ~15.3 hours for 72 pairs vs. Stanford's ~16 minutes
  for its full 256-pair matrix (Sec 5.4 B1, `IncrementalSession`) is roughly three
  orders of magnitude slower per query, on a smaller topology. Per-query cost was
  extremely variable throughout (sub-second to 80.3 minutes, no clear trend across the
  run), so it isn't one identifiable pathological pair -- it's the instance in general.
  Whether this is inherent to i2's mesh-shaped, giant-single-SCC topology (Sec 5.5's own
  giant-SCC finding) or a further encoding/solving lever could still bring it down
  (Sec 8.6's scoped architecture tracks, or a lower-level SAT-solver tuning pass) is not
  yet known -- C1's GO does not imply C2/C3/C4 are unblocked, only that correctness
  itself is no longer in question for this path.

  **C2 update 2026-09-06 -- solver choice materially changes the tractability picture,
  and single-query probes still don't predict it.** Ran the same full 72-pair set
  (`--lite-acyclic`, `--checkpoint-every 1`) with Cadical195, the other
  assumptions-capable candidate from the solver-comparison shortlist that had only been
  probed on query 1 before (2.386s there, vs. Glucose4's 0.704s -- Cadical195 looked
  *worse* on that single data point). Full run: **completed in 12,821s (~3.56h)**,
  `oracle_match: true` (72/72, 0 missing/extra) -- both correct, but **~4.3x faster than
  Glucose4's 15.3h**, with a materially tighter distribution too: avg 178.0s (3.0 min,
  vs Glucose4's 755.7s/12.6 min), max 1877.2s (31.3 min, vs Glucose4's 4820.8s/80.3 min).
  So the single-query probe's ranking (Glucose4 > Cadical195) INVERTED at full scale --
  reinforcing Sec 5.5's own earlier lesson that a first-query probe is necessary but not
  sufficient, this time in the solver-selection dimension specifically, not just the
  "does it hang" one. Recomputed against Stanford's ~16 min/256-pair baseline: Cadical195
  is now only ~13x slower per query, not ~57x -- still a real, unresolved tractability
  gap, but a substantially smaller one than the Glucose4 number alone suggested. Archived
  as `eval/ad6_i2_cadical195_lite_72pairs_complete.json`. Worth trying the remaining
  shortlisted backend (none left untested among the assumptions-capable ones -- Minisat22
  never got past query 1, Kissat404 is disqualified) if a further solver-side lever is
  wanted; otherwise Cadical195 is now the better default for any further i2 full-run
  work on this path.

  **C2 follow-up 2026-09-08 -- Kissat404 workaround found (disqualification was
  architecture-specific, not fundamental); a real per-query timing gap closed; and the
  resulting data answers "is it always the same queries" -- yes, and it tracks
  Internet2's geography.**

  **Kissat404 isn't fundamentally unusable, just incompatible with the persistent-session
  architecture.** It was disqualified above because PySAT's wrapper ignores its
  `assumptions` parameter (Kissat has no native incremental API -- `incr=True` raises
  `NotImplementedError` in PySAT's own constructor). But the persistent-session
  architecture's own `solver_load_s` measurements (Cadical195's run: 7.186s to bootstrap
  a fresh solver from the full 14.9M-clause `dimacs_clauses` list) show that a full
  reload is cheap relative to the 100s-800s/query solve times already measured --
  cheap enough that a genuinely non-incremental solver becomes viable if it gets a
  FRESH solver per query instead of reusing one via assumptions. Added
  `--fresh-per-query` to `bench/ad6_i2_measure.py`: bakes the source/dest OR-gate
  literals in as unit clauses on a freshly-bootstrapped solver each query (no
  assumptions needed), keeping `dimacs_clauses` resident across queries instead of
  freeing it (checked first: freeing it after the persistent solver's initial load only
  recovers ~160MB out of ~11GB resident, so retaining it is not the memory risk that
  free's own comment implies). One-query probe on a real cross-router pair
  (`chic->atla`, `--pair-filter exclude-self --max-queries 1`): solved in 279.7s + 4.9s
  reload -- landing close to Cadical195's own per-query average (178.0s), so not a clear
  win on this single sample, but not disqualifying either. A full 72-query Kissat404 run
  was not executed (deprioritized below in favor of closing the timing-history gap
  first); still open if a further solver-side lever is wanted.

  **A real instrumentation gap, found and fixed: neither archived full run ever recorded
  more than its LAST query's timing.** `last_query_s`/`last_query` are overwritten every
  checkpoint -- even with `--checkpoint-every 1`, the on-disk JSON only ever retains the
  final query's numbers. So the "per-query cost was extremely variable throughout... no
  clear trend across the run" / "no pathological pair identified" conclusions logged
  2026-09-05/06 were from watching the live stderr scroll during those multi-hour runs,
  not from saved data -- neither archived file could actually be queried for a pattern.
  Added `result["query_log"]`, appended every query regardless of checkpoint cadence:
  `{index, source, probe, elapsed_s, solver_load_s, sat}` -- cheap (72 small dicts), and
  the on-disk WRITE cadence stays gated by `--checkpoint-every` so this adds no
  meaningful I/O overhead to a long run.

  **Reran the full 72-pair Cadical195 set with this instrumentation** (same
  `--lite-acyclic --pair-filter exclude-self --checkpoint-every 1`, archived as
  `eval/ad6_i2_cadical195_lite_72pairs_complete_v2.json`): **completed in 14,896s
  (~4.14h)**, `oracle_match: true` again (72/72, 0 missing/extra) -- correct, but
  noticeably slower than the original run of the IDENTICAL instance/solver/encoding
  (12,821s / ~3.56h, 2026-09-06) -- a real ~16% run-to-run wall-clock variance to keep in
  mind for any single-run number this investigation has reported, not just a
  cross-solver effect.

  **The pattern, finally checked against real data: query cost tracks topological
  distance through the backbone, not run position.** Correlation between query index
  (position in the persistent incremental session, i.e. accumulated OR-gate clause
  count) and elapsed time: **0.01** -- ruling out "queries get harder as clause bloat
  accumulates" as an explanation. Per-router means instead show real structure that
  lines up with Internet2's geography:

  | router | mean as SOURCE (n=8) | mean as DESTINATION (n=8) |
  |---|---|---|
  | `newy32aoa` (New York) | 321.3s | 380.5s |
  | `losa` (Los Angeles) | 296.3s | 430.0s (slowest destination) |
  | `hous` (Houston) | 144.1s | 165.3s |
  | `chic` (Chicago) | 230.2s | 87.4s (fastest destination) |

  (overall: mean 206.9s, median 133.2s, stdev 290.5s, n=72.) **The single hardest pair in
  the entire set is `losa`↔`newy32aoa` in BOTH directions** -- `losa->newy32aoa`=1688.8s
  (rank #1), `newy32aoa->losa`=1460.2s (rank #2) -- the two most geographically distant
  endpoints on the backbone (west coast/east coast). The fastest queries are dominated by
  `hous` at either endpoint (`hous->salt`=1.1s, `hous->kans`=2.6s, the two fastest
  overall) and other short/central hops (`kans->chic`=3.1s, `chic->salt`=3.4s). ~~**Working
  hypothesis:** hardness tracks how much of the giant SCC a source→destination witness has
  to traverse.~~ **FALSIFIED same day, see below -- this was an ungrounded read of city
  names, not a checked claim.**

  **CORRECTION 2026-09-08, same day -- the topological/geographic-distance hypothesis
  above does NOT survive being checked against the actual graph.** Built
  `bench/ad6_i2_query_distance.py`: no SAT solving at all, just the same Kripke graph
  every C1/C2 run already builds (~5-6 min, the dominant cost either way), then three
  cheap graph-theoretic probes correlated against the `query_log` timings above:
  - **Shortest-path hop count** (BFS from each query's source node to its destination
    node, treating either transition flag as a graph edge -- same convention as the
    giant-SCC finding's own "any edge either direction can fire" definition): `corr =
    0.167`. Weak, and directly contradicted by counterexamples -- `hous->salt` is the
    FASTEST query overall (1.1s) despite 44 hops; `chic->seat` takes only 4.5s despite 87
    hops (the second-highest hop count in the set).
  - **OR-gate fan-in** (the exact literal count each query's destination OR-gate clause
    gets -- `ad6_i2_measure.py`'s own `b_trans`/`or_gate`): fan-out is uniformly 1 (every
    source has exactly one injection point, as expected), fan-in ranges 18-36 with `corr
    = -0.098` -- no better than noise.
  - **Forward-reachable-from-source ∩ backward-reachable-to-destination set size** (two
    BFS passes per query, no solving -- "how many nodes could plausibly appear on ANY
    witness path", not just the shortest one): ranges **77,521-77,533 out of 78,078 total
    nodes** -- essentially flat, a direct consequence of the giant-SCC finding itself
    (99.3% of nodes in one SCC means forward/backward-reachable sets are both "almost the
    whole graph" regardless of which specific pair is queried). `corr = -0.036`.

  **Honest conclusion: the `losa`↔`newy32aoa` bidirectional extreme is real and
  reproducible (very unlikely to be coincidence -- ranking #1 and #2 of 72 in both
  directions), but none of position, hop-distance, OR-gate size, or reachable-set size
  explain it.** The mechanism is more likely rooted in the SAT solver's internal search
  dynamics for this specific instance (clause-learning/variable-branching interactions
  with the acyclic rank encoding) than in any static graph property -- checking that
  further would need solver-internal instrumentation (PySAT's own conflict/decision/
  propagation counters per query), which requires an actual solve and so reintroduces the
  multi-hour cost this diagnostic line was specifically trying to avoid. Left open rather
  than chased further; not blocking C3/C4.

  **Caveats on the underlying pattern, stated plainly:** n=8 samples/router with
  heavy-tailed distributions (stdev routinely exceeds the mean -- e.g. `probe.losa`
  stdev=523.5 on a mean of 430.0), so treat the per-router means as a qualitative signal,
  not a rigorous statistical claim; the bidirectional agreement on the single hardest
  pair is the more load-bearing piece of evidence. And this is **Cadical195-only** --
  Glucose4's archived run predates `query_log` and has no per-pair record, so whether the
  SAME pairs are hardest under Glucose4 is still unconfirmed (plausible, given both
  solvers already showed "the same order-of-magnitude per-query cost" in aggregate, per
  the 2026-09-06 update above, but not verified pair-for-pair).

  **KISSAT404 FULL-RUN ATTEMPT 2026-09-09 -- the last untested shortlisted backend is
  ~2.9x SLOWER than Cadical195, and per-pair hardness does NOT transfer between solvers.**
  Ran the `--fresh-per-query` workaround at full scale (`--lite-acyclic --pair-filter
  exclude-self --checkpoint-every 1`, identical encoding/order to the Cadical195 v2 run so
  the `query_log`s are comparable pair-for-pair), under a 6h cap. **Reached 36 of 72 pairs
  before the cap fired** (`timeout` rc=124); archived as
  `eval/ad6_i2_kissat404_lite_freshpq_partial36of72.json`. Note its `status` field still
  reads `running:querying` -- SIGTERM landed between checkpoints, and the file is the
  process's own last write, left unedited rather than doctored to a terminal state.
  - **Paired comparison on the same 36 pairs, solve time only** (reload excluded, so
    Kissat is not charged for the workaround): Kissat404 18,500s (mean 513.9s, median
    375.0s, stdev 444.3s) vs Cadical195 6,427s (mean 178.5s, median 121.0s, stdev 208.5s)
    -- **2.88x slower**. The reload tax the `--fresh-per-query` architecture adds is
    5.56s/query, **1.1% of query wall**, so the loss is real solving cost, not the
    workaround. All 36 answers SAT, no oracle divergence on the prefix.
  - **So the solver-side lever is exhausted.** All four shortlisted backends now have a
    verdict at i2 scale: Minisat22 never resolved past query 1; Glucose4 ~15.3h/72;
    Cadical195 ~3.56h and ~4.14h/72; Kissat404 ~2.9x Cadical, extrapolating to ~11h/72.
    **Cadical195 stands as the best available backend for i2 and no untested candidate
    remains**; any further tractability gain has to come from the encoding (§8.6, and
    Axis 1's Tseitin result in AD6_ENCODING_PLAN §3.1), not the backend.
  - **The per-pair hardness pattern is solver-specific, which settles the question the
    `query_log` was added to answer.** Pearson correlation between the two solvers'
    times on the same 36 pairs is **0.199** -- essentially none. Inversions run both
    ways and are large: `losa->kans` 52.6s under Cadical vs 1231.6s under Kissat
    (23.4x), `newy32aoa->atla` 84.9s vs 1215.2s (14.3x), while `seat->hous` is 483.5s
    under Cadical and only 126.1s under Kissat (0.26x) and `kans->atla` 639.1s vs 376.8s
    (0.59x). **This corroborates the 2026-09-08 falsification from the other side:** no
    static graph property explained Cadical's `losa`↔`newy32aoa` extreme because the
    hardness is not a property of the instance at all -- a second solver on the identical
    CNF disagrees about which pairs are hard. What survives is weaker and worth stating
    exactly: `losa` appears in the top pairs of BOTH solvers (Kissat's #1/#2 are
    `losa->atla` 1344.6s and `atla->losa` 1341.9s, bidirectional like Cadical's
    `losa`↔`newy32aoa`), so `losa` may be a genuinely awkward endpoint while its worst
    partner is solver-search-dependent. Any §7 claim about "hard pairs" in i2 must be
    attributed to a specific solver.

  **UPDATE 2026-09-12 -- THIS WHOLE COMPARISON IS RANK-ENCODING-SCOPED, AND ITS OWN CLOSING
  PREDICTION WAS RIGHT.** Every number above was measured under the rank encoding
  (`--lite-acyclic`) on the PLAIN model. That was never stated because at the time there was
  only one encoding; it has to be stated now, because the flow encoding (§7.5/§7.5c) changes
  the conclusions in two different directions.

  - **The prediction lands, by a larger margin than it anticipated.** This section closed
    with *"any further tractability gain has to come from the encoding, not the backend"*.
    It does: same model, same solver, same 72 pairs, swapping only the grounding constraint
    gives **9.0-10.8x wall and 6.0x peak RSS** (§7.5b). The encoding was the right lever and
    the solver was not.
  - **"Minisat22 never resolved past query 1" is an artifact of the ENCODING, not of the
    backend.** Under the rank encoding it had not resolved query 1 in 90+ minutes, which is
    why it was struck from the shortlist. Under the flow encoding the same backend answers
    **all 72 plain queries in 1,451 s of solving (~20 s/query)**. So the shortlist's
    conclusion -- "Cadical195 stands as the best available backend for i2 and no untested
    candidate remains" -- must be read as scoped to the rank encoding. Under flow,
    cadical195 still wins on i2 but only by 1.65x (plain) / 1.18x (faithful), and on
    wl_stanford minisat22 wins outright. **A backend disqualified under one encoding can be
    competitive under another; the shortlist was never a property of the solvers alone.**
  - **The per-pair-hardness conclusion SURVIVES -- and a confound that could have broken it
    is now identified.** Cross-solver correlation under the flow encoding, cadical195 vs
    minisat22 on identical CNF:

    | flow run | n | cross-solver correlation |
    |---|---:|---:|
    | plain (all SAT) | 72 | **-0.076** |
    | faithful, pooled | 72 | **0.587** |
    | faithful, SAT-only | 61 | **0.206** |
    | faithful, UNSAT-only | 11 | **-0.128** |

    The pooled faithful figure looks like a refutation of "hardness is solver-specific" and
    is not. **UNSAT pairs are intrinsically expensive -- 6.6x the mean SAT cost under
    cadical195 (122.15 s vs 18.53 s) and 7.4x under minisat22 (152.45 s vs 20.55 s)** --
    because a refutation has to exhaust the search space while a witness can be found by
    luck. Both solvers agree the 11 unreachable pairs are the dear ones, and pooling the two
    satisfiability classes creates a two-cluster structure that inflates the correlation.
    Split them and the correlation collapses back to noise in BOTH classes, matching the
    plain model and the archived rank figure.

    **So the statement to carry into §7 is sharper than the original:** satisfiability class
    is a genuine instance property with a ~7x cost effect; per-pair hardness WITHIN a class
    is a solver-search artifact. And the methodological rule: **never compute a per-pair
    hardness correlation over a mixed SAT/UNSAT set** -- it measures the class split, not
    the pairs. (The 0.199 above is unaffected: plain i2 is an all-reachable mesh, so it was
    already an all-SAT measurement. It was clean; it was just never scoped as such.)
  - **Open curiosity, cheap to check, deliberately not chased:** Kissat's three slowest
    queries cluster within 4.9s of each other (1339.7s / 1341.9s / 1344.6s -- a 0.4%
    spread) despite finishing at 13:54, 15:32 and 11:33 respectively, i.e. before,
    during and after the swap episode below, so it is not a memory artifact. A tight
    ceiling like that looks more like an internal Kissat bound than coincidence.
    Re-running one of those pairs alone (`--pair-filter exclude-self --max-queries`
    plus a pair selector, which does not exist yet) would confirm or dismiss it in ~25
    min; not done.
  - **Memory: `--fresh-per-query` is CHEAPER than the persistent session on this
    instance, the opposite of the expectation its own code comment sets up.** Peak RSS
    12,075 MB vs 13,432-13,464 MB for the two persistent Cadical runs -- retaining the
    ~11GB `dimacs_clauses` list and rebuilding a solver every query costs less than one
    persistent solver accumulating OR-gate clauses across 72 queries, and it was flat
    across 36 bootstrap/delete rounds (no leak). One caveat on that number: the kernel
    did evict ~4GB to swap mid-run (13:28-~16:00, the full 4GB device) and faulted it
    back in later, and `ru_maxrss` counts only resident pages, so 12,075 MB slightly
    understates the true footprint (~11.6GB observed as RSS+swap at the low point).
    Timings are unaffected -- reload times stayed flat at 4.4-6.7s throughout, including
    post-eviction, and the paired ratio was if anything better after (2.55x, n=16) than
    before (3.11x, n=19).

  - **Cheap orientation check DONE 2026-08-27 (`--skip-acyclic` flag added to
    `bench/ad6_i2_measure.py`): full-scale plain-mode reachability, WITHOUT the acyclic
    constraints, EXACTLY matches `reachable.json` — 72/72 pairs, 0 missing, 0 extra.**
    Completed in a single ~6.4 min run (well inside this sandbox's apparent process-lifetime
    ceiling, since it skips the expensive stage entirely): build 337.7s, DIMACS 2.3s
    (243,361 variables, 681,216 clauses), 81 queries (72 cross-role + 9 self, self excluded
    from the reported count) in 40.1s, peak RSS 3.38 GB.
    **Important caveat on what this does and does NOT establish:** `bench/wl_i2/reachable.json`
    is a COMPLETE all-reachable mesh (every one of the 9x8 ordered pairs is expected
    reachable, zero expected-unreachable pairs). The floating-cycle bug the acyclic
    constraints defend against manifests as a FALSE-POSITIVE SAT (reporting reachable when
    it truly isn't) — with no expected-unreachable pair in this oracle at all, this dataset
    has **zero discriminating power** to catch that failure mode; a spurious SAT on an
    already-truly-reachable pair is invisible here by construction. So this result is a
    genuine, valuable data point (i2's plain forwarding logic is translated correctly — the
    adapter/translator itself is validated) but it is **not** evidence that skipping the
    acyclic-safety fix is sound for i2, and must not be read as such. A real soundness
    verdict still needs either (a) the full acyclic-constrained run to actually complete, or
    (b) some expected-unreachable i2 pairs to test against (none exist in the current
    benchmark's checks — `cchecks.json`'s own reach-only structure would need checking for
    whether any negative checks exist at all before concluding this path is unavailable).

---

## 6. Algorithmic lever — amortise the O(n²) toward O(n) — CONFIRMED 2026-08-24/25

Directly attacks Factor A: for a fixed source, solve the n destination queries under solver
**assumptions**, reusing learned clauses across them — a warm single solver session
approximating a flood — collapsing O(n²) toward ~O(n). Measures "how close a generic solver
gets to a domain-specific flood by amortising."

**Answered empirically, not just measured-then-deferred**: a parallel investigation
(`AD6_ENCODING_PLAN.md`, harness in `ad6_encoding_bench/`, kept deliberately separate from
this document's own working files while both were active) ran the lever against the real
wl_up FaVe+ad6 model (137 generators/probes, 5,977 Kripke nodes) and its full real
`bench/wl_up/cchecks.json` (11,902 queries, 3,302 stateful `<->>`), not a synthetic proxy:

- Assumption-based incremental solving over one shared base gives **near-flat scaling in
  query count** (confirmed first on a controlled synthetic case, then survives genuine
  cross-source variation — both source AND destination varying every query, the real shape
  of `InstantiateEndToEnd`/`SolveAcyclicEndToEnd` — not just fixed-source flooding).
- At wl_up's real scale, full query set, **exact-match-correct against ad6's own current
  answers throughout**: Z3 incremental **71–102s** (two independent full runs) vs. an
  extrapolated **~2 hours** for ad6's current per-query-fresh-solve architecture and **~42
  min** for a fresh-Z3-per-query control — **~100–140× faster**.
- The lever is **not Z3/SMT-specific**: ad6's own solver family (Minisat), driven via its
  real native incremental library API (PySAT's `Minisat22`, not a CLI subprocess) — **16.6s
  for the full 11,902-query set, ~490× faster** than the extrapolated current-architecture
  baseline.
- **Separable finding, smaller and lower-risk, does not require adopting incrementality at
  all**: tracing the real production call path (`Instantiator.InstantiateEndToEnd` →
  `AbstractSolver.Solve`/`_ConvertToDIMACS`, `ad6/fave_bridge.py`'s query loop) found that
  every query today pays for a `deepcopy()` of the *entire* base CNF (an lxml tree — tens
  of thousands of clauses at wl_up scale) plus a full from-scratch Python-level DIMACS
  variable-renumbering pass, on top of the actual solve — independent of solver choice
  (`fave_bridge.py` already calls `pycosat`, a native library, not a CLI subprocess; there
  is no "swap CLI for a library" win available here, that framing was a mischaracterization
  caught while scoping this section). Caching the base DIMACS mapping once per run and
  converting only each query's small delta — same solver, same correctness properties, no
  architecture change — is a cheaper first step available independent of the incremental-
  solving decision.
- **Stanford follow-up, DONE 2026-08-27 — the lever survives real cyclic-topology
  rank-constraint escalation cost, the thing wl_up's result above couldn't speak to at
  all** (`AD6_ENCODING_PLAN.md` §3.10, `AD6_PLAN.md` §5.4's B1 write-up, "fourth item"):
  baking the SCC-scoped rank constraints B1's own escalation path uses into a persistent
  incremental solver's base once, then answering all 256 real Stanford source→probe pairs
  as single assumption-checks, completed the entire real all-pairs matrix in **~16.2
  minutes** (971.09s), 0 mismatches against ad6-real's own answers — against B1's own
  measured 6-hour/28.9%-complete result and ~20-21h extrapolation for a full run. Getting
  there took three attempts (Z3's term-based construction never completed even one solve
  in 90 minutes on this instance — a Z3-specific limitation, not evidence against the
  lever; a flat-DIMACS/PySAT-Minisat22 construction, architecturally matching what already
  gave the wl_up win, succeeded cleanly) and surfaced an unrelated, still-open C-stack
  overflow robustness bug in `SolveAcyclicEndToEnd`'s escalation path (see B1's write-up's
  "third item"). Scope caveat: answers the reachability question correctly and fast, but
  doesn't by itself complete `test_ad6_wl_stanford.py`'s own differential-against-
  NetPlumber comparison (a natural, cheap next step, not yet done), and is still a
  benchmark-harness reconstruction, not a `fave_bridge.py`/`Instantiator` production
  change.
- **Applied to production 2026-08-27.** `ad6/src/solver/incremental.py`
  (`IncrementalSession`) is the new production implementation of everything above: builds
  the base encoding once, bakes the SCC-scoped acyclic rank constraints in
  *unconditionally* (no more lazy escalation — sound by construction, no CEGAR needed, per
  `_CreateAcyclicConstraints`'s own docstring), converts to DIMACS once, and drives one
  persistent PySAT `Minisat22` session for the whole run. `ad6/fave_bridge.py`'s query
  loop now calls `IncrementalSession.Query` instead of
  `Instantiator.InstantiateEndToEnd`/`SolveAcyclicEndToEnd` — the ONLY call site changed;
  `Instantiator`'s own methods are untouched, so nothing else that depends on them (direct
  tests included) is affected. New production dependency: `python-sat` (pinned
  `1.9.dev15` in the `Dockerfile`, alongside `pycosat`; PySAT only ever ships
  "dev"-tagged PyPI releases — that's its normal versioning scheme, not an unstable pin).
  **Verified, not just asserted**: `ad6 make test` (10 suites, including the new
  `testRunWithBigStackIsATransparentWrapper`) green; the real fave-side ad6 test files —
  `test_ad6_wl_ifi(.py/_stateful.py)`, `test_ad6_wl_up.py`, `test_ad6_adapter_lpm_prio.py`,
  `test_ad6_adapter_multi_device_acl.py`, `test_ad6_wl_stanford_plain.py` (36 tests total,
  the last one including a real N=2-router live-NetPlumber differential) — all pass
  end-to-end through the new architecture, exercised via the real
  `Ad6Adapter`→subprocess→`fave_bridge.py` path, not just in-process shortcuts. wl_ifi's
  full 219-pair compliance run: 0.81s (previously multiple seconds per query in the old
  architecture). Along the way, fixed an unrelated, pre-existing environment gap in this
  sandbox (`liblog4cxx.so.15` missing, blocking `NetPlumberLibAdapter` entirely — apt
  install, not an ad6/fave code change) that was silently skipping the only real
  live-NetPlumber ad6 differential test this project has.
- **Correction to the bullet above, 2026-09-09 — the "all pass end-to-end" evidence was
  real but was never produced by `./test.sh`, in any tier.** Those fave-side ad6 test
  files pass when pytest is invoked from `fave/` (which is how they were run on
  2026-08-27, and how they still pass today). But `test.sh`'s `fast` tier — the only tier
  that collected them — ran from the repo root, and every one of them locates its
  generated benchmark inputs through a CWD-relative `_PREFIX = "bench/<wl>"`. So from
  `$ROOT` the prefix was unresolvable and they skipped themselves as "inputs not
  generated": 11 passing ad6 tests, including `test_ad6_wl_stanford_plain.py`'s N=2
  live-NetPlumber differential, were invisible to the runner and to CI. The
  `liblog4cxx.so.15` gap recorded above was therefore only *half* of why that
  differential wasn't running: the library was missing, and the harness was never
  invoking it either. Fixed 2026-09-09 (fast tier now runs from `fave/`, three
  natively-dependent ad6 files moved to `FAVE_INTEGRATION_TESTS`, wl_up input generation
  added to that tier) — `TODO.md` item 1u. **A second, compounding finding from the same
  session (`TODO.md` item 1t, `ad6/FAVE_CHANGES.md` item 24): `ad6 make test` exited 0
  unconditionally**, so the "green" claim in the bullet above rested entirely on reading
  the suite output by eye — the exit code proved nothing. Both the suites and the entry
  point now propagate their verdict. Neither finding changes any measurement or
  correctness result in this plan; both change how much a bare "the tests are green"
  statement is worth, so treat pre-2026-09-09 green claims as inspection-based.

Full methodology, every intermediate axis (naive-vs-Tseitin CNF, ad6's own encoding vs.
native SMT, array/UF/quantified FIB theory, synthetic-then-real incremental scaling), and
the underlying harness: `AD6_ENCODING_PLAN.md`, `ad6_encoding_bench/`.

---

## 7. Measurement & write-up

- **7.1** "Price of genericity" section: the two-factor decomposition, **scaling curves**
  (gap vs network size and vs n), and the crossover analysis (wl_up vs Stanford/i2).
- **7.2** Expressiveness × performance table: properties each family can/can't express.
- **7.3** The BDD-APKeep phase-split bridge figure (representation-maintenance vs traversal).
- **7.4** Keep this **separate** from the clean 3-engine reachability comparison and the NDD
  faithful-VLAN result — ad6 is its own contribution/section, not a fourth column bolted
  onto the reachability matrix.
- **7.5 (new 2026-09-11) The grounding constraint is a RESULT, not an implementation
  note — write it up as a correction to the published formalism.** See below.
- **7.5b (new 2026-09-11) wl_i2: a matched flow-vs-rank ratio of 9.0-10.8x on the PLAIN
  model, and a qualitative result on the faithful one** (rank does not scale there; owner
  decision not to spend budget measuring it). The flow advantage GROWS with model size
  (7.0x wall on wl_stanford -> 9.0-10.8x on i2) and its memory advantage grows faster still
  (1.4x -> 6.0x).
- **7.5c (new 2026-09-11) The flow 2x2 across {minisat22, cadical195} x {plain, faithful}:**
  all four complete, all verdicts solver-independent. **The flow encoding rescues a backend
  the rank encoding disqualified** (Minisat22: query 1 unresolved in 90+ min under rank ->
  all 72 queries in 1,451 s under flow), and wl_stanford's solver inversion does NOT
  generalise — solver preference is benchmark-dependent, so no claim about a best backend
  may omit the benchmark, the encoding and the model.

### 7.5 Grounding a witness in a real origin — a correction to SECRYPT'15

**The finding, stated as a claim about the paper rather than about the code.** The
SECRYPT'15 formalism's `trans(C)` support term is purely LOCAL: an edge's firing is
justified by its own endpoints' conditions, with nothing tying the fired set back to an
initial state. A cycle therefore discharges the term self-referentially, and the paper's
"a solution represents a path starting at an initial state" does not hold. This is a gap in
the FORMALISM, not a defect in ad6's implementation of it — established 2026-09-05
(`258394f8`), with the minimal counterexample recorded in `ad6/FAVE_CHANGES.md` §20 and
pinned as a test: `entry -> unrelated_sink` is a dead-end out-edge that discharges the
query's source-side conjunct while `A` sits in a self-supporting cycle discharging the
destination-side conjunct, with NO path between them. Unconstrained, that query is SAT.
**Any reachability number computed under the published formalism is an over-approximation
of unknown size**, which is why this belongs in the write-up rather than in a footnote.

**Two repairs, with different scope.** Both are implemented, both are held to identical
ground truth by `instantiatortest.py::IncrementalSessionGroundingTest`, and since
2026-09-11 both are selectable from the production path (`IncrementalSession(...,
grounding=)`, `Ad6Adapter(..., grounding=)`, `fave_bridge.py --grounding`) rather than only
from the measurement drivers:

| | rank (`_CreateAcyclicConstraints`) | flow (`_CreateFlowPathConstraints`) |
|---|---|---|
| mechanism | per-edge `Rank(Target) > Rank(Node)`; a cycle chains into `Rank(A) > Rank(A)` | single-unit s-t flow; in/out-degree ≤ 1 makes the flow subgraph disjoint simple paths and cycles, and the source starts a path that only the destination can end |
| scope | **property-agnostic** — forbids every floating cycle regardless of the query | **reachability-specific** — names the endpoints |
| placement | shared base, built once | per query, by construction |
| session | one persistent incremental solver | fresh solver per query |
| sized by | largest cyclic SCC (`Width` bits × qualifying edges) | Kripke edge count |

**The measurement, MATCHED — and the first number quoted here was wrong.** Re-run
2026-09-11 under one configuration (both sides `--solver cadical195`, port-scoped, faithful
VLAN, same model, same 256 queries, all runs answering **165 reachable pairs**):

| N=16 run | solver | acyclic | wall | query | clauses | peak RSS |
|---|---|---|---:|---:|---:|---:|
| rank | cadical195 | lite | 1,136.9 s | 1,086.2 s | 851,631 | 2,051 MB |
| **flow** | **cadical195** | — | **163.5 s** | **117.2 s** | **313,555** | **1,491 MB** |
| rank (archived) | minisat22 | general | 2,131.7 s | 2,039.7 s | 851,631 | 4,173 MB |
| flow (archived) | minisat22 | — | 98.2 s | 63.2 s | 313,555 | 1,442 MB |

**Matched, the flow advantage is 7.0x wall / 9.3x query / 1.4x memory — not the 21.7x /
32.3x / 2.9x previously quoted here.** The old figure compared flow *at its best* (minisat22)
against rank *at its worst* (minisat22 + the general acyclic encoding), because those were
the only two artifacts that existed. Moving the rank side to cadical195 + lite nearly halves
it on its own (2,131.7 → 1,136.9 s), and the flow side is actually 1.66x SLOWER under
cadical195 than under minisat22 (98.2 → 163.5 s). **This is exactly the failure
generality-debt item 2 describes, caught in this plan's own headline number** — which is the
best argument available for the stamping gate, so it is recorded rather than quietly
corrected.

Three figures, all defensible, for different claims:

- **7.0x — matched configuration.** The one to quote for "how much does the grounding
  constraint itself cost", since nothing else varies.
- **11.6x — each at its own best** (rank 1,136.9 s at cadical195+lite, flow 98.2 s at
  minisat22). The one to quote for "what does each approach achieve when tuned".
- ~~21.7x~~ — **retired.** Two variables at once; not a valid comparison.

Either way the shape of the result holds, and the interesting clause survives intact: flow
wins *despite* giving up incremental reuse across queries entirely, which materially weakens
the 439x cold/warm argument for the persistent session (generality-debt item 3).

**A second finding from the same pair: the solver preference INVERTS with the grounding.**
Rank is ~1.9x faster under cadical195+lite than minisat22+general; flow is 1.66x slower
under cadical195 than minisat22. So "which solver is best for ad6" has no answer
independent of the encoding — a sharper version of item 2's warning, and a caution against
ever picking a backend once and reusing the choice across a table.

**Why it wins, and the shape of the claim to make.** Flow SHRINKS the shared base (2.7x on
wl_stanford, 4.2x on wl_i2) and pays per query instead. On wl_i2 the rank encoding is
**95% of the entire CNF** (14,201,913 of 14,883,129 clauses = 140,613 qualifying edges ×
101 clauses at `Width`=17) — floating-cycle defence that all 72 queries drag along, on a
graph whose giant single SCC makes nearly every edge qualify. The honest framing is not
"flow is faster" but "a global numeric ordering is the wrong shape of constraint for a
reachability question; a path skeleton is the right one" — and that generalises to any
verifier grounding a witness in a SAT encoding, which is what makes it a contribution
rather than a tuning note.

**State the boundary explicitly, or the claim over-reaches.** Flow generalises across
MODELS completely (pure graph structure, nothing benchmark-specific, and complete — any
genuine simple s→t walk can carry the unit, so no real witness is rejected). It does NOT
generalise across PROPERTY CLASSES: a single unit forbids branching witnesses (multicast,
ECMP where both branches must be asserted, a query whose witness IS a cycle), and having no
single s-t pair to hang on, it cannot express AF/AX, waypointing, or the anomaly-detection
queries. So the rank encoding remains necessary for exactly the expressiveness §0 leans on
— the temporal/QBF properties the domain-specific tools structurally cannot express. **Two
grounding strategies with different scopes, not a replacement.**

### 7.5b wl_i2: a matched ratio on the PLAIN model, and a qualitative result on the faithful one

**CORRECTION 2026-09-11, same day, before this section was ever quoted:** its original title
("Why wl_i2 has no flow-vs-rank ratio") was too strong. It is true of the FAITHFUL model
only. Running the flow encoding on the PLAIN model under cadical195 produced a partner for
the two archived rank runs that is matched on every axis that matters, so i2 does have a
ratio — and it is LARGER than wl_stanford's.

**The matched plain pair.** Same solver (cadical195), same model (plain, no VLAN
admission), same 72 pairs (`--pair-filter exclude-self`), both `oracle_match: true`. The
base encoding is provably the same object: the rank run's 14,883,129 clauses are exactly the
flow run's 681,216 base plus 14,201,913 acyclic. Only the grounding differs — and the
session structure it forces.

| plain i2, cadical195, 72 pairs | wall | query | clauses | peak RSS |
|---|---:|---:|---:|---:|
| rank + lite (archived v1) | 12,820.8 s | 12,417.2 s | 14,883,129 | 13,464 MB |
| rank + lite (archived v2) | 15,312.4 s | 14,895.9 s | 14,883,129 | 13,432 MB |
| **flow (new)** | **1,424.0 s** | **879.6 s** | **681,216** | **2,245 MB** |

**flow is 9.0-10.8x faster in wall-clock, 14.1-16.9x in query time, and 6.0x smaller in peak
RSS, on 21.8x fewer clauses.** The range spans the two archived rank runs, whose 19%
spread is real run-to-run variance on this box; the honest figure is the range, not either
endpoint, and it is against ARCHIVED rank runs rather than a same-session pair.

**Two scope labels this figure must carry.** (1) It is **INTRA-AD6** — both sides are ad6,
so the plain model's dst-IP-only workload-parity gap (§5.2's WORKLOAD PARITY note) does not
affect it, but it also means this number may NOT be set beside a NetPlumber or APKeep
figure; cross-family i2 comparison uses the faithful runs only. (2) It is a **PLAIN-model**
ratio and should not be assumed to transfer to the faithful model: plain is an all-SAT
instance (72/72 reachable), while faithful adds 11 UNSAT pairs that cost 6.6-7.4x a SAT pair
(§7.5c), and whether that surcharge falls equally on both encodings is untested — there is
no faithful rank run to compare against, by the owner's decision above.

**The trend across the two benchmarks is the interesting part, and it goes the right way for
the thesis.** wl_stanford N=16 matched: 7.0x wall, 1.4x memory. wl_i2 plain matched:
9.0-10.8x wall, **6.0x memory**. The advantage GROWS with model size, and the memory
advantage grows much faster than the time advantage — consistent with the mechanism, since
what the rank encoding costs is a per-edge comparator over a graph whose cyclic SCC is
enormous on i2 and modest on wl_stanford.

**On the FAITHFUL model there is still no ratio, and that part of this section stands.**

### 7.5c The flow 2x2: {minisat22, cadical195} x {plain, faithful} — all four complete

Run 2026-09-11 in place of the rank measurements (owner decision above), strictly
sequential on a 4-core box, 2 h cap each. **All four completed well inside their caps**;
total measurement time 2 h 49 min of the 12 h budget.

| solver | model | wall | build | query | clauses | peak RSS | reachable |
|---|---|---:|---:|---:|---:|---:|---:|
| cadical195 | plain | 1,424.0 s | 530.1 s | 879.6 s | 681,216 | 2,245 MB | 72/72 |
| minisat22 | plain | 1,818.4 s | 356.8 s | 1,451.1 s | 681,216 | 2,478 MB | 72/72 |
| cadical195 | faithful | 3,218.1 s | 716.2 s | 2,475.5 s | 3,508,560 | 9,153 MB | **61/72** |
| minisat22 | faithful | 3,663.3 s | 706.9 s | 2,931.2 s | 3,508,560 | 9,666 MB | **61/72** |

**Every verdict is solver-independent.** Both plain runs report all 72 reachable; both
faithful runs report the SAME 11 unreachable pairs. The Chicago-crossing result is therefore
now corroborated by two independently-implemented engines (ad6, NetPlumber) and a
structural witness computed by a third method, and within ad6 reproduced across two SAT
backends and two separate runs. **Read that with §5.5's "WHAT THE i2 ORACLE ACTUALLY IS":
the implementations are independent, the process that produced the agreement was not** —
both engines were corrected repeatedly until they agreed, so it is the manual root-cause
inspection against the raw data, not the agreement itself, that rules out a co-adapted
shared error.

**THE HEADLINE: the flow encoding rescues a backend the rank encoding disqualified.** Under
the rank encoding at i2 scale, Minisat22 **had not resolved query 1 in 90+ minutes** (§5.5's
solver comparison, which is why it was dropped from the shortlist). Under the flow encoding
the same backend answers all 72 plain queries in **1,451 s of solving, ~20 s/query**. Nothing
about the solver changed; the grounding constraint did. That is the sharpest single piece of
evidence that at i2 scale the binding factor is the ENCODING, not the backend — and it
retrospectively reframes §5.5's entire solver-comparison exercise, which spent four backends
and ~30 hours searching for tractability in the wrong dimension.

**The wl_stanford solver inversion does NOT generalise — question answered, negatively.**
§7.5 found flow preferring minisat22 on wl_stanford (1.85x on query time) while rank
preferred cadical195, and flagged whether that held at i2 scale as open. It does not:

| benchmark, flow grounding | faster backend | margin (query time) |
|---|---|---|
| wl_stanford N=16 faithful | minisat22 | 1.85x |
| wl_i2 plain | **cadical195** | 1.65x |
| wl_i2 faithful | **cadical195** | 1.18x |

So solver preference under the flow grounding is **benchmark-dependent, not a property of
the grounding**. Combined with §5.5's finding that per-pair hardness is a solver-search
artifact rather than an instance property, the standing rule for §7 is: **ad6 has no
benchmark-independent best backend, and any claim about one must name the benchmark, the
encoding AND the model.** Note also that cadical195's margin SHRINKS as the instance hardens
(1.65x plain -> 1.18x faithful), so the two converge where it matters most; a single-model
solver choice should not be extrapolated to a harder one.

**Per-pair hardness under the flow encoding (§5.5's question, re-asked on the new
instances).** Cross-solver correlation on identical CNF is **-0.076** on plain and **0.587**
on faithful — and that second figure is a confound, not a contradiction. UNSAT pairs cost
**6.6x** the mean SAT pair under cadical195 (122.15 s vs 18.53 s) and **7.4x** under
minisat22 (152.45 s vs 20.55 s), because a refutation must exhaust the search space while a
witness can be found by luck. Splitting the classes returns the correlation to noise
(SAT-only 0.206, UNSAT-only -0.128). **Satisfiability class is a real instance property with
a ~7x cost effect; per-pair hardness within a class stays a solver-search artifact** — and
no §7 hardness correlation may be computed over a mixed SAT/UNSAT set.

**Artifacts** (all `status: completed`, fully stamped):
`eval/ad6_i2_flowpath_{plain,faithful}_cadical195_72pairs_sandbox.json`,
`eval/ad6_i2_flowpath_{plain,faithful}_minisat22_72pairs_sandbox.json`. Sandbox/directional
per the environment guardrail; all four ran sequentially on the same box, so the
cross-solver and cross-model comparisons within this table are the defensible quantities.

**Decision (owner, 2026-09-11): do not spend measurement budget on the rank encoding at i2
scale.** (This is why the plain ratio above leans on ARCHIVED rank runs rather than a fresh
matched pair, and why no faithful rank number exists at all.) *"I am not sure if it is really worthwile to measure the rank approach at all. As
said, we came up with the flow approach since the rank approach did not scale well."* The
i2 contribution is therefore NOT a speed ratio like wl_stanford's 7.0x. It is the
qualitative claim that **the rank encoding does not scale to i2 and the flow encoding
does** — which is a stronger statement than any ratio, and the reason the flow constraint
was designed in the first place. Recorded here with its evidence so a later reader sees a
measured reason rather than a missing cell in a table.

**Three tiers of evidence, in increasing order of how much they cost to establish.**

1. **The GENERAL rank encoding never ran on i2 at all.** `_CreateAcyclicConstraints`
   retains ~0.14-0.18 MB per SCC-qualifying edge in lxml objects; i2's giant single SCC
   makes 140,613 of 155,199 edges qualify, projecting ~22 GB — and it was OOM-CONFIRMED at
   82,363/140,613 edges = 14.44 GB, during construction, before DIMACS conversion or
   solving begin. This is generality-debt item 1's tool limitation, and it is why
   `--lite-acyclic` is mandatory rather than chosen.
2. **rank + lite on the PLAIN model completes, and is the fair thing to say in rank's
   favour.** Two archived cadical195 runs: 3.56 h and 4.25 h for 72 pairs (172.5 and
   206.9 s/query), 13.4 GB peak, exact oracle match. So "rank does not work on i2" would be
   too strong — on the plain model it works.
3. **rank + lite on the FAITHFUL model is where it stops scaling.** Only ever run on 3
   pairs (`eval/ad6_i2_faithful_untagoff_3pairs_sandbox.json` and its witness companion):
   **641.6 and 713.8 s per query** at **18,416 / 18,454 MB peak against this box's 19,484 MB**
   — 94.5% of RAM, for 3 of 72 queries, with 17,683,953 clauses. Extrapolating the
   per-query cost to 72 gives **~13.6 h of solving** for a single measurement, against a
   12 h budget for the whole exercise, with roughly 1 GB of headroom left for 69 further
   queries' accumulated OR-gate clauses.

   *Stated honestly:* the ~13.6 h is an extrapolation from **n=3**, and i2's per-query cost
   is famously variable (sub-second to 80 minutes, and §5.5 established that per-pair
   hardness is a solver-search artifact rather than an instance property), so it is an
   order-of-magnitude estimate, not a measurement. Whether 72 queries would actually OOM is
   likewise untested — what is measured is that the headroom is ~1 GB after 3.

**Against which the faithful FLOW run is the whole point, now measured twice:** a fresh
cadical195 run (72 pairs, `--pair-filter exclude-self`) completed in **3,218.1 s wall /
2,475.5 s query at 9,153 MB**, and **independently reproduced the same 11 unreachable pairs**
as the archived run — `chic` unreachable from hous/kans/losa/salt/seat, and `atla`,
`newy32aoa`, `wash` unable to reach `kans` or `seat`. That is now a fourth independent
confirmation of the Chicago-crossing result, alongside the earlier ad6 run, NetPlumber, and
the structural oracle. The archived figures: all 81 queries (72 cross-role +
9 self) completed in **4,201 s wall / 3,410 s query — about 70 minutes — at 9,183 MB peak**,
and it is the run whose 11 unreachable pairs are corroborated by NetPlumber and by the
structural witness (§5.5's "WHAT THE i2 ORACLE ACTUALLY IS" for what that corroboration is
worth, and what it is not). Per query that is ~42 s against rank's extrapolated
~678 s. **The comparison on the faithful model is not "7x"; it is "one finishes in about an
hour using half the box, the other is a multi-hour run pressed against the memory
ceiling."**

**What is being measured instead (2026-09-11):** the flow encoding under BOTH solvers, on
both models — a 2x2 of {minisat22, cadical195} x {plain, faithful}, 2 h cap each. This asks
a better question than re-confirming rank's cost, because §7.5's wl_stanford pair found the
**solver preference inverts with the grounding** (rank ~1.9x faster under cadical195+lite;
flow 1.66x faster under minisat22). Whether that inversion survives at i2 scale is open, and
non-obvious: minisat22 was disqualified at i2 scale in §5.5's solver comparison ("never
resolved past query 1") — but that was a 14.9 M-clause PERSISTENT rank instance, whereas the
flow instance is 3.5 M clauses with a fresh solver per query.

**Status.** The wl_stanford pair is DONE and fully stamped (`eval/
ad6_faithful_N16_lite_cadical195_sandbox.json`, `eval/
ad6_faithful_N16_flowpath_cadical195_sandbox.json`, both `status: completed`,
`reachable_pairs: 165`); it is the first wl_stanford result whose configuration needs no
inference. **Still open:** the wl_i2 flow/rank pair is NOT like-for-like (the flow run is
faithful + port-scoped, the rank-lite run is plain mode), so the i2 side has no matched
figure at all yet — and given what matching did to the wl_stanford number, it should not be
assumed to survive the same treatment. Sandbox/directional per the environment guardrail;
the ratio is the defensible quantity, since both halves were measured on the same box.

---

## 8. Architecture & design review (deferred until the benchmarks work)

**Added 2026-08-20 (Claas), deliberately gated:** do NOT start this until wl_up (and
ideally Stanford/i2) are working end to end — the point is to review ad6's 2014 design
with real, working benchmarks and concrete pain points in hand, not to refactor
speculatively ahead of need.

- **8.1 XML as the primary data structure — reconsider.** Claas, in hindsight: *"I would
  probably not go for XML as my primary data structure."* ad6 uses `lxml.etree` Elements
  for BOTH the network/ruleset config input AND the SAT formula (Kripke encoding, CNF) —
  the same generic tree type represents structurally very different things (a config
  schema vs. a boolean-formula AST) with no type safety between them. Two of the bugs
  found building the wl_ifi translator (§4.4, `ad6/FAVE_CHANGES.md` item 6) are arguably
  symptoms of this: `ConvertCIDRToVariables` silently produces a **structurally valid but
  semantically wrong** empty `<conjunction/>` for a `/0` CIDR (a typed AST node could
  make "AND of nothing" impossible to construct by accident, or force an explicit
  true/false default); `_CreateInitConstraints`'s chained-XOR off-by-one went unnoticed
  for years partly because there's no isolated unit test for it (easier to write, and to
  motivate writing, against a small typed builder than against ad-hoc XML tree surgery).
  Worth asking concretely: would typed Python objects (dataclasses or similar) for the
  formula AST, with the current XML only as an optional serialization format, have caught
  either bug at construction time instead of at solve time?
- **8.2 The two known core bugs — DONE 2026-08-21, fixed test-first (not deferred after
  all).** Claas asked for both to be fixed properly rather than left as documented
  workarounds. Both are now fixed in ad6 core, each with a regression test written first
  (confirmed failing pre-fix): the `/0`-CIDR empty-conjunction bug in
  `ConvertCIDRToVariables` (now returns `constant()` for a `/0` prefix —
  `ad6/FAVE_CHANGES.md` §7, `test/xml/xmlutilstest.py:testCIDRMatchAll` +
  `test/core/instantiatortest.py:testMatchAllReachable`), and
  `_CreateInitConstraints`'s chained-XOR (turned out to be far more broken than the
  original "last few of >16 nodes" diagnosis — a brute-force sweep found only `(T[0],T[1])`
  was ever correctly excluded for ANY N>3, not just a tail slice; fixed by replacing the
  chain with the same direct pairwise `_xor(all transitions)` the N∈{2,3} case already
  used correctly — `ad6/FAVE_CHANGES.md` §8, `test/core/initconstraintstest.py`, a new
  property-test suite). Neither was exercised by ad6's existing test suite or its native
  `IP6TablesParser` frontend, which is presumably why they survived undetected since 2014.
  `fave_bridge.py`'s `_exclusivity_conjuncts` per-query workaround for the second bug is
  removed (verified redundant, not just coincidentally still passing, by re-running
  wl_ifi's differential with it deleted).
- **8.2b `CanonizeIP`'s IPv6 "::" expansion bug — DONE 2026-08-21, fixed test-first, same
  ask.** Found building wl_up (§5.1) and originally logged there as a `favemodel.py`
  workaround (`_ipv6_safe`); Claas asked for the same core-fix treatment as §8.2's two
  bugs instead. Tests first (`test/xml/xmlutilstest.py:testIp6BoundaryCompression`, newly
  wired into `xmlsuite.py` — which also revealed `testCIDRMatchAll` from §8.2 had NEVER
  actually been registered there, so `make test` never ran it either; both are now
  registered) confirmed the true scope before fixing: not just the originally-logged
  trailing-`::` case, but leading `::`, `::` alone (all three: an empty `Prefix`/`Postfix`
  from `Address.split('::')` is silently counted as one explicit group instead of zero),
  AND a separate `UnboundLocalError` crash for an address with no `::` compression at
  all — the same "worse than first diagnosed" pattern as §8.2's init-mutual-exclusion bug.
  Fixed by replacing the `try/except`-driven split with an explicit `if '::' in Address'`
  branch and building the expanded address as a flat group list
  (`PrefixGroups + ['0']*InLen + PostfixGroups`, `[]` not `['']` for an empty side)
  joined once — can't produce a stray leading/trailing colon by construction.
  `favemodel.py`'s `_ipv6_safe` workaround is removed (verified redundant first, same
  discipline as the `_exclusivity_conjuncts` removal above). `ad6/FAVE_CHANGES.md` §11.
- **8.3 Test coverage for the "generic infrastructure" layer** (`XMLUtils`, `SATUtils`,
  `Instantiator`'s constraint builders) is thin relative to how much correctness leans on
  it — `ad6/test/` covers the happy-path small fixtures (§3.1) but has no test exercising,
  e.g., a `/0` CIDR or >16 simultaneous inits. Consider whether a review should add
  property-style tests here (e.g. "for N inits, exactly one of N transitions is
  satisfiable, no more, no fewer") rather than only example-based ones.
- **8.4** More generally: revisit whether the current frontend/backend split (§4.4 —
  `GenUtils` as the IR, `Kripke`/`Instantiator` as the backend) is the right seam long-term,
  now that a second frontend (`favemodel.py`) exists alongside `IP6TablesParser` and both
  can be compared for what they needed from that seam and what friction each hit.
- **8.5 (new 2026-08-21j) `ad6/src/sat/satutils.py`'s naive (non-Tseitin) CNF conversion is
  a candidate general improvement, independent of the VLAN spike.** Surfaced investigating
  §5.4: `ConvertToCNF` distributes ANDs over ORs directly (De Morgan + split, no auxiliary
  variables), which is exponential in formula *alternation depth* — cheap today only because
  every existing frontend emits shallow, flat conditions. §5.4 Stage B treats a Tseitin
  rewrite as a targeted fix *if* the SSA/frame-axiom encoding's numbers show naive
  conversion (not the encoding itself) is the bottleneck — but the same naive-conversion
  ceiling applies to ad6 generally, not just to VLAN rewrite, and could matter for any
  future frontend (or a deeper wl_up-style state-interweaving attempt, §5.1) that produces
  less shallow formulas than today's. Worth scoping as its own improvement independent of
  §5.4's outcome, once the benchmarks stabilize — not undertaken speculatively before a
  concrete need is measured, same discipline as everywhere else in this plan.
- **8.6 (new 2026-08-28) §8.1's "reconsider XML" question now has a concrete, quantified
  memory cost behind it, not just the bug-symptom argument — and a second, separate
  bottleneck surfaced alongside it. Scoping two separately-landable tracks; NOT started,
  gated the same way as the rest of §8 (real pain point in hand, no speculative refactor).**

  **What grounds this:** wl_i2's C2 NO-GO (§5.5) was root-caused to
  `Instantiator._CreateAcyclicConstraints` retaining ~0.14-0.18 MB of genuinely-referenced
  (not reclaimable-garbage — confirmed via `gc.collect()` returning 0 every time)
  memory per SCC-qualifying edge, from building/CNF-converting an `lxml.etree`-backed
  formula tree per edge — projecting ~22GB for i2's 140,613 qualifying edges alone. A
  workaround, `Instantiator._CreateAcyclicConstraintsLite`, hand-emits the IDENTICAL
  clause set (proven by `testAcyclicRankConstraintLiteMatchesGeneralEncoding`, an exact
  clause-set equivalence check, not a spot check) as plain `(name, negated)` tuples,
  bypassing lxml/`SATUtils.ConvertToCNF` entirely for this one already-fully-understood
  formula shape. Measured result: the full edge set builds in ~15-20s peaking at ~8.5GB
  (was: OOM before 60% done, projected ~22GB) — confirms the lxml-per-node cost is real,
  large, and fixable when the target clause shape is already known. **Not yet committed**
  (implemented + tested this session, pending a commit decision).

  **A second, separate bottleneck surfaced alongside it:** even with construction fixed,
  loading the resulting instance (6.3M variables, 14.9M clauses — `_CreateAcyclicConstraints`
  and `_CreateAcyclicConstraintsLite` produce the same clause COUNT, only the construction
  cost differs) into Minisat22 and solving even the FIRST query did not complete in 77+
  minutes, with host memory exhausted into heavy swap thrashing. `bench/ad6_i2_measure.py`
  (both variants) bakes ALL acyclic constraints into the shared base model unconditionally
  for every query — the same pattern §5.4 B1 already found costly on Stanford (~6s/query)
  and routed around via `Instantiator.SolveAcyclicEndToEnd`'s lazy escalation (plain solve
  first, build the rank machinery only if a witness turns out ungrounded). i2's measurement
  script never uses that lazy path. Whether i2's instance is fundamentally SAT-hard at this
  scale, or just suffering the same avoidable "bake it all in" tax Stanford already worked
  around, is an open, likely-higher-leverage question than the data-structure refactor below
  — **recommend investigating this before or alongside starting either track.**

  **Track A — the Kripke graph layer** (`structure.py`'s `Kripke`/`KripkeNode`,
  `Instantiator._ComputeSCCs`): already NOT XML (a hand-rolled, dict-backed structure,
  confirmed O(1) transition lookups) but implements graph algorithms (Kosaraju's SCC) by
  hand. Candidate: replace with a real graph library's SCC — but NOT reflexively networkx,
  whose dict-of-dicts-of-dicts adjacency and per-node/edge attribute objects are
  optimized for ergonomics/algorithmic breadth, not memory density, at exactly the scale
  (78,078 nodes / 155,199 edges on i2 alone) this investigation just found lxml wanting
  at. First narrow the actual need (SCC may be it — reachability is handled by the SAT
  encoding, not graph traversal): `scipy.sparse.csgraph.connected_components` (C-backed,
  sparse-matrix, likely both lighter and faster) is a better-scoped candidate than a
  general graph library; `rustworkx`/`igraph` if genuinely broader graph operations are
  wanted later. Any candidate gets an empirical scale-check (a capped isolation probe
  measuring RSS/wall-clock on real i2-sized data, same methodology as today's `gc_probe.py`
  finding) BEFORE adoption, not after — "mature and well-tested" is a correctness claim,
  not a per-node-cost-at-100k+-instances one, which is exactly the assumption that broke
  on lxml this session.
  **Track B — the SAT-formula AST** (`XMLUtils`'s variable/conjunction/disjunction/
  implication nodes, `SATUtils.ConvertToCNF`): needs none of XML's features (no
  namespaces/mixed content, ~6 node kinds, ≤2 attributes) and is what's actually paying
  the measured per-node cost. Candidate: a minimal, purpose-built representation
  (`__slots__` classes or tuples) with `SATUtils`'s transformations retargeted at it —
  NOT reflexively a general symbolic/tree-transformation library (e.g. sympy's boolean
  algebra module already does CNF distribution, but its immutable, hash-cached expression
  nodes carry their own substantial per-instance overhead aimed at symbolic-math
  generality, a plausible repeat of the same mismatch). Check first whether **PySAT**
  (already a dependency via `Minisat22`) ships usable CNF/Tseitin-adjacent formula
  utilities in `pysat.formula` before building or adopting anything else. Every
  transformation this track touches is soundness-critical (this is the exact machinery
  §5.4 B1's floating-cycle bug and its fix live in) — needs the same exact-equivalence
  testing discipline `testAcyclicRankConstraintLiteMatchesGeneralEncoding` established,
  not example-based spot checks (§8.3's existing thin-coverage concern applies doubly
  here). The `_CreateAcyclicConstraintsLite` pattern (hand-derive direct clause emission
  for a formula shape that's already fully understood and static) stays a complementary,
  narrower technique alongside this track, not a substitute for it — it doesn't help
  formulas whose shape isn't known/fixed ahead of time.

  Config parsing (device tables/rules/actions, `favemodel.build_config`) stays lxml —
  it's a genuinely hierarchical, attribute-rich config format where XML's tooling is a
  reasonable fit; this review is scoped to the graph and formula layers only, not a
  blanket "remove XML from ad6."

---

## 9. The ad6 adapter rewrite: structural translation (owner decision 2026-09-12)

**Owner framing, recorded because it sets the scope:** *"I think we should invest in the
integration now. FaVe's network model (mostly match-action tables with unidirectionally
connected ports) is not too complicated and in an earlier session you said, that ad6's
primitives should be sufficient for the implementation of the adapter. With wl_ifi at
hand, we also have a rather small and fast running benchmark to accompany our work.
Hence, we need an implementation plan (as always: test first)."*

### 9.1 The diagnosis: semantic reconstruction, not translation

`fave/ad6/adapter.py` does not translate FaVe's model. It RECOGNISES FaVe's naming
conventions and rebuilds meaning from them, emitting an IR of interpreted CONCEPTS
(`acl_in`, `acl_out`, `in_admit`, `mid_rw`, `out_rw`, `in_vlans`, `routing_rules`) rather
than of rules. The evidence is explicit in the code:

  * `_build_ir` sniffs the WORKLOAD -- `if any(d.split('.', 1)[0] == 'mid' for d in
    devices)` is "this is wl_stanford", in the production path, with a comment saying
    there is no other flag distinguishing the benchmark.
  * Eight `_capture_*` methods recover concepts from the `in.*`/`mid.*`/`out.*` stage
    convention, plus `_fold_mid_rewrites` and `_collapse_out_stage`.
  * `load_bench_metadata` DISCARDS FaVe's already-parsed rules for every device carrying a
    `ruleset_path` -- **136 of wl_up's 159 devices** -- and re-reads the raw ip6tables
    text so ad6's own `IP6TablesParser` can parse it instead. Its docstring states the
    rationale ("feed ad6 its native format directly", on the strength of
    `IP6TablesParser`'s exact match on wl_tum's 3,795 rules).

Every generality problem this plan has hit traces back to that design: the LPM tiebreak
bug, the per-(port, VLAN) admission cross-product, the out-stage collapse, and the wl_up
NO-GO (§5.1). **The wl_up NO-GO's REASONING was right and its SCOPE was one level too
wide:** porting state-shell interweaving into `ad6/src/parser/iptables.py` is still not
worth doing, but that conclusion was reached without questioning the bypass that makes
`IP6TablesParser` load-bearing on the adapter path at all. FaVe already does the
interweaving; the adapter throws the result away.

**Target: STRUCTURAL TRANSLATION.** FaVe table -> ad6 table; FaVe rule -> ad6 rule in
FaVe's own `idx` order; FaVe field -> ad6 match; FaVe action -> ad6 action; FaVe link ->
ad6 connection. No name recognition, no concept recovery, no workload detection.

### 9.2 Two prerequisites, both checked in the code before planning

**(a) A FaVe backend needs NO stateful reasoning -- confirmed, and it is stronger than it
sounds.** Owner framing: *"once ad6 can be used as a FaVe backend, there is no necessity
for stateful reasoning anymore as FaVe only requires stateless verification engines."*
`fave/iptables/generator.py:519`'s `_interweave_state_shell` does not merely derive the
ESTABLISHED-accept leg -- it STRIPS the conntrack matches outright
(`match=Match([f for f in rule.match if not is_conntrack(f)])`) and re-emits the derived
rules carrying a plain `RuleField('related', '1')`/`('related', '0')` (`:368`, `:404`).
`related` is an ordinary 8-bit header field in FaVe's model
(`fave/netplumber/mapping.py:34`). So the engine sees no state at all, just a field named
`related` -- one entry in a field-mapping table, and `_STATE_FOR_RELATED`'s state
semantics leave the adapter path entirely.
**The consequence that drives the design: the state semantics survive PURELY AS RULE
POSITION.** The interwoven ruleset is correct only if evaluated in order. Rule-ordering
fidelity is therefore the translator's critical property, not a detail.

**(b) ad6's primitives suffice.** `ad6/src/xml/genutils.py` provides `firewall`, `table`,
`rule(name, key)`, the generic `fieldmatch(field, value, negated)`, the typed
`address`/`port`/`proto`/`vlan` matches, `action(type, target, rewrite_field,
rewrite_value)`, `connection(target)` and `route(target, flag)` -- a complete match-action
vocabulary. `ad6/src/core/kripke.py:62` walks a table's rules in DOCUMENT ORDER with the
index in hand, so ordering is representable. (Whether the fall-through semantics are
exactly first-match-wins is Phase 0.1's job to pin, not to assume.)

### 9.3 The plan (test first, per the standing rule)

**Phase 0 -- establish the ground before changing production code.**
  1. **Settle ad6's rule-order semantics FIRST; it gates the design.** A two-rule table
     where order decides the verdict (rule 0 accepts what rule 1 drops, then swapped).
     If ad6 is not first-match-wins in document order, Phase 1's shape changes.
  2. **Characterization tests.** Snapshot `_build_ir()` for all six benchmarks and the
     verdict matrix from each of the 13 `fave/test/test_ad6_*` files. These are
     TRIPWIRES, not specifications -- their only job is to make every change visible.
  3. **Name the adjudicator BEFORE seeing a diff.** The recorded answers (wl_ifi 54/54,
     wl_stanford 165 pairs, wl_i2 61/72 with the 11 named pairs) were produced BY THE
     ADAPTER BEING REPLACED, so a difference is not automatically a regression. Each one
     is adjudicated against NetPlumber's own matrix (§9.4) or, on i2, the structural
     oracle. Deciding this in advance is what keeps the rewrite from silently ratifying
     an existing bug.

**Phase 1 -- the translator: pure, bottom-up, tests written first.** A new
`fave/ad6/translate.py`, no I/O and no adapter state, each function's tests written from
hand-built FaVe objects before the function exists:
`field_to_match(RuleField)` (one test per field: ipv4/ipv6 src+dst, `vlan`, ports, proto,
`related`, and negation on each) -> `rule_to_ad6(Rule, pos)` (matches + `in_ports` +
`Forward`/`Rewrite`/`Miss`, position preserved) -> `table_to_ad6` -> `model_to_config`.
All sub-second and benchmark-free: this is where the design work is and where tests are
cheapest.

**Phase 2 -- swap it in behind a STAMPED flag.** `Ad6Adapter(...,
translation='semantic'|'structural')`, defaulting to `semantic`. Stamped in the IR and in
every result file: the generality-debt gate applies, since this is measurement-affecting
configuration. The 13 existing test files then run under BOTH, and the differential is
the test.

**Phase 3 -- climb the ladder, measuring model SIZE at each rung.** wl_example (10) ->
**wl_ifi (54 checks, 2.1 s -- the inner loop)** -> wl_stanford plain -> wl_stanford
faithful -> wl_i2 plain -> wl_i2 faithful. Record verdicts AND
`kripke_nodes`/`clause_count` at every rung. **The main risk lives here:**
`_collapse_out_stage` and `_fold_mid_rewrites` are partly model-size reductions, and a
structural translation keeps every stage. **wl_ifi cannot reveal this** -- it will look
free until i2. If size regresses, the collapses return as STRUCTURAL optimizations
("collapse any table that is a pure port permutation"), stamped and separately
toggleable, never name-triggered.

**Phase 4 -- wl_up.** Delete `load_bench_metadata`'s ruleset bypass so those 136 devices
arrive through `add_rules` with the interweaving intact, and test that wl_up's plain
checks stop being vacuous (currently 1,712/1,713 false violations, §5.1). This settles
§9.1's scope correction empirically and should be nearly free once Phase 1 exists.
**Note what it would mean for the thesis:** wl_up going from NO-GO to working by DELETING
an ad6-specific shortcut is a better result for the "generic tool, low integration cost"
claim than wl_up staying out of scope.

**Phase 5 -- delete.** Remove the semantic path, the `mid.*` sniff, the eight
`_capture_*` methods, `_fold_mid_rewrites`, `_collapse_out_stage`, `ruleset_devices`,
`_build_ruleset_firewall`, and `IP6TablesParser` from the adapter path; flip the default.
`favemodel.py` loses most of its IR-interpretation surface with it. **The line count
going sharply DOWN is the deliverable.**

**Phase 6 -- production wiring (SEPARABLE, may run in parallel).** Backend selection in
the aggregator -- `aggregator/aggregator_service.py:92` hardcodes `NetPlumberAdapter`
and its `engine=` parameter is documented as a TEST injection seam, so no production
route to ad6 (or APKeep) exists at all today; this is the §1.4 "Integration level: (A)
`AbstractVerificationEngine` backend vs (B) model translation" decision, still open.
Plus solver/grounding plumbing through `fave_bridge.py`: `IncrementalSession` hardcodes
`Minisat22` at `incremental.py:134` and `:215`, so the production path cannot today
reproduce the cadical195 configuration every wl_i2 number was measured under, and
`lite_acyclic` is not plumbed there either -- which means **i2 through FaVe is only
possible under flow grounding** (rank needs lite at that scale; the general path cannot
reach DIMACS conversion). Survivable -- the flow 2x2 puts minisat22 only 14% behind
cadical195 (3,663 s vs 3,218 s faithful) -- but it must be a stated, stamped choice.

### 9.4 Scope of the accompanying agreement check (owner direction 2026-09-12)

Item 1 of the owner's own list -- *"for each benchmark ad6 and NetPlumber should yield the
same reachability matrix"* -- has a narrower real scope than it reads, established by
counting the shipped check files:

| benchmark | `checks.json` | `cchecks.json` | comparable matrix? |
|---|---|---|---|
| wl_example | 10 | 3 | yes |
| wl_ifi | 299 | 17 | yes |
| wl_up | 11,902 | 131 | **after Phase 4** |
| wl_tum | **0** | **0** | nothing to compare |
| wl_stanford | 240 | 16 | yes |
| wl_i2 | 72 | 9 | yes |

wl_tum ships zero checks in both files and `wl_tum/benchmark.py` never references checks
-- it is a build/scale workload. wl_shadow, wl_expand, wl_generic_fw and
wl_state_snapshots are not reachability benchmarks (shadow is anomaly detection;
state_snapshots is stateful-snapshot work). **The matrix itself comes from NetPlumber's
own flow-tree dump** (owner's method: roots and leaves of the dumped trees), for which
`bench/np_i2_flow_dump.py` + `bench/np_i2_flow_leaves.py` are the existing, only lightly
i2-specific machinery. The property any generalization must preserve is the one that tool
already states: NetPlumber emits a leaf for any node with no onward flow, so **a leaf is
either a probe arrival or a dropped branch and only the node id says which** --
conflating them makes "ad6 forwarded past an NP leaf" trivially true at every probe.
Two prerequisites sit upstream: the `bench` tier's `/dev/shm` exhaustion and its missing
inter-workload cleanup (TODO item 1r).

**Logical generality is explicitly NOT a goal here** (owner, 2026-09-12): *"I do not
think that ad6 requires logical generality. Instead, I would document the gap and if
necessary, e.g., through some benchmark, I'd approach the issue again with that specific
use case."* With §9.2(a) settled, the documented gap narrows to what no in-scope
benchmark asks: AF/AX, waypointing, and the anomaly queries. APKeep is out of scope for
this effort (owner, same date), which also removes generality-debt item 5 from the
critical path.

### 9.5 Phase 0 -- DONE 2026-09-12. The design is cleared to proceed.

**0.1 -- ad6's rule-order semantics: FIRST-MATCH-WINS IN DOCUMENT ORDER, WITH
GENUINE RESIDUALS.** Measured, not read off the code, then pinned as
`ad6/test/core/instantiatortest.py::RuleOrderSemanticsTest` (6 tests, wired into
`instantiatorsuite.py`'s manual registry). Two rules over the identical packet space:
the first is reachable, the second UNREACHABLE, and swapping their positions swaps the
verdict exactly -- so the asymmetry comes from POSITION, not from the rules. Three
further cases pin the residual behaviour that LPM depends on:

| rules, in document order | rule 0 reachable | rule 1 reachable |
|---|---|---|
| `10.0.0.1/32` then `10.0.0.1/32` (identical) | yes | **no** -- fully shadowed |
| `10.0.0.1/32` then `10.0.0.2/32` (disjoint) | yes | yes |
| `10.0.0.0/24` then `10.0.0.0/8` (narrow, then WIDER) | yes | **yes** -- on its residual |
| `10.0.0.0/8` then `10.0.0.0/24` (wide, then narrower) | yes | **no** -- no residual left |
| `0.0.0.0/0` (or no condition at all) then anything | yes | **no** |

This is exactly iptables semantics, and it is the green light for §9's design: **the
translator can simply preserve FaVe's own `idx` order and the semantics follow.** Two
consequences. (a) The narrow-then-wider row is the property `_reprioritise_fib_lpm` and
the whole LPM-tiebreak class of bug (ad6/FAVE_CHANGES.md §14) turn on -- a model that
shadowed wholesale on any overlap would make every less-specific route dead, so this is
pinned rather than assumed. (b) The `_lpm_prio` machinery in the adapter becomes
unnecessary in principle: FaVe's delivered rule order already IS the semantics. Whether
`Rule.idx` as delivered reflects the final intended priority is Phase 1's question, and
`test_ad6_adapter_lpm_prio.py` is the existing pin on it.

**0.2 -- characterization tripwires in place.** `bench/ad6_ir_snapshot.py` snapshots
`Ad6Adapter._build_ir()` as a sha256 over the canonical IR plus a per-key SHAPE summary
(the hash answers "did anything move", the shape answers "where" -- a bare hash would
make every diff a bisection). Nine recipes covering every benchmark and every
measurement-relevant configuration, recorded in `bench/ad6_ir_snapshots.json`:

| recipe | IR bytes | build |
|---|---|---|
| wl_ifi | 11,949 | 0.1 s |
| wl_up | 429,962 | 1.7 s |
| wl_i2_plain / _faithful / _faithful_untag | 6.8 M / 10.1 M / 10.1 M | ~8 s each |
| wl_stanford_n2_plain / _faithful | 105,976 / 151,888 | 0.2 s |
| wl_stanford_n16_plain / _faithful | 544,767 / 732,853 | 0.9 s |

The whole set rebuilds in ~28 s. `fave/test/test_ad6_ir_snapshot.py` (18 tests) pins
them, with the three wl_i2 recipes behind `AD6_IR_SNAPSHOT_FULL=1` so the fast tier stays
fast. Verified in BOTH directions -- reproducible on a re-run, and a perturbed stored
hash is caught and localized to the key that moved. The suite also pins that the
tripwires can DISCRIMINATE the configurations they exist to cover (plain vs faithful, and
untag on vs off, must not hash alike); a snapshot that cannot tell two configurations
apart is not a tripwire. **wl_up's recipe calls `load_bench_metadata` on purpose**, bypass
and all -- a snapshot that did not pin the bypass could not witness Phase 4 removing it.

Verdict matrices need no new machinery: the 13 existing `fave/test/test_ad6_*` files
already pin them (e.g. `test_ad6_wl_ifi.py::test_reachability_matches_ground_truth`
compares the FULL wl_ifi matrix against `reachable.json`), and the archived
`bench/wl_*/eval/*.json` artifacts carry the rest.

**0.3 -- the adjudication rule, fixed BEFORE the first diff.** A changed snapshot is a
prompt to adjudicate, never by itself a regression: the IR being pinned is the one §9
exists to REPLACE, so a difference may equally well be the rewrite CORRECTING an existing
bug. Each difference is adjudicated against NetPlumber's own matrix (§9.4) and, on wl_i2,
`bench/i2_structural_oracle.py`. Re-recording happens in the SAME commit as the change
that moved it, so the diff shows both halves together; re-recording separately, or before
adjudicating, destroys the only thing the tripwire provides. **This rule is written where
someone hitting a failure will actually read it** -- the tool's module docstring and the
test module's docstring -- not only here.

**Still open from Phase 0, deliberately:** nothing blocking. Phase 1 may start.


### 9.6 Phase 1 -- the field layer, and what measuring the vocabulary found

**The vocabulary is bounded and was MEASURED, not guessed** (2026-09-12, by replaying
wl_ifi / wl_up / wl_i2 / wl_stanford through a recording `Ad6Adapter` subclass). Across
~95,000 rules the whole model surface is **17 match fields**, and of those exactly three
are ever REWRITTEN -- `packet.ether.vlan`, `in_port`, `out_port`. Also measured:
**zero negated matches anywhere**, and forwarding actions that always carry exactly one
port.

| benchmark | rules | distinct match fields | rewrite fields | max actions on one rule |
|---|---|---|---|---|
| wl_ifi | 191 | 5 | in_port, out_port, vlan | 2 |
| wl_up | 7,828 | 13 | in_port, out_port | 2 |
| wl_i2 (faithful) | 77,841 | 2 | vlan | 2 |
| wl_stanford N=16 (faithful) | 8,792 | 6 | vlan | **16** |

**DELIVERED: `fave/ad6/translate.py`'s field layer**, with `fave/test/test_ad6_translate.py`
(30 tests) written first. `field_to_match(RuleField, mutable)` -> one ad6 match element,
or `None` for a match-all address; `rewritten_fields(rules)` computes the model-wide
mutable set; `rewrite_field_for(name)` is the single source of the ad6 field name used by
BOTH `<fieldmatch field=...>` and `<action rewrite_field=...>`, so the two cannot drift.
The module is pinned by a test to branch on no device name, table name or benchmark.

**The design rule the field table encodes.** ad6's typed primitives
(`address`/`port`/`proto`/...) resolve against one model-wide global alias; `fieldmatch`
resolves NODE-SCOPED against this node's own SSA copy. For a field some rule rewrites,
only the latter is correct -- the field legitimately holds different values at different
points along one path. So the choice is a property of the WHOLE MODEL, and the mutable
set is an ARGUMENT rather than a hardcoded list: hardcoding it would be precisely the
workload assumption §9 exists to remove.

**A SILENT WRONG-ANSWER HAZARD, found by these tests before a single model was built.**
FaVe canonicalises a protocol at `RuleField` construction (`'tcp'` -> `'6'`). ad6's
`XMLUtils.CanonizeProto` looks its IANA table up BY NAME and, on a miss, silently returns
the no-next-header code under a `# TODO: error handling` comment:

```
CanonizeProto('tcp')      -> 0 0 0 0 0 1 1 0   (6)   correct
CanonizeProto('6')        -> 0 0 1 1 1 0 1 1   (59)  WRONG, no error
CanonizeProto('nonsense') -> 0 0 1 1 1 0 1 1   (59)  indistinguishable
```

Passing FaVe's own canonical value through would have turned **every tcp/udp/icmp match
into a no-next-header match**, undetectably -- `'6'` and a typo produce byte-identical
output. `translate.py` therefore carries an explicit number->name map and REFUSES any
protocol ad6 cannot name, rather than letting it through. The test asserts the round trip
against `CanonizeProto` itself (6 -> tcp -> 6), not merely against the name. Measured
protocol values across the benchmarks are 6, 17 and 58; ad6's table also knows 1.
**This is the case for testing the field layer at this granularity**: the bug is
invisible in a reachability matrix, and would have surfaced as a plausible-looking
verdict difference somewhere in Phase 3.

**A second, milder finding, recorded rather than fixed:** ad6's own vocabulary spells
ICMPv6 types `neighbor-solicitation` while FaVe emits `neighbour-...`. These become
plain string-keyed variables (`XMLUtils.ConvertToVariables`), so a spelling difference
does not corrupt anything as long as ALL rules come from one source -- which is exactly
what the structural translation guarantees and what the current adapter, mixing
FaVe-parsed rules with ad6-`IP6TablesParser`-parsed ones, does not. An argument for §9
that was not anticipated when it was written.

**TWO REPRESENTATION GAPS now block `rule_to_ad6`; both need a decision before Phase 1
continues.** Neither is a translation problem -- ad6's XML layer cannot express what
FaVe's model contains:

  1. **Multi-action rules.** `ad6/src/core/kripke.py:229` reads
     `Rule.xpath(ACTIONPATH)[0]` -- the FIRST `<action>` only; any further action is
     SILENTLY IGNORED. wl_stanford has rules carrying up to **16** actions (10,120
     `Forward`s over 8,792 rules), i.e. genuine multi-port fanout. wl_i2 and wl_up never
     exceed 2 (a `Rewrite` plus a `Forward`), which is why this has never been hit.
  2. **Multi-field rewrites.** `GenUtils.action` takes a single
     `rewrite_field`/`rewrite_value` pair, while **187 rules** across wl_ifi and wl_up
     rewrite more than one field at once. The Kripke layer is already fine here --
     `kripke.py:242` writes into a `Node.Rewrites` DICT -- so this gap is only in the XML
     surface, and is the cheaper of the two to close. Note also that it stores
     `int(rewrite_value)`, so a non-integer rewrite value has no representation today.

  A third, smaller observation from the same reading: `kripke.py:246`'s
  `Rules[Index+1].attrib['key']` false-transition IS the fall-through mechanism behind
  Phase 0.1's first-match-wins result -- independent confirmation of that measurement
  from the code side.


### 9.7 The two representation gaps: options worked out (2026-09-12)

Owner direction: *"Please work out the options for both gaps before touching ad6."*
Measured first, on all four benchmarks. **One of the two gaps turns out not to exist.**

#### 9.7.1 Gap 2 (multi-field rewrites) DISSOLVES -- no ad6 change needed

§9.6 recorded 187 rules rewriting more than one field, against a `GenUtils.action` that
carries a single `rewrite_field`/`rewrite_value` pair. Measuring WHICH fields co-occur
changes the conclusion entirely:

| rewrite field set | wl_ifi | wl_up | wl_i2 | wl_stanford |
|---|---|---|---|---|
| `packet.ether.vlan` alone | 0 | 0 | 77,451 | 3,417 |
| `in_port` alone | 16 | 318 | 0 | 0 |
| `out_port` alone | 0 | 159 | 0 | 0 |
| `in_port` + `out_port` | 17 | 159 | 0 | 0 |
| `in_port` + `vlan` | 1 | 0 | 0 | 0 |
| `out_port` + `vlan` | 10 | 0 | 0 | 0 |

**Every multi-field rewrite involves a PORT.** And `in_port`/`out_port` are not packet
fields being mutated -- they are FaVe's record of which port the packet entered or left
by, i.e. the forwarding decision itself. In ad6 a forwarding decision is an EDGE (a jump
to the interface node), not a field rewrite; the current adapter already reads it that
way (`Ad6Adapter._out_ports` looks in the `out_port` Rewrite to find the jump target).

So translating `in_port`/`out_port` as EDGES rather than as field rewrites leaves a
residual genuine-field-rewrite set of exactly `{packet.ether.vlan}`, **which is always
single-field** -- 80,868 of 80,868 occurrences. `GenUtils.action`'s single pair is
sufficient. Two corroborating facts from the same measurement:

  * **No rule anywhere has more than ONE `Rewrite` action** (max 1 across all four
    benchmarks), so there is never a per-forward differing rewrite, and ad6's per-NODE
    `KripkeNode.Rewrites` dict is the right granularity rather than a limitation.
  * **The non-integer rewrite values are exactly the port ones** (`'ifi.10_egress'`,
    `'adm.uni-potsdam.de.1_ingress'`; 61 in wl_ifi, 795 in wl_up). `kripke.py:242` does
    `int(Action.attrib['rewrite_value'])`, which would raise on these -- loudly, not
    silently. Treating ports as edges removes the only values that would ever reach it,
    so the `int()` stays sound instead of becoming a latent crash.

**Conclusion: gap 2 is closed by translating correctly, not by extending ad6.** This is
the outcome most favourable to the thesis -- the gap was an artefact of reading FaVe's
port bookkeeping as field mutation.

#### 9.7.2 Gap 1 (multi-action rules / fanout) is real. Three options.

wl_stanford genuinely fans one rule out to many egress ports -- up to 16 actions on a
single rule, 10,120 `Forward`s over 8,792 rules, and **552 of those multi-Forward rules
ALSO carry a rewrite**. `kripke.py:229` reads `Rule.xpath(ACTIONPATH)[0]`, the first
`<action>` only, and silently ignores the rest. It is the ONLY site in ad6 that reads an
action at all (grepped).

The Kripke layer is already fine: `KripkeStructure.Put` calls `_AppendTransition`, so
`_FTransitions[key]` is a LIST and several simultaneous TRUE edges out of one node give
OR/existential semantics for free -- which is the correct reading for a reachability
query (does SOME path arrive), and the same reading NetPlumber gives a branching flow.
The gap is purely in the XML surface and its reader.

**Option A -- fanout indirection node, wired in a post-pass. No ad6 change.**
The translator emits a rule whose single jump targets a synthetic `<key>_fanout` node,
and separately returns the list of (fanout node -> egress node) edges; the adapter
applies them with `Kripke.Put` after `ConvertToKripke`.
  * *Precedent:* this is exactly what `favemodel.wire_fanout` does today, already
    validated on wl_stanford, and post-pass wiring is the ESTABLISHED idiom here --
    `wire_edges` wires all topology connectivity the same way, by necessity, because
    interface nodes do not exist until conversion has run.
  * *For:* zero ad6 change, which is the outcome that best supports §0's "generic tool,
    low integration cost" thesis. The single rewrite rides on the single jump, cleanly.
  * *Against:* the XML no longer fully describes the model, so `translate.py` stops being
    a pure `model -> config` map and returns `(config, fanout_edges)`. Adds one synthetic
    node per fanout rule (552 on wl_stanford, 0 on wl_i2 -- negligible).
  * *Note:* the fragility §9.1 objects to in today's `wire_fanout` -- "must re-derive each
    route's rule position via the EXACT same filter+sort" -- does NOT carry over. Today it
    re-derives keys from the IR; here the translator emits the edge list directly as it
    assigns the keys.

**Option B -- multiple `<action>` elements per rule, read as multiple TRUE edges.**
Change `kripke.py:229` from `Rule.xpath(ACTIONPATH)[0]` to a loop over all actions, body
unchanged. The translator emits one `<action type="jump">` per `Forward` port.
  * *For:* the XML fully describes the model; no synthetic nodes, no edge manifest, no
    key coordination; `translate.py` stays a pure function. It is a ONE-SITE, one-line
    change, and a STRICT GENERALIZATION: every rule ad6 emits today has exactly one
    action, so iterating is byte-identical on all existing input -- pinnable by a test
    that an existing model's Kripke is unchanged.
  * *Against:* it is still a change to ad6, however small. The shared rewrite must be
    repeated on each of the N actions (harmless -- they write the same per-node dict
    entry -- but redundant), or the reader must take the rewrite from whichever action
    carries one.
  * *Risk check:* `ACTIONPATH` has exactly one reader in the whole of `ad6/src/`
    (`kripke.py:229`), and `<action>` is not among `RBODYPATHS`, so the rule's condition
    extraction cannot be affected.

**Option C -- one ad6 rule per (FaVe rule, port).** REJECTED, and the reason is Phase
0.1's own result: ad6 tables are first-match-wins, so several rules sharing an identical
condition would let only the FIRST fire, silently dropping every other port's
reachability. `Ad6Adapter._add_fwd_route`'s docstring already records this conclusion
from the previous encounter with the same problem. Recorded so it is not re-proposed.

**RECOMMENDATION: Option B**, with A as the fallback.
The deciding argument is that B's change is not a behavioural change at all but a
generalization of a single expression, verifiable by asserting that every existing
benchmark's Kripke is byte-identical before and after -- whereas A buys "no ad6 change"
at the price of a model the XML only half-describes, a translator that is no longer a
pure function, and a second mechanism to keep in step with the first. The thesis argument
for A is weaker than it looks: "ad6 needed one expression generalized to accept a list"
is not a meaningful integration cost, and §9.1's whole complaint is about mechanisms that
live outside the declared model.

**If B is taken, the work is:** generalize `kripke.py:229` to iterate; decide whether the
rewrite is repeated per action or taken from whichever action carries one; add an ad6
test that a multi-action rule yields one TRUE edge per action and that a single-action
rule is unchanged; then `rule_to_ad6` follows directly.


#### 9.7.3 DECISION (owner, 2026-09-12): option B, with A recorded as the fallback

*"Please go with option B but record A as a fallback."*

**B is DONE.** `ad6/src/core/kripke.py`'s `_HandleRule` now iterates
`Rule.xpath(ACTIONPATH)` instead of taking `[0]`, so every `<action>` contributes its own
TRUE transition. Seven tests in `ad6/test/core/kripketest.py::MultiActionRuleTest`,
written BEFORE the change and red against the old reader (with `tgt_a` reachable while
`tgt_b`/`tgt_c` were not -- the bug, exhibited), wired into `kripkesuite.py`'s manual
registry.

**The backward-compatibility claim was VERIFIED, not argued.** Every benchmark's Kripke
was digested (nodes with their props and rewrites, plus forward and backward transition
sets, canonicalised and hashed) before and after the change:

| benchmark | nodes | forward edges | digest |
|---|---|---|---|
| wl_ifi | 298 | 290 | identical |
| wl_up | 5,977 | 8,661 | identical |
| wl_stanford_n2_plain / _faithful | 1,196 / 1,286 | 1,920 / 2,100 | identical |
| wl_stanford_n16_plain / _faithful | 5,463 / 5,967 | 7,764 / 8,772 | identical |

All six byte-identical, as the "every existing rule carries exactly one action" argument
predicted. (wl_i2 was not digested -- its Kripke build is ~17 min -- but it is the
benchmark LEAST able to exercise this: its rules never exceed two actions and never fan
out.)

Two deliberate semantic decisions came with it, neither incidental:

  * **A rule with NO action now means "matches, forwards nowhere" -- a drop.** The old
    `[0]` raised `IndexError` on that shape. FaVe produces many such rules (2,315 in
    wl_up, 690 in wl_stanford N=16), so it needed a definite meaning rather than a crash;
    the rule still falls through, so it does not swallow what follows.
  * **Two actions disagreeing about one rewrite field are REFUSED**, not resolved by
    last-write-wins. This is the single new failure mode the loop introduces -- under
    `[0]` a second, disagreeing rewrite was simply unreachable. No benchmark produces it
    (measurement: no rule anywhere carries more than one `Rewrite` action), which is
    exactly why it must fail loudly if one ever does: a silently-picked rewrite is a wrong
    answer inside a normal-looking run.

**A stays on the record as the fallback**, and remains viable without modification: emit
a rule whose single jump targets a synthetic `<key>_fanout` node, return the
(fanout -> egress) edge list alongside the config, and apply it with `Kripke.Put` after
`ConvertToKripke` -- the idiom `favemodel.wire_edges`/`wire_fanout` already use. It costs
zero ad6 change and buys a model the XML only half-describes plus a translator that is no
longer a pure function. **The condition under which A should be revisited:** if the
per-NODE rewrite granularity ever stops being sufficient -- i.e. if some workload
produces a rule whose fanout targets need DIFFERENT rewrites, which is precisely what
§9.7.3's conflict guard will report. A's indirection node gives each target its own node
and therefore its own rewrite set, so it is the natural answer to that case, and the
guard is what would surface it. **Option C (one ad6 rule per port) stays rejected** on
Phase 0.1's first-match-wins result; see §9.7.2.


### 9.8 Phase 1 continued: ports are structural, and the port graph is a function

#### 9.8.1 DECISION (provisional): `in_port`/`out_port` are structural, not fields

FaVe carries port provenance as ordinary header bookkeeping, because NetPlumber's header
space is where all of its state lives. ad6 has real interface NODES
(`iface_key(dev, port)` + `_in`/`_out`), so "arrived via this port" is a property of the
PATH. The translator therefore emits an `<interface direction=...>` CONDITION for a port
match and an EDGE for a forward, and `field_to_match` REFUSES both field names outright --
so the model carries exactly one representation of a port rather than two that could
disagree.

Two measurements make this safe rather than merely tidy:

  * **Every rule carrying an `out_port` rewrite also carries exactly one `Forward`**
    (wl_ifi 27/27, wl_up 318/318). The Forward is always the authoritative forwarding
    decision; the rewrite is never the sole record of an egress.
  * **Half of those rewrites are not ports at all.** They set a 32-wide WILDCARD
    (`"x"*32` -- "forget where this came from"): wl_ifi 17 of 27 `out_port` and 17 of 34
    `in_port`, wl_up 159 of 318 and 159 of 477. `kripke.py`'s `int(rewrite_value)` could
    not represent a wildcard under ANY scheme, so treating port rewrites as field
    mutations was never an option that closed.

With ports structural, the residual rewrite set is `{packet.ether.vlan}` -- always single
-field, always integral -- which is what makes §9.7.1's "gap 2 dissolves" true in the
implementation and not only on paper.

**PROVISIONAL, and flagged as such in the code.** "Matches `in_port == P`" and "the path
traversed interface node P" are equivalent by construction, but that is VALIDATED only
when Phase 3 reproduces each benchmark's verdicts. If it does not hold, the alternative is
to keep ports as fields and solve the wildcard/int problem inside ad6 instead -- which is
strictly more work, which is why it is the fallback and not the default.

#### 9.8.2 The port graph: measured, and uniform across all three device shapes

`Ad6Adapter.add_wiring` is a **no-op** -- *"internal device pipeline plumbing; not needed
for a flat dst-IP model"*. FaVe DECLARES its intra-device pipeline
(`AbstractDevice.wiring`, a list of unidirectional port-to-port links) and the current
adapter discards it, then rebuilds an approximation of it by recognising table-name
suffixes (`.acl_in`, `.routing`, `.pre_routing`). The structural translation gets the real
thing for free. Measured 2026-09-12:

| benchmark | devices | devices with declared wiring | wiring pairs |
|---|---|---|---|
| wl_ifi | 17 | 1 (the `ifi` router) | 8, emitted twice -- dedup required |
| wl_up | 136 | 136 | 952 |
| wl_stanford | 48 | **0** | 0 |

The three shapes look different and resolve identically. wl_up declares the full packet
-filter pipeline (`pre_routing_input -> input_filter_in -> internals_in -> ...`); wl_ifi
declares only its router's four-stage chain; wl_stanford declares NONE, because its
pipeline is expressed as SEPARATE `in.*`/`mid.*`/`out.*` devices joined by inter-device
links. That last row is worth dwelling on: the stage-prefix convention §9.1 objects to is
not a pipeline encoding at all, it is what a pipeline looks like when it has been spread
across devices -- and inter-device links already describe it, with no name parsing.

**THE DECISIVE STRUCTURAL FACT: `port -> table` is a FUNCTION.** Across all three
benchmarks, no port appearing in any rule's `in_ports` maps to more than one table. So a
port names an unambiguous table entry, and `model_to_config` can resolve a jump target
without a second pass, a position re-derivation, or any name recognition:

  1. dedup the declared wiring;
  2. `port -> table` from the rules' own `in_ports`; entry is that table's rule 0, since
     per-rule `in_ports` are emitted as `<interface>` CONDITIONS, leaving every table a
     single linear first-match chain (§9.7.3, Phase 0.1);
  3. to resolve a forwarded port P: follow intra-device `wiring` if P is a wiring source;
     else P's own table if it has one; else follow the inter-device LINK from P to the
     next device's port and resolve there.

Everything the current adapter recovers by convention is recovered here from declared
structure. Nothing in the rule is consulted except its matches, its `in_ports` and its
actions.


### 9.9 Generators and probes: no mechanism of their own

A generator is a device with ONE rule that forwards to its own port; a probe is a device
with one rule that forwards to its own ACCEPT port. The topology's existing links carry a
generator onward and a probe inward, and `PortGraph` resolves both exactly as it resolves
any other device -- so `model_to_config` contains no generator or probe case at all.

That is the design working, not a coincidence. `Ad6Adapter`'s `_gen_firewall` needs four
branches (is this a ruleset device? is the attachment FaVe's `output_filter_in` marker
port? is the port admitted? which `entry_key` applies?) precisely because it reconstructs
meaning. A translator carrying declared structure has nothing left to decide.

**Measured vocabulary (2026-09-12), and it is small:** every generator and probe field
carries EXACTLY ONE value across all four benchmarks, so no disjunction support is needed
-- and a multi-valued field is REFUSED rather than half-supported, because ad6 ORs
repeated `<vlan>`/`<port>` elements but CONJOINS two `<ip>` elements, which would make a
two-valued address silently unsatisfiable rather than either value.

| benchmark | generators | probes | generator fields | probe fields |
|---|---|---|---|---|
| wl_ifi | 17 | 17 | vlan (16), ipv4.source (10) | none |
| wl_up | 137 | 137 | ipv6.source (137, all `::/0`) | `filter_fields` dport (21) |
| wl_i2 | 9 | 9 | ipv4.destination (9, all `/0`) | `test_fields` vlan (9, all 0) |
| wl_stanford | 16 | 16 | ipv4.destination (16, all `/0`) | `test_fields` vlan (16, all 0) |

Two decisions the measurement forced:

**A generator's MUTABLE field becomes a REWRITE on its injection edge, not a match**
(AD6_PLAN.md §5.4 B2, found the hard way there and re-derived here). wl_ifi's generators
declare real VLAN tags. A match would leave the field a free SSA variable that any
downstream admission check could satisfy by picking a convenient value, silently
over-approximating reachability instead of gating it. Pinned by a pair of tests: a source
tagged 48 must NOT reach a device admitting only 10, and one tagged 10 must.

**A PROBE ACCEPTS ANY INCOMING TRAFFIC (owner decision 2026-09-13):** *"Please make the
probe accept any incoming traffic. If we need filtering at probes, we can implement that
later, e.g., when used in a benchmark."* `probe_device` therefore carries no match at all,
and `probe_entry_key` is reachable exactly when a packet arrives at the probe's port --
the reachability question every in-scope benchmark actually asks. Every refutation in the
translator's test suite consequently comes from the PATH (a generator's own constraint, a
device's match, a missing link), never from the probe.

This also removed the accept-port indirection §9.9.1 had introduced: with no probe
condition to enforce, that edge was inert machinery kept only against a future need. What
a future implementer needs instead is the FINDING below plus the measured shapes above --
wl_i2 and wl_stanford probes declare `test_fields={'packet.ether.vlan': ['0']}`, 21 wl_up
probes declare `filter_fields={'packet.upper.dport': ['22']}`, and which of the two to
enforce is a measurement-affecting choice (generality-debt item 4) that belongs to the
caller, where it can be stamped.

#### 9.9.1 A TERMINAL NODE'S OWN CONDITION IS NOT ENFORCED -- found here, and it matters

In ad6 a rule's condition gates its OUTGOING edges: `_ConvertNodesToImplications` makes a
node's proposition follow from its INCOMING transitions, and a transition carries the
condition of the node it LEAVES. **A terminal rule's match is therefore enforced by
nothing.** Asking whether its node is reachable asks only whether a packet ARRIVED -- not
whether it satisfied the probe.

Measured directly rather than reasoned about: a probe demanding dst `192.168.0.0/16`
behind a router forwarding only `10.0.0.0/8` came back REACHABLE.

**This is not a defect to fix; it is what "reachable" means here**, and the encoding is
consistent about it. It is recorded because it is INVISIBLE and the failure it causes is
silent over-approximation -- reporting reachable what is not, the one direction a
soundness error must never go.

It explains two existing pieces of this codebase. It is why
`favemodel.probe_vlan_literals` forces a probe's declared VLAN as explicit per-bit
literals onto the QUERY instance rather than relying on the probe node's own condition.
And it is why probe filtering, when it is wanted, cannot simply be a match on the probe's
rule: the condition has to sit on a real transition, which means giving the probe one
outgoing edge to a dedicated accept port and querying THAT node.

**Pinned at the ad6 level, not the translator's**, since it is a property of the encoding
rather than of probes: `ad6/test/core/instantiatortest.py::TerminalConditionTest`, three
tests -- that a contradictory terminal condition is reachable, that the SAME condition
does bite once the rule has an outgoing edge, and a control proving the contradiction is
genuine and not a broken fixture. The first will start failing if ad6 ever begins
enforcing terminal conditions, which would be a real semantic change and would make probe
filtering expressible directly.


### 9.10 Phase 2: the selector works, the differential does not -- `out_port` is INTENT

`Ad6Adapter(translation='semantic'|'structural')` is in place and stamped, the structural
payload crosses the subprocess boundary, and the bridge builds a model from it. wl_ifi runs
end to end under both paths. **They do not agree, and the cause is a genuine semantic gap
that §9.8.1's provisional decision got half right.**

| wl_ifi, 289 pairs | reachable |
|---|---|
| semantic | 70 |
| structural | 16 |
| differ | 54 pairs, ALL in one direction (structural more restrictive) |

#### 9.10.1 Two real corrections found on the way, both keepers

**`Rule.idx` IS A PRIORITY, NOT A LIST POSITION.** `table_to_ad6` originally asserted the
two agreed and refused when they did not -- which is how the mistake surfaced, on
`admin.ifi` carrying `idx=65535` at list position 1. FaVe hands rules out in an order that
often disagrees with their own indices: 4 of wl_ifi's 38 tables, 9 of wl_i2's 36, 16 of
wl_stanford's 96, 138 of wl_up's 1,134. Lower index wins (65535 is the max-priority default
rule, and `np_preparation._reprioritise_fib_lpm` repairs a FIB by reassigning indices in
descending prefix-length order). Since ad6 evaluates a table first-match-wins in DOCUMENT
order, emitting the list as handed over would run a default rule before the specific rule it
backs up. Now sorted by ascending idx, with duplicates and partially-indexed tables refused
(measured: neither occurs).

**A SERIALIZED CONFIG SILENTLY LOSES ITS XPATHS.** `GenUtils.config()` declares
`xmlns="http://config"` on the root while every child it builds carries no namespace --
consistent in memory, where ad6's unprefixed xpaths match. Serialize it and that
declaration becomes the document's DEFAULT namespace, so on re-parse EVERY descendant is in
it and every one of those xpaths matches NOTHING: no error, just an empty model. The adapter
re-roots onto a plain `<config>` before serializing. Pinned, with a negative control, by
`fave/test/test_ad6_translation_flag.py`.

#### 9.10.2 THE OBSTACLE: `in_port` is provenance, `out_port` is intent

§9.8.1 decided both port fields are structural -- "which port a packet came in on is a
property of the PATH, expressed as an `<interface>` condition". **That is correct for
`in_port` and wrong for `out_port`,** and the difference is not a detail:

  * `in_port` records where the packet HAS BEEN. ad6 has exactly that: the path really did
    traverse the ingress interface node, so the condition is satisfiable and means what it
    says.
  * `out_port` records where the packet IS GOING -- a decision written by one rule
    (`Rewrite(out_port=...)` in `routing`) and READ by a later rule in the same device
    (`post_routing`). ad6 has no counterpart: it makes the egress decision by TAKING AN
    EDGE and has no readable "where am I headed" register.

Translating an `out_port` MATCH as "the path traversed that egress interface" is therefore
circular, and the trace shows it exactly. Following `source.admin.ifi -> probe.office.ifi`
node by node, the structural model crosses the whole router correctly -- ingress, `acl_in`,
`routing`, `acl_out`, all 22 `post_routing` rules -- and then dies at
`favenet_ifi_5_egress_out`, whose own Gamma is `constant true`. The rule that would LEAD to
that node demands the path had already been through it.

**Where it bites, measured:**

| benchmark | `out_port` matched in | count |
|---|---|---|
| wl_stanford | nowhere | 0 |
| wl_i2 | nowhere | 0 |
| wl_ifi | `post_routing` | 34 |
| wl_up | `routing` 318, `post_routing` 318, `forward_filter` 2, `output_filter` 2 | 640 |

So the structural path is already sound for the two benchmarks the headline numbers come
from, and blocked on the two with a real packet-filter pipeline. wl_ifi's 34 split cleanly
into two shapes: 17 rules with an `out_port` match and one Forward (egress selection), and
17 with `in_port` + `out_port` and NO action -- the hairpin drop, "do not send a packet back
out the interface it arrived on".

**What the semantic path does about this: nothing.** It never reads `post_routing` at all
(it dispatches only on `.routing`/`.1`/`.acl_in`/`.acl_out`/`.pre_routing`), so it does not
see the hairpin rule and over-approximates by construction -- and still matches wl_ifi's
accepted answer, because no wl_ifi reachability question turns on a hairpin. That is worth
stating plainly: the 70-pair result is not evidence that ignoring `out_port` is CORRECT,
only that it is harmless on this workload.

**Options, none of them free:**

  1. **Make `out_port` a genuine mutable field.** FaVe's `model.ports` already maps a port
     name to a number, so integer values exist, and the width is 32. Blocker: half of the
     port rewrites are a 32-wide WILDCARD (`"x"*32`, "forget where this came from"), and
     `kripke.py` stores a rewrite as `int(rewrite_value)` -- there is no "clear" operation.
     A reserved sentinel would be readable by a later match and is therefore not sound.
  2. **Expand the register into the graph** -- one post-routing branch per possible egress,
     so "intent" becomes "which branch you are on". Structurally faithful and needs no ad6
     change, at the cost of a per-device product blow-up (wl_up: 136 devices x their port
     counts).
  3. **Drop `out_port` matches, and say so.** Matches what the semantic path effectively
     does, keeps the model small, and is an over-approximation that must then be STAMPED
     and reported -- the hairpin check disappears. This is the only option that silently
     weakens the model, which is the direction this plan has refused everywhere else.


### 9.11 Option 1 implemented: ports are fields. The circularity is gone.

Owner decision 2026-09-13: *"Please go with option 1."* `in_port`/`out_port` are ordinary
mutable fields, and §9.8.1's "ports are structural" is withdrawn for `out_port` (it stands
for `in_port`'s role in the port GRAPH, which is a different mechanism -- see below).

**ad6 gained two capabilities, both test-first and both strictly additive:**

  * **Several rewrites per action.** `<rewrite field= value=/>` children alongside the
    existing `rewrite_field`/`rewrite_value` attribute pair, which still works and means
    the same thing (pinned by a test that the two forms agree). Needed because wl_ifi's
    `routing` rules set `out_port` AND `vlan` together.
  * **CLEAR -- a rewrite with no value**, meaning the field becomes UNCONSTRAINED
    downstream. In the SSA encoding that is the ABSENCE of any axiom on that edge: neither
    a REWRITE forcing the target's bits to a constant nor a FRAME copying the source's
    across. Spelled as a valueless element rather than a reserved integer on purpose -- a
    sentinel would still be a VALUE, readable by a rule testing for that port.
    `instantiatortest.ClearedFieldTest` pins all three cases against each other, because
    the two failure modes are opposite and both silent: frame-instead-of-clear wrongly
    REFUTES, zero-instead-of-clear wrongly MATCHES.

**The translator uses DENSE IDS, not FaVe's port numbers.** The field is only ever compared
for equality against ids this module assigns, so the numbering is free -- and much cheaper:
wl_ifi needs 7 bits and wl_up 13, against the 32 `FIELD_SIZES` gives the field, and ad6
pays that width per node per mutable field. Measured declaration on wl_ifi:
`{'in_port': 7, 'out_port': 7, 'vlan': 12}`.

**FaVe supplies the whole lifecycle; nothing is synthesised** -- `pre_routing` sets
`in_port`, `routing` sets `out_port` (and reads it), `post_routing` reads both then clears
both.

**RESULT: the circularity is gone and the direction of the disagreement FLIPPED.**

| wl_ifi, 289 pairs | reachable | vs `reachable.json` |
|---|---|---|
| semantic | 70 | **exact match, 0 roles differ** |
| structural, ports structural (§9.10) | 16 | 54 pairs missing |
| structural, ports as fields (this) | 122 | 8 roles with EXTRA reachability, 0 missing |

The over-approximation is now the only gap, and it is one-directional: the structural model
never refuses something ground truth calls reachable. The affected sources are exactly
those whose generator declares NO `packet.ipv4.source` (`cam.ifi`, `hpc_ic.ifi`,
`hpc_mgt.ifi`, `mgt.ifi`, ...), which leaves their source address a free variable.

**Working hypothesis for Phase 3, recorded rather than acted on.** Both models contain the
identical `acl_out` rules -- verified by dumping each -- including, for VLAN 464:

```
idx 7432  src=10.0.0.0/16   dst=10.0.14.0/23  -> DROP     (internal sources not listed above)
idx 7433  src=0.0.0.0/0     dst=10.0.14.0/23  -> PERMIT   (anything else)
```

so a free source address simply picks its way past 7432 into 7433. The two paths then
differ in WHICH acl_out group a packet is subject to: the semantic path binds the group to
the EGRESS PORT (`out_port_vlan`), while the structural path applies the group matching the
packet's own VLAN FIELD -- which `routing` rewrites on only 10 of its rules, so a packet
may still be carrying its INGRESS vlan when it reaches `acl_out`. If that is the mechanism,
the structural reading is the one faithful to FaVe's rules and the semantic one is a
structural shortcut that happens to be right here; that has to be adjudicated against
NetPlumber (§9.3 Phase 0.3), not settled by which one matches the number we already have.

**A diagnostic that does NOT discriminate, recorded so it is not repeated:** asking whether
an `acl_in` rule's NODE is reachable says nothing about whether its condition held. A rule
is entered by its predecessor's FALSE (fall-through) edge as well as by matching, and a
rule's condition gates its OUTGOING edges (§9.9.1). Reachability of the rules for VLANs 48,
463 and 464 from a source declaring VLAN 477 is therefore expected and proves nothing.


### 9.12 Adjudication: the acl_out hypothesis is REFUTED; `<interface>` is a free variable

Owner asked (2026-09-13) for §9.11's acl_out-grouping hypothesis to be adjudicated against
NetPlumber. It does not survive first contact with the shared model, and chasing it led to
the actual root cause, which is more serious and invalidates a §9.8.2 design decision.

#### 9.12.1 The hypothesis, refuted by the model both engines consume

§9.11 guessed that the two paths applied DIFFERENT acl_out groups -- the semantic path
binding the group to the egress port, the structural path to the packet's own VLAN field,
"which `routing` rewrites on only 10 of its rules". Dumping `ifi.routing` settles it: all
10 rules rewrite VLAN, one per destination prefix, and the route to admin's `10.0.14.0/23`
sets `vlan := 464` together with `out_port := ifi.4_egress`. **Both paths therefore apply
acl_out group 464.** The hypothesis was wrong, and no NetPlumber run was needed to retire
it -- the shared model answers it directly.

#### 9.12.2 The real cause, traced: ad6's `<interface>` condition is NOT reachability

wl_ifi's ingress ACL denies cam outright -- `ifi.acl_in` idx 7632, `vlan=477 -> DROP`,
matching `reachable.json`'s `cam.ifi: []`. The structural model lets cam through anyway.
Reading the VLAN bit-vector out of a satisfying assignment, node by node along the path:

| node | vlan |
|---|---|
| `favenet_source_cam_ifi_1_out` | 477 |
| `favenet_cam_ifi_2_in` / host rules / `favenet_cam_ifi_1_out` | 477 |
| `favenet_ifi_acl_in_in_in` and every `acl_in` rule | **4095** |

4095 is written by exactly one rule: `ifi.pre_routing` r0, whose condition is the ingress
interface `ifi.1_ingress` -- the INTERNET UPLINK, not cam's port. The solver fires that
rule, relabels the packet 4095, and sails past the vlan-477 deny into `acl_in`'s final
`vlan=4095 -> PERMIT`.

It can do that because **the interface condition is a free variable**:

```
node favenet_ifi_1_ingress_in  REACHABLE from cam : False
variable favenet_ifi_1_ingress_in in the model    : True
```

The node is provably unreachable and the variable is nonetheless true. `<interface
direction="in">K</interface>` becomes `XMLUtils.variable(K + '_in')`, and nothing ties that
variable to the node of the same name having been entered -- `_ConvertNodesToImplications`
constrains TRANSITIONS, not node propositions. §9.8.2's design ("entry is rule 0 always;
per-rule `in_ports` become `<interface>` CONDITIONS, leaving every table one linear
first-match chain") is therefore UNSOUND: a packet may take a rule written for a different
ingress port.

**How the semantic path avoids it, and why this is the deeper lesson:** it never asks the
solver which port a packet came in on. `entry_key(device, port, ir)` sends a packet
arriving on port P to a PORT-SPECIFIC entry node, so ingress discrimination lives in the
GRAPH. That is the same shape as §9.10.2's finding about `out_port` -- twice now, a thing
FaVe expresses as a per-rule attribute has turned out to need a structural counterpart in
ad6 rather than a condition. The difference is that `out_port` had no structural
counterpart at all (hence option 1, ports as fields), whereas `in_ports` has an obvious
one.

#### 9.12.3 The fix, and why it is cheap

Drop the `<interface>` condition for `rule.in_ports` and make ENTRY port-specific: for each
(table, entering port) emit a chain containing only the rules applicable to that port, with
the fall-through running down that chain.

Measured, this barely grows the model, because heterogeneous `in_ports` are rare:

  * `ifi.acl_in`, `ifi.acl_out`, `ifi.routing` and every host `.1` table have UNIFORM
    `in_ports` across their rules -- one chain, exactly today's output.
  * `ifi.pre_routing` has 17 rules across 17 ports, ONE rule per port -- 17 chains of one
    rule each, i.e. the same 17 rules, just reachable only from their own port.

So the specialization is per (table, port) and collapses to a no-op wherever a table's
rules agree on their ports, which is almost everywhere. It also removes an unsound
construct rather than adding a guard around it, which is the right direction: the
`<interface>` condition cannot be made sound without ad6 tying interface propositions to
reachability, a core change with unclear blast radius and no other caller asking for it.


### 9.13 Port-specific entry -- and wl_ifi AGREES, exactly

§9.12.3's fix, implemented. `rule.in_ports` emits NO condition; instead
`PortGraph.chains()` compiles each table once per ENTERING PORT, holding only the rules
that port can reach, and `entry(port)` names rule 0 of that port's own chain. Ingress
discrimination now lives in the graph, where the solver cannot wish it away.

**wl_ifi, 289 pairs:**

| | reachable | vs `reachable.json` | vs the other path |
|---|---|---|---|
| semantic | 70 | 0 of 17 roles differ | — |
| structural | 70 | **0 of 17 roles differ** | **0 pairs differ** |

**The first rung of Phase 3 is green: the structural translation reproduces wl_ifi's full
reachability matrix exactly, pair for pair, and matches ground truth independently.**

**Cost, measured before implementing rather than discovered after.** Total rules before ->
after: wl_i2 77,841 -> 78,047 (1.00x), wl_up 7,828 -> 7,892 (1.01x), wl_ifi 191 -> 223
(1.17x), wl_stanford 8,792 -> 14,821 (1.69x, its `in.*` stage carrying the whole spread).
The expansion is small because heterogeneous `in_ports` are rare: `acl_in`, `acl_out`,
`routing` and every host `.1` table have UNIFORM `in_ports` and compile to exactly one
chain, while `ifi.pre_routing`'s 17 rules across 17 ports become 17 chains of one rule --
the same 17 rules, each now reachable only from its own port.

Details worth keeping:

  * **A rule with no `in_ports` joins EVERY chain of its table** (155 such rules in wl_up),
    since it is reachable from every port that enters.
  * **A table no port enters yields one chain with `port=None`** -- a generator's own
    injection table, which is entered by key rather than by arrival.
  * Chain identity is part of the rule key (`chain_key`), so the same FaVe rule compiled
    for two ports is two distinct ad6 nodes, as it must be: they have different
    predecessors.

**What this closes, and what it cost to find.** Three successive attempts at port handling,
each refuted by measurement rather than argument: ports as `<interface>` conditions for
BOTH provenance and intent (§9.8.1, circular for `out_port` -- killed every path at its own
egress node); ports as fields with `in_ports` still a condition (§9.11, unsound -- the
condition is a free variable, so a packet fired a rule written for the Internet uplink);
and now ports as fields with ingress in the graph. The pattern across all three: **FaVe
states as a per-rule attribute what ad6 can only express structurally, and each time the
give-away was a verdict that moved in the direction of MORE reachability.**


### 9.14 Phase 3 rung 2: wl_stanford N=16 plain -- identical, and it lands on 165

| wl_stanford N=16 plain, 256 pairs | reachable | wall |
|---|---|---|
| semantic | 176 | 1,022 s |
| structural | 176 | 1,498 s (1.47x) |
| **differ** | **0 pairs** | |

**Both paths give 165 of the 240 NON-SELF pairs** -- exactly the figure §5.4 B3 records
against the NetPlumber-proven plain oracle. The 176 is that 165 plus 11 reachable
self-pairs (5 of the 16 self-pairs are unreachable), which an all-pairs sweep includes and
the archived measurement did not. So the structural translation reproduces the canonical
answer, and does so through a model built from FaVe's declared structure with no stage-name
recognition anywhere.

The 1.47x wall cost tracks the 1.69x model growth (8,792 FaVe rules -> 14,853 ad6 rules in
981 chains), which is the price of per-port entry chains (§9.13).

**NOTE ON THE ORACLE, since wl_stanford differs from wl_ifi here:** `reachable.json`
declares 240 pairs -- every non-self pair -- so like wl_i2's all-reachable mesh it CANNOT
discriminate, and the differential test's independent ground-truth check (which wl_ifi has)
would be vacuous on wl_stanford. The reference here is the 165-pair NetPlumber oracle
recorded in §5.4, not the shipped JSON.

#### 9.14.1 Three constraint classes the structural path carries and the semantic one drops

Reaching this rung required three fixes, and all three are the same shape: FaVe states a
constraint the semantic path never looks at, so nothing had ever exercised it.

  1. **Transport port RANGES as masked bit-vectors.** wl_stanford has 236 of them against
     1,321 plain decimals (`1xxxxxxxxxxxxxxx` = 32768-65535, `000000000001010x` = FTP's
     20-21). It surfaced as a CRASH -- `int('000000000001010x')` inside ad6's `CanonizePort`
     -- which is the right failure. ad6 already had the answer: its `<port>` text accepts a
     `value/prefix` form that truncates the bit-vector, exactly a prefix mask. A mask whose
     don't-cares are not a suffix is REFUSED, since ignoring the low bits would WIDEN the
     match. The semantic path never reads transport ports at all.
  2. **Fields that are MATCHED but never rewritten still need a declared width**, because a
     `<fieldmatch>` is resolved against a bit-vector. Collecting only the rewritten set left
     wl_up raising on `related` (3,137 matches). Caught by checking wl_up ahead of its turn
     rather than by waiting to be surprised.
  3. **Some field values are not numbers in any base** -- `module.limit` = `'900/min'`,
     `module.ipv6header.header` = `'ipv6-route'`. No width helps. These are now refused at
     TRANSLATION time, naming field and value, instead of failing deep inside the
     instantiator long after the causing rule is out of sight. wl_up's structural build
     stops there today, which is the honest state for a rung not yet reached.

The asymmetry is itself a result worth stating plainly: **the structural translation carries
constraints the semantic one discards.** That is the point of the rewrite, and it is also
why its numbers need not have matched the archived ones -- that they DO, on the benchmark
where a real oracle exists, is the evidence that the extra constraints are right rather than
merely extra.


### 9.15 Phase 3 rung 3: wl_stanford N=16 FAITHFUL -- identical, and 165 again

| wl_stanford N=16 faithful, 256 pairs | reachable | wall |
|---|---|---|
| semantic | 176 | 1,194 s |
| structural | 176 | 1,712 s (1.43x) |
| **differ** | **0 pairs** | |

**165 of the 240 non-self pairs, matching the archived `faithful_vlan=True` figure
exactly** (`bench/wl_stanford/eval/ad6_faithful_N16_portscoped_sandbox.json`). Faithful
and plain also agree pair-for-pair under the structural path (0 of 256 differ), which
reproduces §5.4 B3's own finding that wl_stanford's VLAN admission does not move its
reachability answer.

**This is the first run of the VLAN mutable-field path at scale in the structural
translation**, and the part plain mode could not exercise: 3,417 VLAN rewrites and 4,267
VLAN matches become 12 bits of per-node SSA state across ~15k rule nodes, with a
`<fieldmatch>` per match and a `<rewrite>` per assignment. Plain mode declares no mutable
field at all, so none of that machinery ran there.

#### 9.15.1 A DRIVER difference on self-pairs, not a translation difference

The archived faithful run reports 165 reachable over 256 queries with **zero self-pairs
among them** -- all 16 were unreachable. Both adapter-path translations find **11 of 16
self-pairs reachable** (5 unreachable). The non-self figure, which is what the NetPlumber
oracle covers, is 165 either way.

This is a difference between `bench/ad6_faithful_measure.py` and the `Ad6Adapter` path, not
between the two translations -- they agree with each other on every one of the 256 pairs,
self-pairs included. It cannot therefore affect the differential. It does mean the two
DRIVERS are not asking quite the same question when a source and a probe hang off the same
router, so §9.4's "state the denominator" rule applies whenever the two numbers appear side
by side: **165 of 240 non-self is the comparable quantity; 176 of 256 is not.**

Recorded rather than chased: it is orthogonal to §9's question, and chasing it now would be
the same mistake as §9.11's acl_out hypothesis -- reasoning about a number before the thing
it is supposed to test has been established.


### 9.16 wl_i2 PLAIN: the differential differs on 11 pairs -- and structural is RIGHT

| wl_i2 plain, 72 pairs (exclude-self) | reachable | wall | peak |
|---|---|---|---|
| semantic | **72** (none unreachable) | 3,370 s | 2.4 GB |
| structural | **61** | 5,387 s (1.6x) | 10.3 GB (4.3x) |
| differ | **11 pairs** | | |

**The 11 are EXACTLY the archived set** -- `chic`->{hous,kans,losa,salt,seat} and
`atla`/`newy32aoa`/`wash`->{kans,seat} -- the pairs corroborated three independent ways in
§5.5: ad6 via SAT, FaVe+NetPlumber via HSA, and `bench/i2_structural_oracle.py` by a third
method over the raw JSON. Set equality checked, not eyeballed.

**This is the differential FAILING and that being the right outcome.** Everywhere else a
difference meant the structural path was wrong. Here the semantic path is: in plain mode it
finds wl_i2 entirely reachable, which §5.5 already recorded as plain mode being INSUFFICIENT
for i2, and the structural path recovers the corroborated answer without being asked.

#### 9.16.1 Why: `faithful_vlan` is INERT for the structural path

`Ad6Adapter._build_structural` never reads `self._faithful_vlan` -- verified by walking its
AST, not by grepping prose. It translates FaVe's rules as given, and FaVe's i2 rules carry
VLAN matches and rewrites regardless of any flag. The semantic path's plain mode
DELIBERATELY discards VLAN (the adapter's own docstring: *"VLAN is structural only (which
port's ACL group applies), never a match field"*), which is what makes plain i2 come back
all-reachable.

So the plain/faithful distinction is a property of the SEMANTIC path, not of the model. Two
consequences, and the second is a defect:

  * It explains §9.15's otherwise-curious result that wl_stanford structural plain and
    structural faithful agree pair-for-pair on all 256. They are the same computation.
  * **A structural result stamped `faithful_vlan: false` is not a plain result.** That
    breaks the generality-debt gate's own rule -- the stamp must say what produced the
    number -- and it must be fixed before any structural measurement is quoted. The honest
    stamp is that `faithful_vlan` does not apply under `translation: structural`.

#### 9.16.2 What the plain rung was, and what it was not

§9.16's plain sweep was described in advance as a scale-and-plumbing test, because a 72/72
semantic matrix has no refutations and agreement on it would prove nothing. That reading
was right about the SEMANTIC side and wrong about the rung: the structural side produced 11
refutations, and they are the corroborated ones. The rung turned out to be the strongest
correctness evidence in Phase 3, by accident of the semantic path being the weaker one here.

**Cost.** 1.6x wall and 4.3x peak RSS. The memory gap is explained by the same mechanism:
structural carries VLAN as a 12-bit mutable field across ~78k rule nodes while semantic-plain
carries no mutable field at all. The FAITHFUL comparison, now running, should narrow it,
since semantic declares VLAN mutable there too -- a prediction this record commits to before
the result.


### 9.18 wl_up's fields: use FaVe's OWN encoding, not an invented one

Owner question 2026-09-14: *"Could you please elaborate on how exactly you modeled these
fields and values? And did you double check on how that was modeled for NetPlumber as a
backend?"* -- the second half of which had NOT been checked, and answering it overturned
the design.

**What the first attempt did, and why it was wrong.** `module.limit` ('900/min') and
`module.ipv6header.header` ('ipv6-route') were carried as UNINTERPRETED propositions -- one
boolean per (field, raw value) -- on the reasoning that the values "are not numbers in any
base". Checking NetPlumber shows they are:
`util.ip6np_util.field_value_to_bitvector`, which is exactly what
`netplumber/adapter.py` feeds its backend, normalises them to real numbers over FaVe's own
declared widths.

| field | value | FaVe -> NetPlumber | meaning |
|---|---|---|---|
| `module.limit` | `900/min` | `...1101001011110000` | **54000** = 900 x 60, 32 bits |
| `module.ipv6header.header` | `ipv6-route` | `00101011` | **43**, the IPv6 Routing header number, 8 bits |
| `packet.ipv6.icmpv6.type` | `neighbour-advertisement` | `10001000xxxxxxxx` | **136**, distinct from solicitation's 135 |

So the opaque form was wrong twice over. NetPlumber models these as NUMBERS, and keying a
proposition on the RAW STRING would have made `'900/min'` and `'54000/sec'` -- the same rate
-- two different conditions. Both are now normalised through FaVe's own function, which makes
ad6 and NetPlumber model the same quantity BY CONSTRUCTION rather than by coincidence, and
the width comes from `netplumber/mapping.py`'s `FIELD_SIZES` rather than a number chosen
here.

The numeric form is also strictly stronger: two different rates are two different numbers in
one field, so no packet satisfies both. The opaque form made them independent booleans and
needed a model-wide single-value guard to stay sound. That guard, and the `<opaque>` element
added to ad6 for it, are both REMOVED -- leaving an unused element that looks meaningful is
the trap §9's own `resolve_interface` cleanup exists to avoid.

**The ICMPv6 fix is INDEPENDENTLY CONFIRMED by the same check.** FaVe's normaliser spells
these the British way with distinct type numbers (135 solicitation, 136 advertisement); ad6's
table spells them the American way and returned type 0 for both, colliding with each other
and with every typo. After translation ad6 encodes 135/136/128, the same NUMBERS NetPlumber
uses -- the two differ only in bit LAYOUT (ad6 puts the number in the low 8 bits of 16,
FaVe in the high 8 with the code don't-care), which is internal to each engine and does not
affect agreement.

**wl_up's structural build**: 8,166 rules in 1,280 chains, 2,528 edges, mutable
`{in_port: 12, out_port: 12, module.ipv6header.header: 8, module.limit: 32, related: 8}`.

**The lesson, which generalises past this field.** Three of this phase's findings --
`proto`, ICMPv6 type, and now these -- were cases of ad6 and FaVe disagreeing about how to
name or encode the same quantity, and in every one ad6 failed SILENTLY (a lookup miss
returning a plausible value). The check that catches them is not reading ad6's code: it is
asking what FaVe already hands NetPlumber, because that is the encoding the other backend is
measured under.

### 9.17 wl_i2 complete -- and the like-for-like cost is a WASH

| wl_i2, 72 pairs (exclude-self) | plain | faithful |
|---|---|---|
| semantic | 72/72 reachable **(wrong)** | **61/72** |
| structural | **61/72** | **61/72** |
| differ | 11 pairs | **0 pairs** |

All three cells that find 11 unreachable pairs find **the same 11** -- set equality against
the archived, three-way-corroborated set, checked not eyeballed. Structural plain and
structural faithful are pair-identical, confirming §9.16.1's inertness claim on real data as
well as by the byte-identical-config test.

**The faithful differential agrees on all 72 pairs.** That is the comparison the
differential is actually about: the only i2 configuration in which the two paths are asked
the same question.

#### 9.17.1 Cost: the structural translation is not a regression

| wl_i2 faithful | wall | peak RSS |
|---|---|---|
| semantic | 4,465 s | 9.7 GB |
| structural | 4,232 s | 10.3 GB |
| ratio | **0.95x** | **1.06x** |

Like for like, the structural path is slightly FASTER and uses 6% more memory. The 1.6x
wall / 4.3x memory gap seen in plain mode (§9.16) was never the translation being wasteful:
it was the two paths computing different things, and it vanishes the moment the semantic
path is asked to carry VLAN too. The verdict side and the cost side were two signals of one
cause, and this record predicted the collapse before the run.

Across the whole of Phase 3 the structural path costs 1.47x/1.43x wall on wl_stanford
(where per-port chaining grows the model 1.69x) and 0.95x on wl_i2 (where it grows it
1.00x). The cost tracks MODEL GROWTH, which tracks how heterogeneous a benchmark's
`in_ports` are -- not the translation strategy itself.

#### 9.17.2 Phase 3 scoreboard

| rung | pairs | differ | note |
|---|---|---|---|
| wl_ifi | 289 | 0 | both match `reachable.json` on all 17 roles |
| wl_stanford N=16 plain | 256 | 0 | 165 of 240 non-self, the NetPlumber oracle |
| wl_stanford N=16 faithful | 256 | 0 | 165 again; VLAN mutable-field path at scale |
| wl_i2 plain | 72 | **11** | **structural right, semantic wrong** (§9.16) |
| wl_i2 faithful | 72 | 0 | 61/72, the corroborated 11 |
| wl_up | -- | -- | BLOCKED: non-numeric field values (§9.14.1 item 3) |

**949 pairs compared across four benchmarks; one disagreement, and it favours the
structural path.** The translation reproduces every number the semantic path gets right,
plus one it gets wrong.


---


## Cross-cutting guardrails (reused from the APKeep/NDD work)
- **Soundness gate:** ad6 must never drop an NP-reachable pair (differential vs NP oracle).
- **Env pinned** in the shared `Dockerfile`; measurements only trusted on the controlled
  (bare-metal) environment.
- **Vendoring hygiene:** ad6 edits as separate commits with a changelog.
- **Metric stated explicitly** (build + query×count), reported both cold and warm.

### Generality debt: the pre-measurement checklist (owner framing 2026-09-11)

Feasibility work legitimately collapses the configuration space -- it adapts the tooling to
one workload in order to find out whether correct results are obtainable at all. That is
fine at this stage and must be UNWOUND before any headline measurement. The owner's
framing, recorded verbatim because it is the standing rule: *"In this stage, this is fine
but we need to generalize again when we want to work towards the real measurements."*

**The distinction that actually binds is not general-vs-workload-specific, it is whether a
choice affects the NUMBER being reported.** Two adaptations look alike and are not:

  * *Selection scaffolding* -- `--pairs`, `--dry-run`, `--witness`, the NetPlumber leaf
    parser, `bench/ad6_i2_measure.py` and `bench/ad6_faithful_measure.py` existing at all.
    These change only WHAT IS ASKED. Both drivers deliberately sit off the production path
    (they drive PySAT and ad6's `src.*` directly rather than through
    `Ad6Adapter`/`fave_bridge.py`), so they cannot contaminate a production result. i2-shaped
    is harmless here.
  * *Measurement-affecting configuration* -- the encoding, the solver, the session
    structure. This is where the debt accrues, and it is invisible unless stamped.

**NOT debt, despite looking like it:** the per-(port, VLAN) admission fix (§5.5) is a MODEL
CORRECTNESS fix, not a workload adaptation -- it applies to any workload with port-scoped
VLAN admission, it changed wl_stanford by the identical mechanism, and its `_ANY_PORT`
fallback ADDS generality by defining a case no shipped benchmark has.

**The debt itself, to be discharged or explicitly restated at measurement time:**

1. **`--lite-acyclic` is MANDATORY on i2, not chosen.** The general
   `_CreateAcyclicConstraints` does not complete at all (one SCC over 99.3% of nodes). It is
   clause-identical by test (`testAcyclicRankConstraintLiteMatchesGeneralEncoding`) so
   results stay sound, but "the general path is unusable at this scale" is a TOOL LIMITATION
   to report, not a flag preference to omit.
   - **The claim attached to the flag is STALE, found 2026-09-11.** Both
     `_CreateAcyclicConstraintsLite`'s docstring and the warning
     `bench/ad6_i2_measure.py` prints on every `--lite-acyclic` run still say it "fixes
     wl_i2's C2 memory blowup, but NOT C2 overall (solving still hangs regardless of
     backend)". That was superseded on 2026-09-05/06: Cadical195 completed all 72 pairs in
     3.56 h with an exact oracle match, Glucose4 in 15.3 h. The function is still marked
     EXPERIMENTAL and "never called by any default/production path" on the strength of a
     question that has since been answered. **This is the failure mode stamping does not
     cover** — `lite_acyclic: true` is stamped correctly while the prose next to it is
     wrong, and the warning goes to stderr on every run, so the next reader of a log is
     misled.
   - **DISCHARGED 2026-09-12 by restating, not by promoting.** All three stale sites are
     corrected: `_CreateAcyclicConstraintsLite`'s docstring, the stderr line
     `ad6_i2_measure.py` prints on every `--lite-acyclic` run, and that flag's `--help`.
     They now say what is actually established -- clause-identical by test, byte-identical
     CNF on real wl_stanford data, *cheaper* to build where both complete (10.4 s vs
     15.9 s at N=2), and solving COMPLETES (cadical195 72/72 in 3.56 h, exact oracle
     match) -- and they state the half that is still true: the GENERAL path cannot reach
     DIMACS conversion at wl_i2 scale, so the flag is MANDATORY there and must be reported
     as a tool limitation.
     **Why restate rather than promote, which the earlier framing called the least
     defensible option:** the reason it stays opt-in turns out to be ARCHITECTURAL, not
     evidentiary, and that was never written down. The function returns plain
     `(name, negated)` clause tuples; `_CreateAcyclicConstraints`' production callers
     (`InstantiateBase`, `SolveAcyclicEndToEnd`, `IncrementalSession`) all `extend` an
     lxml-Element formula list, and each of the two measurement drivers resolves the
     tuples to DIMACS integers itself. Promoting it is therefore a plumbing change across
     three production callers, not a switched default -- out of scope for a documentation
     correction, and it would alter what every default path builds. Recording that reason
     is what makes "opt-in *and* mandatory on the largest benchmark" defensible; the
     previous framing was indefensible because the stated reason was a question that had
     already been answered.
   - **Now measurable rather than only argued (2026-09-11):** `ad6_faithful_measure.py`
     takes `--lite-acyclic`, so the general-vs-lite difference can be measured on a
     benchmark where BOTH complete. At N=2 they produce byte-identical CNF (86,645 acyclic
     clauses, 161,249 total, 59,521 variables) and the same verdicts, with lite cheaper to
     build (10.4 s vs 15.9 s wall) -- so "mandatory on i2" remains a tool limitation to
     report, but it is no longer an unquantified one.
   - **Scale, for the report:** on wl_i2 the rank constraints are 14,201,913 of 14,883,129
     clauses (**95% of the whole CNF**) = 140,613 SCC-qualifying edges × 101 clauses at
     `Width`=17; on wl_stanford N=16 they are 443,963 of 711,100 (62%) = 6,253 × 71 at
     `Width`=12. The projected lxml construction cost at ~0.155 MB/edge is ~22 GB vs ~1 GB —
     which is why the general path is merely expensive on Stanford and impossible on i2. The
     bottleneck is the intermediate representation, never the clause count.
2. **Solver-per-problem-class would break uniformity.** If refutation wants Kissat404 and
   existence wants Cadical195, a 72-pair sweep mixes them and is no longer ONE
   configuration. What made the earlier solver comparison valid was the same encoding AND
   the same query order throughout (§5.5's WARM-SOLVER POSITIONAL EFFECT is why order
   counts).
   - **DRIVER PARITY, found 2026-09-11 — the live violation is BETWEEN benchmarks, not
     within a sweep.** `bench/ad6_i2_measure.py` takes `--solver`, `--lite-acyclic`,
     `--fresh-per-query` and stamps all three. `bench/ad6_faithful_measure.py` (wl_stanford)
     hardcodes `Minisat22` and has no acyclic option at all. **These are not stamps someone
     forgot to add: the choices are not configurable there**, so discharging items 1, 2 and 8
     on the Stanford side is CODE work, not documentation. Every wl_stanford number is
     Minisat22 + general acyclic while every wl_i2 number is Cadical195 + lite acyclic, and
     the two are quoted side by side.
   - **STAMPING HALF DONE 2026-09-11.** `ad6_faithful_measure.py` now records `solver`,
     `grounding`, `lite_acyclic`, `skip_acyclic`, `fresh_per_query`, `probe_untag` and the
     three `in_admission_*` fields, the last via `bench/ad6_stamp.py` so both drivers compute
     admission by the IDENTICAL rule rather than a second implementation of it. The
     constant/derived half sits in a pure `_config_stamp()` so it is unit-tested without a
     model build (`fave/test/test_ad6_faithful_measure.py`), including a cross-driver pin
     that the solver spelling stays inside the wl_i2 driver's own `_SOLVERS` vocabulary.
     Verified not to move the measurement: a re-run of N=2 reproduces the archived
     `ad6_faithful_N2_portscoped_sandbox.json` exactly (`clause_count` 161,249,
     `reachable_pairs` 2), which also retroactively CONFIRMS that archived run was
     port-scoped -- the fact that previously had to be inferred from its clause count.
   - **DISCHARGED 2026-09-11.** `ad6_faithful_measure.py` now takes `--solver` (the shared
     `bench/ad6_stamp.py` vocabulary, so a name means the same thing in both drivers'
     files), `--lite-acyclic` and `--fresh-per-query`. Defaults are unchanged, so a bare
     invocation is still the Minisat22 + general-acyclic + persistent-session run every
     archived result came from. **An apples-to-apples wl_stanford-vs-wl_i2 table is now
     producible**: point wl_stanford at `--lite-acyclic --solver cadical195` to match the
     encoding and backend wl_i2 is forced onto.
     - **Validated as a 7-way differential at N=2, not just by unit test**: general/lite ×
       minisat22/cadical195/glucose4/kissat404 × persistent/fresh × rank/flow all produce
       the IDENTICAL reachability matrix. General and lite also come out byte-identical in
       size on real wl_stanford data (86,645 acyclic clauses, 161,249 total, 59,521
       variables either way), corroborating
       `testAcyclicRankConstraintLiteMatchesGeneralEncoding` outside its synthetic fixture.
       Lite is also cheaper to BUILD at this scale (10.4 s vs 15.9 s wall at N=2), so the
       memory motivation is not its only one.
     - **A latent hazard was found and guarded while doing this.** `--fresh-per-query` is
       REQUIRED for kissat404, which the wl_i2 driver documented in help text but never
       enforced. Verified by experiment rather than from documentation: bootstrapped with
       `[[1, 2]]` and solved under `assumptions=[-1, -2]`, Minisat22/Glucose4/Cadical195
       return UNSAT while **Kissat404 returns SAT**, emitting only a `RuntimeWarning`. In a
       persistent session that silently drops each query's own source/destination literals,
       so every query is solved against the bare base encoding and the run reports
       EVERYTHING REACHABLE -- in a result file that looks entirely normal. Both drivers now
       refuse the combination, and the solver's actual behaviour is pinned by a test so the
       guard can be relaxed if PySAT ever fixes it.
   - **State the denominator, and never compare totals across different query counts.**
     §5.5's header reads "~13x slower per query than Stanford's ~16 minutes for its full
     256-pair matrix", but 13x is total-wall / total-wall across **72 queries vs 256**. Per
     query it is 172.5 s (i2) against 2.79 s (Stanford pre-fix) or 7.97 s (post-fix) —
     **~62x or ~22x, not 13x**. The stamping gate catches unstamped configuration; it does
     not catch incommensurable quantities, so this clause is a needed second half of the
     rule. The Stanford baseline in every such ratio is also STALE: the port-scoped
     admission fix moved N=16 from 764 s to 2,132 s.
3. **`--fresh-per-query` and the persistent session are DIFFERENT measurements**, not two
   routes to one number -- that is the 439x cold/warm effect. Pick one and hold it across
   the whole table.
4. **`probe_untag` off is a cross-engine PARITY choice, not a fidelity choice** (§5.5
   PROBE-UNTAG PARITY FINDING). It has to be restated wherever the number appears, since the
   faithful model would enforce it.
5. **`apkeep/adapter.py:_capture_in_admission` still carries the per-device projection**, so
   cross-backend faithful comparison is unlike-for-like in principle (measured: 7 crossings,
   0 reachability pairs on wl_stanford).
6. **A `--skip-acyclic` refutation, if used, is UNSAT ON A RELAXATION.** Sound in that one
   direction only (the rank encoding is purely additive, so removing it only ADDS models),
   and it must be reported as such -- never folded into a reachability table as if it were a
   normal run.
7. **Deliberate, recorded loss: there is no flag to reproduce the pre-fix per-device
   admission.** The archived pre-fix numbers are reproducible only from an ARCHIVED IR
   (`favemodel._in_vlans_for` still reads the flat shape), not from the current adapter. A
   defect is not a configuration -- but this is a real reproducibility narrowing, not a
   free choice.

8. **The GROUNDING CONSTRAINT is measurement-affecting configuration, and until 2026-09-11
   it was not even selectable outside the two measurement drivers.** `_CreateAcyclicConstraints`
   (rank) and `_CreateFlowPathConstraints` (flow) both close the SECRYPT'15 grounding gap and
   are held to identical ground truth by test, but they are NOT interchangeable and they do
   not cost the same: on wl_stanford N=16 faithful-VLAN, same model, same 256 queries, same
   165-pair answer, flow runs 7.0x wall / 9.3x query / 1.4x peak RSS under a MATCHED configuration (both cadical195) (§7.5).
   A table mixing the two is mixing encodings, exactly as item 2 forbids for solvers.
   **This item caught an error in this plan's own headline figure**: the previously quoted
   21.7x was flow-at-minisat22 against rank-at-minisat22-with-the-general-encoding, i.e. two
   variables moving at once. Recorded rather than quietly corrected, because it is the best
   evidence available that the gate is worth enforcing.
   - **The scope boundary must be restated wherever the flow number appears**, because it is
     easy to misread as a strictly better default: flow is REACHABILITY-SPECIFIC (it names
     its endpoints, forbids branching witnesses, and cannot express AF/AX, waypointing or
     the anomaly queries), whereas rank is property-agnostic. `grounding='rank'` stays the
     default for that reason, not from caution.
   - **It also entangles item 3:** flow is per-query by construction, so choosing it CHOOSES
     `--fresh-per-query`. The two are not independent knobs and cannot be varied separately.
   - **Stamped on both sides since 2026-09-11** (see item 2's driver-parity note):
     `ad6_faithful_measure.py` records `grounding` (derived from `--flow-path`, since the
     flow REPLACES the rank encoding rather than supplementing it) alongside
     `fresh_per_query`, so the architectural entanglement above is visible in the file
     rather than only in this checklist. The ARCHIVED pre-2026-09-11 artifacts still carry
     none of it; the wl_stanford N=16 pair has since been REPEATED under the stamping driver
     (§7.5), which is how the 21.7x was found to be an unmatched comparison. wl_i2's own
     flow/rank pair has not been repeated and remains unmatched.

**The mechanism that discharges all of this already exists: the result files stamp their own
configuration** -- `faithful_vlan`, `probe_untag`, `lite_acyclic`, `skip_acyclic`,
`fresh_per_query`, `solver`, `probe_vlan`, `oracle_match`, and (since 2026-09-10)
`in_admission_port_scoped`/`in_admission_ports`/`in_admission_pairs`. That stamping IS how a
later reader tells whether two numbers are comparable, which is exactly why the missing
admission stamp was worth fixing mid-run. **The gate: every collapse of the configuration
space must be a stamped field, never an undocumented habit.** If a measurement-affecting
choice has no stamp, add the stamp before quoting the number.

## Open decisions (resolve at the §1.4 gate)
- Integration level: (A) `AbstractVerificationEngine` backend vs (B) model translation.
- ~~wl_up's stateful instantiator soundness — GO/NO-GO~~ **RESOLVED 2026-08-21g: NO-GO on
  wl_up via ad6, both stateful and plain.** The second bug (7/8 hosts bypassing a
  source-scoped DROP under `related:0`) was root-caused and fixed (`ad6/fave_bridge.py`'s
  query seeding, commit `dfd543b0`) and generalizes at scale (1/1126 stateful violations
  post-fix, was ~45%). But the follow-on plain-query measurement it enabled found *plain*
  wl_up checks are equally vacuous (1712/1713 false violations) for the same root cause as
  the still-unfixed `related:1` bug — so there is no sound subset of wl_up left for ad6
  without porting FaVe's own state-shell interweaving into `IP6TablesParser`, judged not
  worth the investment. wl_up's correctness work moves to FaVe+NetPlumber (oracle) /
  FaVe+NDD-APKeep (arbiter); ad6 effort redirects to Stanford/i2 (§5.2). Full writeup:
  §5.1's resolution, §1.4(b).
- Stanford/i2 feasibility in ad6's encoding (IPv4 forwarding + VLAN) — go/no-go. **Scoping
  narrowed then re-widened 2026-08-21h: the 165-target plain result only needs LPM + a
  dead-port gate (VLAN admission cross-product is not load-bearing there,
  `[[apkeep-vlan-admission-tractability]]`); an LPM-tiebreak bug in the reusable
  `_routing_table`/`_translate_fwd_rule`/`_translate_routing_rule` building block was found
  test-first and fixed (`ad6/FAVE_CHANGES.md` §14). But per §5.3, the target to build
  TOWARDS is the faithful (VLAN admission + rewrite) variant, not the plain 165 special
  case — the tractability go/no-go on that full cross-product is still genuinely open.**
  **RESOLVED (provisional) 2026-08-27, §5.4 B3: PROVISIONAL GO.** The full faithful-VLAN
  16-router model builds and solves completely (~12.7 min wall on yolobox, sub-exponential
  clause growth 138k→711k from N=2→16), `reachable_pairs`=165 exactly matching the
  NetPlumber-proven plain oracle. "Provisional" because these wall-clock numbers are only
  measured on yolobox, not the bare-metal environment the plan's own guardrail requires for
  a final verdict — and because a real N=3/N=5 discrepancy against APKeep's own faithful
  numbers was found, narrowed (via a live NetPlumber arbiter check) to NOT be an ad6
  forwarding bug, but not fully root-caused (see §5.4 B3 for the full write-up and the
  working hypothesis). Full details: §5.4, `ad6/FAVE_CHANGES.md` §23.
- Incremental-SAT lever (§6): build before or after the baseline measurement.
- Primary SAT solver (clasp vs minisat vs pycosat) for the headline numbers.
- ~~Whether faithful-VLAN variants are in scope for ad6 at all.~~ **RESOLVED 2026-08-21h
  (Claas): yes, in scope, and the target — see §5.3.**

---

## TODO checklist
- [x] **§1.1** Write the two-factor (A/B) + per-solve cost model vs {NP, APKeep, NDD}.
- [x] **§1.2** Confirm ad6's reach vs `<->>` policy-compliance query counts from the code
      (`Instantiator`, FPL semantics); check one-source→all-dests feasibility. **Finding:
      `<->>` is FaVe's own policy language (thesis, not ad6-native); ad6 has no 3-check
      instantiator. CORRECTED 2026-08-20: `<->>` IS required — wl_up (3302/11902 checks)
      and wl_ifi (54/299) both need it in principle; only wl_stanford/wl_i2 stay k=1. ad6
      already has the STATE field end to end, so this is query-orchestration work, not new
      modelling — pulled into §4.2 as required for wl_up (and wl_ifi, §4.4). **wl_ifi was
      briefly dropped from scope on a wrong "not ad6-ingestible" premise, then REINSTATED
      2026-08-20 (§4.4) — the premise was wrong: the FaVe adapter never needs ad6's own
      parser to ingest anything.**
- [x] **§1.3** Predict the per-benchmark regime table (build/query-count/dominant factor).
- [x] **§1.4** GO/NO-GO gate: benchmark scope, Stanford/i2 feasibility, lever timing.
      **Claas confirmed GO 2026-08-20 ("Please go ahead on the ad6 plan"), then corrected
      the integration architecture the same day (§4.4).** Current scope: wl_ifi (build the
      FaVe→ad6 translator) → wl_up (add stateful) → Stanford/i2 (add LPM-at-scale + VLAN
      admission, the genuine remaining feasibility spike); §6 lever after the wl_up
      baseline; wl_tum's backend-correctness result carried along throughout.
- [ ] **§2** Fix the shared metric (build + query×count), fairness protocol, solver-variance
      protocol; confirm reuse of ad6's built-in instantiate/solve timing split.
- [x] **§3.1** Get `ad6` `make test` green; inventory + modernise deps (changelog).
      **DONE 2026-08-20 (commit `53e1f53d`): 2 real test-fixture bugs found+fixed (`test/`
      shadowed by stdlib, `_ConnectOutputs`-incompatible fixture firewall-key convention);
      46/46 green. Deps: minisat/clasp (apt), lxml/yappi/pycosat (pip). `ad6/FAVE_CHANGES.md`
      added.**
- [ ] **§3.2** Reproduce the ~36 min wl_up reachability baseline. **PARTIALLY DE-RISKED
      2026-08-20: the 138 shared per-host rulesets are byte-identical to today's wl_up right
      now (though `fave/bench/wl_up/rulesets/` is gitignored, so this isn't provable back
      through git history) — plan is to re-run fresh rather than forensically date the old
      run. Topology-wiring parity (ad6's generated `large.xml` vs FaVe's `topology.json`)
      still unchecked. Also: the historical ~36 min number did NOT exercise `<->>` (not yet
      built), so a faithful re-measurement will take longer once §4.2's stateful
      instantiator exists.**
- [x] **§3.3** Pin ad6 env (Python deps + SAT binaries) in the Dockerfile. **DONE 2026-08-20,
      same commit as §3.1.**
- [x] **§4.1** Decide integration level (A vs B) from a scoping pass. **DECIDED 2026-08-20:
      (B) model translation. `ad6/bench/tum/tum-ruleset` is byte-identical to FaVe's own
      default (ipv4) `fave/bench/wl_tum/rulesets/tum-ruleset` — zero ruleset translation
      needed for wl_tum. Initial "topology gap" note was premature (walked back after
      checking FaVe's own wl_tum model, which is equally interface-agnostic) — see §4.3.**
- [~] **§4.2** Wire ad6 to answer the source→probe matrix. **wl_ifi forwarding+ACL path
      DONE 2026-08-20** (`fave/ad6/adapter.py` + `ad6/src/parser/favemodel.py` +
      `ad6/fave_bridge.py`) — non-stateful (wl_ifi's `cchecks.json` stateful checks weren't
      exercised by this milestone's plain existential query; see below).
      **Stateful `related`-forcing mechanism BUILT 2026-08-21** (`_capture_acl`'s
      5th tuple slot, `favemodel._acl_rule`'s `GenUtils.state(...)`,
      `fave_bridge._state_literals`, `Ad6Adapter._cond_to_json`) and exercised end-to-end
      against wl_ifi's real `cchecks.json` (`fave/test/test_ad6_wl_ifi_stateful.py`): all
      245 plain checks pass, all 27 related:1 checks pass, all 27 related:0 checks
      currently fail against a state-blind real ACL rule (traced, understood, NOT yet
      confirmed against a live NetPlumber oracle — see §4.2's prose above and
      `ad6/FAVE_CHANGES.md` for the full trace). **Still open: resolve that open question,
      then wl_up's own stateful checks (11902/3302) at scale — the actual wl_up ACLs use
      `ctstate ESTABLISHED` for real (confirmed via `fave/bench/wl_up/rulesets/`, unlike
      wl_ifi's state-blind admin rule), so wl_up may behave differently from wl_ifi here.**
- [x] **§4.4** (new 2026-08-20) Investigate whether ad6 needs a "major refactor" to
      separate frontend/backend for FaVe integration, per Claas's correction. **Finding:
      largely already done** — `GenUtils` is an existing, generic Config-tree IR builder,
      fully decoupled from `IP6TablesParser`'s text parsing; a new FaVe-model→`GenUtils`
      translator is the actual scope, not ad6 surgery. **Experimentally verified** (not
      assumed): a rule's `action type="jump"` can target a specific declared egress
      interface directly, giving real per-rule forwarding/routing semantics with zero
      backend changes (synthetic 2-interface test, confirmed via forced-destination SAT
      queries that routing correctly discriminates). wl_ifi reinstated as the recommended
      first translator target (small, fast, exercises ACL+forwarding+VLAN).
- [~] **§4.3** Differential vs NetPlumber on **wl_tum + wl_ifi + wl_up** (soundness gate;
      wl_ifi reinstated 2026-08-20, §4.4). **wl_tum DONE 2026-08-20: exact match** (ad6 and
      NetPlumber both say source.tum→probe.tum is reachable), `ad6/test/differential/`.
      **wl_ifi DONE 2026-08-20: EXACT MATCH to `reachable.json` (54/54, 0 missing/0 extra)**
      — `fave/test/test_ad6_wl_ifi.py`, ~2.6s for the full 17-device/17-role model. This is
      the first real FaVe→ad6 translator result (not just ad6's own native-format
      shortcut like wl_tum). wl_up remaining, needing §4.2's stateful instantiator on top
      of this same translator.
      additionally needs the stateful instantiator.
- [x] **§5.1** Enable wl_up + wl_tum + wl_ifi end-to-end through the integrated path.
      **wl_up's translator BUILT and structurally verified 2026-08-21. Stateful
      differential: bug 2 root-caused and FIXED 2026-08-21g (`ad6/fave_bridge.py` query
      seeding, commit `dfd543b0`) — generalizes at scale (1/1126 stateful violations on a
      3342-check sample, was ~45% before the fix). But that same larger run found *plain*
      wl_up checks are equally vacuous (1712/1713 false violations) — same architectural
      root cause as the still-unfixed `related:1` bug (no state-shell interweaving in
      `IP6TablesParser`; confirmed FaVe+NetPlumber avoids this by construction via
      `fave/iptables/generator.py`'s own interweaving, `use_interweaving=True` default).
      **RESOLVED: NO-GO on wl_up via ad6 (Claas), both stateful and plain — not worth
      porting interweaving into ad6's translator. wl_up's correctness work moves to
      FaVe+NetPlumber/FaVe+NDD-APKeep; ad6 effort redirects to §5.2 Stanford/i2.** wl_tum
      and wl_ifi's exact-match results stand, unaffected (neither needed interweaving).**
- [~] **§5.2** Feasibility spike: IPv4 forwarding (+VLAN) encoding for Stanford/i2. **Now the
      primary remaining ad6 target (2026-08-21g), following wl_up's NO-GO** — orthogonal to
      everything above (0 stateful checks in either benchmark), oracle already in hand
      (NetPlumber==APKeep==165 on wl_stanford, `[[stanford-forwarding-overapprox]]`).
      **Stanford PROVISIONAL GO 2026-08-27 (§5.4 B0-B3 all done)**: faithful-VLAN full
      16-router model completes in ~12.7 min (yolobox), 165/165 matching the NetPlumber-
      proven plain oracle, sub-exponential clause growth. Provisional pending a bare-metal
      re-run (yolobox numbers are directional only) and a still-open, non-blocking N=3/N=5
      discrepancy vs APKeep's own faithful numbers (narrowed to not be an ad6 bug via a
      live NetPlumber arbiter, not fully root-caused). **i2: staged plan (C0-C4) written
      2026-08-27, §5.5. C0 DONE/GO (structural expectations exactly confirmed: 18 devices,
      77,460 fwd_rules, 0 ACLs). i2's giant single SCC (99.3% of nodes, 140,613/155,199
      edges qualifying — the SCC-scoping that made Stanford's B1 cheap barely helps i2's
      dense mesh topology) drives the general `_CreateAcyclicConstraints` into a genuine
      ~22GB memory blowup (measured ~0.14 MB/edge, OOM-confirmed at 82,363/140,613 edges
      = 14.44GB) before DIMACS/solving even start — root-caused, not a sandbox artifact,
      see `[[ad6-wl-i2-c2-nogo-oom]]`. Fixed by an experimental, opt-in
      `_CreateAcyclicConstraintsLite` (proven clause-equivalent by test, not just
      assumed). **C1 DONE/GO 2026-09-05**: full 72-pair differential, WITH the real
      acyclic-safety fix active (lite encoding), completed and exactly matches the
      oracle (72/72, 0 missing/extra) — stronger evidence than the earlier
      `--skip-acyclic` check, which only validated the translator with the safety
      machinery off. **C2 (tractability) still open, solver-choice-sensitive
      (2026-09-06)**: Glucose4 took ~15.3 hours for 72 pairs (~3 orders of magnitude
      slower per query than Stanford's ~16 min for 256 pairs); Cadical195, same
      encoding, same exact oracle match, took only ~3.56 hours (~13x slower than
      Stanford, not ~57x) — ~4.3x faster than Glucose4 despite looking worse on a
      single-query probe. Per-query cost stays highly variable either way
      (sub-second to 31-80 min depending on solver) — correct but not yet practical with
      either backend. **UPDATE 2026-09-08**: added full per-query timing (`query_log`,
      `bench/ad6_i2_measure.py`) — neither archived run had actually recorded more than
      its last query's time before this. A Cadical195 rerun with it (72/72,
      `oracle_match: true`, 14,896s this time vs 12,821s originally — real run-to-run
      variance) found 0.01 correlation with query position (rules out clause-bloat
      accumulation) and confirmed the hardest pair in the whole set is `losa`↔`newy32aoa`
      (LA/NYC) in BOTH directions, fastest queries all involving `hous`. **Same-day
      correction**: initially read this as "hardness tracks topological distance" — a
      follow-up graph-only check (`bench/ad6_i2_query_distance.py`, no solving) falsified
      that: hop-count (`corr=0.17`), OR-gate fan-in (`corr=-0.10`), and
      forward/backward-reachable-set size (`corr=-0.04`, expected given the giant SCC)
      all fail to predict it. The `losa`↔`newy32aoa` pattern is real (very unlikely to be
      coincidence) but its cause isn't visible in static graph structure — likely
      SAT-search-internal, left open rather than chased further. Also found Kissat404's
      disqualification is architecture-specific, not fundamental — a `--fresh-per-query`
      mode (fresh solver + unit clauses instead of assumptions) lets it run at all, since
      solver reload is cheap (~5-7s) against 100s-800s/query solve times; a single-query
      probe (279.7s) landed near Cadical's average. **Kissat404 full run DONE
      2026-09-09**: 36/72 under a 6h cap, **2.88x slower than Cadical195** on the same 36
      pairs (18,500s vs 6,427s solve-only; reload tax only 1.1% of wall, so the
      `--fresh-per-query` workaround is not the cause) -- extrapolates to ~11h/72. All
      four shortlisted backends now have an i2 verdict and **Cadical195 is the best
      available; the solver-side lever is exhausted**, further gains must come from the
      encoding. Also settles the per-pair question the `query_log` was added for:
      cross-solver correlation is **0.199**, with inversions up to 23x in both
      directions, so i2's "hard pairs" are solver-search artifacts, not instance
      properties (corroborating the 2026-09-08 graph-property falsification from the
      other side); `losa` is in both solvers' top pairs, its worst partner is not.
      Archived `eval/ad6_i2_kissat404_lite_freshpq_partial36of72.json`.
      **SCOPED AND PARTLY SUPERSEDED 2026-09-12 (§5.5 "UPDATE 2026-09-12", §7.5c):**
      every figure in this solver comparison is a RANK-encoding (`--lite-acyclic`)
      measurement on the PLAIN model -- never stated, because only one encoding then
      existed. (a) Its own closing call was right and the lever it named delivered:
      swapping ONLY the grounding, same model/solver/pairs, gives **9.0-10.8x wall and
      6.0x peak RSS**. (b) But "the solver-side lever is exhausted" and "Cadical195 is
      the best available" are RANK-scoped, not properties of the solvers: **Minisat22's
      disqualification was an artifact of the encoding** -- query 1 unresolved in 90+ min
      under rank, yet all 72 plain queries in 1,451 s (~20 s/query) under flow. Under
      flow cadical195 still leads on i2 but only 1.65x (plain) / 1.18x (faithful), and on
      wl_stanford minisat22 wins outright. (c) The per-pair conclusion SURVIVES, with a
      confound now measured: cross-solver correlation under flow is -0.076 (plain, all
      SAT) but 0.587 (faithful, pooled) -- which decomposes, because **UNSAT pairs cost
      6.6-7.4x the mean SAT pair** (a refutation must exhaust the space; a witness can be
      lucky), and splitting the classes returns it to noise (SAT-only 0.206, UNSAT-only
      -0.128). So satisfiability class IS an instance property with a ~7x effect, while
      per-pair hardness within a class stays a solver artifact -- and no hardness
      correlation may be computed over a mixed SAT/UNSAT set. The 0.199 above is
      unaffected (plain i2 is an all-reachable mesh, hence already all-SAT). C3/C4 (a
      cheaper general encoding, a further solver-level lever, or accepting this speed)
      still open; full write-up above. **WORKLOAD PARITY 2026-09-09**: every i2 number
      above is dst-IP-ONLY. The model's 77,451 `out.X` routes each carry a `rw=vlan:M`
      egress rewrite and its 390 `in.X` rules are pure VLAN admission -- all of which
      NetPlumber consumes (`netplumber/adapter.py:452-501`) and the faithful NDD run
      answers (`test_apkeep_ndd_fwd.py:166`, the instance BDD-APKeep cannot finish),
      while `fave/ad6/adapter.py` had no `_capture_out_rewrite` at all and dropped them in
      BOTH modes. So no ad6 i2 figure was like-for-like with another family's, the bias
      favoured ad6, and C3's "does plain mode match the oracle" criterion cannot detect it
      (an all-reachable oracle has zero power against over-approximation). C3 is NOT
      closable as a documentation decision.
      **RESOLVED FOR FAITHFUL MODE, AND THE PREDICTION ABOVE IS NOW MEASURED (2026-09-12).**
      C4 part 1 built `_capture_out_rewrite` (`fave/ad6/adapter.py:608`,
      `ad6/FAVE_CHANGES.md` §25) and the per-(port, VLAN) admission fix followed (§27), so
      `--faithful-vlan` now carries **77,451 out-stage rewrites and a 223-port / 596-pair
      ingress admission relation**, all stamped in the result file. The
      "drops them in BOTH modes" clause is simply no longer true of faithful mode.
      **What makes this a verification rather than a claim:** plain and faithful runs of the
      identical driver, solver and pair set report **72/72 reachable vs 61/72** — so plain
      over-approximates by EXACTLY the 11 pairs that NetPlumber and the independent
      structural oracle both confirm unreachable. The paragraph above predicted precisely
      this ("the bias favours ad6"; "an all-reachable oracle has zero power against
      over-approximation") and the size of the bias is now a number rather than an argument.
      Matching the all-reachable oracle, which plain mode does perfectly, is exactly the
      symptom it warned about.
      **STILL TRUE, and it is the live half:** PLAIN-mode i2 figures remain dst-IP-only and
      are NOT cross-family comparable — that is what "plain" means, not a defect — so every
      plain number, **§7.5b's 9.0-10.8x matched flow-vs-rank ratio included**, must be
      labelled INTRA-AD6. Cross-family i2 comparison uses the faithful runs only. The one
      remaining fidelity gap there is `probe_untag`, deliberately off as a cross-engine
      parity choice (generality-debt item 4) and stamped in every artifact.
      **For C3:** the workload-parity ground for holding it open is discharged — the
      faithful model exists, is measured, and its verdict is corroborated by two independent
      engines. **Found independently the same day by the
      parallel QA session, with counter-evidence this line lacked: FaVe+NetPlumber,
      cross-checked on i2 for the first time, reports 11 of the 72 pairs UNREACHABLE**,
      and a three-query faithful experiment is planned to decide C3 -- see "C3 REOPENED"
      and its WORKLOAD-PARITY companion in §5.5. Note a `faithful_vlan` switch alone will
      not suffice: `Ad6Adapter` needs `_capture_out_rewrite` written first, which is C4.
      Intra-ad6 solver comparisons are unaffected (identical encoding throughout).
- [ ] **§6** (optional) Prototype incremental-SAT source-amortisation; measure O(n²)→O(n).
- [ ] **§7** Write the "price of genericity" section + expressiveness table + bridge figure.
- [~] **§7.5** (new 2026-09-11) Write up the grounding constraint as a CORRECTION to the
      SECRYPT'15 formalism, not an implementation note: `trans(C)`'s support term is purely
      local, so a floating cycle discharges it self-referentially and any reachability number
      computed under the published formalism over-approximates by an unknown amount. Two
      repairs with different scope (property-agnostic rank vs reachability-specific s-t
      flow), both now selectable from the PRODUCTION path (`IncrementalSession(...,
      grounding=)`, `Ad6Adapter(..., grounding=)`, `fave_bridge.py --grounding`, commit
      `e1ba05b2`) rather than only from the measurement drivers — which is what stops the
      flow approach from being lost. Measured on wl_stanford N=16 faithful-VLAN, same model,
      same 256 queries, same 165-pair answer, MATCHED on cadical195 since 2026-09-11:
      **7.0x wall, 9.3x query, 1.4x peak RSS**, while giving up incremental reuse entirely.
      (The 21.7x/32.3x/2.9x first recorded here was an UNMATCHED comparison -- flow at its
      best solver against rank at its worst -- and is retired; 11.6x is the best-of-each
      figure. The correction is itself the strongest argument for generality-debt item 2.)
      **wl_i2 resolved differently (§7.5b, owner decision 2026-09-11):** no flow-vs-rank
      ratio will be measured there, because the rank encoding does not scale to the faithful
      model — general encoding OOMs outright (~22 GB projected, confirmed at 14.44 GB);
      rank+lite costs 641.6-713.8 s/query at 94.5% of box RAM on n=3, extrapolating to
      ~13.6 h for 72 pairs, against a faithful FLOW run that finished all 81 queries in
      ~70 min at 9.2 GB. Budget went instead to flow under BOTH solvers on both
      models (§7.5c, DONE 2026-09-11: all four complete in 2 h 49 min, verdicts
      solver-independent). That answered the inversion question NEGATIVELY — it does not
      survive at i2 scale — and turned up the sharper result that the flow encoding rescues
      Minisat22, which the rank encoding had disqualified there.
- [~] **§8 (deferred until wl_up + ideally Stanford/i2 work)** Architecture & design
      review: reconsider XML as ad6's primary data structure (config AND SAT-formula AST
      share one generic tree type); **§8.2 DONE 2026-08-21 — both known core bugs fixed
      test-first; §8.2b DONE 2026-08-21 — the CanonizeIP IPv6 "::" bug found building
      wl_up ALSO fixed test-first (same ask), worse than first logged (leading-`::`/
      `::`-alone also broken, plus a separate no-compression crash)**, ahead of the rest
      of §8 (Claas asked for the fixes directly rather than waiting); assess test coverage
      for the XMLUtils/SATUtils/Instantiator "generic infrastructure" layer (§8.3, still
      open — the three new tests are a start, not full coverage); revisit the
      frontend/backend seam with two frontends now in hand (§8.4, still open).
