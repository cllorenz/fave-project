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

### Phase 1d — A/B SETTLED by running vanilla NetPlumber: scenario A (2026-08-12)

Got `~/hassel-public` (Peyman Kazemian's original HSA/NetPlumber,
`bitbucket.org/peymank/hassel-public`), built its `net_plumber` (only fix needed: the old
code uses dynamic exception specs, so compile `-std=gnu++11`), and ran it. Since the Python-2
upstream generators aren't runnable here, the **canonical vanilla dataset was reconstructed
by inverting `transform.py`** (reverse the rules back to longest-first, toggle the masks back)
— and it faithfully reproduces the documented canonical result, so the reconstruction is
sound. Reachability measured per-source (one `add_source` + all 16 probes, counting probes
that reach "Met Probe Condition", self excluded):

| run | reachable pairs |
|---|---|
| **vanilla NP, canonical (longest-first) vanilla dataset** | **10** — the same edge→core set (→ bbra/bbrb) as FaVe |
| vanilla NP, reversed (shortest-first) order | LPM (e.g. source bbra reaches **15** routers) |
| FaVe net_plumber (production adapter path) | 10 |

**So vanilla NetPlumber gives `10`, identical to FaVe — scenario A.** The non-LPM result is
**canonical to the HSA/NetPlumber Stanford analysis**, *not* a FaVe-introduced artifact, and
`transform.py`'s `rules.reverse()` is a **correct** adaptation (both engines end at `10`), not
a bug.

**Mechanism (now fully pinned).** Vanilla NP is *also* lower-position-wins, but its `--load`
path calls `add_rule(table, index=0, …)` for every rule, and `_add_rule` **front-inserts**
when `index < size` — so the in-memory rule list is the **reverse of the file order**. The
canonical vanilla file is longest-first, so front-insertion puts the `/0` default at the
list front (highest priority) → the default shadows the specific routes → non-LPM. FaVe
reaches the identical `10` by a different route (`transform.py` reverses the file to
shortest-first, and FaVe's adapter/`--load` keys priority by index directly). The order is
provably the sole driver: same rules + same engine, only the file order differs, gives
`10` vs LPM (confirmed both directions above).

**Bottom line.** Both NetPlumbers (vanilla and FaVe) compute the non-LPM `10` on the
canonical Stanford dataset; the real Cisco FIB does longest-prefix-match (`~165`); APKeep's
LPM forwarding is faithful to the real router, while **neither NetPlumber is** for these
overlapping FIB routes. Whether the canonical HSA pipeline's non-LPM outcome is an intended
model choice or a latent load-order issue in NetPlumber is a separate question — but it is
canonical (reproduced by the original tool), not something the FaVe port introduced.

Reproduce: clone `bitbucket.org/peymank/hassel-public`, build `net_plumber/Ubuntu-NetPlumber-Release`
with `-std=gnu++11`, reconstruct the vanilla dataset by inverting `np_reproduction/transform.py`
on `fave/bench/wl_stanford/stanford-json/*.tf.json`, and run
`net_plumber --hdr-len 16 --load <dir> --policy <dir>/policy.json` one source at a time.

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

**Open question for the user (supersedes the earlier Decision Point):** the natural next
step is fixing the FaVe Stanford model's rule priority to LPM (sort the mid-stage FIB
longest-first) so NetPlumber is a faithful oracle, then measuring APKeep's real (VLAN/ACL)
residual against it. Per the 2026-08-12 decision this is **paused** pending your call on
how it reframes the thesis.
