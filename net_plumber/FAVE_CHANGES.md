# FaVe modifications to NetPlumber

This directory is a **fork of upstream NetPlumber**, the C/C++ engine of Peyman
Kazemian's *hassel* (Kazemian et al., *"Real Time Network Policy Checking Using Header
Space Analysis"*, NSDI '13):

- Upstream: <https://bitbucket.org/peymank/hassel-public>, directory `net_plumber/`.
- **Baseline: upstream `master` at `697b35c9`** (2013-06-04, "some missing files").
  FaVe imported it on 2017-10-30 as a squashed git subtree (`b3753f52`, "Merge commit
  '31633805…' as 'code/hassel'"). `31633805` is the subtree commit git synthesised and
  does not exist upstream; the imported tree is **byte-identical** to upstream
  `697b35c9`'s tree (tree hash compared, 2026-09-29). Upstream's `net_plumber/` did not
  change after `5eb81eeb` (2012-11-28) on any branch, so there is no later upstream
  engine this fork has missed.
- The rest of hassel-public (`hassel-c`, `hsa-python`, the demos) was removed from FaVe
  (`cd1ff28c`, 2020-10-31), and `hassel/net_plumber/` became `net_plumber/` (`5434ef8d`,
  `e99f1259`). History before 2020-10-31 lives under `hassel/net_plumber/`.

As with `apkeep/FAVE_CHANGES.md`, `ndd/FAVE_CHANGES.md` and `ad6/FAVE_CHANGES.md`, this
file states FaVe's changes prominently and is the record for any publication. It is also
what the `authors+fave` provenance value (TODO item 31) cites for NetPlumber.

**Licences are per file and kept as upstream has them.** The engine (`src/net_plumber/`)
is Apache-2.0 (© 2012 Google Inc.); the header-space library (`src/headerspace/`) is
GPLv2 plus the Stanford FOSS exception (`LICENSE.txt`, `LICENSE_EXCEPTION.txt`). Files
FaVe added carry their directory's licence (e.g. `array_packet_set.cc` Apache-2.0,
`bitval.h` GPLv2 + exception). FaVe authors are named in the file headers (`a7928385`,
`4079ee0d`, `a669e49e`); those headers do not say *what* changed, and this file does.

**Contributors.** Claas Lorenz (661 commits), Jan Sohre (42, pipe slicing, 2018–19), one
commit as "System Administrator" (`1495778e`, pipe slicing). Sebastian Kiekheben has no
commits of his own: the 2017 drop (§1) is **joint work of Claas Lorenz and Sebastian
Kiekheben**, and Kiekheben implemented the first version of the dynamic header-space
expansion (§2) (owner, 2026-09-29; git records the drop as one squashed commit). Commits from 2026 carry a
Claude co-author line.

**How to read this.** There are 700 commits (`git log -- hassel/net_plumber net_plumber/`);
this file groups them by capability and cites the commits that introduced or decided
something, not every follow-up fix. Kinds:

- **[NEW]** — a capability upstream NetPlumber did not have;
- **[CHANGE]** — upstream behaviour altered by design. These matter most when NetPlumber's
  results are compared with another tool's, or with upstream's;
- **[FIX]** — a correctness bug, in upstream code or in FaVe's own;
- **[PERF]** — a performance change with no intended effect on verdicts;
- **[INFRA]** — build, test, diagnostics and tooling that do not change verification
  behaviour.

**The canonical build.** Everything below is described as it behaves in the default
build, which is the configuration the owner's thesis evaluated and FaVe measures
(`TESTING_STRATEGY_CXX.md`):

```
USER_FLAGS = -DWITH_EXTRA_NEW -DCHECK_ANOMALIES -DSTRICT_RW      (build/sources.mk)
NetPlumber<hs, array_t>                                           (main.cc)
```

`python/build_libnetplumber.sh` compiles with the same defines. Features behind other
flags are listed in §9 as off. The canonical build is what a stamp should name.

---

## 1. The 2017 pre-repository drop  **[NEW]**

`9259da12` ("Merge changes into hassel subtree", 2017-10-30) brought 2,579 lines of
earlier work, joint by Claas Lorenz and Sebastian Kiekheben, into the fresh subtree in
one squashed commit. It added:

- **header expansion** — `NetPlumber::expand`, `Node::enlarge`, the `expand` RPC (§2);
- **firewall rule nodes** (`firewall_rule_node.{h,cc}`) and **policy rules and policy
  probes** (`policy_checker`, `policy_probe_node`);
- **slices** (`add_slice`/`remove_slice`, leakage and overlap callbacks), the start of §8;
- the RPCs `print_topology`, `print_plumbing_network` and `reset_plumbing_network`.

The firewall rule nodes and policy probes were unfinished and were **removed** again on
2019-02-13 (`93fb0e80`, `e8cac639`, `39f47838`); nothing in the current engine derives
from them.

## 2. Dynamic header length  **[NEW]**

The "dynamic" in DHSA. Upstream fixes the header length when the network is created;
FaVe grows it at runtime whenever the model gains a field, and every node, flow and
table is enlarged in place.

- `expand` RPC, `NetPlumber::expand`, `Node::enlarge`, `SourceProbeNode::enlarge` (`9259da12`):
  the first version, by Sebastian Kiekheben.
- Lengths are expanded in **multiples of 8** (`98617ba3`).
- Generic enlargement padding (`b672527d`, `9a460e43`). Rule masks are padded with `0`,
  not with `x`, which triggered a `has_x` assertion before (`da53af82`).
- Enlargement through the RPC fixed (`a6e7e788`, `128d6139`).

## 3. Compliance checking  **[NEW]**

This is the path FaVe's checks run on. Upstream reports probe events one at a time; FaVe
asks, for a set of (source, destination, condition) policies, whether each is met, in a
single call.

- `NetPlumber::check_compliance` (`50804c4c`), in the `net_plumber` tool
  (`--compliance <file>`, `b078bc07`) and over JSON-RPC (`check_compliance`, `1246b3a7`);
  small performance fix `9a1e4927`.
- Flows carry the **originating source node id** while they propagate (`d81b5c05`,
  `a43c6760`), so a result can be attributed to a source.
- `hs_overlaps_arr` — does a header space overlap a condition vector (`4cc519c9`).
- Probes accept **matches** (`f7d222d0`) and empty filters and tests (`d0d62931`). Source
  and probe ids can be set explicitly (`4cc52662`).
- Fixes on this path are in §5: a missing destination crashed the check (#C2), malformed
  input crashed the parser (#C7), and conditioned checks were looser than seeded ones
  (item 26).

## 4. Anomaly detection  **[NEW]**

Rule-table anomalies, checked **on demand only** (`--anomalies`, or the `check_anomalies`
RPC). The check does not run on rule insertion, so it adds nothing to a timed model
build.

- Rule unreachability and shadowing (`dd695b27`, fixed `2a78b5d8`, `66d95cef`,
  `39946e24`); reimplemented as its own function (`9cb4141a`, `f0f21f42`); offered over
  the RPC (`ebecad8a`).
- Generalization detection, with the checks made configurable (`3bbce5c0`, fixed
  `ec921f47`). **Default: shadowing only** (`ed0e212c`).
- Black-hole detection (`9f9a9c83`) — behind `CHECK_BLACKHOLES`, **off** in the canonical
  build.
- Tests `c40812e6`, `e1604bc7`.

## 5. Correctness fixes  **[FIX]**

**Header-space algebra** — the part verdicts rest on:

- `hs_is_empty`, `hs_is_sub` (`2b8eadd3`, regressions `0cd98964`, `aab02d2e`);
  `array_is_sub` and `array_is_sub_eq` were under-complete (`462ba3ed`).
- The complement returned early when the positive set was "all" (`7c329245`); the
  complement of empty sets (`7dcaa09a`).
- Wildcard counting ignored the mask (`af53c497`, `c1595f6c`).
- Arrays whose last word is not fully used: the x-check, the z-check and intersection
  read stale bits (`4952cb8f`, regressions `73ca140b`).
- **#C4** `hs_cmpl` skipped a universe cube among other positive cubes, so the complement
  came out non-empty when it should be empty. This is a soundness bug on the verification
  path, reaching `hs_minus`. **#C5** `hs_add_hs` desynchronised the element and diff
  arrays (out-of-bounds access). Both were found by the concrete-packet oracle
  (`32a41069`).
- **Item 26:** `hs_overlaps_arr` reported overlaps against an empty space, so
  conditioned checks were looser than seeded ones (35 against 30 pairs on wl_stanford).
  Its blast radius was measured, not inferred: the shipped conditioned checks on
  wl_cloud, wl_ifi and wl_up produce byte-identical violation sets before and after
  (`0921496c`).

**Engine:**

- Loading from a directory ignored rule ids (`e91676ec`, `b1152af4`).
- Destroying a network reported loops, because flows outlived links and tables
  (`a7799546`).
- Empty matches were mishandled (`16c9a611`, `d02ff86b`, `8ac118c7`).
- Pipe propagation (`b9493cee`); node ids when dumping and loading (`c0593fc4`).
- **#C1** `remove_link` never updated the inverse topology and erased through a foreign
  iterator (UB). **#C2** `check_compliance` crashed on a destination without a node
  (`a74b6b31`).
- Rule ports must be ports of their table (`fdf5f181`).
- Memory: use-after-free, double free, leaks and uninitialised reads, largely found with
  valgrind in 2018–19 (e.g. `1ddf1fdf`, `668211e8`, `099258b0`, `83d695ea`, `bfa64a6f`,
  `8ea08b66`, `6dc9721c`) and with ASan/UBSan in 2026 (**#C8**: `qsort`/`memcpy` on NULL,
  `022e12cd`).

**RPC server robustness:**

- Very long messages on the TCP, UNIX and UDP servers (`364b017c`, `10598e7e`,
  `cbf9f7ba`); queued calls (`01d9945e`).
- **#C6** A malformed condition aborted the server (`78668206`); unbounded recursion on
  nested conditions (`ded01415`); **#C7** the `check_compliance` parser crashed and
  leaked (`728dc3ac`).

## 6. Behaviour changed by design  **[CHANGE]**

Each item here makes FaVe's NetPlumber answer or accept something differently from
upstream's. Anyone comparing against upstream NetPlumber, or feeding it upstream-format
input, needs this section.

- **Rewrite masks are inverted (`STRICT_RW`, on).** Upstream: a mask bit `0` marks a bit
  the rule replaces. FaVe: `1` means rewrite and `0` means keep (`array.c`,
  `array_rewrite`; `f24a417d`, activated `ffdb625d`). Rules in upstream hassel `.tf`
  format therefore need their masks inverted before FaVe's engine can read them. This is
  the trap described in `CLOUD_BENCH_PLAN.md` §1.6: `wl_stanford`'s committed
  `stanford-json/` already carries inverted masks and cannot be regenerated from
  `stanford-tfs/`. Wildcard counting follows the new convention (`x_count`).
- **Negation of the ternary values.** Upstream swaps the two bits, so `~x = x` and
  `~z = z`. FaVe: `~z = x`, `~x = z`, `~0 = 1`, `~1 = 0` (`06186e9f`), i.e. the complement
  of "any" is empty.
- **Rule tables are index → rule maps** (`57908d4a`). Upstream keeps a table as a list,
  and adding a rule at an index inserts it there and shifts the rules after it. FaVe keys
  the table by index, so **adding a rule at an existing index replaces that rule**. Table
  semantics are first-match in index order (`TABLE_SEMANTICS_PLAN.md`).
- **Rule groups are disabled** (`USE_GROUPS` off; same commit: "buggy and we do not use it").
- **Probes keep flows in lazy-subtraction form** (`4fafd88c`): the explicit `hs_comp_diff`
  at a probe is off, because it could explode memory. This changes the representation,
  not the set; a verdict depends on the diff-aware operations of §5 being right.
- **Loop checking is unchanged from upstream** (a flow that revisits a table). **It
  is FaVe's declared semantics** (owner, 2026-09-30; TODO item 33): a second pass
  through a table counts as a loop and stops the flow, whatever its header. The
  NetPlumber paper states it so ("determine if the flow has passed through the
  current table before", §4.2), loosening HSA's port-granular check. So a packet
  that legitimately passes a table twice (a router on a stick) is lost:
  `fave/test/test_revisit_router_on_a_stick.py` pins it. FaVe added
  optional per-rule "dense" checking (`d2f95032`), off by default. Its commented-out line
  in `build/sources.mk` reads `DDENSE_LOOPS`, missing the `-`, so uncommenting it as it
  stands would not enable it.

## 7. Performance  **[PERF]**

These are why a FaVe NetPlumber number is not an upstream NetPlumber number, even on
upstream-compatible input:

- Intersection of header spaces with arrays: an intersecting constructor, in-place array
  intersection, and use of both in flow propagation (`24ffc361`, `33d0a039`, `e8aa20a7`,
  `4f18d009`, `485d22d3`, all 2021-04-25).
- Subset tests: trivial-case shortcuts (`f97a5eeb`, `c19e341a`), one round of
  `hs_is_sub_eq` saved (`2e57e343`), array subset (`d3955d6b`), a simple subset check and
  merge-insert (`da6207be`).
- A new `array_combine` (`WITH_EXTRA_NEW`, on; `5db4adfa`).
- `add_rules` — a batch of rules in one RPC (`1c90d27b`).
- **`libnetplumber`** — in-process pybind11 bindings over the engine (`python/`,
  `cd68e0b7`, `208d4f49`, `59949dec`). It mirrors `rpc_handler.cc`'s argument translation
  so the engine sees the same inputs as over RPC, without the IPC and serialisation cost
  on the rule bulk (`APKEEP_BACKEND.md` P1).

## 8. Pipe slicing  **[NEW]** — off in the canonical build

Network slices with an allow matrix between them, and leakage detection when a pipe
connects slices it should not. Started in the 2017 drop (§1); built out by Jan Sohre in
2018–19 (`0ab5e7ba` … `d8bff047`, measurements `0aeac5a2`); refactored onto packet sets
(`c10052fc`). It sits behind `PIPE_SLICING` and is **off**. The RPCs `add_slice_matrix`,
`add_slice_allow`, `print_slice_matrix`, `dump_slices` etc. exist only when it is on.

## 9. Parked experiments  **[NEW]** — off in the canonical build

Per the author these are abandoned or experimental (`TESTING_STRATEGY_CXX.md` gives the
table):

- **Templated engine over packet sets** (`e4f3323c` … `7802a0e6`, 2019-11-19) and the
  `PacketSet` interface (`90f0a086`, `0645b7bf` …) — `GENERIC_PS`. The templating itself
  is live: the canonical build instantiates `NetPlumber<hs, array_t>`.
- **BDD packet sets over BuDDy** (`64e59157`, `0ccd5f6f`, 2020) — `USE_BDD`; parked on the
  unsolved masked-rewrite problem (`3b9b8b28`). libbdd is not linked by default
  (`31cec427`).
- **A simplified header-space structure** (`c537a07f`, 2019-08) — `NEW_HS`, a dead end.
- `CHECK_REACH_SHADOW`, `CHECK_SIMPLE_SHADOW`, `SORTED_DIR`, `SORTED_FWD` — minor
  experiments. `USE_DEPRECATED` gates upstream functions FaVe no longer uses.

## 10. Diagnostics, build and tests  **[INFRA]**

- **Dumps:** the network, flows, pipes and flow trees as JSON (`70429a13`, `a156ed41`,
  `d852b855`, `7f1be6be`), a compressed tree dump of root and leaves only (`295b43e4`),
  one file per tree (`08a4188c`); SVG titles (`a0391fc5`); metrics, microsecond timing and
  maximum RSS when loading (`3d5e933e`, `47bd6001`, `d4120041`); a `stop` RPC
  (`1f3ddfa7`).
- **Logging:** log4cxx statically linked and quieter (`c603e675`), trace logging across
  the nodes (`fb2ce4f5`), optional loop verbosity (`1466d50c`).
- **Build:**
  - C++11, then C++14, then C++17 (`1d573f4b`, `6bf09bb5`, `c80d5cff`), with the language
    stated per subdirectory (`2749dab0`);
  - `-Wextra -Wpedantic` (`6c17feae`), a GCC 15 fix (`2b452d4c`);
  - install, coverage and valgrind targets (`cc10ee96`, `2d97de18`, `2d2f921e`);
  - setup scripts for Ubuntu 24.04 and Arch Linux (`713ec758`, `1f4c263d`);
  - the Eclipse `Ubuntu-`/`MacOS-NetPlumber-Release/` build directories replaced by
    `build/` (`5434ef8d`).
- **Tests:** CppUnit suites for `array_t` and `hs` (`11a3b6ea`, `3f01e5ef`), the engine,
  plumbing, conditions, packet sets, slicing and anomalies. Upstream had the basic,
  plumbing and conditions suites and none for the header-space library. Added in 2026 (TODO items 7 and 1h/1i):
  - the concrete-packet oracle with algebraic-law tests (`32a41069`);
  - public-API and RPC-parser contract tests (`ce580d6f`, `78668206`);
  - test isolation (`3af54d86`);
  - an ASan+UBSan CI job (`022e12cd`);
  - a failing suite now returns a non-zero exit code (`b5e46260`).

  `net_plumber --test`: OK (119).
- **Loop reports, counted in-process** (2026-09-30): `libnetplumber` replaces the
  logging-only loop callback with a per-instance counter, `loop_reports()`. This
  changes no behaviour, since the flow is stopped whether or not a callback is set.
  A count of zero proves the table rule truncated nothing on a workload
  (`fave/bench/analysis/netplumber_loop_census.py`).
- **Removed:** upstream `list.h` and `map.h`; code no longer used (`b18bddb7`, `31268590`,
  `c26bdf04`).
