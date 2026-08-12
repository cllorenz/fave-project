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

The user chose to verify which priority model is faithful *before* any fix. The answer is
now definitive and it **inverts the premise**: NetPlumber's canonical `10/240` is **not**
the true data plane.

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

**Open question for the user (supersedes the earlier Decision Point):** the natural next
step is fixing the FaVe Stanford model's rule priority to LPM so NetPlumber is a faithful
oracle, then measuring APKeep's real (VLAN/ACL) residual against it — do you want to
proceed that way, or investigate the model-vs-canonical-`.tf` ordering question first
(is this a FaVe decomposition bug, or does the upstream Hassel `.tf` itself carry non-LPM
order)?
