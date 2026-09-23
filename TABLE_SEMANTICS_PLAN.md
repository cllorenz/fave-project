# Declared table semantics: making FaVe's implicit first-match contract explicit

**Status 2026-09-23 — DESIGN AGREED, NOTHING BUILT.** This document records a
design discussion with the owner and the measurements taken during it. No code
has changed. It is the sibling of [`CLOUD_BENCH_PLAN.md`](CLOUD_BENCH_PLAN.md)
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

## 8. A defect found during this discussion (not yet filed)

Tracing whether `FilterElement` could carry VLAN — the blocker recorded in
`_first_match_devices`' docstring — turned up a live inconsistency:

* `_filter_rule_string` already emits a **VLAN slot** (token 17), always `null`.
* **BDD honours it.** `FilterElement.encodeOneRule` -> `ACLRule` (parses the VLAN
  token, `ACLRule.java:216`, P9a) -> `ConvertACLRule` (conjoins it, including
  comma-separated VLAN sets, P7b).
* **NDD ignores it.** `NddReachabilityEngine.ruleToNDD` reads tokens 6-15 and 18
  and never touches token 17; the `+ acl` branch adds `vlanPred(t[17])`
  explicitly, the `+ filter` branch does not.

Measured on the real wl_tum model, forcing the slot to `10` and pinning the
arrival VLAN:

| engine | slot `null` | slot `10` | |
|---|---|---|---|
| BDD | vlan10 reachable, vlan20 reachable | vlan10 reachable, **vlan20 NOT** | honoured |
| NDD | vlan10 reachable, vlan20 reachable | vlan10 reachable, vlan20 reachable | **ignored** |

It costs nothing today only because the adapter always writes `null`. Anyone
"fixing" `_filter_rule_string` in the obvious way would get a correct BDD model
and a silently over-permissive NDD one. **The fix is the two lines the adjacent
`+ acl` branch already has**, plus a differential test asserting both engines
agree on a VLAN-qualified filter rule — which the two-engine differential of
CLOUD_BENCH_PLAN.md §2.9 would now catch and would not have caught a week ago.

Worth doing independently of this plan, and a prerequisite for ever declaring
`admission` (§7.2).

---

## 9. Build plan

Deliberately sliced so the channel is proven end-to-end before anything is built
on it.

**S1 — the channel.** `AbstractDeviceModel.table_semantics` + `semantics_of()`
defaulting to `FIRST_MATCH`; `to_json`/`from_json` round-tripping overrides only.
No producer, no consumer. Test: existing model JSON is byte-identical.

**S2 — one producer, one consumer.** `np_preparation` sets `lpm` on wl_stanford's
`mid` and wl_i2's `out` tables, replacing `fib_table_types`' name-prefix match;
`_is_dst_lpm_table` becomes a cross-check that refuses on conflict. Test: the
declaration survives aggregator dispatch into the adapter, and wl_stanford /
wl_i2 reachability is unchanged on all three backends.

**S3 — delete what it replaces.** `_reprioritise_fib_lpm` moves from generation
time into the NetPlumber and ad6 adapters; `wl_deltanet`'s `sw.` prefix and
`_DEVICE_PREFIX` go away. Test: wl_deltanet's model is unchanged apart from
device names, and the LPM walker test (`test_deltanet_model.py::TestDeltanetLPM`)
still passes.

**S4 — the checks.** Declarability and ambiguity in the aggregator, with the
§4.1 caveat in the docstring. Expected to find nothing (§2.6); the test is what
gives them value.

**S5 — the rich models.** `RouterModel` and the packet-filter model declare their
`routing` table `lpm` (§7.3), which is where §2.5 says the coverage is.

Anything beyond S5 — group identity, `admission`/`permutation`, retiring the
remaining name tests — is gated on §7.1 and on the APKeep `FilterElement` VLAN
work, and should not be started with this plan as its justification.

---

## 10. Provenance

Every figure in §2 was measured on 2026-09-23 against the working tree at commit
`a6516457`, by ad-hoc scripts over `bench/*/routes.json`,
`bench/*/topology.json`, the device models and the two engines' Java sources.
**None of it is currently re-derivable from a committed script** — that is a gap
against the owner principle (CLOUD_BENCH_PLAN.md §1.8), and S4's tests are the
intended place to close it, since they measure the same properties.
