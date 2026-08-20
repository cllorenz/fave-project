# ad6 → FaVe backend: a generic SAT/QBF model checker for comparison

**Status:** §1 theory DONE (2026-08-20); §1.4 go/no-go pending owner confirm before §3 code
revival. Owner: Claas Lorenz. Companions:
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
ad6-home-turf benchmark) and wl_ifi (the §4.3 smoke/differential target) both require the
stateful 3-check semantics.** `cchecks.json` entries already show the exact FaVe encoding:
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
originally modelled, and makes wl_ifi's small size more valuable as a smoke/differential
target precisely *because* it also exercises the stateful path at trivial scale.

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
| wl_ifi | 17+17 ⇒ ~34 | small (`ifi.csv`/`acls.txt`, dozens of rules) | 299 (54 stateful) | neither — cheap on both axes, but exercises the stateful path | best smoke/differential target (§4.3): fast, AND covers `<->>` at trivial scale |
| wl_up | 137 | large — `ad6/bench/up/up-gw-alt-ruleset` alone is 6606 lines, dozens of per-department rulesets on top | **11902 (3302 stateful)** | **Factor A dominates hardest of all four** — true query count (11902) is ~0.6× n², not the naive n²≈18.8k, because FaVe's compliance translation doesn't check every ordered pair at k=3 uniformly, but it's still ~86× wl_ifi's count with a widened per-pair cost (§1.2 correction: `<->>` pairs cost ad6 3 independent solves vs ~free extra reads for NP/APKeep/NDD) — worst case for ad6, and worse than §0 originally modelled | ad6's own bundled `bench/up/run_large.sh` builds `bench/up/large.xml` with `--anomalies end_to_end` over an all-pairs target list (internet + gateway + wifi-clients + 8 DMZ hosts + 21 subnets × 6 subhosts) that sums to **exactly n=137** — the *same* role count as FaVe's wl_up. This is almost certainly the "known ~36 min baseline" referenced in §3.2 — **but note `_measure_end_to_end` as coded only issues the plain (non-stateful) check, so that historical ~36 min number was NOT exercising `<->>` either; a faithful re-measurement will need the stateful instantiator built first and will very likely take substantially longer** |
| wl_tum | very small (single firewall `fw.tum`, essentially a 1-Kripke-endpoint model per `policies.json`) | large (`ad6/bench/tum/tum-ruleset` = 3795 lines; FaVe's `wl_tum` cites "3.8k stateful rules") | **Factor B alone** — n² term is negligible, this isolates raw per-solve/per-flood cost vs ruleset size | cleanest single-axis measurement: if ad6 loses here it's pure representation/solve cost, not query amortisation |
| wl_stanford | 16 (240 all-pairs checks) | IPv4 LPM FIB, not iptables — **not yet ad6-encodable** (§5.2 risk); `ap_num` ~21.6k on the faithful VLAN variant | small n keeps Factor A cheap even at k=3; Factor B depends entirely on the (unbuilt) IPv4/VLAN encoding | feasibility gate, not a cost question, until §5.2's encoding exists |
| wl_i2 | 9 (72 checks) | ~77k dst-IP FIB routes | tiny n²=81 but potentially huge `C_solve(R)` per query — the sharpest test of the "intuition-flipping" hypothesis | **the decisive case**: if a plain per-rule SAT encoding of dst-IP LPM forwarding stays roughly linear in clause count (unlike BDD's monolithic blowup — `[[stanford-forwarding-overapprox]]`/`[[apkeep-vlan-admission-tractability]]` found NDD/BDD blow up on field-*independent* VLAN admission, not on LPM alone), ad6 could plausibly be **competitive or fast** here purely because it only issues 81 solves total — same feasibility caveat as Stanford (§5.2) |

wl_tum's exact role count and wl_stanford/i2's true ad6-side rule count (FIB entries, not
firewall lines) are asserted from file sizes/prior memory, not re-derived from a running
ad6 encoding — first cheap validation step in §3 (`make test` + a dry run against
`bench/tum`) should confirm these before trusting the table for planning purposes.

### 1.4 GO/NO-GO gate — recommendation (owner decision required)

Recommend:
- **(a) Benchmark scope:** proceed with wl_ifi (smoke) → wl_tum (clean Factor-B isolation)
  → wl_up (headline Factor-A case) first, exactly as §5.1 already orders it. wl_stanford/i2
  gated separately behind §5.2's IPv4/VLAN encoding spike — do not block §3/§4 on it.
- **(b) `<->>` stateful query semantics — REQUIRED, moved out of "optional/deferred."**
  Corrected 2026-08-20: wl_up and wl_ifi both need it (§1.2). Pull the stateful
  instantiator (3 checks: plain, `state∈{ESTABLISHED,RELATED}` reverse-must-reach,
  `state=NEW` reverse-must-NOT-reach) into §4.2's required scope, driven off `cchecks.json`'s
  `(dst, must_reach, [conditions])` tuples. De-risked: ad6 already has the `STATE` field
  end-to-end (parser + bit-vector encoding), so this is query-orchestration work on top of
  existing machinery, not new modelling — but it is not skippable for a faithful wl_up/wl_ifi
  comparison, and it makes ad6's per-pair cost worse (3 independent solves, not 1) than the
  original plan assumed.
- **(c) Incremental-SAT lever (§6):** build **after** the (now-stateful) wl_up baseline, not
  before. §6 is only worth the effort if wl_up's O(n²)-ish query cost is shown to actually
  dominate wall-clock (more likely now that each `<->>` pair costs 3 solves) rather than
  build cost — confirm by measuring first.
- **(d) Stanford/i2 feasibility:** real risk, correctly scored as its own spike (§5.2), not
  a freebie — confirmed by reading the parser (`IP6TablesParser` only), not by assumption.
  Both remain genuinely k=1 (no `related:` conditions in their `cchecks.json`), so they do
  NOT need the stateful instantiator — only wl_up/wl_ifi/wl_tum(tbd) do.

**Do not start code revival (§3) until Claas confirms (a)–(d) above.**

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
- **4.2** Wire the reachability query so ad6 answers the **same source→probe matrix** as
  NP/APKeep/NDD, **including the stateful `<->>` 3-check form (REQUIRED for wl_up/wl_ifi,
  see §1.2/§1.4).** Build a stateful sibling of `InstantiateEndToEnd` that asserts a
  `state`/`ctstate` literal (ad6 already has the field: `XMLUtils.STATES`,
  `ConvertStateToVariables`, `IP6TablesParser`'s `--ctstate`) alongside the existing
  DisjSrc/DisjDst conjunction, driven directly off each benchmark's `cchecks.json`
  `(dst, must_reach, [conditions])` tuples so ad6's query semantics can't drift from FaVe's
  own compliance translation. wl_stanford/wl_i2 stay on the plain (non-stateful) path.
- **4.3 Differential correctness gate:** ad6 vs NetPlumber (the oracle) on wl_ifi + wl_up;
  **soundness is the hard gate** (ad6 must never drop an NP-reachable pair). Same discipline
  as the APKeep/NDD differentials.

---

## 5. Extend to all benchmarks

- **5.1** wl_up, wl_tum — ad6's home turf (IPv6 firewalls; rulesets already in
  `ad6/bench/{up,tum}`). Lowest risk; gets the large-n end of the curve.
- **5.2 Stanford, Internet2 — the small-n hypothesis test (§0). REAL FEASIBILITY RISK.**
  ad6 is IPv6-firewall/anomaly-oriented (its parser is `IP6TablesParser`; Stanford/i2 are
  **IPv4 forwarding** networks with **VLANs**). Encoding pure IPv4 LPM forwarding (+ VLAN
  match/rewrite) as an ad6 Kripke/SAT model is **substantial modelling work, not a config
  toggle** — it is the crux effort, and it must clear the §1.4 gate. Owner's position:
  "matter of effort, not principle" — accepted, but the plan treats it as a scoped task
  with its own feasibility check, not a freebie.
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
      and wl_ifi (54/299) both need it; only wl_stanford/wl_i2 stay k=1. ad6 already has
      the STATE field end to end, so this is query-orchestration work, not new modelling —
      pulled into §4.2 as required, not optional.**
- [x] **§1.3** Predict the per-benchmark regime table (build/query-count/dominant factor).
- [ ] **§1.4** GO/NO-GO gate: benchmark scope, Stanford/i2 feasibility, lever timing.
      **Recommendation written (updated 2026-08-20 to make the stateful instantiator
      required); awaiting Claas's explicit confirm before §3 code revival.**
- [ ] **§2** Fix the shared metric (build + query×count), fairness protocol, solver-variance
      protocol; confirm reuse of ad6's built-in instantiate/solve timing split.
- [ ] **§3.1** Get `ad6` `make test` green; inventory + modernise deps (changelog).
- [ ] **§3.2** Reproduce the ~36 min wl_up reachability baseline. **PARTIALLY DE-RISKED
      2026-08-20: the 138 shared per-host rulesets are byte-identical to today's wl_up right
      now (though `fave/bench/wl_up/rulesets/` is gitignored, so this isn't provable back
      through git history) — plan is to re-run fresh rather than forensically date the old
      run. Topology-wiring parity (ad6's generated `large.xml` vs FaVe's `topology.json`)
      still unchecked. Also: the historical ~36 min number did NOT exercise `<->>` (not yet
      built), so a faithful re-measurement will take longer once §4.2's stateful
      instantiator exists.**
- [ ] **§3.3** Pin ad6 env (Python deps + SAT binaries) in the Dockerfile.
- [ ] **§4.1** Decide integration level (A vs B) from a scoping pass.
- [ ] **§4.2** Wire ad6 to answer the source→probe matrix, **including the stateful `<->>`
      3-check instantiator (required for wl_up/wl_ifi, see §1.2 correction).**
- [ ] **§4.3** Differential vs NetPlumber on wl_ifi + wl_up (soundness gate).
- [ ] **§5.1** Enable wl_up + wl_tum end-to-end through the integrated path.
- [ ] **§5.2** Feasibility spike: IPv4 forwarding (+VLAN) encoding for Stanford/i2.
- [ ] **§6** (optional) Prototype incremental-SAT source-amortisation; measure O(n²)→O(n).
- [ ] **§7** Write the "price of genericity" section + expressiveness table + bridge figure.
