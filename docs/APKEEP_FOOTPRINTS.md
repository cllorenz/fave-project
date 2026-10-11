# APKeep footprints: which checks an update re-checks

A self-contained account of how FaVe's incremental APKeep (BDD-APKeep and
NDD-APKeep) decides which compliance checks to ask again after an update,
written to be lifted into a paper. Design history, code locations and the
indicative measurements are in `APKEEP_INCREMENTAL_SCOPE.md` §4 and §9; the
evidence is cited in §6 below.

**Default (owner, 2026-10-11): witness + dead ends.** The coarse footprint
stays selectable (`footprint=()`, `--footprint coarse`) and is the reference
row of the ablation (`INCREMENTAL_PLAN.md`).

## 1. Setting

- A **check** asks whether packets from a source (a port, narrowed to a source
  prefix, the **seed**) can reach a target port, under the check's header
  conditions. The answer is existential: *reachable* iff at least one packet
  has a path.
- The network is APKeep's: **elements** (forwarding tables, ACLs, rewrites, the
  packet filter's first-match stage), each mapping packet sets to its logical
  ports, joined by **links** between physical ports.
- An **update** is a rule insertion or deletion, or a link going up or down.
  APKeep turns a rule update into **changes** `(e, δ, from, to)`: at element
  `e` the packet set `δ` now leaves by port `to` instead of `from`. A link
  update changes one physical port's downstream.
- The **walk** answering a check is APKeep's depth-first search from the
  source. It carries the set of packets still alive, and it stops at the first
  packet set that arrives at the target.
- Updates are applied in batches. After a batch, `takeAffected` reports the
  checks to ask again; those are re-answered, and the rest keep their cached
  answers.

**What is claimed.** The rule below is *sound*: every check whose answer
changed in the batch is reported. A reported check is answered from scratch by
the unchanged engine, so the footprints decide only *which* checks are asked,
never an answer. Not claimed: minimality.

**Assumptions** the arguments use, and why FaVe's model meets them:
- **A1, existential checks.** Reachable iff some packet has a path. (An
  isolation requirement is the negation of the same query, so it re-checks
  when the query does.)
- **A2, a complete walk.** If a path exists, the walk finds one. The DFS is
  exhaustive up to its first witness.
- **A3, monotone forwarding.** Every element's transfer is a union over
  packets, with no negation over packet sets. A rewrite's image grows with its
  input. Hence removing packets from a port can only remove paths, never
  create one.

## 2. The coarse footprint (scope §4)

For each check, the walk records, per element it visited, the forwarded set
and the seed set that arrived there, plus the physical ports it left by. A
change `(e, δ, ·, ·)` reports the check if `δ` meets either set at `e`; a
link update reports it if it left by that port.

*Sound because* a change that meets nothing that arrived at `e` cannot alter
anything the walk saw. A link update off the walk's ports cannot either.

*Coarse because:*
- The seed constrains only the source address, so it meets almost every
  change.
- For a reachable check, the explored part depends on the order in which the
  walk tries ports (§5).

## 3. Witness (reachable checks)

**Idea.** A reachable check needs only one surviving path. Its footprint is
that path, not everything the walk explored on the way.

**Definition.** When the walk reaches the target, it records the **witness**:
- the sequence of **hops** (element, the logical port it left by, or none for
  a rewrite);
- the **egress** physical ports (links) it used.

Let `W` be the packets that arrived at the target within the seed and the
check's conditions. Pick one concrete packet `p ∈ W`, a full header
assignment, chosen deterministically.
- A hop **after the path's last rewrite** carries `{p}`: there the header is
  unchanged, so `p` is the very packet that traversed that hop.
- A hop **at or before the last rewrite** carries the forwarded and seed sets
  that arrived there. The header `p` had there is a pre-image under the
  rewrite, which we do not compute.

The check is reported if, in the batch:
- a change at a hop element with `from` = the hop's port has a `δ` meeting the
  hop's set; or
- a change at a rewrite hop has a `δ` meeting its set, whatever the port; or
- a link update hits an egress port.

**Soundness (sketch).** Suppose none of these occurred.
- **Hops after the last rewrite.** At each of these hops, no change moved
  packets of the hop's set (`{p}`) out of the hop's port. A change moving
  packets *into* that port only adds. So `p` still leaves every such hop by
  the same port.
- **Rewrite hops and the hops before them.** No change moved any packet of the
  arriving set out of the hop's port. At a rewrite hop, no change touched the
  arriving set at all. So whatever packets made the path at those hops still
  do.
- **Links.** The links used are unchanged.

So the path still delivers a packet to the target (A3 for the rewrite's
image). By A1 the check is still reachable, and by A2 a re-check would find a
path again. Changes elsewhere, including on branches the walk tried first, can
only add paths.

**What it does not cover.** An unreachable check has no witness, so it keeps
an explored footprint: the coarse one, or the one of §4.

## 4. Dead ends (unreachable checks)

**Idea.** An unreachable check changes only if a path *opens*, and a path
cannot open through packets sent nowhere.

**Definition.** The **to-port** of a change at element `e` is a **dead end**
for a check if it is one of:
- the deny port, or the packet filter's drop sink; or
- a logical port all of whose physical ports have no link, judged on the
  topology after the batch. None of them may be one of the check's targets.

Rewrite elements and an ACL element's permit ports are never dead ends: their
downstream positions are not named after the element, so "no link" cannot be
read off them. An ACL's deny port is a dead end.

For an unreachable check, a change whose `δ` meets its explored footprint at
`e`, but whose to-port is a dead end, is *not* reported. Instead its physical
ports join the ports the check watches. Every other rule of §2 applies
unchanged.

**Soundness (sketch).** A change `(e, δ, from, to)` removes `δ` from `from`,
which by A3 removes paths only, and adds `δ` to `to`. Any new path would have
to continue from `to`, and from a dead end nothing continues:
- deny and drop forward nothing;
- an unlinked port is not the target and leads nowhere.

The other changes of the batch are tested on their own. One that later moves
those packets on from the dead end has `from` = the dead end, a `δ` meeting
what arrived at `e`, and its own to-port to test. A link that comes up on the
dead end is a link update on a watched port. Changes are tested before link
updates within a batch, so a port watched in the same batch is seen.

**Kept apart.** A reachable check's explored footprint (when witness is off)
is never subject to this rule: moving its witness packets into a dead end
*can* make it unreachable.

## 5. Caveats to state with the results

- **The counts depend on the witness found.** Which witness the DFS finds, and
  therefore which updates hit it, depends on the order in which each element's
  ports are tried. Soundness does not depend on it; the re-check counts do.
  The two engines iterate ports in different orders: BDD-APKeep in a
  `HashMap`'s hash order of port names, NDD-APKeep in `NddPorts`'
  `LinkedHashMap` insertion order. Under witness their totals happened to be
  equal on `wl_example`, `wl_airtel1` and `wl_ifi` S3, but nothing guarantees
  that. Owner decision, 2026-10-11: the authors' checker code stays as it is
  (`APKEEP_INCREMENTAL_SCOPE.md` §9, "Known properties").
- **One packet per hop is a choice.** Any `p ∈ W` is sound; a different `p`
  gives different counts. `p` is deterministic: JDD's `oneSat` with free
  variables 0 on BDDs, the first non-empty NDD path on NDDs.
- **Rewrites.** At and before a path's last rewrite, the footprint falls back
  to the arriving sets. Inverting the rewrite to carry `p` backwards would be
  finer; it is not built.
- **Cost.** A witness costs a union of the arrived sets, one packet, and a set
  per hop, on every reachable re-check. On a tiny network that is the same
  order as the walk itself: `wl_example` S1's median re-check time doubles
  from about 0.5 to about 1.1 ms. Every larger cell got faster.

## 6. Evidence (indicative: dev, one repetition)

Sources: `fave/bench/campaigns/results_inc_dev_footprints_20261010/FINDINGS.md`
(predictions committed before the run) and its `default_switch_check/`.

- **Same verdicts.** Every mode changed the same verdicts as the coarse
  footprint, on every update of 84 timed cells. Three oracle runs (selective
  == full after every update, full == from-zero at checkpoints) pass with both
  modes.
- **Oracle tests.** Every stream of `fave/test/test_incremental_apkeep.py`
  passes under the oracle on both engines, now at the default and also with
  the coarse footprint; NDD-APKeep is also tested with dead ends alone. One of
  these streams is `wl_cloud`, with NATs under updates.
- **Unit tests.** `fave/test/test_apkeep_incremental_core.py` tests each rule
  on a small network. Examples: only the half of a split path holding `p` is
  reported; before a rewrite the arriving set counts; a link coming up on a
  dead end is reported.
- **Negative controls.** Two variants, each with one plausible bug, fail both
  unit tests and oracle tests:
  - the witness test on the to-port instead of the from-port: 6 unit tests,
    4 of 6 oracle tests;
  - every port a dead end: 6 unit tests, 5 of 6 oracle tests.
- **Effect.** Re-checks summed over 200-update streams, coarse → both modes:

  | workload | S1 | S2 | S3 |
  |---|---|---|---|
  | `wl_cloud` | 5,330 → 10 | 5,181 → 466 | 4,540 → 1,866 |
  | `wl_airtel1` | ~3,500 → 0 | ~4,200 → 4 | ~10,100 → 4,564 |

  NetPlumber on `wl_cloud`: 10 / 45 / 370. On `wl_cloud` the median per-update
  re-check falls from 63–76 ms to 0.04 ms on S1 and S2.
- **Which mode does what.** Witness alone covers link updates (S3), because a
  link update triggers by port, where dead ends has nothing to say. The two
  modes are complementary on rule updates: witness narrows the reachable
  checks, dead ends the unreachable ones.
