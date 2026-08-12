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
