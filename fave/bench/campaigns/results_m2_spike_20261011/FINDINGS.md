# Findings: the M2 packet-filter spike (dev), 2026-10-11

`INCREMENTAL_PLAN.md` §8, step 1. This run was exploratory, used this machine, and is not reportable. The tool is
`spike.py` (this directory). It regenerates the packet-filter model after every
edit of a seeded stream and counts the rules an engine must delete or insert:
- under **dense** indices, which is today's scheme;
- under **stable renumbering by alignment**;
- and against the **floor**, the smallest change any order-preserving alignment allows.

`PROTOCOL.txt` was committed (`dca21368`) before R1–R4 ran, and its addendum
(`04a58cf3`) before R5/R6. The four runs before it (wl_up api-web, wl_example pgf,
wl_up pgf, wl_tum; 30 random edits each) are exploratory and not scored. They
agree with R1: stable == floor on all 120 edits.

## The question, and the answer

*Can a modelling engine's output keep rule indices stable under single-rule
firewall edits?* **Yes, but not as a pure function of the ruleset. Stability
needs the previously emitted model.** The packet filter numbers its rules by
position. It renumbers every chain densely (`generator.py:598`), and then the
interwoven table too (`_interweave_state_shell`, `:511`). Its internal spacing
`2·idx·n + r.idx` (`:420`, `:500`) depends on the table size `n`. A ruleset
says nothing about which rule "was" where before an edit. So any stable
scheme has to remember the last emission.

**The mechanism, stable renumbering by alignment,** works per table:
- Align the new rule list with the last emitted one by **content**. The content is the
  table, in-ports, match and actions. It excludes `idx` and the raw-line metadata,
  which no engine reads.
- Matched rules keep their index.
- A run of new rules takes evenly spaced free indices between its neighbours.
- When a run does not fit its gap, the smallest window around it is relabelled
  to half the nominal spacing (R4c, below).

Nothing in this is specific to the packet filter. The mechanism preserves order by
construction (the tool asserts it after every emission), and its cost is per
device (20 ms on wl_tum's 5,108 rules).

## Results (engine-rule changes per edit)

| run | ruleset (engine rules) | edits | dense median / max | stable median / max | floor median / max | stable == floor | relabelling |
|---|---|---:|---:|---:|---:|---:|---|
| R1 | wl_up pgf (2,056) | 500 random | 2,521 / 4,078 | **2 / 4** | 2 / 4 | 500 / 500 | none |
| R2 | wl_up pgf | 200 at one line | 3,356 / 6,095 | 2 / 7,289 | 2 / 1,184 | 177 / 200 | 23 whole-table |
| R3 | wl_up pgf | new ESTABLISHED rule, each chain | FORWARD 2,045 | FORWARD 5,105 | 1,021 | 2 / 3 | 1 whole-table |
| R4c | wl_up pgf | as R1 / R2 / R3 | — | 2/4; 2/3,847; FORWARD 2,035 | — | 500; 169; 2 of 3 | 0; 53; 1 local |
| R5 | wl_up pgf | 200 `-I CHAIN 1` | 324 / 4,338 | **2 / 444** | 2 / 2 | 178 / 200 | 23 local |
| R6 | wl_tum (5,108) | 200 at one line | 4,590 / 9,620 | **1 / 867** | 1 / 14 | 162 / 200 | 39 local |

Totals over R5's 200 inserts: dense 304,538, stable 4,528, floor 400.
Over R6's: dense 1,099,089, stable 15,855, floor 269.

| | prediction | outcome |
|---|---|---|
| P1 | R1: stable == floor on ≥ 99%, ≤ 2 re-spacings | **held**: 100%, 0 |
| P2 | R2: ≥ 15 whole-table re-spacings (midpoint splitting runs out) | **held**: 23 |
| P3 | R3: a new shell, \|reverse chain\| + O(1), at the floor | **half**: INPUT/OUTPUT at the floor; **FORWARD falsified**: 1,021 new rules do not fit one gap, so the whole table was re-spaced (5,105) |
| P4 | R4: no whole-table re-spacing; max ≤ 2 × window | **held for the whole-table half in all three variants**; the second half was never given a number, so it is not scored |
| P5 | R5: 0 whole-table; median = floor; ≤ 20,000 old rules moved | **held**: 0; 2 = 2; 2,064 |
| P6 | R6: median = floor; ≤ 60 local windows | **held**: 1 = 1; 39 |

## What the variants taught

- **Whole-table re-spacing (R2, R3)** is correct but expensive under clustered
  inserts. R2's worst edit changed 7,289 rules, more than dense indexing ever did.
- **R4a**, a window relabelled only to spacing/16, fails again on the next insert
  at the same spot. It gave 426 windows, 38,516 moved, median 198. It is best for one
  bulk insert (FORWARD: 1,103), worst for clusters.
- **R4b** used the relabel target as the *trigger*. Every ordinary midpoint
  insert into a relabelled region then fails at once (median 632). That was a design error,
  kept for the record.
- **R4c** triggers only when a run does not fit its gap, and relabels the window
  to half the nominal spacing. It costs nothing on random edits and keeps
  clusters near the floor. It pays 2,035 rather than 1,103 for a new FORWARD
  shell, a structural edit made perhaps once in a ruleset's life. **R4c is
  the candidate.** It is the classic order-maintenance trade-off; Bender et al.'s
  thresholds would bound it formally, which is not needed at these sizes.
- **`-I CHAIN 1` is the realistic cluster.** Head-of-chain insertion is
  ordinary iptables practice. That is why the clustered case matters more than
  the bulk one.

## Constraints found for the implementation

- **Engines bound the index differently:**
  - NetPlumber's adapter uses `idx << 12`, so `idx ≤ 2^20−1` (`_RULE_IDX_MAX`).
  - APKeep's packet filters use `10,000,000 − idx`; its router ACLs use
    `70,000 − idx` (`apkeep/adapter.py:77`, `:119`).
  - ad6 encodes indices in 16 bits (`ad6/translate.py:116`).
  - VeriFlow-FR uses `−idx` (unbounded).

  So the spacing budget must come from the engine. Each adapter declares its
  largest usable index, and the indexer spaces within it.
- **From-zero runs must not change.** V5's numbers and ad6's encoding assume the
  generators' dense indices. So stable indexing is **opt-in** on the incremental
  path, and the default path stays byte-identical.
- **The history already exists in the aggregator.** It keeps every device's model
  (`aggregator_service.py:794`). Aligning there keeps the generators, and the
  router/switch models, stateless and unchanged. The owner's requirement 1
  (update-stable indices *emitted to the engines*) holds at the boundary
  that matters. Requirement 2, the per-(device, table, idx) content diff, then
  follows directly. This is a placement choice for the owner to confirm; it is
  recorded as such in `INCREMENTAL_PLAN.md`.

## F1: a generator crash found on the way (not this spike's question)

A state-checking rule that drops, `-m conntrack --ctstate ESTABLISHED -j DROP`,
crashes `_derive_conditional_state_shells` with `IndexError`
(`generator.py:489`). DROP becomes an empty action list (`:193`), while the
shell code reads `actions[0]`. Its own branch intends `Forward([])` (drop) for
exactly this case. No shipped ruleset has such a rule. Fixed separately, with a
test.
