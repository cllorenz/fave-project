# State as virtual header bits: generalizing state shell interweaving

**Status (2026-10-14): RESEARCH, not started.** §8's questions answered from the thesis and the code where they could be; one remains for the owner (questions 2–4 decided 2026-10-14). Filed after an owner discussion of
which device classes FaVe should model next (TODO item 51). Nothing here is built
or measured. §3 is a hypothesis, and §7 is the first experiment that would test it.
Its prerequisite is TODO item 50, which was found while preparing this document.

## 1. The question

Most device classes worth adding to FaVe hold state: NAT gateways, cloud
security groups, load balancers, learning switches. FaVe has two ways to model
state, and neither carries over to them:

- **Snapshots** (`devices/snapshot_packet_filter.py`) feed live state changes
  into the model. They do not scale. The thesis (Lorenz 2026, §7.1.6, Fig. 7.8)
  measured one firewall in front of one web server. FaVe fell behind the
  connection rate **between 400 and 500 new connections/s when only the state
  rules were inserted**. **With traffic propagating**, which verification needs,
  it fell behind **between 10 and 50/s**. The 2021 paper's "up to 400" is the
  first figure. Snapshots also verify only the states observed, not all
  reachable ones.
- **State shell interweaving** (`iptables/generator.py`; thesis §7.1.7, the
  2021 paper's §IV) scales, but models conntrack alone, with two states.

The thesis names this question as future work. Its outlook (Chapter 9,
*Application Level Policies*) proposes "adapting the state shell interweaving
from Section 7.1.7 to support generic models like finite automata". The
motivating case there is the ALG (Appendix A.14), whose relays rely on snapshots.

**Question:** can state shell interweaving be generalized to a finite state
machine per device class, projected onto virtual header bits, so that
verification remains one propagation run and incremental updates keep working?

## 2. Baseline: what state shell interweaving does

As implemented (`_derive_general_state_shell`, `_derive_conditional_state_shells`,
`_interweave_state_shell`):

- conntrack's state is projected onto one virtual header bit, `related`:
  `NEW` packets carry 0 and `ESTABLISHED` packets carry 1. There is no `RELATED`
  state and nothing connection-specific, such as counters.
- The **general state shell** consists of the direction-swapped copies of the
  chain's rules, matching `related=1`. The **conditional shells** intersect it
  with each state-checking rule and are woven in at that rule's position, so
  rules before a state check still see backward traffic first. This is the
  inter-rule dependency the paper's §IV-A example shows.
- Both directions travel through the network **in the same run** (owner,
  2026-10-13). That run is what keeps verification cheap and updates
  incremental. In the code, a source leaves `related` as a wildcard
  (`devices/generator.py` never sets it), so each source's flow covers forward
  and backward packets at once. Only the checks constrain the bit (§4).

The thesis states the shell's limits itself (§7.1.7, *Limitations*):
- no custom chains, so rule sets must be preprocessed first;
- **no `RELATED`**: only an FTP or RTP session's control channel is analysed;
- no complex extension modules (pattern matches, rate limiting, eBPF);
- stateful traffic is assumed to cross **the same firewall interfaces in both
  directions**, which leaves out load balancing across firewall interfaces.
  This is condition (c) of §3 below.

Two properties make one run enough:

1. **State is carried by the packet.** A connection's state is the same at every
   device on its path, so the packet can carry it as a header field.
2. **Every condition on state is local and static.** A backward packet passes a
   firewall if that firewall's own rules would accept the reversed header. That
   condition is fixed by the configuration. It does not depend on what the
   network actually delivered to the device.

A design that makes a device's state depend on a propagation result would need
several runs that depend on each other, so it loses both properties (§5).

## 3. Hypothesis: a device-local state machine, compiled to header bits

A device class qualifies when:

- **(a)** its state is keyed by header fields (5-tuple, source address, ...);
- **(b)** its transitions are guarded by header predicates;
- **(c)** the state is a property of the connection: the same at every device
  on its path.

Then, for each device:

1. Number the states Q in k = ⌈log₂|Q|⌉ virtual header bits.
2. Compute, **from the device's own rules only**, the set of (state, header)
   pairs the device can reach. This assumes any packet history may arrive. It
   is a small local fixpoint: finite and independent of the network.
3. Compile that set, together with the rules that act on each state, into
   stateless rules over the header plus the k bits.

Today's shell is the case |Q| = 2, k = 1. This would preserve:

- **one run:** every condition is still local (property 2);
- **incremental updates:** a rule change at a device recomputes that device's
  compiled rules, and the difference reaches the engine as ordinary inserts and
  deletes.

Counters and timers cannot be represented and become **nondeterministic**: a free
bit that the check leaves as a wildcard. As FaVe's field map reads, `-m limit`
already works this way: it is the virtual field `module.limit` (32 bits). It
appears in 113 of `wl_up`'s rule sets, and the thesis's Tab. 7.2 lists `limit`
among UP's header fields.

**Header width: probably no expansion needed.** `related` is already an 8-bit
field (`netplumber/mapping.py`), and one bit of it is used:
`util/ip6np_util.py` normalizes a value to `<bit>xxxxxxx`. So up to 7 more state
bits fit without widening the header. That matters because widening at runtime
costs 2–3 orders of magnitude more than a rule insertion (thesis §6.3, Fig. 6.15:
2,906 ms against 9.86 ms at 50,000 rules).

**Per-engine cost of wider state (code, 2026-10-14):**
- NetPlumber, ad6 (`related` declared 8 bits wide) and VeriFlow-FR (any field
  in `FIELD_SIZES`) read the field generically.
- APKeep's adapter refuses any `related` value other than 0 or 1
  (`apkeep/adapter.py`, the query-condition parser, and `related` declared 1 bit
  wide). Its checker (`ReachabilityChecker.java`) also relies on **nothing in
  FaVe's models ever rewriting `related`**. §3 keeps that property, because a
  connection's state does not change along its path. A design in which devices
  rewrote state bits would break the shortcut.

## 4. Precision, soundness, and how to recover precision

Each place the conditions in §3 fail costs **precision** for isolation
properties ("A must not reach B"), not soundness:

| Condition fails | Example | Effect |
|---|---|---|
| (c) | asymmetric routing; a device that sees only one direction; tracking that starts mid-path | the device assumes a history it never saw, which causes false alarms. Being exact would need state bits per device. |
| field correlation | masquerade NAT and port translation: the reply must restore *the* original source | HSA rewrites set constants or wildcards and cannot copy one field into another. The reverse rewrite goes to the wildcard set of possible originals. This is exact for 1:1 NAT. The BDD engines might express field equality, which is an open question for each backend. |
| order, counting | `recent --hitcount`, `limit`, `connlimit` | nondeterministic (§3) |

**Required reachability** is the opposite case: an over-approximation can hide a
violation. This is already true of today's shell.

**Which checks are affected, per check type.** The thesis (§7.2, *Transforming
FPL rules*) compiles `A <->> B` into three checks, and
`bench/reach_csv_to_checks.py` emits exactly these for a `(X)` cell:

| check | emitted as | effect of an over-approximated state |
|---|---|---|
| A reaches B | `s=A && EF p=B` | `related` unconstrained, so a backward packet also counts. A shell that is too permissive can satisfy it. |
| B answers A | `... && f=related:1`, must reach | **can hide a violation**: the abstraction may let a reply through that the real firewall drops |
| B never initiates to A | `! ... && f=related:0` | **unaffected**: shell rules match `related=1` only |
| default deny | `! s=A && EF p=B`, no `related` constraint (`_deny_checks`) | **false alarms only**: a reply the abstraction admits but the device would not counts as a violation |

So FPL's `<->>` mixes both directions. Its answer half is the one that loses
soundness under a coarser abstraction, and its no-initiation half is exact. A
generalized compiler must keep the no-initiation half exact. Any new state that
admits more replies needs either an exact guard, or the per-alarm refinement
below run on the **satisfied** `related:1` checks too.

**Lazy refinement**, if false alarms become a problem: for each alarm that
depends on a state bit, check whether the history it assumes can reach the
device. That is one extra query per alarm, not per verification, so the
single run and the incremental path stay as they are.

## 5. Alternatives considered

- **A fixpoint across the whole network over abstract state** (forward run, then
  derive state at each device, then run again, until stable). It drops the
  locality assumption, but needs several runs that depend on each other.
  **Not pursued** (owner, 2026-10-13): it gives up the single run that makes
  the current design cheap and incremental.
- **Snapshots as the verification method:** do not scale (§1).
- **Snapshots as a test oracle: kept.** Every concrete state a snapshot observes
  must lie inside the compiled abstraction. Throughput does not matter there.

## 6. Device classes by kind of state

| Kind of state | Device classes | Approach |
|---|---|---|
| none | VRFs and policy routing, mirror ports and taps, data diodes, stateless cloud ACLs | no state problem |
| traffic-created, reversible | security groups, Kubernetes NetworkPolicy, static 1:1 NAT, fixed DNAT port forwards | today's shell, generalized as a template per device class |
| traffic-created, more than direction | conntrack `RELATED`/`UNTRACKED`/`INVALID`, `-m recent`, masquerade/PAT, sticky load balancers | §3, with the losses of §4 |
| control-plane driven, low rate | spanning-tree port states, load-balancer health, FIBs | snapshots may be acceptable: the scaling problem is per-connection state. Open question for the owner (§8). |
| externally driven | 802.1X, VPN security associations, identity-based firewalls | a parameter: verify over every authorized assignment |

## 7. First experiment

- **E0 (prerequisite): TODO item 50.** Today any conntrack match other than
  exactly `ESTABLISHED` or `NEW` is dropped, and its rule becomes unconditional.
  A state list has to be handled before `RELATED` can be a state of its own.
- **E1 — formalize.** Define Q, the guards and the local fixpoint for conntrack
  with `NEW`, `ESTABLISHED`, `RELATED`, `UNTRACKED` and `INVALID`, in the 2021
  paper's notation. `RELATED` covers both halves of §8.3: helper expectations,
  and ICMP errors (wildcard first, embedded-header fields as a measured
  variant). Today's shell must fall out as the two-state special case.
  This is the regression oracle: on every workload, the generalized compiler
  restricted to two states must produce the same verdicts as today's.
- **E2 — conntrack plus `recent`.**
  - Input: synthetic rule sets, then the raw TUM save
    (`bench/wl_tum/iptables-save-2015-05-15_15-23-41_tum`). The raw save
    uses `RELATED,ESTABLISHED,UNTRACKED` (lines 134 and 144) and `recent`'s
    `ratessh` list (lines 137–159). FaVe's `wl_tum` cannot serve as input: it
    is a preprocessed rule set (`rulesets/tum-ruleset`, 3,795 lines against the
    raw 4,948) with `ESTABLISHED` only and no `recent` or `limit`. Getting the
    raw features through FaVe's parser is part of E2.
  - Measure: header bits added; size of the compiled rules against today's
    shell (the conditional shells are already products of rules and
    state-checking positions); single-run verification time and incremental
    update cost per engine. Engines (owner, 2026-10-14): NetPlumber, with ad6
    as sparring partner, while the encoding and its algorithms are being worked
    out; ad6 is a different paradigm (SAT/QBF), so verdicts that agree across
    both test the encoding rather than one engine. The other engines follow in
    a step of their own once the encoding is stable. APKeep and NDD need atoms
    over the new bits, and APKeep's adapter must first accept more than one bit.
  - Soundness check, on small networks: a brute-force concrete-packet simulation
    with real conntrack semantics, plus the snapshot oracle of §5.
- **E3 — static NAT,** the first state that depends on more than direction.

## 8. Questions: answered from the thesis and the code (2026-10-14), and what is left

1. **Where are the snapshot measurements, and do they cover low-rate state?**
   *Answered:* thesis §7.1.6, Fig. 7.8 (§1 above). Each request inserted one
   connection's two state entries, one per direction. The limit is the cost of
   each update (insertion plus propagation) against the rate of updates: about
   10–50 updates/s with propagation. *Not measured:* low-rate state, such as
   spanning-tree or load-balancer health changes. *Inference, not a measurement:*
   such state is within reach whenever its change rate stays far below that.
   FaVe already treats a FIB this way, through incremental route updates
   (`INCREMENTAL_PLAN.md`). So the control-plane row of §6 stands, with the
   caveat that the rate must be measured for each workload.
2. **Which engines must take the new bits?** *Narrowed:* the thesis is
   NetPlumber-only. In the code, NetPlumber, ad6 and VeriFlow-FR read `related`
   generically, and only APKeep's adapter needs work (§3). *Decided (owner,
   2026-10-14):* E2 runs on NetPlumber with ad6 as sparring partner; the other
   engines follow once the encoding and algorithms are stable (§7).
3. **Is `RELATED` in scope?** *Answered for the thesis:* out of scope (§7.1.7,
   *Limitations*), so FTP and RTP data connections are not analysed, only their
   control channels. *Decided (owner, 2026-10-14):* item 51 takes on both
   halves (§7, E1):
   - helper expectations (FTP-like): the parent connection's acceptance at the
     same device is the local guard; the expected ports come from the payload
     and are wildcarded;
   - ICMP errors about a tracked connection: the connection sits in the
     error's embedded header. First a wildcard over it, which is cheap and
     sound for isolation checks; then embedded-header fields as a measured
     variant, to put a number on the precision bought and the header widening
     paid (thesis §6.3). For IPv6 this half matters more: Packet Too Big is
     needed for path MTU discovery.
4. **Which soundness direction does `<->>` declare?** *Answered:* both. It is
   three checks, and they differ (§4). *Decided (owner, 2026-10-14):* reports
   mark passing `related:1` answer checks as resting on the state
   over-approximation, and an opt-in strict mode reports them as undecided.
   Filed as TODO item 52; independent of this plan, but item 51 drops the mark
   where its encoding makes an answer check exact.
5. **New, from the thesis's scope (§1.8):** the thesis left NAT out on purpose:
   it plays no role for compliance, and IPv6 makes it obsolete. Does that still
   hold, given that `wl_cloud` already models a gateway's DNAT and the raw TUM
   rule set has SNAT? It decides whether E3 is worth doing.

## 9. Literature

The owner's thesis: Lorenz, *Continuously verified Compliance: Achieving and
Maintaining Network Security*, dissertation, 2026 (in this tree as an untracked
PDF). Read for this plan: §1.8, §4.1.2, §6.3, §7.1.5–7.1.7, §7.2, Chapter 9,
Appendix A.14.

Cited from memory, so to verify before anything leans on it:

- Velner, Alpernas, Panda, Rabinovich, Sagiv, Shenker, Shoham, *Some complexity
  results for stateful network verification*, TACAS 2016. Verifying stateful
  networks is undecidable in general.
- Alpernas et al., *Abstract interpretation of stateful networks*, SAS 2018.
  The problem becomes tractable when state is a set, with no packet order and no
  counters, which is the abstraction of §3.
- Panda et al., *Verifying reachability in networks with mutable datapaths*
  (VMN), NSDI 2017.
- Diekmann et al., fffuu (the 2021 paper's [2]): how it treats conntrack states.
