# FaVe Quality Assurance — TODO

This document tracks suggested quality-assurance improvements for FaVe.
Items are grouped by priority. Each item notes the concrete finding and the
proposed fix.

**Convention:** each item has a top-level checkbox; multi-step items have nested
checkboxes so partial progress is visible. Tick a box only when that piece is
truly complete (use the session task list for in-progress/blocked granularity).
The *Finding* / *Fix* / *Decision* lines are reference context, not tasks.

## State of QA (baseline)

What is already in place:

- `.gitlab-ci.yml` with `pre → build → test → deploy → bench` stages, containerized via `Dockerfile`.
- Python unit tests (`fave/test/`, `policy_translator/test/`) on `unittest`.
- C++ CppUnit-style suites in `net_plumber/src/*/test/` (`hs_unit`, `array_unit`, `net_plumber_*_unit`) wired to a `make test` target.
- Benchmarks run in CI as end-to-end smoke tests (example, ifi, up, tum, …).
- Linting infrastructure (`fave/test/lint_test.sh`, parallelized pylint with an ignore-list for vendored Hassel code).

The main theme below: several checks exist but **do not actually gate** (drift, non-failing scripts, discarded output).

---

## High priority — make the QA itself trustworthy

### 0. Migration to GitHub CI — DONE (workflow added; needs real-CI validation of heavy tiers)
- [x] **GitHub Actions workflow added: `.github/workflows/ci.yml`, jobs invoke `test.sh <tier>`.**
  - [x] Skeleton: triggers `push: [main]` + `pull_request` + `workflow_dispatch`; `runs-on: ubuntu-24.04` (matches Dockerfile base / README platform).
  - [x] **Native runner, not a baked image.** Chose a native runner over building/pushing the `Dockerfile` to GHCR: the Dockerfile `COPY`s the repo and builds+tests at *image-build* time, which fights per-PR testing (a `container:` job would mount a fresh checkout over the pre-built tree). Native install matches the tier philosophy (fast=native, integration=full stack) and tests the actual checkout. System deps are installed inline with the Ubuntu-24.04 package names from the Dockerfile (`liblog4cxx15`, `libcppunit-1.15-0`, `flex`, `bison`, `build-essential`).
  - [x] Jobs → tiers (updated in item 1g): `fast` → `bash test.sh fast` (pure-Python; **gates**); `lint` → `lint_test.sh` (non-gating until item 2); `integration` → `COVERAGE=1 bash test.sh integration` (build + C++ tests + bison tests, no live backend; **gates**); `e2e` → `bash test.sh e2e` (test_rpc + smoke; **non-gating**, `continue-on-error`); `bench` → `bash test.sh bench` (`workflow_dispatch` only). Heavy native setup shared via composite action `.github/actions/setup-fave-native`.
  - [x] Coverage artifact uploaded from the integration job; gating intent documented (fast = required gate).
  - [x] **`fast` job validated end-to-end locally** (clean venv + `pip install -r requirements.txt` + `bash test.sh fast` → 46 + 80 passed).
  - [x] **First real CI run analyzed** (run 75323499335). `fast` + `lint` ran fine; NetPlumber built; `integration` FAILED. Diagnosis below.
  - [ ] **Validate `integration`/`bench` on real CI** — first run failed; quick fixes applied (below), RPC/C++ items still open.
  - [ ] **Then retire GitLab:** once the GitHub workflow is green, delete `.gitlab-ci.yml` and update README/badges. Left in-tree for now (conservative — don't delete the old CI before the new one is proven).
  - [ ] **Branch protection** (repo setting, not in YAML): mark `fast` (and later `lint`, `integration`) as required for merge.

#### First integration-run diagnosis (run 75323499335)
The job's non-zero exit came **only** from the `fave` native pytest (`5 failed`); everything else was non-fatal or silent. pandoc was a red herring for the *failure* (real gap, but non-fatal).
- **Quick fixes — DONE:**
  - [x] Fixed `netplumber/jsonrpc.py` `%`-format bug: `"%s" % (server, port)` (a 2-tuple → `TypeError: not all arguments converted`) → wrap as 1-tuple. This was masking the real "could not connect" error in `test_rpc`. Verified both socket/port forms.
  - [x] Fixed `test.sh` coverage CWD bug ("No data to combine"): `export COVERAGE_FILE="$ROOT/.coverage"` so `coverage run -p` (from `fave/` in the integration tier) and `coverage combine` (from `$ROOT`) agree. Verified cross-dir.
  - [x] Added `pandoc` + `inkscape` to the CI `integration`/`bench` jobs; added `pandoc` to the `Dockerfile` (it was never there — `inkscape` already was).
  - [x] **Verified on CI run 75331175825** (after the quick-fix commit, before the e2e split): jsonrpc fix landed (error is now a clean `RPCError: could not connect ... ('localhost', 1234)`, not the old `TypeError`); coverage fix landed ("Combined 1 file", no more "No data"); pandoc now installed; `fast` PASSED (46 + 80). The remaining integration failures in that run (`test_to_json`, 4× `test_rpc`) are addressed by the *later* e2e-split commits and await the next CI run.
  - **CORRECTION (inkscape hypothesis was wrong):** the wl_ifi German "Datei(en) konnte(n) nicht gelesen werden" persisted *with inkscape installed*. Root cause is **our own code**: `policy_translator.py:67` prints that (German) string and `sys.exit(1)` when it cannot read its input file(s). The wl_ifi benchmark feeds it a path that doesn't resolve in CI, and the benchmark swallows the non-zero exit (prints "generated policy matrix" regardless). See item 1n. (inkscape is still legitimately used by the visualizers, so adding it is not wasted — it just wasn't this bug.)
- **Open — to discuss (RPC + C++):** see items 1g, 1h below.
- **Open — gating gaps (silent failures):** see item 1i.
- **Follow-up:** `net_plumber/setup-ubuntu.sh` is stale (Ubuntu-20.04 package names `liblog4cxx10v5`/`libcppunit-1.14-0`, and builds BuDDy which the "don't link libbdd by default" change made unnecessary). The workflow inlines the correct 24.04 deps instead; consider updating `setup-ubuntu.sh` to 24.04 and having both it and CI share one dep list (DRY).

### 1. Resolve Python 2 vs 3 drift (CONFIRMED: drop Python 2) — DONE
- [x] **Drop Python 2 entirely; make everything Python 3**
  - [x] Delete the remaining 10 py2 shebangs (`policy_translator/*`, `np_reproduction/*`, `ad6/bench/up/inventory.py` — all already py3-compatible).
  - [x] Port the two genuinely-Python-2 scripts (`np_reproduction/transform.py`, `np_reproduction/analyze_output.py`): `print` statements → `print()` (preserved the py2 soft-space on the trailing-comma `print` via `end=' '`).
  - [x] Replace inline `python2 -c "print …"` one-liners in `rename_workload.sh` and `run_vanilla.sh` with `python3 -c "print(…)"`; convert FaVe's own `python2` script calls in `run.sh` to `python3`.
  - [x] **Kept** `run.sh` TF/JSON generator calls on `python2` — they invoke the upstream Hassel reference impl (`~/hassel-public/hsa-python`, py2-only); added an explanatory comment. (Not ours to port.)
  - [x] Update docs: `policy_translator/README.md` (`python2 …` → `python3 …`, "developed/tested with 2.7" → "runs on Python 3").
  - [x] Reconcile path drift: `README.md` `example/example.sh` → `examples/example.sh` (actual dir is `examples/`).
  - [x] Fixed a broken shebang found in passing: `run_vanilla.sh` `#!/use/bin/env bash` → `#!/usr/bin/env bash`.
  - [ ] Fold corrected commands into the new GitHub workflow (deferred to item 0; `.gitlab-ci.yml` is being retired, not edited).
- **Finding:** Code is Python 3 (129 py3 shebangs vs 10 py2; `Dockerfile` installs `python3*` and runs `python3 fave/test/unit_tests.py`; README uses `python3`). The old `.gitlab-ci.yml` still calls `python2`, `python2-coverage`, and bare `python` in 9 places.
- **Decision:** GitLab CI is inactive and stays that way → migrate to GitHub CI (see item 0). Drop Python 2 entirely.
- **Verification:** `policy_translator` unit tests pass under py3 (39/39). All ported np_reproduction files pass `python3 -m py_compile`. No `python2` references remain except the intentional Hassel-generator calls in `run.sh`. (`fave` unit suite needs `pybison`, only present in the Docker image — not runnable in this shell.)
- **Follow-up (separate from py2 work):** `fave/iptables/parser.py:487` emits a py3 `SyntaxWarning: invalid escape sequence '\-'` (regex should be a raw string). Minor py3-cleanliness; tracked as a small item, not fixed here to avoid scope creep.

### 1b. Local tiered test runner — `test.sh` — DONE (foundation for item 0)
- [x] **One suite, one entry point (`./test.sh`), tiered by dependency footprint**
  - [x] `fast` — pure-Python, no native deps, runs natively in <1s (inner-loop gate). Auto-discovers via `pytest` over `policy_translator/test` + `fave/test`, *ignoring* the native-dep exceptions (so new pure-Python tests are picked up automatically — no registry to forget).
  - [x] `smoke` — `example.sh` + `wl_example` + `wl_ifi` (quick end-to-end; needs native stack).
  - [x] `integration` — NetPlumber C++ `make test` + bison-dependent fave tests (`test_topology`, `test_packet_filter`, `test_iptables_parser`) + `test_rpc` (needs live backend) + smoke.
  - [x] `bench` — `wl_up`/`wl_tum`/`wl_stanford`/`wl_i2`. `all` = fast + integration.
  - [x] `COVERAGE=1` toggle wraps Python tiers in `coverage` and prints a report (parallel-mode + combine).
  - [x] Documented in top-level `README.md` (`## Testing`). `.gitignore` updated for py/test artifacts.
- **Design decisions (confirmed with user):** one suite / two entry points (local + CI run the *same* command, CI only selects a tier); Docker for integration, native for fast; tier = dependency footprint, not runtime (so the quick `example`/`wl_ifi` benches are *smoke/integration*, not fast).
- **Verification:** `./test.sh fast` is **deterministically green across hash seeds** — `policy_translator`: `46 passed`; `fave`: `80 passed`; **no `xfail`/`xpass` remaining** (the `test_grammar` orphan was deprecated → item 1c; `test_to_iptables` was rewritten block-wise → items 1d/1e). Stable under seeds 0/1/7/42 and default, and across repeated runs. `COVERAGE=1` reports ~72% from the fast tier. Bad tier → usage + exit 2. (smoke/integration/bench need the native stack/Docker — implemented but not runnable in the dev shell.)
- **This absorbs items 3, 4, 5** (see those items).

### 1c. Orphaned AI-generated grammar tests — RESOLVED (deprecated)
- [x] **Move the orphaned `test_grammar.py` out of the active suite**
  - [x] `git mv policy_translator/test/test_grammar.py → policy_translator/deprecated/test_grammar.py` (outside the pytest collection root).
  - [x] Removed the (mis-framed) `xfail` quarantine marker; replaced with a deprecation header + `policy_translator/deprecated/README.md`.
  - [x] Added `pytest.ini` with `norecursedirs = *deprecated*` (mirrors `lint_test.sh`) so no future `deprecated/` dir is ever collected.
- **Context (per user):** not test debt — an unfinished CodiumAI experiment left orphaned in the repo (never wired in, never ran; expectations don't match `fpl_grammar.parse_fpl()`). Deprecated rather than deleted in case proper FPL-grammar tests are revisited. Verified: `test_grammar` is no longer collected (count 0); fast tier stays green.

### 1d. Make `test_to_iptables` concept-aligned (block-wise) — DONE
- [x] **Rewrote `test_to_iptables` to test what §7.3 / Algorithm 7.1 actually guarantees; removed the `xfail`.**
  - [x] Asserts **block order** exactly (canonical sequence of the nine section headers; catches missing/extra/interleaved blocks).
  - [x] Asserts each block's rules as an **order-independent multiset** (`assertCountEqual`) — intra-block order is non-semantic by the concept.
  - [x] Removed the module-level `pytest.mark.xfail`.
- **Decision (with user):** the generator's non-deterministic intra-block order is **NOT a bug** — §7.3 permits it (each block is single-action; block order is fixed; verified against `to_iptables()`). **Output stays as-is**; consumers must not rely on intra-block order. The defect was in the *tests*, which over-specified exact line order — fixed there, not in `policy.py`.
- **Verification:** `test_to_iptables` now passes **12/12 deterministically under seeds 0/1/7/42 and default**. Full fast tier: 46 + 80 passed, repeatable, **no `xfail`/`xpass` anywhere**.

### 1e. Block-membership indicators — RESOLVED (section headers as an output feature)
- [x] **Emit `# === <name> ===` section headers in the generated rule set; tests use them as authoritative block boundaries.**
  - [x] Added nine headers to `Policy.to_iptables()` (IPv4/IPv6 × default/anti-spoofing/state, plus IPv6 ICMP, IPv6 hardening, access). Semantically inert (shell/`iptables-restore` comments).
  - [x] Tests parse blocks by header (`parse_blocks`) — no fragile rule-shape pattern-matching (per user's reservation that pattern-matching could miss future rule-shape changes).
- **Decision (with user):** chose explicit output headers over a test-side pattern classifier. Justified as an independent **readability/audit** feature for human reviewers, not test-only scaffolding. Headers reflect the per-protocol block structure; item 1f later added the leading `Suppress` block to match Algorithm 7.1's `Suppress + Main`.

### 1f. Generator structure matches Algorithm 7.1 (Suppress list) — DONE (refactored)
- [x] **Refactored `to_iptables()` to the two-list `Suppress + Main` form.** Decision (with user): FaVe is a *reference implementation* of the thesis, so the generated artifact should mirror Algorithm 7.1 rather than just be equivalent. Collected the stateless-suppression `raw/PREROUTING ... -j NOTRACK` rules into a `suppress_rules` list and prepended them as a leading `# === Suppress (stateless NOTRACK) ===` block; the access block now holds only the FORWARD rules.
- **Behavior unchanged:** purely organizational — netfilter evaluates the `raw` table before `filter` regardless of command order, so inline vs. prepended produce identical packet filtering. Verified via the block-wise `test_to_iptables` (now includes the leading Suppress block; 12/12 deterministic across seeds 0/1/42/default; fast tier 46 + 90 green).

### 1g. `test_rpc` backend dependency — RESOLVED via e2e tier split
- [x] **Introduced an `e2e` tier and made `integration` deterministic + gating.**
  - [x] `test.sh` now has three native-stack tiers split by dependency footprint: `integration` = NetPlumber C++ `make test` + bison tests (`test_topology`, `test_packet_filter`, `test_iptables_parser`) — needs build + pybison but **no live backend** → deterministic, **gates**; `e2e` = `test_rpc` + smoke (`example.sh`, `wl_example`, `wl_ifi`) — needs a running net_plumber + `/dev/shm` → **non-gating** for now.
  - [x] Fixed the `test_rpc` port mismatch: it called `start_np.sh` (defaults to `44001`) but connected to `1234`. Now starts with `-p 1234` to match the connect port. (The `jsonrpc.py` format bug fixed earlier was masking this as a `TypeError`.)
  - [x] Fixed `test_packet_filter::TestSwitchModel` (`test_to_json`/`test_from_json`): removed `raw_line`/`raw_line_no` from the **device-level** expected dicts. **Root cause confirmed via git history (user-verified):** origin tracking is a *rule* property — added to the `Rule` model by `ee07118f` and correctly emitted there. Commit `de8e5311` ("Fix broken tests due to model changes") updated test expectations for the new rule-level field but **over-applied** it to the device/switch-level dicts (before `'type':'switch'`); `AbstractDeviceModel`/`SwitchModel` never carried those fields (no commit ever touched `raw_line` under `fave/devices/`). The broken assertions went unnoticed because `test_packet_filter` (bison-dependent) wasn't being run. Confirmed design: **rules carry origin, devices don't.** All remaining `raw_line` in the file is rule-level and correct. (Verified by reading + history, not run — needs pybison; next CI run confirms.)
  - [x] CI: `integration` job gates (no `continue-on-error`); new `e2e` job is `continue-on-error: true`. Extracted a composite action `.github/actions/setup-fave-native` so integration/e2e/bench share the heavy native setup (DRY).
  - [ ] **Client-contract test (agreed, still TODO):** add a fast-tier mock-socket test for `jsonrpc.py` (validates request encoding / response parsing without a backend). See item 1k.
  - [ ] **`test_rpc` next bug (CI run 75548766906):** the port fix worked (it now connects), revealing a stale API mismatch — `jsonrpc.py:56` (`for sock in socks`) expects a **list** of sockets (multi-NetPlumber support), but `test_rpc` passes a single `self.sock` → `TypeError: 'socket' object is not iterable`. Fix: pass `[self.sock]` (or make `setUp` hold a list) at the call sites. Multi-site but mechanical. e2e/non-gating.
  - [ ] **Promote `e2e` to gating** once `test_rpc` + smoke are reliable on real CI.
- **Note:** `integration` gating is currently effective for the build + bison Python tests; the C++ `make test` failures are still *silent* (exit 0), so the gate does not yet catch them — see items 1h (triage) and 1i (make `make test` propagate).

### 1h. C++ header-space soundness regression — FIXED (single root cause)
- [x] **Fixed:** `array_isect`/`array_has_x`/`array_has_z` `len % 4 == 0` masking (see below). This **single fix resolves both** `test_is_equal_regression2` **and** `test_compact_regression`, plus the new `array_unit` len4 microtests. User's full `make test` run passes; replicated exactly against the fixed `array.c` (`hs_is_equal(compact(a), b_wrong)=false`, `hs_is_equal(compact(a), c_correct)=true`).
- **Correction:** an earlier "second bug — `hs_compact` over-merges" report was a **false alarm** — a transcription error in a throwaway harness (`hs_micro2.c`) compared `compact(a)` against the 6-diff `c_correct` set while mislabeling it `b_wrong` and expecting inequality. There is **no separate `hs_compact` bug**; the masking fix was complete.
- **What fails:** `hs_unit.cc:1936` (`test_compact_regression`) and `:1965` (`test_is_equal_regression2`). Both assert `!hs_is_equal(&a,&b)` where `b` is a *deliberately wrong* over-merge (its `000xx10x` cube covers `10.0.4.0/23`, which is **not** in the input — the source even comments `<- this is wrong`). They fail ⇒ the code now treats `a == b`, i.e. compaction over-merges (or `hs_is_equal` wrongly equates).
- **Tests are old/correct:** added with the original import (`e99f1259`); they encode known-correct behavior.
- **Suspected cause — refactor `da6207be`** (Jan 2022, "Refactor headerspaces to support a simple subset check and a merge insert operation"): added `hs_merge_insert` (greedy pairwise `array_merge`) and rewrote `hs_is_equal` to a subset-based check. `array_merge` itself only merges cubes differing in ≤1 bit (locally sound); the over-merge is suspected in the *greedy* use during compaction and/or the subset-based equality. **`NEW_HS` is OFF** (`sources.mk:30` commented), so the refactored path is the one compiled.
- **Severity — on the real verification path (not test-only):** `hs_compact` → `rule_node.cc:421`, `hs_packet_set.cc:248`; `hs_is_equal` → `hs_packet_set.cc:212` (`HeaderspacePacketSet` equality); `hs_simple_merge`/`hs_merge_insert` → `net_plumber.cc` aggregation. An over-merge here corrupts computed header spaces → potentially wrong verification verdicts. Most serious finding of the QA effort; impact direction (false compliance vs false anomaly) needs the author's analysis.
- **Confirm by bisect (needs a build):** build at `da6207be^` vs `da6207be` and run `./net_plumber --test`. Has been failing **silently since then** because the runner returns 0 regardless (item 1i).
- **ROOT CAUSE FOUND (primary bug) — `len % 4 == 0` masking in `array.c`.** Via standalone microtests + a 256-point oracle, traced to three primitives that mask the "incomplete leading bits" of the last `array_t` word using `set_bits = (len % (sizeof *a / 2)) * 16` (`sizeof(array_t)/2 == 4` header bytes per 64-bit word):
  - `array_has_x` (`array.c:242`, `&=` mask → undefined `>>64`),
  - `array_has_z` (`array.c:258`, `|=` mask),
  - `array_isect` (`array.c:627`, `|=` mask).
  When `len` is a multiple of 4 (e.g. **len=4**, the regression's length), `set_bits == 0` so the mask becomes all-ones and **corrupts the whole word** (e.g. `array_isect` returns all-x instead of the real intersection). `len=1,2,3` are unaffected — which is why the existing `test_array_isect` (len=2) never caught it, and my early len=1 micro-tests passed.
  - Chain: `array_isect` wrong → `array_is_sub_eq` wrong (a concrete point reported as NOT ⊆ a cube that contains it) → `hs_is_sub_eq`/`hs_is_equal` wrong.
  - **Fix APPLIED to repo `array.c` (3 sites): guard `if (rem)` where `rem = len % (sizeof *a / 2)` — only mask when the last word is NOT fully used.** Verified against the repo source: `array_isect` returns the correct intersection, `array_is_sub_eq` is correct at len=4, the new `array_unit` microtests pass, and **`test_is_equal_regression2` passes**. (User confirmed the two new tests failed pre-fix.)
- **No second bug.** An earlier note here claimed `hs_compact` still over-merged after the `array.c` fix — that was a **transcription error** in a throwaway harness (compared `compact(a)` against the 6-diff `c_correct` set but labeled it `b_wrong` and expected inequality). Re-checked with the *exact* `test_compact_regression` data (b = the 5-diff wrong set): `hs_is_equal(compact(a), b_wrong)=false` and `hs_is_equal(compact(a), c_correct)=true` — both assertions pass. The masking fix was the complete fix.
- **Microtests added to the suite** (`array_unit.{h,cc}`): `test_array_isect_len4_regression`, `test_array_is_sub_eq_len4_regression` — fail pre-fix, pass post-fix. (The throwaway standalone harness used during localization has been removed now that the coverage is in the CppUnit suite.)

### 1i. C++ test runner propagates failures — DONE
- [x] **`run_tests()` now returns `collectedresults.wasSuccessful()`; `main` does `return run_tests<...>() ? 0 : 1` on `--test`** (`net_plumber/src/net_plumber/main.cc`). Chain: `./net_plumber --test` exits non-zero on any CppUnit failure → `make test` fails (target has no error suppression) → `test.sh integration` sets `rc=1` → the **gating** `integration` CI job fails. Safe now that the suite is green (1h fixed): it exits 0 today and stays green, but will catch any future C++ regression. (Verified the chain by inspection; couldn't link here — no cppunit/log4cxx — so rebuild + `make test` to confirm.)

### 1p. Surface swallowed `example.sh` flow-test failures — TO ADDRESS
- [ ] **`example.sh` does `... || echo "some example flow tests failed"` and exits 0** — the failure is reported but swallowed (seen in CI). Decide: make it fail the script (so the e2e tier reflects it), or accept it while e2e stays non-gating. (The C++ `make test` propagation half of the old item is done — see 1i.)
- **Theme:** same "checks that don't gate" smell as the lint script (item 2) and the old coverage report (item 3).

### 1j. `\-` SyntaxWarning (py3 cleanliness) — DONE
- [x] **Made the regex strings raw strings.** `fave/iptables/parser.py:487` (`_word`) and `policy_translator/policy_builder.py:33` (`value_pattern`) → `r'...'`. A repo-wide sweep (excluding venv/hassel/deprecated) confirmed these were the only two. Verified behavior-preserving: raw strings leave the exact bytes the regex engine receives unchanged (the `\"`-vs-`"` in `policy_builder`'s class is regex-equivalent — both match `"`), and a char-by-char comparison of old vs new showed no difference. Re-sweep: 0 invalid-escape warnings remain.

### 1q. Python 3 division semantics: `router.CAPACITY` should be an integer — FIXED (verify on e2e/bench)
- [x] **Changed `RouterModel.CAPACITY = 2**16 / 2**12` → `2**16 // 2**12`.** Confirmed with the author: this was a **Python 2 → 3 migration artifact** (item 1) — under py2 `/` between ints was integer division (→ `16`), but py3 makes `/` float division (→ `16.0`). The `# XXX: ugly workaround` comment predated the migration.
- [x] **Removed the `# type: ignore[arg-type]`** on the `aid+rid` `Rule(...)` in `devices/router.py`. `aid = int(vlan) * CAPACITY` is now an `int`, so the rule index is an `int`; mypy (`warn_unused_ignores`) confirms the ignore is no longer needed and there is no remaining `arg-type` error. `./test.sh fast` still 46 + 90. Other `idx` arithmetic in `persist()` (`offset+idx`, `enumerate` indices) was already integer.
- **Effect (the fix):** a freshly-built (not round-tripped) router now serialises ACL rule `idx` as `"16"` instead of `"16.0"`. This was previously tolerated (`Rule.from_json` does `int(j["idx"])`, `Rule.__eq__` is numeric), so the only observable change is the serialised form.
- [ ] **@USER e2e/bench:** the serialised form changed (`"16.0"` → `"16"`); validate against NetPlumber's JSON-RPC parsing / any stored snapshots when you run the heavy tiers. Expected to be a strict improvement (integer indices), but it touches the wire format.

### 1k. Fast-tier RPC client-contract test — DONE
- [x] **Added `fave/test/test_jsonrpc_client.py`** — 10 mock-socket contract tests for `netplumber/jsonrpc.py`, no backend, auto-discovered into the fast tier (now 90 passed, <1s). Covers: request encoding (method+params+`jsonrpc:"2.0"`) for `init`/`destroy`/`add_table`/`add_link`/`remove_rule`/`add_rule`; response parsing (`add_rule` returns the `result` node id); error handling (`error.code != 0` → `RPCError`; `code == 0` → ok); multi-socket broadcast; and a **regression guard** for the `connect_to_netplumber` `%`-format fix (mocks `socket`/`time.sleep` so the 100-retry loop is instant). A `FakeSocket` models the `MSG_PEEK`-then-consume recv pattern.
- **Rationale (with user):** mocking fits the *client/protocol* surface (correct JSON requests, response parsing); it does NOT replace `test_rpc` (whose log assertions validate NetPlumber's engine). Derived from the JSON-RPC interface contract, not C++ internals — small, stable maintenance surface.

### 1l. NetPlumber port convention — DONE (consolidated on 44001)
- [x] **Standardized on `44001` = `NET_PLUMBER_DEFAULT_PORT`** (already the default for `start_np.sh`, the benchmarks, the aggregator, and `check_compliance`'s real default). Fixed the stragglers:
  - `print_np.py` — actual default `port = 1234`/`server = "127.0.0.1"` → `jsonrpc.NET_PLUMBER_DEFAULT_PORT`/`NET_PLUMBER_DEFAULT_IP` (single source of truth); stale help text `port=1234` → `44001`.
  - `check_compliance.py` — stale help text `port=1234` → `44001` (its real default already used the constant).
  - `test_rpc.py` — now starts `start_np.sh` with its default (44001) and connects to `NET_PLUMBER_DEFAULT_PORT` (dropped the earlier self-consistent `-p 1234` patch).
  - `scripts/test_all.sh` — `NPPORT=44001`; `examples/demo_slicing.py` — `PORT=44001`.
  - Verified: no `1234` remains in `fave/` (excl. venv/hassel); changed files compile; `print_np.py` lints clean.

### 1m. pandoc PDF report needs a LaTeX engine — minimal install added (verify on CI)
- [x] **Installed a minimal LaTeX set** (`texlive-latex-base` + `texlive-latex-recommended` + `texlive-fonts-recommended`) for `pandoc report.md -o report.pdf` (which needs `pdflatex`). `texlive-latex-extra`/`texlive-full` intentionally omitted — the generated `report.md` is plain markdown (headings, lists, inline code; no tables/images/math), so pandoc won't pull in `longtable`/`booktabs`. Added to the composite action and the `Dockerfile`.
- [x] **Moved report tooling off the gating job.** pandoc/inkscape/LaTeX were installing on the `integration` gate too (they were in the shared composite); gated them behind a `report-tools` input so only `e2e`/`bench` install them — keeps the gate lean.
- [x] **CI run 75548766906:** pdflatex now present, but pandoc failed on `lmodern.sty not found`. Root cause: `lmodern` is a standalone package that `texlive-fonts-recommended` only *recommends*, so `--no-install-recommends` skipped it. **Fixed:** added `lmodern` explicitly (composite action + Dockerfile).
- [ ] **Verify on next CI run** that pandoc→PDF now succeeds. If another `.sty` is still missing, add it (or `texlive-latex-extra`) — non-gating (e2e), so it only shows in logs.

### 1n. wl_ifi smoke: PolicyTranslator input not read + swallowed failure — TODO (e2e/non-gating)
- [ ] **Fix the wl_ifi policy-matrix input path (CI) and stop the benchmark swallowing the failure.** `policy_translator.py:67` prints `"Fehler: Datei(en) konnte(n) nicht gelesen werden."` and `sys.exit(1)` when it can't open its input files; in CI the wl_ifi benchmark passes a path that doesn't resolve (likely CWD/relative-path), yet proceeds ("generated policy matrix") — the non-zero exit is ignored. Two sub-issues: (a) the input path resolution in CI; (b) the benchmark swallowing a failed sub-step (same "silent failure" theme as 1i). Minor extra: the error string is hardcoded German in an otherwise-English codebase.
- [ ] **@USER: commit the missing wl_ifi input files.** Root cause confirmed: the files `benchmark.py` references are **not in the repo** — `fave/bench/wl_ifi/` has no `roles_and_services.orig.txt` / `policy.orig.txt` (nor the non-`.orig` `roles_and_services.txt` / `policy.txt`). The path "doesn't resolve in CI" because the files were never committed, not because of a CWD/relative-path bug. **Claas needs to add and commit these files** (not available in the current working tree). Until then the uncommitted `benchmark.py` edit (both `roles_services` + `reach_policies` commented out, `inventory` only) is a stopgap that can't actually generate the policy matrix. Once the files are committed: revert/clean up that edit, then revisit (a)/(b) above.

### 1o. NetPlumber build breaks on GCC 14+ (Ubuntu 26.04) — FIXED (verify on 26.04)
- [x] **Fixed `-Wincompatible-pointer-types` errors in the C headerspace code.** GCC 14 promoted a family of C warnings to **default errors** (`-Wincompatible-pointer-types`, `-Wint-conversion`, `-Wimplicit-function-declaration`, `-Wimplicit-int`, `-Wreturn-mismatch`). On Ubuntu 24.04 (GCC 13) these only *warned*; on 26.04 (GCC 15) they fail the build. The reported error (`array.c:329`) was `&tmp` (a `char[]`/`array_t[]`) passed where the callee wants a plain `T*` — same address, wrong type. Dropped the erroneous `&` at: `array.c:270,329,335,850`; `hs.c:259,261,276,278,313,316` (compiled), plus `array.c:998` (in the dead `#ifdef NEW_HS` path, for completeness).
- **Validated locally** by forcing the GCC-14 diagnostics to errors on GCC 13 (`-Werror=incompatible-pointer-types -Werror=int-conversion -Werror=implicit-function-declaration -Werror=implicit-int -fsyntax-only`): `array.c` and `hs.c` both compile clean (rc=0). This also caught two sites a naive grep missed (`hs.c:276,278`, `&tmp2`).
- [ ] **Verify the full build on Ubuntu 26.04.** `array.c`/`hs.c` are the only compiled C files; the rest are C++ (`g++`), where these C-specific promotions don't apply, but GCC 15's `g++` may surface its own stricter diagnostics — if so, address separately. I couldn't run the full link here (no log4cxx/cppunit; sandbox is GCC 13/24.04).
- **Optional hardening:** these were latent type bugs; consider de-VLA-ing the `array_t tmp[SIZE(len)]` buffers (heap/bounded) as a separate cleanup — not required for the build.

### 2. Make linting gate the pipeline — DONE (pending user review + a real CI run)
- [x] **`lint_test.sh` gates on pylint ERROR/FATAL only** (style reported, non-gating; exit-bit `RC&3`). Verified categorization (undefined-var → gate fail; convention-only → no gate). IGNORE additions: `examples/demo_slicing.py` (stale demo, 89 findings) and `util/dynamic_distribution.py` (orphaned, built on `asyncore` which is removed in 3.12 — every importer is commented out; needs an `asyncio`/`selectors` port to revive). Reuses existing `fave/.pylintrc` via `--rcfile`.
- [x] **Fixed all ~12 genuine error-level findings** (the gate surfaced real latent bugs). Re-scan (E/F, import-error excluded) over the 127 linted files: **0 error/fatal findings remain** → gate green.
  - Core: `mapping.py` `super().__cmp__` → dict-equality (also un-inverted the logic); `topology.py` undefined `dtype` → `args.type`; `aggregator_service.py` `err.message` → `str(err)`.
  - Other: `check_flows.py` `.message`×2 → `str(...)` + misplaced-paren `json.load(open(p),"r")` → `open(p,"r")`; `switch.py` `add_rules(idx,[rule])` → `add_rules([rule])` (would have crashed); `np_preparation.py` `%s`→`%s %s`; `compare_fffuu6_fave.py` add `IP_BITS` param; `checkgen.py`×2 loop var `next`→`cur` (shadowed builtin → UnboundLocalError).
- [x] **CI lint job now gates** (removed `continue-on-error` in `.github/workflows/ci.yml`).
- [x] **First gating CI run (75587914483) FAILED — fixed three issues in `lint_test.sh`:**
  - **Broken IGNORE matching:** `[[ $IGNORE =~ <path> ]]` treated the file path as a regex against the IGNORE string, so glob entries (`*.py`) never matched → the vendored **Hassel** trees (`*/i2-hassel/*`, `*/stanford-hassel/*`) were linted and failed (py2 code, `E1101` etc.). Fixed: prune those trees + `deprecated/` at the `find` stage; specific-file ignores now use exact-path matching.
  - **Gate failing on env-fragile import resolution:** `checkgen.py` (`E0611 no-name 'AD6'`) and `microbench_parsers.py` (`E0401 import-error` ×, `E0611`). pylint resolves imports differently from the runtime `PYTHONPATH`, so these are noisy/non-deterministic. Policy: **do not gate on `import-error`/`no-name-in-module`** (`--disable`); real broken imports are caught by the fast/integration tiers anyway.
  - **Logs not verbose (user's idea):** failures printed only `FAIL` + a `/tmp/...log` path that never reached the CI log. Now prints the actual error/fatal messages in a consolidated section at the end (single-threaded, E/F only — not the style noise).
  - **Also pruned in-repo virtualenvs** (`*/.venv/*`, `*/venv/*`, `*/site-packages/*`): a local `.venv` inside `fave/` was being swept by `find` (804 files, 94 venv-internal "failures"). CI didn't hit this (uses `setup-python`, no in-repo venv), but it's a real robustness gap. Removed the stale `examples/example-traverse.py` ignore (file no longer exists).
- [x] **Local gate is GREEN:** `skipped 2, ok 16, style-only 111, failed 0` over the 129 real fave files — even without `pybison` locally (CI has it, so will be ≥ as clean). All 14 original CI failures addressed.
- [x] **CONFIRMED green on real CI** (user-verified). The `lint` job now gates. This was the last "check that doesn't gate" — `fast`, `integration`, and `lint` all gate; `e2e`/`bench` are non-blocking by design.
- **Finding (original):** `lint_test.sh` recorded counts but always exited 0, so `lint_fave` could never fail.

### 3. Re-enable coverage reporting — mostly absorbed by item 1b
- [x] **Report coverage** — `COVERAGE=1 ./test.sh <tier>` runs under `coverage` and prints a report (72% from the fast tier today).
  - [ ] Optionally add `--fail-under` so coverage cannot silently regress (deferred until a baseline is agreed).
  - [ ] Wire `COVERAGE=1` into the GitHub `test-*` jobs + upload the report as an artifact (belongs to item 0).
- **Finding:** CI ran `coverage run` but `coverage report` was commented out (`# && python2-coverage report`). Coverage was paid for but never seen.

---

## Medium priority — structural improvements

### 4. Add a dependency manifest — mostly DONE (item 1b)
- [x] Add a pinned `requirements.txt` (pure-Python: `cachetools`, `dd`, `filelock`, `graphviz`, `pyparsing`, `coverage`, `pytest`). `pybison` deliberately excluded (native build; documented as integration-only, stays in the Dockerfile) so the fast tier is pure-Python.
  - [ ] Have the `Dockerfile` install from `requirements.txt` instead of its unpinned inline `pip install` lines (and keep the `pybison` line). Not yet done.
- **Finding:** Dependencies lived only as unpinned `apt`/`pip` lines in the `Dockerfile`; env was not reproducible outside Docker.

### 5. Replace the manual test registry with discovery — DONE (item 1b)
- [x] **Use test discovery instead of a hand-maintained registry** — `test.sh` uses `pytest` discovery; the old hand-maintained `unit_tests.py` is bypassed. Discovery immediately surfaced 8 hidden `policy_translator` tests (incl. the never-run `test_grammar`, now item 1c) that the registry omitted.
  - [ ] Delete/retire the now-redundant `fave/test/unit_tests.py` and `policy_translator/test/unit_tests.py` registries once item 0 no longer references them.
- **Finding:** `fave/test/unit_tests.py` hand-imported and hand-registered every `TestCase`; new tests silently didn't run until someone edited this file. (Confirmed: `policy_translator`'s registry was hiding 8 tests.)

### 6. Add static type checking — DONE (core slice typed + gated; optional tightening below)
- [x] **Added `mypy` over the core modules, typed leaf-first and gated core-only.** The full core slice (28 modules: `rule`, `netplumber/*`, the `util/` helpers, all `devices/`, all `aggregator/`) is typed and `mypy`-clean; a gating `typecheck` CI job enforces it (steps a–f below all complete). Follow-ups since completed: the two flagged latent bugs are fixed (`Slice.from_json` ns_diff; `adapter.delete_probe` now uses `self.links`), and a `TraceLogger` type (a `logging.Logger` subclass used as a cast/annotation target) replaced the call-site and `adapter`-logger ignores. The core slice now carries **one** `type: ignore` total — the `logging.Logger.trace` monkeypatch assignment, irreducible without a riskier `setLoggerClass` refactor. A device `Protocol` to reduce `model: Any` was assessed as high-effort/low-value (Generator/Probe diverge from AbstractDeviceModel) and left as-is.
- [x] **Coverage extended beyond the original core slice** to the modeling layer that feeds it — **`iptables/`** (`parser`, `parser_singleton`, `generator`), **`topology/topology.py`**, **`reporting/`** (`reporter`, `report`), and **`util/lock_util.py`**. The gate now covers **35 modules**, and the typed `aggregator_service` no longer has any untyped imports. (`reporter._parse_cond` was refactored to compute `get_field_from_vector` once instead of 3×/field.) Notes: `parser` is a pybison boundary (handlers `-> Any`, `warn_return_any` off); `generator` navigates the `Tree` AST (a `_req()` non-None helper + asserts for grammar-guaranteed lookups, `FieldValue`-as-`str` narrowing, `tid: Union[int,str]`-as-`str` narrowing). py3 bug fixed in `parser`: `raise "..." % (...)` (raising a str) → `raise Exception(...)` at five branches. `iptables`/`topology` tests are integration-tier (not run here) — mypy-verified, behaviour-preserving; confirm on integration/e2e.
- [x] **`policy_translator/` fully typed** (all 8 modules: `policy_exceptions`, `policy_logger`, `fpl_grammar`, `policy`, `policy_builder`, `policy_translator`, the two `visualize_*`). It is a separate package (own `PYTHONPATH` root): added it to `mypy_path` and the typecheck script now discovers sections under both `fave/` and `policy_translator/`. The gate now covers **43 modules**. `policy_logger` got its own `TraceLogger` shim (for `PT_LOGGER.trace`). Two more py2→3 bugs found by typing: the report CSV opened `'rb'` then handed to `csv.reader` (py3 needs text) → `'r'`; and (in `policy_builder.match`) a sentinel var retyped bool→`re.Match`. Its 46 tests are in the fast tier, so this is test-covered, not just mypy-verified.
- [ ] **Remaining untyped (lowest value, optional):** assorted `misc/`/CLI tooling (`netplumber/{check_compliance,dump_np,print_np}`, `util/{bench_utils,json_util,parallel_utils}`). `util/dynamic_distribution.py` is dead (`asyncore`).
- **Finding (re-measured):** FaVe's own code is effectively **0% typed** — across ~1,149 function defs there are **zero** return annotations. The TODO's earlier "only 3 files use type hints" overcounts: two of those are vendored Hassel benchmark code (`bench/wl_i2/i2-hassel/headerspace/tf.py`, `bench/wl_stanford/stanford-hassel/headerspace/tf.py`) and only `iptables/parser.py` is ours. This is a green-field typing effort, not a top-up. A silent type/shape error undermines the soundness story of a verification tool (same rationale as the `array.c` fix, item 1h).

#### Criteria for a "core module" (intersection of three filters — not any one alone)
1. **Soundness-critical (on the verification path):** bugs here change verdicts → `rule/`, `netplumber/{vector,mapping,adapter,slice}.py`, `devices/`.
2. **High fan-in / foundational (leaf dependencies):** typing leverage flows bottom-up — you cannot meaningfully type a consumer whose params are untyped objects from another module. The internal import graph ranks these: `rule.rule_model`, `netplumber.vector`, `netplumber.mapping`, and the `util/` helpers (`ip6np_util`, `packet_util`, `match_util`, `model_util`, `collections_util`).
3. **Stable and actively maintained:** **reuse the lint exclusion list** (item 2) — exclude vendored Hassel trees, `deprecated/`, demo/example scripts, `np_reproduction/`, and the sibling detectors (`ad6`, `z3-anomalies`, `stl-anomalies` are separate codebases). Do NOT invent a second notion of "in scope."
- **Litmus test for borderline modules:** "If this returned the wrong shape, would a verification verdict silently change?" Yes → core. Glue/orchestration/reporting → not core (type opportunistically later).
- **Resulting core slice (~5–6k LOC of the ~12k in `fave/`):** `rule/rule_model.py`, `netplumber/{vector,mapping,adapter,slice,jsonrpc}.py`, `devices/*.py`, plus the `util/` helpers they import.

#### Migration strategy (the work is "make the code mypy-legible + wire it in like the lint gate", not just writing annotations)
- [ ] **a. Strictness ramp via per-module config, not a global `--strict`.** Repo defaults lenient; opt *core* into strict via `[mypy-rule.*]`, `[mypy-netplumber.*]`, `[mypy-devices.*]` sections. "Core module" becomes a literal, reviewable line in `mypy.ini`; the rest of the tree stays quiet (`ignore_errors`) during migration.
- [~] **b. Type leaves first, in dependency order:** `vector.py`/`mapping.py` → `rule_model.py` → `devices/` → `adapter`/`aggregator`. Each layer annotates against already-typed dependencies.
  - [x] `netplumber/mapping.py` + `netplumber/vector.py` typed (the header-space + field-mapping leaves). `mypy` green on all three typed modules together; `./test.sh fast` still 46 + 90. `Mapping(dict)` → `Mapping(Dict[str, int])`, `class Match`-style subclassing confirmed fine at runtime. These are true leaves (no untyped pass-through into returns) so their strict sections enable `warn_return_any = True`.
  - [x] **`util/ip6np_util.py` typed — and the payoff landed.** `mypy` green on all four typed modules together; `./test.sh fast` still 46 + 90. **`warn_return_any` is now ON for `[mypy-rule.*]`** — `rule_model`'s last untyped dependency is gone, so its conversions return concrete types instead of `Any` (exactly the leaf-first dividend the plan predicted). Notable decisions/findings:
    - **Circular import avoided:** `field_value_to_bitvector(field)` needs `RuleField`, but `rule_model` imports this module at runtime → imported `RuleField` under `if TYPE_CHECKING:` (annotations are PEP-563 strings, never evaluated at runtime).
    - **Dynamic dispatch tables** typed as `Dict[str, Callable[[Any], Any]]` (extracted the inline normalizer dict to a named local `normalizers`); the per-name signatures are genuinely heterogeneous, so `Any` is honest.
    - **Two latent crash paths surfaced by typing, both now handled gracefully (behavior-preserving for all real inputs — they previously *crashed*):** (1) `bitvector_to_field_value(vector: Optional[str], ...)` now early-returns `None` for a `None` vector instead of `len(None)`-crashing — this is the empty-`Match.intersect` path; (2) `field_value_to_bitvector` asserts `value is not None` after the `Vector` early-return (a `None` field value has no bitvector; previously raised `TypeError` deeper in).
    - **Latent bug NOT fixed (flagged for author):** `_normalize_rt_type` / `_normalize_ah_spi` can return a `Tuple[str, str]` (range form `x:y`), but the dispatch does `vector[:] = normalizers[name](value)` and `Vector.__setitem__` requires `str` → a range value on `module.ipv6header.rt.type` / `ah.spi` would crash (`str + tuple`). Typing made the `Union[str, Tuple[str, str]]` return explicit. Also `_normalize_frag_id` formats with `:032b` (requires `int`) but is dispatched with the string field value — typed `frag_id: int` to reflect the body; mismatch noted.
  - [x] **`util/packet_util.py` typed (pure leaf, only stdlib `re`).** `mypy` green on all five typed modules together; `./test.sh fast` still 46 + 90. Strictest section (`warn_return_any = True`). **Cascade: `warn_return_any` is now ON for `[mypy-util.ip6np_util]` too** — its (de)normalizer dependency is typed, so `bitvector_to_field_value` returns `Optional[str]` not `Any`. Behavior-preserving refactors strict mode forced: rebind-to-different-type avoided by new locals (`cidr` str stays str + `clen: int`; `laddr`/`raddr` str → new `lblocks`/`rblocks` lists). No logic change.
  - [x] **`util/collections_util.py` + `util/tree_util.py` typed (pure leaves).** `mypy` green on all 7 typed modules together; `./test.sh fast` still 46 + 90. `collections_util` typed with `TypeVar`s (`_K`/`_V`/`_T`) to preserve genericity; subtract/intersect take the second operand as `Dict[Any, Any]`/`List[Any]` (only membership matters). `tree_util.Tree(list)` → `Tree(List["Tree"])`, `value: Any` (generic AST payload); `__eq__(self, obj: object)` now returns `NotImplemented` for non-`Tree` (was an `AttributeError` on `.value`) — mypy-required `object` param, and the correct Python contract.
  - [x] **`match_util` + `model_util` deliberately skipped** — constant-only modules (no `def`s), already fully inferred by mypy; a strict section would check nothing. Consumers get their types regardless.
  - [x] **`util/path_util.py` typed** (used by `netplumber/slice.py`). `mypy` green on all 8 typed modules together; `./test.sh fast` still 46 + 90. Decisions: fall-through converters typed `Optional[...]` with explicit `return None` added (mypy `[return]`; behavior-identical); in-module consumers narrow with asserts (`_normalize_pathlet`, `Path.from_string`, `Path.__str__`) — turns implicit-`None` `TypeError`/unpack crashes into documented preconditions for invalid input. `json_to_pathlet` JSON/`Any` boundary handled with `cast(str, ...)`, so `warn_return_any` stays ON. `Path.__eq__` → `object` param + `NotImplemented`.
  - **Util-leaf layer for the core slice is now typed:** `ip6np_util`, `packet_util`, `collections_util`, `tree_util`, `path_util` (+ `typing_util`). Constant-only `match_util`/`model_util` need none.
  - [x] **`util/aggregator_utils.py` typed** (socket connect / framed send+recv, stdlib-only leaf). Guarded the unconditional `logger.warn` on the empty-recv error path (`logger` defaults to `None`) → falls back to the documented `None` return instead of crashing.
  - [x] **Gate infra: catch-all `[mypy-*] ignore_errors = True`** added (gradual-typing pattern) so a typed module can import not-yet-typed siblings without mypy reporting errors inside them; per-module strict sections override it. Verified it still catches planted errors in core modules.
  - [x] **`devices/` fully typed (base-first).** All 10 modules: `abstract_device`, `abstract_firewall`, `packet_filter`, `generator`, `probe`, `switch`, `application_layer_gateway`, `snapshot_packet_filter`, `router` (+ `__init__`). `mypy` green on all 18 typed modules together; `./test.sh fast` 46 + 90 throughout. Shared contract: `idx: int`, `ports` values heterogeneous → `Dict[str, Any]`, `wiring: List[Tuple[str, str]]`, `ingress/egress_port: str -> str`, `_adds: Dict[Any, List[Rule]]`. `Rule` imported under `TYPE_CHECKING` in the base (no cycle).
  - **Contract widenings forced by subclasses (typing-surfaced):** `internal_ports: Collection[str]` (firewall base — subclasses store a list *or* a dict, used only for `in`); ctor `ports` is `Iterable[str]`/`Collection[str]` (router needs `len()`+re-iteration) to fit the dict-passed-back-as-ctor-arg pattern in `__sub__` (re-prefixing oddity flagged); `table_ids` always-bound `Optional` instead of conditionally set + `hasattr`.
  - **Latent issues flagged for author (behaviour preserved):** (1) `SwitchCommand` del/upd in `switch.main()` passed a bare `Rule` to a `to_json` that iterates `rules` — wrapped in `[...]` (needs e2e check). (2) **`router.CAPACITY = 2**16 / 2**12` is a float**, so ACL rule `idx` becomes e.g. `16.0`; tolerated by `Rule.from_json`'s `int()` + numeric `__eq__` but serialises as `"16.0"`. **fixed under item 1q** (py2→3 artifact: now `//`, the `type: ignore` removed; e2e validation of the `"16.0"`→`"16"` wire-format change pending). (3) `ProbeModel._normalize_fields(None)` and `aggregator_utils` logger paths now degrade gracefully instead of crashing.
  - [x] **`netplumber/{slice,jsonrpc,adapter}.py` typed.** `mypy` green on all 21 typed modules together; `./test.sh fast` 46 + 90 (incl. the 10 `test_jsonrpc_client` contract tests). Decisions: `jsonrpc` and `adapter` are JSON/RPC-boundary modules → `warn_return_any` OFF. `adapter` is heavily duck-typed (`model` params span all device types with no common base; `logger` has a custom `.trace`) → `model`/`logger` typed `Any`. **jsonrpc payload params relaxed to `Any`** (ports, `match`/`mask`/`rewrite` vectors, `hs`/`ns` lists): typing the adapter proved the real wire values are integer global ports + `Optional[str]` vectors (and `add_slice` even passes `Vector` objects), not the `str`/`List[str]` first guessed — `Any` is honest for a pass-to-JSON boundary. Fixes: `setblocking(1)`→`setblocking(True)`; `_sendrecv` (dead) py2→3 `str+=bytes`.
  - **Latent bugs found and since FIXED:** `Slice.from_json` read `j["ns_list"]` for `ns_diff` (copy-paste) → now `j["ns_diff"]`; `adapter.delete_probe` `port2 in self.ports[sport]` indexed an `int` → now `self.links[sport]` (the dual of `delete_generator`), which also dropped a `# type: ignore[operator]`. Both paths (network slices; re-adding a probe) were unexercised by the e2e benchmarks, so the fixes only turn latent crashes into correct behaviour.
  - [x] **`aggregator/` fully typed** (all 8 modules: `abstract_engine`, `aggregator_abstract`, `aggregator_singleton`, `aggregator_signals`, `aggregator_mock`, `stop`, `aggregator_service`). `mypy` green on all **28** typed modules together; `./test.sh fast` 46 + 90. `aggregator_service` and the duck-typed parts are model/JSON-heavy → `model` params `Any`, `warn_return_any` OFF. `abstract_engine`'s `*args/**kwargs` stubs typed `-> Any` and confirmed Liskov-compatible with the adapter's concrete overrides. `AGGREGATOR` singleton typed `Any` (reassigned at startup; avoids a cycle). The `logging.Logger.trace` monkeypatch (in `aggregator_abstract`) is typed via a `TraceLogger` type (a `Logger` subclass used as an annotation/cast target); only the monkeypatch assignment itself keeps a `# type: ignore[attr-defined]`. Another py2→3 `str += recv()` bytes bug fixed in `aggregator_mock`. Minor fixes: `assert data != None`→`is not None`, `logging.logThreads/logProcesses = 0`→`False` (typeshed `bool`).
- [x] **e2e regression found & fixed (`wl_example`/`wl_up`):** typing `SwitchModel.table_ids` made it *always-bound* (`None` when unset) instead of *conditionally set*, which silently broke `adapter.add_tables`'s `hasattr(model, 'table_ids')` presence-check — it became always-True for switches and subscripted `None` (`TypeError`). Hit only by workloads with switches lacking `table_ids` (`wl_example`/`wl_up`); `wl_tum`/`wl_stanford`/`wl_i2` passed. **Fix:** `getattr(model, 'table_ids', None)` truthiness, which exactly reproduces the original `hasattr` behaviour for all three cases (no attr / `None` / dict) — verified at runtime. **Audited the whole tree: this was the only `hasattr`/presence-contract an always-bound conversion could break** (the only other `hasattr` is the `logging.Logger.trace` monkeypatch guard). Lesson: converting a conditionally-set attribute to always-bound-`Optional` can break `hasattr` callers — check call sites, not just the class.
- **The core slice (TODO 6 criteria) is now typed end-to-end:** data model (`rule`), header-space + mapping leaves, the `util/` helpers, all `devices/`, all `netplumber/`, and all `aggregator/`. 28 modules, `mypy` clean together, fast tier green throughout, committed module-by-module on `typing`.
- [x] **c. JSON-boundary convention — DONE and now shared.** `JSONDict = Dict[str, Any]`; `from_json(j)` resolved by splitting parse-from-construct (`jd = json.loads(j) if isinstance(j, str) else j`). As the second+third modules needed it, the alias was moved out of `rule_model.py` into the shared **`fave/util/typing_util.py`** (realizes step d) — `rule_model`, `vector`, `mapping` all import `JSONDict` from there. (`Mapping.from_json` additionally `cast`s the decoded dict to `Dict[str, int]` at the JSON boundary.) TypedDict promotion still deferred.
- [~] **d. Third-party stubs / missing-import handling + shared alias module:** `dd`, `cachetools`, `graphviz`, `pyparsing` need `types-*` stubs or per-module `ignore_missing_imports`. **`pybison` is native/integration-only → must `ignore_missing_imports`** so mypy runs in the pure-Python `fast` tier (mypy analyzes without importing, so it fits the fast tier cleanly). Handled globally for now via `ignore_missing_imports = True` in `[mypy]`; tighten per-module as leaves are typed. **Shared alias module `fave/util/typing_util.py` created** (holds `JSONDict`; domain-specific aliases like `FieldValue` stay local to their module to avoid back-dependencies, e.g. `FieldValue` would pull `netplumber.vector` into `util`).
- [x] **e. Dynamic patterns cataloged (retrospective).** The patterns this step predicted were largely non-issues: builtin-collection subclassing (`Match`/`Mapping`/`Tree`) works via parameterized aliases; static `from_json` factories via a parse-split (`jd = json.loads(j) if isinstance(j, str) else j`) + covariant returns; polymorphic attributes via `Union` aliases (`FieldValue`, `Rule.tid`); **no `setattr`/dict-as-record found**. The real dynamic cost was **duck-typed `model: Any`** in `adapter`/`aggregator_service` (a heterogeneous device set with no common base) plus the JSON/RPC `warn_return_any`-off boundaries. Net residue across the 28 modules: **one `# type: ignore`** (the `logging.Logger.trace` monkeypatch) + 2 `cast`s at JSON trust boundaries. The bugs that earlier needed ignores (`delete_probe`, `Slice`) were fixed, and the `trace` call-site ignore was removed via `TraceLogger`.
- [x] **f. Wired in as a gating CI check (like pylint, item 2).** New `fave/test/typecheck_test.sh` runs mypy **once** over the core slice (cross-module inference) and gates on any error; the catch-all scopes reporting to core. New gating `typecheck` CI job (pure-Python, no native stack — mypy is static). Verified the gate bites (planted error → exit 1) and passes clean (28 modules → exit 0). Decisions (with user): **gate immediately** (core is already clean) rather than non-gating-first; `mypy` added to `requirements.txt` **unpinned** — prefer benefiting from improved checking over version stability, and fix code promptly if a newer mypy flags a real problem. **Checked-file set is DERIVED from mypy.ini's `[mypy-<module>]` sections** (single source of truth: adding a strict section auto-extends the gate, no second list). Benign `unused section(s): [mypy-*]` note does not affect the exit code.

#### Suggested first step (pilot to calibrate effort before committing to the whole slice)
- [x] **Pilot on `rule/rule_model.py` — DONE.** Fully typed (467 LOC, ~100 insertions / 68 deletions); `mypy.ini` skeleton added with a strict `[mypy-rule.*]` section; `PYTHONPATH=fave mypy --config-file mypy.ini fave/rule/rule_model.py` → **Success: no issues**; `./test.sh fast` still **46 + 90 passed** (behavior preserved).
- **Calibration read (effort):** ~1 hour for 467 LOC including investigation. The mechanical annotation is fast; the time goes into (a) reading consumers to fix polymorphic types right and (b) the small refactors mypy forces. Extrapolating, the ~5–6k-LOC core slice is on the order of a few focused days — *if* leaves are typed first so consumers aren't fighting `Any`.
- **Conventions decided against real code (now in place):**
  - `from __future__ import annotations` at module top (lazy annotations; clean forward refs).
  - JSON boundary: `JSONDict = Dict[str, Any]`; `from_json(j: Union[str, JSONDict])` with the `str`-or-parsed union resolved by a small refactor — `jd: JSONDict = json.loads(j) if isinstance(j, str) else j` (split parse-from-construct, not `@overload`), exactly as planned in 6c. Aliases are pilot-local; **move to a shared `util/typing.py` when the migration expands** (6d).
  - `FieldValue = Union[str, Vector, None]` — the `None` arm is **real, not defensive**: `Match.intersect` feeds `RuleField.intersect`'s result (`bitvector_to_field_value(...)`, `None` for an all-ignore vector) straight back into a `RuleField`. Construction sites elsewhere always pass `str`.
- **Type-model gaps mypy surfaced (genuine, fixed in the pilot):**
  - `RuleAction` (explicitly the *abstract* base) had no `to_json`, yet `Rule.to_json` calls it on every `List[RuleAction]` element → added an abstract `to_json` raising `NotImplementedError` (subclasses already override; semantically inert).
  - The `from_json` dispatch dict `{"forward": Forward, ...}` can't be proven to carry `.from_json` on the joined class type → annotated `Dict[str, Any]` (a constructor dispatch table is honestly heterogeneous).
  - Invalid legacy type-comment `# type: [Field()]` on `Rewrite.rewrite` (mypy rejects it) → real annotation `self.rewrite: List[RuleField]`.
  - `Match(list)` → `Match(List[RuleField])` so element access is typed.
- **Decisions to carry forward:**
  - `warn_return_any` is **OFF** in `[mypy-rule.*]` for now: `rule_model` calls still-untyped leaves (`util.ip6np_util`, `netplumber.vector`) that return `Any`; flipping it on is gated behind typing those leaves (6b). This is concrete evidence for the **leaf-first** ordering.
  - mypy is **not yet in `requirements.txt`/CI** — install is dev-only for the pilot. Add a dev/test dependency + a non-gating `lint`-tier mypy step when wiring in (6f).
  - **Latent bug noted, NOT fixed (out of scope):** `Match.intersect` sorts `self` twice (`match2 = sorted(self, ...)` should be `sorted(other, ...)`) and indexes `match1[idx1]` before the `idx1 < len(...)` guard. Typing doesn't catch logic bugs; flag for the author.
  - **Unused import noted, NOT removed:** `FIELD_SIZES` is imported but unused in `rule_model.py` (pre-existing). Left as a pylint-tier cleanup to avoid changing import side-effects in a typing change.
- **Open decision (unchanged):** continue leaf-first into `netplumber/vector.py` + `netplumber/mapping.py` (then turn on `warn_return_any` for `rule.*`), or lock the full core scope list first. (Recommended: continue leaf-first — the pilot validated the approach.)

---

## Verification-engine-specific (high leverage, longer term)

### 7. C++ hardening for NetPlumber
- [ ] **Add sanitizer (and later coverage) builds for NetPlumber**
  - [ ] CI job building with `-fsanitize=address,undefined` running `make test`.
  - [ ] Longer term, add `gcov`/`lcov` C++ coverage.
- **Finding:** NetPlumber is the soundness-critical core; no sanitizers/coverage in CI.

### 8. Differential / oracle testing across detectors
- [ ] **Cross-check FaVe verdicts against Z3/STL oracles**
- **Finding:** Three independent anomaly detectors (`ad6`, `z3-anomalies`, `stl-anomalies`) plus the `np_reproduction` HSA baseline exist.
- **Fix:** Cross-check FaVe's verdicts against Z3/STL on the same rulesets as a property-based oracle. Disagreements are bugs or interesting findings. Highest-value correctness lever specific to FaVe.

---

## Resolved questions

- **Is the GitLab pipeline still the active CI?** No — GitLab CI is inactive and will remain so. Migrating to GitHub Actions (item 0).
- **Is dropping Python 2 support intended?** Yes — drop Python 2 entirely and fix all `python2`/bare `python` references (item 1).

---

## Suggested order of work

1. ~~Item **1** (Python 3)~~ ✅ · ~~Item **1b** (`test.sh` runner)~~ ✅ · ~~Items **4, 5**~~ ✅ (absorbed by 1b) · Item **3** mostly ✅.
2. Item **0** (GitHub CI migration) — now thin: jobs just call `./test.sh <tier>`. Plus item **2** (gating lint).
3. Item **1c** (triage quarantined `test_grammar`) and item **6** (mypy) — structural.
4. Items **7–8** (deeper, verification-specific).
5. *Then:* expand coverage with new, more sophisticated tests (user's stated next phase).
