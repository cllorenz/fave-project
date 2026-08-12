# Phase 0c spec: the NetPlumber forwarding mechanism behind the wl_stanford over-approximation

**Status:** GATE RESULT — the mechanism is **identified and confirmed by evidence**,
and it **overturns the prior hypothesis** (out-stage in-port permutation / VLAN
coupling / split-horizon). The decisive question it raises — *which backend's forwarding
is faithful to the real data plane* — is a modelling decision surfaced for the user
before any core surgery (see "Decision point").

Reproduce everything below with:
`PYTHONPATH=. python bench/apkeep_convergence.py --routers bbra_rtr,rozb_rtr`
(the Phase-0b harness), which isolates the divergence to the single pair `bbra→rozb`.

---

## 1. The mechanism (one sentence)

NetPlumber resolves rule priority by **rule index / insertion order** (lower index =
higher priority) with header-space **priority-subtraction**; APKeep's adapter resolves
priority by **IP prefix length** (longest-prefix-match). On the Stanford mid-stage FIB
these two orders disagree, so APKeep forwards packets out specific transit routes that
NetPlumber has shadowed — over-approximating reachability.

## 2. Evidence chain (2-router reproducer: `{bbra_rtr, rozb_rtr}`)

The subset isolates the divergence to exactly one pair: NP reaches `rozb→bbra`
(edge→core) but **not** `bbra→rozb` (core→edge); APKeep reaches both.
`over_approx = {bbra→rozb}`.

1. **Topology is symmetric.** Both cross-links exist:
   `out.bbra_rtr.120001 → in.rozb_rtr.1200001` and `out.rozb_rtr.1220001 → in.bbra_rtr.100001`.
   So the block is *forwarding logic*, not missing links.

2. **The full static path bbra→rozb is open.** `mid.bbra` has 248 dst-IP routes with
   `fd=110001` (the egress toward rozb), each rewriting `vlan:2`; the internal links,
   the `out.bbra` permutation rule (`in_port 130001 → egress 120001`), and the external
   link to `in.rozb.1200001` all exist; and **`in.rozb` admits `vlan=2`** on that port
   (`match=[vlan=2] in_ports=[1200001] → 1200000`). Nothing on the path rejects the flow.

3. **NP nonetheless never sends bbra's flow toward rozb.** Tapping bbra's egress ports
   (an observation probe wired to a single egress) shows source.bbra's flow leaves
   `mid.bbra` **only via the default egress `110004`**, never via the rozb egress
   `110001`/`120001`. It reaches `probe.bbra` (self) via the default route and stops.

4. **The decisive isolation.** Restrict source.bbra to **only** `dst=172.28.0.0/14` —
   a prefix that has an *explicit specific route* `172.28.0.0/14 → fd 110001` (toward
   rozb). NP forwards it out the **`/0` default egress `110004`**, and the rozb egress
   `110001` stays empty. **NP forwards /14 traffic out the /0 default → NP is not doing
   longest-prefix-match.**

5. **Why:** NetPlumber core `net_plumber.cc:396` (`if (r->index < rule->index)`) makes
   the **lower-index** rule the influencer whose match is **subtracted** (`hs_diff`,
   `rule_node.cc` `process_src_flow`, "diff higher priority rules") from higher-index
   rules. In the Stanford mid-stage FaVe model, the match-all `/0` default (and low-index
   aggregate drops such as `172.16.0.0/12 → []`) sit at **low indices = high priority**,
   so they subtract the high-index specific routes to ∅. bbra therefore forwards its
   whole source flow out the default egress and never out the specific transit routes.

6. **APKeep does the opposite.** `apkeep/adapter.py:213,227` assigns priority = prefix
   length (LPM): the `/14` specific beats the `/0` default, so APKeep forwards toward
   rozb → `bbra→rozb` reachable → the over-approximation.

Removing the two mid-stage match-all defaults did *not* by itself unblock bbra→rozb (it
broke rozb→bbra, which relied on bbra's default to deliver locally) — consistent with a
*stack* of low-index shadowers (default + aggregate drops), not a single rule.

## 3. What this corrects

- The prior hypotheses — out-stage input-port permutation, split-horizon
  (`should_block_flow`), VLAN mid→out coupling, probe `vlan=0` filter — are **not** the
  mechanism for the `bbra→rozb` residual. (Confirmed incidentally: the probe does **not**
  filter `vlan=0`; `probe.bbra` observes the arriving flow at `vlan=2`.)
- VLAN coupling (prior P7b, which took APKeep 240→77) is a **separate** contributor for a
  *different* set of pairs; this spec explains the priority-model residual. The relative
  size of each is measurable with the Phase-0b harness once a faithful mode exists.

## 4. Where the priority comes from

The rule index is **not** invented by FaVe: `bench/np_preparation.py rule_to_route` sets
`rid = int(rule['id']) & 0xffffffff`, i.e. the **`position` of the rule in the original
Stanford `*.tf.json` transfer function**. `mid.bbra` rule at position 0 (lowest index =
highest NP priority) is the match-all default. So **NetPlumber faithfully computes the
canonical Hassel/HSA Stanford dataset** — the same dataset and the same header-space
semantics the original HSA/NetPlumber papers used to report reachability. NP's 10/240 is
therefore the canonical HSA answer, not a FaVe-side mis-conversion. APKeep is the one that
departs: its adapter *re-derives* priority as IP prefix length (LPM), overriding the
dataset's rule order.

## 5. Decision point (needs user input before Phase 1)

The mechanism is a **priority-model disagreement**, and the priority is fixed by the
canonical dataset, so the remedy is now concrete and comparatively **small**:

> **Option 2, made specific:** make the APKeep adapter honour the Stanford mid-stage's
> **rule-index / position priority** (as NP does) instead of overriding it with
> prefix-length LPM — a change to `apkeep/adapter.py`'s forwarding-rule priority, *not*
> the out-stage/VLAN core surgery the plan anticipated.

This is much cheaper than feared, but two things must be settled before coding:

- **(a) Semantic question for the thesis.** NP/HSA gives the default-route precedence its
  rule order encodes; a real router does longest-prefix-match. If the goal is "APKeep
  agrees with NP on the canonical dataset," option 2 is right and tractable. If the goal
  is "APKeep models the true LPM data plane," then NP is arguably the over-*restrictive*
  one and the comparison's oracle assumption needs revisiting. **This is a call for the
  user** — it decides what "faithful" means here.
- **(b) Soundness on the already-exact workloads.** APKeep is exact on wl_ifi/wl_i2
  *with* LPM priority. Switching the Stanford tables to index-priority must not regress
  them (they may or may not contain overlapping routes where the two orders differ). The
  Phase-0a exactness gate + Phase-0b harness are the tripwires; a per-table opt-in
  (index-priority only for HSA-decomposed Stanford tables) is the likely safe shape.

**Recommendation:** settle (a) with the user, then prototype option 2 as a flagged,
per-table priority mode in the adapter (Phase 1c micro-test first), gated on 0a staying
exact and the 0b over-approx count dropping.

---

## Phase 1 — GROUND TRUTH RESOLVED (2026-08-12): the true data plane is LPM; NP's 10 is an artifact

> **Read this section together with Phase 1d below (the final, corrected resolution).**
> "NP" / "NetPlumber's `10`" throughout Phases 1–1c means **the FaVe backend NP as it loads
> the wl_stanford dataset** — that is the `10`, and it is non-LPM. **Vanilla NetPlumber,
> loaded via its own `--load` front-insertion, does LPM (~165)** — see Phase 1d. So the `10`
> is a **FaVe-backend load-order bug** (list→map `--load` dropped the front-insertion
> reversal), not canonical HSA behaviour. The "faithful data plane is LPM" conclusion stands
> and is strengthened (APKeep *and* vanilla NP agree at LPM).

The user chose to verify which priority model is faithful *before* any fix. The answer is
now definitive and it **inverts the premise**: the FaVe backend's `10/240` is **not** the
true data plane (the true data plane is LPM; vanilla NP and APKeep both compute it).

**1. The real Stanford routers do longest-prefix-match.** The raw Hassel FIB dumps
(`bench/wl_stanford/stanford-hassel/<rtr>_rtr_route.txt`) are real Cisco routing tables.
`bbra_rtr` has overlapping routes:
```
172.16.0.0/12   attached   Null0          # drop
172.28.0.0/14   172.20.5.33 Vlan2         # forward (176 routes use this next hop, toward rozb)
0.0.0.0/0       172.20.4.2  Vlan2         # default
```
A real router forwards `172.28.x.x` via the **longest** match (`/14`, toward rozb) — not
the `/12` drop, not the `/0` default. The FaVe model even maps `172.28.0.0/14 → fd 110001`
(the egress toward rozb) correctly.

**2. NetPlumber, as the FaVe model feeds it, does NOT do LPM.** `bench/np_preparation.py`
assigns each rule's index = its **file position** in the `.tf` (`tf_to_json.py cnt++`), and
NP treats lower index as higher priority. The `/0` default lands at a lower index than the
`/14`, so NP forwards `172.28/14` out the **default** egress — the `bbra→rozb` block.
Proven with `bench/np_egress_trace.py` (source.bbra restricted to `dst=172.28.0.0/14`
leaves bbra via the `/0` default `110004`, never the `/14` `110001`).

**3. Fixing the priority to LPM makes NP agree with the real FIB.** Re-prioritising every
mid-stage FIB table by prefix length (longest = highest priority) and re-running NP
(`bench/stanford_priority_check.py`):

| NP priority model | reachable pairs (full 16-router) |
|---|---|
| file-order (as fed today — the "canonical" oracle) | **10** |
| prefix-length / LPM (faithful to the real FIBs) | **165** |

`bbra→rozb` flips from blocked to reachable under LPM, matching the real FIB and APKeep.

**Conclusion.**
- **The faithful data plane is LPM.** APKeep's forwarding (prefix-length priority) is
  **correct**; NetPlumber's `10` is a **priority artifact** of the FaVe model feeding
  rules in file order instead of prefix-length order.
- The `230`-pair "over-approximation" (APKeep forwarding-only `240` vs NP `10`)
  **decomposes**: ~`155` pairs are NP *under*-reporting (its non-LPM artifact — APKeep is
  right), and the residual (`165` LPM-NP vs `240` forwarding-only-APKeep) is APKeep's known
  VLAN/ACL-ignorance (the P7b gap), where NP is right.
- **The premise that "NetPlumber is the reference oracle for wl_stanford" is invalid.** The
  over-approximation was largely NP under-approximating.

**This changes the remedy entirely.** "Make APKeep faithful to NP" (option 2) would make
APKeep *less* correct on the ~155 LPM pairs. The real work is:
- **(i)** Fix the *model's* rule priority so NP does LPM (sort mid-stage FIB rules by prefix
  length in `np_preparation.py` / the decomposition, or make NP's Stanford tables
  prefix-length-priority). This is a **FaVe-model** fix, not an APKeep or NP-core fix, and
  it makes NP a trustworthy oracle again (`~165`).
- **(ii)** Then re-run the 0b harness: APKeep-forwarding-only (`240`) vs the corrected
  NP-LPM (`~165`); the remaining gap is the genuine VLAN/ACL modelling APKeep still needs
  (P7b), now measured against a *correct* oracle.

Numbers (`165`, the `155/75` split) are first-order estimates from a straightforward
prefix-length re-sort; ties and the drop/`Null0` handling need care before they are quoted
as final. The qualitative conclusion — LPM is faithful, NP's `10` is an artifact — is
airtight (real Cisco FIB + the reproducible flip).

### Reconciliation with the prior P7c conclusion (which said the opposite)

Earlier committed work (TODO.md P7c, 2026-07-10) concluded `bbra→rozb` is "genuinely
UNREACHABLE, NetPlumber sound AND complete on this pair; APKeep over-approximates," and
attributed the block to a **out-stage header-overlap failure**. That conclusion is
**wrong**, and the reason it was reached is instructive:

- P7c **trusted NetPlumber's forwarding as ground truth** and read its flow dumps to locate
  where bbra's flow "dies." But NP-as-fed uses **file-order** rule priority, so its flow
  dumps already encode the priority bug — reading them to find the mechanism is circular.
- P7c **assumed NP implements longest-prefix-match** — TODO.md line 388 reasons "LPM `/20`
  forward beats the `/16` discard." NP-as-fed does **not** do LPM (that is the whole
  finding), so this assumption was false and hid the real cause.
- The flow *does* die at the `mid.bbra→out.bbra` transition (P7c saw this correctly), but
  the cause is **mid-stage priority-subtraction** eating the specific transit routes, not an
  out-stage pipe/overlap failure. Re-prioritising only the mid-stage by prefix length flips
  `bbra→rozb` to reachable in the **full** 16-router model (`10→165` reachable pairs) — with
  the out-stage untouched — which an out-stage mechanism could not explain.
- Ground truth is the **real Cisco FIB** (`bbra_rtr_route.txt`), not NP: it forwards
  `172.28.0.0/14` (longer than the `/12` Null0 and `/0` default) out a shared segment
  (`out.bbra.120001 → {in.boza, in.rozb}`) that includes rozb. Under real LPM the pair is
  reachable.

So P7c's "NetPlumber is the reference oracle, sound and complete" is the exact premise this
Phase-1 investigation overturns.

### Phase 1b — where the non-LPM order comes from (the `.tf` provenance, 2026-08-12)

Traced end to end through the transformation scripts:

1. **Original data** — `stanford-hassel/<rtr>_rtr_route.txt` are real Cisco `sh ip cef`
   routing tables (longest-prefix-match FIBs).
2. **Canonical Hassel parser** — `stanford-hassel/cisco_router_parser.py` reads them
   (`read_route_file`) and compresses the FIB with a **binary trie**
   (`utils/helper.py compress_ip_list`). Its `node.output_compressed` is a **post-order**
   walk (children before parent), so it emits rules **longest-prefix-first**. Verified on
   the regenerated `stanford-tfs/bbra_rtr.tf`: the FIB `rw` rules run `/32 … /18 (line 962)
   … /14 (line 983) … default last` — longest-first.
3. **Priority convention is consistent and LPM-correct.** Both the Hassel `tf.py`
   (`_find_influences`, lines 277-288) and C++ NetPlumber (`net_plumber.cc:396`) treat
   **lower index = higher priority** (each rule is diffed against lower-index overlappers).
   Longest-first input + lower-index-wins = **correct longest-prefix-match**. The canonical
   toolchain, used as designed, does LPM.
4. **But the files NetPlumber actually consumes are inverted.** `bench/np_preparation.py`
   reads `stanford-json/*.tf.json` (renamed by commit `b2ad4fa4` from
   `<rtr>_rtr.{in,mid,out}.rules.json`, "aligned with vanilla NP"). `11.tf.json`
   (`mid.bbra`) holds the **same 861 FIB rules** as `bbra_rtr.tf` (full set intersection)
   but ordered **shortest-prefix-first** — `match-all default at position 0`, ascending to
   `/32` at the end. With lower-index-wins, the position-0 default shadows every specific
   route → the non-LPM `10`.

**So the non-LPM ordering is an inversion in the specific committed `stanford-json/*.tf.json`
dataset — NOT in the original Cisco data (LPM), the canonical parser (longest-first), or the
priority convention (lower-index-wins, which needs longest-first for LPM).** The `.tf.json`
is ordered the exact opposite of what the canonical toolchain produces and what NetPlumber
needs. The fix is to restore longest-first order for the mid-stage FIB (sort by prefix
length in `np_preparation.py`, or regenerate the `.tf.json` from the LPM-ordered `.tf`).

### Phase 1c — the reversal is located: `np_reproduction/transform.py` (2026-08-12)

The shortest-first order is produced by an explicit **`tab['rules'].reverse()`**. Traced
through `np_reproduction/run.sh`:

1. Upstream Hassel (`generate_stanford_backbone_tf.py` + `generate_rules_json_file.py`,
   Python 2, `~/hassel-public`) generates the **vanilla NP dataset** `stanford_json_vanilla/`.
2. `python3 transform.py $VANILLA_DIR $FAVENP_DIR` converts it to the FaVe dataset; its two
   operations are **`tab['rules'].reverse()`** and `toggle_mask_bits(rule['mask'])`.
3. `run.sh` then `cp`s that output into the repo:
   `cp $FAVE_DIR/*.json ../fave/bench/wl_stanford/stanford-json/`.

So **FaVe's `stanford-json/*.tf.json` is literally the vanilla dataset with its rule order
reversed** (and masks toggled). Since FaVe's is shortest-first, **the vanilla dataset is
longest-first** (LPM-order), consistent with the `cisco_router_parser` trie output.

### Phase 1d — A/B SETTLED (2026-08-12): vanilla NetPlumber does LPM (~165); the FaVe backend has the bug

> **This supersedes an earlier draft of this section that wrongly concluded "scenario A:
> vanilla = 10."** That draft ran vanilla NP on a *reconstruction* (`reverse(fave-dataset)`)
> that did **not** account for the canonical generator's own reversal, so it fed vanilla NP
> the wrong order. Correcting it flips the conclusion.

Got `~/hassel-public` (Peyman Kazemian's original HSA/NetPlumber,
`bitbucket.org/peymank/hassel-public`), built its `net_plumber` (`-std=gnu++11` for the old
dynamic-exception-spec code), **built python2.7 from source**, and ran the authentic
`generate_stanford_backbone_tf.py`. Findings:

1. **The authentic `.tf.json` FIB is longest-first** (`/32` host routes first, `/15` last).
2. **The canonical generator `generate_rules_json_file.py` does `insert(0)`** (front-inserts
   each rule into the per-stage list), i.e. it **reverses** the FIB to **shortest-first**
   when writing the vanilla `*.rules.json` dataset.
3. **Vanilla NP's `--load` front-inserts too** — `main_processes.cc` calls
   `add_rule(table, index=0, …)` and `_add_rule` inserts at the list front, so the in-memory
   list is the **reverse of the file order** → back to **longest-first** → **LPM**.

So the generator's `insert(0)` and the loader's front-insertion are a **matched pair** (two
reversals that cancel), and **vanilla NetPlumber computes LPM**. Confirmed empirically on the
authentic shortest-first dataset: source `bbra` reaches **15/16** routers (and router 12
reaches 15) — LPM — vs **0** on the reversed order.

| run | result |
|---|---|
| **vanilla NP, authentic (shortest-first) canonical dataset** | **LPM (~165)** — core routers reach ~all |
| vanilla NP, reversed (longest-first) order | non-LPM (10) |
| **FaVe backend (np_preparation → adapter → NP)** | **non-LPM (10)** |

**So vanilla NetPlumber's front-insertion is NOT a bug** — it is the designed counterpart of
the generator's `insert(0)`. Vanilla NP, APKeep, and the real Cisco FIB **all agree: LPM
(~165)**.

**The bug is in the FaVe backend, and it stems from the list→map change.** Vanilla's `--load`
ignores each rule's stored id and passes `index=0` (front-insert); FaVe's fork changed
`--load` to pass the rule's **stored id / file position** as the index
(`net_plumber/src/net_plumber/main_processes.cc:144,157`, commits `e91676ec` 2019 +
`c0593fc4` 2021 "Fix node id handling when dumping and loading nodes") — because a hash-map
keys by index and cannot front-insert with `index=0` (collisions). That **dropped the
load-side reversal**. FaVe's `stanford-json/*.tf.json` is the vanilla `mid.rules.json`
**renamed** (`b2ad4fa4`) — the shortest-first canonical data **without** the compensating
reverse — and `np_preparation.py:114` also uses the `.tf.json` position as the NP index. So
the FaVe backend loads shortest-first *as priority order* → the `/0` default is highest
priority → shadows the specifics → **non-LPM (10)**.

`transform.py`'s `rules.reverse()` (which the user added, `059d13bd`) is a **correct**
compensation for the *reproduction* harness: it pre-reverses the dataset so that FaVe's
id-indexed `--load` reproduces vanilla's front-inserted order, and both give LPM (165) and
agree. The production **backend** simply never got that reverse.

**Bottom line (corrected).** APKeep (LPM), vanilla NetPlumber (LPM ~165), and the real Cisco
FIB all agree and are faithful. **The FaVe backend (10) is the only non-LPM one** — a
priority-order bug introduced when the list→map refactor replaced vanilla's `--load`
front-insertion with id-based indexing, removing the reversal that the canonical
shortest-first Stanford dataset relies on.

### The fix (FaVe backend) — IMPLEMENTED & VALIDATED 2026-08-12

**Done in `bench/np_preparation.py`** (commit follows this doc update). Rather than a blind
`rules.reverse()` — which only yields LPM if every FIB table happens to be monotonically
prefix-sorted, and which would silently invert the *intended* priority of any shared
benchmark — the fix replicates the exact transform already proven in
`bench/stanford_priority_check.py::_reprioritise_lpm` (the one that lifted NP 10 → ~165):

- New `_reprioritise_mid_lpm(routes)` re-assigns each **`mid.*`** FIB table's rule index so
  that a **longer `ipv4_dst` prefix gets the lower (higher-priority) NP index**, stable within
  a prefix length; the match-all/default (`-1` prefix) sinks to the lowest priority. In/out
  ACL stages are left untouched. Called once at the end of `prepare_benchmark`.
- **Scope is self-limiting, no flag needed:** only the Stanford model has a `mid` stage
  (`table_types ['in','mid','out']`). wl_i2 is `['in','out']` and wl_ifi does not use
  `prepare_benchmark` at all, so for them the pass finds no `mid.*` device and is a
  *structural* no-op. (Chosen over a `prepare_benchmark` flag precisely because the mid-scoping
  already guarantees the no-op — verified below — so the cleaner unconditional form is safe.)

**Gate results (both green):**
- **0b convergence** (`bench/apkeep_convergence.py`, full 16-router): NetPlumber **10 → 165**,
  APKeep 240, **under-approx 0 (SOUND)**, over-approx **155 → 75**. The old 230-pair gap
  decomposes exactly as predicted: `165−10 = 155` was the NP non-LPM artifact (now gone),
  leaving `240−165 = 75` as the *genuine* APKeep VLAN/ACL over-reach — the real P7b residual,
  now measured against the **corrected LPM oracle (165)** instead of the artifact (10).
- **0a exactness** (`fave/test/exactness_gate.sh`): **PASS** — Java core, bundled-Stanford
  golden pin, wl_ifi, wl_i2 (77k routes, exact — confirms the mid-scoped pass is a true no-op
  there), wl_stanford P7a, and the backend differential all green. Regeneration diff confirmed
  only `mid.*` routes changed (3844/8792), only the index field, zero non-mid changes.

Alternative not taken: reinstating front-insertion in the FaVe `net_plumber` `--load`/adapter
path. The model-side reprioritisation is the smaller, testable change and keeps the C++ fork
aligned with its id-keyed hash-map storage.

Reproduce vanilla-NP LPM: clone `bitbucket.org/peymank/hassel-public`, build
`net_plumber/Ubuntu-NetPlumber-Release` with `-std=gnu++11`, build python2.7, run
`generate_stanford_backbone_tf.py`; run vanilla `net_plumber --hdr-len 16 --load <shortest-first dir>
--policy <dir>/policy.json` one source at a time (the FaVe `stanford-json` *is* that
shortest-first dir, with masks toggled to the vanilla convention).

### Note on the mask-semantics change (does bit-comparison mislead this?)

The FaVe net_plumber changed the semantics of masking bits at some point, and `transform.py`
carries a paired `toggle_mask_bits`. That does **not** affect the priority/LPM conclusion,
because NetPlumber's priority/overlap computation uses the rule **`match`** array *only* —
`net_plumber.cc add_rule` builds influences from `r->match ∩ rule->match` (never the mask) —
while the **mask** is used solely by the `rw` action to apply the VLAN rewrite
(`rule_node.cc array_rewrite(inv_match, mask, rewrite)`). So the mask change touches
VLAN-*rewrite* behaviour, which is orthogonal to the forwarding-*priority* (LPM) issue, and
to the separate `rules.reverse()`. The shortest-first ordering was re-confirmed from
`np_preparation`'s own `ipv4_dst=X/N` decode (current FaVe conventions, not raw bits), and
all load-bearing results are behavioural (the current net_plumber's own computation) or
textual (the real Cisco route tables) — none rests on a raw-bit interpretation. Caveat kept
for later: if the mask change ever affected VLAN-rewrite *correctness*, that bears on the
separate VLAN/ACL residual (P7b), not on the priority/LPM finding.

**Status update (2026-08-12):** the FaVe-backend LPM fix is now **implemented and validated**
(see "The fix (FaVe backend) — IMPLEMENTED" above): NetPlumber is a faithful LPM oracle (165),
and APKeep's residual over-reach against it is a concrete **75 pairs** — the genuine VLAN/ACL
gap (P7b) to characterise next. The remaining open item is the **thesis framing**: prior P7c
("bbra→rozb genuinely UNREACHABLE; NP sound *and* complete") is overturned — the FaVe-backend
NP was under-reporting via a priority artifact, and APKeep's forwarding was the faithful one.
Next measurable step (P7b): enumerate and attribute the 75 APKeep-only pairs to specific
VLAN/ACL semantics APKeep's forwarding-only model ignores.

## Phase 2 — attribution of the 75-pair APKeep residual (2026-08-12)

**Result: the 75 pairs are NOT VLAN-rewrite and NOT 5-tuple ACL filtering. They are one
mechanism — _in-port-qualified ingress admission_ — and they reduce to 5 source routers
attached to unconfigured interfaces.**

**Decomposition.** The 75 = **exactly 5 source routers × 15 destinations**. Per-source counts
(`bench/apkeep_convergence.py --emit`): `bbrb_rtr, boza_rtr, goza_rtr, roza_rtr, yozb_rtr`
each reach **0** in NP but **15** (everything) in APKeep; the other 11 routers reach 15 in
both. APKeep reaches the full **240**-pair mesh; NP reaches **165 = 11 × 15**. So the residual
is entirely **source-side**: NP blocks 5 sources completely, at ingress.

**It is not the egress VLAN filter.** Dropping the probe's `vlan=0` test field and regenerating
left NP unchanged at 165 (the 5 sources still 0) — the flows never arrive at any probe, so the
block is upstream of egress, not the `vlan=0` filter.

**Mechanism — in-port-qualified admission (verified, 16/16 discriminator).** A source is
blocked in NP **iff its source in-port has no matching rule in that router's in-stage table.**
The in-stage (`X0.tf.json`) rules are `(in_port, vlan) → fwd to mid`: the router's L2 input
processing (which VLANs each physical port admits). The source generators attach at:
`roza→1100032, boza→300032, goza→700032, bbrb→200001, yozb→1600001` — and **none of those
ports appears in its in-stage `in_ports`**, so NetPlumber (which propagates the `in_port`
field and honours in-port-qualified rules) drops the flow at ingress, for every destination.
The 11 live sources' ports are all covered. This is exactly P7c "gap 2 — transfer-function
fidelity": the in/mid TF rules are in-port-qualified, but APKeep's `_translate_fwd_rule`
(`fave/apkeep/adapter.py:204`) keys **only on the dst field and ignores `rule.in_ports`**, so
the in-stage collapses to a `/0` forward-all that admits traffic on *any* port. APKeep has no
way to express "this ingress port admits nothing," so it forwards where NP drops.

**Root config cause — unconfigured ports (VLAN membership).** Via `stanford-hassel/port_map.txt`,
roza's source port 32 = interface **gi4/8**, whose entire config is `no ip address / no cdp
enable` — no `switchport`, no VLAN membership, no IP. It is a member of no VLAN, so the
authoritative Stanford parser (`cisco_router_parser.py`) emits no in-stage admission rule for
it and a host there is genuinely dead. So the underlying reason is L2 (VLAN membership), but
the mechanism NP uses to drop is the `in_port` qualification — *input-port admission*, not
VLAN rewrite and not an IP/5-tuple ACL.

**The oracle twist (which engine is "right" depends on the question).** `reachable.json` is the
**intended policy** (derived from `roles.txt`/`reach.txt`), a full **240**-mesh — not a
data-plane computation. Measured against it: **APKeep = 240 = exactly the oracle**; **NP = 165
under-reports**, flagging the 5 dead-port sources as 75 policy *violations* (`oracle \ NP` = 75,
`NP \ oracle` = 0). Measured against the **real data plane**: those 5 sources sit on genuinely
unconfigured interfaces, so **NP's drop is faithful and APKeep over-approximates**. Both
statements are true; they answer different questions. Net: the 75-pair "APKeep over-reach" is
half an APKeep fidelity gap (no in-port-qualified admission) and half a **benchmark
source-placement artifact** — the committed `policy.json` attaches these 5 sources to dead
interfaces, which the full-mesh policy oracle simultaneously assumes are live.

**Bottom line for the thesis / next work.**
- The genuine APKeep limitation exposed here is **in-port-qualified forwarding/admission**
  (P7c gap 2), *not* VLAN rewrite (P7b's earlier `240→77` VLAN work) and *not* IP ACLs. VLAN
  rewrite and 5-tuple ACLs contribute **0** of these 75 pairs.
- Diagnostic confirmed the residual is *entirely* this one mechanism: re-placing the 5 sources
  onto covered in-ports makes NP reach the full **240** (each formerly-blocked source → 15),
  so **no VLAN/ACL residual hides beneath** — on live ports the two backends agree completely.
- Reproduce: `bench/apkeep_convergence.py` (counts + over-set); the discriminator and the
  gi4/8 config are a read over `stanford-json/*0.tf.json` in_ports vs `sources.json` links and
  `stanford-hassel/port_map.txt` + `roza_rtr_config.txt`.

### Phase 2 fix — APKeep made in-port-faithful (IMPLEMENTED & VALIDATED 2026-08-12)

Per the principle "if APKeep deviates from reality, fix APKeep — don't bend the benchmark,"
the fix went into the **APKeep adapter**, not the source placement (roza gi4/8 genuinely
admits nothing, so NP's drop is faithful and APKeep forwarding it is the deviation).

- **`fave/apkeep/adapter.py`:** `_capture_in_admit` records each in-stage device's admitted
  physical-port set (from the in-port-qualified in-stage rules; `None` if an in-port-agnostic
  rule admits all). `_gate_dead_ingress` (called in `_build` before `init_in_memory`) drops
  topology edges delivering to an unadmitted ingress port. No-op where the in-stage admits all
  ports or the target is admitted; inter-router links land on admitted trunk ports and survive;
  wl_i2 (no dead-port sources) is unaffected.
- **Result:** APKeep **240 → 165**, converging **exactly** with NetPlumber
  (`apkeep_convergence.py`: over_approx=0, under_approx=0, SOUND). Both backends now compute the
  same faithful data plane.
- **`test_apkeep_stanford` recalibrated (user decision, Option A):** it asserted
  APKeep == `reachable.json` (the all-to-all *policy*, 240) — which the faithful data plane does
  not satisfy. It now asserts **APKeep == FaVe+NetPlumber** (both 165), NP computed in a separate
  process (a resident JVM in-process makes NP misreport). `reachable.json` stays the intended
  must-reach policy; the 75 dead-port pairs are genuine policy *violations* a faithful verifier
  reports. Exactness gate green (10/10, wl_i2 77k exact unchanged).
- **Scope note:** the fix models the *dead-port* admission case (a port admitting nothing),
  which is 100% of this residual. Full per-(port,VLAN) admission is the separate P7b concern
  (correct-but-intractable at scale); it is not needed here.
- **Thesis takeaway:** with both the LPM fix and this in-port fix, **NetPlumber and APKeep agree
  exactly on wl_stanford (165 = the faithful data plane)**. The all-to-all 240 was never the
  data plane — it is the policy, violated by 5 sources on unconfigured interfaces. Prior P7c/P7b
  framings that treated 240 or NP's non-LPM 10 as ground truth are both superseded.
