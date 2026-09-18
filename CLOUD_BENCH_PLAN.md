# Benchmark-suite extension: the NoD cloud dataset and the Delta-net traces

**Status 2026-09-18 — `wl_cloud` built and running. All six third-party oracle
verdicts reproduced on NetPlumber (§1.7.1). ad6 refuses the workload for a
structural encoding reason (§1.7.2); APKeep under-approximates by 3 (§1.7.3).
Three defects fixed in shared code along the way (§1.6). Delta-net not started.**

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

**Open discrepancy, to resolve before trusting a disagreement.** The README says
the public TCP port is **331**; query 04 excludes `0x014B` = 331, consistent with
that; but query 03 is *satisfiable* with `dport = 0x014C` = **332**. Either the
encoding is off by one somewhere or the scenarios were generated by different
runs. This must be settled before any FaVe/oracle mismatch is attributed to
FaVe: an off-by-one in a port number is precisely the shape of bug that would
manufacture a false disagreement.

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
- [ ] **C7** Only then: express wl_cloud as an FPL policy — both the README's
      26x26 ACL matrix and the six oracle queries — so the workload goes through
      PolicyTranslator like every other one instead of hand-built checks.
      **Blocked on three work items, all found by trying it: §1.9.**

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
Whether it is *removable* — ad6's `<port>` text already accepts a `value/prefix`
form, so a prefix-capable `fieldmatch` may be reachable — is ad6-core work and an
owner decision, not something to slip in.

### 1.7.3 APKeep — drops all three reachable pairs

    - `source.q01` does not reach `probe.dc1_leaf5_host5_rx`
    - `source.q03` does not reach `probe.dc1_leaf0_host20_rx`
    - `source.q05` does not reach `probe.dc0_leaf1_host1_rx`

Exactly the three `sat` queries; the three `unsat` ones pass trivially, since
"unreachable" satisfies a must-not-reach check whatever the reason. So this is a
**pure under-approximation of 3**, which the project's own soundness gate
(`bench/apkeep_convergence.py`: "APKeep must never drop a pair that NetPlumber
reports reachable") forbids outright.

**Diagnosis (strongly supported, not yet proven by a controlled experiment):**
`apkeep/adapter.py` still reconstructs meaning from FaVe's device NAMES. It
branches on `model.node.split('.', 1)[0] == 'out'` / `'mid'` / `'in'` in at least
eleven places, decides whether a link is internal or external the same way
(lines 1214–1264, 1349–1351), and carries a literal workload sniff:

    self._stanford = any(d.split('.', 1)[0] == 'mid' for d in self._fwd_devices)

wl_cloud's devices are `core.` / `lin.` / `lout.` / `gw.`, so none of those
branches fires and the inter-device topology is never built. The rule tables
themselves ARE captured (`<node>.1` matches `fwd_tables`), which fits the
symptom: rules present, links absent, nothing reaches anything. That q05 — a
host-to-host query involving **no NAT at all** — also fails is what rules out
"APKeep cannot do NAT" as the explanation.

**This is the same defect class `AD6_PLAN.md` §9 spent an entire phase removing
from the ad6 adapter** — §9.25 names "a literal `if any(d.split('.', 1)[0] ==
'mid' ...)` workload sniff in the production path" among the things deleted. The
identical construct is still live in `apkeep/adapter.py:793`. A new workload with
different naming rediscovered it in a day, which is an argument for the workload
as much as a finding about the adapter.

**Not fixed here.** Doing to APKeep what §9 did to ad6 is a phase of work, and
the owner decides whether it is worth it. What this run establishes is the
evidence that it is the same problem.

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
workload produces neither. §1.7.3's APKeep under-approximation had to be reported
by hand for exactly that reason.

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
expectation *we* derived — and §1.9.2 shows there will be many. Unlabelled in one
table, a mistake in our own understanding freezes in and reads as authoritative
as the external verdicts, which is precisely the property §1.8 exists to protect.

### 1.9.1 F1 — `--->` with a service emits a condition that crashes the checker

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

### 1.9.2 F2 — choose an operator, knowing the backward check is ours, not the oracle's

**Measured, not argued.** The reverse direction of q05 — generator at
`dc0_leaf1_host1_tx`, probe at `dc1_leaf6_host2_rx`:

| reverse check | result |
|---|---|
| unconstrained | **reachable** |
| on TCP 350 | **not reachable** |
| on TCP 40000 | **not reachable** |

Because `dc1_leaf6`'s ACL has exactly three rules — `dst=10.0.7.0/25 dport=332
-> forward`, `dst=10.0.7.0/25 -> DROP`, `(any) -> default route`. Leaf6 publishes
**only port 332**, so reverse traffic gets in on 332 and nothing else.

That breaks both candidate operators, and the verified semantics say why:

| operator | forward | backward |
|---|---|---|
| `--->` | reachability + service conditions | **nothing emitted** — the denial comes from default-deny leaving the cell empty |
| `<-->` | same | same, **carrying the same service** |
| `<->>` | reachability with service | `{"state": "RELATED,ESTABLISHED"}`, **no service** |

- **`--->`** asserts backward unreachability *unconditionally*. FaVe's conditions
  are existential over header space (`hs_overlaps_arr`), so that means "no packet
  whatsoever from B reaches A" — and one does, on 332. Spurious violation.
- **`<-->`** asserts backward reachability *on the same service*, 350. Measured
  false. Also a spurious violation. It additionally **refuses to compile** unless
  both roles offer the service (`Fehler: Service HostA.S350 unbekannt.`), because
  the backward policy is added with the same `service_to`. `<->>` escapes this
  only because its backward policy carries no service at all.

So the real difficulty is not statelessness: **the oracle makes one directed,
service-scoped statement, while every FPL operator emits a directed pair.**
Whichever is chosen, the backward check asserts something the dataset never said,
and here it is measurably wrong in both directions.

That is survivable — §1.9.0's expectation table simply records the backward
violations as expected — but it means roughly half the generated checks are
self-derived, which is what makes the provenance labelling load-bearing rather
than tidy.

- [ ] Choose the operator, with the backward expectation stated explicitly for
      each rule and marked self-derived.
- [ ] Also fix, or document, `<-->`-with-service requiring both roles to offer
      it — today it is a parse-time refusal with a message that does not hint at
      the cause.

### 1.9.3 F3 — without a complement check, q04 silently weakens

`internet ---> host22.331` under default-deny *means* "only 331 gets in". But
`reach_csv_to_checks` emits only the **positive** check for a conditionally
permitted cell; its unconditional `! s=… p=…` branch fires only for cells with no
permission at all. So nothing would verify that 332, or anything else, stays out.

Routed through FPL as written, q04 degrades from *"nothing outside 331 enters"*
to *"331 enters"* — a strictly weaker statement than the `04.unsat.smt2` instance
asserts, and the oracle instance would be silently spent.

The engine offers no positive form: its only condition primitive is existential
overlap, with no universal counterpart (probe filters and header tests are
deactivated — `filter_expr = None`, and test-fields-only collapses to
`{"type": "true"}`, with an `XXX` comment citing memory explosion). So *"only
331"* is expressible **only** as *"nothing outside 331"* — a must-not-reach over
the complement. That is not a stylistic choice; it is the sole mechanism.

- [ ] Emit the complement check for conditionally permitted cells in
      `reach_csv_to_checks.py`. The `f=!field:value` syntax and its adapter-side
      expansion already exist (§1.6b/c).
- [ ] **Prerequisite:** fix `NetPlumberAdapter._expand_negations`, which keys its
      per-field vectors by field NAME. For a cell permitting alternatives —
      `(protocol:tcp;port:80|protocol:tcp;port:22)`, whose complement is
      `¬80 ∧ ¬22` — the second `packet.upper.dport` silently overwrites the
      first, so half the complement would be checked while the output looked
      complete. Multiple check entries OR together, so the intersection must be
      materialised as a union of arrays: pairwise intersection of the two
      expansions, unsatisfiable pairs dropped.
      **This is not hypothetical and not deferrable: `wl_example` has such a cell
      today**, so the generator change would misfire on the smallest workload in
      the suite the moment it lands.

wl_cloud itself stays clear of that case — its ACL matrix is boolean (26x26 of
0/1, 25 declared services) and each oracle-derived service cell is a single
service on a distinct role pair — but the generator change is suite-wide.

### 1.9.4 Still open

- [ ] Is the 26x26 matrix parsed mechanically out of `README.txt` (per §1.8), or
      written as FPL by hand with a script checking it against the README?
- [ ] The matrix is 26 wide but only 25 services are declared (0-24). The 26th
      index is probably the internet/public, given the public IP and TCP/331 —
      **to be confirmed from the data, not assumed**, since it decides whether
      `Internet` is a fabricated role or one the dataset names.

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

The airtel2 insert trace measures: **38,100 inserts, 57 routers, 52 next-hops,
1,400 distinct prefixes**, prefix lengths 14–25 (so genuine LPM). The fourth CSV
field takes 18 distinct values in 180–220; its meaning is **not yet established**
and must not be guessed at in a converter.

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
      **Still open:** the archive's origin URL, which nobody recorded.
- [ ] **D1** Establish the meaning of the fourth CSV field before writing any
      converter.
- [ ] **D2** Replay `airtel2-only-inserts.csv` into a final FIB; report the
      router/prefix/rule census.
- [ ] **D3** Decide the property (edge-to-edge reachability matrix vs
      loop-freedom) and whether the topology can be recovered from the
      `next_hop` column alone.
- [ ] **D4** Static run on all three backends.
- [ ] **D5** *Then* revisit the incremental benchmark, with D4's costs known.

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
