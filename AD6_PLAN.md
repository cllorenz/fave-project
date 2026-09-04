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
devices/77,460 rules/0 ACLs); plain-mode reachability without the acyclic-safety fix
EXACTLY matches the 72/72-pair oracle (~6.4 min) — but that oracle has zero
expected-unreachable pairs so this can't validate soundness. C2 is now NO-GO at this
scale, root-caused (2026-08-28): `_CreateAcyclicConstraints` OOM-kills every time, not
from any sandbox timer but genuine memory blowup in the per-edge Tseitin/CNF-conversion
step (each of the 140,613 SCC-qualifying edges builds/discards its own lxml-backed
XML formula tree via `SATUtils.ConvertToCNF`). Instrumented with a per-edge progress
callback (`Instantiator._CreateAcyclicConstraints(..., ProgressCallback=...)`) and
measured directly: RSS grows linearly at ~0.14 MB/qualifying-edge; the process was
confirmed OOM-killed (exit 137, host `available` memory hit ~20MB immediately before
the kill, fully recovered after) at 82,363/140,613 edges (58.6%) with RSS=14.44GB.
Linear extrapolation to all 140,613 edges projects **~22GB just for this phase's
constraint list** (before DIMACS conversion or solving even start) — genuinely
intractable on commodity hardware at this scale with the current per-edge encoding,
not merely slow. The giant single SCC (99.3% of nodes) explains WHY so many edges
qualify for the expensive treatment; the memory blowup is what actually kills it.
Any fix needs either a fundamentally cheaper per-edge clause-construction path (bypass
the generic lxml/Tseitin machinery) or acceptance that i2 needs a different acyclic-safety
strategy than Stanford's SCC-scoped rank encoding.
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
  - **C4 — (conditional on C3 finding plain mode insufficient).** Scope a new, i2-shaped
    joint-constraint encoding: a single-hop `out.X` rewrite/`in.X` admission gate, reusing
    Stage A2's `fieldmatch` primitive (`ad6/src/xml/genutils.py:fieldmatch`,
    `ad6/src/core/instantiator.py:_HandleFieldMatches`) but WITHOUT §5.4's multi-hop SSA
    path-pinning machinery, since i2 has no mid-stage rewrite chain to track. Explicitly
    test, not assume, whether SAT's existential search sidesteps the (dst x VLAN)
    cross-product blowup stalling APKeep's BDD approach — SAT never needs to materialize an
    explicit joint predicate space the way BDD/NDD atom enumeration does, which could be a
    genuine comparative finding for §7's write-up rather than a risk to route around.

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

## Cross-cutting guardrails (reused from the APKeep/NDD work)
- **Soundness gate:** ad6 must never drop an NP-reachable pair (differential vs NP oracle).
- **Env pinned** in the shared `Dockerfile`; measurements only trusted on the controlled
  (bare-metal) environment.
- **Vendoring hygiene:** ad6 edits as separate commits with a changelog.
- **Metric stated explicitly** (build + query×count), reported both cold and warm.

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
      77,460 fwd_rules, 0 ACLs). Plain-mode `--skip-acyclic` orientation check matches the
      72/72 oracle exactly (validates the translator, not soundness — the oracle has zero
      expected-unreachable pairs). **C2 RESOLVED NO-GO 2026-08-28**, root-caused and
      quantified, not a sandbox artifact: i2's giant single SCC (99.3% of nodes,
      140,613/155,199 edges qualifying — the SCC-scoping that made Stanford's B1 cheap
      barely helps i2's dense mesh topology) drives `_CreateAcyclicConstraints` into a
      genuine ~22GB memory blowup (measured ~0.14 MB/edge, OOM-confirmed at
      82,363/140,613 edges = 14.44GB), before DIMACS/solving even start. See
      `[[ad6-wl-i2-c2-nogo-oom]]`. i2's problem shape differs from Stanford's (no mid
      stage, route-table-size-dominated, no working faithful-VLAN reference since APKeep's
      own i2 faithful build has never completed, and now this SCC/mesh-topology-driven
      memory blowup). C3/C4 need a cheaper per-edge encoding or a different
      acyclic-safety strategy before i2 can proceed with ad6.
- [ ] **§6** (optional) Prototype incremental-SAT source-amortisation; measure O(n²)→O(n).
- [ ] **§7** Write the "price of genericity" section + expressiveness table + bridge figure.
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
