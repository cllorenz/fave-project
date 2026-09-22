# Benchmark-suite extension: the NoD cloud dataset and the Delta-net traces

**Status 2026-09-21 — `wl_cloud` built, running, and driven by an FPL policy in
BOTH of its phases (§1.9).** The oracle phase states the dataset's six questions
as five FPL rules over a fabricated inventory; the matrix phase states the
dataset's own 26x26 ACL matrix (C7, §1.9.6). All six third-party oracle verdicts
reproduced on NetPlumber before and after the switch (§1.7.1). Both other
engine families first got it wrong and both were fixed: ad6 refused the workload
outright, then answered every cell (§1.7.2), and APKeep answered ten of
sixty-four cells wrong, then all of them (§1.7.3). Running the matrix phase then
found a third defect, in ad6's rule reader -- a rule matching both transport
ports was read as an OR (§1.7.4). **With that fixed, all three engines agree on
every check of all three phases.** Three defects fixed in shared code building it (§1.6) and two more
building the policy (§1.9.6). **Delta-net: D1 and D2 done 2026-09-22** — the
fourth CSV column is a priority encoding LPM (`5*plen+100`, exact on all
76,200 rows), the trace needs no replay because no insert overwrites another,
and three figures this document stated about the traces were wrong (§2.2 D1).
What they contain is now derived into `fave/bench/wl_deltanet/TRACES.md` and
pinned, rather than described here. D3-D5 open.

**C7 headline:** the dataset's own 26x26 ACL matrix compiles to 4,224 checks over
26 roles. Under the matrix as written, **1,312 violations, every one of them
predicted before the run** — the generator publishes a service with a
source-less ACL rule, so all 11 public services are reachable from all 26 roles
while the matrix authorises 102 of 286 such cells. Stating that makes the run
clean. **3 violations survive both policies**, and they are a
finding about the DATASET: services 1, 11 and 23 are the only public services
whose prefixes span two datacenters, and the gateway publishes only one prefix
of each, so half of each is unreachable from the Internet although matrix row 25
authorises the service. `network.tf` carries a second, SHADOWED NAT rule for
each; reduce it by Hassel's own priority rule and the file becomes exactly the
Datalog's 11 gateway rules, so the dataset's two encodings agree and FaVe
reproduces both (§1.9.6, TODO item 16 — which first recorded this as an engine
semantic difference, wrongly).

Two third-party datasets arrived in the tree as untracked archives
(`cloud_bench.tar.bz2`, 21 MB; `deltanet-NSDI17-dataset.tar.gz`, 9.6 GB). This
document records what they contain, what each is good for, and the build plan
for the new workloads. **The archives themselves are no longer kept** — the
parts in scope are vendored, extracted, under
`fave/bench/wl_cloud/cloud-tf/` and `fave/bench/wl_deltanet/deltanet-traces/`,
and git is what reveals a change to them (§1.8). It is the sibling of [`AD6_PLAN.md`](AD6_PLAN.md) for the
*benchmark* axis rather than the *backend* axis.

**Owner decisions 2026-09-18:**
1. cloud: **oracle first, then matrix** — gate `wl_cloud` on the six labelled
   sat/unsat queries before compiling the README's 26x26 ACL matrix into a full
   compliance workload.
2. Delta-net: **static snapshot first** — replay an only-inserts trace into a
   final FIB and verify it statically; decide on the incremental benchmark after,
   with evidence.
3. Extract only the two `*-only-inserts.csv` files (2.4 MB total).
4. **Do not keep the source archives** (revised 2026-09-18): they are far too
   large, the extracted copies live in the repository instead, and git is what
   reveals a change to them. Claas will re-supply an archive if one is ever
   needed again.

---

## 0. Why extend the suite at all

The suite has six workloads (`wl_example`, `wl_ifi`, `wl_up`, `wl_tum`,
`wl_stanford`, `wl_i2`). Against the four verification families they are used to
compare, they leave three gaps:

- **No external oracle.** Every correctness result to date is a *consensus*
  between implementations in this tree. `AD6_PLAN.md` §9.28 says so explicitly
  ("a CONSENSUS between two implementations, not an oracle"), and `TODO.md`
  item 1s records that the `bench` tier does not gate on correctness. Nothing in
  the suite carries a verdict produced by a tool outside this repository.
- **No header rewriting.** `wl_stanford`/`wl_i2` are forwarding + ACL;
  `wl_up`/`wl_tum` are firewalls. Rewriting (NAT) is exactly where HSA, AP/BDD
  and a SAT encoding diverge in cost, so its absence leaves a hole in the very
  design space `AD6_PLAN.md` §0 is about.
- **No incremental axis.** All six are static snapshots, although FaVe's own
  TNSM'21 claim is *continuous* verification and `NetPlumberAdapter` is the only
  adapter that implements `delete_rules` at all.

The cloud dataset closes the first two. The Delta-net traces address the third.

---

## 1. The NoD cloud dataset (`cloud_bench.tar.bz2`)

Tarred 2013-08/2013-09 by `nlopes`, i.e. the Network-Optimized-Datalog line of
work. Eight scenarios; **only `cloud/base` is in scope** (owner decision — the
others exist as a ready-made scaling axis and cost nothing to defer).

`cloud/base` holds:

| file | what |
|---|---|
| `network.tf` | Hassel transfer function, 2,941 rules, 713 KB |
| `README.txt` | the generator invocation, service -> prefix table, and a 26x26 ACL matrix |
| `0[1-6].{sat,unsat}.smt2` | six Z3-Datalog reachability queries, **verdict in the filename** |
| `network.svg` | rendered topology |

Generator invocation, from the README:

    topology_gen.py --nodes-per-datacenter=200 --router-replication=2 \
                    --ports-per-router=32 --ports-per-leaf-router=32 \
                    --random-seed=346376325

5 datacenters, 8 leaf routers each, 30 hosts per leaf router, 26 services,
public service IP `121.140.254.0`, public TCP port 331.

### 1.1 Header layout — MEASURED, not assumed

The `.tf` syntax is byte-identical in shape to `wl_stanford`'s
(`$`-separated, `fwd`/`rw` actions), but the **field order inside the 128-bit
match string is different**, and nothing in the file declares it. It was
recovered by counting, for each of the 128 bit positions, how many of the 2,941
rules constrain it; the field boundaries fall out of the density profile:

| bits | constrained in | field |
|---|---:|---|
| 0–15 | 0 rules | `packet.ether.vlan` (never used) |
| 16–47 | ~1,555 | `packet.ipv4.source` |
| 48–79 | ~1,682 | `packet.ipv4.destination` |
| 80–87 | 396 | `packet.ipv6.proto` — single value `00000110` = 6 (TCP) |
| 88–103 | 353 | `packet.upper.sport` |
| 104–119 | 382 | `packet.upper.dport` |
| 120–127 | 0 rules | `packet.upper.tcp.flags` (never used) |

Cross-checks that make this a measurement rather than a guess: the only value
ever seen at bits 80–87 is 6 (a legal protocol number, and the only one the
generator emits); decoding bits 48–79 as an address yields `10.0.0.0/25`-style
prefixes matching the README's service table; the 28 `rw` rules carry a mask of
48 ones / 32 zeros / 48 ones, i.e. they rewrite exactly bits 48–79, which is
destination NAT at the gateway and is what a public-service IP requires; and
decoding under `wl_stanford`'s own layout instead yields nonsense addresses like
`6.1.75.1` (the proto byte read as the first octet).

**The counts above are per-BIT density, which for an IP field is a range rather
than a number** — a `/22` constrains 22 of its 32 bits and a `/30` constrains 30,
so source runs 1,558 down to 0 across bits 16–47 and destination 1,682 down to
14. That is what the tilde on `~1,555` is doing. `bench/wl_cloud/WORKLOAD.md`
tabulates the same fields as *rules whose field is not fully wildcarded* — one
well-defined number each, and 1,558 for the source — and is derived on every
run rather than written here once.

`packet.ipv4.destination` lands at bit 48 under **both** layouts, which is a
coincidence worth knowing about: a converter that got the layout wrong would
still produce plausible-looking forwarding and would fail only on the ACL and
NAT fields. This is exactly the class of defect `AD6_PLAN.md` §9.29 describes,
so the layout is pinned by a test, not by a comment.

FaVe needs no code change for this: `Mapping` is data-driven, so the layout is a
`mapping.json`:

```json
{ "packet.ether.vlan": 0, "packet.ipv4.source": 16,
  "packet.ipv4.destination": 48, "packet.ipv6.proto": 80,
  "packet.upper.sport": 88, "packet.upper.dport": 104,
  "packet.upper.tcp.flags": 120, "length": 128 }
```

### 1.2 The device model — MEASURED

Unlike `wl_stanford`, this dataset has **one flat rule list for the whole
network and no `link$` lines**. Ports are not interfaces; they are **nodes**,
and a rule `fwd A -> B` means "a packet at node A moves to node B" — the same
`R_<node>` relation set the `.smt2` files declare. The topology is therefore
implicit in shared node ids and has to be derived.

Deriving it by in-degree/out-degree over all 2,941 rules gives a completely
regular decomposition — 2,487 nodes in exactly three classes:

| class | count | evidence |
|---|---:|---|
| appears as both rule in-port and out-port | **85** | the forwarding devices |
| in-port only | **1,201** | 1,200 host *transmit* nodes + internet ingress |
| out-port only | **1,201** | 1,200 host *receive* nodes + internet egress |

The 85 split further, and the split matches the README exactly: **5** nodes with
`id % 100000 == 0` (the datacenter cores), **40** odd ids (leaf-router ingress),
**40** even ids (leaf-router egress) = 5 datacenters x (1 core + 8 leaves x 2).
1,200 hosts = 5 x 8 x 30, i.e. the README's "30 hosts per leaf router".

Each host owns a node *pair*: an even transmit node and an odd receive node on
the same `/30`. The internet follows the same convention (`1500000` transmit,
`1500001` receive).

One leaf router, decoded, shows the whole idiom:

```
fwd 1000001 -> 1000002   dst=10.0.0.0/25,proto=6,dport=350    <- the ACL
fwd 1000001 -> 1000002   dst=10.0.0.0/25,proto=6,dport=342    <- the ACL
fwd 1000001 -> None      dst=10.0.0.0/25                      <- drop: local, not permitted
fwd 1000001 -> 1000000   *                                    <- default route, up to the core
fwd 1000002 -> 1000003   dst=10.0.0.0/30                      <- deliver to host 1
fwd 1000004 -> 1000001   src=10.0.0.0/30                      <- host 1 injects
```

So the ingress node carries the **ACL and the routing decision**, the egress node
carries **host distribution**, and the host transmit rule is a pure source
constraint. Rule counts by class: leaf-ingress 448, leaf-egress 1,200,
core 74, host/internet transmit 1,219 — total 2,941.

45 rules have **no out-port**: those are drops, at 41 distinct nodes.

### 1.3 The mapping onto FaVe

| cloud node class | FaVe object |
|---|---|
| 85 forwarding nodes + internet ingress (19 NAT rules) | **86 tables** (`switch` devices) |
| host transmit node | **generator**, header = the node's own `src=<prefix>` rule |
| host receive node | **probe** |

That is ~1,722 table rules over 86 devices — between `wl_ifi` and `wl_stanford`
in size, and comfortably inside what all three backends have already run.

The host transmit rules become generator constraints rather than tables, which
is why the table-rule count is 2,941 − 1,219.

> **CORRECTION (2026-09-22): it is 1,741, not ~1,722.** The subtraction above
> removes the internet gateway's 19 rules along with the 1,200 host injectors,
> while the line above it counts that same gateway as one of the 86 tables. The
> gateway's rules *are* table rules, so the figure is 2,941 − 1,200. `routes.json`
> has carried 1,741 entries since the workload was first built — the model was
> never wrong, only this description of it. Derived and pinned in
> `bench/wl_cloud/WORKLOAD.md` / `test/test_cloud_census.py`.

**Design decision: a cloud-specific preparation module, not an extension of
`bench/np_preparation.py`.** That module's `_port_no_to_port_name`,
`_probe_id_to_name` and `_source_id_to_name` encode `wl_stanford`'s port
arithmetic (`port // 100000` = table id, `intervals` mapping the remainder to an
in/mid/out stage) and its `add_source` path hardcodes an unconstrained
`ipv4_dst=0.0.0.0/0` generator. Cloud needs neither the three-stage pipeline nor
an unconstrained source. What *is* generic and will be reused: `_CONVERSION`,
`_get_field_from_match`, `_get_rewrite` (all driven by `mapping`) and
`_reprioritise_fib_lpm` — the last is load-bearing here, because cloud resolves
`/30` host routes against `/25` leaf routes, `/22` datacenter routes and a
wildcard default, and NetPlumber orders by rule index.

### 1.4 The oracle

Six queries, verdict in the filename, all endpoints exactly the transmit/receive
node classes derived above:

| query | source | constraint | target | verdict |
|---|---|---|---|---|
| 01 | internet `1500000` | none | `1100323` | **sat** |
| 02 | internet `1500000` | none | `1200449` | **unsat** |
| 03 | internet `1500000` | `dport=0x014C`, `proto=6` | `1100043` | **sat** |
| 04 | internet `1500000` | `dport != 0x014B` | `1400233` | **unsat** |
| 05 | host `1100380` (`dc1_leaf6_host2`, 10.0.7.8/30) | `dport=0x015E` (350) | `1000067` (`dc0_leaf1_host1`, 10.0.0.132/30) | **sat** |
| 06 | host `1100376` (`dc1_leaf6_host0`, 10.0.7.0/30) | `dport=0x015F` (351) | `1000067` (the same host) | **unsat** |

Query 04 is the interesting one: *"from the internet, on any port other than
331, can anything reach `1400233`?"* — a genuine security property, not a
synthetic pair.

**05/06 are NOT a matched pair, contrary to what this section first said.** They
differ in SOURCE HOST as well as in port — `dc1_leaf6_host2` (10.0.7.8/30) on
350 against `dc1_leaf6_host0` (10.0.7.0/30) on 351. Both sources sit behind the
same leaf router in dc1 and both target the same host in dc0, so the forwarding
path from that leaf onward is shared and the contrast is close to
single-variable — but it is not the port-only contrast originally claimed, and
if either ever disagrees with the oracle the cause could be the source address
rather than the ACL. Corrected 2026-09-18 while laying the oracle out endpoint
by endpoint.

**Open discrepancy — RESOLVED 2026-09-21, and it was neither an off-by-one nor
two generator runs.** It read: the README says the public TCP port is **331**;
query 04 excludes `0x014B` = 331, consistent with that; but query 03 is
*satisfiable* with `dport = 0x014C` = **332**.

331 is not *the* public port. It is the **base of the service port range**:

    service i  <->  TCP port 331 + i  <->  public address 121.140.254.i

so 331 is service 0 and 332 is service 1. Query 03's target `1100043` sits in
datacenter 1, whose only service the README lists is **service 1**, published on
332. Query 04's target `1400233` sits behind a leaf whose only *public* service
is **service 0**, on 331 — which is why excluding 331 makes it unsatisfiable.
Both queries are consistent with one README and one generator run.

Measured, not inferred (`test_cloud_readme.py`): the 2,941 rules constrain
exactly the 25 ports 331–355, one per declared service, and each of the 19
gateway NAT rules maps `121.140.254.<i>:331+i` onto a datacenter the README says
hosts service `i`. The port offset and the address offset are the same index,
which is what rules out an encoding slip in either.

All six verdicts follow from that algebra alone — e.g. q02 is unsat because its
leaf permits only port 343, whose rules carry a source constraint, and the
internet is not a service.

### 1.5 Build plan (`fave/bench/wl_cloud/`)

- [x] **C1** `cloud_tf.py` — parse `network.tf`, classify nodes, derive the port
      graph. Test-first, with the node-class census (85/1,201/1,201 and the
      5/40/40 split) as the assertion. `test/test_cloud_tf.py`, 26 tests.
- [x] **C2** `mapping.json` + a test pinning the field layout of §1.1 against
      decoded known values from the README, so a silent layout regression fails.
      Includes a guard test asserting the Stanford layout decodes the same rule
      *differently*, without which the pinning would be vacuous.
- [x] **C3** `cloud_preparation.py` — emit FaVe's `topology`/`routes`/`sources`/
      `probes` JSON. `test/test_cloud_preparation.py`, 20 tests.
- [x] **C4** `benchmark.py`. `fib_table_types` is declared as a module constant
      (`FIB_TABLE_TYPES`) rather than a `config.json`, because this workload
      builds its own model instead of going through `prepare_benchmark`; the
      "declared, never inferred" rule of `AD6_PLAN.md` §5.5 is satisfied either
      way.
- [x] **C5** **DONE 2026-09-18 — all six oracle verdicts reproduced on
      NetPlumber, zero violations.** See §1.7.
- [~] **C6** **ad6 REFUSES the workload** (§1.7.2, a structural encoding limit);
      **APKeep drops all three reachable pairs** (§1.7.3). NetPlumber is
      therefore the only family that currently answers this workload.
- [x] **C7 DONE 2026-09-21 for the MATRIX — §1.9.6.** wl_cloud goes through
      PolicyTranslator like every other workload: 26 roles (the dataset's 25
      services plus the Internet) over 65 endpoints, 215 FPL rules covering all
      226 ordered 1-cells, 4,224 checks. Two policies, because the matrix and
      the data plane disagree by design (owner decision): `matrix/reach.txt`
      states the matrix and reports 1,315 violations, `matrix/reach_public.txt`
      adds what the
      generator implemented and reports 3. Operators: `--->` twice per service
      pair, `<-->` for the Internet pairs — so F1 and F2 are both load-bearing.
      **The six oracle queries became FPL too**, in a parallel session and by
      the other route (§1.9, eight fabricated host roles). This half had
      expected them to stay as they are, on the grounds that host roles would
      overlap the service roles — they do, and the two phases are kept in
      separate directories because of it. The original reasoning follows, since
      the overlap it names is real: they name individual hosts, and expressing
      them as FPL would cost seven
      fabricated roles overlapping the service roles, putting the one
      third-party artifact through a self-derived pipeline. Follow-up, not
      a gap.

---

## 1.6 Four defects found building it, and one latent trap

Three of the four are in **shared** code, not in the new workload, and each was
invisible until a workload with different shape arrived.

**(a) `netplumber/adapter.py`: a character-set strip truncating device names.**
`add_tables` resolved a declared table index with `model.table_ids[name.rstrip('.1')]`.
`str.rstrip` strips CHARACTERS, not a suffix: it ate the `.` separator and then
kept eating `1`s out of the device name itself, so `lin.dc0_leaf1.1` resolved to
`lin.dc0_leaf` and raised `KeyError`, killing the model-add task. Every workload
predating this one names its devices `bbra_rtr`, `fw`, `sw` — none ends in `1` —
so nothing had ever hit it. **Fixed** (`removesuffix('.1')`) with two regression
tests. `test/test_adapter.py` already carried a note flagging the sibling site
(`_get_index_for_src`) as fragile; that one is safe, because its two-step
`rstrip('1').rstrip('.')` lets the `.` act as a barrier.

**(b) `bench/compliance_checker.py`: a negated field condition was unsayable.**
`_parse_check` built every `RuleField` with `negated=False` hardcoded, so a check
could negate its REACHABILITY (`!`) but never a field VALUE. **Fixed** additively
(`f=!field:value`) with a test module the parser never had.

**(c) `netplumber/adapter.py`: the negation was then silently dropped.** With (b)
fixed, query 04 still answered the wrong question: `_create_compliance_rules`
built its condition with `_build_vector`, which writes each field's value into
one vector and never reads `RuleField.negated`. So *"on any port other than 331"*
was sent to NetPlumber as *"on port 331"* — and the reported violating flow
carried `packet.upper.dport=331`, the very value the check was meant to exclude.
The adapter already had `_expand_negations` (used on rule matches) and the
compliance path simply never reached for it. **Fixed**: a negated condition now
expands into its complement (16 vectors for a 16-bit port), and a negated
condition on a MUST-REACH check is **refused** rather than approximated — each
expanded entry is checked independently, so requiring reachability under every
complement vector would be a strictly stronger claim than the question asked.

This is the swallowed-sub-step pattern of `TODO.md` items 1i/1n/1p in its most
expensive form: the check ran, produced a verdict, and the verdict answered a
different question.

**(d) In the new code: a rewrite's prefix length was stripped.** The DNAT rules
rewrite the destination to a **/24 service subnet**, not to a host. Emitting
`ipv4_dst:10.0.0.0` instead of `ipv4_dst:10.0.0.0/24` pinned every inbound flow
to one host, and all four internet-sourced queries answered "unreachable". Found
because two of them were labelled `sat`; without the oracle it would have looked
like a plausible result.

### The latent trap: mask polarity

Hassel applies a rewrite as `(h & mask) | rewrite`
(`wl_stanford/stanford-hassel/headerspace/tf.py`), so **mask `0` marks the bits a
rule replaces**. The cloud `network.tf` follows that, and so do the raw
`wl_stanford/stanford-tfs/*.tf` — all 874 `rw` rules in `bbra_rtr.tf` carry
`0000000000000000` on the VLAN field they rewrite.

But `np_preparation._get_rewrite` tests the field's mask for **all ones**, and
the committed `wl_stanford/stanford-json/*.tf.json` carries inverted masks. Those
two agree with each other, so wl_stanford's 3,417 rewrites come out correct
(`rw=vlan:2`) and **no current result is affected**.

The trap is that `stanford-json/` cannot be regenerated from the `stanford-tfs/`
sitting beside it. Running today's `tf_to_json.py` + `np_preparation` over the raw
file yields, for the rule whose committed form is `['vlan:2']`:

    ['tcp_flags:0', 'tcp_dst:0', 'tcp_src:0', 'ip_proto:0',
     'ipv4_dst:0.0.0.0/32', 'ipv4_src:0.0.0.0/32']

— every field zeroed *except* the one actually rewritten. Anyone regenerating
that workload's JSON gets a silently different model. Not fixed here: which of
the two conventions `stanford-tfs/` is supposed to be in is a question about that
dataset's provenance, not about this one.

---

## 1.7 Results

### 1.7.1 NetPlumber — all six verdicts reproduced

    ## Compliance Check
    No compliance violations have been found.

Model: **86 devices, 1,741 routes, 145 inter-device links, 6 generators,
5 probes** (six queries, two of which share a target). `report.md` exists and the
aggregator log carries `completed task check_compliance` with zero `task failed`
lines — the §3 guardrail, checked rather than assumed.

**The green is not vacuous, and that was verified rather than argued.** Three
independent pieces of evidence: the first run of this same pipeline reported
q01/q03 as violations and the second reported q04, so violations demonstrably
surface; `checks.json` holds all six checks; and a deliberate **mutation
control** — flipping q06's expectation from `unsat` to `sat` — produces exactly
one violation, naming q06.

So **FaVe+NetPlumber agrees with a third-party tool, on a network neither has
seen, on all six labelled instances.** That is the first externally-grounded
correctness result in this suite.

The §1.4 port discrepancy (README says 331, q03 is sat on 332) never had to be
resolved: both queries reproduce as labelled, so whatever the 331/332 difference
means, FaVe and the oracle agree about it. It stays on record as unexplained.

#### Re-verified under the FPL policy (2026-09-21)

The workload is now expressed as an FPL policy (§1.9), so the six checks are no
longer hand-built. **The verdict is unchanged: 6/6 reproduced**, which is what
makes this a reformulation rather than a new result. Model census moved
(**8 generators, 8 probes** — one per role member rather than one per query),
because four of the six queries now share the internet gateway's single
generator and carry their constraints on the check instead.

Query 06 reproduces **by the violation its rule predicts** (§1.9.0's
"expected verdict per check", now `cloud_provenance.expected_violated`), and
query 04 by the complement term `--complement` generates.

Alongside them, 65 self-derived expectations, reported separately and never
summed:

| what | outcome |
|---|---|
| unconditioned cross-pair denials | **48 of 50 violated** |
| self-pair denials (host → its own rx node) | 6 of 7 violated |
| complements of a conditional permission | **5 of 7 held** |
| the conditional permission itself | 1 of 1 held |

The 48 say that our fabricated default-deny does not describe this network:
hosts in this datacenter reach each other freely, which the dataset never
claimed otherwise. That is a statement about the policy we wrote, which is
exactly why the two provenances are kept apart.

**Every internet-facing complement held.** "These services and nothing else" is
true at the perimeter for all three internet-sourced rules — the half of a
conditional permission §1.9.3 added and which no workload had yet been able to
check. The two that fail are both host-to-host, where no ACL sits.

### 1.7.2 ad6 — refuses the workload, for a structural reason

    UnsupportedField: field 'packet.ipv4.destination' matches '10.0.0.0/25',
    which is not an integer.

This is the encoding limit `AD6_PLAN.md`'s translate module documents, reached
for the first time by a workload rather than by construction. ad6 offers two
representations for a field: an ADDRESS primitive, which understands CIDR, and a
mutable `fieldmatch` over a bit-vector, which is integer-valued and is the only
correct form for a field that some rule REWRITES. The choice is a property of the
whole model — a field rewritten anywhere must use `fieldmatch` everywhere.

The cloud model **rewrites `ipv4_dst` and `ipv4_src`** (NAT at the gateway) and
**matches `ipv4_dst` with 1,668 non-/32 prefixes**. Those requirements are
mutually exclusive in ad6's encoding, so the translation refuses — loudly and at
the right place, which is the designed behaviour.

**This is a result, not an obstacle**, and it is the reason the dataset was worth
adding: it is the first workload in the suite that rewrites an ADDRESS field, and
it converts "a generic model checker pays for genericity" from an argument into a
measured boundary. It belongs in `AD6_PLAN.md` §7's expressiveness table.

**RESOLVED 2026-09-21, and the boundary was ONE THING TOO MANY.** The refusal was
an artefact of `ConvertFieldToVariables`, not of the encoding: ad6's two OTHER
converters (`ConvertPortToVariables`, `ConvertCIDRToVariables`) were already
prefix-capable, and the newest one took an integer only because the fields it was
built for (`vlan`, `in_port`, `out_port`) are exact-valued. `<fieldmatch>` now
takes a TERNARY bit-vector (`AD6_PLAN.md` §9.35), so a rewritten field can be
matched by prefix. Measured on this dataset: **2,480 of 2,480 distinct address
match values translate, 0 refused** — where previously every one was refused.

**Closing it uncovered a SECOND boundary the first was hiding** — and that one is
now closed too (`AD6_PLAN.md` §9.36). The 28 NAT rules rewrite the destination to
a SUBNET (`10.0.0.0/24`, `10.0.12.0/23`, `10.0.16.128/25` — 24 distinct values,
none of them a host address), and `translate._rewrites` required an integer or a
wildcard: 0 of 24 accepted. **Owner ruling 2026-09-21: the unwritten bits are
PRESERVED** — Hassel's `(h & mask) | rewrite`, not cleared and not arbitrary.
That turned out to be the operation ad6's frame axioms already perform per bit,
so a masked rewrite is the REWRITE and FRAME axioms mixed within one field,
chosen per bit by the mask.

**ad6 no longer refuses wl_cloud.** Measured on the dataset's own 2,941 rules:

    address MATCH values  : 2480 translate, 0 refused
    address REWRITE values:   24 translate, 0 refused

**It is not yet a result.** Translatable is not solvable, and none of this
touches cost — mutable addresses give every node its own 64-bit SSA copy over
~2,500 nodes, plus a frame-or-rewrite axiom per bit per edge. Size the instance
before solving it; item 0a applies to whatever number comes out.

#### The masked rewrite was implemented BACKWARDS — found 2026-09-21

Running it produced a wrong answer, not a cost problem: **ad6 called every
internet-sourced pair unreachable**, against NetPlumber and against the dataset's
own `sat` verdicts for q01 and q03.

The ruling was right and the implementation applied it to the wrong bits. Hassel
preserves what a rewrite does not replace, but **which bits those are is decided
by the MASK, not by the value** — net_plumber's `array_rewrite` says so outright
("a 0 in the mask means that the bit should be kept whereas a 1 means it should
be rewritten"), and a rewritten bit takes the rewrite value's bit *including its
`x`*. FaVe's model has no mask-0 bit inside a rewritten field at all:
`NetPlumberAdapter` synthesises `"1"*FIELD_SIZES[f]` for every field a `Rewrite`
names. So a value's don't-cares are the only wildcards there are, and framing
them preserved bits nothing had asked to preserve.

**§1.6 had already written the symptom down**, for the mirror-image bug on the
FaVe side of the same boundary: *"`10.0.0.0/24` leaves the low 8 bits free.
Emitting the bare address instead pins traffic to one host and every
internet-sourced query answers unreachable."* The DNAT matches a `/32` public
address and rewrites to a `/22` subnet, so the framed bits were fully determined
by the match and the `/22` collapsed to exactly one host — 10.0.6.1. Measured at
the hop: of `dc1_core`'s fourteen out-ports, exactly one was reachable from the
internet generator.

Corrected in `AD6_PLAN.md` §9.36. All-pairs reachability over the eight FPL
endpoints, unconditioned:

| | agrees with NetPlumber |
|---|---:|
| ad6, before | 58 / 64 |
| ad6, after | **64 / 64** |
| APKeep, before | 54 / 64 |
| APKeep, after (§1.7.3) | **64 / 64** |

and after the correction ad6 matches the dataset at q01, q02 and q03.

#### ad6 RUNS IT — 6/6, and identical to NetPlumber on all 71 checks

The last blocker was the query-seeding path, not the model:
`fave_bridge._SUPPORTED_COND_FIELDS` forced only `related`, and the FPL check
set puts `f=related:0` on every conditional check plus `f=!port:331` on the one
carrying q04. Generalised at `AD6_PLAN.md` §9.37, and the run now completes:

    ad6, 6/6 oracle verdicts reproduced, 56/65 self-derived violated
    netplumber, 6/6 oracle verdicts reproduced, 56/65 self-derived violated

Not merely the same totals. Every query is paired to the SAME check line on both
engines, every per-query record matches, and **all 71 per-check verdicts are
identical** — 57 violated on each, zero disagreements. The model census
(86 devices, 145 links, 1,741 routes, 8 generators, 8 probes) is identical too,
which is what makes the comparison one of engines rather than of two models.

So this workload now has two independent engines agreeing with each other AND
with six verdicts produced outside this repository a decade earlier. Both stamps
are committed under `eval/`.

**Guarded from here on.** `fave/test/test_ad6_cloud_differential.py`
(integration tier, ~2 min) holds ad6 and NetPlumber to the same matrix and both
to the dataset. It exists because no unit test could have caught this: every
piece was individually correct, and the test that pinned the encoding asserted
the wrong behaviour *in its own name*.

### 1.7.3 APKeep — a forwarding table is not always a FIB (FIXED 2026-09-21)

**The first diagnosis here was wrong, and how it was wrong is half the lesson.**
It read the symptom — nothing in the datacenter reached anything — as a missing
topology, and blamed `apkeep/adapter.py`'s device-name coupling, since
wl_cloud's `core.`/`lin.`/`lout.`/`gw.` devices fire none of the
`in.`/`mid.`/`out.` branches that adapter is full of. That named a real defect
(the coupling is there; `AD6_PLAN.md` §9.25 deleted the same construct from
ad6) but not this one. Dumping the built model settles it: **86 devices, 165
edges, 1,736 forwarding rules — the topology was built.** The evidence had been
available from the start, and a plausible story was written instead of read.

**What was wrong is the element every forwarding table became.** APKeep's
`ForwardElement` is a destination-prefix trie: one match field, longest prefix
wins. `_translate_fwd_rule` turned every table into one, keeping the destination
and dropping the rest — any source, protocol or port the rule matched, any
header rewrite, and the rule ORDER, which it replaced with the prefix length.
For a FIB that is exactly right, and every workload before this one had only
FIBs. wl_cloud is the first whose forwarding tables carry ACLs:

    lin.dc1_leaf5
      1  dst=10.0.6.128/25, proto=6, dport=332  -> forward to the hosts
      2  dst=10.0.6.128/25                      -> drop
      3  (default)                              -> forward upstream

Rules 1 and 2 arrived as a forward and a drop on the same prefix at the same
priority. **The two engines behind the one adapter then resolved that tie
oppositely** — APKeep's BDD engine kept the drop (8 of 64 cells reachable), the
NDD engine kept the forward (57) — which is as direct a demonstration as one
could ask that the outcome had stopped being the policy's to decide. Beside it,
the gateway's fourteen DNAT rules arrived with no rewrite (so internet-sourced
traffic kept its public destination and no core had a route for it), and its
five source-only anti-spoofing drops were skipped by the discard guard. Three
widenings and one narrowing, one cause.

**And a fourth, found by fixing the first three.** With the tables right, the
matrix phase still over-reported by 293 pairs. `add_generator` read the injected
source ADDRESS and ignored every other field a generator states — which cost
nothing while every workload injected only an address, and wl_cloud's matrix
phase injects `tcp_src` as well, one per service endpoint, which its leaf ACLs
match on. A source that emits from one port was queried as if it emitted from
all of them.

#### The fix: the table decides the element, from its rules

A table whose rules match only a destination prefix (plus `vlan`/`in_port`,
which other mechanisms handle) and rewrite only `out_port` stays a
`ForwardElement` — still every other workload, and wl_cloud's own 40 leaf-egress
tables. Anything else becomes a `FilterElement`: a first-match list carrying the
whole 5-tuple, with the rule index as the priority. An address rewrite on such a
table becomes a `NATElement` inline on its egress port. On wl_cloud that is **46
of 86 devices (40 `lin.`, 5 `core.`, 1 `gw.`), 541 filter rules and 28 address
rewrites**; the other 40 keep the trie.

Nothing in that decision reads a device name (`_is_dst_lpm_table`), which is
what the first diagnosis was right to care about while naming the wrong cause. A
name-keyed fix would have been the same defect with a longer list of prefixes.
One exemption remains and is deliberate: the HSA `in.`/`mid.`/`out.` stages are
claimed by the wl_stanford/wl_i2 collapse paths, whose approximation is a
decision taken in `APKEEP_STANFORD_NP_SPEC.md` rather than one to re-open here.
Lifting it means giving the `FilterElement` a VLAN field.

Three things had to be built rather than rewired:

* **A source rewrite.** `NATElement` could rewrite the destination only, keyed
  on a destination prefix (`common.Fields.src_ip` reached `get_field_bdd` and
  got `BDDFalse` back). wl_cloud's cores rewrite the SOURCE of outbound traffic,
  which is exactly what carries it past the gateway's anti-spoofing rules — and
  two of those rewrites leave the same port with the same source /24, differing
  only in `tcp_src`. So the rewrite is keyed on the rule's whole match, not on
  an address: `+ nat <dev> <port> match <src|dst> <ip> <len> <that match>`.
* **The same in the NDD engine**, whose `+ nat` handled the VLAN rewrite only.
* **Check conditions beyond `related`.** The FPL check set puts
  `f=protocol:tcp`, `f=port:332` and `f=!port:331` on its checks and the adapter
  refused everything but `related` — the blocker ad6 cleared at `AD6_PLAN.md`
  §9.37. Each condition is now the packet space of a one-field rule, or its
  complement, intersected with what arrives at the probe. Constraining at
  arrival equals injecting only that traffic exactly while nothing rewrites the
  field, so a condition naming a field THIS model rewrites is refused rather
  than answered — on wl_cloud that is both addresses.

**A rewrite onto a prefix frees the bits it does not fix.** Both engines
quantify the field away and then constrain it to the new predicate, so a DNAT
onto a /22 reaches the whole /22 — the semantics §1.7.2 and `AD6_PLAN.md` §9.36
had to correct on the other backend, where preserving those bits collapsed the
/22 to one host.

#### Result: APKeep agrees with NetPlumber everywhere this workload asks

All-pairs over the eight FPL endpoints, unconditioned:

| | agrees with NetPlumber |
|---|---:|
| ad6 | 64 / 64 |
| APKeep, before | 54 / 64 |
| APKeep, after | **64 / 64** |

and through PolicyTranslator, on the identical generated model (86 devices, 145
links, 1,741 routes, 8 generators, 8 probes), all three phases:

| phase | checks | APKeep | NetPlumber |
|---|---:|---:|---:|
| oracle | 71 | 6/6 verdicts, 57 violated | 6/6, 57 violated |
| matrix | 4,224 | 1,315 violations | 1,315 |
| public | 4,199 | 3 violations | 3 |

Not merely the same totals: the violated **check sets** are equal, pair for pair
and condition for condition, in all three. The one remaining difference is
presentational — NetPlumber decomposes a negated port condition into the ternary
terms of its complement and reports one line per term, so its `report.md` has 58
lines where APKeep's has 57 for the same 57 violated checks.

The five unreachable cells are the ones the model explains: `dc2_leaf7_host6`
neither reaches the internet (its /24 is in no core's source-NAT rule, so the
gateway's anti-spoofing drops it) nor is reached (its leaf denies its own
prefix, which is q02's `unsat`), plus `internet → internet`.

**Guarded from here on.** `fave/test/test_apkeep_cloud_differential.py`
(integration tier, one engine per process) holds APKeep and NetPlumber to the
same matrix and both to the dataset; `fave/test/test_apkeep_first_match.py`
(25 tests) pins each property separately, including the two refusals, which no
reachability run can reach. Verified by mutation: making every table a FIB fails
9, dropping the address rewrite fails 6, narrowing the generator seed back to
the address fails 1. Dropping the check conditions is not a unit-test matter and
was measured instead — the oracle phase falls to **4/6** and the public policy
reports **817 violations instead of 3**.

#### Still open: the BDD engine does not finish this model

The default APKeep engine is NDD, and every number above is its. APKeep's own
BDD engine (`--apkeep-engine bdd`) **did not complete the build within 40
minutes** on the corrected model, where it took seconds on the lossy one. That
is consistent with the atomic-predicate wall P7b hit on wl_stanford
(`APKEEP_BACKEND.md`, "Performance analysis: BDDs vs APs"): 46 `FilterElement`s
carrying a few hundred 5-tuple rules each split the AP partition, and
`APKeeper.updateSplitAP` touches every element per split. **It is a cost result,
not a correctness one** — no verdict was produced, so none is reported — and
sizing it properly is its own piece of work.

---

### 1.7.4 ad6 — a rule matching both transport ports meant OR (FIXED 2026-09-22)

**Found by running the matrix phase on ad6, which had never been run.** The
oracle phase agreed with everything (6/6 verdicts, 57 violated of 71, §1.7.2)
and the all-pairs matrix agreed with NetPlumber on all 64 cells, so the workload
looked settled. The 4,224-check matrix phase did not: **1,778 violations against
NetPlumber's 1,315 — 463 unexpected, 0 missing.** A pure over-approximation.

**The cause, in the rule reader.** `KripkeUtils.ConvertToKripke` collected every
`<port>` element of a rule into one list, regardless of direction, and combined
them with a **disjunction** whenever there was more than one. That is right for
several ports in the same direction — `--dports 80,443` is an alternation — and
wrong for a source port beside a destination port, which is a conjunction. So
`sport=342 AND dport=346` was encoded as:

    <disjunction>
      <variable name="src_port_342"/>
      <variable name="dst_port_346"/>
    </disjunction>

an over-approximation on ANY rule carrying both ports. The interface reader
immediately above it and the VLAN reader immediately below both split their
elements by direction; only the port reader did not.

**Reduced to two switches in series**, each permitting a different SOURCE port.
No packet carries two source ports, so the probe is unreachable:

| the rules match | ad6, before | ad6, after / NetPlumber |
|---|---|---|
| conflicting src ports | unreachable | unreachable |
| conflicting src ports **+ a dst port** | **reachable** | unreachable |
| conflicting dst ports | unreachable | unreachable |
| conflicting dst ports **+ a src port** | **reachable** | unreachable |
| both ports conflict | **reachable** | unreachable |

Either port alone was honoured; the two together were both lost, and the second
port did not need to discriminate anything — the same value at both hops was
enough.

**Why the oracle phase never showed it.** wl_cloud's leaf ACLs match both ports
on every rule, so the defect was present in both runs. The oracle generators
inject no source port: the port is free, a permitted value always exists, and
every engine agrees the traffic gets through. The matrix generators pin each
endpoint's source port, and the pinned constraint is the one that went missing.
A defect can sit in a shared reader for as long as no workload states the thing
it drops.

**The first suspect was wrong, and checking beat arguing.**
`Instantiator._ShortenPrefixes` is the IP-prefix shortening optimisation, and its
caller really does hand it every key beginning `src_`/`dst_` — so `src_port_342`
arrives there and is read as a dotted-quad with an implicit `/32`. That looked
conclusive. Instrumenting it showed it mutates nothing in either the passing or
the failing case; it is a separate latent oddity, not this. Printing the rule
condition settled it in one line.

**Fix:** split the port list by direction and mirror the neighbours —
alternatives within a direction, a conjunction across them. One change, in the
one place both the upstream `InstantiateBase` path and FaVe's
`fave_bridge._instantiate_literal` call. `ad6/FAVE_CHANGES.md` item 32.

**Blast radius, counted rather than assumed.** Rules carrying `--sport` and
`--dport` together: zero in ad6's own `bench/tum` and `bench/up`, zero in
wl_tum, wl_up, wl_ifi, wl_example and wl_generic_fw, zero in wl_stanford (its
ACLs match a destination port only). wl_shadow has 138,666 and does not reach
this code — it exists for anomaly detection, `BACKENDS_WITH_ANOMALIES` is
NetPlumber alone, and no ad6 result for it exists in the tree. The fix only ever
narrows an answer, so it cannot invalidate a recorded one.

**Result: three engines, three phases, one set of answers.**

| phase | checks | ad6 | APKeep | NetPlumber |
|---|---:|---:|---:|---:|
| oracle | 71 | 6/6 verdicts, 57 violated | 6/6, 57 | 6/6, 57 |
| matrix | 4,224 | 1,315 violations | 1,315 | 1,315 |
| public | 4,199 | 3 violations | 3 | 3 |

The violated SETS are equal across all three engines in all three phases, not
merely the totals, and the two policy phases match their derived expectations
exactly. Guarded by `fave/test/test_ad6_port_pair.py` (7 tests, mutation-verified
in both directions: not splitting by direction fails 4, AND-ing same-direction
ports fails the alternation test). `AD6_PLAN.md` §9.38.

---

## 1.8 Everything is regenerated from the raw data (owner principle 2026-09-18)

> *"I regularly ran into the challenge of errors in the data that I fed into
> FaVe/NetPlumber due to manual changes while debugging. In the end, I overcame
> this by scripting any transformation from the raw data to the actual input
> data. It is important that in the end, we can recreate any benchmark and
> measurement from the raw data."*

**Agreed, and this workload did not meet it when first built.** Three of its
artifacts were produced by hand — `network.tf` and `README.txt` were `cp`-ed out
of the extracted archive, `np.conf` was copied from `wl_stanford`, and
`oracle.json`, *the artifact the whole result rests on*, was transcribed by eye
from `grep` output over the `.smt2` files.

That last one is the dangerous shape: a single mistyped node id would have
produced a wrong oracle that FaVe then "agreed" with — a self-confirming result
with nothing able to notice. It was checked afterwards and was correct, but
"checked afterwards" is the wrong order, and it is only checkable at all because
a derivation was written.

**The same failure is already in this tree, years old.** §1.6 records it:
`wl_stanford/stanford-json/*.tf.json` cannot be regenerated from the
`stanford-tfs/*.tf` beside it, because their rewrite masks are inverted. Nothing
is wrong today only because the committed JSON and `np_preparation` happen to
agree — but which of the two is authoritative is now unanswerable. That is what
a derived artifact with no derivation looks like after a few years.

### The chain, all of it scripted

    bench/wl_cloud/cloud-tf/          the raw cloud/base scenario, TRACKED WHOLE
                                      (6.7 MB, 9 files, exactly as shipped),
                                      covered byte-for-byte by SHA256SUMS.
                                      THIS is the raw data; the archive is gone.
      -> oracle.json                  DERIVED by cloud_oracle.py from the six
                                      .smt2 instances
      -> topology / routes / sources / policies / mapping / checks
                                      DERIVED by cloud_tf.py + cloud_preparation.py
      -> eval/<engine>-<utc>.json     the STAMPED result

Everything after the first arrow is gitignored and rebuilt by
`fave/test/gen_wl_cloud_inputs.sh`, which follows the `gen_wl_*_inputs.sh`
convention the suite already uses. It reads the vendored scenario and nothing
else -- there is deliberately no live-extraction path (owner decision
2026-09-18). Before the archive was removed the script's `--from-archive` mode
was run once and confirmed the vendored copy is byte-identical to what the
archive ships; that check is what the tracked `SHA256SUMS` now carries forward.

Four properties, each enforced rather than intended:

- **The raw data is verified before anything is derived.** `verify_raw` checks
  every vendored file against `SHA256SUMS` at the start of every run and refuses
  loudly on a mismatch — a manual edit made while debugging is precisely the
  failure being prevented, and it is unrecoverable once forgotten.
- **The oracle is derived, never written.** `cloud_oracle.py` reads the argument
  order *out of each file* rather than assuming it, and refuses anything it does
  not fully understand instead of returning a partial query, which would weaken
  the gate without changing its shape. The six derived queries are pinned
  explicitly in `test_cloud_oracle.py`, so a parser change cannot quietly change
  what the benchmark is gated on.
- **`oracle.json` is no longer tracked.** It was, while hand-written. Tracking a
  generated oracle is how a benchmark ends up gated on an artifact nobody can
  rebuild.
- **The measurement is stamped too.** Every run writes
  `eval/<engine>-<utc>.json` carrying the engine and its options, the header
  length, the model census, the per-query verdict, and **the sha256 of each
  `.smt2` the verdicts came from** — so a result names the exact bytes behind
  it. The stamp's reading of `report.md` is its own tested function, because a
  stamp that always says "all reproduced" manufactures evidence.

### Provenance — incomplete, needs the owner

The archives are **not kept** (owner decision 2026-09-18 — far too large, and
git reveals any change to the extracted copies that replace them). Their
checksums are recorded here so that a re-supplied archive can be identified as
the same one these files came from:

|  | sha256 | size |
|---|---|---|
| `cloud_bench.tar.bz2` | `0c13076b0b2aa7a6be108bf44fb3f3ea37f814a55ea2e36950c35cd5b621d147` | 21 MB |
| `deltanet-NSDI17-dataset.tar.gz` | `cc67472319e5d4791b96d8ceed1a5038af1ea719c360c3ce30040f3cc17f334b` | 9.6 GB |

Internal evidence of origin, and nothing more: the cloud archive's members are
owned by `nlopes/algos` and dated 2013-07/2013-09, consistent with the
Network-Optimized-Datalog line of work; the Delta-net members are owned by
`ali/ali` and dated 2016-09, re-tarred 2019-10.

**Neither download URL was recorded, and I cannot supply one** — inventing a
plausible one would be worse than leaving the gap visible. It needs writing down
here by whoever fetched them.

What that gap now costs is bounded, because both datasets' in-scope parts are
vendored: the repository reproduces every benchmark it defines without either
archive. The gap only bites if the scope ever widens — a second cloud scenario
for the scaling axis, or a Delta-net trace beyond the two insert-only ones.

---

## 1.9 The FPL route: three work items (owner direction 2026-09-18)

**Decision:** wl_cloud should be expressed as an **FPL policy** rather than as
hand-built checks — both the 26x26 ACL matrix and the six oracle queries. The
argument is tooling consolidation and human-readability: one fewer
benchmark-specific transformation, and a workload that exercises FaVe's policy
layer rather than only its verification engine. Fabricating an inventory (a role
per endpoint host carrying its /30, a service per port) has no real-world
counterpart, which is odd, but is a fair price.

It also plugs wl_cloud into machinery it currently cannot reach: `reachable.json`
and `cchecks.json` are what `bench/apkeep_convergence.py`,
`bench/apkeep_tum_diff.py` and `bench/i2_structural_oracle.py` consume, and this
workload produces neither. §1.7.3's APKeep disagreement had to be reported by
hand for exactly that reason.

### 1.9.0 The shape, and why a policy is not enough

Claas's formulation of the six queries:

| query | FPL rule | expected |
|---|---|---|
| q01 | `internet ---> host5` | satisfied |
| q02 | *(nothing — default deny covers it)* | satisfied |
| q03 | `internet ---> host20.332` | satisfied |
| q04 | `internet ---> host22.331` (the double negative turns positive) | satisfied |
| q05 | `host2 ---> host1.350` | satisfied |
| q06 | `host0 ---> host1.351` | **violated** |

**A policy is an INTENT, not a fact, so the oracle is policy + an expected
verdict per check.** wl_ifi is the precedent: the same data plane reports 27
violations under `<->>` and none under `<-->`, because its Cisco ACLs really are
stateless. Nothing in a policy says which outcome is the expected one.

**Every expectation must be labelled by PROVENANCE.** Six come from the `.smt2`
files and are third-party. Every other check an FPL policy generates is an
expectation *we* derived — and §1.9.4 shows there will be many. Unlabelled in one
table, a mistake in our own understanding freezes in and reads as authoritative
as the external verdicts, which is precisely the property §1.8 exists to protect.

### 1.9.1 F1 — `provider` was an OR operand instead of a qualifier — FIXED 2026-09-18

`policy_builder` attaches `{"provider": role_to}` to a `--->`/`<-->` rule that
names a service, and `add_reachability_policy` appends the service's attributes
as a **separate** condition — which its own docstring defines as an **OR**
operand. So `HostA ---> HostB.S350` compiles to

    HostA,X,(provider:HostB|protocol:tcp;port:350)

Two things wrong. `provider` is metadata, not a header field, and it is OR-ed
with the service instead of qualifying it, so the cell reads *"provider is HostB
**or** tcp/350"*. `bench/reach_csv_to_checks.py` then emits it verbatim and
`bench/compliance_checker.py` dies:

    KeyError: 'provider'

No workload exercises `--->`-with-a-service today, which is why this has sat
undisturbed. Four of the six rules above use it, so it blocks the route outright.

- [ ] Decide what `provider` is *for* (it may simply not belong in `conditions`),
      fix the OR/AND confusion, and add the `--->`-with-service path to the
      translator's tests, which currently have no coverage of it.

### 1.9.2 F2 — `<-->`'s backward direction must SWAP the service — FIXED 2026-09-18

**Owner specification 2026-09-18.** `A <--> B.S` should yield two checks:

* forward — A reaches B with S's attributes **in forward direction**
  (`proto=tcp`, `dport=80` for HTTP);
* backward — B reaches A with S's attributes **in reverse direction**
  (`proto=tcp`, **`sport=80`**).

What is implemented instead passes `service_to` to the backward policy verbatim,
so the backward check asks for `dport=80` again *and* looks the service up on the
reverse role — which is why

    Internet <--> host20.S332   ->   Fehler: Service Internet.S332 unbekannt.

`--->` and `<-->` have had far less exercise than `<->>`, which is the likely
explanation for the shape of both this and F1's `provider` condition.

#### The measurement, corrected

A first pass here tested the backward direction with `dport=350` and concluded
`<-->` was unusable. **That was measuring the buggy implementation, not the
intended semantics.** Re-measured with the reverse-direction condition — all four
on q05's pair, generator at `dc0_leaf1_host1_tx`, probe at `dc1_leaf6_host2_rx`:

| check | condition | result |
|---|---|---|
| forward (control, = q05) | `dport=350` | **reachable** |
| backward, unconstrained | — | **reachable** |
| backward, **as intended** | `sport=350` | **reachable** |
| backward, mechanism check | `sport=350, dport=332` | **reachable** |
| backward, as implemented | `dport=350` | **not** reachable |
| backward, ephemeral | `dport=40000` | **not** reachable |

`dc1_leaf6`'s ACL is three rules — `dst=10.0.7.0/25 dport=332 -> forward`,
`dst=10.0.7.0/25 -> DROP`, `(any) -> default route` — so leaf6 publishes **only
port 332**, and the last row is why `dport=350` backward fails.

So under the specified semantics **`<-->` holds for q05 and is the right
operator**: stateless ACLs, TCP, and return traffic characterised by its source
port. One honesty note on the evidence: the checks are existential over header
space, so `sport=350` passes because *some* packet with `sport=350` and
`dport=332` gets in. That is weaker than "the return flow of the 350 session
works", which a stateless model cannot express at all.

`--->` remains wrong here for the reason first measured, which does survive: its
backward denial is unconditional, and the unconstrained backward direction is
reachable (on 332). That denial is also emitted by *nothing* — it is default-deny
leaving the cell empty — so another rule granting B->A would make it vanish with
no conflict raised.

#### The `Internet` role does not offer anything — and fixing that is not enough

Checked on the hypothesis that the builtin `Internet` should offer every service
by default, the intuition being that the Internet lies outside the
administrative boundary of whoever writes the policy, so its offerings cannot be
enumerated or restricted.

**It is not implemented.** `Policy.default_roles` is
`{"Internet": [('interface', '"fw.generic.eth1"')]}` — an attribute and nothing
else — and `Role.offers_service` is a plain `name in self.services` with no
special case for Internet anywhere in the lookup path.

**And implementing it would not fix `<-->`.** With no Internet in the rule at all:

    host2 <--> host1.S350   ->   Fehler: Service host2.S350 unbekannt.

The cause is structural rather than about Internet. `policy_builder` builds the
backward direction as

    policy.add_reachability_policy(role_to, role_from, service_to, condition=cond)

so `add_reachability_policy` validates `service_to` against the new `role_to`,
which is the original **source**. A service is offered by the *server* side, so
the reverse role will essentially never offer it; `Internet` is merely the most
conspicuous instance. Making Internet offer everything fixes the three
Internet-sourced rules of §1.9.0 and leaves q05/q06 broken exactly as they are.

**Done 2026-09-18 (§1.9.5), and it behaved exactly so.** With `Internet`
offering every declared service, the full six-rule `<-->` policy stops failing
on `Internet.S332` and fails on `host2.S350` instead — the error moved down to
the first host-to-host rule, and an Internet-only `<-->` policy compiles. So the
Internet-shaped instance is closed and the general one is untouched.

The real fix is the swap: the backward direction takes the *same* service —
still offered by B — and applies its attributes reversed, without a second
lookup on A.

#### The scope of the damage, precisely

`--->` and `<-->` are fine **without** a service, because `cond` is then `None`
and no lookup happens. That is the form in production use:
`wl_up/reach.txt` has `Internet <--> DMZPublicServers` and
`wl_ifi/reach_stateless.txt` has `access_to_internet <--> Internet`; both yield a
plain `X` in each direction, verified. **It is the service-carrying form of both
operators that is wholly unexercised**, and both defects — F1's `provider`
condition and the reverse-role lookup above — live on that one `if service_to`
path.

- [x] **DONE 2026-09-18.** `provider` is merged into the service condition as
      a qualifier and the service is looked up on the provider, not the reached
      role; the wildcard expands over the provider's services too.
      `Policy._condition_to_csv` resolves the direction where both role names
      are in scope — `port` towards the provider, `sport` away from it — and
      drops the marker, so a matrix consumer reads a header field rather than
      needing to know who offers what. `sport`/`dport` added to
      `OXM_FIELD_TO_MATCH_FIELD`, which carried only the forward `port`.
      The six-rule `<-->` policy now compiles, all 56 generated checks parse,
      and none mentions `provider`:

          host1,,(protocol:tcp;sport:351),X,(protocol:tcp;sport:350),,,,
          host2,,,(protocol:tcp;port:350),X,,,,

      **No existing workload changes** — a condition without a provider takes
      the same path as before, which is every use in the tree. Verified by
      regenerating and diffing: wl_example, wl_ifi and wl_up matrices are
      byte-identical.
- [ ] Decide `<-->` vs `<->>` for wl_cloud once it works. `<->>` needs **no
      fixes at all** (§1.9.4) but asserts stateful return traffic that stateless
      cloud ACLs do not provide — the wl_ifi pattern, where the violations are
      the finding rather than an artifact.

### 1.9.3 F3 — "these services and NOTHING ELSE" — IMPLEMENTED 2026-09-18

A conditionally permitted cell states the only traffic the policy allows between
a pair. Only the confirming half was ever checked. A *wholly* denied pair is
checked (the empty-cell branch) and a permitted pair is checked, but a
**partially** permitted one was checked in the direction that confirms it and
never in the direction that constrains it — so `Internet ---> host22.S331` passed
whether or not 332 also got through, and q04 would have degraded from *"nothing
outside 331 enters"* to *"331 enters"*.

**Claas's framing, which is what this implements.** No legacy probe mechanics is
needed: the reachability tree already answers it. For `A <--> B.S` the question
is whether any flow reaching A from B carries something other than S — and the
place it must hold is **the probe**, not the path. An ACL-enforcing router
between them will produce leaves bearing other ports, and that is perfectly
fine: those flows never arrive, so `check_compliance`, which iterates
`dst->source_flow`, never sees them. Nothing has to reason about intermediate
leaves.

**"...unless some other rule allows it" is already computed.** That clause
needs no logic in the generator, because `ReachabilityPolicy.update_conditions`
has merged the rules before it gets there: another *conditional* rule joins as an
OR operand, and another *unconditional* one wins outright ("the empty list
overpowers all other lists of conditions"), leaving the cell plain `X` with no
complement to check. So the generator complements the cell's own condition list
and nothing else.

**Generalised beyond the third check.** The same argument applies to the forward
direction, so this is a property of the MATRIX rather than of an operator: *every
conditionally permitted cell gets a complement check, against the union of its
own conditions.* `<-->` with a service therefore yields four checks, `--->` two
plus the unconditional denial its empty reverse cell already produces, and no
operator-specific code exists.

#### The shape

`not (a and b)` is `not a or not b`, and the complement of a union is the
intersection of complements — so complementing a cell means contradicting every
alternative at once: pick one field from each alternative and negate it, for
every combination. Multiple check entries OR together, so each combination
becomes its own must-not-reach check. Terms that are supersets of another are
dropped, since more negations describe a smaller set.

    (protocol:tcp;port:331)                       -> NOT port:331
                                                     NOT protocol:tcp

    (protocol:tcp;port:80|protocol:tcp;port:22)   -> NOT port:22 and NOT port:80
                                                     NOT protocol:tcp

    (protocol:tcp;port:80|protocol:udp;port:53)   -> NOT port:53 and NOT port:80
                                                     NOT port:53 and NOT protocol:tcp
                                                     NOT port:80 and NOT protocol:udp
                                                     NOT protocol:tcp and NOT protocol:udp

The second collapses from four raw combinations to two; the third needs all four,
and dropping any of them would admit traffic the cell forbids.

#### OFF by default

`bench/reach_csv_to_checks.py --complement`. Emitting these changes the check set
of every workload with a conditionally permitted cell, and therefore what those
workloads are expected to report — a decision per workload, not a silent upgrade.
Verified unchanged with the flag off: wl_ifi, wl_up and wl_stanford regenerate
byte-identical check sets, and wl_example's positive checks are identical
(10 checks; 14 with the flag).

#### Two defects it exposed, both fixed

**The `_expand_negations` collision** (the prerequisite). It keyed per-field
vectors by field NAME, so two negated fields of one name left only the last:
`[!80, !22]` returned exactly the vectors of `[!22]`, measured identical. The
error direction is a **false violation** — the survivor `¬22` is a strict
superset of `¬80 ∧ ¬22`, so port 80, which the cell *permits*, overlaps it and
the check fires. Several constraints on one field now INTERSECT (`_meet_all`),
with contradictory pairs dropped; an intersection that is empty contributes no
vectors at all.

**The report could not render a complement.** `reporting/reporter.py::_parse_cond`
asserted that any non-all-`x` field has a concrete value —
`assert value is not None  # a non-all-x field has a concrete value`. True of
every condition the suite could previously produce (a service names one exact
port) and false by construction of a complement vector, which pins one bit and
wildcards the rest. The report task died with a bare `AssertionError`, losing the
whole report for a run whose compliance check had already completed. Partially
determined fields now render as their bit pattern.

#### What it found on wl_example

wl_example is the only workload in the tree with service-conditional cells, so it
is the only one the flag currently changes. Run with it:

**261 violations, all on the single pair `office -> dmz`** — 253 naming
`packet.upper.dport`, 8 naming `packet.ipv6.proto`. Every complement vector
fires, which means the flow arriving at `dmz` from `office` is essentially
unconstrained in both fields: the data plane does **not** restrict that pair to
the services its policy permits.

**ROOT-CAUSED — it is a real modelling infidelity, not a toy-model shrug.**
The cause is the single rule

    ip6tables -A FORWARD -o 1 -s 2001:db8::200/120 -j ACCEPT

which implements `Office <->> Internet` by permitting the office subnet out
**port 1, the internet port**. Controlled experiment, using material already in
the tree: `rulesets/violation-ruleset` differs from `pgf-ruleset` in exactly that
line (commented out). Re-run with it, the office->dmz violations drop from **261
to 0**, leaving only the two expected `Office <->> Internet` failures that
ruleset exists to demonstrate.

**Why an `-o 1` rule permits traffic out port 2.** `devices/packet_filter.py`
wires the pipeline `forward_filter -> routing -> post_routing`, so the FORWARD
chain runs BEFORE the routing decision. At that point the packet's `out_port`
field is still wildcard, so matching `out_port = pgf.1_egress` does not fail --
it NARROWS the header space. The routing table then *writes* `out_port`
(`post_routing`'s own comment: "forward packets according to out port field set
by the routing table"; `AD6_PLAN.md` §9.10.2 says the same from ad6's side --
"a decision written by one rule (`Rewrite(out_port=...)` in `routing`) and READ
by a later rule in the same device"), overwriting the narrowing. The rule
therefore reduces to *"accept anything sourced from 2001:db8::200/120"*.

Linux is the other way round: netfilter routes before the FORWARD chain, which
is what makes `-o` meaningful there. **Any `-o` match in a FORWARD rule is
therefore inert in FaVe's model**, and the direction of the resulting error
depends on the target -- `-j ACCEPT` over-permits, `-j DROP` over-restricts.
Tracked as its own item in `TODO.md`; it is a modelling question for FaVe, not
something wl_cloud should decide.

One caveat on presentation, separate from the cause: 261 violations of what is
essentially one fact is a poor way to say it. When many complement vectors fire,
the useful report is "this pair is reachable outside its permitted services", not
an enumeration of bit patterns. Worth a summarising renderer before this is
turned on for any workload with a large matrix.

### 1.9.4 What the throwaway inventory produced

A fabricated inventory for the six queries — one role per endpoint host carrying
its real /30, one service per port named by the oracle — compiled against all
three operators:

| operator | outcome |
|---|---|
| `--->` | compiles; **crashes at check time** on `f=provider:` (F1) |
| `<-->` | **refuses to compile**: `Fehler: Service Internet.S332 unbekannt.` (F2) |
| `<->>` | **compiles cleanly, no `provider` operand** — its forward call passes no condition |

`<->>` is therefore the only operator that works with services today.

**The number that matters for provenance.** Five policy rules become **60 checks**
(9 must-reach, 51 must-not-reach); `<->>` gives 61. Six of those correspond to
oracle statements. **So ~54 of 60 expectations would be self-derived** — an order
of magnitude more than the third-party ones, which is what makes §1.9.0's
provenance labelling structural rather than tidy-minded.

Also observed, and to be decided rather than inherited: the diagonal fills with
`X` self-reachability for every atomic role (added whenever `policy.strict` is
false), and `<->>` additionally emits a `related:0` must-not-reach on every
backward pair. The cloud model has **no state field at all**, so those conditions
name a field outside its mapping — worth measuring before relying on it, since
extending the mapping at check time is `AD6_PLAN.md` §9.29's territory.

The inventory itself is deliberately **not** committed: it would read as a live
input while the three items above are open. It is ~60 lines and reconstructible
from the tables in §1.4 and §1.9.0.

### 1.9.5 Still open

- [x] **What "the Internet offers anything" means — RESOLVED 2026-09-18,
      reading (a): every DECLARED service.** Implemented in `policy.py`
      (`INTERNET_ROLE`, honoured by `offers_service`, `offers_services` and
      `get_services`), 12 tests in
      `policy_translator/test/test_internet_services.py`.

      **Claas's argument, which is the whole reason for choosing (a) over
      "anything at all":** a service's conditions come from its inventory entry,
      never from its name. If a service did not have to be declared, its
      attributes could only come from a table of well-known names — HTTP would
      then always mean port 80, an HTTP service on port 123 would be unsayable,
      and a custom service (ABC on tcp/1234) could not be expressed at all. So
      every compliance-relevant service stays explicit in the inventory even
      when the Internet is the side offering it, and `Internet.*` picks up
      exactly those.

      Effect, measured:

          host2 <->> Internet.*   before:  X
                                   after:  (protocol:tcp;port:331|...332|...350|...351)

      and `Internet <--> host20.S332` now compiles, where it used to raise
      `Fehler: Service Internet.S332 unbekannt.` **Inert for existing
      workloads** — no policy in the tree names a service on the Internet side
      or uses a wildcard service, so nothing that compiled before compiles
      differently.

- [x] **Switch wl_cloud to the FPL route — DONE 2026-09-21.** Five rules over a
      fabricated eight-role inventory, compiled with `--complement`, 71 checks.
      6/6 oracle verdicts still reproduced (§1.7.1). The inventory IS committed
      after all — the three blockers it was withheld for are closed, and
      `cloud_endpoints.role_members` refuses at run time any role that names no
      endpoint or declares an address its generator does not inject, so the
      fabricated half cannot drift from the model.

      Two things the shape forced, both worth keeping in mind for the 26x26
      matrix:

      * **A role must resolve to ONE name.** `reach_csv_to_checks` writes
        `s=source.<name>` and `p=probe.<name>` from the same inventory entry,
        and this dataset models a host as a `_tx`/`_rx` pair. `cloud_endpoints`
        folds them; the internet is the one pair folded by hand, its gateway
        being a device.
      * **`related:0` rides on every conditional check.** The cloud model has no
        conntrack, so `related` is declared in `FAVE_MAPPING` (not
        `CLOUD_MAPPING`, which stays the measured layout) and is wildcard
        everywhere — vacuous, which is the right reading for a stateless model.
        Declared up front rather than added by `_update_mapping` at check time,
        which is §9.29's hazard.

- [x] **`policy_builder`'s catastrophic backtracking — FIXED 2026-09-21.**
      Found while writing the inventory: `comment_pattern` was
      `[ \t]* \# [ \t]* .* <nl>`, where the second quantifier and `.*` both
      match the blanks after the `#`. The same language — `[ \t]*.*` accepts
      exactly what `.*` accepts — but one extra way to match EVERY comment
      line, so a run of them before a definition had 2^n parses to explore
      before it could fail. Measured: 10 lines 0.06s, 16 lines 0.20s, 20 lines
      2.08s, 24 lines over two minutes; and blank lines made it WORSE (three
      blank-separated blocks of 8 measured 31.8s), because they are another
      alternative in the same group.

      The redundant quantifier is gone. The same overlap one line lower —
      `[ \t]* = [ \t]*` against a `value_pattern` that contains a space, so
      every attribute line doubled the search space of its role — is made
      POSSESSIVE rather than deleted, because that quantifier is what keeps
      the blanks out of the captured value. 200 comment lines and a
      100-attribute role are now both flat.

      **No policy in the tree changes.** All seven committed inventory/policy
      pairs (wl_example, wl_ifi ×2, wl_up, wl_i2, wl_stanford, wl_cloud)
      compile to a byte-identical matrix and roles dump. One input does change
      meaning, deliberately and under test: `key =   ` followed by nothing but
      a newline used to parse as an attribute whose value is a single space —
      an artifact of the backtracking — and is now a syntax error. No
      inventory has such a line.

      The guards run the parse in a SUBPROCESS with a hard deadline. An
      in-process budget cannot fail when the defect is present: the old
      patterns take longer than any run will wait, so the test hangs instead of
      reporting, and a signal handler does not help because `re` matching is
      one C call that never yields to Python. Verified inverted — against the
      shipped patterns the suite now fails in 60s where it previously hung.

      wl_cloud's FPL files were written thin as a workaround; that is undone,
      and they now carry their full rationale.

- [x] **Parsed mechanically out of `README.txt` — DECIDED 2026-09-21**
      (`bench/wl_cloud/cloud_readme.py`). §1.8 leaves no real choice: 676 matrix
      cells copied by eye is `oracle.json`'s original defect at a hundred times
      the scale, and one flipped cell becomes a wrong expectation that FaVe then
      agrees with. Nothing is defaulted — an unrecognised preamble line, a
      non-square matrix, or a service whose `#n` disagrees with its list is
      refused rather than skipped.
- [x] **The 26th index IS the Internet — CONFIRMED FROM THE DATA 2026-09-21,
      so `Internet` is a role the dataset NAMES.** Four independently derived
      sets coincide exactly, all equal to
      `{0, 1, 8, 10, 11, 13, 14, 18, 19, 22, 23}`:

      | derivation | what it reads |
      |---|---|
      | matrix row 25 | the README |
      | the 43 ACL rules with **no source constraint** | `network.tf` |
      | the 19 destination-NAT rules at the gateway | `network.tf` |
      | the 14 source-NAT rules at the datacenter cores | `network.tf` |

      Any one alone would be a coincidence; four is an identification, and
      `test_cloud_readme.py` asserts all four so the reading cannot rot. This is
      what lets wl_cloud's policy be third-party evidence instead of a
      fabrication — the inversion of §1.9.4's "~54 of 60 self-derived".

---

### 1.9.6 C7 DONE — wl_cloud as an FPL policy (2026-09-21)

The workload now goes through PolicyTranslator like every other one, and
produces the `reachable.json`/`cchecks.json` that `apkeep_convergence.py`,
`apkeep_tum_diff.py` and `i2_structural_oracle.py` consume and it did not have.

**The premise changed, which is why this is smaller than §1.9.4 predicted.**
That section costed a FABRICATED inventory — a role per endpoint host, a service
per port — at ~54 self-derived expectations out of 60. None of that was needed.
`cloud-tf/README.txt` declares 25 services with their prefixes and a 26x26
authorisation matrix over them, and index 25 is the Internet (§1.9.5). The
roles, the services and the policy are all the dataset's; the only fabrication
left is how model endpoints are NAMED.

    README.txt --(cloud_readme.py)--> 26x26 matrix + service algebra
               --(cloud_policy.py)--> FPL inventory + two policies
               --(PolicyTranslator)--> reachability.csv  (676 cells)
               --(reach_csv_to_checks)--> checks.json    (4,224 checks)

**Shape.** 26 roles over **65 model endpoints**: one generator + one probe per
(service, leaf router) pair, 64 of them, plus the Internet. A service spans one
to nine leaf routers, so a role is not one place in the model. Derived two ways
that agree on all 40 leaves and all 64 pairs — the README's `Services of router
<id>` census, and containing each leaf's /25 (read off its core's routing table)
in a declared service prefix.

**Operators.** A service pair is realised as two independent ACL rules, one per
direction, each pinning its own destination port, so it becomes **two `--->`
rules** — 204 of them. The Internet pairs are different and `<-->` IS their
shape: inbound is DNAT + the source-less ACL on `dport=331+i`, outbound is the
cores' SNAT on `sport=331+i`. Destination port towards the provider, source port
away from it — exactly the direction resolution F2 added. 11 `<-->` rules, 215
in total, covering all 226 ordered 1-cells. **F1 and F2 are both load-bearing
here**, which is what C7 was waiting on.

#### Results — two policies, two measurements

| policy | checks | violations | expected | agrees |
|---|---:|---:|---:|---|
| `matrix/reach.txt` (matrix as written) | 4,224 | **1,315** | 1,315 | pair for pair |
| `matrix/reach_public.txt` (+ what the generator implemented) | 4,199 | **3** | 3 | pair for pair |

**The expectation is DERIVED, never counted off a previous run.**
`cloud_policy.expected_violations()` computes the (source endpoint, probe
endpoint) pairs a run should report, from the raw data alone: the Internet
against an endpoint the gateway does not publish (3, both policies — see below),
plus every denied cell into a public service (1,312, `matrix` only). Each run
compares its report against that set and stamps `expected_violations`,
`unexpected`, `missing` and `agrees`; a difference is logged loudly. Without
this, "3 violations" and "the RIGHT 3 violations" are the same sentence, which
is TODO item 1s's defect in miniature. It is deliberately not fatal — making the
bench tier exit non-zero on a wrong verdict is item 1s's job for every workload
rather than this one's.

**The 1,312 are the result, not a failure — and they were predicted exactly
before the run.** A service in matrix row 25 is one the Internet may reach; the
generator implements that as an ACL rule with **no source constraint**, which
admits every source. So all 11 public services are reachable from all 26 roles,
while the matrix authorises 102 of those 286 cells. Expanded over endpoints that
is 1,312 device-level cells, and the run reports 1,312 — over **184 role pairs,
every one of which targets a public service, none of which the matrix
authorises**. Stating that in `matrix/reach_public.txt` makes the run clean, and the
delta between the two IS the finding: *the generated network does not enforce
its own matrix for the services it publishes.*

The matrix's private half, by contrast, is enforced **exactly**: 113 ordered
1-cells into source-constrained services, 113 source-constrained ACL rules, set
equality in both directions with no slack. That is what makes the public half's
gap a property of the generator rather than noise in the reading.

#### The 3 remaining violations — the dataset's, not the engine's

    source.internet does not reach probe.dc4_leaf0_svc11  (dport 342)
    source.internet does not reach probe.dc4_leaf4_svc01  (dport 332)
    source.internet does not reach probe.dc4_leaf6_svc23  (dport 354)

Services **1, 11 and 23 are the only PUBLIC services whose prefixes span two
datacenters**, and the gateway publishes only one prefix of each:

| service | declared | published to the Internet |
|---|---|---|
| 1 | `10.0.4.0/22` + `10.0.18.0/25` | `10.0.4.0/22` |
| 11 | `10.0.0.0/24` + `10.0.16.0/25` | `10.0.0.0/24` |
| 23 | `10.0.2.0/24` + `10.0.19.0/25` | `10.0.2.0/24` |

`network.tf` does carry a second NAT rule for each, pointing at the other
datacenter with a **byte-identical match** — but it is SHADOWED, and by Hassel's
own rule rather than by a choice made here: the vendored `tf.py` makes a rule
`affected_by` every earlier rule it intersects and subtracts that header space,
which for an identical match is total.

**The check that settles it.** The dataset ships the same network a second time,
as Z3-Datalog inside each `.smt2`. Its gateway carries **11** rules where the
`.tf` carries **14** — and reducing the `.tf` by the shadowing above yields
exactly those 11, identical, against all six instances. So the two encodings
agree, there is no engine disagreement to adjudicate, and the three endpoints
are unreachable in both. `fave/test/test_cloud_encodings_agree.py` pins it.

This is the MIRROR of the 1,312: the generated data plane is more permissive
than its own matrix for the services it publishes, and less permissive for the
three it splits.

**DECIDED (owner, 2026-09-21): the UNIVERSAL reading stays**, so these three are
a permanent expected result rather than an open question.
`reach_csv_to_checks` expands a role-level cell into a must-reach at EVERY
endpoint of the target role. The alternative was existential ("the Internet may
reach service 11" holds if it reaches any of its hosts), which would have made
these three green at the cost of weakening every must-reach check in every
workload — and the universal reading is what surfaced the finding at all.
wl_cloud is the only workload where the two differ, since these are the only
roles with a published/unpublished split. TODO item 16 is closed.

#### What it cost in shared code

- **`reach_csv_to_checks.py`: a denied cell now names EVERY endpoint of the
  target role.** It used the bare `target`, which the `for target in targets`
  loop above it had left bound to the last element — so a multi-device role was
  asserted unreachable at one endpoint and silently unasserted at the rest. Only
  reachable by a workload with multi-device roles in denied cells. **wl_up had
  40 such roles**: its check set moves 11,911 → 18,811, and **all 6,900
  previously missing checks PASS** (re-run 2026-09-21, zero violations), so
  nothing was hiding behind them — but they were not being asked. Every
  quoted wl_up check count predating this is a different denominator (TODO
  item 0a).
- **`reach_csv_to_checks.py --deny-per-service`, OFF by default.** A denied cell
  normally denies all traffic to the target, which is right where a role is a
  subnet. Where a role is a SERVICE two roles can name the same machines —
  services 2 and 3 are both `10.0.17.0/25`, separated only by TCP port — and the
  blanket reading makes such a matrix self-contradictory rather than strict: a
  row permitting service 2 and denying service 3 asks for a packet to arrive at
  those hosts and not arrive at them. Probe-side filtering would be the other
  resolution, but `netplumber/adapter.py` has `filter_fields` commented out
  (memory explosion) and never reads `match`, so the qualification lives in the
  check. The mirror-image constraint is on the generator, which pins
  `sport=331+i` — without it service 3's traffic satisfies service 2's ACL.
- **`related` is declared, not extended at check time.** Every conditionally
  permitted cell emits `f=related:0` and the cloud model has no state field —
  §1.9.4's open concern. Measured: the adapter WOULD cope (`_build_vector` ->
  `_update_mapping` -> `expand`), but `cloud_tf.FAVE_MAPPING` appends the field
  up front instead, at bit 128, leaving §1.1's measured layout untouched. Both
  phases read it: the two arrived at the same table independently and it is one
  table now. A session
  that silently changes its vector width partway through is not the thing being
  measured (AD6_PLAN.md §9.29). `related:0` is vacuous here rather than wrong —
  nothing sets the field, so it stays wildcard.

#### The defect that nearly shipped a wrong policy

A role whose FPL block failed to parse was **silently skipped**: the translator
exited 0 with a smaller inventory and a policy that compiled against what was
left. Eight of the 25 roles vanished on the first run because their description
contained a `+`, which `PolicyBuilder.value_pattern` does not admit. The matrix
came out 18x18 instead of 26x26 and nothing said so.

**FIXED 2026-09-21 (TODO item 15).** `PolicyBuilder._assert_every_block_parsed`
compares the blocks a file DECLARES against the blocks the parser produced and
raises naming each one skipped, and `policy_translator.py` now exits non-zero on
a `PolicyException` instead of printing and falling through — which had made
*every* policy error, not just this one, report success to its caller. The same
check also closes a second cause: `fpl_grammar.py` accepts `desc` and
`PolicyBuilder` does not, so a `desc` block used to vanish identically.

wl_cloud keeps its three guards anyway, because they check the other direction —
the emitter's charset is asserted against the value pattern, the translator's
role count is asserted to be 26, and the benchmark refuses to run if the FPL
names a different endpoint set than the model builds.

#### Provenance, stated

| expectation | source | count |
|---|---|---|
| the 26x26 matrix | `cloud-tf/README.txt` | 676 cells |
| service ports, prefixes, public addresses | `cloud-tf/README.txt`, cross-checked against `network.tf` | 25 services |
| the Internet role | matrix row 25, confirmed four ways against `network.tf` | 1 role |
| endpoint NAMES, and the (service, leaf) split | ours | 65 endpoints |
| the six oracle verdicts | the `.smt2` filenames | 6 queries |

The oracle phase is unchanged and still runs — `bench/wl_cloud/benchmark.py`
with no argument, 6/6 reproduced (re-verified 2026-09-21). It is the only part
of this workload whose expectations come from outside the repository, and the
policy phase does not replace it: intent and third-party verdict are different
kinds of evidence. `--policy matrix` and `--policy public` select the others,
and each stamps `eval/<engine>-<utc>_policy-<which>.json` recording which policy
produced the number.

**Still open from C7:** expressing the six oracle queries themselves as FPL
(owner direction 2026-09-21: matrix first, oracle queries as a follow-up — they
name individual hosts, so uniformity would cost seven fabricated roles
overlapping the service roles).

---

## 2. The Delta-net traces (`deltanet-NSDI17-dataset.tar.gz`)

11 CSVs of forwarding-rule updates, format `+<prefix>,<router>,<next_hop>,<N>`:

    +100.3.0.0/16,s10-1,s2-9,180

**Size is the binding constraint.** Uncompressed totals ~40 GB against 7.1 GB
free on the working box, so several files are not merely inconvenient but
physically out of reach:

| file | size | | file | size |
|---|---:|---|---|---:|
| airtel2-only-inserts | 1.2 MB | | rf3257 | 4.8 GB |
| airtel1-only-inserts | 1.2 MB | | rf6461 | 4.8 GB |
| airtel1 | 447 MB | | rf1755 | 2.1 GB |
| berkeley | 773 MB | | rf1755.links | 1.1 GB |
| berkley-…-random-remove | 773 MB | | airtel2 | **16.0 GB** |
| | | | inet | **14.4 GB** |

`berkeley.csv` and `berkley-ribs-add-random-remove-random.csv` are byte-identical
in size, supporting the reading that the latter is a churn-randomised derivative
of the former.

**In scope, and VENDORED** under `fave/bench/wl_deltanet/deltanet-traces/`
(2.4 MB, with its own `SHA256SUMS` and a README recording the scope and what is
known about the format): `airtel1-only-inserts.csv`, `airtel2-only-inserts.csv`.
They were copied out of the archive before it was deleted; nothing else from the
archive survives in the repository, and re-deriving anything else would need
Claas to supply the archive again.

**What the two traces contain is no longer stated here.** It is derived from
them by `fave/bench/wl_deltanet/deltanet_census.py` into
[`fave/bench/wl_deltanet/TRACES.md`](fave/bench/wl_deltanet/TRACES.md) and
pinned byte for byte by `fave/test/test_deltanet_census.py`, on §1.8's principle.
The headline: **38,100 inserts, 57 routers, 52 next-hops, 1,400 distinct
prefixes** — the same figures for *both* traces, not airtel2 alone — and prefix
lengths **14–32** (so genuine LPM).

Three figures this paragraph used to carry were measured by hand at vendoring
time and were wrong; `TRACES.md` records what each should have said. Two of them
are D1's subject and are corrected below.

**The paper itself arrived 2026-09-22** (Horn, Kheradmand and Prasad, NSDI'17,
supplied by Claas) and settles more than D1: it identifies
`airtel1-only-inserts.csv` as the published data-plane snapshot its §4.3.2
reports on, explains the node naming, and supplies the origin URL this document
had as lost. §2.3.

### 2.1 Why "static snapshot first"

An insert-only trace replays to a well-defined final FIB with no deletions. That
snapshot is a real-world 57-router IPv4 forwarding model the **existing** harness
can verify with no new metric and no adapter work — whereas the incremental
benchmark needs all three of:

- a **new metric** (per-update latency distribution), which §2 of `AD6_PLAN.md`
  (still open) would have to grow a second clause for;
- **APKeep incremental wiring** — `delete_rules` exists only on
  `NetPlumberAdapter`; the APKeep and ad6 adapters buffer the whole model and
  solve at `check_compliance`. APKeep supports incremental updates natively, so
  this is adapter work, not a research question;
- an explicit statement that **ad6 rebuilds per update**, which is a result
  rather than a gap (it is Factor A of `AD6_PLAN.md` §1.1 at the model-update
  level instead of the query level).

The snapshot also has a weakness worth stating up front: the data is pure L3
forwarding with **no ACLs**, so any compliance property has to be invented. That
makes it a reuse of the *data*, not a reproduction of the *experiment* — a
weaker claim than the cloud dataset's, and it should be written up as such.

### 2.2 Build plan — deferred until `wl_cloud` reaches C5

- [x] **D0** **The raw traces are vendored and checksummed** (2026-09-18).
      They had been extracted with ad-hoc `tar` commands existing nowhere in the
      repository, which would have left the whole Delta-net phase resting on my
      shell history; the archive has since been deleted, so that debt is now
      settled rather than merely noted. `deltanet-traces/` holds both CSVs, a
      `SHA256SUMS`, and a README recording the scope decision, the measured
      shape of the data and the unresolved fourth-column question.
      **Origin URL — CLOSED 2026-09-22.** It was recorded as lost ("nobody
      recorded it"); the paper's reference [14] is
      `https://github.com/delta-net/datasets`. Not verified as still live, and
      the archive's sha256 is what actually matters for re-derivation, but the
      provenance gap is closed.
- [x] **D1 — DONE 2026-09-22. The fourth field is a PRIORITY ENCODING LPM**, and
      the plan's own description of it was wrong in a way that would have
      propagated. See §2.3.

          priority = 5 * prefix_length + 100

      Exactly, on every row of both traces — **76,200 of 76,200**, no exception.
      Longer prefix, higher priority: the standard linearisation of
      longest-prefix match into a priority-ordered flat rule list.

      **The paper confirms it, twice** (Horn, Kheradmand and Prasad, *Delta-net:
      Real-time Network Verification Using Atoms*, NSDI'17 — supplied by Claas
      2026-09-22, after the measurement). §3 states the design: *"longest-prefix
      routing can be simulated by assigning rule priorities according to prefix
      lengths"*. §4.2 states it of this very data set: *"SDN-IP sets the priority
      of rules according to the longest prefix match where rules with longer
      prefix lengths receive higher priority"*. So `5*plen+100` is the concrete
      constant SDN-IP happened to use, and D1 is no longer an inference from two
      files — it is a measurement agreeing with the generator's documented
      policy.

      **The column therefore carries no information of its own.** Everything it
      states is already in the prefix, so a converter reads the prefix and
      ignores the column — which is the answer D1 was blocking on, and it means
      no converter has to decide what to do with an unexplained number.

      **It is asserted, not merely recorded.** `deltanet_trace.parse_trace`
      checks the identity on every row it reads and refuses the file otherwise,
      so a trace that encodes something ELSE in that field — an administrative
      distance, a metric, a timestamp — is rejected loudly instead of being read
      as an LPM tie-break it is not. A finding about two files becomes an
      assumption the moment a third arrives, and this is what keeps it from
      doing so silently. The parser refuses a withdrawal for the same reason:
      `*-only-inserts` is a claim about the data, and §2.1's whole static-first
      argument rests on it, so it is checked rather than trusted.

      **Two stated figures did not survive the measurement**, both in this
      document's §2 preamble and in `deltanet-traces/README.md`:

      | stated | derived | what happened |
      |---|---|---|
      | 18 distinct values in **180–220** | 18 values in **170–260** | the count was right, the range was not |
      | prefix lengths **14–25** | **14–32** | 14–25 is 12 lengths, and the same sentence says 18 values |

      The two were one error: the range 180–220 is exactly the priorities of
      /16 through /24, which is where 37,377 of the 38,100 rules sit. A sample
      of the common case was written down as the whole. /31 is the one absent
      length, which is why 18 values span 19 lengths — and had D1 been guessed
      from the stated range instead of measured, **9 of the 18 actual priorities
      would have fallen outside it**.

      A third figure, "1,400 distinct prefixes", was right about airtel2 and
      silent about airtel1, where it also holds.
- [x] **D2 — the census is DONE; the replay turned out to be vacuous.**
      `TRACES.md` reports it for both traces. **No insert ever overwrites a
      `(router, prefix)` an earlier one set** — 38,100 inserts, 38,100 distinct
      keys, in each file — and neither file contains a withdrawal. So no rule
      supersedes another, replay order cannot matter, and **the final FIB is the
      file**. D2 as written asked for a replay; the measurement makes it a
      census.

      Left open by this, and belonging to D3 rather than D2: rules per router
      run 100–1,400 (mean 668), so the model is markedly non-uniform.
- [~] **D3 — the INTERFACE half is DONE 2026-09-22 (§2.4). The property choice
      is what remains.** The topology is recoverable, exactly and with nothing
      invented, and the question as filed rested on a misreading of the data —
      mine, recorded here because it is the kind that survives by sounding
      obvious.

      **What I had wrong.** The previous revision of this item said "a row names
      a router and a next-hop and neither end's port, while FaVe's router model
      is port-based. That, not the fourth column, is what the converter has to
      invent." Every clause of that is false. `s<i>-<j>` is not a router, it is
      a **(switch, port) pair**, and both columns of every row name one. It is
      the paper's own device for modelling ports without a port field: Delta-net
      splits a switch into one graph node per input port its rules match — "if a
      switch s contains rules that can match three input ports, we encode s as
      three separate nodes" (§4.1) — which is exactly why Table 2 reports 68
      nodes for a 16-switch network. The count was in front of me from the
      first census and I read it as a name space rather than as a model.

      **What the data gives.** 16 switches, 26 undirected inter-switch links,
      68 ports, and **every switch with exactly `degree + 1` ports**: one per
      neighbour, plus port 1, which no inter-switch link ever lands on. Port 1
      is the external, border-router-facing port — the paper attaches a Quagga
      border router to each of the sixteen switches (§4.2) — and it is where
      traffic enters. Both traces derive the **same** topology, port map and
      homing; only the forwarding differs, which is what makes §2.3's
      differential clean.

      **The egress port is the one figure no row carries, and it does not need
      to.** The port `i` sends out of to reach `k` is the port `i` receives from
      `k` on, and the switch-level edge set is symmetric, so the map is total.
      `bench/wl_deltanet/deltanet_topology.py` derives all of it and REFUSES
      each invariant rather than assuming it — one link per switch pair,
      injective neighbour-to-port, symmetry, ports exactly `1..degree+1`, no
      intra-switch forwarding, no U-turn — because every one is a property of
      these two files and not of the format.

      **The sinks are answered too, and they are not a modelling decision.** A
      node receiving a prefix while carrying no rule for it is where that prefix
      is DELIVERED. Every one of the 1,400 prefixes terminates at exactly one
      switch, and **14 switches home exactly 100 each** — the paper's "each
      border router advertises one hundred IP prefixes" (§4.2). So an
      edge-to-edge property has both of its ends: traffic enters at port 1 and
      leaves at its prefix's home switch.

      **The property is DECIDED and BUILT — 2026-09-22, §2.5.** Owner's call:
      the reachability matrix, stated as an FPL inventory and policy. 16 roles,
      210 rules, **256 checks = 210 must-reach + 46 must-NOT-reach**, and
      **0 violations on NetPlumber**, verified non-vacuous by a mutation. The
      matrix avoids the all-reachable trap because s8 and s9 home no prefix, so
      30 off-diagonal cells are denials an over-approximating engine fails.
      It remains a **consistency property, not an oracle** — the expectation is
      derived from the same traces as the model. Recorded alongside it: the
      paper's own goals were forwarding loops and the link-failure "what if",
      neither of which is a reachability matrix, and §4.3.2 stays the sharper
      experiment for later.
- [ ] **D4** Static run on all three backends.
- [~] **D4 — NetPlumber DONE 2026-09-22 (§2.5): 256 checks, 0 violations, non-vacuous.**
      ad6 and APKeep are next, and §1.7's history says to expect both to find
      something.
- [ ] **D5** *Then* revisit the incremental benchmark, with D4's costs known.
      **D2 bounds what it can claim.** An insert-only trace that never
      overwrites a rule measures incremental FIB *construction*, not churn:
      nothing is ever withdrawn and nothing is ever revised. The members that
      would test withdrawal (`airtel1.csv`, `berkley-ribs-add-random-remove-
      random.csv`) went with the archive, so the churn axis needs Claas to
      re-supply it. Worth settling before D4 is costed, because it changes
      whether D5 is a benchmark or a sentence.

---

## 2.3 What the traces ARE, and the differential the pair affords

Not in the original plan; it fell out of D1's census (2026-09-22), and was then
substantially corrected by the paper Claas supplied the same day.

### The published snapshot, identified

`airtel1-only-inserts.csv` is not "an insert trace". It is the **consistent data
plane snapshot the paper's §4.3.2 reports on**, and three independently
published figures say so:

| the paper states | published | derived here |
|---|---:|---:|
| rules in the ONOS data-plane snapshot (Table 4) | 38,100 | **38,100** |
| queries posed on it, one per link (§4.3.2) | 158 | **158** |
| nodes (Table 2) | 68 | **68** |

**This is the first external check the Delta-net workload has, and it changes
what §2.1 could claim.** A mis-parse of the traces — a dropped rule, a
misread name space — would now be caught by something outside this repository.
It does NOT make the workload an oracle: the paper's results are query *times*,
not sat/unsat, so every correctness result here is still a consensus between
implementations in this tree. §0's first gap stays `wl_cloud`'s alone. The
distinction to hold is **the model is corroborated, the verdicts are not**.

Two further things the paper settles that this document had as unknown or
guessed:

* **the `s<i>-<j>` names.** The topology is AS 9498 (Airtel) emulated as
  **16 Open vSwitches**; the paper splits one switch into several graph nodes
  when its rules match on several input ports ("we report the number of graph
  nodes rather than the number of switches"). So `i` is the switch, `j` the
  per-input-port node, and 16 switches become 68 nodes. The §2.2/D3 "sinks" are
  graph nodes that terminate a link without carrying rules — a consequence of
  that split, not an anomaly.
* **1,600 vs 1,400 prefixes — ACCOUNTED FOR by D3's homing, not resolved.**
  §4.2 says each of the sixteen border routers advertises 100 prefixes,
  "resulting in a total of 1,600 unique (but possibly overlapping) IP
  prefixes". Both traces carry **1,400**, homed 100 apiece at **14** switches;
  **s8 and s9 home none**, and 2 x 100 is exactly the shortfall. So the gap has
  a shape rather than being a mystery. WHY those two have none — no border
  router attached, nothing advertised, or a distillation that dropped them —
  the data does not say. They are well connected (degree 7 and 6) but not the
  best connected: s2 has degree 8 and homes its hundred, so "pure transit"
  describes what they do rather than explaining it.

`airtel2-only-inserts.csv` matches on rules (38,100) and nodes (68) and carries
**155** links. The paper publishes one snapshot, so nothing states what its edge
count should be.

### Where the two traces come from — NOT two arbitrary routings

The paper's §4.2 gives the pair a cause, and it is not the one an earlier draft
of this section assumed. Both data sets are link-failure experiments on the same
emulated network: **Airtel 1** fails "a single inter-switch link at a time,
recovering each link before failing the next"; **Airtel 2** induces "all 2-pair
link failures... including their recovery". So the two are the same network
under two different failure-injection regimes, which is a sharper account of
their difference than "routed two ways" — and it explains why airtel2 exercises
fewer links in its snapshot.

It also raises a question D3 should settle rather than assume: the full traces
are enormous (Table 2: 14.2M operations for Airtel 1, 505.2M for Airtel 2) while
these files hold 38,100 rules each and no rule ever overwrites another. The
`-only-inserts` files are therefore a *distillation*, not a prefix of the trace,
and exactly how they were distilled is not stated anywhere available here.

### The differential

The two traces are the same network measured as set equality rather than
inferred from equal counts:

| the two traces agree on | identical |
|---|:---:|
| the 1,400 prefixes | yes |
| the 57 router names | yes |
| the 52 next-hop names | yes |
| the directed edge set | **no** — 158 vs 155 |

Of 38,100 rules each, 36,300 `(router, prefix)` keys are common — 3,300 of them
forwarding somewhere different — and 1,800 keys are unique to each side.

So every reachability difference between the two models is attributable to the
forwarding change alone, with the topology, the prefix set and the rule count
held fixed. That is a **stronger cross-engine test than either snapshot on its
own**:
three engines agreeing on one model is consensus on an answer, while three
engines agreeing on the DELTA between two models is consensus on a behaviour,
and the second is what an incremental claim (§0's third gap) actually needs.

It costs nothing extra — both files are already vendored, and D4 runs them both
regardless. It does not, however, manufacture an oracle: the differential is
still a consensus between implementations in this tree, which is §0's first gap
and only `wl_cloud` closes it.

---

## 2.4 The topology, derived (D3's interface half)

Derived by `bench/wl_deltanet/deltanet_topology.py`, rendered into
[`fave/bench/wl_deltanet/TRACES.md`](fave/bench/wl_deltanet/TRACES.md) and
asserted by `fave/test/test_deltanet_census.py`. Identical from both traces.

| | |
|---|---:|
| switches | 16 |
| inter-switch links (undirected) | 26 |
| ports | 68 |
| ports per switch | `degree + 1` |
| prefixes | 1,400 |
| switches homing prefixes | 14, at 100 each |

The model a converter can build from this, with nothing invented:

* a **device per switch**, with `degree + 1` ports;
* **port 1** external, facing the border router — the traffic source, and the
  only port no inter-switch link lands on;
* **ports 2..degree+1** one per neighbour, bijectively, so a port identifies
  its link;
* a **link** for each of the 26 pairs, its two port numbers recovered from the
  two directions of the symmetric edge set;
* a **rule** per row: at switch `i` port `j`, match the prefix, forward out
  `egress_port(i, k)` — the egress being the one figure no row states and the
  symmetry supplies;
* **delivery** at each prefix's home switch, where its rules stop.

What is NOT derivable, and would have to be invented if the property needs it:
the addresses behind each border router (the traces carry prefixes, not host
addresses), and any notion of an ACL — there are none (§2.1).

---

## 2.5 The property: a reachability matrix as FPL — and the goals it is NOT

Owner decision 2026-09-22: state the property as an **FPL inventory and
policy**, the `wl_cloud` route, and record separately that the paper's own
verification goals were different ones.

### What the paper actually verifies, and why that matters here

Two experiments, and neither is a reachability matrix:

| §  | goal | run over | scale |
|---|---|---|---|
| 4.3.1 | **forwarding loops** — "a common network-wide invariant" | the full traces, in file order | 14.2M / 505.2M operations |
| 4.3.2 | **"what is the fate of packets that are using a link that fails?"** | the data-plane snapshot we hold | **one query per link — 158** |

Pairwise reachability between externally-facing ports is **described but never
run**. Algorithm 3 computes all-pairs reachability — a Floyd–Warshall
adaptation over atoms — and the paper offers it as a capability that
"illustrates how Delta-net facilitates use cases beyond the usual reachability
checks", relevant "during pre-deployment testing". No all-pairs figure appears
in any table. Where that sentence points is worth noting: it cites the
**Datalog** line, references [17] and [33], which is the NoD family `wl_cloud`
comes from. The paper hands the edge-to-edge framing to the tradition
`wl_cloud` already covers rather than claiming it.

So this workload reproduces the **data**, under a property **we** chose. That
is a weaker claim than `wl_cloud`'s and it is to be written that way. §4.3.2
remains the sharper experiment and is the obvious next thing to build (D5 or a
successor), because it is the one property whose expected answer is not uniform
— measured here at 100–1,300 affected flows per link, median 200.

### Measured before choosing, because two of the three candidates are weak

| property | result, both traces | discriminating? |
|---|---|---|
| loop-freedom (§4.3.1) | **0 loops** | no — a negative property whose answer is "none" |
| edge-to-edge reachability, per prefix | **21,000 / 21,000 delivered**, 0 black holes | no — all-reachable |
| link-failure impact (§4.3.2) | 158 links, **100–1,300 flows each** | yes |

The middle row is the trap `AD6_PLAN.md` §5.5 C3 already records for wl_i2:
matching an all-reachable oracle "is guaranteed for any relaxed encoding and
therefore proves nothing". **The FPL matrix avoids it, and that is the point of
stating it at SWITCH granularity**: s8 and s9 home no prefix, so 30 of the 240
off-diagonal cells are must-**NOT**-reach, and an engine that over-approximates
fails them.

### The inventory and the policy

`bench/wl_deltanet/deltanet_policy.py` emits both from the traces on every run;
neither is hand-written, so both are gitignored and there is no tracked/derived
pair to keep apart the way §1.9.6 needs for `wl_cloud`.

* **16 roles**, one per switch — the networks behind its Quagga border router —
  and one model endpoint each. A role per *prefix* would be 1,400 roles and,
  since checks expand over endpoint pairs, about two million checks.
* **No services.** There are no transport fields anywhere in the data, so a
  service would be a condition the data plane cannot express.
* **No `ipv4`.** A homing switch stands for 100 prefixes and the attribute
  carries one; §1.9.6's rule is that it is emitted only when it is the whole
  truth. It also decides `_abstracts_a_subnet`, and a self-check would ask
  whether a border network reaches itself, which this data plane does not say.
* **119 rules** stating 210 ordered permissions: `s_i <--> s_j` for each
  unordered pair of addressable switches (91), and `--->` only from s8 and s9
  (28), which home no prefix and so can send but never receive.

  **Corrected 2026-09-22 after owner review.** The first version wrote all 210
  as `--->`, reasoning that "the two directions are different facts and stating
  them as one would assert a symmetry nothing here guarantees". That was
  borrowed from §1.9's `wl_cloud` rationale, where it is sound for two reasons
  that do not hold here — its ACLs are stateless, so a symmetric operator would
  have claimed something about conntrack, and its 26x26 matrix is genuinely
  asymmetric cell by cell. This matrix is symmetric wherever both ends are
  addressable, *by construction*, since this policy is what asserts it; and it
  carries no services, so there is no statefulness to misstate.
  `policy_builder` expands a serviceless `<-->` into the two unconditional
  permissions, and the compiled `reachability.csv` is byte-identical either
  way — verified, not assumed.

  The mix is worth more than the brevity: the 28 rules that **cannot** be
  written `<-->` are exactly the s8/s9 finding, and 210 identical-looking
  unidirectional lines bury it. `deltanet_policy.directed_pairs` expands the
  operators so the equivalence is asserted rather than trusted.

  `<->>` stays wrong for a third reason, and that one does hold: it makes the
  return direction conditional on RELATED,ESTABLISHED — connection tracking, in
  a data plane that matches nothing but a destination prefix.

Compiled: **256 checks = 210 must-reach + 46 must-NOT-reach** (30 ending at
s8/s9, 16 the diagonal).

### The model, and the one thing in it that is invented

| | |
|---|---:|
| devices (one per switch) | 16 |
| links (directed) | 52 |
| rules read from the trace | 38,100 |
| **delivery rules SYNTHESISED** | **1,400** |
| rules total | 39,500 |
| generators / probes | 16 / 16 |

**The port structure is not invented, and that is the difference from
`wl_cloud`** — whose `cloud_preparation` has to say "THE PORT STRUCTURE IS
INVENTED, AND THAT IS THE RISK" because the NoD transfer function has no
interfaces. Here every device, port and link is read off the data (§2.4).

**The delivery rules are the invention.** The trace carries inter-switch
forwarding only: a prefix's rules thin towards its home switch and stop, which
is how `homes()` finds the home. A packet therefore arrives and dies, and no
probe could ever fire. So one rule per prefix is added at its home switch,
forwarding out port 1 — what SDN-IP installs and the data set omits. Three
things keep it honest: it is **derived** from the homing (itself cross-checked
against the paper's "100 prefixes per border router"); it **shadows nothing**,
measured — no prefix has a single rule at its own home switch, on any port, in
either trace; and it is **counted separately** everywhere, because a rule total
that silently mixes 38,100 read rules with 1,400 invented ones is the figure
nobody can audit later.

### LPM: carried by the rule index, and NOT observable in the matrix

**FaVe does not reorder a table on its own.** Priority IS the rule index:
`build_model` assigns it longest-prefix-first, `netplumber/adapter`'s
`_calc_rule_index` shifts it (`rid << 12`) and hands it to NetPlumber, where the
lower index wins. Nothing downstream repairs a wrong order — which is exactly
what `np_preparation._reprioritise_fib_lpm` exists to fix for the workloads that
load raw tables in file order. This one emits the order directly, so that
function is not in its path.

Only two of the 1,400 prefixes nest inside another, and only one of those two
has an observable consequence:

| specific | container | homes | observable? |
|---|---|---|---|
| `117.53.131.0/24` | `117.53.128.0/20` | **s13 vs s2** | yes — 10 of 20 shared nodes forward them differently |
| `196.28.238.0/24` | `196.28.236.0/22` | s6 vs s6 | no — same egress either way |

**Measured 2026-09-22: inverting the ordering so the SHORTEST prefix wins still
yields 256 checks and 0 violations.** The matrix cannot catch a priority
inversion, because it asks an existential question per switch pair and a
misrouted prefix still leaves its 99 siblings arriving. That is the shape of the
wl_i2 defect `_reprioritise_fib_lpm` records, where 3,731 rules sat shadowed
behind a containing prefix and every number computed on them looked fine.

So the guard is a fast-tier test instead (`TestDeltanetLPM`), and it is a real
one: it resolves the model's own rules the way NetPlumber does — lowest matching
index wins, per in-port — and follows a packet addressed into the /24. Correct
ordering delivers it at s13; inverted, at s2. The test asserts both, so a `_walk`
that ignored the index could not pass it.

**This is an argument for §4.3.2 later.** A link-failure property is
path-sensitive and would notice; a switch-granularity reachability matrix
structurally cannot.

### Result — NetPlumber, 2026-09-22

**256 checks, 0 violations**, `report.md` present and the log carrying
`completed task check_compliance` (§3's guardrail).

**Verified non-vacuous rather than asserted.** Adding one rule the data plane
cannot satisfy — `s1 ---> s8`, a destination that homes no prefix — yields
exactly one violation, naming `source.s1` does not reach `probe.s8`, and the
check total stays 256 because the cell moves from the deny half to the permit
half. Not yet run on ad6 or APKeep; that is the next step, and §1.7's history
says to expect both to find something.

---

## 3. Guardrails carried over

Reused verbatim from `AD6_PLAN.md`'s cross-cutting section, because the failure
modes are the same:

- **A missing output file is not a clean verdict.** Confirm `report.md` exists
  and the log carries `completed task check_compliance` before believing any
  count (§9.34.3).
- **State the denominator.** Never compare totals across different query counts
  (TODO item 0a).
- **Every measurement-affecting choice is a stamped result field**, not an
  undocumented habit — including, for these workloads, the header layout of
  §1.1 and the node-class derivation of §1.2.
