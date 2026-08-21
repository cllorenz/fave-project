# ad6 → FaVe backend: a generic SAT/QBF model checker for comparison

**Status:** §1 theory DONE + §1.4 GO confirmed by owner (2026-08-20); §3.1/§3.3 DONE
(`make test` green, deps pinned); §4.1 decided + §4.4 major integration-architecture
correction from owner review, incorporated same day (wl_ifi reinstated, ad6 needs a new
FaVe-model translator, not a backend refactor). **The translator is now built and proven:
wl_tum (ad6-native format) and wl_ifi (via the new translator, forwarding+ACL) both
EXACTLY MATCH their NetPlumber/reachable.json oracles.** wl_up remains, needing the
stateful `<->>` instantiator (§4.2) added on top of the same translator. Owner: Claas
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
  tuples. De-risked: ad6 already has the `STATE` field end-to-end (parser + bit-vector
  encoding), so this is query-orchestration work on top of existing machinery, not new
  modelling — but it is not skippable for a faithful wl_up (or wl_ifi) comparison, and it
  makes ad6's per-pair cost worse (3 independent solves, not 1) than the original plan
  assumed. wl_tum's oracle is a single reachability check (not an FPL role-mesh — confirmed
  against `policies.json`), so it doesn't need the stateful instantiator and can stay the
  simplest validation of the plain path.
- **(c) Incremental-SAT lever (§6):** build **after** the (now-stateful) wl_up baseline, not
  before. §6 is only worth the effort if wl_up's O(n²)-ish query cost is shown to actually
  dominate wall-clock (more likely now that each `<->>` pair costs 3 solves) rather than
  build cost — confirm by measuring first.
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
     colon), which later crashes `int('', 16)` in `ConvertCIDRToVariables`. wl_up's own
     real rulesets never hit this (they always write an explicit trailing zero,
     `"2001:db8:abc::0/48"`, confirmed in `pgf.uni-potsdam.de-ruleset` — a hand-authored
     convention that happens to dodge the bug); FaVe's own `routes.json`-derived dst
     strings don't follow it. **Not fixed in ad6 core** — logged as a §8 item alongside
     the other latent `CanonizeIP`/`ConvertCIDRToVariables` findings (this one, and the
     multi-value `ctstate A,B` AND-instead-of-OR bug from §4.2); worked around in
     `favemodel.py` with `_ipv6_safe`, which inserts the same explicit zero the real
     rulesets already write by convention. Equivalent, not a behaviour change.

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
- **5.2 Stanford, Internet2 — the small-n hypothesis test (§0). The genuinely remaining
  feasibility risk, corrected 2026-08-20 (§4.4): NOT a parsing-format question (FaVe's
  adapter never depends on ad6's own parser, so "IPv4 vs IPv6-native" is moot) — a
  SAT-encoding-*scale* question.** Does LPM-at-scale forwarding + the VLAN-admission
  cross-product stay tractable in ad6's Kripke/CNF representation, the way NDD's atom
  partitioning tames it in BDD's (`[[apkeep-vlan-admission-tractability]]`), or does it blow
  up the way faithful BDD-APKeep did on the same workloads? Genuinely unknown, still its
  own spike, still gated at §1.4/§4.4 — but now correctly scoped as a scale/tractability
  question to measure, not a "can we even express this" question (§4.4's forwarding-jump
  test suggests expressibility isn't the blocker).
- **5.3** Faithful-VLAN Stanford/i2 variants: likely **out of scope** for ad6 (it is not a
  forwarding/VLAN data-plane tool); revisit only if 5.2 succeeds and there is appetite.

---

## 6. Algorithmic lever — amortise the O(n²) toward O(n) (optional, high value)

Directly attacks Factor A: for a fixed source, solve the n destination queries under solver
**assumptions**, reusing learned clauses across them — a warm single solver session
approximating a flood — collapsing O(n²) toward ~O(n). More aggressive: a **QBF encoding
quantifying over destinations**. Measures "how close a generic solver gets to a
domain-specific flood by amortising." If it works, the comparison tightens dramatically; if
not, *why not* is itself a finding. Decide up-front vs post-baseline at the §1.4 gate.

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

---

## Cross-cutting guardrails (reused from the APKeep/NDD work)
- **Soundness gate:** ad6 must never drop an NP-reachable pair (differential vs NP oracle).
- **Env pinned** in the shared `Dockerfile`; measurements only trusted on the controlled
  (bare-metal) environment.
- **Vendoring hygiene:** ad6 edits as separate commits with a changelog.
- **Metric stated explicitly** (build + query×count), reported both cold and warm.

## Open decisions (resolve at the §1.4 gate)
- Integration level: (A) `AbstractVerificationEngine` backend vs (B) model translation.
- Stanford/i2 feasibility in ad6's encoding (IPv4 forwarding + VLAN) — go/no-go.
- Incremental-SAT lever (§6): build before or after the baseline measurement.
- Primary SAT solver (clasp vs minisat vs pycosat) for the headline numbers.
- Whether faithful-VLAN variants are in scope for ad6 at all.

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
- [ ] **§5.1** Enable wl_up + wl_tum + wl_ifi end-to-end through the integrated path.
- [ ] **§5.2** Feasibility spike: IPv4 forwarding (+VLAN) encoding for Stanford/i2.
- [ ] **§6** (optional) Prototype incremental-SAT source-amortisation; measure O(n²)→O(n).
- [ ] **§7** Write the "price of genericity" section + expressiveness table + bridge figure.
- [~] **§8 (deferred until wl_up + ideally Stanford/i2 work)** Architecture & design
      review: reconsider XML as ad6's primary data structure (config AND SAT-formula AST
      share one generic tree type); **§8.2 DONE 2026-08-21 — both known core bugs fixed
      test-first**, ahead of the rest of §8 (Claas asked for the fix directly rather than
      waiting); assess test coverage for the XMLUtils/SATUtils/Instantiator "generic
      infrastructure" layer (§8.3, still open — the two new tests are a start, not full
      coverage); revisit the frontend/backend seam with two frontends now in hand (§8.4,
      still open).
