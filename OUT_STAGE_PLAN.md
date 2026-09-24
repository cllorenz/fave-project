# Closing P7c gap 2: the wl_stanford out stage as a modelled device

**Status: PLAN (2026-09-24).** Covers TODO items 24 and 25, which are two views of
the same gap. Companion to [`TABLE_SEMANTICS_PLAN.md`](TABLE_SEMANTICS_PLAN.md)
(item 23, built) and [`APKEEP_BACKEND.md`](APKEEP_BACKEND.md) §P7.

---

## 1. What this is about, in one paragraph

The Stanford HSA model splits each router into `in.` / `mid.` / `out.` switches.
The out stage is an **input-port → output-port permutation under an ACL**, and
commit `2a36d4af` (2026-07-01) collapsed it into the topology because APKeep's
only forwarding primitive was a destination-prefix trie, which is in-port-blind.
The collapse keeps the permutation and **discards every match condition on it**.
In the production (faithful) configuration the out stage contributes **zero rules
to the engine**. The question item 24 asks is whether the faithful path can now
keep that stage as a real device.

This plan answers: **yes, and it is far smaller than the stage's size suggests.**

---

## 2. The measurements that size the work

All from `bench/wl_stanford/stanford-json/routes.json` +
`device_topology.json`, 2026-09-24.

### 2.1 Only 68 of 681 arrival ports carry a condition

```
out-stage devices                                    16
out-stage rules                                   2,683
arrival ports (mid -> out edges land here)          681
  UNCONDITIONAL (pure permutation, no match, no drop)  613
  CONDITIONAL  (>=1 match or >=1 drop)                  68   <- 2,118 rules
```

This is the number that makes the work tractable. **613 of the 681 ports are
exactly what the collapse models them as** — an unconditional permutation — and
the collapse is *correct* for them, not approximate. The gap lives on 68 ports.

### 2.2 All 45 VLAN resets are on those same 68 ports

```
non-forward actions in the whole out stage:   rw=vlan:0   x45
  on CONDITIONAL ports    45
  on UNCONDITIONAL ports   0
```

`_build_stanford_faithful` folds that reset into the mid-stage NAT (the
`effective` VLAN). So the fold applies **only** where the condition is also being
discarded. The two are not independent, and §4.2 is why that matters.

### 2.3 Every conditional port ends in a forwarding catch-all, and the
###     permutation is NOT over-permissive in the port dimension

```
conditional ports whose catch-all FORWARDS            68
conditional ports whose catch-all DROPS                0
conditional ports where the UNIONed permutation
  reaches MORE egress ports than the catch-all         0
```

**This is the most important measurement in the plan.** `_capture_out_perm`
unions every rule's egress ports per in-port, so the obvious worry is that the
collapse invents paths. It does not: on all 68 ports the union equals the
catch-all's egress set. The collapse is over-permissive **purely in the header
dimension** — narrower forwards that the catch-all also permits, plus 16 denies.

Consequence, and it is a prediction this plan must be held to: **closing the gap
will not move the reachability matrix at all.** 165/165 today, 165/165 after. A
reachability oracle cannot evaluate this work. See §3.

### 2.4 The conditions, by field set

```
  982  ip_proto,ipv4_dst,tcp_dst,vlan          114  ipv4_src,vlan
  273  ip_proto,ipv4_dst,ipv4_src,tcp_dst,vlan 106  ipv4_dst,ipv4_src,vlan
  192  ip_proto,tcp_dst,vlan                    96  ipv4_dst,vlan
  134  ip_proto,ipv4_dst,vlan                   86  vlan
   68  (no match = the per-port catch-all)      36  ip_proto,vlan
   24  ip_proto,tcp_flags,vlan                   6  ip_proto,ipv4_src,tcp_dst,vlan
```

Every conditional rule carries `vlan`. A `FilterElement` can express all of these
**except `tcp_flags`**: `_filter_rule_string` already has the trailing VLAN slot
(emitted `null` today), and item 23 step 0 taught the NDD engine to read it, so
both engines now agree on that slot.

### 2.5 The 16 denies, and why `tcp_flags` is not a footnote

```
out.goza/gozb  12 rules  ipv4_src=<5 hosts>/32 + vlan=570, 172.17/16 + vlan=730
out.yoza/yozb   4 rules  ip_proto=6 + vlan=78   and   ip_proto=6 + vlan=68
```

All 24 `tcp_flags` rules are **permits** (`tcp_flags=1xxxxxxx` + `ip_proto=6` +
`vlan=78`), sitting in front of the `ip_proto=6 + vlan=78` **deny**. That is an
established-only egress filter. So:

- Dropping the `tcp_flags` conjunct **widens a permit**, which is the
  over-approximation direction this backend already documents — but it widens it
  to *all* TCP on vlan 78, which **makes the vlan-78 deny vacuous**. Two of the
  16 denies become inert.
- The `vlan=68` denies have no `tcp_flags` permits in front of them and are
  **fully expressible today**.
- The 12 `ipv4_src` anti-spoofing denies are fully expressible today.

So `tcp_flags` gates 2 of 16 denies, not the work as a whole — but it is the one
place where "declare the approximation" is doing real load-bearing work rather
than covering a rounding error.

### 2.6 A latent hole in the ingress contract

`_ingress_qualified` skips any device not in `self._fwd_devices`, and `_build`
does `self._fwd_devices -= first_match` **before** `_demux_ingress` and
`_assert_ingress_accounted` run. A first-match `FilterElement` device is
therefore invisible to the refusal that exists to catch exactly this.

Measured: **0 devices affected today** (no wl_cloud device discriminates among
its arrival ports; all 1,741 rules name an in-port, but never a discriminating
subset). So this is a **latent** hole, not a live defect — and it becomes
load-bearing the moment out-stage ports become `FilterElement`s. Step 1.

---

## 3. The oracle problem — this comes FIRST

§2.3 measured that reachability cannot move. `test_apkeep_stanford.py` compares
against a *stored* expectation, and the NetPlumber differential compares
pair sets. **None of the three current gates can tell the fixed model from the
broken one.** Building the fix first and looking for a green tier would repeat
the ad6 mistake from item 23 (a test that passed against any implementation).

So step 0 is the oracle, and it has an acceptance criterion of its own:

> **The differential must FAIL on the current tree.** If it passes before the fix,
> it is not measuring the gap.

The material is already there: `_COND_SLOTS` carries `ip_proto`, `ipv4_src`,
`ipv4_dst`, `tcp_src`, `tcp_dst` as arrival constraints built from the same
5-tuple encoding the model's own rules use, and `cchecks.json` /
`reach_csv_to_checks.py --cchecks` already express conditioned checks (wl_up and
wl_cloud use them). The 16 denies of §2.5 are all conditionable on
`ipv4_src` / `ip_proto`.

**Note the one thing the condition path cannot carry: `vlan` is not in
`_COND_SLOTS`.** Every deny is VLAN-qualified, so a conditioned check asks a
*broader* question than the deny. That is fine for a differential — both backends
get the identical broader question, and they must still agree — but it is the
reason the check is a *differential against NetPlumber* and not an assertion of a
hand-computed expected answer.

---

## 4. The build

### 4.1 Step 1 — close the ingress-contract hole (no behaviour change)

Make `_ingress_qualified` cover devices realised as `FilterElement`s, not only
those in `_fwd_devices`. Gate: the fast + integration tiers, and an explicit
measurement that the set of qualified devices is unchanged on wl_cloud, wl_up,
wl_tum, wl_deltanet (predicted: unchanged, §2.6).

Independently worth having, and it is what will refuse step 3 if step 3 is wrong.

### 4.2 Step 2 — let a `FilterElement` rule carry its VLAN match

`_filter_rule_string` gains a `vlan` parameter for slot 17 (today hardcoded
`null`); `_VLAN` joins `_FILTER_MATCH_FIELDS`.

**Do NOT also retire the `in.`/`mid.`/`out.` exemption in
`_first_match_devices`.** That is item 25's trap, measured: carrying VLAN into
every table drops wl_stanford to **150 pairs — below NetPlumber, i.e. unsound**.
The exemption stays; step 3 claims the out stage by a dedicated builder instead.

Gate: unchanged everywhere, because no non-exempt table carries a VLAN match
today (`_is_dst_lpm_table` already routes dst+vlan tables to the LPM path).

### 4.3 Step 3 — `_build_out_stage`: the 68 conditional ports become elements

Mirrors the `iacl_<idx>` pattern `_build_stanford_faithful` already uses for
ingress VLAN admission, and the `<elem>.inP` prefilter pattern
`_build_pf_pipeline` uses for in-port-qualified chain rules.

For each of the 68 conditional arrival ports `(out_dev, in_port)`:

- emit one `FilterElement` `oacl_<idx>`, carrying that port's rules in index
  order at `_FILTER_PRIO_BASE - idx` (first-match), with the egress port in the
  action slot and `__drop__` for the 16 denies;
- re-route the collapsed edge through it:
  `mid_dev mid_port oacl_<idx> inport` and
  `oacl_<idx> <egress_port> <neighbour_dev> <neighbour_port>`;
- move that port's VLAN reset out of the mid NAT and onto the element's egress
  as `+ nat oacl_<idx> <egress_port> vlan ...`.

The **613 unconditional ports keep the collapse**, which §2.1/§2.3 measured to be
exactly right for them.

**Why the reset has to move, and it is the crux.** Today the mid NAT writes the
*effective* egress VLAN — already reset to 0 where the out stage resets. An
element spliced after the mid would then match on the post-reset VLAN, not the
transit VLAN its rules are written against, and every VLAN-qualified condition
would miss. Unfolding gives the correct order: **mid NAT sets N → `oacl` matches
N → `oacl` NAT resets to 0.** All three primitives exist. §2.2 is what makes this
a clean cut: the fold applies to exactly the 68 ports being unfolded, so
`_out_reset` is consumed entirely by this step and no port is left half-folded.

**Alternative considered, and why not first:** un-collapse *uniformly* and let
`_demux_ingress` split all 681 ports, which is what plain mode already does
(`apkeep_vs_netplumber.py`: "all 48 switches survive as 719 elements"). It is
more uniform and would delete `_out_perm`/`_out_reset` outright. It is not the
recommendation because (a) `_build_first_match_tables` reads `_fwd_table`, which
`_demux_ingress` does **not** re-key, and it runs *before* the demux — so uniform
un-collapse needs a re-keying and a reordering that selective un-collapse does
not; and (b) it takes the faithful path from ~48 elements to ~700 *with*
NATElements and ACLElements, which is the deferred BDD-scalability question, not
this one. Keep it as the fallback if the selective builder turns out to need more
special-casing than it saves.

### 4.4 Step 4 — `packet.upper.tcp.flags` in both engines, or a declared approximation

24 rules, 12 ports. Two acceptable outcomes, and the choice is the owner's:

- **Implement it**: a trailing token on the `+ filter`/`+ acl` string, parsed in
  `ACLRule`/`ConvertACLRule` (BDD) and `ruleToNDD`/`withVlanSlot` (NDD). **Both
  engines must change together** or they silently answer different questions —
  that is item 23 step 0's finding, and it is the reason this is one step.
- **Declare it**: register the 12 ports as `ACCOUNT_APPROXIMATE` with the §2.5
  consequence stated in the declaration — that the vlan-78 TCP deny is inert. The
  repo's discipline permits a declared approximation; it does not permit a silent
  one.

Everything else in step 3 lands either way.

### 4.5 Step 5 — item 25's rewrite residue

Wire the existing `+ nat <dev> <port> vlan ...` into `_build_first_match_tables`
(22 rules). Subsumed by step 3 for wl_stanford; kept as its own step because the
primitive gap is general.

---

## 5. Gates

| step | gate |
|---|---|
| 0 | the conditioned differential **fails** on the current tree |
| 1 | fast + integration; qualified-device set unchanged on 4 workloads |
| 2 | fast + integration; no non-exempt table gains a VLAN match |
| 3 | the step-0 differential **passes**; 165/165 vs NetPlumber unchanged, EXTRA=0 MISSING=0, faithful *and* plain; wl_i2 61 pairs unchanged |
| 4 | both engines agree on the same rule string (extend `test/test_ndd_vlan_slot.py`'s pattern) |
| 5 | fast + integration |

Two standing constraints, both from item 24:

- **Do not gate on the reachability matrix alone.** §2.3 predicts it cannot move.
  It is a regression guard here, never the proof.
- **Production is NDD** (owner, 2026-09-24). Gate on NDD; measure BDD build time
  separately and report it — if it regresses, that is evidence for the deferred
  BDD-scalability item, not a reason to hold step 3.

---

## 6. What this does not do

- It does not touch the `in.`/`mid.`/`out.` exemption in `_first_match_devices`
  (§4.2), so the last device-name test in that decision survives this plan.
- It does not address wl_i2, whose out stage is a real dst FIB and is already
  modelled (`_build_i2_faithful`).
- It does not settle BDD scalability, which the owner deferred until after items
  24 and 25.
