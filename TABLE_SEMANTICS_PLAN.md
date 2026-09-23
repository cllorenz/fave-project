# Declared table semantics: making FaVe's implicit first-match contract explicit

**Status 2026-09-23 — BUILT. Every step of §9 is done** (step 0, S1+S2, S4,
S3a on both positional backends, S3b, S5), each gated on `./test.sh fast` and
`./test.sh integration`. The declaration now reaches the engines, both
positional backends order a declared-LPM table themselves, and the
generation-time repair is gone. Still open, deliberately: the group-identity
question (§7.1) and the `admission`/`permutation` vocabulary, which has no
consumer until the APKeep `FilterElement` work.

**What it cost to be right, recorded because the pattern repeated.** The channel
was silently dropped at **two of its four boundaries** (§9.3); a NetPlumber
harness reported the exact number a broken ordering produces and was itself
broken (§9.6); a test compared positional rule NAMES and would have passed
against any implementation (§9.5); and two claims in this document -- that four
device models would drop the field (§9.3), and that the packet filter's routing
table is a FIB (§9.7) -- were disproved by measuring them. Every one was caught
by a control run or a deliberately-failing assertion, and none by reading.

It is the sibling of [`CLOUD_BENCH_PLAN.md`](CLOUD_BENCH_PLAN.md)
(the benchmark axis) and [`AD6_PLAN.md`](AD6_PLAN.md) / [`APKEEP_BACKEND.md`](APKEEP_BACKEND.md)
(the backend axis) for the *model* axis: what a FaVe table means, and who is
allowed to decide it.

**The thesis, in one paragraph.** Every table in FaVe is implicitly first-match.
Nothing states it, so a table whose real semantics is something else — a FIB
resolved by longest prefix, an ingress admission list — has to be *preprocessed
into* first-match order before it enters the model, and every backend adapter
has to *re-derive* what it originally was. Two of three backends happen to share
the implicit default (NetPlumber resolves priority by rule index, ad6 is
first-match in document order), so the assumption stayed invisible until APKeep
arrived with a destination-prefix trie, for which it is wrong. The proposal is
to state the default explicitly on every table, let a benchmark declare only the
exceptions, and move enforcement out of the model and into the adapters.

---

## 0. Owner decisions (2026-09-23)

1. **Special semantics are flagged in the model, not enforced there.** The model
   records what a table *is*; it does not reorder, re-prioritise or otherwise
   normalise it.
2. **The adapter implements the declared semantics, or rejects it.** Sorting an
   LPM-declared table so a first-match engine resolves it correctly is the
   *adapter's* job, because the need is backend-specific.
3. **The default is explicit and total.** Every table is first-match-wins unless
   overridden. A benchmark states only its exceptions.
4. **The default is filled in during modelling** — in the device models — so no
   producer has to write `first_match` anywhere.
5. **Order-validation is OUT** (see §4). Checking early that an LPM table
   *happens* to be in longest-prefix-first order contradicts decisions 1 and 2.
6. **`fib_table_types` and `table_semantics: lpm` stay two different things**
   (2026-09-23, after the wl_cloud example below). The first is a *repair
   instruction* -- "run the prefix-length re-prioritisation over these tables";
   the second is a *semantic claim* -- "this table resolves by longest prefix".
   They coincide for wl_stanford, wl_i2 and wl_deltanet and **diverge for
   wl_cloud**, which declares `core`/`lin`/`lout` for the repair while 382 of
   those rules match more than a destination. **wl_cloud declares no `lpm`
   table.** Owner: *"I do not want to fiddle with wl_cloud's semantics... The
   benchmark authors chose this form and we need to have faith in the
   correctness of the authors' modeling step. We can assume first-match
   semantics and digest the tables accordingly even though this might pose a
   challenge for the APKeep adapter."*

---

## 1. Why: the implicitness has a traceable cost

Three artefacts in the tree exist only because table semantics are unstated:

| artefact | what it is |
|---|---|
| `bench/np_preparation.py::_reprioritise_fib_lpm` | LPM had to be **encoded into** first-match order, then repaired at generation time |
| `fave/apkeep/adapter.py::_is_dst_lpm_table` | the adapter **infers** whether a forwarding table is a trie or a first-match list, because nothing tells it |
| the 12 `in.`/`mid.`/`out.` name tests in `apkeep/adapter.py` | table roles inferred from **device names**, the only channel available |

The cost is not hypothetical. `_reprioritise_fib_lpm`'s predecessor hardcoded
`dev.startswith('mid.')` and therefore did nothing at all on wl_i2, whose FIB is
the `out` stage — **every FaVe+NetPlumber wl_i2 number was computed on a non-LPM
forwarding model, with 3,731 rules shadowed by an earlier containing prefix**
(AD6_PLAN.md §5.5). The repair was to make FIB-ness a *declaration*
(`fib_table_types` in the benchmark's `config.json`) with a hard error on
omission. That fix is the direct ancestor of this plan, and §3 explains why it
only went half the distance.

**Why APKeep felt it and the others did not.** FaVe's implicit semantics is
first-match. NetPlumber resolves rule priority by rule index; ad6 evaluates a
table first-match-wins in document order (measured — `ad6/test/core/
instantiatortest.py::RuleOrderSemanticsTest`). APKeep's `ForwardElement` is a
destination-prefix trie that resolves LPM natively and ignores order entirely.
It was the first backend for which the unstated assumption was false.

---

## 2. Measurements taken during the design discussion

All figures below were measured on 2026-09-23 against the current tree, and are
the evidence the design rests on. Re-derive before trusting.

### 2.1 The two benchmark families are real, and MIXED

| benchmark | device models |
|---|---|
| `wl_cloud` | 86 switch |
| `wl_stanford` | 48 switch (3 stages x 16 routers) |
| `wl_i2` | switch (2 stages x 9 routers) |
| `wl_deltanet` | 16 switch |
| `wl_ifi` | **1 router** + 16 switch |
| `wl_up` | **1 packet_filter + 135 host** + 23 switch |

Raw-table benchmarks arrive already decomposed from their source configurations;
rich-model benchmarks supply device models that FaVe decomposes itself. **But no
benchmark is purely one or the other** — wl_ifi is one router among sixteen
switches, wl_up is 136 filter-ish devices among twenty-three switches. The split
is per-device, not per-benchmark, which is an argument for per-table metadata on
the model over extending the per-benchmark `config.json`.

### 2.2 LPM lives in different tables, and the declaration is what finds it

wl_stanford's generated `routes.json`, rules ordered by rule index, counting
inversions against longest-prefix-first:

| stage | devices with dst routes | inversions |
|---|---:|---:|
| `mid` (**declared** FIB) | 16 | **0** |
| `in` | 8 | 137 |
| `out` | 5 | 4 |

`_reprioritise_fib_lpm` repaired exactly the declared tables and correctly left
the others alone. **The 137 and 4 are not defects** — those stages are genuinely
first-match, and their order is load-bearing.

### 2.3 The raw data was never LPM-ordered; a LOADER was

The raw HSA dataset is in file order, shortest-prefix-first. Vanilla NetPlumber's
`--load` front-inserts every rule, which reverses file order into longest-first;
the FaVe fork's list->map `--load` keys priority by the stored rule id and lost
that reversal, which is why `_reprioritise_fib_lpm` had to exist. **The semantics
were carried by an implicit insertion order inside a third-party tool** — even
more fragile than a naming convention, and worth remembering as the failure mode
this plan is meant to end.

### 2.4 Every benchmark is currently LPM-clean, so this is a GUARDRAIL

Per device, rule-index order vs longest-prefix-first:

| benchmark | devices with dst routes | not LPM-ordered |
|---|---:|---:|
| `wl_cloud` | 86 | 0 |
| `wl_up` | 24 | 0 |
| `wl_ifi` | 17 | 0 |
| `wl_deltanet` | 16 | 0 |
| `wl_example` | 3 | 0 |

**Nothing is broken today.** This plan prevents a recurrence of the wl_i2 defect;
it does not repair a live one. It should compete for time on those terms.

### 2.5 The rich models do not enforce LPM, and the coverage is not where it looks

`RouterModel` emits `for idx, route in enumerate(self.routes)` — the rule index
is the caller's list position. No sorting, no validation, no declaration. wl_up's
`pgf.uni-potsdam.de` routing table expresses LPM by **hand-picked magic
indices**: 23 x /64 at priorities 0..22, one /48 aggregate at 65534, the default
at 65535.

But the coverage of a router-model feature would be almost nil:

* **`RouterModel` instances in the whole benchmark suite: 1** (wl_ifi's `ifi`).
* wl_up has **zero** routers. Its dst routes sit on **23 switch models + 1
  packet_filter**.

So "teach the rich router model to mark and enforce LPM" would cover one device
in one benchmark. The feature is right; aim it at the **packet_filter's routing
table** (where wl_up's only non-trivial LPM structure lives) and at whatever
produces routes for plain switches.

### 2.6 What validation would actually catch

Splitting the two checkable properties, measured:

| check | wl_stanford `mid` (declared FIB) | wl_cloud | all others |
|---|---:|---:|---:|
| rules with non-dst match fields (**not trie-able**) | 0 | **382** on 41 devices | 0 |
| pure-dst rules **ambiguous** (same prefix, differing action) | 0 | 0 | **0** |

* The **declarability** check is already implemented, in one adapter:
  `_is_dst_lpm_table` is exactly what catches wl_cloud's 41 devices and routes
  them to a first-match `FilterElement`. Centralising it is a refactor, not a
  feature — its value is that all three adapters would then see the same answer.
* The **ambiguity** check finds **nothing, anywhere**. It is sound and cheap and
  worth keeping, but it is a guardrail for a future dataset, not a repair.

### 2.7 Structural facts that shape the implementation

* Tables are created **lazily**: `devices/router.py` alone calls
  `self.tables.setdefault(...)` at lines 215, 258, 294 and 317, during
  `to_json` and during ACL/route persistence. A default dict materialised in
  `__init__` would silently miss them.
* **30 test modules** read generated model/topology JSON. Emitting a semantics
  entry for every table would move all of them.
* `self.tables` is a bare `Dict[str, List[Rule]]` on `AbstractDeviceModel` —
  there is **no per-table attribute channel at all** today. `SwitchModel.table_ids`
  is the only per-table side-channel and carries an integer for NetPlumber's
  table numbering.
* The **APKeep adapter reads `model.type` zero times**; the NetPlumber adapter
  uses it (`model.type == 'router'`). The device-level metadata channel exists
  and one adapter ignores it in favour of table-name suffixes
  (`.forward_filter`) and device-name prefixes.

---

## 2.8 The case that settled it: wl_cloud mixes forwarding and filtering

45 of wl_cloud's devices carry a table holding both. `lin.dc1_leaf0`, as it
ships (`cloud-tf/network.tf` lines 615/676/678, node `1100001`) and as FaVe
models it:

| idx | match | action | meaning |
|---:|---|---|---|
| 1 | `ipv4_dst=10.0.4.0/25`, `ip_proto=6`, `tcp_dst=332` | forward | permit the one service |
| 2 | `ipv4_dst=10.0.4.0/25` | *(none)* = drop | deny the rest of that subnet |
| 3 | *(matches everything)* | forward | otherwise, pass on |

*"Traffic to this leaf's subnet is allowed only on TCP port 332; anything else
to that subnet is dropped; anything not for that subnet goes to the core."*

**Rules 1 and 2 match the SAME prefix and do opposite things.** Longest-prefix
-match cannot resolve that pair -- there is no longer prefix to prefer -- so only
their ORDER decides, and the permit must come first or the service disappears.
The table is genuinely first-match and merely happens to be written in
destination-prefix terms: an ACL with a default route as its last line, not a
FIB with an ACL bolted on.

§9.4's two checks reject it on **two independent grounds**, and both are right:
rule 1 matches more than a destination (declarability), and rules 1 and 2 share
a prefix while disagreeing (ambiguity).

**The repair has never reordered anything in wl_cloud.** Measured by
instrumenting a full regeneration: **zero cross-class promotions**. Rules 1 and 2
tie at /25 and the default sorts last anyway, so sorting by prefix length leaves
the table exactly as written. (`cloud_preparation` discards the promotions report,
so had there been any, nobody would have seen them.)

This is the same benchmark-shape question as §2.1: wl_cloud arrives semi-modelled
from raw configuration, and the modelling step is the authors'. The tables are
correct as written; reordering them would be the defect, not the fix.

---

## 3. Why `fib_table_types` went only half the distance

The existing mechanism is the right idea and is **not name-free**:

```python
def fib_tables(routes, fib_table_types):
    return {r[0] for r in routes
            if r[0].split('.', 1)[0] in set(fib_table_types)}
```

It declares which **name prefixes** are FIBs. The naming convention survives, and
it *spreads*: `wl_deltanet` is sixteen flat switches with no stages at all, and
was given `STAGE_SWITCH = 'sw'` / `_DEVICE_PREFIX = STAGE_SWITCH` purely so a
stageless workload could participate in a stage-prefix mechanism. A new workload
having to adopt a convention it does not need is the clearest evidence the
mechanism is in the wrong place.

It is also consumed **only at generation time**, by `np_preparation`. By the time
a model reaches an adapter the declaration is gone, which is precisely why the
APKeep adapter re-derives it from device names. **This plan is the completion of
that mechanism, not a new one.**

---

## 4. The correction: what "validation" may and may not mean

An earlier draft of this proposal had the model or aggregator validate that a
declared-LPM table *is in* longest-prefix-first order. **The owner rejected it,
correctly**: if the adapter implements the semantics — sorting for a positional
engine, ignoring order for a trie — then checking the order early is either
vacuous or it silently reinstates the positional assumption that decisions 1 and
2 exist to remove. One cannot hold both "order is not the model's business for
this table" and "the model checks the order".

The inverse is the actual payoff, and it was under-sold: **declaring a table LPM
is what frees its order from carrying semantics.** Today order is load-bearing
*and* undeclared, which is the worst combination. Once declared:

* `_reprioritise_fib_lpm` stops being a generation-time repair; the NetPlumber
  adapter reorders at translation time, where it belongs.
* The vendored raw order survives into the model untouched — **better** for the
  re-derivability discipline (CLOUD_BENCH_PLAN.md §1.8), not worse.
* An **undeclared** table stays first-match, so its order remains load-bearing and
  must be preserved verbatim. That is the correct treatment for wl_stanford's
  `in`/`out` stages (§2.2).

What survives, in two different places:

| where | question | nature |
|---|---|---|
| model / aggregator | **declarability** — does every rule in an LPM-declared table match only a destination prefix and carry a forward-or-drop action? | backend-neutral property of the rules |
| model / aggregator | **ambiguity** — do two rules share a prefix and length but differ in action? Then order decides, so the LPM declaration is false. | backend-neutral, falsifies the declaration |
| adapter | **implementability** — can *I* express this? | per-adapter by nature; the refusal path |

Neither central check asks about order. That question only has meaning once a
positional backend has been chosen.

### 4.1 The honest limit

Validation **cannot catch a wrong declaration in the ambiguous case**, which is
the case that matters most. `np_preparation` already documented it: a FIB with a
discard aggregate (`10.0.0.0/8` DROP ahead of a `10.240.0.0/12` forward) and a
genuine deny-before-permit filter have **identical shape**. That is exactly why
FIB-ness was made a declaration rather than an inference.

So the declaration's correctness is not machine-checkable in general. The
mechanism's real contribution is that a *missing* declaration is loud and a
*grossly wrong* one is caught. **A passing validation must never be read as
evidence that a table really is a FIB**, and that sentence belongs in the code.

---

## 5. Scope: what this does NOT fix

The declaration is **intra-table**. It states how rules within one table resolve
against each other. It says nothing about:

* how tables **compose** into a device pipeline (`_build_pf_pipeline`, the
  `in.` -> `mid.` -> `out.` chain);
* a rule's **ingress dependence** (`_gate_dead_ingress`, and the whole
  ingress-accounting contract of CLOUD_BENCH_PLAN.md §2.7/§2.8);
* which **device** a stage belongs to (`'out.' + router`, recovered today by
  string surgery);
* whether a workload's semantics exceed a backend's primitives (`self._stanford`).

Mapped onto the twelve name tests in the APKeep adapter:

| kind | sites | retired by this plan? |
|---|---:|---|
| role classification (`mid` = FIB, `in` = admission, `out` = permutation) | 5 | **yes** |
| workload sniff (`self._stanford`, `_i2_faithful`) | 3 | no |
| cross-stage joining / edge classification | 4 | no — unless the declaration also carries a **group identity**, see §7 |

It also does **not** help wl_stanford's in-stage, whose problem is not resolution
order: its VLAN match is dropped by `_translate_fwd_rule` (2,063 rules collapse
to 52; 16 of 22 elements hold a single default route), and the target primitive
cannot carry it. **Declared semantics are bounded by what the primitives can
express.** A `role: admission` tag would be a correct declaration that APKeep
must then refuse — still far better than today's silence, but not a fix.

---

## 6. Design

### 6.1 Carry overrides only; default on read

Store nothing for the common case and default at the accessor:

```python
# AbstractDeviceModel
self.table_semantics: Dict[str, str] = {}      # OVERRIDES ONLY

def semantics_of(self, table: str) -> str:
    return self.table_semantics.get(table, FIRST_MATCH)
```

Two measured reasons (§2.7) to prefer this over materialising the default:

1. **Tables are created lazily** in at least four places in `router.py` alone. A
   dict populated in `__init__` would miss them, and a *missing* flag in a design
   whose premise is totality is the worst possible failure mode. Defaulting on
   read is total by construction.
2. **`to_json` emits the dict only when non-empty**, so every existing benchmark
   serialises byte-identically and none of the 30 JSON-reading test modules move.
   Only wl_stanford's `mid` and wl_i2's `out` gain an entry. The precedent is
   `SwitchModel.table_ids` ("always bound (None when absent); to_json emits it
   only when truthy").

It belongs on `AbstractDeviceModel`, which gets all seven table-building device
models at once.

The default is **safe, not merely conventional**: on a table whose rules are
disjoint, first-match is indistinguishable from any other resolution, so stamping
it changes nothing where it does not matter.

### 6.2 Division of labour

| component | responsibility |
|---|---|
| device models | fill the default; record an override when the producer declares one |
| aggregator | **carry** the declaration through dispatch; run the declarability and ambiguity checks |
| NetPlumber adapter | honour `lpm` by assigning rule indices longest-prefix-first at translation time |
| ad6 adapter | honour `lpm` likewise — it is first-match in document order, so it needs the order too |
| APKeep adapter | **ignore** `lpm` (its `ForwardElement` trie resolves it natively); cross-check against `_is_dst_lpm_table` and refuse on conflict |

**The aggregator must not normalise.** It would have to act before knowing which
backend is attached, it would hand APKeep a reordered table it does not need, and
it would make the in-memory model no longer a faithful record of the source
configuration.

### 6.3 The prize: inference becomes cross-check

Today `_is_dst_lpm_table` decides alone and is right by luck of shape. With a
declaration it becomes *declared LPM, **and** the shape agrees* — and a
disagreement is a **refusal**, not a silent choice. That is the
`UntranslatedSemantics` / `ACCOUNT_COMPLETE|APPROXIMATE` pattern
(CLOUD_BENCH_PLAN.md §2.7) applied one level earlier, and it is what would have
caught the wl_i2 shadowing at the time rather than years later.

---

## 7. Open questions

1. **Does the declaration carry a group identity too?** `'out.' + router`
   recovers the mid<->out correspondence by constructing a name. A role tag
   cannot express a *relationship*. Carrying `{'role': ..., 'group': 'bbra_rtr'}`
   would turn the string surgery into a lookup and retire four more name tests —
   but it makes the mechanism richer than "table semantics", and that is a
   decision to take up front rather than bolt on.
2. **What is the vocabulary?** `first_match` and `lpm` are needed. `admission`
   and `permutation` are implied by wl_stanford's other two stages but have no
   consumer until the APKeep `FilterElement` can carry VLAN on both engines
   (the NDD gap of §8). Adding a term with no
   consumer risks a declaration nothing honours.
3. **Who writes it for rich models?** `np_preparation` is the obvious producer
   for raw-table benchmarks. For `RouterModel`/`PacketFilterModel` the model
   itself knows its `routing` table is a FIB and could set it unconditionally —
   which is takeaway (1) of the discussion, applied where §2.5 says the coverage
   actually is.

---

## 8. Step 0 -- the `+ filter` VLAN slot. FIXED 2026-09-23.

Tracing whether `FilterElement` could carry VLAN -- the blocker recorded in
`_first_match_devices`' docstring -- turned up a live inconsistency, now fixed.

### What it was

* `_filter_rule_string` emits a **VLAN slot** (token 17), always `null`.
* **BDD honoured it.** `FilterElement.encodeOneRule` -> `ACLRule` (parses the
  VLAN token, `ACLRule.java:216`, P9a) -> `ConvertACLRule` (conjoins it,
  including comma-separated VLAN sets, P7b).
* **NDD ignored it.** `NddReachabilityEngine.ruleToNDD` reads tokens 6-15 and 18
  and never touched token 17; only the `+ acl` branch conjoined
  `vlanPred(t[17])`.

So one rule string meant two different things depending on the engine. It cost
nothing while the adapter always wrote `null`, and would have cost a silently
over-permissive NDD model the moment anyone emitted a real tag.

### The fix

Both branches now share one helper, `withVlanSlot(hit, t)`, rather than the
`+ acl` branch carrying its own copy -- the two having private copies is what let
them drift. `ndd/src/main/java/org/ants/jndd/fave/NddReachabilityEngine.java`.

Verified by construction: `test/test_ndd_vlan_slot.py` (6 tests, integration
tier) **fails on the pre-fix jar and passes on the fixed one**, checked by
reverting the source, rebuilding, and re-running. The assertion that guards the
defect is the *differential* -- either engine alone can be self-consistently
wrong, and it was the divergence that made this a defect rather than a choice.

### The trap: the FIRST measurement of this was confounded

The table this section used to carry was measured **at a probe**, and is not
evidence for what it claimed:

| engine | slot `10`, arrival vlan=20 | |
|---|---|---|
| BDD | unreachable | |
| NDD | reachable | reported as "NDD ignores the slot" |

**The NDD engine existentially quantifies VLAN out of any device whose name
starts with `probe.`** (a host on an access port receives the frame untagged),
and it does so *before* the `target_vlan` arrival constraint is applied. So a
test that pins the arrival VLAN at a probe cannot observe a VLAN constraint on
NDD **whatever the filter rule says** -- it measures the untag, not the slot.

The code reading was sound and is what the fix rests on: before the change,
nothing in the `+ filter` path referenced `t[17]`. The *measurement* was not.
`test_ndd_vlan_slot.py` therefore routes to a destination deliberately **not**
named `probe.*`, and its docstring records why.

### Still open, and NOT part of step 0

The confounded measurement uncovered a second, genuine divergence that the fix
does **not** address: **BDD does not untag probe VLANs, NDD does.** The two model
the same intent by different mechanisms -- the adapter sets `target_vlan=0` at
faithful-wl_stanford probes, which BDD enforces as a real constraint while NDD's
untag makes it vacuous. Both are gated green today, and the divergence is
unobservable wherever nothing constrains VLAN (every plain-mode workload). It is
recorded here rather than chased: it belongs to the faithful-VLAN path, not to
the declaration channel, and it needs its own measurement before anyone decides
which engine is right.

---

## 9. Build plan

Sliced so that the channel is proven end-to-end before anything is built on it,
and so that the one risky step is verifiable by construction rather than by
hoping the tests cover it. **The order below revises an earlier draft** (S1..S5
in sequence); the two changes are that the checks move ahead of the migration,
and that the migration splits in two. Both changes follow from §9.1.

### 9.1 The constraint that shapes the order: `rule.idx` does two jobs

In the NetPlumber path a rule's index is simultaneously:

* **priority** -- `jsonrpc.add_rule(socks, t_idx, r_idx, ...)` is called with
  `r_idx = _calc_rule_index(rule.idx)`, and NetPlumber resolves priority by that
  index (lower wins);
* **identity** -- `delete_rules` looks up
  `self.rule_ids[_calc_rule_index(rid, t_idx=tid)]`, keyed on the model's
  `rule.idx`, to find the handles to remove.

`_reprioritise_fib_lpm` makes the two consistent by **rewriting the idx field**
at generation time (`routes[p] = (t[0], t[1], new_idx, t[3], t[4], t[5])`).

**So S3 is a decoupling, not a move.** The good news is that the mapping layer
already exists: `add_rule` *returns* an NP-assigned `r_id` and `self.rule_ids`
maps model-idx -> handles, so an adapter can pass a reordered `r_idx` for
priority while continuing to key `rule_ids` on the model's own idx for identity.
No redesign of rule identity is required -- but the step must be scheduled as a
decoupling, and that is why it is split and why the checks precede it.

**Open risk, to be decided before S3b.** `_calc_rule_index` shifts by 12 bits and
those 4,096 slots between consecutive rules are reserved for negation expansion
(`n_idx`), not for new rules. An **incremental insert** into an already-built LPM
table therefore has no priority headroom without renumbering. Irrelevant to the
static benchmarks; a real question for the continuous-verification path, and S3b
is where it stops being hypothetical.

### 9.2 Step 0 -- the NDD VLAN slot (§8). FIRST, and independent.

The only thing in this package that is **wrong today**: BDD honours filter token
17, NDD silently ignores it. Two lines mirroring the adjacent `+ acl` branch,
plus a differential test asserting both engines agree on a VLAN-qualified filter
rule. It surfaced during this discussion but depends on nothing in it, and it is
a prerequisite for ever declaring `admission` (§7.2). It jumps the queue because
it is a defect; everything below is a guardrail (§2.4).

### 9.3 S1 + S2 -- ONE landing, not two. DONE 2026-09-23.

`AbstractDeviceModel.table_semantics` (overrides only) + `semantics_of()`
defaulting to `FIRST_MATCH`, `to_json`/`from_json` round-tripping overrides;
**and in the same landing** one producer (`np_preparation` sets `lpm` on
wl_stanford's `mid` and wl_i2's `out`, replacing `fib_table_types`' name-prefix
match) and one consumer (`_is_dst_lpm_table` becomes a cross-check that
**refuses** on conflict).

Landed separately, S1 is unvalidated plumbing nobody reads. The single biggest
unknown is whether the declaration survives **aggregator dispatch** into the
adapters, and only a producer plus a consumer demonstrates that.

*Gates:* existing model JSON byte-identical (30 test modules read it, §2.7);
wl_stanford and wl_i2 reachability unchanged on all three backends.

#### What it took, and the two places it was silently lost

Landing them together was the right call for a sharper reason than "a channel
with no consumer cannot be validated": **the channel crosses four boundaries and
was dropped at two of them, silently, with the identical symptom each time** --
every table arriving as `first_match` and nothing raising. Only a probe of what
the ADAPTER received caught either; the serialised JSON was correct throughout.

| boundary | outcome |
|---|---|
| `SwitchModel.to_json` -> wire | carried first try |
| `AggregatorService._model_from_json` | **LOST** -- it is handed the whole COMMAND, whose own type is `topology_command`, so the device and its declarations sit one level down under `"model"` |
| `_sync_diff`: `add = model - self.models[node]` | **LOST** -- the engine is handed the DIFF, a different object, and there are **four** `__sub__` implementations (`AbstractDeviceModel`, `AbstractFirewallModel`, `RouterModel`, `SwitchModel`), none of which carried the field |
| `APKeepAdapter.add_tables` | now `lpm` on BOTH of the two calls each device gets |

Both fixes went to the **single consumer**, not the N producers: one restore in
`_model_from_json` (recursing through the wrapper), one carry at the sole
`model - model` call site. Eight independent `from_json` methods and four
`__sub__` methods would each have to remember; one call site stays right when a
ninth or a fifth is added. That is the same reasoning twice, and it is the
transferable lesson of this slice.

#### Result

```
wl_stanford   mid = lpm (16)    in/out = first_match (32)
wl_i2         out = lpm  (9)    in     = first_match  (9)
```

Each tracks **its own** `config.json` rather than a hardcoded name -- which
makes the wl_i2 defect (`dev.startswith('mid.')` doing nothing at all, 3,731
rules shadowed) structurally impossible rather than merely fixed.

#### A claim of mine that was wrong, corrected

This document and two code comments asserted that four device models would
silently drop a base-class field because they "override `to_json` without
chaining". That was a `def to_json` grep that never checked class membership.
**All five `AbstractDeviceModel` subclasses carry it** -- `SwitchModel` and
`RouterModel` chain, `PacketFilterModel`, `ApplicationLayerGatewayModel` and
`SnapshotPacketFilterModel` inherit -- and the two apparent counterexamples,
`GeneratorModel` and `ProbeModel`, do not subclass `AbstractDeviceModel` at all,
so neither can reach `set_table_semantics`. The refusal guard in that method is
kept, and its docstring now says plainly that **it fires on nothing today**.

#### The consumer

`_is_dst_lpm_table` stops deciding alone: a device whose forwarding table is
DECLARED `lpm` is cross-checked against the rules, and a disagreement raises
`UntranslatedSemantics` naming the offending field. The converse is deliberately
not enforced -- an UNDECLARED dst-only table still becomes a `ForwardElement`,
because making the declaration authoritative for undeclared tables would change
every workload that declares nothing, and that belongs to §9.7.

`test/test_table_semantics.py`, 16 tests.

#### One regression it caused, and the assumption behind it

The first integration run after this landed was **22 failed, 13 errors**, all one
cause: `_capture_declared_semantics` called `model.semantics_of(...)`
unconditionally, and not every object reaching `add_tables` is an
`AbstractDeviceModel` -- the unit tests build models as `SimpleNamespace`. Fixed
by treating a missing `semantics_of` as "declares nothing", which costs no
coverage, because the cross-check only ever CONSTRAINS a table that was declared
and such an object cannot declare one.

The assumption worth naming: **an adapter entry point is not typed by the model
hierarchy**, and a new call on `model` there is a new requirement on every
producer, test fakes included. Cheap to find (the tier said so immediately) but
it would have been cheaper to look at `add_tables`' callers first.

---

### 9.4 S4 -- the checks. PROMOTED ahead of the migration. DONE 2026-09-23.

Declarability and ambiguity in the aggregator, with the §4.1 caveat in the
docstring. They belong **before** S3, not after it: they are what establishes
that a declaration is coherent before anything starts trusting it to drive
reordering. They are cheap, and §2.6 measured them as finding nothing -- which
makes them a clean baseline now, rather than noise arriving mid-migration.

#### What the two checks actually ask

* **declarability** -- every rule matches a destination prefix **and nothing
  else**. Deliberately narrower than the APKeep adapter's `_LPM_MATCH_FIELDS`,
  which also admits VLAN and `in_port` because APKeep handles those by other
  machinery: LPM is a statement about which rule WINS, so the neutral question
  is about the match alone. **Rewrites are not checked** -- they change what a
  rule does, never which rule wins. (Measured first: the declared tables carry
  3,372 VLAN rewrites on wl_stanford and 77,451 on wl_i2, so a check that
  rejected rewrites would reject both declarations.)
* **ambiguity** -- no two rules share a prefix and differ in action. A rule
  with no destination field matches everything and is keyed as the default
  route, so two disagreeing defaults are caught like any other pair.

#### Incremental, because rules arrive in batches

The index is carried per `(node, table)` across calls on the aggregator. Rules
arrive in batches and a collision between two batches is still a collision, but
re-scanning the whole table per batch would be quadratic -- wl_i2 sends 77,451.
Measured: wl_i2 replays in **7.0 s**, wl_stanford in 2.0 s.

#### Non-vacuous, and asserted to stay so

| workload | declared tables validated | rules validated |
|---|---:|---:|
| wl_stanford | 16 | 3,844 |
| wl_i2 | 9 | 77,451 |

Exactly the rule counts §2.6 measured from the raw data. A test pins these,
because §9.3 found the declaration silently dropped at two of four boundaries
and **a validation that runs over nothing passes just as quietly as one that
runs over everything**.

#### Both checks pass everywhere, which is what §2.6 predicted

They are a guardrail, not a repair. `test/test_table_semantics.py` gained 8
tests that fire them deliberately -- a non-destination match, two rules on one
prefix, colliding default routes, a collision spanning two batches -- plus the
one that matters for not over-refusing: **a discard aggregate is accepted**
(`10.0.0.0/8` drop ahead of a `10.240.0.0/12` forward), because those are
different prefixes and longest-prefix-match resolves them. Refusing that shape
would block every real FIB, which is the mistake `_cross_class_promotions`
records an earlier design making.

### 9.5 S3a -- adapters honour `lpm`, with generation-time reordering STILL ON. **DONE 2026-09-23, both backends.**

The NetPlumber adapter decouples the `r_idx` it passes to `add_rule` from the key
it uses in `rule_ids` (§9.1), and orders a declared-`lpm` table longest-prefix
-first at translation time. **ad6 must be covered in the same step**: it is
first-match in document order, so it consumes FaVe's ordering too.

With `_reprioritise_fib_lpm` still running, the reordering is **idempotent, so the
output must be byte-identical**. That turns the risky step into a free
differential: if adapter-side ordering is correct nothing changes anywhere, and
if it is not, the existing benchmarks say so immediately.

**The differential is only as good as the declaration ARRIVING, and §9.3 is why
that has to be asserted rather than assumed.** The channel was silently dropped
at two of its four boundaries, both times with no error. If a future boundary
drops it again, this step passes *trivially*: the adapter reorders nothing, the
generation-time repair does all the work, and the output is byte-identical for
the wrong reason. So S3a must assert a NON-ZERO count of declared tables reaching
the adapter (16 for wl_stanford, 9 for wl_i2) before comparing anything --
otherwise it is the "a skip is NOT a pass" failure in the shape this tree has now
hit twice, most recently as the wl_up differential that errored at setup in every
integration run while its number sat in a results table.

#### The decoupling was already structural

§9.1 expected this step to need one. It does not: `jsonrpc.add_rules_batch`
unpacks `_np_rid, t_idx, r_idx, ...`, so the tuple's **element 0 is the local
identity key** (`rule_ids`) and **element 2 is the index NetPlumber uses as
priority**. They were always separate slots -- only their VALUES were both
derived from `rule.idx`. `_prepare_generic_rule` now takes an optional priority
and uses it for element 2 alone.

#### Measured: the association is identical, the send order is not

On wl_stanford's 16 declared tables / 3,844 rules, with the RPC mocked so no
backend is involved:

| | |
|---|---|
| rule -> priority association | **identical** whether the adapter orders or the generator does |
| send order | **differs**, by construction |

The multiset comparison is the right one, and the sequence comparison is not:
`_reprioritise_fib_lpm` rewrites `idx` IN PLACE and leaves the rule list in file
order, while the adapter sends the sorted list. A second test asserts the send
orders DO differ, so the first cannot pass by the adapter quietly doing nothing.

#### The sort key is `(-prefix length, idx)`, not a stable sort

A stable sort on the list order is correct only while the generation-time repair
leaves the list in file order. After S3b `idx` is the file position again, and
this key reproduces the generator's assignment in both worlds: longest prefix
first, ties in the order the table was written.

#### §9.1's incremental question is now a refusal

Indices are dense (1..n), so a second batch for an already-ordered declared
table has no free index below an existing one and a longer prefix arriving late
would silently lose. `LpmOrderingError` instead. Measured: every declared table
in wl_stanford and wl_i2 arrives in **exactly one batch** today (16 of 16, 9 of
9), so this refuses nothing now and guards the continuous-verification path.

#### ad6 is NOT done, and S3b is blocked on it

`ad6/translate.py::table_to_ad6` already sorts rules by ascending `idx`, and its
docstring records exactly why: *"`np_preparation._reprioritise_fib_lpm` repairs a
FIB by REASSIGNING indices in descending prefix-length order, so the longest
prefix gets the lowest index and is evaluated first."* ad6 therefore **consumes
the generation-time repair**. Deleting it without teaching ad6 the declaration
reintroduces the wl_i2 defect in the one backend whose whole design point is
that it reads no names. `table_to_ad6` had no access to the model's declared
semantics, so the declaration is threaded to it through the adapter's `devices`
dict, and it sorts by the same `(-prefix length, idx)` key.

**Idempotence measured the same way:** all 16 wl_stanford declared tables /
3,844 rules order identically whether sorted by `idx` or by the LPM key.

**One test nearly shipped vacuous, and the reason generalises.** The first
version compared the rule NAMES ad6 emits -- but those are positional (`r0`,
`r1`, assigned AFTER the sort), so they are identical whatever the order and the
test would have passed against any implementation, including one that ignored
the flag. It compares the emitted destination addresses instead, and a companion
test asserts the flag DOES reorder a table whose `idx` does not carry the rank --
which is exactly the state S3b creates.

**Unrelated, pre-existing:** `test_ad6_translate.py` and `test_ad6_grounding.py`
cannot be collected in one pytest invocation (they are in different tier groups,
so nothing runs them together). Reproduced at HEAD with these changes stashed.

---

### 9.6 S3b -- remove the generation-time reordering. DONE 2026-09-23.

Delete `_reprioritise_fib_lpm` from the generation path, and with it
`wl_deltanet`'s `sw.` prefix and `_DEVICE_PREFIX`.

*Gated on S3a being green for **both** positional backends.* If only NetPlumber
honours `lpm` when the generation-time repair goes away, **ad6 silently regresses
into the wl_i2 defect** -- the exact failure this plan exists to prevent.

*Test:* wl_deltanet's model unchanged apart from device names, and
`test_deltanet_model.py::TestDeltanetLPM` still passes (item 12a's guard).

#### Three producers, not one

§9.6 assumed `np_preparation` was the only caller. There were three, and they
needed different treatment:

| producer | treatment | evidence |
|---|---|---|
| `np_preparation` (wl_stanford, wl_i2) | call removed; both stages already declare | NetPlumber recomputes wl_stanford's **165** pairs and wl_i2's **61** |
| `deltanet_preparation` | now DECLARES `lpm` on all 16 switches; call removed | backend differential passes |
| `cloud_preparation` | call removed, declares **nothing** (§0.6) | routes **byte-identical**, 1,741 rules |

#### Validation

* **wl_stanford on NetPlumber: 165 reachable pairs**, the reference figure, with
  the generation-time repair gone. The adapters now supply the ordering the rule
  index used to carry.
* **wl_i2 on NetPlumber: 61 pairs** -- and APKeep's 72 beside it is not a
  disagreement but the over-approximation `test_apkeep_i2` documents by
  construction ("it reports all 72 pairs reachable where the real data plane
  delivers 61"). Confirmed by a CONTROL rather than by reading: the pre-S3b
  inputs were reconstructed (repair applied, declarations stripped) and give
  **the same 61 vs 72**. S3b changed nothing here.
* **wl_cloud: byte-identical output**, confirming §2.8's measurement that its
  repair had never reordered anything.

#### The first NetPlumber harness was wrong, and it looked exactly like a regression

It reported 240 pairs -- every pair -- which is precisely what a failed LPM
ordering looks like. Running it against the PRE-S3b tree gave 240 as well, which
is what exposed it: `_not_reached` records that NetPlumber reports node **ids**
where APKeep reports names, so the violation set was empty and everything looked
reachable. Using the differential's own helper gives 165. **A number that
confirms the failure you are looking for deserves a control run before it is
believed.**

#### Five tests failed, and all five asserted the ABSENCE of the fix

That is the expected shape of this step, and each needed a different repair:

* `test_rules_are_ordered_longest_prefix_first` asserted the emitted INDEX
  carries the prefix rank. It now asserts that indices are unique and that the
  DECLARATION is present -- the property that replaced it.
* the two `TestDeltanetLPM` walk tests resolved by lowest index. They now
  resolve the way the backends do, longest prefix with the index as tiebreak.
  **The inversion guard had to change with them**: it inverted the INDEX, which
  the walk no longer reads, so it would have kept passing while guarding
  nothing. It inverts the RESOLUTION instead.
* the two S3a differentials compared the adapter's ordering against the
  generator's. With the generator no longer ordering there is nothing to match,
  so they assert the ordering is RIGHT -- non-increasing prefix length in the
  index NetPlumber receives and in the document ad6 emits.
* **wl_cloud's `TestLpmReprioritisation` is a semantic REVERSAL, not a repair.**
  It asserted that the repair made a longer prefix outrank a shorter one
  "regardless of file order". Under §0.6's reading that reordering is the defect:
  the table is first-match, so its file order IS its semantics. It now asserts
  the emitted index FOLLOWS the dataset, and its docstring carries both the
  reversal and the byte-identical measurement behind it.

Also chased rather than trusted: a "1 inversion" measured on `gw.internet` was an
artifact of the measuring script treating source-matching anti-spoofing rules as
having no destination. Identical before and after.

#### Deleted 2026-09-23, on the owner's instruction

`_reprioritise_fib_lpm`, `_cross_class_promotions` and their two now-orphaned
helpers `_net_of` and `_forwards` are gone, with the three test classes covering
them (fast tier 887 -> 879, exactly the 8 deleted tests). `_prefix_len`,
`fib_tables` and `FibDeclarationError` STAY -- the first two are used by
`bench/stanford_priority_check.py` and the third still guards the config
validation that produces the declaration.

**The prose needed more work than the code.** 21 references named the function,
and two were not merely dangling but stale:

* `test_table_semantics`' two class docstrings still said *"BOTH run for now"* --
  the S3a world, untrue since S3b.
* **`bench/stanford_priority_check.py` can no longer fail.** Its docstring
  claimed both columns reading 165 was "THE FIX LANDING, NOT THE CHECK GOING
  STALE", which held while a preparation-time repair pre-sorted `routes.json`.
  The NetPlumber adapter now orders declared tables at translation time, so it
  orders BOTH columns: the script's own local `_reprioritise` cannot change the
  answer and the A/B is a tautology. Kept for its narrative and its measured
  10 -> 165 result, with the docstring saying plainly **do not read a passing
  run as evidence of anything** and pointing at the live guards instead. Leaving
  a check that cannot fail is the "a skip is NOT a pass" shape this tree has now
  hit three times.

---

### 9.7 S5 -- the rich models. DONE 2026-09-23, and HALF of it was refused.

`RouterModel` and the packet-filter model declare their `routing` table `lpm`
(§7.3). **Last**, because §2.5 measured the coverage: exactly one `RouterModel`
exists in the whole suite, and wl_up's dst routes sit on 23 switches plus one
packet_filter. Its value is for the *next* benchmark, not this one.

#### Measured before declaring, and the packet filter did NOT qualify

The plan said "`RouterModel` and the packet-filter model declare their `routing`
table `lpm`". Only the router does.

| model | `routing` table's match fields | declared? |
|---|---|---|
| `RouterModel` (wl_ifi `ifi`) | 9 rules matching **only** `packet.ipv4.destination`, plus one default | **yes** |
| `PacketFilterModel` (wl_up `pgf`) | 25 rules matching `out_port` ALONE, 23 matching `out_port` + destination, 2 matching nothing | **no** |

A packet filter selects its egress with an `out_port` MATCH feeding the device's
internal pipeline -- which is what `apkeep/adapter._first_match_devices` already
says in prose -- so the table is not a destination-prefix trie and declaring it
would be false. §9.4's declarability check would refuse it, correctly. **The
plan asserted a property of that model that measuring disproved**, and the
declaration is worth exactly as much as the measuring behind it.

#### Coverage is one device, as §2.5 said

Exactly one `RouterModel` exists in the suite. The value is for the next
benchmark: a router built tomorrow declares its FIB without its producer having
to remember, and both positional backends order it.

#### One pinned snapshot moved

`test_models.py::TestRouterModel::test_to_json` compares the router's whole JSON,
so it gained the `table_semantics` entry. That is the ONLY generated-JSON
expectation this plan moved anywhere -- the overrides-only design (§6.1) kept
every model that declares nothing byte-identical.

---

### 9.8 What NOT to do

* **Not S1 alone** -- unvalidated plumbing nobody reads.
* **Not S3 before S4** -- reordering driven by a declaration nothing has verified
  is coherent.
* **Not S5 early** on the strength of "rich models should enforce LPM"; measured,
  that is one device.
* **Not new vocabulary without a consumer.** `admission`/`permutation` have none
  until step 0 lands and the `FilterElement` carries VLAN on both engines.
  Declaring a semantics nothing honours is the failure mode this plan exists to
  end.

Anything beyond S5 -- group identity, retiring the remaining name tests -- is
gated on §7.1 and on the APKeep `FilterElement` VLAN work, and should not be
started with this plan as its justification.

---

## 10. Provenance

Every figure in §2 was measured on 2026-09-23 against the working tree at commit
`a6516457`, by ad-hoc scripts over `bench/*/routes.json`,
`bench/*/topology.json`, the device models and the two engines' Java sources.
**None of it is currently re-derivable from a committed script** — that is a gap
against the owner principle (CLOUD_BENCH_PLAN.md §1.8), and S4's tests are the
intended place to close it, since they measure the same properties.
