# VeriFlow as a FaVe Verification Backend — an Independent Implementation

**Status:** PLANNING (opened 2026-09-29). No code yet. D1-D6 resolved 2026-09-29 (§9); D5's first batch (Q10-Q14) awaits sending.
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

## 6. Architecture (proposal)

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
  *Resolved 2026-09-29 (D6):* in scope, as a **required, staged** variant, not an optional
  one. V1-V3 are plain; V3b adds §4.6, with plain VeriFlow-FR as its verdict oracle. §9.
- **Q7 — Port semantics.** See §6. Path: FaVe semantics; stamped.
- **Q8 — Delivery.** When does a device "consume" a packet? FaVe answers this with its
  own sink nodes; no consultation needed. Recorded because §3 notes a seen-in-code
  convention we are deliberately *not* using.
- **Q9 — Priority ties** between overlapping rules of equal priority at one device:
  OpenFlow leaves it undefined. FaVe's table semantics (`TABLE_SEMANTICS_PLAN.md`)
  make every table first-match-wins in document order unless declared otherwise, so
  document position is the tie-break and the adapter encodes it into priority.

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
- **Unit tests from the literature:** §4.3's worked example (with §4.9's correction),
  Alg. 2's branch rule, and a crafted rewrite chain for §4.5.
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

**Measurement stamps** (TODO 0a: *every measurement-affecting choice is a stamped
result field*): trie field order; mode (incremental / bulk); field classification `vf_fields` (D6); port
semantics (Q7); port-range expansion factor; EC count per update (VeriFlow's own
headline metric); compiler, standard and flags (D3); thread count (1, D3); provenance `reimpl-literature` with the
engine commit (TODO item 31's provenance column, shared by every backend). **A VeriFlow-FR number is reported as VeriFlow-FR's**,
beside a sentence on what it interprets — as Delta-net did for Veriflow-RI.

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
   engine.
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

**Workload features, by what VeriFlow-FR must support** (a hypothesis until V0's survey):

| needs | workloads |
|---|---|
| dst-IP forwarding only | `wl_airtel1`, `wl_airtel2` (Delta-net's regime; the calibration data) |
| + multi-field ACLs | `wl_stanford`, `wl_i2`, the firewall workloads (`wl_up`, `wl_tum`, `wl_ifi`, `wl_generic_fw`) — where APKeep saw the EC explosion |
| + header rewrites (§4.5) | VLAN models of `wl_i2`/`wl_stanford`; NAT in `wl_cloud` |

The thesis's §4.5 moved the last row from "out of scope" (the NSDI paper alone) to
"native".

## 10. Phases

- **V0 — Spec freeze.** Survey each workload's features (fills §9's table), including
  its `vf_fields` classification (D6); resolve Q1, Q2, Q5, Q7-Q9 on paper. D2, D3 and D6
  are resolved. *Exit:* §7 has no unresolved question that blocks V1.
- **V1 — Single-field core** (≈ Veriflow-RI): trie, EC, forwarding graph, reachability
  and loop queries over dst-IP; the link-failure query. `wl_airtel1`/`wl_airtel2`,
  differential + LPM guard green. *Exit:* the §8 calibration against Delta-net
  Table 4.
- **V2 — Multi-field + ACLs.** Report EC counts and range-expansion factors against
  APKeep's figures.
- **V3 — Rewrites** (§4.5). Required, not optional (D1). Q3/Q4 resolved.
- **V3b — The §4.6 optimisation** (D6), generalised to FaVe's fields, with excluded sets
  under rewrites. *Exit:* verdicts identical to plain VeriFlow-FR on every workload.
  Fallback per D6.
- **V4 — FaVe integration.** Adapter, `FAVE_BACKEND=veriflow`, doctor entry for the
  build, `integration`-tier gate, every accommodation entered in TODO item 31's
  registry.
- **V5 — Measurement** over the whole suite, both regimes where TODO item 31's
  incremental axis exists, stamped per §8. Both field variants (D6): §4.6 as the
  headline where it applies, plain as the ablation.

## 11. Citation and attribution

Cite the NSDI'13 paper and the thesis for the algorithm. Because nothing is derived
from the UIUC software, its licence's notice and acknowledgement clauses (§2.7-2.8) do
not apply — **that is only true while §5 holds**, which is the practical reason the
protocol is strict, and why D4 is closed rather than left to per-question approval.
