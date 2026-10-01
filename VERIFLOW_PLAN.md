# VeriFlow as a FaVe Verification Backend — an Independent Implementation

**Status:** V1, V2, V3 and V3b DONE (2026-09-29 to 2026-10-01, §10); V4 next. V5 waits for the larger machine (TODO item 31). D1-D6 resolved (§9); D5's first batch (Q10-Q14) awaits sending.
**Owner:** Claas Lorenz. **Driver:** PhD-thesis future work — a further engine family
beside NetPlumber (HSA), APKeep (atomic predicates, BDD/NDD) and ad6 (SAT/ASP).
Siblings: [`APKEEP_BACKEND.md`](APKEEP_BACKEND.md), [`AD6_PLAN.md`](AD6_PLAN.md),
[`CLOUD_BENCH_PLAN.md`](CLOUD_BENCH_PLAN.md) §2 (the Delta-net workloads).

Name of our implementation: **VeriFlow-FR** (FaVe reimplementation; §9, decision D2). It
is *not* "VeriFlow", and no result from it is to be reported as VeriFlow's.

---

## 1. The decision this plan records

Owner decision, 2026-09-29: **build our own implementation from the literature.**

- The only published implementation of VeriFlow — the UIUC release, Copyright 2012-2013
  The Board of Trustees of the University of Illinois — is under the *VeriFlow Research
  License Agreement*. That licence was granted per requester through a web form that no
  longer exists; we do not hold it. Its §3 treats the software as proprietary and
  confidential, so the copy that survives on GitHub (inside a 2016 student project,
  `xwu64/Network-Monitor-Middleware`, first commit `d31f03c`) is very likely an
  unauthorised redistribution, and holding a copy of it grants nothing.
- Veriflow was commercialised (Veriflow Systems, acquired by VMware in 2019), which is
  one more reason not to lean on the licensor's goodwill.
- **Therefore:** no code from any VeriFlow implementation is copied, and **no
  implementation is added to this repository** — neither the UIUC release nor the
  GPL-3 Python reimplementation `MuLx10/VeriFlow` (§3). That is stricter than the law
  requires for the GPL-3 one (FaVe is itself GPL-3), and deliberately so: keeping our
  reading of the literature independent is what makes the result ours to interpret.

The UIUC release may not be **run** either — the licence grant (§2.1) is the only thing
that would permit use, and we do not hold it. It is therefore **not a test oracle**.

## 2. Sources, and the standing of each

| source | what it is | standing |
|---|---|---|
| Khurshid et al., *VeriFlow*, NSDI'13 | the design paper | primary spec; `2013_Khurshid_et_al_…pdf` in repo root (untracked) |
| Khurshid, *Monitoring and Verifying Network Behavior Using Data-Plane State*, PhD thesis, UIUC 2015 (IDEALS `hdl.handle.net/2142/90066`) | Ch. 3 is VeriFlow, extended | primary spec, **richer than the paper** (§4); `2015_Khurshid_PhD-thesis_…pdf` in repo root (untracked; "Copyright 2015 Ahmed Khurshid", no open licence — cite, do not commit) |
| Horn et al., *Delta-net*, NSDI'17, §5 | describes *Veriflow-RI*, their own reimplementation | interpretation precedent; states that "neither Veriflow's implementation (or its algorithm) nor any of the data sets … are publicly available" |
| Zhang et al., *APKeep*, NSDI'20, §6 | benchmarks "an open-source version of VeriFlow" and *Delta-netMF* | prior measurement: VeriFlow-style EC explosion on ACLs (686 ACL rules → ~15 M ECs) |
| `MuLx10/VeriFlow` (GitHub, GPL-3, 2020) | a small Python reimplementation, unvetted | may be **run** as a black-box oracle; code consulted only under §5's protocol |
| UIUC release (`xwu64/…`, commit `d31f03c`) | the original C++ | **not run and not consulted** (D4, closed) |

Searched for and **not found** (2026-09-29): Veriflow-RI code; Delta-net code (the
`delta-net` GitHub organisation holds only `datasets`; neither author's personal account
has verifier code); Delta-netMF (not in `XJTU-NetVerify/apkeep` on any branch, nor in any
other public XJTU-NetVerify repo). Asking the authors remains open (D5).

sha256 of the two local literature PDFs, so a re-supplied copy is identifiable:
- paper: `081f2754be3c46a51ff63ebf7cd16710e1f0e2560cb35a18c2bc45af7bd3e77d`
- thesis: `e983758cf4156d502dcc1a942cd298fec4ea64ee0544121408404b8061780d9e`

## 3. Contamination record — what has already been seen

A clean-room claim is only as good as the record of what its authors saw. On
2026-09-29, while locating the implementation, Claude cloned the UIUC copy into the
session scratchpad (**never into the repo**) and saw:

- the README (build; "test mode" runs a built-in example; "proxy mode" between NOX and
  switches; and the sentence that the *egress for a header signature is denoted by a
  rule whose next hop is its own location*);
- the file list (a trie and trie-node pair, equivalence class and equivalence range,
  forwarding graph / link / device, network, rule, OpenFlow message parsing, a test
  harness, and support files);
- **two headers in full**: the rule class (per-field value and mask strings, a wildcard
  word, location, next hop, priority, a two-valued rule type) and the main class
  (add/remove rule, get affected ECs, process current hop, traverse forwarding graph,
  verify rule with per-phase timers);
- the licence text, and a diff stat of the students' later changes.

**No `.cpp` body was read.** The clone was deleted the same day at the owner's request.
Of `MuLx10/VeriFlow`, only the top-level file listing was seen.

Consequences, stated so they are applied rather than remembered:
- The API names `GetAffectedEquivalenceClasses` / `GetForwardingGraph` /
  `ProcessCurrentHop` are **published** (paper §4.3, thesis §3.2.3) and may be used.
- Our rule representation is designed from FaVe's own header layout (§6), **not** as
  per-field value/mask strings — that choice is made on its merits (FaVe already has a
  bit-vector layout) and it also keeps us visibly apart from the seen header.
- The "next hop = own location means delivered" convention is recorded as seen-in-code.
  Our delivery semantics come from FaVe's model (sinks are FaVe's `probe`/host nodes),
  so we neither need nor adopt it.

## 4. What the literature specifies

Everything in this section is sourced from the paper (P) or the thesis (T); page
references are to the printed thesis pages.

**4.1 Equivalence class (EC).** A set of packets for which every device takes the same
forwarding action (P §3.1, T p.36). Only ECs that overlap a changed rule are rechecked.

**4.2 The multi-dimensional ternary trie** (P §3.1, T pp.36-39, Fig. 3.2/3.3,
Alg. 1/2). One level per header bit; each node has three children — 0, 1, `*`. One
sub-trie per header field, stacked: the next field's sub-trie hangs from the leaves of
the previous one. A root-to-bottom-leaf path is a rule's match; leaves store the
(device, rule) pairs. *Insert* (Alg. 1): follow the rule's bits, `*` down the wildcard
branch. *Find overlapping* (Alg. 2): breadth-first per bit; a concrete bit visits its own
branch **and** `*`; a `*` bit visits all three.

**4.3 EC computation** (T p.37). From the overlapping rules, per field compute the
disjoint ranges that no rule splits; an EC is one choice of range per field (a
cartesian product). **Explicitly not minimal** ("ECs 2 and 4 … could have been
combined").

**4.4 Forwarding graph** (P §3.2, T p.40). Per EC: node = (EC, device), edge X→Y =
X's table forwards the EC to Y. Built by a **second** trie traversal, because rules that
did not help *form* the ECs (e.g. a `0.0.0.0/0` under a new `/8`) still decide
forwarding by priority.

**4.5 Packet transformations — THESIS ONLY** (T §3.1.3, pp.40-41). Not in the NSDI
paper. The paper's first version assumed a header never changes; the thesis version
handles rewrites (the text names SET_DL_DST, SET_DL_VLAN, NAT and MPLS):
1. at the device of the new rule, find the *local* ECs the rule affects;
2. per local EC take the **highest-priority** rule; apply its rewrite actions to the
   EC's field values;
3. follow the output action to the next device and traverse the trie **again** with the
   *transformed* EC, yielding that device's overlapping local ECs;
4. repeat until a device consumes the packet set, or a device is revisited (a loop).

The graph is thus built incrementally, device by device, instead of from one
network-wide EC set. Reported cost: mean 0.38 ms → 0.59 ms per update (+55 %) on the
Route Views trace (T p.48, Fig. 3.5). The thesis also says (T p.38) that Alg. 2 is
iterated "until no additional affected rules are found" when a rewrite sends a packet to
another table on the same switch.

**4.6 The 4 + 10 field optimisation** (P §4.2, T §3.2.2). Of OpenFlow 1.1's 14 match
fields, 10 allow only exact-or-ANY; only the 4 arbitrary-wildcard fields (DL_SRC,
DL_DST, NW_SRC, NW_DST) are trie dimensions. The other 10 are split by a linear scan
over the rules *at the new rule's device*; finer rules met at *other* devices during
traversal are handled by carrying an **excluded packet set** per forwarding action, so a
query's answer is "primary set minus excluded set". **In scope (D6):** generalised to
FaVe's fields and built as phase V3b; every published VeriFlow number was measured with it
on (T p.36 fn.), and neither text measures it off.

**4.7 Queries** (P §3.3, T §3.1.4, Ch. 4). An invariant is a function over one EC's
forwarding graph. Chapter 4 lists ten: basic reachability (DFS, "does the current
device consume the packet?"), loop-freeness, black holes (explicit ACL drop, missing
final permit, missing default route — **drops are thus ACL rules or the absence of a
rule**), consistency of replicated devices, VLAN isolation, loose and strict path
routing (e.g. "Internet traffic always visits the firewall first"), path-length bound,
overlapping rules, next-hop change.

**4.8 Measured sensitivities worth reproducing** (T §3.3):
- **Trie field order matters by an order of magnitude**: NW_DST ahead of NW_SRC cut
  ~1 ms to ~0.1 ms (Table 3.1, 12 orderings). Field order is therefore a
  measurement-affecting choice and must be stamped (§8).
- More match fields → more ECs → slower; the number of filters matters little (Fig. 3.6).
- Link failure: 254 of 381 links touched > 1,000 ECs; mean 1.15 s (T p.50).

**4.9 A typo to not inherit.** Both paper and thesis list the third EC of the worked
example as "11.2.255.255 to 11.255.255.255"; the correct lower bound is `11.2.0.0`. Our
unit test for that example asserts the correct value and cites this line.

## 5. The consultation protocol (clean room)

1. **The spec is written from §2's literature only**, in §4 and §7 of this file.
2. **Every ambiguity becomes a numbered question** in §7 before anyone resolves it.
3. **Resolution order:** (a) re-read the literature; (b) decide from FaVe's own
   semantics and record the reasoning — *most questions should end here*, because we
   are building a FaVe backend, not a VeriFlow replica; (c) run `MuLx10/VeriFlow` as a
   black box on a crafted input and record the observed behaviour; (d) only then,
   consult `MuLx10/VeriFlow`'s *source*; (e) ask the authors (D5); (f) failing all of
   these, **decide it as our own design** and enter it in TODO item 31's accommodation
   registry. Where the literature is silent, the choice is ours, and it is declared.
4. **Source consultation (step d) is done by a separate subagent** that is given the
   question, reads the code outside the repo, and answers **in prose, describing
   behaviour only** — no code, no identifiers beyond those the literature already
   publishes, no data-structure layouts. The answer is appended to §7 verbatim with the
   date and which implementation was read. The implementing agent never has the code
   open.
5. **The UIUC source is never consulted** (D4, closed 2026-09-29), for no question and by
   no one, subagents included. The §3 record of what was already seen stands.
6. Nothing from either implementation — files, snippets, test vectors, topology files —
   enters the repo or `fave/bench/`.

## 6. Architecture

*As built in V1 (2026-09-29):*
- `veriflow_fr/src/veriflow.{h,cc}`: the layout, prefix intervals, the ternary trie,
  the network, ECs and forwarding graphs.
- `veriflow_fr/src/queries.{h,cc}`: walks, the Ch. 4 invariants, bulk `deliveries`
  and `link_failure`.
- `veriflow_fr/test/`: CppUnit, L1-L6, L10, the oracle.
- `veriflow_fr/python/`: the pybind11 binding.
- `fave/veriflow/translate.py`: the pure-Python IR translation.
- `fave/veriflow/adapter.py`: the engine half.

Registering `FAVE_BACKEND=veriflow` is V4's; V1 is driven in-process only. The sketch
below was the proposal.

Placement mirrors the existing engines: an engine directory at the repo root, a thin
adapter under `fave/`, selection through the existing backend switch.

```
veriflow_fr/                C++17 engine, standard library only (D3); built like libnetplumber
  field_layout             FaVe header layout -> ordered trie dimensions (order is a stamp)
  ternary_trie             §4.2: insert / remove / find-overlapping (Alg. 1/2)
  rule_store               (device, rule, priority, match, actions) — our own representation
  ec                       §4.3: per-field disjoint ranges, cartesian product (non-minimal)
  forwarding_graph         §4.4 + §4.5: device-by-device construction, rewrites applied
  queries                  reachability (FaVe checks), loop, black hole — pluggable
  python binding           pybind11, as libnetplumber already does
fave/veriflow/adapter.py   FaVe model -> rules; FaVe checks -> queries; FAVE_BACKEND=veriflow
```

Design points that follow from FaVe rather than from VeriFlow, each to be confirmed:

- **Matches come from FaVe's header layout.** FaVe already models headers as bit
  vectors; a trie dimension is a field of that layout. Non-prefix ranges (L4 port
  ranges) are expanded into prefixes, as APKeep did for VeriFlow — the expansion factor
  is a reported metric, not a hidden cost.
- **Ports, not just devices.** VeriFlow's graph node is (EC, device) and IN_PORT is one
  of the exact/ANY fields. FaVe's semantics are per-port (the §2.8 ingress-demultiplexing
  lesson in `CLOUD_BENCH_PLAN.md`: APKeep's translation silently dropped `in_ports`).
  Either nodes become (EC, device, port) or IN_PORT is a matched field on every table —
  Q7 decides, and the choice is stamped.
- **Drops are rules.** An ACL deny is a highest-priority rule with a drop action; "no
  matching rule" is a drop too (§4.7).
- **Two modes, both measured, never mixed:** *incremental* (replay the model as a
  stream of insertions, verifying per insert — VeriFlow's own regime, and the one
  Delta-net measured on the airtel traces) and *bulk* (load everything, then answer
  FaVe's check set once — FaVe's regime). They are different measurements (compare
  TODO 0a's cold/warm lesson) and carry a stamp.

## 7. Open questions (the ambiguity register)

Each entry: the question, where the literature leaves it open, and the resolution path.
Resolutions are appended below the question with a date.

- **Q1 — EC ranges over which rule set?** T p.37 computes disjoint ranges from "the
  rules that intersect the new rule". Network-wide, or per device? Network-wide is the
  reading consistent with §4.3's non-minimality example. Path: literature, then FaVe
  differential.
  *Resolved 2026-09-29 (literature):* **network-wide.** "We consider overlapping rules at all
  the devices because inserting a rule at a switch can alter the entire path" (T p.38);
  "look for network-wide overlapping rules" (T p.45). The trie is network-wide too: its
  leaves store (device, rule) pairs. The differential will confirm it.
- **Q2 — Rules that split an EC at another device.** Without §4.6's optimisation, can a
  rule at device B split an EC formed from the rules overlapping a new rule at device
  A? If it overlaps the EC it overlaps the new rule and was already included — unless a
  *rewrite* moved the EC (§4.5), which is exactly why the thesis goes device by device.
  Path: derive, then confirm on a crafted rewrite example.
  *Resolved 2026-09-29 (derived):* **not without rewrites; with them, ECs are re-sliced at
  every device.** A rule that splits an EC overlaps it, hence overlaps the new rule,
  hence was in Q1's network-wide lookup. A rewrite breaks the argument, because the
  transformed set may overlap rules the original did not; hence §3.1.3's device-by-device
  traversal. Consequence (§10): the only rewrite-free workloads are the airtel pair.
- **Q3 — Rewrites that split.** After a rewrite, the transformed EC may be split by the
  next device's rules into several local ECs; does the graph fork per local EC, and are
  the forks' packet sets tracked back to the original EC? T §3.1.3 implies forking.
  Path: derive from FaVe's semantics.
- **Q4 — Revisit ≠ loop under rewrites.** T §3.1.3 stops at a device "already visited
  for a previously encountered packet set (which also indicates presence of a routing
  loop)". With rewrites, revisiting a device with a *different* header is not a loop.
  Path: FaVe's loop semantics decide; record the divergence if we differ.
  *Resolved 2026-09-30 (owner):* **the thesis's rule, `vf_revisit=state`, by default.**
  A walk stops at a (table, arrival, packet set) it has already reached. NetPlumber's
  rule, `vf_revisit=path`, where a path revisiting a table stops whatever the header,
  is kept as a stamped option for parity runs.
  - **The divergence, recorded as the path asked.** FaVe's own loop semantics, which
    are NetPlumber's and unchanged from upstream, lose deliveries that legitimately
    pass a table twice. Measured on a router on a stick
    (`fave/test/test_revisit_router_on_a_stick.py`): host A on VLAN 10 crosses one
    switch table twice to reach host B on VLAN 20.
    - VeriFlow-FR `state` and ad6: reached. That is the truth.
    - VeriFlow-FR `path` and NetPlumber: not reached.
    - The genuine-loop control is not reached by all of these.

    APKeep reaches B in both networks, the loop included, with either engine and
    either VLAN mode: a separate over-approximation. Both defects are TODO item 33.
  - **On the suite:** no verdict differs between the rules on the six workloads that
    finish (§10, V3), and `state` never does more work (up to 9x less). The thesis's
    rule is also what keeps VeriFlow-FR independent of NetPlumber, instead of agreeing
    with it by inheriting its limitation.
- **Q5 — Deletion.** Paper and thesis state deletes are handled (all five OpenFlow
  FLOW_MOD types) but describe only insertion. Presumed symmetric: find ECs overlapping
  the removed rule, remove, rebuild their graphs. Path: derive.
  *Resolved 2026-09-29 (literature + derived):* **symmetric to insertion.** The paper handles
  all five FLOW_MOD types, OFPFC_DELETE(_STRICT) among them (its NOX-integration
  passage), and describes only
  insertion. The affected ECs are those inside the removed rule's range; the rule
  leaves the trie; their graphs are rebuilt without it. Built and tested in V1 and
  measured only on TODO item 31's incremental axis: FaVe's own deletion path is still
  unfinished (`aggregator_service.py`: "TODO: fix deletion").
- **Q6 — Is §4.6 in or out?** Implementing the 4+10 optimisation and excluded sets is a
  large share of the complexity and is tied to OpenFlow 1.1's field classes, which are
  not FaVe's. Proposal: V1-V3 build the plain multi-dimensional trie over *all* used
  fields; §4.6 is an optional, stamped variant later. Path: owner (D6).
  *Resolved 2026-09-29 (D6):* in scope, as a **required, staged** variant, not an optional
  one. V1-V3 are plain; V3b adds §4.6, with plain VeriFlow-FR as its verdict oracle. §9.
- **Q7 — Port semantics.** See §6. Path: FaVe semantics; stamped.
  *Resolved 2026-09-29 (FaVe semantics):* **IN_PORT is a matched field**, one of OpenFlow's
  14 and exact-or-ANY, hence a scan field. Its value at each hop is the port the edge
  arrives on (with Q20, a port of a FaVe table). Not to be confused with FaVe's `in_port`
  *header* field, which is metadata bits FaVe itself writes at pre-routing (§9, finding
  5); a test pins the difference. A regression test pins that no rule's `in_ports` is
  dropped, the `CLOUD_BENCH_PLAN.md` §2.8 lesson. Stamp: `vf_ports=field`.
- **Q8 — Delivery.** When does a device "consume" a packet? FaVe answers this with its
  own sink nodes; no consultation needed. Recorded because §3 notes a seen-in-code
  convention we are deliberately *not* using.
  *Resolved 2026-09-29 (FaVe semantics):* a packet is **consumed** when it reaches a probe
  node's port and passes the probe's filter. It is **dropped** by an explicit drop rule,
  when no rule of a table matches (as in NetPlumber, where a flow continues only through
  rules it matches), or at an unwired port. These are the thesis's three black-hole
  causes (Ch. 4, §4.3) in FaVe's terms.
- **Q9 — Priority ties** between overlapping rules of equal priority at one device:
  OpenFlow leaves it undefined. FaVe's table semantics (`TABLE_SEMANTICS_PLAN.md`)
  make every table first-match-wins in document order unless declared otherwise, so
  document position is the tie-break and the adapter encodes it into priority.
  *Resolved 2026-09-29 (FaVe semantics):* as stated. In a declared LPM table, priority is the
  prefix length, and a tie cannot matter: `validate_lpm_rules` refuses two rules that
  share a prefix and differ in action.
- **Q15 — Are ECs computed only within the new rule's range?** L1 and L4 both imply it:
  12.1/16 is not considered, and r1's part outside r4 is not affected. Path: literature
  (step a), confirmed by L1/L4 and the oracle.
  *Resolved 2026-09-29 (literature):* **yes.** Per field, the disjoint ranges come from the
  network-wide overlapping rules (Q1) clipped to the new rule's range, and the ECs are
  their product. In T p.36's example all three ECs lie inside 11/8, and "the new rule
  will not affect packets outside the range". The oracle checks that the ECs partition
  the new rule's range exactly.

**Raised by the V0 survey (§9).** Each is decided from FaVe's semantics (step b), not
from the literature, and each is entered as an adapter encoding or extension in TODO
item 31's registry.

- **Q16 — Rules with several ingress ports.** Expand to one rule per port (an adapter
  encoding, factor stamped: 1.69× on `wl_stanford`), or make IN_PORT a set-valued scan
  field (an extension)? Expansion is the literature-faithful default.
  *Resolved 2026-09-29 (owner):* **expand**, one rule per ingress port. It is an adapter
  encoding, and its factor is stamped (`vf_inport_expansion`: 1.69 on `wl_stanford`, 1.06 on
  the airtel pair).
- **Q17 — Negated check conditions.** Expand into non-negated vectors as NetPlumber does
  (`_expand_negations`), applied to the query's packet set rather than to rules.
  Refuse on a must-reach check, as NetPlumber does, for the same reason. All 8 such
  checks in the suite (`wl_cloud`) are must-not-reach, so the refusal costs nothing
  today.
  *Resolved 2026-09-29:* as stated. An adapter encoding, applied to Q21's query set.
- **Q18 — ICMPv6 type and code in one field.** FaVe packs them into 16 bits, so "type 1,
  any code" is a prefix. OpenFlow keeps two exact-or-ANY fields. Split the field in
  VeriFlow-FR's layout (it moves to scan), or keep FaVe's layout (trie)? Either way it
  is stamped.
  *Resolved 2026-09-29 (owner):* **keep FaVe's layout.** Every engine sees the same 16-bit
  field, and splitting it for VeriFlow-FR alone would make the inputs asymmetric. It
  matters only to V3b, and only on `wl_up`. A split layout remains a possible stamped
  ablation, if `wl_up`'s V3b numbers show the extra trie dimension costs something.
- **Q19 — Clear-to-ANY rewrites.** Needed for FaVe's metadata (finding 4). As an EC
  transformation it widens the field to its full range; that is simple, but it is an
  extension beyond the thesis's actions, and declared so.
  *Resolved 2026-09-29:* as stated. A declared extension; after the clear, the EC is re-sliced
  as in Q2.
- **Q20 — Device or table as the graph node.** FaVe's unit is a table wired inside a
  device. Proposal: a VeriFlow-FR node is a FaVe table, and FaVe's wiring gives the
  edges. The thesis's own note on chaining tables within one switch (T p.38) supports
  it. Stamped as an adapter encoding.
  *Resolved 2026-09-29:* **a node is a FaVe table**; edges come from FaVe's wiring (within a
  device: a router is pre-routing → ACL-in → routing → ACL-out → post-routing) and its
  links. Stamp `vf_node=table`. It also aligns loop semantics with NetPlumber's default,
  "a flow revisits a table" (`net_plumber/FAVE_CHANGES.md` §6), which settles half of
  Q4 in advance.
- **Q21 — A FaVe check as a VeriFlow query (bulk mode).** VeriFlow answers for "the ECs
  a new rule affects"; FaVe's regime loads everything and then asks checks.
  *Resolved 2026-09-29 (owner):* **the check's packet set stands in for the new rule.**
  That set is the source's header space intersected with the condition (after Q17). The
  ECs inside it come from the rules overlapping it network-wide (Q1, Q15); their graphs
  are built, and traversed from the source. This is the pattern of Delta-net's
  link-failure query, "the ECs affected by an event". It is our design, and declared as
  such.

**Raised by V2's census.**

- **Q22 — Bulk checks against the explosion.** Q21 slices a check's packet set by every
  overlapping rule network-wide (Q1, Q15). A source that injects the whole header space
  therefore faces the whole-space product: 5.3e10 ECs on `wl_stanford`, 2.8e17 on
  `wl_up` (§10, V2). Enumerated, that cannot finish. The thesis's rewrite algorithm
  (§4.5, T §3.1.3) already slices *locally*: at each device a packet set reaches, only
  that device's rules split it. That bounds each hop's product by one device's rules,
  not the network's. Path: the literature says this is how VeriFlow handles rewrites,
  and V3 needs it anyway; whether bulk mode uses it for every check, rewrites or not,
  is a design choice (owner). If it does not, the whole-space workloads are reported
  as "did not finish within the limit" (TODO item 31's result cell), not approximated.

  *Resolved 2026-09-29 (owner):* **bulk checks slice locally, device by device**,
  stamped `vf_slicing=device`.

  **The literature.** This is the thesis's final algorithm, not our invention: "we
  can no longer compute network-wide equivalence classes by traversing our trie
  structure just once. We need to traverse the trie multiple times on a
  device-by-device basis", slicing "overlapping local equivalence classes at the next
  hop device" (T pp.40-41). The per-update figures were re-measured with it (T p.48).
  The paper's network-wide algorithm is the earlier version. It stays as
  `vf_slicing=network` for the rewrite-free airtel pair, so the calibration keeps
  measuring what Veriflow-RI measured; where both apply, both are reported.

  **Measured, 2026-09-29.** Whole-space product, network-wide, against the largest
  single-table product, local:

  | workload | network-wide | local |
  |---|---:|---:|
  | `wl_ifi` | 2.9e6 | 4.1e3 |
  | `wl_i2` | 5.8e6 | 1.5e4 |
  | `wl_cloud` | 8.3e7 | 2.0e4 |
  | `wl_stanford` | 5.3e10 | 8.1e7 (`out.yoza_rtr`, 1,614 rules) |
  | `wl_up` | 2.8e17 | 2.6e11 (`pgf` forward filter, 2,042 rules) |
  | `wl_tum` | 5.1e13 | 2.9e13 (its one firewall table, 5,108 rules) |

  These are upper bounds over the whole space. A check's arriving set is narrower, but
  for the two firewalls an estimated 1e9-1e10 remains.

  *Superseded in part, 2026-10-01 (V3b):* the single-table explosion below was PLAIN
  slicing's. With §4.6's scan fields, `wl_up` and `wl_tum` finish and agree with
  NetPlumber (§10, V3b). Kept as written, as the plain ablation's record.

  **What it rescues, and what it does not.** Local slicing makes `wl_ifi`, `wl_i2` and
  `wl_cloud` small and `wl_stanford` heavy but plausible. It cannot help where the
  explosion sits inside ONE table (`wl_tum`, `wl_up`); §4.6's scan still splits by the
  scanned fields, so V3b does not help there either. That is a genuine limitation of
  range-based ECs, the one APKeep reports for Delta-netMF and VeriFlow ("do not run
  to completion"). For the comparison it is a **finding**, of the same class as
  BDD-APKeep's VLAN cost. It is never approximated away; merging ECs across ranges, in
  particular, would be APKeep's idea, not VeriFlow's.

  **How it is reported:**
  - **Did not finish within the declared limit** is the result cell (TODO item 31).
    The limit is one for every engine and is **a suite-wide decision, recorded in item
    31**, not a VeriFlow-FR setting.
  - **Predicted ECs, as a diagnostic, never a verdict:** `ec_count` is cheap, so each
    check stamps the predicted EC count at each table before enumerating. A
    did-not-finish row says why, e.g. "2.6e11 ECs at `pgf.forward_filter`", not just
    that time ran out.
  - **Correctness:** the oracle gains a per-table uniformity check for local slicing,
    and the differential against NetPlumber covers every workload that finishes.

  **The cost, stated in the write-up.** The "forwarding graph per EC" becomes a tree of
  packet sets per check, much like NetPlumber's flows; the Ch. 4 invariants still run
  on the walks. VeriFlow-FR thereby moves structurally closer to header-space
  propagation. That is a consequence of the thesis's algorithm, and is said so.

**For the Delta-net authors (D5, group 1).** These are drafted now because they gate
V1's exit (§8). Each is about what *their* experiment did, which only they can say. They
are phrased in the paper's terms only (Delta-net §4.3.2, Table 4).

- **Q10 — Which data plane is the Airtel snapshot?** The paper says it was extracted "from
  ONOS", with 38,100 rules and 158 queries. We identify it with the final state of
  `airtel1-only-inserts.csv`, but by counts only: both airtel traces replay to 38,100
  rules, and only airtel1 has 158 directed edges (`bench/deltanet/TRACES.md`). Is that
  the same data plane? Path: authors.
- **Q11 — What does one query compute?** The paper reads the question as "construct
  forwarding graphs for all packet equivalence classes that are affected by a link
  failure". Three things follow from that. Is a query one directed edge, which our count
  of 158 suggests? Is each failure independent, with the link restored before the next?
  Does Veriflow-RI's column include a property check, such as the forwarding-loop check
  that Table 4's last column adds for Delta-net, or graph construction only? Path:
  authors.
- **Q12 — What is timed?** Per query, is the snapshot already loaded, with only the
  failure's graph work timed? Is the reported figure the plain mean over the 158? Which
  compiler and optimisation flags were used? Path: authors.
- **Q13 — What did Veriflow-RI optimise?** The paper says Veriflow-RI "optimize[s] the
  computation of equivalence classes and construction of forwarding graphs" in ways
  "not … possible in the original … with its ternary trie", and "may therefore be faster
  than Veriflow". Which optimisations were they? The answer decides how a gap between
  VeriFlow-FR's ternary trie and 4.5 ms should be read. Path: authors.
- **Q14 — Can Veriflow-RI or Delta-net be run by us?** As a binary or as code to run, and
  under what terms. Running Veriflow-RI on our machine would turn the gate from a
  comparison across machines into a direct one. If code is offered, D5's rule on code
  applies. Path: authors.

## 8. Correctness and measurement gates

**Correctness** needs no VeriFlow oracle: FaVe already has three engines that agree.
- **Differential:** every workload VeriFlow-FR runs is compared pair by pair against
  NetPlumber, APKeep (NDD) and, where it runs, ad6 (`test_backend_differential.py`).
- **LPM guard** (`CLOUD_BENCH_PLAN.md` §3): each FIB workload must show its evidence can
  see priority — invert the order, the verdict must change.
- **Tests first, from the literature:** the catalogue at the end of this section (L1-L10).
- **Optional black-box run** of `MuLx10/VeriFlow` on small forwarding-only inputs,
  recorded as behaviour, never vendored.

**Calibration — the gate no other engine in the suite needs.** Every other engine is
its authors' own code, which we have patched; VeriFlow-FR is our reading, and a naive
reading is the easiest straw man in the comparison. The defence is a published number
on identical data. Delta-net §4.3.2 (Table 4) answers 158 "what if a link fails?"
queries on the 38,100-rule Airtel data-plane snapshot — which *is* `wl_airtel1`'s
input (`airtel1-only-inserts.csv`, 158 edges in `bench/deltanet/TRACES.md`) — and
reports an average query time of **4.5 ms for Veriflow-RI** (0.04 ms for Delta-net),
on a 3.47 GHz Xeon, single-threaded. VeriFlow-FR must reproduce that experiment on
`wl_airtel1` — for each link, build the forwarding graphs of every EC the failure
affects — and land within an order of magnitude of 4.5 ms, with the hardware difference
stated. That is a V1 exit gate. It calibrates against Veriflow-RI, not VeriFlow: the
original's per-update figures (0.38 ms, 0.59 ms with rewrites) come from a Route Views
workload that is not available, and Delta-net's per-update tables (Table 3) use the full
traces, which are out of scope (`CLOUD_BENCH_PLAN.md` §2.14).

**Result, 2026-09-29: the gate passes, at about 2.2× Veriflow-RI.**

- **Harness:** `fave/bench/veriflow_calibration.py`, commit `0e297ef6`, clean tree.
- **The model matches Delta-net's graph exactly:** Delta-net's graph over FaVe's
  wl_airtel1 model (`veriflow.translate.node_edges`) has **68 nodes and 158 edges**, the
  paper's node and query counts. That confirms the snapshot identification (Q10) from
  the model's side as well as from the trace's. wl_airtel2 has 155 edges.
- **Stopping rule, declared beforehand:** 1 cold pass, then 5 warm passes over all 158
  edges.

| run | warm mean | median | max | ratio to 4.5 ms |
|---|---:|---:|---:|---:|
| 1 | 9.43 ms | 6.10 ms | 44.9 ms | 2.10× |
| 2 | 10.42 ms | 6.41 ms | 85.6 ms | 2.32× |

- **Per query:** 241 affected ECs and as many graphs built, on average (at most 1,303;
  none empty).
- **Timed:** affected ECs plus their forwarding graphs, inside the engine; no property
  check.
- **Hardware:** Intel Core i5-1135G7 @ 2.40 GHz (a 2020 laptop part with turbo; the
  container exposes no governor, so about 10% run-to-run spread) against DN's
  3.47 GHz Xeon. g++ 13.3, -O3, one thread.

**Reading it.** VeriFlow-FR is within the gate's order of magnitude, and slower than
Veriflow-RI, which is the direction Delta-net predicts for a ternary trie ("may
therefore be faster than Veriflow", DN §5). The comparison is across machines. A newer
core per clock probably flatters us, so the algorithmic gap may be somewhat above 2.2×.
The authors' answers to Q11-Q13 (what one query computes, what is timed, what
Veriflow-RI optimised) will sharpen this, and Q14, running Veriflow-RI here, would
settle it.

**Measurement stamps** (TODO 0a: *every measurement-affecting choice is a stamped
result field*): trie field order; `vf_slicing` (Q22); predicted ECs per table (Q22,
diagnostic); mode (incremental / bulk); field classification `vf_fields` (D6); port
semantics (Q7); port-range expansion factor; EC count per update (VeriFlow's own
headline metric); compiler, standard and flags (D3); thread count (1, D3); provenance `reimpl-literature` with the
engine commit (TODO item 31's provenance column, shared by every backend). **A VeriFlow-FR number is reported as VeriFlow-FR's**,
beside a sentence on what it interprets — as Delta-net did for Veriflow-RI.

### Test-first, from the literature (owner, 2026-09-29)

The owner's preference: **test-first**. Beyond tests aimed at individual functions, the
literature's own worked examples become tests. These pin *published* behaviour, where
function-level tests alone only show that the code agrees with itself.

**The catalogue.** A source marked *derived* has no worked example; the test follows
from the text's definition or steps, and says so.

| ID | Source | Test | Phase |
|---|---|---|---|
| L1 | T p.36 | Existing 11.1.0.0/16 and 12.1.0.0/16; insert 11.0.0.0/8. The overlapping set is {11/8, 11.1/16}; 12.1/16 is not considered. **3 ECs:** 11.0.0.0-11.0.255.255, 11.1.0.0-11.1.255.255, **11.2.0.0**-11.255.255.255. A *deviation test*: it pins §4.9's correction of the printed "11.2.255.255". | V1 |
| L2 | T Fig. 3.2, p.37-38 | Three nested rules on one field (A ⊂ B ⊂ C) give **5** range ECs, and ECs 2 and 4 forward identically. Pins the documented non-minimality: 5, not the minimal 3. | V1 |
| L3 | T p.40 | Existing 0.0.0.0/0; insert 10.0.0.0/8. The /0 adds no EC boundary (1 EC), yet decides forwarding when its priority is higher. Two priority variants. Tests the second trie traversal (§4.4). | V1 |
| L4 | Delta-net §2.1, Fig. 1 | Four switches: r1 s1→s2, r2 s2→s3, r3 s3→s4; insert r4 s1→s4 above r1. **3 ECs** inside r4's range; G1 = {s1→s4}, G2 = G1 + {s2→s3}, G3 = G2 + {s3→s4}; **no graph contains s1→s2**; no loop. The figure is schematic, so our concrete prefixes are a recorded choice: r1 = [0,16), r4 = [8,16), r2 = [12,16), r3 = [14,16) on a narrow field. This is a second group's reading of VeriFlow, which makes it doubly valuable. | V1 |
| L5 | Delta-net §2.1 | 0.0.0.10/31 is the half-open interval [10:12) = {10, 11}. Prefix to interval. | V1 |
| L6 | T Alg. 1/2, p.38-39 | Insert follows the rule's bits, `*` down the wildcard branch. Find-overlapping: a concrete bit visits its own branch and `*`; a `*` bit visits all three. | V1 |
| L7 | T p.37, *derived* | An EC is one choice of range per field (a cartesian product): a two-field case gives the product of the per-field range counts. | V2 |
| L8 | T §3.1.3, *derived* | The four rewrite steps (§4.5): a rewrite at the new rule's device transforms the EC; the next device is traversed with the transformed EC; the walk ends at a consuming device or on a revisit. Q3 and Q4 become tests as they are resolved. | V3 |
| L9 | T §3.2.2, *derived* | A finer, higher-priority rule at another device serves part of a packet set. It becomes an exclusion, and the query's answer is primary minus excluded. | V3b |
| L10 | T Ch. 4 (+ §3.2.3) | One small hand-built network per invariant, ten in all (§4.7). Black holes get all three causes (explicit ACL drop, missing final permit, missing default route). Strict path gets the thesis's example: packets from the Internet always visit the firewall first. Each query lands in the phase that first supports its features. | V1-V3 |

The Table 4 calibration is a gate, not a test; it stays above.

**The rules:**

1. **Red before code.** Every phase from V1 opens by writing its L tests and its
   per-function unit tests, and seeing them fail.
2. **Each test cites its source** (page and figure, or *derived*) and gives the
   derivation of its expected value in a comment. Tests that pin a deliberate deviation
   from the literature are named as such: L1's typo, Q4's revisit-is-not-a-loop, Q9's
   document-order tie-break.
3. **Hand-derived expectations are checked by the oracle too.** The brute-force
   concrete-packet oracle (D3, condition 5) enumerates every packet at small header
   widths. It checks that each EC is action-uniform at every device, which turns the
   definition on T p.36 into a test, and that the ECs partition the new rule's range. A
   mistaken derivation is then caught, instead of being coded towards.
4. **Four layers:** literature examples (L); per-function unit tests; oracle and property
   tests; the FaVe differential above.
5. **Framework: CppUnit, as NetPlumber.** D3's standard-library-only rule binds the timed
   engine, not the test code. The runner joins the `integration` tier, as
   `net_plumber --test` does.

## 9. Decisions

### D1 — RESOLVED 2026-09-29: VeriFlow represents a family in a unified comparison

Owner framing, 2026-09-29: the work's main contribution is **the unification of the
benchmarks through FaVe and a fair comparison of the different verification tools on a
broad set of workloads** — FaVe's own and the literature's. The owner's thesis measured
NetPlumber only, on `wl_tum` only, against firewall tools only (fffuu, an
iptables-capable SymNet); the backends and workloads added since are closing that gap,
and have already produced findings (NetPlumber is robust at scale; update-optimised
tools can be challenged end to end, e.g. APKeep-BDD with VLANs not baked into the
topology; ad6 is feasible within limits).

So VeriFlow-FR needs **no research question of its own**. It is the suite's representative
of **on-demand EC slicing** — the one family that keeps no packet-space partition
between updates, against NetPlumber's rule graph and APKeep's persistent minimal
partition. What follows from that:

- **All workloads, not a tier.** VeriFlow-FR is run on the whole suite. Where it cannot
  run a workload as given, the cell carries a **declared accommodation** (below), not
  a gap.
- **Rewrites (§4.5, V3) are required.** They are part of VeriFlow as the thesis
  specifies it. Without them VeriFlow-FR alone would have holes in the VLAN and NAT rows,
  which would read as VeriFlow's weakness when it is our implementation gap.
- **Both regimes.** VeriFlow is update-optimised; judging it on from-zero time only
  would measure it on a regime it never claimed. The incremental axis is a suite-level
  item (TODO item 31), because fairness to APKeep needs it just as much.
- **Calibration against Veriflow-RI** is a V1 exit gate (§8).

### The accommodation rule (owner, 2026-09-29)

Most tools support far fewer header fields than real networks use — the 5-tuple, or
IPv4 forwarding only (Delta-net). To measure a tool at all we either **implement a
feature**, declaring what and how, or **run a preprocessed workload**, declared as a
tweak of the workload and never presented as a trait of the tool. The suite-wide
registry and naming live in TODO item 31; for VeriFlow-FR:

- **"Native" means as specified in the paper and thesis:** OpenFlow 1.1's 14 match
  fields (incl. DL_VLAN and MPLS), priorities, drops, the §4.5 rewrites, the Ch. 4
  queries. Anything beyond — IPv6, FaVe fields OpenFlow 1.1 lacks, per-port semantics
  if Q7 resolves that way — is a **declared extension**, even though the whole tool
  is ours.
- **Adapter encodings are declared too,** with their cost: port range to prefix
  expansion (factor reported), LPM to priority, ingress demultiplexing.
- **Whose extension:** prefer the literature's approach for VeriFlow (e.g. APKeep's
  prefix expansion) over our own design, and say which was used.

### D2 — RESOLVED 2026-09-29: the name is VeriFlow-FR (owner's call)

**VeriFlow-FR** — "FaVe reimplementation". The name must say that this is not the
authors' code, and it must not collide with Delta-net's reimplementation, which its
authors call **Veriflow-RI** (the owner's first choice, hence taken); both appear side by
side in the §8 calibration gate. Spelling follows the original: the paper and the thesis
write "VeriFlow" throughout; Delta-net writes "Veriflow", and its reimplementation is
quoted as spelled there. Code identifiers: `veriflow_fr/` (engine), `fave/veriflow/`
(adapter), `FAVE_BACKEND=veriflow`. The placeholder "VeriFlow-FR" was dropped because FaVe
is the harness every backend runs in, not one of them.

### D3 — RESOLVED 2026-09-29: C++17, under five conditions (owner's call)

**Why C++.** The deciding ground is fairness, not convenience:

- **The calibration gate (§8) needs it.** Veriflow-RI and Delta-net are C++14,
  single-threaded, using only the standard library (Delta-net, *Implementation*: "around 4,000 lines of
  code"). VeriFlow exposes its query API in C++. A Python VeriFlow-FR would lose one to
  two orders of magnitude before the algorithm counts. It would fail the gate, or pass
  only after the gap was argued away, which is the straw man §8 exists to rule out.
- **Symmetric overhead.** `APKEEP_BACKEND.md` §6 measures from-zero time with
  integration overhead low and equal across backends. NetPlumber runs in-process through
  `libnetplumber`, APKeep through JPype with a warm JVM. A C++ engine behind pybind11
  fits that directly; Java would bring APKeep's warm-up confound to a tool that never had
  it.
- **Rejected:** Python, except as a test oracle (below). Java, for the reason above.
  Rust is equal on speed and better on memory safety, but it would add a toolchain the
  suite does not use, and "Rust versus the authors' C++" is one more difference a
  reviewer would have to discount.

**The conditions.** The language alone does not make the comparison fair:

1. **Standard library only**, as Delta-net did. No third-party data structures, so there
   is no hidden fast library and no licence to track, and the clean room (§5) has a
   short boundary. The pybind11 binding is the one exception; it is not in the timed
   engine. Test code is outside the rule too (CppUnit, §8).
2. **NetPlumber's toolchain and flags.** g++ with `-O3`, both recorded as stamps (§8), so
   that a NetPlumber/VeriFlow-FR gap is not partly a build-flag gap.
3. **Single-threaded**, as VeriFlow, Veriflow-RI and Delta-net were measured.
   Parallelism would be a later, declared variant.
4. **In-process through pybind11**, built as `net_plumber/python/build_libnetplumber.sh`
   builds `libnetplumber`. There is no JSON-RPC path.
5. **Hardening from day one**, learned from `net_plumber/FAVE_CHANGES.md` §5 (#C1, #C4,
   #C5): an ASan/UBSan job, and a brute-force concrete-packet oracle for the trie and EC
   code, as `32a41069` added for header spaces. A small, obviously correct Python EC
   model may serve as a second oracle in the tests.

**C++17 rather than C++14:** it matches the NetPlumber build. The calibration compares
timings, not language editions, and C++17 adds nothing that affects a measurement.

### D6 — RESOLVED 2026-09-29: §4.6 is in scope, staged and measured both ways (owner's call)

**What the texts establish:**

1. **Every published VeriFlow number has §4.6 on.** "An optimization in our
   implementation uses a condensed set of fields in the trie" (T p.36 fn., pointing to
   §3.2.2).
2. **Its benefit has never been measured.** Neither text turns it off. The paper's
   experiment that varies the field count from 1 to 14 removes unused fields from the
   trie, which is not the same thing.
3. **Its premise is OpenFlow 1.1's, not the algorithm's.** It relies on 10 of 14 fields
   being exact-or-ANY. The principle behind it is general: arbitrary-wildcard fields are
   trie dimensions, exact-or-ANY fields are split by a linear scan at the device, and
   excluded packet sets carry the finer rules met elsewhere.
4. **The calibration does not need it.** Airtel is dst-IP only and Veriflow-RI is
   single-field; with one field §4.6 is a no-op, so V1's exit (§8) is unaffected.
5. **The texts never combine it with rewrites.** §4.5 and §4.6 are described apart. How
   excluded sets behave when a rewrite moves an EC to another device is our design,
   whichever way it goes.

**Why it cannot be left out.** The multi-field rows (`wl_up`, `wl_tum`, `wl_ifi`,
`wl_generic_fw`, `wl_stanford`, `wl_i2`) are where APKeep saw its EC explosion, and
plausibly where §4.6 helps most, since a finer rule at another device becomes an
exclusion instead of a network-wide EC split. A slow VeriFlow-FR there without §4.6 could
be "VeriFlow without its own optimisation", which is the straw man item 31 forbids.

**The decision:**

- **Generalise the rule, not the field list.** Per workload, a field is a trie dimension
  if any rule matches it with an arbitrary wildcard, and a linear-scan field otherwise.
  Port ranges expanded to prefixes (an adapter encoding) therefore stay in the trie. V0's
  survey supplies the classification.
- **The classification is a stamp:** `vf_fields=plain`, or
  `vf_fields=4+10:{trie=[…],scan=[…]}`.
- **It is a declared extension** in item 31's registry: the literature's rule applied to
  FaVe's fields. The §4.5 × §4.6 combination is entered as our own design.
- **Phases:** V1-V3 build the plain trie over every used field. It is simpler to get right
  and becomes the oracle. **V3b** adds §4.6; its gate is verdict identity with plain
  VeriFlow-FR on every workload. **V5 reports both.** Where §4.6 applies, the faithful
  variant is VeriFlow-FR's headline number and plain is the ablation, which is the first
  published measurement of this optimisation.
- **Fallback, declared rather than silent:** if excluded sets under rewrites prove
  unworkable, the multi-field rows report plain VeriFlow-FR only, labelled "without §4.6,
  which the published numbers include".

### D4 — CLOSED 2026-09-29: the UIUC source is never consulted (owner's call)

The earlier default was "never, unless the owner allows it per question". That left an
approval path open, and the path cannot be made clean:

1. **Legally, approval does not cure anything.** We hold no licence, the licence's §3
   treats the code as confidential, and the surviving copy is very likely an
   unauthorised redistribution (§1). A clean room protects against copying *expression*;
   it does not change having *read confidential material from an unauthorised source*. A
   per-question approval would only attach the owner's name to each instance. The
   product was commercialised and has a corporate successor (§1).
2. **Our clean room is procedural.** The subagent of §5.4 is the same model, and its
   answer enters the implementer's context. That is adequate for `MuLx10/VeriFlow`, where
   reading is lawful and the separation only protects the independence of our reading,
   but a reviewer or lawyer would rightly discount it for the UIUC code.
3. **It would falsify the provenance value.** TODO item 31 defines `reimpl-literature`
   as "our implementation from the publications alone". One consulted question would
   make that false.
4. **It would settle little.** Most §7 questions end at step (b), FaVe's own semantics.
   The hard ones are rewrites (V3) and §4.6 under rewrites (V3b), both from the 2015
   thesis. The release is the 2012-13 NSDI version and may predate them. That is
   unknown, since no `.cpp` body was read (§3).
5. **A better channel exists:** asking the authors (D5) gives citable answers, raises no
   licence question and keeps the provenance clean. Without an answer the question
   becomes a declared design choice (§5 step f), which is the honest outcome where the
   literature is silent.

**The cost, accepted:** some questions will be decided by our design where reading the
code would have given the original's answer. We could never have checked that fidelity
anyway, since the release is not run (§1). The evidence for VeriFlow-FR is the
calibration gate and the verdict differential (§8).

### D5 — RESOLVED 2026-09-29: ask, in three narrow batches, sent by the owner (owner's call)

Asking the authors is §5's step (e), the last step before a question becomes our own
design (f). Step (b), FaVe's semantics, comes first. So only questions about **what
VeriFlow, or an experiment, did** go to the authors; how FaVe should behave is ours.

**The three groups, in order of value:**

1. **Delta-net (Horn, Kheradmand, Prasad): first, because it gates V1's exit.** Q10-Q14
   (§7): the snapshot's identity, what one query computes, what is timed, what
   Veriflow-RI optimised, and whether Veriflow-RI or Delta-net can be run by us.
2. **Khurshid, possibly with Godfrey in copy: for V3 and V3b, drafted after V0.**
   - Were §3.1.3's rewrites and §3.2.2's optimisation ever combined, and how do excluded
     sets behave when a rewrite moves an EC?
   - Is there an unpublished measurement of what §3.2.2 saves? This bears on D6's
     ablation.
   - Q1: were EC ranges computed network-wide or per device?
   - Was the rewrite version ever released?

   **Not asked:** a licence to the UIUC release. A 2012-13 NOX-proxy release, probably
   without rewrites, would be costly to use as an oracle, and a licence would have to come
   from UIUC's technology transfer, not from its authors.
3. **Zhang's group (APKeep): low value here.** Which "open-source version of VeriFlow"
   did they benchmark (the source of the 686-rule, ~15 M-EC figure, §2)? Is Delta-netMF
   available? This serves TODO item 31's Delta-net question more than this plan, and can
   wait for it.

**The rules:**

- **The owner sends.** Claude drafts, and looks up current addresses and affiliations at
  drafting time rather than guessing them. The sending identity (university or genua) is
  the owner's choice. Sending is outward-facing and is never done by Claude.
- **When:** each group's questions are concrete before they are sent, one batched email
  per group. Group 1 now (V1), group 2 after V0, group 3 with item 31.
- **Content:** our purpose (a FaVe-unified, fair comparison) and that our implementation
  is independent; a request for prose answers and for permission to cite them as
  personal communication. Questions use the literature's terms only and are **never
  shaped by §3's contamination record**; for example, nothing about the
  own-location next-hop convention.
- **Answers** are appended verbatim to the question in §7, with date and sender.
- **Code:** if code is offered or attached, **nobody opens it until the owner decides**.
  It would be a new source, needing its own standing in §2 and a provenance check against
  item 31's values.
- **No answer:** four weeks after sending, the question goes to §5 step (f) and becomes
  a declared design choice. The plan never waits indefinitely.

### Still open

- **Delta-net as a backend** is a suite-level question (TODO item 31), not this plan's.

**Workload features, by what VeriFlow-FR must support.** This is the V0 survey,
2026-09-29 (`fave/bench/feature_survey.py`, tests `fave/test/test_feature_survey.py`).
It replaces the earlier hypothesis table, which had `wl_i2` among the multi-field ACL
workloads; it matches only the destination and the VLAN.

**What it measures and where.** The survey records what an engine is *handed*: a
recording engine stands behind a real in-process aggregator (`util.in_process_driver`),
after FaVe's model building and before any adapter's encoding. So rules an adapter
synthesises for itself are not counted; they are that adapter's accommodations (TODO
item 31). Each field value is classified by its bit vector: ANY, exact, prefix
(wildcards only at the end), ternary, or negated. Checks come from `checks.json`,
parsed with the harness's own parser. The inputs were regenerated from tracked sources
with `fave/test/gen_*_inputs.sh` the same day. The firewall workloads need
`FAVE_ALLOW_OUT_IFACE=1`, which leaves their `-o` matches unmodelled (TODO item 13a).
Regenerate with `python3 bench/feature_survey.py --bench <dir> [--files …]
[--checks …] --json out.json`, from `fave/`.

| workload | devices | tables (LPM) | rules → one per in-port | rewrites | checks: must / must-not (conditioned) |
|---|---|---|---|---|---|
| `wl_airtel1` | 16 switch | 16 (16) | 39,500 → 42,000 | — | 210 / 46 (0) |
| `wl_airtel2` | 16 switch | 16 (16) | 39,500 → 42,000 | — | 210 / 46 (0) |
| `wl_i2` | 18 switch | 18 (9) | 77,841 → 78,047 | VLAN set 77,451 | 72 / 0 (0) |
| `wl_stanford` | 48 switch | 48 (16) | 8,792 → **14,821** | VLAN set 3,417 | 240 / 0 (0) |
| `wl_cloud` | 86 switch | 86 (0) | 1,741 → 1,741 | NAT: dst masked 14, src set 14 | 5 / 66 (12) |
| `wl_ifi` | 1 router, 16 switch | 21 (1) | 191 → 223 | VLAN set 11; metadata set/clear | 54 / 245 (54) |
| `wl_up` | 136 packet filter, 23 switch | 839 (0) | 7,828 → 7,836 | metadata set/clear | 3,371 / 15,440 (3,302) |
| `wl_tum` | 1 packet filter | 3 (0) | 5,116 (from 3,794 ruleset lines, up to 15 each) | metadata set/clear | none: `checks.json` is empty |
| `wl_example` | 1 packet filter, 2 switch | 8 (0) | 37 | metadata set/clear | 7 / 3 (9) |
| `wl_generic_fw` (default instance) | 1 packet filter | 5 (0) | 22 | metadata set/clear | 7 / 3 (9); its policy *is* `wl_example`'s |

**`vf_fields` per workload (D6).** A field is in the trie if some rule matches it with an
arbitrary wildcard; otherwise it is scanned. No field was found constrained by nothing.

| workload | trie | scan |
|---|---|---|
| `wl_airtel1`, `wl_airtel2` | ipv4.dst | — |
| `wl_i2` | ipv4.dst | vlan |
| `wl_stanford` | ipv4.dst, ipv4.src, dport, tcp.flags | vlan, proto |
| `wl_cloud` | ipv4.dst, ipv4.src | proto, sport, dport |
| `wl_ifi` | ipv4.dst, ipv4.src | in_port, out_port, vlan |
| `wl_up` | ipv6.dst, ipv6.src, icmpv6.type | proto, sport, dport, related, module.limit, three ipv6header fields, in_port, out_port |
| `wl_tum` | ipv4.dst, ipv4.src, dport | proto, sport, svlan, dvlan, related, in_port, out_port |
| `wl_example`, `wl_generic_fw` | ipv6.dst, ipv6.src | proto, sport, dport, related, in_port, out_port |

**Findings, and what each means for VeriFlow-FR:**

1. **No rule anywhere carries a ternary or a negated value.** Every constrained value is
   exact or a prefix, so the ternary trie's generality is never exercised by the current
   suite. It is kept anyway, because the literature specifies it and it costs nothing
   when unused. Negations occur only in **check conditions**: `wl_cloud` has 4 on the
   protocol and 4 on the port. They are a query-side matter (Q17).
2. **§4.6's premise largely holds for FaVe.** Only the IP addresses, the destination
   port (`wl_stanford` 234, `wl_tum` 820: port ranges that FaVe's own parsers expand into
   prefixes, the same for every engine), TCP flags (`wl_stanford` 24) and ICMPv6 type
   (`wl_up` 1,766) are ever prefix-valued. The last is an artefact of FaVe's layout
   (Q18).
3. **Rules listing several ingress ports** are disjunctions. One OpenFlow match holds
   one IN_PORT, so VeriFlow-FR must expand them: 1.69× on `wl_stanford`, 1.06× on the
   airtel pair (Q16).
4. **Rewrites come in three kinds.** A *full* set (VLAN on `wl_i2`, `wl_stanford`,
   `wl_ifi`; NAT source on `wl_cloud`); a *masked* set (NAT destination to a subnet,
   `wl_cloud`); and a **clear to ANY**, which is how FaVe forgets its `in_port` /
   `out_port` metadata at post-routing in every router and packet-filter model. The
   thesis's actions cover the first two; the third has no VeriFlow counterpart (Q19).
5. **FaVe's pipeline metadata are header fields.** `in_port` and `out_port` are written
   by FaVe's own pre-routing and matched later by its filters. That is FaVe's
   modelling, the same for every engine, so VeriFlow-FR takes them as header fields
   like any other.
6. **Declared LPM tables** (all 16 airtel tables, 9 in `wl_i2`, 16 in `wl_stanford`, 1
   in `wl_ifi`) need a priority encoding: prefix length becomes priority, as NetPlumber's
   `_lpm_ordered_batch` does. The LPM guard (§8) applies.
7. **Multi-table devices.** `wl_up` has 839 tables for 159 devices, `wl_tum` 3 tables in
   one. VeriFlow's graph node is a device; FaVe's unit is a table wired to others inside
   a device (Q20). There are also 552 multi-port forwards (`wl_stanford`) and explicit
   drops (firewalls, `wl_stanford`, `wl_cloud`).
8. **Probes with path constraints** (`wl_ifi` 10, `wl_up` 137, `wl_example` 3) are
   FaVe's counterpart of the thesis's path invariants (Ch. 4, §4.6-4.7). All 20,271
   checks in the suite use one temporal operator, `EF`.

**Not surveyed, and why:**
- `wl_expand` benchmarks NetPlumber's header-expansion mechanism and asks no
  verification question.
- `wl_shadow` asks an anomaly question, not reachability.
- `wl_state_snapshots` streams state insertions; it calls `random` without a seed, so it
  is not reproducible as it stands.
- `wl_deltanet` is untracked, has no `SOURCE.json`, and its provenance is unknown.

**Found on the way:** `wl_generic_fw`'s `_post_preparation` calls
`bench/wl_generic_fw/reach_csv_to_checks.py`, which does not exist (the script is
`bench/reach_csv_to_checks.py`), and it ignores the exit status. So that benchmark's
checks conversion fails silently (TODO item 32).

## 10. Phases

**Test-first (§8):** every phase from V1 opens by writing its catalogue tests (L) and
unit tests and seeing them fail, and its exit begins with those tests green.

- **V0 — Spec freeze.** Survey each workload's features, including its `vf_fields`
  classification (D6), and resolve Q1, Q2, Q5, Q7-Q9, Q15-Q21. **Done 2026-09-29**
  (§9, §7). Still open, and not blocking V1: Q3/Q4 (V3) and Q10-Q14 (the authors, D5).
- **V1 — Single-field core** (≈ Veriflow-RI): trie, EC, forwarding graph, reachability
  and loop queries over dst-IP; the link-failure query. `wl_airtel1`/`wl_airtel2`,
  differential + LPM guard green. *Exit:* L1-L6 and V1's share of L10 green; the §8
  calibration against Delta-net Table 4. **DONE 2026-09-29.** Every exit item holds:
  - **Tests first and green:** L1-L6, and L10 for §4.1-4.4 and 4.6-4.10 (VLAN
    isolation waits for V3), plus the concrete-packet oracle. 24 C++ tests, clean
    under ASan+UBSan; three injected bugs failed 7, 2 and 9 of the first 10.
  - **The differential:** on both airtel traces the matrix equals `reachable.json` and
    NetPlumber's, through the same in-process aggregator
    (`fave/test/test_veriflow_airtel.py`).
  - **The LPM guard:** all 13 nested prefix pairs with different next hops are decided
    by the longer prefix, and a guard-only inverted build fails all 13. The matrix
    cannot see LPM here.
  - **The calibration:** 2.1-2.3× Veriflow-RI's 4.5 ms (§8).

  V1 translates switch models only and refuses the rest, with the reason: routers,
  packet filters, rewrites, misses, negated rule fields, probe paths.
- **V2 — Multi-field + ACLs.** Report EC counts and range-expansion factors against
  APKeep's figures. *Exit:* L7 and V2's share of L10 green, the oracle and crafted
  multi-field tests. **No FaVe differential here:** the V0 survey found no multi-field
  workload without rewrites. The metadata set/clear alone puts every router and
  packet-filter workload under V3 (Q2). **DONE 2026-09-29.**
  - **Tests first:** L7 (the cartesian product), `ec_count` (counting without building,
    saturating at 2^128), V2's share of L10 (black holes behind a multi-field ACL,
    overlaps across fields). The oracle now also checks count = built on every random
    network. 28 C++ tests.
  - **The EC census** (`fave/bench/veriflow_ec_census.py`, pinned by
    `fave/test/test_veriflow_census.py`) reproduces APKeep's Table 3 exactly where the
    data is the same. On one field, VeriFlow's whole-space range ECs are Delta-net's
    atoms.

    | workload | VeriFlow-FR, FIB destinations | APKeep Table 3, Delta-netMF |
    |---|---:|---:|
    | `wl_airtel1`, `wl_airtel2` | **2,799** | Airtel1/2: 2,799 |
    | `wl_stanford`, 3,844 FIB rules | **2,283** | Stanford*: 2,283 (Table 1: 3.84e3 rules) |
    | `wl_i2`, 77,451 FIB rules | 16,232 | Internet2: 22,212 -- *different data*, 1.26e5 rules |

    Over all fields the whole-space products explode, as APKeep §5.3 reports for range
    ECs (Delta-netMF: 15 million on its Stanford encoding):

    | workload | whole-space ECs |
    |---|---:|
    | `wl_ifi` | 2.9e6 |
    | `wl_i2` | 5.8e6 |
    | `wl_cloud` | 8.3e7 |
    | `wl_stanford` | 5.3e10 |
    | `wl_tum` | 5.1e13 |
    | `wl_up` | 2.8e17 |

  - **Expansion factors:** ingress ports (Q16) 1.0-1.69; FaVe's own port-range
    expansion, which every engine sees alike, only on `wl_tum`: mean 1.19, max 15 rules
    per ruleset line.
- **V3 — Rewrites** (§4.5) **and device-local slicing for every bulk check** (Q22,
  `vf_slicing=device`). Required, not optional (D1). Q3/Q4 resolved. *Exit:* L8 and
  the rest of L10 (VLAN isolation among them) green, and **the first multi-field FaVe
  differential**: every surveyed workload against NetPlumber, APKeep and ad6 (§8).
  **Status 2026-09-30: built and gated; two owner decisions open (Q4, the limit).**
  - **Tests first:**
    - L8 (a rewrite transforms the EC; Q3's reslicing and forks; Q19's clear to
      ANY; the revisit rule);
    - the rest of L10 (§4.5 VLAN isolation);
    - the budget and its diagnostics;
    - an oracle that simulates concrete packets through rewrites, where a rewrite
      to a set branches over its values, on 60 random networks under each revisit
      rule;
    - local = network-wide slicing on 30 rewrite-free random networks.

    39 C++ tests, clean under ASan+UBSan. Dropping rewrites, ignoring revisits,
    and deciding by the wrong candidate fail 5, 2 and 5 of the 37 tests that
    existed then.
  - **The adapter:**
    - translates rewrites (VLAN, NAT source and subnet destination, FaVe's
      metadata set and clear) and router and packet-filter pipelines;
    - mirrors NetPlumber's skipped internal wires, which describe the pipeline;
    - does NOT mirror NetPlumber's pre-routing mask quirk (one rule, wl_ifi); the
      differential shows no difference;
    - accepts probe paths, which NetPlumber's compliance ignores too.
  - **Per-table tries** for local slicing's candidates (T p.40's second trie
    traversal) cut wl_airtel1 from 48.6 s to 8.9 s.
  - **The first multi-field differential, against NetPlumber,** measured under a
    budget of 5e7 local ECs with both revisit rules:

    | workload | outcome | VeriFlow-FR `path` / `state` | NetPlumber |
    |---|---|---:|---:|
    | `wl_ifi` | **equal**, 54 pairs | 0.2 s / 0.2 s | 0.1 s |
    | `wl_cloud` (NAT) | **equal**, 53 | 0.6 s / 0.7 s | 0.5 s |
    | `wl_example` (packet filters) | **equal**, 6 | 0.4 s / 0.3 s | <0.1 s |
    | `wl_airtel1` (device slicing) | **equal**, 210 | 9.4 s / 9.6 s | 12.8 s |
    | `wl_i2` (VLAN mesh) | **equal**, 61 | 493 s / 444 s | 876 s |
    | `wl_stanford` | did not finish within 5e7; **under 2e9: equal**, 165 pairs, 5.67e8 local ECs, 0.9 GB peak | 1,973 s / -- | 11.9 s |
    | `wl_up` | did not finish; the work is at the `pgf` forward filter (3.2e7) | -- | -- |
    | `wl_tum` | did not finish; its firewall table alone predicts 1.74e10 | -- | -- |

    APKeep and ad6 are compared with NetPlumber on these workloads by their own
    differentials. VeriFlow-FR's agreement with them follows by transitivity
    where those hold, and was not run separately.
  - **Q4, resolved (owner, 2026-09-30): `state`, the thesis's rule,** by
    default. The two rules differ in no verdict on any workload that finishes.
    `state` never does more work (wl_i2: 0.94M local ECs against 1.93M; wl_ifi:
    716 against 6,255). The router-on-a-stick experiment shows the path rule
    losing a real delivery, as NetPlumber does (§7 Q4, TODO item 33).
  - **The limit** for "did not finish" is the open suite-wide decision in TODO
    item 31. 5e7 local ECs is a working budget, not that limit. With room to
    run, wl_stanford **finishes and agrees**: 33 minutes and 0.9 GB against
    NetPlumber's 12 s. About 166x is the measured price of range-based ECs on
    its out-stage ACLs, a finding and not a failure. Whether wl_up and wl_tum
    finish under the suite's limit is for V5 to measure once the limit is set.

- **V3b — The §4.6 optimisation** (D6), generalised to FaVe's fields, with excluded sets
  under rewrites. *Exit:* L9 green; verdicts identical to plain VeriFlow-FR on every
  workload.
  Fallback per D6.
  **DONE 2026-10-01.**
  - **Tests first:**
    - L9, a finer rule serves a subset and the coarse rule the rest;
    - an exclusion surviving a rewrite of its own field: the pitfall our design
      guards, where subtracting after the rewrite would empty the set;
    - refusal of a prefix on a scan field;
    - fewer local ECs than plain;
    - D6's gate, verdict identity with plain on 120 random rewriting networks
      under both revisit rules.

    Never materialising, never excluding, and skipping the emptiness test each
    fail a test. 44 C++ tests.
  - **The design where the thesis is silent, declared (D6):**
    - exclusions at every table: bulk mode has no "new rule's device" to split
      at fully;
    - a rewrite of a field an exclusion constrains first materialises "primary
      minus excluded" by exact box subtraction.

    `scan_fields(ir)` classifies per workload (the V0 survey's `vf_fields`),
    stamped `vf_fields=4+10:trie=[...],scan=[...]`.
  - **The gate, met.**
    - Verdict identity with plain VeriFlow-FR on every workload where plain
      finishes: `wl_ifi`, `wl_cloud`, `wl_example`, `wl_airtel1`, `wl_i2`,
      `wl_stanford`.
    - **Agreement with NetPlumber on all nine**, including the two plain could
      never finish:

    | workload | plain | 4+10 | NetPlumber |
    |---|---|---|---:|
    | `wl_example` | 40,097 local ECs | **218** | -- |
    | `wl_cloud` | 47,611 | **14,684** | -- |
    | `wl_i2` | 444 s | **254 s** | 788 s |
    | `wl_stanford` | 911 s, 1.07e8 | **303 s**, 3.7e7 | 6.4 s |
    | `wl_up` | did not finish (2.6e11 predicted at `pgf`) | **3,660 pairs = NP**, 788 s, 2.24e7 | 33 s |
    | `wl_tum` | did not finish (1.74e10 predicted) | **finishes, = NP**, 612 s, 1.17e6 | 10 s |

    Times are `limit_class=dev`, not reportable; the verdict equality is
    evidence on any machine. wl_tum's comparison is ONE existential pair
    (`source.tum` reaches `probe.tum` on both), since its only source and probe
    share a name.
  - **Default:** `fields="4+10"`, VeriFlow-FR's headline per D6; plain is the
    ablation. The wl_tum did-not-finish test now pins plain explicitly.
  - **What it changes for the comparison:** the explosion inside single firewall
    tables (Q22) was plain slicing's, not VeriFlow's as specified. The thesis's
    own optimisation removes it, which is exactly why D6 made §4.6 required.

- **V4 — FaVe integration.** Adapter, `FAVE_BACKEND=veriflow`, doctor entry for the
  build, `integration`-tier gate, every accommodation entered in TODO item 31's
  registry.
- **V5 — Measurement** over the whole suite, both regimes where TODO item 31's
  incremental axis exists, stamped per §8. **Under the suite-wide limit** (TODO item
  31, decided 2026-10-01): 24 h and 32 GB per cell, on the larger machine to come.
  V5 waits for it; runs in this container are `limit_class=dev` and not reportable. Both field variants (D6): §4.6 as the
  headline where it applies, plain as the ablation.

## 11. Citation and attribution

Cite the NSDI'13 paper and the thesis for the algorithm. Because nothing is derived
from the UIUC software, its licence's notice and acknowledgement clauses (§2.7-2.8) do
not apply — **that is only true while §5 holds**, which is the practical reason the
protocol is strict, and why D4 is closed rather than left to per-question approval.
