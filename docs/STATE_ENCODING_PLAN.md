# State as virtual header bits: generalizing state shell interweaving

**Status (2026-10-13): RESEARCH, not started.** Filed after an owner discussion of
which device classes FaVe should model next (TODO item 51). Nothing here is built
or measured. §3 is a hypothesis, and §7 is the first experiment that would test it.
Its prerequisite is TODO item 50, which was found while preparing this document.

## 1. The question

Most device classes worth adding to FaVe hold state: NAT gateways, cloud
security groups, load balancers, learning switches. FaVe has two ways to model
state, and neither carries over to them:

- **Snapshots** (`devices/snapshot_packet_filter.py`) feed live state changes
  into the model. They do not scale. The 2021 paper (Lorenz et al., TNSM,
  §I) measured up to 400 new connections per second on a single firewall,
  and the owner's thesis has the full measurements. Snapshots also verify only
  the states observed, not all reachable ones.
- **State shell interweaving** (`iptables/generator.py`, the 2021 paper's §IV)
  scales, but models conntrack alone, with two states.

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
  incremental.

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
appears in 113 of `wl_up`'s rule sets.

## 4. Precision, soundness, and how to recover precision

Each place the conditions in §3 fail costs **precision** for isolation
properties ("A must not reach B"), not soundness:

| Condition fails | Example | Effect |
|---|---|---|
| (c) | asymmetric routing; a device that sees only one direction; tracking that starts mid-path | the device assumes a history it never saw, which causes false alarms. Being exact would need state bits per device. |
| field correlation | masquerade NAT and port translation: the reply must restore *the* original source | HSA rewrites set constants or wildcards and cannot copy one field into another. The reverse rewrite goes to the wildcard set of possible originals. This is exact for 1:1 NAT. The BDD engines might express field equality, which is an open question for each backend. |
| order, counting | `recent --hitcount`, `limit`, `connlimit` | nondeterministic (§3) |

**Required reachability** ("A must reach B", including FPL's stateful
reachability operator) is the opposite case: an over-approximation can hide a
violation. This is already true of today's shell. Each check should state which
direction its abstraction is sound for.

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
  paper's notation. Today's shell must fall out as the two-state special case.
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
    update cost per engine (NetPlumber first; APKeep and NDD need atoms over the
    new bits).
  - Soundness check, on small networks: a brute-force concrete-packet simulation
    with real conntrack semantics, plus the snapshot oracle of §5.
- **E3 — static NAT,** the first state that depends on more than direction.

## 8. Open questions for the owner

1. Where in the thesis are the snapshot measurements? Does the limit apply only
   to per-connection state, or also to low-rate state (the control-plane row in
   §6)?
2. Which engines must support the new bits in E2: NetPlumber only, or the whole
   comparison set?
3. Is `RELATED`'s ICMP-error half in scope? Modeling it needs the ICMP error's
   embedded header, or a wildcard over it.
4. Which soundness direction should FPL's stateful reachability operator
   declare (§4)?

## 9. Literature to check

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
