# VeriFlow as a FaVe Verification Backend — an Independent Implementation

**Status:** PLANNING (opened 2026-09-29). No code yet.
**Owner:** Claas Lorenz. **Driver:** PhD-thesis future work — a further engine family
beside NetPlumber (HSA), APKeep (atomic predicates, BDD/NDD) and ad6 (SAT/ASP).
Siblings: [`APKEEP_BACKEND.md`](APKEEP_BACKEND.md), [`AD6_PLAN.md`](AD6_PLAN.md),
[`CLOUD_BENCH_PLAN.md`](CLOUD_BENCH_PLAN.md) §2 (the Delta-net workloads).

Working name for our implementation: **VF-FaVe** (placeholder — §9, decision D2). It
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
| UIUC release (`xwu64/…`, commit `d31f03c`) | the original C++ | **not run**; consulted only under §5's protocol, and only if the owner lifts the default (D4) |

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
query's answer is "primary set minus excluded set".

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
   consult an implementation's *source*.
4. **Source consultation (step d) is done by a separate subagent** that is given the
   question, reads the code outside the repo, and answers **in prose, describing
   behaviour only** — no code, no identifiers beyond those the literature already
   publishes, no data-structure layouts. The answer is appended to §7 verbatim with the
   date and which implementation was read. The implementing agent never has the code
   open.
5. **The UIUC source is off-limits by default** (D4). Consulting it at all is an owner
   call per question, because even reading an unlicensed copy sits uneasily with its
   §3.
6. Nothing from either implementation — files, snippets, test vectors, topology files —
   enters the repo or `fave/bench/`.

## 6. Architecture (proposal)

Placement mirrors the existing engines: an engine directory at the repo root, a thin
adapter under `fave/`, selection through the existing backend switch.

```
vf_fave/                    C++17 engine (D3), CMake or make like net_plumber/
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
- **Q2 — Rules that split an EC at another device.** Without §4.6's optimisation, can a
  rule at device B split an EC formed from the rules overlapping a new rule at device
  A? If it overlaps the EC it overlaps the new rule and was already included — unless a
  *rewrite* moved the EC (§4.5), which is exactly why the thesis goes device by device.
  Path: derive, then confirm on a crafted rewrite example.
- **Q3 — Rewrites that split.** After a rewrite, the transformed EC may be split by the
  next device's rules into several local ECs; does the graph fork per local EC, and are
  the forks' packet sets tracked back to the original EC? T §3.1.3 implies forking.
  Path: derive from FaVe's semantics.
- **Q4 — Revisit ≠ loop under rewrites.** T §3.1.3 stops at a device "already visited
  for a previously encountered packet set (which also indicates presence of a routing
  loop)". With rewrites, revisiting a device with a *different* header is not a loop.
  Path: FaVe's loop semantics decide; record the divergence if we differ.
- **Q5 — Deletion.** Paper and thesis state deletes are handled (all five OpenFlow
  FLOW_MOD types) but describe only insertion. Presumed symmetric: find ECs overlapping
  the removed rule, remove, rebuild their graphs. Path: derive.
- **Q6 — Is §4.6 in or out?** Implementing the 4+10 optimisation and excluded sets is a
  large share of the complexity and is tied to OpenFlow 1.1's field classes, which are
  not FaVe's. Proposal: V1-V3 build the plain multi-dimensional trie over *all* used
  fields; §4.6 is an optional, stamped variant later. Path: owner (D6).
- **Q7 — Port semantics.** See §6. Path: FaVe semantics; stamped.
- **Q8 — Delivery.** When does a device "consume" a packet? FaVe answers this with its
  own sink nodes; no consultation needed. Recorded because §3 notes a seen-in-code
  convention we are deliberately *not* using.
- **Q9 — Priority ties** between overlapping rules of equal priority at one device:
  OpenFlow leaves it undefined. FaVe's table semantics (`TABLE_SEMANTICS_PLAN.md`)
  make every table first-match-wins in document order unless declared otherwise, so
  document position is the tie-break and the adapter encodes it into priority.

## 8. Correctness and measurement gates

**Correctness** needs no VeriFlow oracle: FaVe already has three engines that agree.
- **Differential:** every workload VF-FaVe runs is compared pair by pair against
  NetPlumber, APKeep (NDD) and, where it runs, ad6 (`test_backend_differential.py`).
- **LPM guard** (`CLOUD_BENCH_PLAN.md` §3): each FIB workload must show its evidence can
  see priority — invert the order, the verdict must change.
- **Unit tests from the literature:** §4.3's worked example (with §4.9's correction),
  Alg. 2's branch rule, and a crafted rewrite chain for §4.5.
- **Optional black-box run** of `MuLx10/VeriFlow` on small forwarding-only inputs,
  recorded as behaviour, never vendored.

**Measurement stamps** (TODO 0a: *every measurement-affecting choice is a stamped
result field*): trie field order; mode (incremental / bulk); §4.6 on/off; port
semantics (Q7); port-range expansion factor; EC count per update (VeriFlow's own
headline metric); language/build flags. **A VF-FaVe number is reported as VF-FaVe's**,
beside a sentence on what it interprets — as Delta-net did for Veriflow-RI.

## 9. Owner decisions pending

- **D1 — The research question.** "EC slicing as a technique" makes VeriFlow the
  canonical baseline. "The strongest incremental competitor" argues for Delta-net's
  atoms instead (fully specified, datasets already in `bench/deltanet/`). The answer sets
  the workload scope below.
- **D2 — Name.** `VF-FaVe` is a placeholder.
- **D3 — Language.** C++ proposed: the original was C++ and NetPlumber is C++, so a
  timing comparison is not dominated by the runtime. Python would be faster to write
  and slower to measure.
- **D4 — UIUC source consultation.** Default: never. Owner may allow it per question.
- **D5 — Ask the authors?** Godfrey (licence/permission for the original); Horn or
  Kheradmand (Veriflow-RI / Delta-net); Zhang's group (Delta-netMF).
- **D6 — §4.6 optimisation** in scope, or a later variant (Q6)?

**Workload scope, by what VF-FaVe must support** (to be confirmed per workload in V0 —
the feature column below is a hypothesis until surveyed):

| tier | needs | candidates |
|---|---|---|
| A | dst-IP forwarding only | `wl_airtel1`, `wl_airtel2` (Delta-net's own regime) |
| B | + multi-field ACLs | `wl_stanford`, `wl_i2` (minus VLAN), firewall workloads (`wl_up`, `wl_tum`, `wl_ifi`, `wl_generic_fw`) — where APKeep saw the EC explosion |
| C | + header rewrites (§4.5) | VLAN models of `wl_i2`/`wl_stanford`; NAT in `wl_cloud` |

The thesis's §4.5 **moves tier C from "out of scope" to "in scope in principle"** —
the NSDI paper alone ruled it out.

## 10. Phases

- **V0 — Spec freeze.** Survey each candidate workload's features (fills §9's table);
  settle D1-D3, D6; resolve Q1, Q2, Q5, Q7-Q9 on paper. *Exit:* §7 has no unresolved
  question that blocks V1.
- **V1 — Single-field core** (≈ Veriflow-RI): trie, EC, forwarding graph, reachability
  and loop queries over dst-IP. Tier A, both modes, differential + LPM guard green.
- **V2 — Multi-field + ACLs.** Tier B; report EC counts and range-expansion factors
  against APKeep's figures.
- **V3 — Rewrites** (§4.5). Tier C; Q3/Q4 resolved.
- **V4 — FaVe integration.** Adapter, `FAVE_BACKEND=veriflow`, doctor entry for the
  build, `integration`-tier gate.
- **V5 — Measurement**, stamped per §8.

## 11. Citation and attribution

Cite the NSDI'13 paper and the thesis for the algorithm. Because nothing is derived
from the UIUC software, its licence's notice and acknowledgement clauses (§2.7-2.8) do
not apply — **that is only true while §5 holds**, which is the practical reason the
protocol is strict.
