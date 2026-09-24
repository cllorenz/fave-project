# Closing P7c gap 2: the wl_stanford out stage as a modelled device

**Status: step 0 DONE (negative result), step 1 DONE; steps 2-5 proceed under the
revised sec. 7 rationale (2026-09-24).** Covers TODO items 24 and 25, which are
two views of the same gap.

> **Read sec. 3 first.** The oracle step 0 asked for was built
> (`bench/apkeep_out_stage_oracle.py`) and it established that **no source->probe
> reachability question can observe this gap, in the REFERENCE model**: deleting
> all 16 out-stage deny rules from wl_stanford changes NetPlumber's own answer by
> nothing. The cause is that a high-priority match-all shadows the whole out-stage
> ACL, upstream of FaVe (sec. 3.3).
>
> The cause is a shadowing match-all, confirmed upstream: hassel reads tf files
> top-down, first-match (owner, 2026-09-24), so **wl_stanford's entire out-stage
> ACL is dead** -- 2,002 of 2,683 rules unreachable -- while its in-stage VLAN
> admission is live (sec. 3.3.1).
>
> **Sec. 7 is revised (owner, 2026-09-24): step 3 proceeds, for COST rather than
> correctness.** A shadowed rule still costs a verification tool, and APKeep is
> currently charged 0 of the out stage's 2,683 rules where NetPlumber is charged
> all of them — so the published from-zero comparison is not over the same
> workload. That gives step 3 the gate sec. 5 said it lacked. Two questions in
> sec. 7.4 gate it in turn. Companion to [`TABLE_SEMANTICS_PLAN.md`](TABLE_SEMANTICS_PLAN.md)
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

## 3. Step 0 — the oracle, and its negative result

Sec. 2.3 measured that reachability cannot move, so step 0 built a header-level
differential before touching the adapter, with one acceptance criterion:

> **The differential must FAIL on the pre-fix tree.** If it passes before the
> fix, it is not measuring the gap.

It does fail -- and then the investigation of *why* it fails invalidated it as a
gate. Both halves are below, because the second is the result.

### 3.1 What was built

`bench/apkeep_out_stage_oracle.py`. It drives wl_stanford through both backends
in the PRODUCTION configuration (APKeep faithful + NDD, the aggregator default)
and diffs the pair sets for a question narrowed two ways:

- `--seed` constrains what the GENERATORS emit;
- `--cond` constrains what may ARRIVE at the probe (`_COND_SLOTS` /
  `_create_compliance_rules`).

Nothing in wl_stanford rewrites anything but `vlan` (checked: the only `rw=` kind
in `routes.json`), so for `proto`/`src`/`dst` the two are the same question.

Aiming a question at a deny needs both halves at once. Every out-stage deny is
VLAN-qualified and no engine-portable condition can name a VLAN, so a single
field leaves reachability existential over every VLAN and never reaches the deny.
Pinning the DESTINATION pins the VLAN, because the mid stage assigns the egress
VLAN per dst route. That is how the battery was derived -- from the discarded
rules, not guessed: `mid.yoza/yozb` route `172.24.68.0/23` with `rw=vlan:68` onto
the out in-ports carrying `ip_proto=6 + vlan=68 -> DROP`.

### 3.2 The result: the reference model cannot see its own denies

```
$ python bench/apkeep_out_stage_oracle.py --drop-out-denies \
      --seed none \
      --seed 'ipv4_dst=172.24.68.0/23+ip_proto=6' \
      --seed 'ipv4_dst=171.64.158.0/23+ipv4_src=217.78.63.15/32'

seed=none                                      intact=165  without-denies=165   INERT
seed=ipv4_dst=172.24.68.0/23+ip_proto=6        intact=30   without-denies=30    INERT
seed=ipv4_dst=171.64.158.0/23+ipv4_src=...     intact=39   without-denies=39    INERT
```

**Deleting all 16 out-stage deny rules changes NetPlumber's answer by nothing.**
Not unconditioned, not under a seed aimed squarely at each deny. And the seeded
backend differential agrees everywhere: APKeep 30 = NetPlumber 30 for both
`ip_proto=6` and `ip_proto=17` on the TCP-deny route.

**Then the same test over each deny's WHOLE targeted header space.** The 16
denies match on exactly seven source-controllable header classes -- six `ipv4_src`
values and `ip_proto=6` -- so seeding each one with the destination left FREE asks
the most favourable existential question a deny could possibly answer: *is there
any route, to any destination, on which this traffic's fate depends on the deny?*

```
seed=ipv4_src=217.78.63.15/32    intact=165  without-denies=165   INERT
seed=ipv4_src=210.132.185.87/32  intact=165  without-denies=165   INERT
seed=ipv4_src=221.132.67.163/32  intact=165  without-denies=165   INERT
seed=ipv4_src=202.181.206.18/32  intact=165  without-denies=165   INERT
seed=ipv4_src=200.87.13.14/32    intact=165  without-denies=165   INERT
seed=ipv4_src=172.17.0.0/16      intact=165  without-denies=165   INERT
seed=ip_proto=6                  intact=165  without-denies=165   INERT
```

Seven for seven. The remaining field each deny carries is `vlan`, which a source
cannot set -- the mid stage assigns it per route -- so leaving it free is the
strongest form of the question, not a gap in it. This is as near exhaustive as a
pair-level test can be: **no traffic a wl_stanford source can emit has its
reachability changed by any of the 16 denies.**

So the gap is unobservable through a probe, and two independent readings of the
data say the same thing:

1. **Egress (sec. 2.3).** All 68 conditional arrival ports have a SINGLE-egress
   catch-all, and no narrower permit routes anywhere else. The 2,118 discarded
   permits are therefore redundant with their catch-all -- HSA decomposition
   artefacts, not policy. **Only the 16 denies remove anything at all.**
2. **VLAN, and this one is narrower than it first looks.** The denies are
   written against VLANs 68, 78, 730 and 570, and no out-stage rule *on the
   device carrying the deny* ever resets those to 0 -- the only vlan-570 resets
   are on `out.yoza` in-ports 1530047/1530043, while the vlan-570 denies are on
   `out.goza`/`out.gozb`. All 16 probes filter `vlan=0`. So denied traffic can
   never reach **that router's own** probe.

   It does **not** follow that it can reach no probe at all: absent the deny the
   packet would continue to the next router, whose mid stage could rewrite the
   VLAN and whose out stage could reset it to 0. So (2) narrows where the denies
   could possibly matter; it does not by itself prove they cannot. The proof is
   (1) plus the measurement, not (2).

### 3.3 Why: the rules are SHADOWED (owner, 2026-09-24)

The measurement says the denies do nothing; it does not say why. The owner's
reading does, and it is the better statement of the same fact: **a high-priority
match-all rule shadows everything behind it**, so the out stage's filtering
behaviour cannot depend on which packet class is sent through it.

Verified at three independent encodings of the order, and at the source rather
than in FaVe's output:

```
FaVe routes.json   the match-all is FIRST by rule index on all 68 conditional ports;
                   all 1,986 narrower permits and all 64 deny instances follow it
stanford-json/152.tf.json (a TRACKED upstream artefact):
                   array order == `id`-counter order == `position` order, and the
                   match-all holds the lowest of each on 32 of 32 out-stage ports
                   with more than one rule -- e.g. in_port 1530053: match-all at
                   position 7, the 158 ACL rules at 82 and beyond
```

So FaVe preserves the upstream order; it does not create the shadowing.

**But the operator did not write it either**, and that is the part worth being
careful about. The real Cisco ACL behind those rules is well formed:

```
access-list 178 remark CSDCF: ACL for Theory Lab, vlan 78
access-list 178 permit tcp any any established
access-list 178 permit ip 171.64.78.0 0.0.0.255 172.24.78.0 0.0.0.255
...                                                            (91 lines)
```

Nothing in it is dead. The match-all that kills it is introduced one layer up, in
the HSA transfer function, where the forward-out-the-interface rule is emitted
*ahead* of the ACL. So the suboptimality this benchmark exercises is the
compilation's, not the network's.

**SETTLED (owner, 2026-09-24): hassel reads the tf files top-down with
first-match semantics.** This was left open here as the one thing that could have
made the problem much larger -- if the ACL were live upstream, FaVe's reading
would be what kills it, in both backends. It is not: FaVe's reading is correct,
and the dead ACL is a property of the shipped dataset.

### 3.3.1 Which stages that applies to, and the trap in the inference

"A leading match-all shadows what follows" holds only for a **first-match** table.
It is wrong for an LPM table, where a leading default route is just the /0 entry
and longer prefixes win regardless of file order. wl_stanford declares
`fib_table_types: ['mid']` (`stanford-json/config.json`), so `mid` is LPM and
`in`/`out` take the implicit first-match default. Applying the test per stage:

```
stage  arrival ports   with >1 rule   leading match-all   semantics   verdict
in         252             149               0            first-match LIVE
mid         16              16              16            LPM         not shadowing -- the default route
out        681              68              68            first-match DEAD
```

The mid column is exactly the trap: read without the declaration it says the
entire 3,844-rule FIB is dead, which is plainly false -- forwarding works, and
seeding a destination changes the pair count. It is the `table_semantics`
distinction item 23 built, doing its job.

So the conclusion is stage-specific and sharper than "wl_stanford has dead rules":

> **wl_stanford's only live filtering is the in-stage VLAN admission. Its entire
> out-stage ACL is dead** -- 2,002 of the out stage's 2,683 rules (1,986 narrower
> permits + 16 denies) are unreachable, and the 681 live ones are one match-all
> per arrival port.

That the in stage is live matters for sec. 7.2: APKeep's 2,265 -> 52 there is a
re-encoding of semantics that really are in force, not a compression of rules
that were dead anyway.

### 3.4 What this does and does not mean

- It does **not** say the collapse is correct in general. It says the collapse is
  reachability-EQUIVALENT to the faithful out stage *on wl_stanford*, which is
  now proved structurally and empirically rather than assumed.
- It does say that closing the gap **cannot be gated on wl_stanford**, by any
  reachability oracle, and that on wl_stanford it buys nothing observable.
- The 1,986-rule and 16-deny figures in TODO item 24 and `APKEEP_BACKEND.md`
  stand as counts of what is discarded. What changes is their *consequence*: the
  1,986 were already redundant, and the 16 are inert.

**This is an owner decision, not a technical blocker.** The options are laid out
in sec. 7.

### 3.5 A separate defect found on the way (TODO item 26)

For **NetPlumber**, a dst-CONDITIONED check and a dst-SEEDED check give different
answers -- 35 vs 30 on the full model, 2 vs 1 on the `yoza_rtr,bbra_rtr`
subnetwork -- although nothing but `vlan` is rewritten, which makes them the same
question. APKeep's two answers agree with each other and with NetPlumber's seeded
one, so two of the three readings agree and NetPlumber's conditioned check is the
odd one out. The divergence is in the unsound direction for whichever is wrong,
and `--cond` reproduces it in ~20 s on a two-router model. Filed separately
because it has nothing to do with the out stage, and it is the reason `--seed` is
the trustworthy instrument above.

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

| step | gate | status |
|---|---|---|
| 0 | a header-level oracle that **fails** on the pre-fix tree | **DONE — negative result, sec. 3** |
| 1 | fast + integration; qualified-device set unchanged on 4 workloads | ready |
| 2 | fast + integration; no non-exempt table gains a VLAN match | ready |
| 3 | reachability unchanged (guard) **+ a reported cost delta** — sec. 7.3 | gated on the sec. 7.4 questions |
| 4 | both engines agree on the same rule string (extend `test/test_ndd_vlan_slot.py`'s pattern) | ready, but subordinate to 3 |
| 5 | fast + integration | ready |

**Step 3 has no CORRECTNESS gate, and that is the finding rather than an
omission.** The original entry read "the step-0 differential passes; 165/165
unchanged". Sec. 3 showed the first clause is unreachable — NetPlumber cannot see
the denies either, so no reachability differential can distinguish the fixed
model from the broken one — and the second is satisfied by doing nothing at all.

**Sec. 7.3 supplies a different gate: a reported COST delta.** That is what the
benchmark exists to measure, it is achievable, and it does not pretend to be a
correctness proof. The candidates below remain the options for a correctness gate
should one ever be wanted; none is a prerequisite for step 3 under the cost
framing.

1. **A purpose-built fixture.** A small model in `test/` with an out-stage-shaped
   device whose deny IS observable — a probe that accepts the denied VLAN. Tests
   the mechanism honestly and costs a day; does not tell us anything about
   wl_stanford.
2. **Rule-string unit tests.** Assert the emitted `+ filter` strings for the 68
   conditional ports. Pins the implementation, not the semantics — and on its own
   it is the ad6 mistake again (green against any model that emits those strings).
3. **A NetPlumber flow-tree differential.** Compare the header space ARRIVING at
   each probe rather than a yes/no, via `dump_flow_trees`. The only gate that
   would measure the real thing, and APKeep has no equivalent dump — so it is
   substantial work in the Java engines before it could be a gate at all.

Two standing constraints, both from item 24, and sec. 3 sharpened the first from
a prediction into a measurement:

- **Do not gate on the reachability matrix.** Not "not alone" — not at all, for
  this gap, on this benchmark.
- **Production is NDD** (owner, 2026-09-24). Gate on NDD; measure BDD build time
  separately and report it — if it regresses, that is evidence for the deferred
  BDD-scalability item, not a reason to hold a step.

---

## 6. What this does not do

- It does not touch the `in.`/`mid.`/`out.` exemption in `_first_match_devices`
  (sec. 4.2), so the last device-name test in that decision survives this plan.
- It does not address wl_i2, whose out stage is a real dst FIB and is already
  modelled (`_build_i2_faithful`).
- It does not settle BDD scalability, which the owner deferred until after items
  24 and 25.

---

## 7. Why step 3 is worth doing anyway: cost, not correctness

**Revised 2026-09-24 after the owner's reading of sec. 3.3.** The earlier version
of this section recommended closing item 24 as measured-inert, on the grounds
that the fix bought nothing. That was premised on correctness being the only
thing at stake. It is not.

### 7.1 The argument

Two premises, both the owner's:

1. **An unreachable rule still costs a verification tool.** It occupies storage,
   it is parsed and encoded, and in an atomic-predicate engine it can split
   predicates whether or not any packet ever reaches it. "Dead" is a property of
   the packet space, not of the work.
2. **Benchmarking FaVe exists to quantify what to expect on an unknown
   workload.** A tool is useful only if it processes real configurations
   including their suboptimalities, and the benchmark is only informative if it
   charges the tool for them.

The out-stage collapse means APKeep is not charged. Measured, wl_stanford:

| stage | FaVe model | NetPlumber | APKeep faithful | APKeep plain |
|---|---|---|---|---|
| `in` | 2,265 | 2,265 | **52** | **52** |
| `mid` | 3,844 | 3,844 | 7,216 | 3,844 |
| `out` | 2,683 | 2,683 | **0** | 1,576 |
| total to the engine | 8,792 | 8,792 | 7,328 (+60 ACL) | 5,472 |

So `bench/apkeep_vs_netplumber.py` reports a from-zero comparison in which one
backend was handed 2,683 rules the other declined. Whatever that difference is
worth, it is currently attributed to engine speed.

### 7.2 Two corrections to that argument, so it does not prove too much

**The in-stage number is NOT the same kind of gap.** 2,265 → 52 is the larger
compression, but it is a re-encoding, not a discard: the faithful path expresses
per-port VLAN admission as 60 `iacl_*` ACL rules, each matching a whole admitted
VLAN set at once rather than one rule per tag, and the result was measured sound.
Turning 2,265 rules into 112 is a legitimate translation result -- arguably a
finding to report rather than a distortion to fix. **The out-stage 0 is
different: semantics dropped, not compressed.** Only the second belongs in the
cost complaint.

**Eliding dead rules is a FEATURE, not a cheat** -- when a tool detects them.
That is shadow/anomaly detection, and NetPlumber implements it (`check_anomalies`)
while APKeep raises `NotImplementedError`. The defect in `_capture_out_perm` is
not that it elides, it is that it elides **without checking**: it ignores the
match unconditionally, so it would return the identical answer if positions 7 and
82 in sec. 3.3 were swapped and the ACL were live. Right answer, wrong reason.

**That is the correctness argument for step 3, and it is the only one that
survives sec. 3.** Not "the current numbers are wrong" -- they are not -- but
"the current numbers do not depend on the rules being shadowed, so they would not
change if they were not."

### 7.3 The gate this supplies

Sec. 5 records that step 3 had no gate: no reachability oracle can distinguish
the fixed model from the broken one. Cost can, and cost is what the benchmark is
for. Step 3's acceptance criterion becomes:

- **regression guard**: 165/165 vs NetPlumber unchanged, EXTRA=0 MISSING=0,
  faithful *and* plain; wl_i2's 61 pairs unchanged. Necessary, never sufficient.
- **the actual result**: a REPORTED cost delta from carrying the 2,683 rules --
  build time, element count, NDD atom count, and BDD build time measured
  separately. Reported, not bounded: a large delta is the finding, not a failure.

This is achievable, unlike a correctness gate, and it answers the question the
benchmark exists to ask.

### 7.4 Therefore

**Do step 3** (with steps 1, 2, 4 and 5 around it), for the cost measurement and
for the translation robustness of sec. 7.2 -- not for a reachability number,
which will not move. Sec. 4.3's design is unchanged: 68 conditional ports become
`FilterElement`s, 613 keep the collapse, the VLAN reset unfolds from the mid NAT
onto the out element.

**The hassel-semantics question is SETTLED** (owner: top-down, first-match), so
nothing blocks step 3 on correctness grounds. One decision remains:

**Charge APKeep the full 2,683, or only the 681 live ones?** Now that the split is
known exactly -- 681 live match-alls, one per arrival port, and 2,002 dead
(1,986 narrower permits + 16 denies) -- this is the whole cost question in one
number. Carrying all 2,683 is the honest cost of the workload as shipped and is
what premise 1 asks for; carrying only the live ones would measure a network
nobody operates. **Recommendation: all 2,683**, with the live/dead split reported
alongside so the number can be read either way.

**A by-product worth taking separately:** wl_stanford contains 2,002 unreachable
rules and no FaVe backend currently reports them -- NetPlumber could
(`check_anomalies`), APKeep raises `NotImplementedError`. "This benchmark's
out-stage ACL is entirely dead, and its only live filtering is the in-stage VLAN
admission" is a benchmark result in its own right, and establishing it took an
out-of-band investigation plus an owner ruling on hassel's semantics rather than
a FaVe run. That is its own gap, and it is the one a user of the suite would most
want closed: a workload's *live* rule count is what its cost numbers should be
read against.
