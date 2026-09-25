# Unifying header-field handling in the FaVe-facing NDD engine

**Status: PLAN (2026-09-25).** Written after the fourth slot-drop defect of the
same shape. Scope set by the owner: **APKeep as a FaVe verification backend, not
as a standalone tool.**

---

## 1. The problem, in one sentence

A header field is not a thing the NDD engine *has*; it is a thing that must be
remembered in five places, and every defect in this class has been one of those
places forgetting.

## 2. The evidence

Four slot-drop defects have been found and fixed in this repository. Three were
NDD-only, and the fourth cost three times more to fix in NDD than in BDD:

| defect | NDD | BDD |
|---|---|---|
| item 23 step 0 — `+ filter` drops VLAN | **dropped** | honoured ("always did") |
| OUT_STAGE_PLAN sec. 4.2 — `+ nat … match` drops VLAN | **dropped** | honoured via `ACLRule` |
| the condition path — drops VLAN *and* flags | **dropped** | honoured |
| step 4 — `tcp_flags` absent from both | 3 call sites to edit | 1 edit |

That is not luck. It follows from the structure:

```
BDD   one parser.  ConvertACLRule ANDs eight field nodes:
        {protocolNode, srcPortNode, dstPortNode, srcIPNode,
         dstIPNode, vlanNode, relatedNode, tcpFlagsNode}
      6 callers, none of which handles a field itself.

NDD   four parse sites, three of which remember two helpers:
        200:  withFlagsSlot(withVlanSlot(ruleToNDD(t), t), t)     + filter
        225:  withFlagsSlot(withVlanSlot(ruleToNDD(t), t), t)     + acl
        271:  withFlagsSlot(withVlanSlot(ruleToNDD(body), body))  + nat … match
        455:  ruleToNDD(...)                                      conditions  <- the miss
```

**And the split is arbitrary.** `ruleToNDD` reads the 5-tuple *and* `related`
(token 18) inside itself; only VLAN (17) and flags (19) live outside. The
boundary is not "the classic quintuple versus the rest" — it is "whatever was in
the parser on the day the field arrived". VLAN was added for `+ acl` alone, later
extracted into a helper applied at the branches rather than folded in, and flags
copied that pattern.

## 3. What "handling a field" costs today

Adding one header field currently means touching, in order:

1. `_filter_rule_string` / `_acl_rule_string` — the emitter, a new trailing token
2. one or more of six field sets in `apkeep/adapter.py` —
   `_FILTER_MATCH_FIELDS`, `_LPM_MATCH_FIELDS`, `_LPM_REWRITE_FIELDS`,
   `_NAT_IP_FIELDS`, `_COND_SLOTS`, `_SUPPORTED_COND_FIELDS`
3. `_is_acceptall_filter_rule` — which reads slots positionally and treats an
   unknown one as a wildcard, i.e. silently widens (this bit us in steps 2 and 4)
4. NDD: a predicate builder, a `withXSlot` helper, and **every** call site
5. NDD: a new positional parameter on `isReachable` — which is why there are
   **four overloads** (`…, targetVlan`, `…, related`, `…, conds`)

BDD needs three edits, all inside two files: `ACLRule` (parse), `BDDACLWrapper`
(declare + convert + the field array).

## 4. Scope

**In:** `ndd/src/main/java/org/ants/jndd/fave/` (FaVe-only — verified, the sole
references are `fave/apkeep/lib_ndd.py` and `fave/apkeep/adapter.py`) and
`fave/apkeep/adapter.py`.

**Out:** `ndd/src/main/java/application/**` (the standalone NDD tool: `Main`,
`wan`, `batfish`, `nqueen`) and standalone APKeep's own input formats. Nothing
below changes them.

**Deliberately minimal on BDD.** It is already uniform, and `common/ACLRule.java`
+ `common/BDDACLWrapper.java` are shared with standalone APKeep, so changing the
grammar there carries risk the FaVe path does not need.

---

## 5. The plan

### Step 1 — fold VLAN and flags into `ruleToNDD`

Move `withVlanSlot`/`withFlagsSlot` inside, next to where `related` already is.
One parser per engine; all four call sites get every field.

This is also the fix for the condition-path defect — not as a patch, but as a
consequence of removing the asymmetry. The existing length guards
(`t.length > 17`, `> 19`) carry over unchanged and keep the shorter `+ acl`
layout (18 tokens, no rel/flags) working.

*Gate:* the three rule sites must produce **identical** predicates (pure
refactor, no verdict moves anywhere); the condition site must gain the
constraint — pinned by the divergence measured on a toy model:

```
traffic carries vlan 5, condition vlan=9   NDD True -> False   (BDD already False)
traffic has flags MSB 0, condition 1xxxxxxx NDD True -> False   (BDD already False)
```

Plus fast + integration, and wl_stanford 165/165.

### Step 2 — one declaration of the slot layout, per side

**Java:** replace the hand-written index reads with a single table —
`{slot, field, builder}` — and one loop over it. Adding a field becomes one row.

**Python:** derive `_filter_rule_string` *and* `_is_acceptall_filter_rule` from
one ordered spec, so an emitted slot is a parsed slot by construction. This is
the half that has bitten twice: an unrecognised slot in the accept-all test reads
as a wildcard, which makes a field-qualified rule look like a semantic identity
and lets `_elide_passthrough_filters` contract it away.

*Gate:* byte-identical rule strings on every workload (diff the emitted IR before
and after), and `_is_acceptall_filter_rule` unchanged on the existing cases.

### Step 3 — retire the `isReachable` overloads

`targetVlan` and `related` are arrival constraints, which is exactly what `conds`
already is. Express both as conditions and collapse four overloads into one.

Note `target_vlan` is now **dead in production**: item 27 removed the adapter's
only use, and it survives solely as a test affordance. `related` keeps its own
adapter-level path for the reason `_cond_related` documents (both engines carry
it as a single header bit and it cannot be rewritten) — that argument is about
the *adapter*, not the engine, and does not require a separate engine parameter.

*Gate:* `test_apkeep_compliance_cond.py` and `test_ndd_vlan_slot.py` unchanged in
outcome; the wl_up `related` checks (3,302 of them) unchanged.

### Step 4 — widen `_COND_SLOTS` to what the parser now handles

The payoff. *"Is X reachable from Y on VLAN 78"* is a meaningful question FaVe
currently refuses, and after step 1 it is safe to answer. Add VLAN and flags to
`_COND_SLOTS` and drop the corresponding refusal.

*Gate:* a conditioned-vs-seeded differential for the new fields, the way
`bench/apkeep_out_stage_oracle.py` does for dst — and it must **fail** before
step 1, or it is not testing anything.

*Note:* `test_apkeep_first_match.py::test_a_field_neither_engine_carries_is_refused`
is misnamed today — BDD *does* carry VLAN in a condition, and since step 4 both
engines carry flags. The refusal is about `_COND_SLOTS`, not about engine
capability. Rename it with the step, or delete it if the refusal goes.

### Step 5 — the grammar itself (NOT scheduled)

The root cause is that the rule string is a Cisco ACL line with fields bolted on
the end as optional trailing tokens, chosen so the historic 14-token format kept
parsing. That puts every new field at a position only *some* readers know about.
A keyed encoding (`vlan:78 flags:1xxxxxxx`) or a fixed full-width layout would
retire the defect class outright.

It is **not scheduled** because it touches `common/ACLRule.java`, which
standalone APKeep shares, and the owner's priority is the FaVe path. Steps 1–2
get most of the benefit at none of that risk. Recorded so the remaining
fragility is a stated bound rather than a surprise.

---

## 6. Order and expected effect

| step | effect | risk |
|---|---|---|
| 1 | closes the condition-path defect; one parser per engine | low — pure refactor at 3 of 4 sites |
| 2 | adding a field becomes one row, not five places | low — gated on byte-identical IR |
| 3 | four overloads become one; deletes a dead parameter | low — `target_vlan` is already unused |
| 4 | VLAN/flags-conditioned checks become expressible | medium — new capability, needs its own oracle |
| 5 | retires the class | not scheduled — touches shared standalone code |

Steps 1–3 are refactors with no intended verdict change on any workload; step 4
is the only one that adds behaviour.
