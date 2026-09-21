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

### 0a. GATE before any headline measurement: discharge the generality debt
- [ ] **Feasibility work has deliberately collapsed the configuration space; unwind it before quoting a headline number.** Owner framing 2026-09-11: *"In this stage, this is fine but we need to generalize again when we want to work towards the real measurements."* The binding distinction is not general-vs-workload-specific but **whether a choice affects the number being reported** — selection scaffolding (`--pairs`, `--dry-run`, `--witness`, the NP leaf parser, the two measurement drivers, which sit off the production path by design) is harmless; the encoding, the solver and the session structure are not. Eight items, each to be discharged or explicitly restated: mandatory `--lite-acyclic` on i2 (a tool limitation, not a preference); solver-per-problem-class breaking uniformity; `--fresh-per-query` vs the persistent session being *different* measurements (the 439x cold/warm effect); `probe_untag` off being a parity not a fidelity choice; APKeep's unfixed per-device projection; a `--skip-acyclic` refutation being UNSAT-on-a-relaxation; and the deliberate loss of any flag reproducing the pre-fix per-device admission;
and (added 2026-09-11) **which GROUNDING CONSTRAINT closed the SECRYPT'15 gap** — rank vs
s-t flow are not interchangeable (rank is property-agnostic, flow is reachability-specific
and forces `--fresh-per-query`) and do not cost the same (7.0x wall on wl_stanford N=16
under a MATCHED configuration -- the 21.7x first recorded here was flow at its best
solver against rank at its worst, and the gate caught it),
so a table mixing them mixes encodings. **Two further findings from the same pass:** the
wl_stanford driver `bench/ad6_faithful_measure.py` hardcodes `Minisat22` with no acyclic
option and stamps none of it, so discharging items 1/2/8 there is CODE work rather than
documentation; and the gate needs a second clause — *state the denominator, never compare
totals across different query counts* — since §5.5's "~13x slower per query" is actually
total-wall/total-wall over 72 queries vs 256 (per query: ~62x, or ~22x against the
post-admission-fix Stanford baseline). **A third instance, 2026-09-21:** wl_up's
check count moved 11,911 -> 18,811 when `reach_csv_to_checks.py`'s denied-cell branch
was fixed to cover every endpoint of a multi-device role (item 12 / C7). All 6,900
added checks pass, so no wl_up verdict changes -- but `AD6_PLAN.md`,
`APKEEP_BACKEND.md` and `APKEEP_BDD_BASELINE.md` all quote the 11,911 denominator
throughout and are now annotated at their first mention rather than rewritten,
because each of those measurements was correct for the denominator it had. **The gate: every collapse of the configuration space must be a stamped result field, never an undocumented habit** — if a measurement-affecting choice has no stamp, add the stamp before quoting the number. Full checklist: [`AD6_PLAN.md`](AD6_PLAN.md) "Generality debt: the pre-measurement checklist".
  - **NOT debt despite looking like it:** the per-(port, VLAN) admission fix is a model correctness fix, general by nature — it changed wl_stanford identically, and its `_ANY_PORT` fallback adds generality by defining a case no benchmark has.

### 0. Migration to GitHub CI — DONE (workflow added; needs real-CI validation of heavy tiers)
- [x] **GitHub Actions workflow added: `.github/workflows/ci.yml`, jobs invoke `test.sh <tier>`.**
  - [x] Skeleton: triggers `push: [main]` + `pull_request` + `workflow_dispatch`; `runs-on: ubuntu-24.04` (matches Dockerfile base / README platform).
  - [x] **Native runner, not a baked image.** Chose a native runner over building/pushing the `Dockerfile` to GHCR: the Dockerfile `COPY`s the repo and builds+tests at *image-build* time, which fights per-PR testing (a `container:` job would mount a fresh checkout over the pre-built tree). Native install matches the tier philosophy (fast=native, integration=full stack) and tests the actual checkout. System deps are installed inline with the Ubuntu-24.04 package names from the Dockerfile (`liblog4cxx15`, `libcppunit-1.15-0`, `flex`, `bison`, `build-essential`).
  - [x] Jobs → tiers (updated in item 1g): `fast` → `bash test.sh fast` (pure-Python; **gates**); `lint` → `lint_test.sh` (non-gating until item 2); `integration` → `COVERAGE=1 bash test.sh integration` (build + C++ tests + bison tests, no live backend; **gates**); `e2e` → `bash test.sh e2e` (test_rpc + smoke; **non-gating**, `continue-on-error`); `bench` → `bash test.sh bench` (`workflow_dispatch` only). Heavy native setup shared via composite action `.github/actions/setup-fave-native`.
  - [x] Coverage artifact uploaded from the integration job; gating intent documented (fast = required gate).
  - [x] **`fast` job validated end-to-end locally** (clean venv + `pip install -r requirements.txt` + `bash test.sh fast` → 46 + 80 passed).
  - [x] **First real CI run analyzed** (run 75323499335). `fast` + `lint` ran fine; NetPlumber built; `integration` FAILED. Diagnosis below.
  - [ ] **Validate `integration`/`bench` on real CI** — first run failed; quick fixes applied (below), RPC/C++ items still open. **`bench` is additionally blocked by item 1r** (2026-09-09: the tier never waits for the backend, so it reports wrong verdicts and exits 0, and it cannot complete at all on the default 63 MB `/dev/shm`) — validating it on CI before 1r would only certify a vacuous pass.
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
- **Follow-up — `net_plumber/setup-ubuntu.sh` was stale; UPDATED 2026-06-24.** It carried Ubuntu-20.04 package names (`liblog4cxx10v5`/`libcppunit-1.14-0` — neither exists on 24.04, so the script failed there), omitted `build-essential`, and cloned+built BuDDy which the default build doesn't use. Rewritten for 24.04: correct lib names, `build-essential` added, `--no-install-recommends -y`, `apt-get update` + `set -e`, BuDDy dropped with a comment explaining how to re-enable the optional BDD path (`-DUSE_BDD` + `LIBS += -lbdd` are both commented out in `sources.mk`/`objects.mk`; only the standalone `buddy_test` target links `-lbdd`). Names now match the Dockerfile and the CI composite. **Still open (DRY):** the three lists (`setup-ubuntu.sh`, `Dockerfile`, composite action) are kept in sync by hand — consider sharing one dep list.
- **Native-build snags found while building the stack locally (2026-06-24)** — neither blocks CI, and the documented `fave/setup.sh` path already handles both:
  - **`python3-dev` is required for the native bison tests.** `pybison` *generates* a parser in C at runtime and compiles it against `Python.h`; without the headers the bison-dependent tests **segfault (exit 139)** with a confusing core dump rather than a clean error (the real message is `tmp.y:5: fatal error: Python.h: No such file or directory`). **Already covered:** `fave/setup.sh` installs `python3-dev`, the Dockerfile installs it, and the CI composite gets headers via `actions/setup-python`. The segfault only bites a setup that skips `fave/setup.sh` (as my manual reproduction did). No code change needed — noted so the failure mode is on record.
  - **Report tooling (LaTeX) was missing from `fave/setup.sh`; ADDED 2026-06-24.** `fave/setup.sh` installed `pandoc`+`inkscape` but not the LaTeX engine `pandoc report.md -o report.pdf` needs, so the report step would fail (`pdflatex`/`lmodern.sty not found`) for anyone setting up via the script — even though the Dockerfile and the CI composite (item 1m) already had the minimal set. Added `texlive-latex-base` + `texlive-latex-recommended` + `texlive-fonts-recommended` + explicit `lmodern`, with the same comment as the Dockerfile. The three dep sources now agree.
  - **`make all` won't rebuild a stale binary after a lib upgrade.** A pre-built `net_plumber` binary linked against an older `liblog4cxx` failed at runtime with `undefined symbol: ...log4cxx...addFatalEvent...`; `make all` reported "nothing to be done" (object timestamps current) and left the broken binary in place. A `make clean && make all` fixed it. Minor, but worth a note for devs whose system libs move under a previously-built tree.

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
  - [ ] **`test_rpc` next bug (CI run 75548766906; REPRODUCED locally on native stack 2026-06-24):** the port fix worked (it now connects — verified locally: socket reaches `raddr=...:44001`), revealing a stale API mismatch — `jsonrpc.py:57` (`_async_send`, `for sock in socks`) expects a **list** of sockets (multi-NetPlumber support), but `test_rpc` passes a single `self.sock` → `TypeError: 'socket' object is not iterable`. All 4 `test_rpc` tests fail in `setUp` at `init(self.sock, 1)`.
    - **NEW — the same misuse exists in production code, not just the test:** `netplumber/print_np.py:104,107` builds a single `sock` and passes it to `jsonrpc.print_topology(sock)` / `print_plumbing_network(sock)`, which would hit the identical `TypeError`. Production `aggregator/.../adapter.py` correctly passes the `self.socks` **list** everywhere, so the contract *is* "list of sockets" — `print_np.py` and `test_rpc` are the two stragglers.
    - **Fix direction is a judgment call (don't fix unprompted):** (a) test-only — pass `[self.sock]` at the `test_rpc` call sites (mechanical, multi-site) — but leaves `print_np.py` broken; or (b) library-side — make the `jsonrpc.py` entry points normalize a lone socket to `[sock]` (fixes both `test_rpc` and `print_np.py`, but widens the typed `List[socket.socket]` contract). Recommend (b) since two independent callers got it "wrong" the same way. e2e/non-gating.
  - [ ] **Promote `e2e` to gating** once `test_rpc` + smoke are reliable on real CI.
- **Note:** `integration` gating is currently effective for the build + bison Python tests; the C++ `make test` failures are still *silent* (exit 0), so the gate does not yet catch them — see items 1h (triage) and 1i (make `make test` propagate).

### 1h. C++ header-space soundness regression — FIXED (single root cause)
- [x] **Fixed:** `array_isect`/`array_has_x`/`array_has_z` `len % 4 == 0` masking (see below). This **single fix resolves both** `test_is_equal_regression2` **and** `test_compact_regression`, plus the new `array_unit` len4 microtests. User's full `make test` run passes; replicated exactly against the fixed `array.c` (`hs_is_equal(compact(a), b_wrong)=false`, `hs_is_equal(compact(a), c_correct)=true`).
- [x] **CONFIRMED locally on a clean native build (2026-06-24):** built the native stack on Ubuntu 24.04 (GCC 13) and ran `make -C net_plumber/build test` → **`OK (94)`, exit 0**. The two regression tests (`test_compact_regression`, `test_is_equal_regression2`) and the new len4 microtests all pass against the fixed `array.c`. This is the first time the C++ suite has been *run* (not just inspected) since the fix — it stands.
- **CAVEAT — does not clear the `example.sh` 7/13 flow mismatch (item 1p).** The unit suite is green, but the live `example.sh` flow check still mismatches 7 of 13 flows on the same binary. So either (i) the mismatch is on a path the regression tests don't cover, or (ii) `example.sh`'s expected flows are stale. Triage needed — see item 1p.
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

### 1i. C++ test runner propagates failures — DONE (CONFIRMED on a real build 2026-06-24)
- [x] **`run_tests()` now returns `collectedresults.wasSuccessful()`; `main` does `return run_tests<...>() ? 0 : 1` on `--test`** (`net_plumber/src/net_plumber/main.cc`). Chain: `./net_plumber --test` exits non-zero on any CppUnit failure → `make test` fails (target has no error suppression) → `test.sh integration` sets `rc=1` → the **gating** `integration` CI job fails. Safe now that the suite is green (1h fixed): it exits 0 today and stays green, but will catch any future C++ regression.
- [x] **Confirmed on a real build (2026-06-24):** with cppunit/log4cxx installed and a clean rebuild, `make -C net_plumber/build test` returns **exit 0** on the green suite (`OK (94)`), and `test.sh integration` reports `RESULT: integration PASSED`. The propagation chain is now exercised end-to-end, not just inspected.

### 1p. Surface swallowed `example.sh` flow-test failures — DONE (assertion/finding split, 2026-06-25)
- [x] **`example.sh` now gates on flow *assertions* and exits with `check_flows`'s code.** The old unconditional `exit 0` is replaced by `exit $FLOW_RC`; `check_flows.py` exits non-zero iff a flow *assertion* failed.
- [x] **Expectation lives in the caller, not the oracle (revised design).** `check_flows.py` stays a **pure oracle** — it reports per check whether the assertion holds (exit 0) or not (non-zero), with no notion of "soft"/"finding"; its multi-spec `-c` batch is unchanged. `example.sh` invokes it **once per spec** and pairs each with an external expectation (parallel `NAMES`/`SPECS`/`EXPECT` arrays; `EXPECT[F9]=fail`), applying a 2×2: `pass+expect-pass → ok`, `fail+expect-fail → SOFT_OK` (known finding confirmed), and either mismatch → `FAILURE`. Only a FAILURE gates (exit non-zero). This keeps softness out of the production input language (every finding is equal to the engine; the user decides). The earlier inlined `?`-marker prototype was reverted per design review.
- **Bug fixed in passing:** `check_flows` crashed with `ZeroDivisionError` when a run performed **zero** checks (empty `_MEASUREMENTS` → mean/min/max) — latent in batch mode, hit by per-spec runs of probeless specs. Guarded.
- **Resolution of the mismatch (was 7/13, now the single F9):** the other six were **real soundness bugs** fixed by the NetPlumber work (item 1h + #C1–#C3). The remaining one — `! s=hs1 && EF p=hp2 && f=related:0` — is **not a bug**: the FORWARD chain ACCEPTs NEW ICMPv6 (a deliberate, standard practice), so NEW (`related:0`/wildcard) ICMPv6 legitimately reaches hp2; FaVe correctly detects this policy-vs-config discrepancy. It is annotated as an expected finding (`EXPECT[F9]=fail`) with a rationale, so e2e stays green while still surfacing it as SOFT_OK. (Diagnosis: of 32 hs1→hp2 leaves, 14 are ESTABLISHED icmpv6 (related:1), 14 NEW icmpv6 (related wildcard), 2+2 ESTABLISHED tcp/udp; the wildcard-`related` leaves are the finding.)
- **Pre-existing latent issue surfaced (separate, flagged):** F1 and F6 are table-only checks (no `p=` probe) that **broad mode silently skips** — so they have never actually been verified by this demo; in non-broad mode they currently *fail*. Kept as broad no-ops (EXPECT=pass) to preserve existing behavior; worth deciding later whether to check them in non-broad (and fixing whatever they then surface).
- **Old wording (superseded):** `... || echo "some example flow tests failed"` and an unconditional `exit 0` swallowed everything.
- **Reproduced on the native stack (2026-06-24):** `check_flows.py` (line 206, 13 flow specs) reports `failure: the following flows mismatched: ... which is 7 of 13`, then line 207 prints `some example flow tests failed` — but the script ends with an **unconditional `exit 0` (line 232)**, so `test.sh`'s `run_smoke` (`bash examples/example.sh || rc=1`) never trips. Confirmed: the e2e tier's FAILED result came **solely** from `test_rpc` (item 1g); this >50% flow mismatch passed green. The 7 mismatched flows were:
  `s=hs1 && EX t=fw0.pre_routing && EF t=sw0_1 && EX p=hp2` · `s=hs1 && EF p=hp2 && f=related:1` · `s=hs2 && EX t=sw0_1 && EX t=fw0_pre_routing && EF p=hp1` · `s=hs2 && EF p=hp1` · `s=hs2 && EF p=fp` · `s=fs && EF p=hp1 && f=related:1` · `s=fs && EF p=hp2 && f=related:1`.
- **Two separable concerns (don't conflate):** (1) the **swallow** — CI hygiene, this item; (2) the **mismatch itself** — a possible *correctness* signal. 7/13 wrong in the *basic* example is large; it may be a live symptom of the header-space soundness path in **item 1h** rather than a stale-fixture issue. The `array.c` masking fix (1h) was applied to the source, but the local `net_plumber` binary was rebuilt clean against that fixed source and the mismatch still shows — so either the fix doesn't cover this path, or the expected flows in `example.sh` are themselves stale. **Needs triage before promoting e2e to gating** — cross-ref item 1h's caveat.
- **Theme:** same "checks that don't gate" smell as the lint script (item 2) and the old coverage report (item 3).

### 1t. ad6 test runner propagates failures — DONE (2026-09-09)
- [x] **`ad6/test/test.py` now ends `sys.exit(0 if RunSuites(suites) else 1)`; all eleven `test/*suite.py` classes now `return self._runner.run(self._suite)`.** The exact ad6 counterpart of item 1i's C++ fix, and the same "discarded output" failure mode this section's theme line names.
- **Finding:** `make test` exited **0 on a run containing six errored tests** (`FileNotFoundError: 'minisat'`/`'clasp'`). The verdict was dropped at two independent layers: every suite called `unittest.TextTestRunner.run()` — which *returns* a `TestResult` — and threw it away, returning `None`; and `test.py` ran `for suite in suites: suite.run()` then fell off the end of `__main__`, never calling `wasSuccessful()` or `sys.exit()`. Fixing either layer alone would not have been enough. Found by re-checking a suite that had gone red, not by reading the code — a person skimming the tail saw the last suite print `OK`.
- **Fix:** test-first (`ad6/test/runner/runnertest.py` + `ad6/test/runnersuite.py`, registered — item 11's lesson from `ad6/FAVE_CHANGES.md`), with the new verdict logic extracted to `ad6/test/suiterunner.py` so it is directly testable. `RunSuites` fails **closed** (a suite returning no result counts as a failure) and does **not** short-circuit (one red suite must not stop the rest of the tree being tested).
- **Verification:** pre-fix, all ten registered suites failed the new layer-1 contract test *while `make test` still exited 0 with those ten failures in it*. Post-fix: clean tree → 11 suites / 88 tests, exit **0**; a temporary injected `self.fail(...)` in a registered test → `test.py` exit **1**, `make test` exit **2**. Full write-up: `ad6/FAVE_CHANGES.md` item 24.
- **Flagged, not changed:** `ad6/test/qbfsuite.py` is a pre-existing **unregistered** suite (same class of gap as `FAVE_CHANGES` item 11's never-registered `testCIDRMatchAll`). It got the one-line `return` for consistency but was deliberately not wired into `test.py`, since that could surface unrelated failures. Worth deciding separately.

### 1u. `fast` tier ran from the wrong CWD — 14 benchmark-driven tests never ran in any tier — DONE (2026-09-09)
- [x] **`test.sh`'s fast tier now runs its fave step from `fave/`, like the `integration` and `e2e` tiers already did.**
- **Finding:** every fave test consuming generated benchmark inputs locates them via a CWD-relative `_PREFIX = "bench/<wl>"` (the convention in all 10 such files). The fast tier was the only fave step running from `$ROOT`, so that prefix was unresolvable and the tests **skipped themselves as "inputs not generated"** — in every tier, permanently and silently, since no tier ran them from anywhere else. This hid 11 ad6 tests that pass (including `test_ad6_wl_stanford_plain.py`'s N=2 live-NetPlumber differential, the only real live-backend ad6 differential in the project) plus `test_apkeep_ndd_wlup.py`. Exactly the "a skip is NOT a pass" hazard `fave/test/backend_gate.py` was written to prevent — whose own docstring already names "generated inputs missing" as a condition that must not silently skip.
- **Fix:** make the fast tier honour the same cwd invariant as the other tiers, rather than splitting the `_PREFIX` convention in two. Two dependent changes came with it: three ad6 files moved into `FAVE_INTEGRATION_TESTS` because they have genuine native dependencies the fast tier must not acquire (`test_ad6_wl_up.py` → pybison; `test_ad6_wl_stanford{,_plain}.py` → a libnetplumber worker), without which the cwd fix would make `fast` *error* rather than skip on a machine with no native stack; and the integration tier now generates wl_up's inputs, which is required rather than optional because `FAVE_REQUIRE_BACKENDS=1` (how CI invokes that tier) turns a missing generated input into a hard failure.
- **Verification:** `fast` 301 passed/21 skipped → **298 passed/8 skipped**, and the 8 remaining skips changed reason from the misleading "wl_up inputs not generated" to the honest "JPype or the NDD jar is unavailable". Integration's pytest step 15 passed/22 skipped → **29 passed/24 skipped**. The three moved files under `FAVE_REQUIRE_BACKENDS=1`: 14 passed, 2 skipped (the opt-in `AD6_STANFORD_FULL_DIFFERENTIAL` guard, a plain `skipUnless`), no hard failure.
- **Still open (separate, not fixed here) — the `fast` tier's coverage floor is unreachable in CI by construction, and two test files are misfiled.** `COVERAGE_MIN=79` is only met with the JVM stack present: **measured 69.9% without the jars, 85% with them** (both on the full tier; an earlier 81.2% estimate here was low because it counted only `fave/apkeep/*` on the pre-jar denominator, while running those tests also imports more modules — 8,647 → 9,163 statements — and covers more than that package). The decision this forces:
  - **CI's `fast` job has no Java at all.** It is a separate runner from the `integration` job with no artifact passed between them, and its setup is only `pip install -r requirements.txt` — no JDK, no Maven, no JPype. That is deliberate: `.github/actions/setup-fave-native` keeps `pybison`/`JPype1` integration-only "so `fast` remains pure Python". So `test_apkeep_ndd_{fwd,wlup}.py` can **never** run in CI's fast job no matter where the jar is built (2026-09-09: the jar is now built in `integration`, item above / `fave/test/ndd_build.sh` — that makes the stack reproducible but does not and cannot change this).
  - **Those two files' dependency footprint says `integration`, not `fast`** — they need JPype + a built jar, exactly what `fast` is defined to exclude. They only ever *looked* pure-Python because they always skipped. They are also what makes `fast` slow: ~2s → **96s** (169s under coverage), essentially all of it these two, dominated by one test (`test_i2_faithful_vlan_matches_ground_truth`, ~77s). A tier documented as "<1s, the inner-loop gate (run on save)" is not that at 96s.
  - **So: either** move both files to `integration` (where they can actually run, and whose CI job already has the toolchain) and drop the floor to ~70 to match what a pure-Python tier really covers, **or** accept that the 79 floor is a local-only figure and CI's fast job is red on it. The first looks right on every axis (tier taxonomy, runtime, CI reachability) but it lowers a ratchet, which the convention says never to do downward — hence a decision to take deliberately, not a fix to slip in.

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

### 1n. wl_ifi smoke: PolicyTranslator input — INPUT FILES RESOLVED (verified 2026-06-25); swallow still open
- [x] **Missing wl_ifi input files committed + `benchmark.py` adapted (by Claas, commit `bfee2856`).** Added `fave/bench/wl_ifi/roles_and_services.txt` (182 lines) and `reach.txt` (13 lines) under standard file names, and adjusted `benchmark.py` (2-line change) to use them. This removes the original blocker (the files were simply never in the repo).
- [x] **Verified end-to-end on my native stack (2026-06-25):** `python3 bench/wl_ifi/benchmark.py` → **exit 0, no `Fehler:` line**, policy matrix generated from the committed files, full pipeline runs (topology/routes/probes → flow trees → anomalies), and a fresh `report.md`/`report.pdf` is produced (pandoc + LaTeX from item 1m now installed). The report's Compliance Check lists the expected reachability violations (e.g. `source.external.ifi reaches probe.Internet`, multiple `... reaches probe.admin.ifi`), so the verification path actually ran — not just a clean skip. Confirms the user's setup result reproduces here.
- [ ] **Still open — the benchmark swallows a failed sub-step (silent-failure theme, same as 1p/1i).** `policy_translator.py:67` still prints `"Fehler: Datei(en) konnte(n) nicht gelesen werden."` and `sys.exit(1)` on unreadable input, but the wl_ifi `benchmark.py` proceeds regardless ("generated policy matrix") and the non-zero exit is ignored. It no longer *triggers* (files exist now), but the latent swallow remains: if the input ever goes missing again, the benchmark would still pass green. Decide whether to make the benchmark fail on a non-zero sub-step. Minor extra: the error string is hardcoded German in an otherwise-English codebase.

### 1o. NetPlumber build breaks on GCC 14+ (Ubuntu 26.04) — FIXED (verify on 26.04)
- [x] **Fixed `-Wincompatible-pointer-types` errors in the C headerspace code.** GCC 14 promoted a family of C warnings to **default errors** (`-Wincompatible-pointer-types`, `-Wint-conversion`, `-Wimplicit-function-declaration`, `-Wimplicit-int`, `-Wreturn-mismatch`). On Ubuntu 24.04 (GCC 13) these only *warned*; on 26.04 (GCC 15) they fail the build. The reported error (`array.c:329`) was `&tmp` (a `char[]`/`array_t[]`) passed where the callee wants a plain `T*` — same address, wrong type. Dropped the erroneous `&` at: `array.c:270,329,335,850`; `hs.c:259,261,276,278,313,316` (compiled), plus `array.c:998` (in the dead `#ifdef NEW_HS` path, for completeness).
- **Validated locally** by forcing the GCC-14 diagnostics to errors on GCC 13 (`-Werror=incompatible-pointer-types -Werror=int-conversion -Werror=implicit-function-declaration -Werror=implicit-int -fsyntax-only`): `array.c` and `hs.c` both compile clean (rc=0). This also caught two sites a naive grep missed (`hs.c:276,278`, `&tmp2`).
- [ ] **Verify the full build on Ubuntu 26.04.** `array.c`/`hs.c` are the only compiled C files; the rest are C++ (`g++`), where these C-specific promotions don't apply, but GCC 15's `g++` may surface its own stricter diagnostics — if so, address separately. I couldn't run the full link here (no log4cxx/cppunit; sandbox is GCC 13/24.04).
- **Optional hardening:** these were latent type bugs; consider de-VLA-ing the `array_t tmp[SIZE(len)]` buffers (heap/bounded) as a separate cleanup — not required for the build.

### 1r. `bench` tier is vacuous — nothing waits for the backend (found 2026-09-09)
- [x] **Add a real completion barrier before `_report`. DONE 2026-09-09** (`util/barrier.py` + `test/test_barrier.py`, 14 fast-tier tests). Client arms a per-request barrier, puts its path in the message, and blocks; the aggregator releases it in a `finally` after handling, passing the exception text on failure. Because the aggregator is single-threaded FIFO and `check_compliance` is synchronous down to net_plumber, "message N finished" transitively means "everything earlier applied AND net_plumber answered". **No timeout, by design** — FaVe's runtime is unknowable in advance, so a deadline is both too tight (a premature timeout is a FALSE failure, the worst outcome for a compliance tool) and too loose. The wait is bounded by EVIDENCE instead: it continues only while the releaser is provably the live aggregator (owner file with pid + start time; zombies and pid reuse both rejected, since `os.kill(pid, 0)` and bare `pgrep -f` are fooled by a `<defunct>` process). Prerequisite `jsonrpc` EOF fix landed separately. Effect on wl_i2: the benchmark process went from 7.4 s to **422 s**, i.e. it now actually waits — the aggregator's `links` task alone is 339 s.
- **Mechanism (reference):** `GenericBenchmark.run` never waits for the verification to finish, so the tier times message-*sending*, reports whatever `report.md` happens to contain, and exits 0. Three independent fire-and-forget seams, all confirmed in the code:
  - `_wait_for_fave` blocks on `SoftFileLock("np_dump/.lock")`, but that lock is only ever created by the **dump** path (`aggregator/aggregator_service.py:226`, `netplumber/dump_np.py:137`). All four bench workloads use the constructor default `use_dump=False`, so they take `_wait_for_fave`, which acquires an unheld lock and returns in ~0.1 s. It is a **no-op for every bench workload**.
  - `bench/compliance_checker.py` imports only `connect_to_fave`/`fave_sendmsg` — **no `recv` at all**.
  - `reporting/report.py` likewise only sends `{'type':'report'}` and closes; the aggregator writes `report.md` asynchronously afterwards.
- [x] **`_report` converts the PREVIOUS workload's report. FIXED 2026-09-09** — `reporting/report.py` now blocks on a barrier before returning, so `pandoc` sees the report the aggregator just wrote. Measured before: `report.pdf` 4m27s OLDER than `report.md`; after: 1 s apart.
- **Mechanism (reference):** Because `report.py` is async, `_report`'s `pandoc report.md -o report.pdf` runs on whatever is already on disk. Measured on the wl_i2 run: `report.md` mtime 09:01:41 vs `report.pdf` 08:57:14 — the PDF is **4m27s older than the markdown**, and is wl_stanford's. (The item-1n swallow fix, commit `0a0b7ee9`, surfaces the sub-steps' *exit codes* correctly but sits on top of this race: necessary, not sufficient.)
- **CORRECTED TWICE 2026-09-09 — read this carefully, the record oscillated.**
  1. *Originally claimed:* "the tier reports WRONG verdicts and exits 0 -- wl_i2
     claimed 35 of 72 pairs 'does not reach' while the oracle says all 72 are
     reachable; early report = 35, after 285 s of waiting = 0, RACE CONFIRMED."
  2. *The EXPERIMENT was invalid* (found while validating the barrier fix):
     `reporting/reporter.py:117` renders only
     `self.events[self.last_compliance:cur_event]`, and line 178 advances that
     watermark inside `dump_report`. The discriminator called `_report()` twice,
     so its `0` was an EMPTY DELTA, not a corrected verdict. Nothing about a
     race was demonstrated, and the "285 s of waiting" was irrelevant.
  3. *The CLAIM is nevertheless true*, re-established by a sound route that does
     not depend on that experiment — see the artifact comparison in **item 1s**.
     wl_i2's expected verdict really is 0 violations and the tier really does
     report 35; what was wrong was my evidence, not the conclusion.
  The intermediate "whether 35 is correct is UNKNOWN / `reachable.json` cannot
  adjudicate `checks.json`" note was also wrong and is withdrawn: the two encode
  the same question (item 1s proves the pair sets are set-equal).
- **What the barrier work did establish (all verified):** the completion barrier
  was genuinely missing, the tier's runtimes were measuring message-sending
  only, and `report.pdf` really was converted from a stale `report.md`. See the
  fix note below.
- **Measured phase split (2026-09-09, yolobox, logs redirected to disk, single run each).** The verification is almost entirely POST-EXIT:

  | workload | benchmark process | backend after exit | real total | recorded NP engine (cross-check) |
  |---|---:|---:|---:|---|
  | wl_up | 12.4 s | 34.2 s | **46.5 s** | 49 s (`APKEEP_TUM_UP_PLAN.md:663`) |
  | wl_tum | 4.7 s | 6.0 s | **10.7 s** | 6.58 s build (`APKEEP_TUM_UP_PLAN.md:78`) |
  | wl_stanford | 2.4 s | 2.0 s | **4.4 s** | ~1.4 s build (`APKEEP_BACKEND.md:434`) |
  | wl_i2 | 7.4 s | 281.4 s | **288.8 s** | 341 s (`APKEEP_BACKEND.md:271`) |

  So 74 % (wl_up) to 97 % (wl_i2) of the real work happens after `benchmark.py` has already exited rc=0. The totals corroborate the recorded engine numbers well, from a different harness and machine. Per-phase detail: every phase inside the process is 0.0–8.3 s; the only non-trivial ones are `_pre_preparation` (wl_up 8.3 s, ruleset generation) and `_initialization` (wl_i2 3.5 s, sending 77k routes). Instrumented externally by patching `GenericBenchmark.run` from a throwaway driver — no repo change.
- **Why smoke/e2e look fine:** it is a race, not a designed wait. wl_example/wl_ifi are small enough that `net_plumber` usually answers before `_report` runs, so the smoke tier wins the race and the bench tier loses it. Verdict correctness was checked against an oracle **only for wl_i2**; wl_up/wl_tum/wl_stanford are timed but their verdicts are unverified and should be assumed affected until shown otherwise.
- **Decision needed (async contract — author's call, do not change unilaterally):** (a) have `compliance_checker.py`/`reporting/report.py` await an ack from the aggregator; (b) make `_wait_for_fave` wait on something that is actually held for the non-dump path; or (c) have the aggregator expose a "queue drained" query the benchmark polls. (a) and (c) change the aggregator protocol; (b) is the smallest but needs a lock that the non-dump path genuinely takes.
- **Blocks item 0's "validate `bench` on real CI":** certifying the tier green before this is fixed would only certify a vacuous pass.
- **Related:** the correctness-gating half is **item 1s** (the tier still cannot fail on a wrong verdict). The two runtime-robustness bullets under item 10 (backend death, teardown-doesn't-reap) were both re-confirmed while measuring this — see their `CONFIRMED 2026-09-09` lines. Same "checks that do not gate" theme as items 1i/1n/1p.

### 1s. `bench` does not gate on correctness — and wl_i2's verdict is wrong (found 2026-09-09)
Item 1r made the tier *honest* (real runtimes, no stale reports, failures raised).
It did **not** make it a *gate*: `benchmark.py` renders `report.md` and exits 0
whatever it says. Nothing compares the verdict to an expectation, so a wrong
answer passes green. Validating `bench` on CI (item 0) is worth little until this
is closed.

#### The oracle question, stated explicitly
**For each bench workload: what is the expected compliance verdict, and what
artifact establishes it?** Without a per-workload answer there is nothing to
gate against. Status:

| workload | checks in `checks.json` | negated (`!` = must NOT reach) | oracle artifact | expected violations | status |
|---|---:|---:|---|---:|---|
| wl_i2 | 72 | 0 | `bench/wl_i2/reachable.json` (72 pairs) | 0 **per the POLICY** | **NOT a usable gate** — see below |
| wl_stanford | 240 | 0 | `bench/wl_stanford/reachable.json` (240 pairs) | 0 **per the POLICY** | **NOT a usable gate** — same defect |
| wl_up | 11 902 | 8 532 | none tracked | computable, not yet computed | **OPEN** |
| wl_tum | **0** | 0 | n/a | n/a — checks nothing | **VACUOUS** |

**The key structural fact, measured: every check in all four workloads is `EF`**
(existential reachability) — `s=source.X && EF p=probe.Y`, optionally negated.
None use `EX`/`AF`/`AX`, waypoints, or conditions. So ONE mechanism — a
reachability oracle plus the per-check negation flag — can adjudicate the whole
tier; there is no need for four bespoke expectations.

- **CORRECTED — `reachable.json` is NOT an independent oracle; my "set-equal"
  evidence was circular.** I had argued that wl_i2 and wl_stanford "expect 0"
  because the `(source, probe)` pairs in `checks.json` are set-equal to those in
  `reachable.json`. They are — but **tautologically**: `gen_wl_i2_inputs.sh:41`
  emits `checks.json`, `cchecks.json` AND `reachable.json` from the *same*
  `roles.txt`/`reach.txt` via one `reach_csv_to_checks.py` invocation. Same
  generator, same input, so of course they agree. `reachable.json` records the
  **policy intent**, not verified data-plane truth, and set-equality proves
  nothing about the network.
- **Worse, the oracle cannot discriminate over-approximation.** Per
  `AD6_PLAN.md:2040` (the author's own caveat): wl_i2's `reachable.json` is a
  COMPLETE all-reachable mesh — every one of the 9x8 pairs expected reachable,
  **zero expected-unreachable pairs** — and therefore has "zero discriminating
  power". Any backend that *relaxes* a constraint reports MORE reachability and
  so scores a perfect 72/72 by construction. An all-reachable oracle can only
  catch under-approximation, never over-approximation. **Gating on it would
  therefore certify over-approximating backends as correct.** Same defect on
  wl_stanford (240/240 all-reachable).
- **Caveat on wl_stanford's oracle:** `reachable.json` there is the *artificial
  all-to-all policy* from the HSA/NetPlumber papers, not the data plane
  (`APKEEP_BACKEND.md:278`). It is therefore fine as a *regression* expectation
  ("this run still agrees with the tracked artifact") but should not be read as
  the scientifically meaningful reachability answer — the faithful-VLAN work
  measures 165, not 240.
- **wl_up is open but tractable:** 8 532 of its 11 902 checks are negated, so the
  expected verdict is *not* 0 and has to be computed — violations = positive
  checks whose pair is unreachable, plus negated checks whose pair IS reachable.
  That needs a wl_up reachability oracle; `eval/mat_apk.json` is a frozen BDD
  reachability baseline rather than a compliance expectation, so it is a
  candidate input to that computation, not the answer.
- [ ] **wl_tum checks NOTHING — its `checks.json` is empty (0 entries).** Its
  compliance phase is vacuous by construction: it cannot report a violation, so
  gating it would be meaningless until it has checks. Decide whether wl_tum is
  supposed to have a compliance policy at all (it is a single-firewall
  ruleset-scale workload, so possibly it is deliberately a *performance* rather
  than a *compliance* benchmark) — and if so, say so explicitly rather than
  leaving an empty file that reads like a bug.

An alternative to absolute expectations, worth weighing before building: gate on
a **cross-backend differential** (FaVe+NetPlumber == FaVe+APKeep on the same
checks) and treat *agreement* as the invariant. That reuses the mechanism the
integration tier already trusts, needs no per-workload oracle, and would have
caught the wl_i2 discrepancy below — but it cannot catch a fault both backends
share. **Decision needed before building anything.**

#### The wl_i2 discrepancy — and who has actually been cross-checked
- [ ] **FaVe+NetPlumber reports 11 pairs unreachable on wl_i2 where the policy expects 0.** Measured 2026-09-09 with the in-process `NetPlumberLibAdapter` + `InProcessFaVe` (same driver and same `i2-json` inputs `test_apkeep_i2` uses), reading verdicts from `get_compliance_results()` — so no aggregator, no RPC log, no Reporter. Build 552 s, compliance check 0.6 s, peak RSS 1051 MB. The 11: `chic` → `{hous, kans, losa, salt, seat}`; `atla`/`newy32aoa`/`wash` → `{salt, seat}`. Concentrated on the two western routers.
- **Who has actually been cross-checked on wl_i2 (audited 2026-09-09):**
  | backend | wl_i2 reachability | recorded where | VLAN modelling |
  |---|---|---|---|
  | ad6 | 72/72, `oracle_match: true` | **YES** — `bench/wl_i2/eval/ad6_i2_{cadical195,glucose4}_lite_72pairs_complete.json` carry the full `reach_matrix` | **`faithful_vlan: false`** on every recorded run |
  | APKeep | 72/72, missing=0/extra=0 | no artifact; asserted live by `test_apkeep_i2` | "the VLAN is just link identity" (that test's own docstring) |
  | NetPlumber | **never verified** | — | HSA, models the `rw=vlan:V` rewrite |
  `bench/apkeep_vs_netplumber.py` measures **time only** (`_from_zero_run` returns elapsed; `_benchmark` reports ms) — its "NetPlumber 341 s vs APKeep 14 s" is not a correctness result. `test_backend_differential`, which is where `test_netplumber_matches_oracle` lives, is `_PREFIX = "bench/wl_ifi"` — **wl_ifi only**. So "all backends agree on wl_i2" means *ad6 and APKeep agree with the policy*; NetPlumber was not in that comparison.
- **What `routes.json` says directly (checked 2026-09-09, no engine):** the model is in-stage VLAN admission (390 rules matching `vlan=V` per in-port) feeding out-stage LPM (77 451 rules matching `ipv4_dst`, each doing `rw=vlan:V` + `fd=`), and probes are existential on **`vlan=0`**. Two structural checks:
  - the **router-level topology is fully connected** (26 edges over 9 routers), so all 72 pairs are graph-reachable — the 11 are not missing links;
  - a **port-level walk over the real FIB with match fields IGNORED also reaches all 72** (473 nodes, 77 841 `fd=` rules, no wildcard-in-port rules).
  So the 11 failures are produced by **field constraints, not structure** — specifically the coupling of in-stage VLAN admission with the out-stage VLAN rewrite, which is exactly the dimension ad6 (`faithful_vlan: false`) and APKeep ("VLAN as link identity") relax.
- **Two readings, and the evidence now favours the second:**
  1. NetPlumber (or the model as loaded) is wrong by 11 pairs, and ad6/APKeep are right.
  2. The i2 data plane genuinely does not provide all-to-all reachability under the faithful VLAN rewrite; **NetPlumber is the only backend strict enough to see it**, and ad6/APKeep miss it because they relax VLAN — invisibly, because the oracle has no expected-unreachable pairs. Relaxing a constraint can only ADD reachability, which is precisely how both land on 72/72.
  Reading 2 is consistent with every piece of evidence above, but is **not proven**: NetPlumber's own rewrite handling could equally be at fault, and nothing here rules that out.
  **SUPERSEDED 2026-09-09 by the three-query faithful run: the evidence no longer favours reading 2.** ad6 with in-stage admission AND all 77,451 out-stage egress rewrites modelled still reports both discriminators REACHABLE, so "NetPlumber is the only backend strict enough to see it" is not supported — a second engine is now strict on the same dimension and still disagrees. Reading 1 (NetPlumber, or the model as loaded, is wrong by 11 pairs) is back in play on equal footing, and the SAT witnesses are what can separate them. See the result item above and [`AD6_PLAN.md`](AD6_PLAN.md) §5.5 "C3 ANSWERED".
- [x] **DECIDED 2026-09-09 (owner): run the FULL faithful i2 model with three queries. RAN 2026-09-09 (untag OFF) — RESULT: decision-table case 2, NetPlumber NOT corroborated.** Control `hous→salt` reachable (agrees, 614.4 s), both discriminators `chic→salt` (63.4 s) and `chic→seat` (1,246.9 s) come out **reachable** where NetPlumber says unreachable. `status: completed`, wall 2,697 s, peak 18,416 MB, 7,274,800 vars / 17,683,953 clauses. **This falsifies this section's own leading hypothesis** — the 11 pairs are NOT the in-stage-admission × out-stage-rewrite coupling that C4 part 1 built, and they are not the probe untag either (neither comparison backend enforces it, and this run had it off), so **both candidate explanations are eliminated**. The disagreement localises to one engine and neither is trustworthy on wl_i2 until root-caused. **Next step, and it is a finite check rather than another engine comparison:** all three answers are SAT, so each is a *witness* — extract the assignment for `chic→salt` (the cheap pair), read off the path and per-hop VLAN, and check it against `routes.json` by hand. Either the witness is a legal path (NetPlumber is at fault) or it violates the FIB (ad6's faithful encoding is still too weak, and the witness names where). Needs a small model-extraction addition to `bench/ad6_i2_measure.py`. **Untested hypothesis, not a finding:** i2's sources are VLAN-unconstrained and an ad6 query is existential, so the solver may be free to *choose* an arriving VLAN satisfying each admission gate, where the real network fixes it by link. Full writeup: [`AD6_PLAN.md`](AD6_PLAN.md) §5.5 "C3 ANSWERED". Recorded in [`AD6_PLAN.md`](AD6_PLAN.md) §5.5 "C3 REOPENED" with the full rationale, risks and prerequisites; that is the primary home, this is the pointer. Induced sub-topologies were **considered and rejected for now**: a subset removes paths, so an UNSAT there would not prove unreachability in the full model, and the owner chose not to introduce that error potential before trying the real thing. Query set, drawn from the recorded Cadical195 `query_log`:

  | query | ad6 plain | NetPlumber | role |
  |---|---:|---|---|
  | `source.hous → probe.salt` | 1.11 s (fastest of 72) | reachable | agreement control |
  | `source.chic → probe.salt` | 3.43 s | **unreachable** | discriminator |
  | `source.chic → probe.seat` | 4.50 s | **unreachable** | discriminator |

  Outcome decides C3: if ad6-faithful also reports the two discriminators unreachable, plain mode is insufficient for i2 (C3 NO-GO, C4 on) and NetPlumber's 11 are corroborated. If it still reports them reachable, the disagreement localises to one engine and must be root-caused before either is trusted.
  **Environment:** the box is being raised **16 GB → 20 GB** for this run (owner, 2026-09-09) — plain-mode `peak_rss_mb` is 13,432 MB and is build/DIMACS-dominated, so it is query-count-INDEPENDENT and the faithful encoding will exceed it. Instrument RSS; an OOM before the first query is a live possibility even at 20 GB.
  **Read the result with these caveats:** all 72 recorded ad6 queries are `sat: true`, so every recorded time is a SAT time and a lower bound — the two discriminators are expected to flip to UNSAT, a regime this workload has never exercised and whose cost is unknown. Fixed cost is ~405 s per run regardless of query count. Do not extrapolate full-set runtime from three queries drawn deliberately from the fast tail (recorded spread: 1.11 s to 1688.8 s).
  **Prerequisites:** see the two checkboxes below.
- [x] **Correct `bench/ad6_i2_measure.py`'s docstrings — DONE 2026-09-09 (commit `251d8c9c`, branch `ad6`), found independently by the ad6 session the same day.** Both sites named below are rewritten: the module docstring now carries a `WORKLOAD SCOPE` note (this script measures dst-IP-ONLY reachability, not the workload NetPlumber and the faithful NDD run answer) and `_build_ir`'s explains that the flag stays off because turning it on would NOT yield a faithful i2 model — `Ad6Adapter` has no `_capture_out_rewrite`, so faithful mode would add in-stage admission with no matching egress rewrite. **Deliberately NOT in the docstring, by owner decision 2026-09-09: the 11-pair NetPlumber finding itself.** Research findings belong in a non-code document; the docstring points at `AD6_PLAN.md` §5.5 instead, so the finding is recorded once and the code comment cannot drift from it. **NB the line numbers below are now stale** (the rewrite is longer): the `faithful_vlan=False` hardcode is line 132 and the result stamp line 163. Original finding, for the record: Two sites state the reasoning C3 was reopened over, so anyone reading the script is told faithful VLAN is unnecessary for i2:
  - **line 25** (module docstring): *"but PLAIN mode (faithful_vlan=False — i2's out-tables are a clean dst-IP FIB, in-tables collapse to a single internal port, **no VLAN modelling needed per §5.5's own C3 gate**)"*;
  - **lines 92-95** (`_build_ir`): *"see §5.5 C3: **whether faithful-VLAN modelling is even needed for i2 is gated on whether plain mode already matches the oracle**, so this script never turns faithful_vlan on"*.
  Both rest on plain-mode-matches-oracle, which is guaranteed for any relaxed encoding against an all-reachable mesh and therefore proves nothing (see the corrected oracle section above, and `AD6_PLAN.md` §5.5 "C3 REOPENED"). Replace with the actual status: plain mode is what has been MEASURED so far, the oracle cannot distinguish it from a faithful encoding, and FaVe+NetPlumber reports 11 of 72 unreachable on the same inputs. Also worth a line pointing at the recorded artifacts (`eval/ad6_i2_*.json`, all `faithful_vlan: false`) so the mode a result was produced in is not lost. Note line 132 stamps `"faithful_vlan": False` into every result record — that stays correct, and becomes load-bearing once faithful runs exist alongside plain ones.
- [x] **Add the switch and the selector the experiment needs — DONE 2026-09-09.** `bench/ad6_i2_measure.py` now takes `--faithful-vlan`, `--probe-untag`, `--pairs SRC>PROBE,...` (order-preserving, bare or fully-qualified names) and `--dry-run`, and its module docstring carries the full run recipe. Built test-first: `fave/test/test_ad6_i2_measure.py`, 34 tests in the `fast` tier, confirmed failing beforehand. **Three guards, each against a SILENT wrong answer rather than a crash:** (a) an unknown router name in `--pairs` is an error naming the offender and listing the real names, not an empty query selection — and it is resolved right after the ~6 s IR build, so a typo costs the replay and not the run; (b) `--probe-untag` without `--faithful-vlan` is refused, because `probe_vlan_literals()` returns `[]` on a plain IR, so the run would stamp `probe_untag: true` while measuring the untagless model; (c) `_forced_literals` refuses any forced variable name absent from the base encoding — the `IncrementalSession._index_for` hazard in the open, since an invented index is unconstrained and the untag would be vacuous. **The untag had to be wired into this script separately from `ad6/fave_bridge.py`:** the script drives PySAT directly (that is what lets it swap solvers and split build/DIMACS/solve), so the bridge's `extra_vars` plumbing never runs here. Also stamps `faithful_vlan`/`probe_untag`/`probe_vlan`/`out_rw_rewrites` into every result, so an artifact says which of the three models produced it. **Validated by dry-run against the real model:** plain unchanged (18 devices, 77,460 fwd_rules, `out_rw_rewrites: 0`, 81 queries), faithful `out_rw_rewrites: 77451`, both faithful modes resolving the 3 pairs, and the untag's literals confirmed as 12 all-negated per-bit variables on each probe's `probe_fanout_probe_<role>` aggregate.
- [~] **Write `Ad6Adapter._capture_out_rewrite` (C4) — the out-stage half DONE 2026-09-09, the probe untag still OPEN.** The rewrite side is built test-first and validated on the real model: all **77,451** of i2's out-stage `rw=vlan:M` actions are now captured (9 devices, matching `routes.json` exactly, 0 failing to key onto a real route), emitted as `ir["out_rw"]` scoped to the devices surviving the out-stage collapse, and consumed by `favemodel._build_device_table`. 17 new fave-side tests + 6 new ad6-side tests through a real Kripke/CNF build+solve, all confirmed failing beforehand by A/B; plain-mode IR byte-unchanged (`fwd_rules` 77,460 in both modes) so the recorded plain figures stay reproducible. Full writeup: [`AD6_PLAN.md`](AD6_PLAN.md) §5.5 "C4 PART 1", `ad6/FAVE_CHANGES.md` §25.
  - [x] **Probe untag DONE 2026-09-09 — built OPT-IN and DEFAULT OFF, on a finding that changes the experiment's design.** `Ad6Adapter(probe_untag=True)`, `_probe_vlan` captured from the probe model's `test_fields` (not `filter_fields` — verified by instrumenting a real replay, where i2's `filter_fields` and `match` are both empty so reading either captures nothing silently), and `favemodel.probe_vlan_literals()` wired into `fave_bridge.py`'s per-query `extra_vars`. 22 new tests, all confirmed failing beforehand; validated on the real model (9/9 probes at `vlan=0`, each resolving to its `probe_fanout_*` aggregate, since every i2 probe has 18–36 attachments). Writeup: [`AD6_PLAN.md`](AD6_PLAN.md) §5.5 "C4 PART 2" + PROBE-UNTAG PARITY FINDING, `ad6/FAVE_CHANGES.md` §26.
    - **Why off by default — neither comparison backend enforces this on i2.** `netplumber/adapter.py:1009` builds the header space from `test_fields` and then two `XXX: deactivate ... memory explosion` guards discard it, sending `test={"type":"true"}` (line 1053) with a match vector from `model.match`, which is **empty** for every i2 probe. `apkeep/adapter.py:1460` gates `tvlan` on `self._stanford and self._faithful_vlan`, so i2 passes `None` — despite `test_apkeep_ndd_fwd.py:166`'s docstring listing "probe untag", which overstates the code. So **the 11-pair NetPlumber disagreement cannot be the untag**, and enforcing it unconditionally would make ad6 the strictest of the three engines.
    - [x] **Consequence for the three-query run: do it with the untag OFF first** — DONE 2026-09-09, see the result above. That was the like-for-like configuration against NetPlumber's 11, and it disagrees on both discriminators.
      - [x] **WITNESS CHECK DONE 2026-09-10 — the primitive works, the divergence is localized to ONE hop with no NetPlumber run, and every model-side explanation checked is CLEAN.** Three witnesses extracted (`--witness`, faithful, cadical195; wall 2,950 s, peak 18,454 MB). **Zero model slack on all three** — every walk uses every true transition edge (n nodes = n−1 edges), so the acyclic constraints leave exactly one path and the extraction is exact, not a search through noise. The control walk is a real Internet2 route (hous→kans→salt) on a pair both engines call reachable, so the primitive is validated against known-good ground truth. **Localization, for free:** the discriminator's walk differs from the mutually-agreed control only in its first hop (`in.chic→out.chic` vs `in.hous→out.hous`); the five-hop tail is identical and NetPlumber accepts it for Houston traffic. `chic→seat` routes *through* salt, so one defect at the Chicago→Kansas entry explains **both** discriminators — consistent with `chic` being the worst offender in NetPlumber's 11. **Both model-side explanations checked, both clean:** every out-stage rewrite on the path lands on a VLAN the downstream in-stage admits (0 violations, 4 hops), and port-scoped too (`in.kans.400022` admits exactly vlans 10/20/30, precisely what `out.chic` writes toward kans). That also weakens the VLAN-choice hypothesis — no illegal choice is needed. Writeup: [`AD6_PLAN.md`](AD6_PLAN.md) §5.5 "WITNESS CHECK DONE".
      - [ ] **ROOT CAUSE FOUND 2026-09-10 (step (c), NetPlumber flow dump): ad6's per-device admission gate IS the cause of the Chicago pairs. NetPlumber is right; ad6's SAT answers are false positives.** `out.chic.220045 → in.kans.400029` rewrites **2,545 routes to vlan 10**, and that specific arrival port admits `{11,20,21,30,31,32,40,60,70}` — **not 10**. Only 2 routes (vlan 20/30) are admitted, and the dump shows exactly 2 branches reaching `in.kans`. Model-wide, only two crossings have any per-port rejection (`out.chic→in.kans` 2,545 rejected/2 accepted; `out.kans→in.chic` 19/5,674) and **2,555 of those 2,564 rejections — 99.6% — are accepted by ad6's per-device model**. The dump also reproduces the 11 pairs *exactly* through a different NP output path than `get_compliance_results()`, so the 11 are real and reproducible. **Two corrections to my own earlier entries:** the finding below recorded as "not the cause" IS the cause (my check aggregated per device — the same error I had just criticised in ad6), and "both model-side explanations clean" was wrong for the same reason: the witness path is legal only under ad6's *relaxed* admission. **Still unexplained: the other 6 pairs** (`atla`/`newy32aoa`/`wash` → {salt,seat}) — no other crossing has a per-port rejection, and `atla` reaches seat's tables yet never delivers to `probe.seat`; the structural dump is exhausted there and the deferred header-space decode stops being optional. Writeup: [`AD6_PLAN.md`](AD6_PLAN.md) §5.5 "STEP (c) DONE".
      - [x] **DONE 2026-09-10: ad6's faithful admission is now a per-(port, vlan) relation.** Capture side (`Ad6Adapter._capture_in_admission`) reads each in-stage rule's own `in_ports` and records `{device: {port: {vlans}}}`, emitted as `ir["in_vlans"] = {device: {port: [vlans]}}`; encoding side (`favemodel.py`) gives every admitted port its own two-rule gate — `fw_<dev>_iadm<port>_r0` carrying just that port's VLAN disjunction, then an unconditional `..._denyall` → DROP — and `entry_key` routes both `wire_edges` and `_gen_firewall` into it, so it cannot be bypassed. The gate hands off to the port's own ingress-ACL group if it has one, so admission and ACL compose in series. **Verified at full i2 scale with no engine and no solve:** 223 admitted ports (identical to `in_admit`'s 223), 596 (port, vlan) pairs, and `in.kans` port `400029`'s gate carries exactly `{11,20,21,30,31,32,40,60,70}` — not 10 — while `out.chic.220045` rewrites to `{10,20,30}`; `in.kans` emits 51 rules and its fwd rule carries 0 fieldmatches, so the device-wide fallback correctly does not also fire. 15 new ad6-side tests through a real Kripke/CNF build+solve (`PortScopedAdmissionTest`) + 20 new fave-side capture/IR tests (`test_ad6_wl_i2_admission.py`), and the three superseded `TestAd6StanfordInAdmission` assertions rewritten. **Three subtleties the tests pin:** the trailing denyall must be unconditional (`_HandleRule` wires each rule's FALSE edge to the next rule in *document* order, so a conditional last rule leaks rejected traffic into the next group); a port with no admitted VLAN resolves to `DROP_KEY` (a generator attaches without passing through `_gate_dead_ingress`); and a rule naming no `in_ports` falls the whole device back to the device-wide gate, because under-approximating it would turn this over-approximation into a false UNSAT. `favemodel._in_vlans_for` still reads the pre-fix flat shape so archived IRs stay reproducible; nothing emits it any more. **i2 three-query run MADE 2026-09-10 — the control answers FASTER, the discriminator becomes INTRACTABLE; suggestive of the flip but NOT proof.** Recipe step (c) verbatim, 6 h timeout, build 771.5 s, peak RSS 18,501.7 MB (pre-fix 18,416.0, as predicted, survived on ~1.9 GB of swap). `hous→salt` (control): **SAT in 425.8 s** vs pre-fix 614.4 s — 1.4x *faster*. `chic→salt` (discriminator): pre-fix **SAT in 63.4 s** → **no answer in 20,302 s** (5h38m, ≥320x). `chic→seat` not reached. **The asymmetry is the signal:** a cheap SAT is cheap because a model exists to exhibit, and refutation is categorically harder — so this is the signature of a flipped verdict, consistent with `chic→salt` now being UNSAT and ad6 agreeing with NetPlumber. It is *not* proof; an undecided query is undecided. §5.5's recorded "case 2" (all three SAT) is superseded either way, since it was produced by the projected gate. Artifact: `bench/wl_i2/eval/ad6_i2_faithful_untagoff_portscoped_partial_sandbox.json`.
        - [x] **SETTLED to strong evidence (not formal proof) 2026-09-11 by a skip-acyclic grounded-witness probe — the fix removes exactly the grounded paths it should.** `--faithful-vlan --skip-acyclic --fresh-per-query --witness --solver cadical195` completed all three queries in **932.9 s on a 9,061.4 MB peak**, against the full encoding's 20,302 s with no answer at 18,501.7 MB. Control `hous→salt`: **grounded** 395-node walk, the real `hous→kans→salt` route. `chic→salt`: **no grounded walk**, 7,656 ungrounded edges (pre-fix it had a *grounded* 249-node path via `chic→kans→salt`). `chic→seat`: **no grounded walk**, 15,417 ungrounded edges (pre-fix grounded, 619 nodes). Both pre-fix Chicago witnesses ran **through `in.kans`** — exactly where `out.chic.220045` delivers `vlan=10` into a port admitting `{11,20,21,30,31,32,40,60,70}`. **Formally solid half:** the control's witness is zero-slack (394 edges / 395 nodes = one simple path, which admits a valid rank assignment), so relaxed-SAT + zero-slack grounded witness *soundly implies* full-encoding SAT. The converse does not hold, so `chic→salt` UNSAT is the strongly-evidenced reading — four independent strands (route/VLAN arithmetic, NetPlumber's flow dump, the grounded path vanishing under the fix, the control surviving) — but only a full-encoding UNSAT is proof. Artifacts: `ad6_i2_skipacyclic_freshpq_portscoped_sandbox.json`, `ad6_i2_skipacyclic_witness_portscoped_sandbox.json`.
        - [x] **ANSWERED 2026-09-11 by the flow encoding — decision-table CASE 1: control SAT, BOTH discriminators UNSAT.** `--faithful-vlan --skip-acyclic --fresh-per-query --flow-path --solver cadical195`: `hous→salt` **SAT 124.9 s**, `chic→salt` **UNSAT 78.4 s**, `chic→seat` **UNSAT 324.8 s**; whole run 1,374.3 s on a 9,093.5 MB peak. The rank encoding could not answer `chic→salt` in 20,302 s. `oracle_missing` is exactly `{salt: [chic], seat: [chic]}` with `oracle_match: false` — correct and expected, since `reachable.json` encodes the all-reachable 72/72 *policy expectation* and both NetPlumber and faithful ad6 say the network does not implement it. **§5.5's C3 question is answered: plain mode is insufficient for i2 and NetPlumber's 11 are corroborated by an independent engine on the Chicago pairs.** The grounding constraint cost 1,092,512 clauses built in 2.192 s against the rank encoding's 14,253,423 — 13x fewer, matching the ~1.2M estimate. Artifact: `bench/wl_i2/eval/ad6_i2_flowpath_portscoped_sandbox.json`.
        - [x] **VALIDATION DONE 2026-09-11 — the flow encoding reproduces the rank encoding EXACTLY on wl_stanford, in both directions.** Full 16-router faithful model under `--flow-path`: `reachable_pairs` **165**, identical to the rank encoding, and the **reach matrices are identical across all 16 probes** — not merely the totals, which two encodings can match while disagreeing about which pairs. 256 queries of which **91 are UNSAT**, i.e. exactly the refutation direction, against a NetPlumber-proven answer; N=2 agrees identically too (2 of 4). Cost: variables 322,496→**83,088**, clauses 851,631→**313,555** (+68,180/query), query time 2,039.7→**63.2 s (32x)**, wall 2,131.7→**98.2 s**, peak RSS 4,173.5→**1,442.0 MB** — despite the flow path paying 256 fresh solver bootstraps where the rank path reuses one persistent solver with assumptions. **So the wl_i2 `chic→salt` UNSAT now rests on a validated encoding, not on its construction argument alone.** Artifacts: `bench/wl_stanford/eval/ad6_faithful_N16_flowpath_sandbox.json`, `..._N2_flowpath_sandbox.json`.
        - [ ] **Superseded — the validation reasoning, kept because it is the standard to hold new encodings to.** A brand-new encoding returning exactly the predicted answer deserves most scepticism, not least. Established: the flow constraint is complete by construction (any genuine simple walk carries the unit — the property an UNSAT claim rests on, and the one an over-constraint would break); it is tested on the rank encoding's own fixture; and the control's SAT structurally proves the flow graph contains the real `hous→kans→salt` path, i.e. that edge enumeration picks up the topology edges `wire_edges` adds after `ConvertToKripke` (had it missed them, *every* query would have been spuriously UNSAT). **Not** established: flow-vs-rank agreement on a large sample — currently one point. The stanford N=16 differential is 256 queries against a NetPlumber-proven answer including **91 genuinely unreachable pairs**, i.e. exactly the UNSAT direction needing validation. Requires adding `--flow-path` to `bench/ad6_faithful_measure.py` too.
        - [x] **METHOD CORRECTION 2026-09-11: `--skip-acyclic` is sound as a one-directional UNSAT test and practically near-vacuous for refutation.** The rank encoding is purely additive so UNSAT-on-the-relaxation *would* imply UNSAT outright — but floating cycles satisfy the relaxation, so it will essentially never *return* unsat. The evidence was already in `ad6/FAVE_CHANGES.md` §20, which records that the floating-cycle bug was discovered *because* ungrounded witnesses made unreachable pairs look reachable: I read the additivity correctly and missed the corollary. What the flag is actually good for — unanticipated, and now the recommended use — is a cheap **grounded-witness search**: SAT + zero-slack grounded walk soundly implies real reachability, SAT + ungrounded blob is strong evidence of unreachability, at 1/20th the wall and half the memory.
        - [x] **Measured: the rank/acyclic block is 83.8% of all variables (6,121,649 of 7,304,828) and 80.2% of all clauses (14,253,423 of 17,761,983).** Dropping it took the control from 425.8 s to 3.5 s (~120x). So the faithful i2 model is **not inherently intractable** — the cost is concentrated in the acyclicity encoding. That reframes the §5.5 tractability question and bears directly on `--lite-acyclic` being mandatory here (generality-debt item 1).
        - [x] **Bug in MY tooling, fixed by documentation 2026-09-10: a result file's verdicts live in `query_log`, not `queries`.** `queries` exists only in `--dry-run` output (the PLANNED pairs), so a progress monitor reading `d.get("queries", [])` on a real run gets an absent key → empty list → indistinguishable from "nothing has finished yet". This cost a real misreading: a control query that had completed in 425.8 s was reported as "still running" for five hours, and a 28x solver slowdown was inferred from the silence — then an explanatory hypothesis (VLAN-chain propagation, tagged vs untagged sources) was built on top of the non-fact. Same silent-empty failure mode `_forced_literals` exists to prevent on the literal side. Now stated in the module docstring, next to the recipe, along with `queries_done`/`last_query`/`last_query_s` as the cheap progress fields. **wl_stanford IS measured, and it corrects my own blast-radius claim:** the full N=16 faithful re-run gives `reachable_pairs` **165 of 256 — identical to the archived artifact**, so wl_stanford's archived faithful *reachability* is confirmed, not superseded (its encoding-size and timing numbers are: 5,463→5,967 nodes, 271,592→322,496 vars, 711,100→851,631 clauses, and query time 713.7→2,039.7 s = **2.9x**, sandbox/directional). **The "252/252 ports are narrower" figure overstates the behavioural blast radius and is the wrong one to quote** — what matters is how many crossings the *device union* wrongly admitted: wl_i2 **2,555 of 2,564 (99.6%)**, wl_stanford **7 of 183 (3.8%)**, because 176 of stanford's 183 per-port rejections were already rejected device-wide. Same defect, two orders of magnitude apart in effect — so the i2 verdict must be measured, and stanford's null result is not evidence either way. Writeup: [`AD6_PLAN.md`](AD6_PLAN.md) §5.5 "PER-(PORT, VLAN) ADMISSION LANDED".
        - [ ] **NEW ASYMMETRY this created: `fave/apkeep/adapter.py:_capture_in_admission` still has the identical projection.** Its `_in_vlans` feeds a different consumer (APKeep's own input format, `adapter.py:1257-1328`), so fixing it is a separate change with its own encoding semantics — not folded in here. Until it lands, an **ad6-vs-APKeep faithful-VLAN comparison on wl_stanford is no longer like-for-like**, which is exactly the comparability §5.4 Stage B ported the projected version to preserve. **Measured priority, though: LOW.** The gap this leaves on wl_stanford is 7 wrongly-admitted crossings and **0** reachability pairs (the ad6 re-run reproduces the archived 165/256 exactly), so the ad6-vs-APKeep comparison is unlike-for-like in principle and equal in outcome. Fix it for correctness, not because it invalidates the existing comparison.
      - [x] **SUPERSEDED by the entry above — kept for the diagnosis, whose "not the cause" verdict was itself wrong (see the ROOT CAUSE entry).** ~~TOP PRIORITY, correctness defect: make ad6's faithful admission a per-(port, vlan) relation.~~ It is a CROSS-PRODUCT OF TWO PROJECTIONS today, and 390 of 390 i2 admission rules are affected (100%).** i2's `in.X` rules are port-scoped — `routes.json`'s 6th positional field is `in_ports` — but ad6 keeps the dimensions separately, `ir["in_admit"]` (ports having any admission rule, `favemodel.py:497/512`) and `ir["in_vlans"]` (vlans the *device* admits, consumed at `favemodel.py:322`), and gates on their product instead of the real (port, vlan) relation. Every one of the 390 (device, vlan) pairs is scoped to a strict subset of its device's ports; worst cases are on `in.chic`, where a vlan admitted on **1 of 36** real ports is granted on all 36. **Not** the cause of the `chic→salt` divergence (that crossing is legal port-scoped) but a genuine structural over-approximation of exactly the kind that manufactures false reachability, and the strongest remaining candidate for the *other* pairs among NetPlumber's 11.
      - [ ] **ROOT-CAUSING PLAN (owner idea + agreed sequencing, 2026-09-10): use NP's `dump_flow_trees` leaves as a differential localizer, sharing one primitive with the witness check.** The technique is already proven here — `APKEEP_BACKEND.md`'s 2026-07-10 baseline validation root-caused wl_stanford's `bbra→rozb` false positive by exactly this route (868 of 869 branches die at `mid.bbra→out.bbra`; APKeep collapses the out stage and forwards past it), and its method note says the flow dump replaced "static rule inspection, which produced five successively-disproven mechanisms here". Its unresolved caveat is our question verbatim: **"do not assert a specific VLAN value until this is decoded"** — so treat NP's flow *structure* as oracle and NP's header *values* as untrusted. **Both ideas need one primitive:** given a solve, which FaVe-identified nodes did the flow traverse (ad6's counterpart to the `witnessPath` instrumentation added to APKeep's checker). Order: (a) the primitive; (b) near-free — intersect the EXISTING `chic→salt` witness path with NP's leaves, which localizes to one `(device, rule)` if the witness passes *through* an NP leaf; (c) one live NP i2 run with `simple=True` (~552 s, ~1 GB); (d) targeted per-node ad6 queries in one *warm* session (the 439x cold/warm effect makes batches cheap — `Query` already takes any node key, only `query_destination_key`'s probe assumption is in the way); (e) full trees only if VLAN values prove unavoidable, and then vector decoding is a prerequisite. **Step (c) is now REQUIRED, not optional** (2026-09-10): the model as ad6 loads it permits the witness path at every gate ad6 models, so the divergence lies in something NetPlumber enforces that ad6 does not represent — and only the flow dump says *where* NetPlumber's Chicago flow dies. The earlier "the shared tail may spare us the dump" reading is retired. **Care needed:** simple mode carries no header space; an NP leaf conflates "delivered" with "dropped" (split via `id_to_probe`, else the comparison is trivially true at every probe); the engines are asymmetric so this is a hypothesis *generator* plus targeted queries, not a symmetric set diff. **Detail to resolve first:** `check_flows.py:213` reads an aggregated `flow_trees.json` that nothing in this repo writes (the C++ writes per-source `<node_id>.flow_tree.json`), so leaf parsing is a small adapter, not reuse. Full analysis: [`AD6_PLAN.md`](AD6_PLAN.md) §5.5 "ROOT-CAUSING PLAN".
      - [ ] **Future option (owner idea 2026-09-10, deliberately deferred): decode NP's leaf header spaces and compare VALUES.** Extend the simple flow-tree dump with the header spaces reaching each leaf; NP's `mapping` gives bit→field semantics (already exposed via `_get_inverse_fave`), so ad6 variable names are derivable and values comparable. Three feasibility notes: the `mapping` supplies what the wl_stanford attempt lacked but does *not* by itself make the packed-48-bit-vector decode reliable; `hs_diff` is only awkward for set-vs-set *equality*, whereas testing whether one ad6 witness point lies inside an HSA space is plain membership; and the **don't-care asymmetry makes the comparison one-directional** — ad6's witness is a point, NP's leaf is a set, so "ad6's point is not in NP's space" is a sound divergence finding (and is the direction i2 runs) while the converse never follows from one witness. Escape hatch if a value claim is ever needed: a bit's don't-care status is decidable by asking ad6 whether both values are satisfiable under the same assumptions — 2 queries per bit, 24 for the 12-bit VLAN, cheap in one warm session. Owner's call: not part of the current witness check.
      - [ ] **Re-examine every per-pair timing claim in §5.5 — the archived `elapsed_s` values are position-dependent, not measurements of pair difficulty.** Found 2026-09-09 while establishing a like-for-like baseline: `hous→salt` is recorded at **1.11 s** (index 50 of 72 in a persistent incremental session) and takes **487.6 s** as the first query of its own run — a **439x** cold/warm factor for the identical pair, encoding and solver. That invalidates the rationale for choosing the three experiment pairs (all at indices 49–57) and puts the "per-pair hardness pattern is solver-specific" conclusion from the Kissat404 comparison in question. **Not affected:** the solver-to-solver comparison itself (same encoding *and* same query order, so the bias applies equally). **Unexplained nuance:** archived per-quarter means are 170.0/182.8/288.7/128.2 s — not monotonic — and the three pairs sit in the slowest quarter while being among the fastest queries. Learned-clause reuse is a hypothesis, untested. **PARTLY DISCHARGED 2026-09-12 by the flow 2x2 ([`AD6_PLAN.md`](AD6_PLAN.md) §7.5c):** `--flow-path` forces `--fresh-per-query`, so every query is bootstrapped into its OWN solver and every query is therefore a *cold* query — the warm/cold asymmetry that produced the 439x factor cannot arise by construction, and no learned clauses cross a query boundary. On that positionally-unbiased dataset the questioned conclusion HOLDS: cross-solver correlation is **-0.076** (plain, all SAT), and faithful's pooled **0.587** decomposes into SAT-only **0.206** / UNSAT-only **-0.128** once the newly-measured **6.6-7.4x SAT-vs-UNSAT** cost split is removed. So "per-pair hardness is a solver artifact" survives, now scoped: *within* a satisfiability class. **Careful about the evidence, though:** index-vs-time correlation is low in the flow runs (+0.03 to +0.18) but is ALSO low in the archived rank run (+0.010) that demonstrably carries the 439x effect — because that effect is a cold-START asymmetry, not a monotone trend, so a low index correlation is NOT evidence of its absence. The load-bearing argument here is architectural (no persistent solver), not correlational. **Still open:** the archived RANK per-pair timings remain position-contaminated and must not be quoted per-pair.
      - [ ] **The untag-ON run is still outstanding** (`--faithful-vlan --probe-untag --lite-acyclic`). Its value has CHANGED given the untag-off result: it was designed to measure the untag's own delta against a corroborating baseline, and there is no corroboration to measure against. It can now only show whether the untag *alone* flips either discriminator to unreachable — which, if it did, would mean the untag is the entire mechanism behind NetPlumber's 11 despite NetPlumber not enforcing it. Worth running, but the witness check above is the higher-value next step.
- [x] **DONE 2026-09-11 — the LPM fix now reaches wl_i2, and ad6 and NetPlumber AGREE EXACTLY on all 11 unreachable pairs.** `_reprioritise_fib_lpm` re-prioritises the DECLARED FIB tables (`config.json`'s `fib_table_types`); both datasets regenerated; NetPlumber re-run on the corrected wl_i2 dataset (build 588.1 s, peak 1,938.5 MB). **The fix moved exactly the three disputed pairs, onto ad6's answer:** `atla`/`newy32aoa`/`wash` → `salt` became reachable, → `kans` became unreachable, and the set difference against ad6 is now **empty in both directions**. So (a) the route-ordering gap was the whole of the remaining disagreement; (b) the three pairs ad6 alone reported were correct and NetPlumber's old `eastern→salt` was the artifact — vindicating the structural trace that predicted it; (c) the agreement is now *genuine corroboration* rather than two engines agreeing while one mis-forwards. **Independent in IMPLEMENTATION, though not in process (owner clarification 2026-09-12, [`AD6_PLAN.md`](AD6_PLAN.md) §5.5 "WHAT THE i2 ORACLE ACTUALLY IS"): there is no external ground truth here — the oracle IS this agreement, reached after multiple rounds of correction to both tools (more to ad6), and finally checked by manual inspection. The engines converge by genuinely different routes:** ad6 gets there by SAT over a port-scoped admission relation with a single-unit s-t flow grounding constraint, NetPlumber by HSA flow propagation, sharing nothing but the dataset — and ad6's IR is hash-identical across the reordering, so the ad6 side did not move at all. Artifacts: `bench/wl_i2/eval/np_i2_flow_leaves_lpmfixed_sandbox.json`, `ad6_i2_flowpath_full72_portscoped_sandbox.json`. Writeup: [`AD6_PLAN.md`](AD6_PLAN.md) §5.5.
  - [x] **ANSWERED 2026-09-11 — `eastern→seat` is the SAME Chicago crossing; all 11 pairs now have ONE cause.** Settled with a third witness, `bench/i2_structural_oracle.py`, which computes the matrix straight from the shipped JSON (no ad6, no NetPlumber) and **reproduces the 11 pairs exactly** — the agreement is now three-way. It is **exhaustive over IPv4**, enumerating the 9,673 exact LPM equivalence classes (atoms) induced by the 10,020 distinct prefixes, and it confirms wl_i2 has **no ECMP at all** (fanout histogram `{1: 77451}`). **Probe semantics, previously unstated and decisive:** `probe.X` is tapped on *every* egress port of `out.X` and fires iff `vlan == 0`, the tap being parallel to any topology link — so “reach `probe.d`” means “egress `d` untagged”. **Why seat is hard: `|A_seat| = 5`** — of 9,673 atoms exactly five are delivered untagged at seat from outside (`64.57.19.16/.18/.20/.22`, `64.57.27.33`, all i2 backbone space), against `|A_salt| = 6,503` and `|A_hous| = 7,269`; almost everything is delivered untagged at an earlier device, so the backbone leaf keeps nearly nothing. **All five die at `BLOCKED@in.kans.400029(vlan=10; admits={11,20,21,30,31,32,40,60,70})` — 100%, from `atla`, `newy32aoa`, `wash` and `chic` alike**, i.e. exactly the crossing that already explained `chic`'s five and the trio's `→kans`. **Why `→salt` escaped:** one atom, `64.57.27.129`, takes a southern bypass `atla→hous→losa→salt` wholly on vlan 0, because `out.atla` splits a single prefix — `64.57.27.0/24` to Chicago, the more specific `64.57.27.128/27` south to Houston. None of seat's five falls in that `/27`; **that lone carve-out is the whole difference between the two verdicts.** **Root fault, re-verified against raw `routes.json`/`topology.json`:** Chicago has three links to Kansas — `220046→400019` and `220047→400022` both admit `{10,20,30}` and carry **0 routes**, while `220045→400029` admits `{11,20,21,30,31,32,40,60,70}` (no 10) and carries **2,547 routes, 2,545 of them tagged vlan 10**. One misconfigured link explains all 11 pairs. Writeup: [`AD6_PLAN.md`](AD6_PLAN.md) §5.5 “ANSWERED — eastern→seat IS THE SAME CHICAGO CROSSING”. Artifacts: `bench/i2_structural_oracle.py` (`--explain SRC DST`), `bench/wl_i2/eval/i2_structural_oracle_atoms.json`.
  - [x] **Superseded framing — the diagnosis.** ~~TOP PRIORITY — the FaVe-backend LPM fix never reached wl_i2, so every FaVe+NetPlumber wl_i2 number (including the 11 unreachable pairs) was computed on a NON-LPM forwarding model.** `bench/np_preparation.py:_reprioritise_mid_lpm` repairs the FaVe fork's `--load` priority bug (commit `f1768c50`, `APKEEP_STANFORD_NP_SPEC.md` Phase 1d — the bug that collapsed wl_stanford's NP count from ~165 to 10) by reassigning rule indices by descending prefix length — but **only for devices named `mid.*`**. **wl_i2 has zero `mid.*` rules**; its stages are `['in','out']` and its FIB is the `out.*` stage, so the fix is a structural no-op there. The earlier gate recorded this as benign — *"0a (wl_ifi/wl_i2 — no overlapping prefixes, reversal is a no-op) stays green"* — and **that premise is false for wl_i2**: measured, `routes.json` (which `np_preparation.py` itself writes, line 421, and NetPlumber ingests) leaves **3,731 rules shadowed by an earlier containing prefix**, 277–589 per out-table. Concrete proof on the decisive link: destination `140.112.0.0` → NetPlumber first-match picks `140.112.0.0/12` out `out.chic.220040` with `rw=vlan:281`, ad6's LPM picks `140.112.0.0/14` out `out.chic.220045` with `rw=vlan:10` — different egress port *and* VLAN, and `220045` is exactly the link into `in.kans.400029` that rejects vlan 10. A real router does LPM, so **ad6 is right**. **Consequence: the ad6-vs-NetPlumber agreement on the five Chicago pairs is much weaker evidence than it appeared** — two engines agreeing while one mis-forwards is not independent corroboration. **Fix, re-measure, then re-read every §5.5 conclusion resting on NetPlumber's i2 output.** The fix is small and already proven here: widen the `mid.`-prefix test to any FIB-bearing stage (or drop the device-name test — re-prioritising a table with no overlapping prefixes is a no-op by construction), with wl_stanford's 165 as the regression gate.
  - **Owner correction 2026-09-11 on a different NetPlumber point, recorded so it is not repeated:** the commented-out probe flow analysis is **not** a defect and does not weaken NetPlumber's verdicts. It is an artifact of a deliberate mode change — NetPlumber originally verified compliance by *backward* flow plus path-pattern matching (an incoming flow could be filtered and its path analysed); the mode was later changed to full flow-tree analysis, and the then-unused probe-side filtering was deactivated because some flows proved prohibitively costly at probe nodes. Accepting any flow at a probe is also the right semantics: **probes are not part of the network model**, so no meaningful flow handling (VLAN rewriting on an egress port, say) should happen there. "NetPlumber does not enforce the untag" stays true as a *workload-parity* fact and remains the reason `probe_untag` defaults off.
  - **Full 72-pair sweep done 2026-09-11 (flow-path, port-scoped) — ad6 finds EXACTLY 11 unreachable pairs, NetPlumber finds EXACTLY 11, they agree on 8, and the difference is a clean 3-for-3 SWAP.** 81 queries in 4,201.4 s on a 9,183.0 MB peak; mean 42.1 s/query, refutations 6.1x the satisfiable queries (152.3 s vs 24.8 s); `reachable_pairs` 61 of 72, `oracle_full_set: true`. **Both unreachable (8):** `chic`→{hous,kans,losa,salt,seat} and `atla`/`newy32aoa`/`wash`→seat. **NetPlumber only (3):** the eastern trio→**salt**. **ad6 only (3):** the eastern trio→**kans**. Same three sources, same three flows blocked, at a *different router* — the signature of a route-selection difference rather than one engine over- or under-approximating, and exactly what the LPM scoping gap predicts (destination `140.112.0.0` leaves Chicago on `220040`/vlan 281 under index order and `220045`/vlan 10 under LPM). **Consequence for the long-open "six unexplained eastern pairs": `→seat` is real and agreed by both engines; `→salt` is one side of the swap and must be re-read only after the LPM fix lands and NetPlumber's i2 baseline is re-measured.** Artifact: `bench/wl_i2/eval/ad6_i2_flowpath_full72_portscoped_sandbox.json`.
  - **[superseded framing] Route-ordering parity gap between ad6 and FaVe+NetPlumber on wl_i2** — the route to the finding above. The full 72-pair flow-path sweep found `atla`/`newy32aoa`/`wash` → `kans` **UNSAT in ad6 and NOT among NetPlumber's 11** — ad6 stricter, the opposite direction from everything §5.5 chased before. Structural investigation (IR + raw `routes.json`, no solve) established that **ad6's IR is faithful and its UNSATs are correct for the model**: all three share one cause, the already-known `out.chic.220045 → in.kans.400029` crossing (writes vlan 10, arrival port admits `{11,20,21,30,31,32,40,60,70}`), because the eastern region's only gateway to Kansas is Chicago. Verified against raw `routes.json`; and note `out.chic.220046/220047` are physical links to arrival ports that *do* admit vlan 10 but carry **zero** routes. **The engines order the same FIB differently:** `Ad6Adapter._lpm_prio` recomputes priority as `65534 − prefix_length`, while `netplumber/adapter.py` passes `_calc_rule_index(rule.idx, …)` — the index from `routes.json`. **`routes.json`'s order violates LPM for 3,731 rules** (277–589 per out-table; e.g. `140.112.0.0/12` before `140.112.0.0/14`), so the two engines select different routes for those destinations. A real router does LPM, so ad6's semantics are the correct ones. Leading hypothesis, not established — NetPlumber's C++ matching was not traced. Writeup: [`AD6_PLAN.md`](AD6_PLAN.md) §5.5.
  - **Refuted along the way:** that the out-stage rewrite is per-in-port the way the in-stage admission was. 0 `(table, dst)` pairs have >1 rewrite VLAN and 0 appear with different `in_ports`, across all 77,451 out rules.
  - **Method note, recorded because the first version of the check was wrong:** an adjacent-pairs-only scan found *zero* overlapping inversions and would have killed this hypothesis. Shadowing is not an adjacency property — the containing rule can sit anywhere earlier in the table. The correct scan (walk file order, probe every supernet of each new prefix against those already seen) finds 3,731.
- [ ] **Latent bug, found while building the above; reported not fixed.** In faithful mode any multi-port (ECMP) route raises `KeyError: '<rule>_fanout'` — `wire_fanout` creates that node with transitions only and no `KripkeNode`, while `Instantiator._CreateMutationConstraints` calls `Kripke.GetNode` on every node with outgoing transitions. Reproduced in a synthetic 3-device IR. Measured as unreachable today rather than assumed: faithful wl_stanford's IR has `max_ports == 1` at N=2 and N=16, i2's out rules carry one `fd=` each, and plain mode builds no mutation constraints. It bites the moment a faithful workload has a genuine ECMP route.
- [ ] **Then, regardless of that outcome: extend `test_backend_differential` to wl_i2.** It is currently `_PREFIX = "bench/wl_ifi"` only, which is how a three-backend "agreement" stood with one backend never compared.
- **Do NOT close this by trusting the majority.** Two backends agreeing while both relax the same dimension is not independent confirmation; it is the same simplification counted twice.

#### Then the gate itself
- [ ] **Make `bench` fail on a wrong verdict.** Compare the verdict (better: the structured compliance events, not the rendered `report.md`) against an expectation and exit non-zero on mismatch — the `backend_gate.py` "a skip is NOT a pass" principle applied to verdicts. Wire into `test.sh run_bench` so CI cannot pass the tier vacuously.
- **The expectation has to be BUILT first; `reachable.json` will not do.** As above it is the policy, is tautologically equal to `checks.json`, and being all-reachable it cannot catch over-approximation — gating on it would certify a relaxed backend as correct. What is needed is a set containing **expected-UNREACHABLE pairs**, from one of: (a) a faithful hand-derived expectation for a small induced sub-topology — the approach `subset_check.py` describes for wl_stanford (`APKEEP_BACKEND.md:586`), though note that file is **not in the tree**, so it would have to be written; (b) cross-backend *agreement* as the invariant, with all backends in their FAITHFUL modes (agreement between relaxed modes is worthless — see the 11-pair finding); or (c) the policy plus a separately-verified data-plane reachability result, which for wl_i2 does not currently exist.
- **Do not gate on either current output.** Pinning the bench path's 35 or the in-process 11 would freeze an unexplained answer into the suite. Root-cause first, then gate.

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

### 1v. Environment gaps rediscovered every container reset — DONE 2026-09-09
- **Finding:** the `Dockerfile` installs every system dependency this project needs, but
  a sandbox *not built from it* (a yolobox starts from its own base image) has none of
  them — while a venv in a persistent `$HOME` survives a restart with all pip deps
  intact. That asymmetry is what made the gap so costly: the Python half of the
  environment looks healthy, so every symptom reads as a code regression. Three cost
  real time this session alone, and two of them had already been diagnosed once before
  (`ad6/FAVE_CHANGES.md` §24's environment note, `AD6_ENCODING_PLAN.md` §3.10's
  `liblog4cxx` note) without the knowledge becoming reusable:
  - `python3-dev` absent → pybison compiles its generated parser at **runtime**, that
    compile fails on a missing `Python.h`, and pybison then **segfaults** with no
    traceback, taking the whole pytest process down (`test_ad6_wl_up.py` dumps core).
  - `liblog4cxx15` absent → `libnetplumber` fails to **load**, and the harness reports
    "libnetplumber is not built; run `build_libnetplumber.sh`" although the `.so` is
    present and correct. Points at the wrong fix; live-NetPlumber tests silently skip.
  - `minisat`/`clasp` absent → `ad6 make test` shows four red suites with
    `FileNotFoundError`. (`which minisat` printing nothing reads as success — check the
    exit status.)
  - Plus: `apt-get update` must run **first**, or install fails with "Unable to locate
    package minisat", which reads like the package no longer exists.
- [x] **`./test.sh doctor`** — a tier that runs no tests. It **parses the `Dockerfile`**
  for the expected apt set (rather than duplicating the list, so the two cannot drift),
  checks each package, every Python import, the native artifacts (`net_plumber` binary,
  `libnetplumber` loadable) and the runtime limits, labels each finding with the tier it
  blocks, and prints the exact repair command with `apt-get update` included. Import
  probes run in their own interpreter so a pybison segfault cannot take the doctor down
  with it. A Dockerfile package missing from the purpose table is reported as
  `UNCLASSIFIED` rather than ignored, so the table cannot quietly fall behind.
- [x] **`.yolobox.toml`** now declares the full package set in `[customize] packages`,
  cross-checked against the Dockerfile, so a fresh sandbox starts complete.
- [x] **README** — a "Checking the environment first" section with the three
  misleading-symptom cases in a table.
- **Effect, measured:** the `integration` tier went from *entirely unavailable* (pybison
  segfault killed the process) to **51 passed / 2 skipped + 8 NDD tests**, and
  `test_ad6_wl_up.py` from a core dump to 3 passed — with no code change, only container
  repair. The doctor now reports "environment complete for every tier".

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
- [x] **`policy_translator/` fully typed** (all 8 modules: `policy_exceptions`, `policy_logger`, `fpl_grammar`, `policy`, `policy_builder`, `policy_translator`, the two `visualize_*`). It is an **independent tool** (no cross-imports with fave, verified) so it is type-checked independently: its own `policy_translator/mypy.ini` + source root, mirroring how its tests run with a separate `PYTHONPATH`. `typecheck_test.sh` runs both tools' mypy passes (own config/root each) and fails if either fails — avoiding a shared-`mypy_path` module-name-collision risk. The gate covers **43 modules** total (35 fave + 8 PolicyTranslator). `policy_logger` got its own `TraceLogger` shim (for `PT_LOGGER.trace`). Two more py2→3 bugs found by typing: the report CSV opened `'rb'` then handed to `csv.reader` (py3 needs text) → `'r'`; and (in `policy_builder.match`) a sentinel var retyped bool→`re.Match`. Its 46 tests are in the fast tier, so this is test-covered, not just mypy-verified.
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

### 7. C++ hardening for NetPlumber — PLAN (see [`TESTING_STRATEGY_CXX.md`](TESTING_STRATEGY_CXX.md))
**Scope: `net_plumber/` C++ backend, the *canonical* build only** — `NetPlumber<hs, array_t>` with the default `USER_FLAGS` (`-DWITH_EXTRA_NEW -DCHECK_ANOMALIES -DSTRICT_RW`). Per the author, that is the supported feature set evaluated in the PhD thesis; the `GENERIC_PS`/`PacketSet`, `USE_BDD`, `NEW_HS`, `PIPE_SLICING`, `CHECK_*_SHADOW`, `DENSE_LOOPS`, `SORTED_*`, `USE_DEPRECATED`, and `USE_GROUPS` paths are abandoned/experimental/legacy and **out of scope**. The full analysis, principles, oracle design, and prioritized roadmap live in `TESTING_STRATEGY_CXX.md`; this item is the actionable checklist. Builds on items 1h/1i.

- **State:** `array_unit.cc` (1129) + `hs_unit.cc` (2009) test the `array_t`/`hs` C API (the real verification data structure) on hand-picked cases; CppUnit harness via `net_plumber --test`, 94 green. But the orchestrator API has ~3 of ~30 public methods tested, the algebra has **no law/oracle coverage** (wrong-but-self-consistent refactors pass), the plumbing tests are internals-coupled + interdependent (`test_probe_transition_* → test_routing_*` chains), and two confirmed bugs sit in untested paths.
- **Guiding principles:** (1) harden the one canonical build, no test matrix; (2) pin *semantics* with a concrete-packet oracle (enumerate all `2ⁿ` packets for small headers, compare against symbolic `hs`/`array_t`), not snapshots; (3) test contracts via the public API, not internal state; (4) property/algebraic-law testing for the algebra; (5) characterize→fix→flip for confirmed bugs.

- [x] **P0 — header-space algebra: oracle + laws (highest leverage). DONE (2026-06-25).** Added an independent concrete-packet oracle (`src/headerspace/test/oracle_util.h`) that decodes `array_t`/`hs` into characteristic vectors over all `2^(8·len)` packets using only the documented 2-bit layout — never the algebra under test — plus an `OracleTest` suite (`oracle_unit.{h,cc}`, registered in `main.cc`) covering `isect`/`cmpl`/`rewrite` identities, the predicate laws, and `hs` `isect`/`minus`/`cmpl`/`add`/`compact`-invariance/De Morgan/`minus≡isect∘cmpl` for `len ∈ {1,2}`. `net_plumber --test` → **OK (110)**. The oracle immediately found two engine soundness/robustness bugs (#C4, #C5 below), now fixed with deterministic regressions. (Decoder validated against `array_is_sub_eq` + the `2^(#x)` cardinality law.)
- [x] **P1 — orchestrator API contracts + the two bugs. DONE (2026-06-25)** (one item deferred). Added to `NetPlumberBasicTest`: `test_remove_link` (topology symmetry, catches #C1), `test_check_compliance_unknown_dst` (#C2), `test_event_api` (`get`/`set_last_event` round-trip + each mutator records its event), `test_rule_id_determinism_and_replacement` (id = `(table<<32)|index`; re-add at an index replaces in place, same id), `test_query_and_error_paths` (unknown port → NULL; add_rule to a missing table → 0; removing absent rule/source is a safe no-op), `test_source_lifecycle` (add→ADD_SOURCE, remove→REMOVE_SOURCE, double-remove safe). `net_plumber --test` → **OK (114)**.
  - [x] **De-chained `test_probe_transition_* → test_routing_*` — DONE (2026-06-25).** Extracted assertion-free builders `setup_routing_{add_source,add_fwd_rule_higher_priority,add_link,remove_link}` (a parallel chain to the `test_routing_*` methods, which now read `setup_* + assert`), and pointed all six probe-transition preconditions at them. The probe-transition tests no longer invoke routing assertions, so a routing-test regression no longer cascades into every probe-transition test. Behavior-preserving (identical build order): `net_plumber --test` → **OK (118)**.
- [x] **P2 — conditions (pure logic) + RPC parser boundary. DONE (2026-06-25)** (depth guard deferred). Added to `ConditionsTest`: `test_boolean_conditions` (And/Or/Not truth tables + De Morgan), `test_cond_json_roundtrip` (`to_json`↔`val_to_cond` serialise→reparse→serialise stability), `test_cond_parse_malformed` (null/unknown/missing/non-string `type` → nullptr; a path with a malformed pathlet still parses). The malformed test exposed and fixed a parser crash (#C6). (`HeaderCondition` empty-intersection→false was already covered by `test_header`.) `net_plumber --test` → **OK (117)**.
  - [x] **Recursion depth guard — DONE (2026-06-25).** `val_to_cond` now takes a defaulted `depth` and rejects (`nullptr`) `and`/`or`/`not` nesting beyond `MAX_CONDITION_DEPTH` (256), and a null/too-deep operand propagates to `nullptr` instead of building a node with a null child (which would crash in `check()`). (`val_to_path` is iterative — bounded by the pathlet-array length — so it needs no guard.) `test_cond_parse_malformed` now also asserts a 5000-deep chain returns `nullptr` without overflow.
  - [x] **`check_compliance` RPC-parser hardening — DONE (2026-06-25, #C7).** Extracted the parsing into a validated free function `val_to_compliance_rules` (+ `free_compliance_rules`) so it is unit-testable, and rewrote the handler to use it. Now rejects malformed input (non-object, non-numeric key, short/ill-typed tuple) with an RPC error instead of throwing (`std::stoull`) or asserting (`asUInt64`/`asCString` on the wrong type) out of the handler; also **fixes a pre-existing leak** (the handler never freed the `cond` arrays). Pinned by `test_compliance_rules_parse`. `net_plumber --test` → **OK (118)**.
- [x] **Sanitizer CI job — DONE (2026-06-25).** New `sanitizers` job in `.github/workflows/ci.yml`: rebuilds NetPlumber with `-fsanitize=address,undefined -fno-sanitize-recover=all` (injected via `DEBUG_FLAGS`, which `GCFLAGS` applies at compile **and** link) and runs `net_plumber --test` under ASan+UBSan+LeakSanitizer. The suite is **clean under all three** (validated locally, `OK (118)`). Bringing it up surfaced and fixed three benign pre-existing UBs (#C8). Deterministic like `integration`, so gating; needs confirmation on a real CI run.
  - [x] **`gcov`/`lcov` C++ coverage — DONE (2026-06-25).** New report-only `coverage-cxx` job in `ci.yml`: rebuilds with `--coverage -O0 -g` (via `DEBUG_FLAGS`), runs `net_plumber --test`, then `lcov` captures + filters (excludes vendored `jsoncpp`, system headers, and `test/`) and `genhtml` produces an HTML report uploaded as the `cxx-coverage-html` artifact. Like the Python coverage it is **not gated** on a percentage. (The makefile's own `coverage` target is bypassed — its `COV_FLAGS` never reach `GCFLAGS` because the `sources.mk` line is commented.) Validated locally with lcov 2.0: engine line coverage **~54%** (`array.c`/`hs.c` ~12-14%, `rpc_handler.cc` ~43%, `conditions.cc` ~35%). Needs `--ignore-errors mismatch,gcov,source,unused` for lcov 2.0's strictness.
- **Finding:** NetPlumber is the soundness-critical core; no sanitizers/coverage in CI, and the public API + algebra semantics are under-pinned for safe refactoring.

#### Confirmed bugs found during analysis (→ characterize→fix→flip; full context in `TESTING_STRATEGY_CXX.md`) — FIXED (commit `a74b6b31`, 2026-06-25)
All three fixed in one commit with public-API regression tests in `NetPlumberBasicTest` (`test_remove_link`, `test_check_compliance_unknown_dst`). Both new tests **fail pre-fix** (assertion / SIGSEGV resp.) and pass after; `net_plumber --test` → **OK (96)**, up from 94. Verified pre-fix-red via a stash-revert-rebuild cycle.
- [x] **#C1 `net_plumber.cc:915-920` (`remove_link`)** — second loop iterated `inv_topology[to_port]` but `erase`d from `topology[from_port]` with a foreign iterator (**UB**) and compared against `to_port` instead of `from_port`; inverse topology never cleaned. Fixed: erase from `v_inv`, compare `from_port`.
- [x] **#C2 `net_plumber.cc:2255` (`check_compliance`)** — `id_to_node[dst]->source_flow` via `std::map::operator[]` inserted+dereferenced a `nullptr` for an unknown `dst` → null-deref crash. Fixed: look up with `find()`; an absent dst has no incoming flows (`any` stays false — correct compliance semantics).
- [x] **#C3 (smell) `net_plumber.cc:2264`** — added parens: `(!valid && any) || (valid && !any)` (no behavior change).

#### Engine bugs found by the P0 oracle (→ fixed; **soundness-critical core — warrant author review**, 2026-06-25)
Both surfaced by `OracleTest` against the concrete-packet oracle, fixed in `src/headerspace/hs.c`, and pinned by deterministic regressions (`test_hs_cmpl_universe_regression`, `test_hs_add_hs_diff_source_regression`) plus the randomized law tests. Both fail pre-fix (236-vs-0 / SIGSEGV); `OK (110)` after.
- [x] **#C4 `hs.c hs_cmpl` (non-NEW_HS)** — when a positive element is the universe (`array_cmpl_a`→NULL) with no diff, the loop did `continue`, but `~(⋃cᵢ)=⋂~cᵢ` is an intersection so an empty factor must zero the whole result. `~(c1 + xxxxxxxx + c3)` came out as `~c1 ∩ ~c3` (e.g. 236 packets) instead of ∅. **Reachable on compacted hs** (`hs_compact` does not drop the redundant universe cube), and it propagates into `hs_minus` (= `isect∘cmpl`). Fixed: empty the result and stop. **Soundness impact on the verification path — please review.**
- [x] **#C5 `hs.c hs_add_hs` (non-NEW_HS)** — a source hs carrying diff lists was mishandled: diff cubes were appended via `vec_append(...,true)`, which grows `elems` but not the parallel `diff` array, desynchronising them → out-of-bounds access / **crash**. Fixed: append each source element with its own diff cubes into the new element's diff slot (the parser's pattern).

#### RPC robustness bug found by the P2 parser tests (→ fixed, 2026-06-25)
- [x] **#C6 `rpc_handler.cc` `val_to_cond`/`val_to_path`** — a condition/pathlet object lacking a string `"type"` reached `val["type"].asCString()`, whose `JSON_ASSERT(type_==stringValue)` is a live `assert()` (no `-DNDEBUG`) → **`abort()` (SIGABRT) on malformed RPC input** (DoS). Fixed: guard with `isObject()`/`isMember`/`isString` and degrade to `nullptr` (the existing contract for unknown types); unrecognised pathlets are skipped. Pinned by `test_cond_parse_malformed` (aborts pre-fix, OK after).

#### RPC robustness bug found by the P2 parser tests (→ fixed, 2026-06-25), cont.
- [x] **#C7 `rpc_handler.cc check_compliance`** — the handler called `std::stoull` on the policy key (throws on a non-numeric key) and indexed `dsts[i][0..2]` with `asUInt64`/`asBool`/`asCString` (assert/abort on a short or ill-typed tuple), either of which **crashed the server on malformed RPC input**; it also **leaked** every parsed `cond` array (`check_compliance` only reads them). Fixed by extracting a validated, two-pass `val_to_compliance_rules` (rejects malformed input → RPC error, no partial state) + `free_compliance_rules` (called after the check). Pinned by `test_compliance_rules_parse`.

#### UB found by the sanitizer CI job (→ fixed, 2026-06-25)
- [x] **#C8 `net_plumber_utils.cc`** — `make_sorted_list`/`make_sorted_list_from_array` called `qsort(NULL, 0, …)` and `intersect_sorted_lists` called `memcpy(NULL, …, 0)` when a list was empty: passing NULL to a `nonnull`-declared argument is UB (no-op in practice, but flagged by UBSan). Guarded all three on `size > 0`. Surfaced while bringing up the `sanitizers` job; the suite is now clean under ASan+UBSan+LSan.

#### Future considerations (NOT testing — for the author's decision)
- [ ] **Shrink the `#ifdef` surface.** ~74 `#ifdef` sites in `net_plumber.cc` alone come from abandoned/experimental/legacy flags that are never built but every refactor must reason about. Deleting the genuinely-dead ones (`NEW_HS` dead-end, `GENERIC_PS`/`USE_BDD` abandoned PacketSet experiment, `USE_DEPRECATED` legacy) would collapse the surface and make refactoring markedly safer; keep whatever is wanted for thesis reproducibility. Code-removal decision, independent of the tests above.
- **PacketSet/BDD stays parked.** Reviving the `PacketSet` abstraction is gated on first solving the BDD masked-rewrite problem (non-trivial; also caused a perf regression vs. pure header-spaces); both **low priority**. If revived, the P0 concrete-packet oracle is directly reusable as the BDD backend's validation harness.

### 8. Differential / oracle testing across detectors
- [ ] **Cross-check FaVe verdicts against Z3/STL oracles**
- **Finding:** Three independent anomaly detectors (`ad6`, `z3-anomalies`, `stl-anomalies`) plus the `np_reproduction` HSA baseline exist.
- **Fix:** Cross-check FaVe's verdicts against Z3/STL on the same rulesets as a property-based oracle. Disagreements are bugs or interesting findings. Highest-value correctness lever specific to FaVe.
- **Note:** `ad6` also has a *second, distinct* role as a full **reachability backend** (generic SAT/QBF model checking) — see item 11 and [`AD6_PLAN.md`](AD6_PLAN.md). Here it is used only as an anomaly-detection cross-oracle; there it answers source→probe reachability across a topology.

### 10. Alternative verification backend: APKeep — PLAN (see [`APKEEP_BACKEND.md`](APKEEP_BACKEND.md))
**Scope: a *second* FaVe verification backend (atomic-predicate engine, Zhang et al. NSDI'20) behind the existing `AbstractVerificationEngine` seam, plus a from-zero performance comparison vs NetPlumber.** Thesis future-work, not QA — but its correctness gate (differential vs NetPlumber) is item 8's oracle idea applied between the two backends, hence its placement here. First milestone is IPv4 (`wl_stanford`/`wl_i2`) only — IPv6 firewalls are out of scope for APKeep as-built. Full motivation, capability analysis, architecture decisions, and roadmap live in `APKEEP_BACKEND.md`; this item is the actionable checklist.

- **Findings (scoping, 2026-06-25):** (1) An official public APKeep impl exists (MIT, Java; <https://github.com/XJTU-NetVerify/apkeep>) — reuse it, do not reimplement. (2) The seam is the Python `AbstractVerificationEngine` (`fave/aggregator/abstract_engine.py:5-62`); a new backend is a subclass selected by a flag, instantiated at `aggregator_service.py:86-91`. (3) APKeep's field set is hardcoded (IPv4 5-tuple + MPLS + inner-IP + IPv6-dst-only) — narrower than FaVe's runtime-extensible mapping. (4) APKeep exposes only loop detection, but its Port Predicate Map (`Element.port_aps_raw`, `forwardAPs`, `getHoldPorts`, `traversePPM`) supports a reachability solver. (5) **Audited `wl_stanford`/`wl_i2`: the entire workload is existential port-to-port reachability** — all probes `existential`/`match=null`/`test_path=null`/condition-true; sources full-space; checks all-pairs `EF`; no slices, no waypoints, no conditions. So the hard parts (paths/universal/conditions/slices/flow-dumps) are not exercised. (6) APKeep ships **zero tests** → build our own gate.
- **Decisions (with user):** persist the plan as `APKEEP_BACKEND.md` + this item; vendor upstream via **fork + git-subtree** in-tree at top-level `apkeep/`; drive both backends in-process via **`libnetplumber`** (pybind11) and **`libapkeep`** (JPype) for a symmetric from-zero comparison; handle the JVM warm-up confound by reporting steady-state (resident JVM, discard warm-up) + a labeled cold number.

- [x] **P0 — Vendoring & build — DONE (2026-06-26).** Subtree at `apkeep/` (user); `mvn package` builds (JDK 11 + Maven); bundled-Stanford smoke + golden loop pin (`fave/test/apkeep_smoke.sh` + `apkeep_stanford_loops.golden`, 20 loops, deterministic) wired into the `integration` tier; README provenance + JDD license check (zlib/public-domain); JDK 11 + Maven added to the CI composite + Dockerfile (needs a real CI run to confirm). Commits `b89b2701` (apkeep/-only) + `30ce338d` (FaVe-side).
  - **Build obstacle + fix (fork-local, in `apkeep/`):** upstream `mvn package` could not resolve its `JDD` dependency at all — `org.bitbucket.vahidi:JDD:108` is a tag that was never published (JDD's tags start at 109), JDD is not on Maven Central, and JitPack serves only JDD's `.pom`, never a `.jar`. Fixed by vendoring a JDD jar (built from the author's Bitbucket source at tag 111, zlib/public-domain) in an in-tree file repo (`apkeep/local-maven-repo/`) and pinning `maven-compiler-plugin` 3.11.0 with `release=11` (the super-POM's 3.1 defaults to Java 1.5). All confined to `apkeep/` so the subtree stays splittable.
- [ ] **P1 — `libnetplumber`.** Map NetPlumber's C++ core API to the `AbstractVerificationEngine` methods; pybind11 binding; a lib-backed adapter selectable by flag; equivalence-tested against the JSON-RPC adapter. *(Low-risk, standalone FaVe win — do first; de-risks the in-process premise.)*
  - [x] **Binding built + smoke-verified (2026-06-26, commit `cd68e0b7`).** `net_plumber/python/libnetplumber.cpp` (pybind11 `LibNetPlumber` over `NetPlumber<hs,array_t>`) + `build_libnetplumber.sh`. Mirrors `rpc_handler.cc`: rule hot path native, source `hs`/probe conditions via copied `val_to_*` on the same JSON. Links against the core `.o` (needs a `-fPIC` build, done via the `DEBUG_FLAGS` hook) + log4cxx; ABI flags `-DWITH_EXTRA_NEW -DCHECK_ANOMALIES -DSTRICT_RW -DJSON_IS_AMALGAMATION -std=c++17`. ABI risk retired. New build deps: `python3-dev`, `pybind11-dev`, `liblog4cxx-dev`.
  - [x] **In-process results channel — option (b) (2026-06-26, commit `208d4f49`).** A collecting `compliance_callback` (replacing `default_compliance_callback`) buffers `(src, dst, valid, cond)` violations -- the same records the `Reporter` parses from `DefaultComplianceLogger` lines -- exposed via `get_compliance_results()`/`clear_results()`. No log round-trip; generalizes to APKeep (JPype-returned verdicts). *(check_anomalies results collection still TODO -- benchmarks need compliance, not anomalies.)*
  - [x] **`NetPlumberLibAdapter(AbstractVerificationEngine)` + transport seam — DONE (2026-06-26, commit `7d36789e`).** Introduced `self._rpc` in `NetPlumberAdapter` (the `jsonrpc` module by default; behaviour-preserving — 29 call sites routed). `netplumber/lib_transport.py` = jsonrpc-compatible facade over `LibNetPlumber`; `netplumber/lib_adapter.py` = `NetPlumberLibAdapter` reusing ALL prep, swapping transport, reading results in-process via `get_compliance_results()`. End-to-end smoke green (flow source→rule→rule→probe, correct compliance verdicts).
  - [x] **Full test suite validated (2026-06-26).** fast **270 passed** (transport seam = no regression), integration green (NetPlumber `OK (118)` + bison 15 + APKeep golden pin), e2e green (test_rpc + smoke), **bench green (wl_up/wl_tum/wl_stanford/wl_i2 all PASS)**. Sandbox provisioning needed (not code): `flex`/`bison` (a missing-pybison **segfault** broke fast via `test_aggregator.py`), `net_plumber` on PATH, venv-on-PATH for e2e/bench subprocesses, and a **`/dev/shm` workaround** (see findings below).
  - [x] **Equivalence test vs the JSON-RPC path — DONE (2026-06-26, commit `b32d0511`).** `fave/test/test_lib_equivalence.py`: one build sequence drives both backends (jsonrpc over live net_plumber; LibTransport over in-process LibNetPlumber) and asserts identical node ids, **byte-identical** `dump_plumbing_network`+`dump_flows` (order-canonicalised), and identical compliance verdicts (RPC parsed from the np log via `reporter._parse_log_line`; lib read in-process via `get_compliance_results`). Wired into the e2e tier (skips if `.so` unbuilt); e2e green (5 passed).

#### Runtime-robustness findings (surfaced validating e2e/bench, 2026-06-26)
Real fragilities (match the author's "past deadlocks" experience); the lib backends' from-zero/in-process/no-Reporter design avoids both:
- [ ] **Aggregator deadlocks on backend death.** When `net_plumber` dies mid-run, the aggregator blocks forever in `poll()` (confirmed via `/proc/<pid>/wchan`) instead of erroring. Here net_plumber was killed by log4cxx `ENOSPC` when its verbose `DEBUG`/`DefaultProbeLogger` output filled the 63 MB `/dev/shm` tmpfs. Add peer-disconnect detection / an RPC timeout. (Also: `net_plumber` logs at `DEBUG` by default — `Log4cxxConfig.conf rootLogger=DEBUG`; the probe-activation spam is the bulk and is pure noise for the verdict.)
  - **CONFIRMED 2026-09-09 (with one correction), while measuring item 1r.** Reproduced verbatim: wl_i2's `net_plumber` died with `terminate called after throwing an instance of 'log4cxx::helpers::IOException' / what(): IO Exception : status code = 28(No space left on device)` after filling the 63 MB `/dev/shm` — ~2.5 min into a run that `benchmark.py` had *already exited rc=0* from, so nothing noticed. An orphaned backend from a separate failed run was then caught blocked in `poll()` having used **0.02 s of CPU in 6 min** (`wchan=poll_schedule_timeout`), matching the deadlock description exactly. **Correction to the DEBUG note:** the *bench* configs are not at DEBUG — `bench/wl_{up,tum,stanford,i2}/np.conf` all set `log4j.rootLogger=INFO`, and `DefaultProbeLogger=INFO,Event` still floods: wl_i2 alone writes **134 MB** of logs, i.e. INFO is already >2x the tmpfs. The `rootLogger=DEBUG` observation applies to `Log4cxxConfig.conf` (the default/e2e config), not to the bench tier — so quieting the bench tier needs the `Event`/`stdout` appenders addressed, not just a root level change.
- [ ] **Benchmark teardown doesn't reap `net_plumber` on a workload's failure path** → the socket/port (`/dev/shm/np1.socket`, TCP 44000) stay bound → next workload fails `EADDRINUSE` ("could not connect to fave"). Even on the success path there's a transient EADDRINUSE between consecutive workloads (swallowed). Teardown should kill the backend unconditionally + wait for socket release.
  - **CONFIRMED 2026-09-09, while measuring item 1r.** Skipping the inter-workload cleanup once reproduced the cascade exactly: a leftover `/dev/shm/np_aggregator.socket` → `aggregator/aggregator_service.py:280 OSError: [Errno 98] Address already in use` → `util/aggregator_utils.py:63 Exception: could not connect to fave`, and the workload died in `_initialization`. Note `test.sh`'s `run_bench` does **not** clean between workloads, so per-workload timings are unobtainable without adding a cleanup step (the item-1r measurements had to add one; the interference is reported there rather than hidden). Orphans also accumulate: ~78 unreaped `[net_plumber] <defunct>` entries built up across runs — the orphaning is FaVe's, the non-reaping is the sandbox's (PID 1 there is `claude`, which does not reap). **NB for whoever writes the fix:** a `kill -0` or bare `pgrep -f` liveness check is useless here — both succeed on a zombie, so a teardown watchdog must filter on process STATE (`ps -eo stat` / `$1 !~ /^Z/`) or it will wait forever on a dead backend.
  - **Sandbox `/dev/shm` note:** the container's `/dev/shm` is 63 MB and **cannot be enlarged** (`mount -o remount`/`--bind` denied). Workaround used to run e2e/bench here: symlink `/dev/shm/np → /var/tmp/np_logs` (disk); survives the benchmark's `rm -rf /dev/shm/np/*`; sockets stay in `/dev/shm/` root. Not committed (env-only).
- [x] **Eager PyBison parser build caused two CI failures — FIXED `60a9686c` (lazy parser).** First real CI run (76209624362): gating **fast** job died `ModuleNotFoundError: No module named 'bison'` (test_aggregator → aggregator_service → topology → parser_singleton built the parser at import; fast job has no pybison); the non-gating **e2e** smoke `example.sh` **segfaulted** building the parser (`tmp.tab.c: unterminated #ifndef` — a truncated generated file) → switch never added (`KeyError: 'sw0.2'`) → 12 flow checks failed. Root cause = `parser_singleton` built the PyBison `IP6TablesParser` *eagerly at import*: the background aggregator built it at startup **concurrently** with the switch `topology.py` client, both writing fixed-name `tmp.y`/`tmp.tab.c` in the same cwd → race → corruption → segfault. Fix = lazy proxy: the parser builds only on first `PARSER.parse(...)`. The aggregator never parses (it gets already-parsed models) and only `packet_filter` clients parse, so at most one sequential build remains — race structurally impossible. Verified: fast 270@81%, full e2e green locally (example flow checks ok). **Residual risk:** PyBison writes fixed-name tmp files to cwd, so any *future* concurrent parser build (parallel benchmarks, a new parsing device type alongside a parsing aggregator) could re-race; a robust fix would isolate PyBison's build dir per process.
  - [x] **Build integration — DONE (2026-06-26).** `pybind11-dev` added to the CI composite (`setup-fave-native`), Dockerfile, and `net_plumber/setup-ubuntu.sh` (`+python3-dev`); `liblog4cxx-dev`/`flex`/`bison` were already present. NetPlumber now built `DEBUG_FLAGS=-fPIC` in the composite + Dockerfile (PIC objects link both the executable and the `.so`; tests unaffected), then `LIBNP_ASSUME_PIC=1 build_libnetplumber.sh` builds the module. `.so` imported off `sys.path` via `lib_adapter.py` (import-safe when absent; equivalence test `skipIf`s). Full clean sequence (`-fPIC` build → `.so` → equivalence test) validated locally. **Needs a real CI run to confirm** (like other CI changes). **P1 COMPLETE.**
- [x] **P2 — `libapkeep` — DONE (2026-06-26, commit `a9e0f968`).** `fave/apkeep/lib_apkeep.py` = `LibAPKeep`, a resident-JVM JPype driver (the APKeep counterpart of the libnetplumber binding): loads the apkeep jar, sets up a network, applies rule updates **in memory** (`run()` takes a Python list of rule strings, not a file APKeep parses), and retrieves loops. **No changes to the APKeep fork needed** — its existing `Network` API is embeddable enough. Validated by `fave/test/test_apkeep_lib.py` (integration tier): drives the bundled Stanford set in-memory and reproduces the **20-loop CLI golden** — proving the in-process binding ≡ the batch CLI. JPype auto-detects the JDK-11 JVM (no `JAVA_HOME`); installed alongside pybison in the CI composite + Dockerfile (kept out of `requirements.txt` so fast stays pure-Python). Integration green (16 tests), fast unaffected (270@81%). **Needs a real CI run to confirm.**
  - [x] **In-memory `initializeNetwork` cast — ROOT-CAUSED + RESOLVED (2026-06-26).** Not a bug: APKeep's `readACLs` (APKeep.java:134-137) splits ACL filenames device-by-`name`, with a `name.equals("stanford")` special case (device = first *two* `_`-tokens for stanford, else first token). My P2 manual call skipped `parseParameters`, so the static `name` stayed `"unknown"` → `readACLs` parsed `coza_rtr_120` as device `coza` → the ACL element `coza_rtr` overwrote the `ForwardElement coza_rtr` → `addVLANs` cast failed. With `name` set, `initializeNetwork` works with correct collections (confirmed). **Irrelevant to P4**, which builds APKeep collections directly from FaVe's model rather than via APKeep's name-dependent file parsers.
- [x] **P3 — reachability solver — DONE (2026-06-26, commits `d84133df` apkeep + `704dedc6` FaVe).** `apkeep/src/main/java/apkeep/checker/ReachabilityChecker.java`: existential port-to-port reachability over the PPM, mirroring `Checker.traversePPMDivision` (full-space `BDDTrue` seed; fwd + ACL AP sets tracked separately, arrival iff they overlap; reduces to plain forwarding when no ACLs; simple-path DFS that terminates on looping networks; arrival only after ≥1 hop so self-reach needs a real cycle). Exposed as `LibAPKeep.is_reachable(src, dst)`. Validated functionally (reaches a real forwarding port; rejects a bogus device + a zero-AP port); integration green (19 tests). *(Loop-based validation was a dead end: APKeep's golden loops are TRANSIENT — accumulated during the incremental updates — while the final PPM routes ~everything via `default`; rigorous reachability correctness is the P5 differential vs NetPlumber.)* Shadow detection via `hit_bdd` not done (optional; benchmarks need reachability/compliance).
  - **Constraint for P5 (from-zero benchmark):** APKeep allocates a single 100M-node BDD table and keeps its network in static fields; JPype's JVM is process-global/resident → **only ONE APKeep network per process** (a second `APKeep.init` OOMs in `new Network`). So a from-zero APKeep measurement needs **one process per run** (fresh Python+JVM) — or a reduced `BDD_TABLE_SIZE` / a reset path. Plan the benchmark harness accordingly (the libnetplumber side has no such limit).
- [x] **P4 — `APKeepAdapter` + model translator — DONE (approach B). FaVe+APKeep matches FaVe+NetPlumber (reachable.json) exactly on wl_ifi.**
  - [x] **In-memory construction + reachability solver foundation (2026-06-26).** `LibAPKeep.init_in_memory` builds an APKeep network from in-memory collections (commit `1d42a1c6`); `ReachabilityChecker` detects arrival at egress *and* link-destination ingress ports (`46697b9f`); deferred `initializeNetwork` cast resolved (`64505baf`).
  - [x] **Forwarding-only `APKeepAdapter` (2026-06-26, commit `dafb4999`).** `fave/apkeep/adapter.py`: `AbstractVerificationEngine` subclass that buffers the FaVe model, builds the APKeep net lazily on first `check_compliance`, translates router/switch device models → `ForwardElement`s + dst-IP `+ fwd` rules, links → topology, generators/probes → ports, and `check_compliance` → `is_reachable` per (source, probe). VLAN dropped (redundant). Validated on a hand-built router+switch+source+probe (`test_apkeep_adapter.py`, integration tier, 4 tests); integration green (23 tests; the adapter's 1M-BDD net coexists with the lib's 100M stanford net).
  - **VLAN double-checks (resolved):** APKeep has no VLAN header field (port-flooding only); wl_ifi forwards purely by dst-IP (`rw=vlan` cosmetic, ACLs IP-based); `inventory.json` gives every role a distinct IPv4 range → VLAN redundant → safe to drop.
  - [x] **ACL translation — DONE (2026-06-29, commits `9455e4f2` apkeep-subtree + `bf164734`,`fda8256b` fave). EXACT match to reachable.json.** The router's acl_in/acl_out become per-port APKeep `ACLElement`s: APKeep has no VLAN field, so the VLAN (which the cisco ACLs key on) is made **structural** — each ingress/egress router port gets its own ACLElement carrying that port's VLAN group, spliced into the L1 link via APKeep's `_in`/`_out` naming convention (the `permit` port leads onward; the unwired `deny` port drops). acl_out attaches to egress ports via the routing VLAN→port map; acl_in attaches to ingress ports traced source→switch→router-port from generator VLANs + pre_routing's port→VLAN (the Internet port's anti-spoofing 4095). cisco first-match → descending priority (APKeep is higher-priority-wins); prefix → cisco IP + inverse-mask wildcard; permit == forwards to an internal pipeline port. **src-IP seeding** (apkeep subtree: `ReachabilityChecker.isReachable(src,target,srcip,len)` + `Network.getACLSeedAPs` → `acl_apk.getAPExp(encodeSrcIPPrefix())`) restricts the ACL packet space to the injected source so src-matching ACLs bite — without it a flow is reachable whenever *any* source is permitted. `test_apkeep_acl` validates the mechanic; `test_apkeep_wl_ifi` now asserts **missing=0, extra=0** vs reachable.json (self-reach source.X→probe.X excluded — never traverses the router). 14 apkeep integration tests pass.
  - [x] **Full wl_ifi end-to-end — DONE (2026-06-29, commit `1bc5f2e0`).** `fave/util/in_process_driver.py` (`InProcessFaVe`) routes topology.py/switch.py's JSON command stream into an in-process `AggregatorService(engine=adapter, reporter=stub)` — reusing all the real model-building + `_sync_diff` dispatch, no sockets/net_plumber (and the P5 comparison substrate). `test_apkeep_wl_ifi.py` drives the real wl_ifi (router `ifi` + 16 switches + 17 gen + 17 probes) and checks the source→probe reachability matrix against `reachable.json`: **forwarding COMPLETENESS holds (MISSING=0** — all 54 expected pairs reachable); EXTRA=122 = 16 self-reach + 106 ACL-dropped (forwarding-only ⊇ ACL-filtered, exactly as theory predicts). 11 apkeep integration tests pass together. Adapter fixes surfaced by the real model: **priority := prefix length** (APKeep ForwardElement is higher-priority-wins; arrival-order priority let `/0` default routes shadow specific routes → every switch sent all traffic to its default port); `_split_port` strips `_ingress`/`_egress`; `match=null` → `0.0.0.0/0`; `add_rules` restricted to `<node>.routing`/`<node>.1` (acl tables forward to internal pipeline ports → bogus APKeep ports); added `global_port`/`links`/`asyncore_socks` (engine surface the aggregator link-wiring touches).
  - **Exact match achieved** via ACL translation (above): the 106 ACL-dropped extras are gone; only the 16 intra-switch self-reach pairs remain, which the policy matrix omits (excluded from the comparison).
  - **P5 can reuse `InProcessFaVe`** to run FaVe+APKeep and FaVe+NetPlumber on the same models and assert agreement / from-zero timing.
- [x] **P5 — Differential gate + benchmark — DONE (2026-06-29).**
  - **Differential gate** (`fave/test/test_backend_differential.py`, integration tier, commit `f404754d`): drives wl_ifi through BOTH backends via the same `InProcessFaVe` path and asserts they compute identical reachability AND both match the policy oracle `reachable.json` (missing=0, extra=0). Two independent algorithms — APKeep's per-pair atomic-predicate port reachability vs NetPlumber's source-flow `check_compliance` (inspects each probe's incoming `source_flow`; violation iff `(valid && !any)` — `any` = a flow from src reaches the probe, so an all-pairs must-reach query's violations are exactly the not-reached pairs). Self-reach excluded. Skips if jar/.so unbuilt or inputs absent. 17 apkeep integration tests pass together (NetPlumber .so + resident JVM coexist).
  - **From-zero benchmark** (`fave/bench/apkeep_vs_netplumber.py`, manual, commit `73f395b3`): user-perceived from-zero (model build + full reachability), in-process, JVM-warm-up handled (resident JVM, steady-state median + labelled cold). **wl_ifi results (12 iters):** NetPlumber steady ~49 ms (cold ~148); APKeep steady ~140 ms (cold ~527, incl. JVM boot+JIT). At wl_ifi's small scale (18 devices) NetPlumber's low constant overhead wins; APKeep's atomic-predicate advantage is expected at larger scale.
  - **Scale validation on wl_i2 — DONE (2026-06-29, commit `71bd572c`).** wl_i2 (Internet2, 77k dst-IP routes / 9 routers) drives through the adapter EXACTLY (reachability == reachable.json, missing=0/extra=0). i2's HSA in/out-switch model collapses cleanly (in-tables forward to one internal port; out-tables are a real dst-IP FIB; VLAN = droppable link identity). **From-zero (single run each, in-process): NetPlumber 341 s (≈all model build — per-rule flow propagation) vs APKeep 14 s (build 6.5 s + compliance 7.6 s) → ~24× faster.** Confirms the thesis premise: header-space flow propagation doesn't scale to large FIBs; atomic predicates do. `bench/apkeep_vs_netplumber.py` is now workload-parameterized (`wl_ifi` | `wl_i2`); `InProcessFaVe.replay` gained a `files` override. **CI gate (commit `f8c28107`):** `test/test_apkeep_i2.py` (integration tier, ~15 s) asserts the exact match; `test/gen_wl_i2_inputs.sh` regenerates the gitignored inputs from tracked sources (prepare_benchmark for the device model; policy_translator + reach_csv_to_checks for the oracle) with no live backend, run by `run_integration` before the APKeep pytest.
  - **wl_stanford NOT supported by the dst-IP adapter (characterized limitation):** stanford's HSA out-tables forward by INPUT PORT (one header class fanned to different egress ports keyed on ingress port) and it carries transport-layer (tcp/proto/flags) ACLs — neither maps to APKeep's destination-IP `ForwardElement`, so the adapter under-approximates (missing=204). Reframed below as an *extension* (P7), not a wall (APKeep paper §9 reassessment).
- [x] **P6 — APKeep core test hardening — DONE (2026-06-30, commits `f50f6ab8` + `5ee99fba`).** Added a JUnit5+jacoco harness to the `apkeep` fork (tests run in the `test` phase of `mvn package`, so the integration tier gates on them) + 16 unit tests across the six reachability-critical classes: `ForwardElement` (LPM via higher-priority-wins), `ACLElement` (5-tuple proto/ports), `APKeeper` (minimum-EC split/merge, Thm 1), `Network` (in-mem wiring, ACL-node naming, `getACLSeedAPs`), `BDDACLWrapper` (encoders + variable-layout lock), `ReachabilityChecker` (ours, 0%→94%). Ratchet floor: BUNDLE instruction ≥ 30% (currently 35.8%). Full detail: [`TESTING_STRATEGY_JAVA.md`](TESTING_STRATEGY_JAVA.md). **Unblocks P7.**
  - *(was)* The APKeep Java core had **zero unit tests** (no `src/test`, no JUnit/jacoco, build `-DskipTests`); covered only indirectly by the Python integration tests, on IPv4-forwarding + IP-only-ACL paths. Add a JUnit5 + jacoco harness (`mvn test` in `apkeep_smoke.sh`, coverage ratchet on the reachability-critical packages) + characterization/unit tests for the path we use & will extend: `BDDACLWrapper` (encoders + **variable-layout lock**), `ForwardElement` (LPM + **priority=higher-wins**), `ACLElement` (**5-tuple proto/ports — currently untested**), `APKeeper` (`getAPExp`, min-EC), `Network` (in-mem wiring, `getACLSeedAPs`), `ReachabilityChecker` (ours). Full strategy: [`TESTING_STRATEGY_JAVA.md`](TESTING_STRATEGY_JAVA.md). Test-before-extend; gates P7–P9.
- *(re-scoped 2026-06-30 after the wl_stanford investigation — see `APKEEP_BACKEND.md` §9. "multicast" = L2 spanning-tree flooding APKeep handles via `vlan_ports`; VLAN-as-match-field is the clean fix for the ACL scoping + the reduced multi-field rehearsal for wl_up.)*
- [x] **P9a — VLAN as a header *match* field in APKeep core — DONE (2026-07-01, commit `350e6f33`).** 12-bit `vlan` field in `BDDACLWrapper` (variables declared last → no field-shift, proven by the P6 layout-lock; `ConvertVLAN` AND-ed into `ConvertACLRule`), `ACLRule` optional trailing VLAN token (14-token format unchanged → wl_ifi ACLs + Python integration unaffected). Test-first: `BDDACLWrapperTest` (VLAN independent/distinct + layout-lock intact), `ACLElementTest` (VLAN-scoped deny/permit), new `VlanFloodTest` (previously-untested `getVlanPorts` flood branch). 19 tests green; ratchet 30→33%. **Unblocks P7.**
- [x] **P7a — wl_stanford forwarding (out-stage collapse) — DONE (2026-07-01, commits `407f095c` gen, `2a36d4af` collapse, `bbd6d3e4` wiring).** `out.X` is an `in_port→out_port` permutation a dst-IP `ForwardElement` can't express (baseline missing=204); `APKeepAdapter._collapse_out_stage` statically resolves `mid.<110n>→out.<130n>→[perm]→out.<120m>→in.Y/probe` and wires the `mid.` egress interface straight to the neighbour (48 switches→32 FEs). Gate `test_apkeep_stanford.py` + `gen_wl_stanford_inputs.sh`; from-zero in `apkeep_vs_netplumber.py` (~1.3 s ≈ NetPlumber ~1.4 s). **The exact match is vs the artificial all-to-all POLICY `reachable.json`, NOT the data plane.**
- [~] **P7b — wl_stanford faithful VLAN. PARTIAL (240→77, sound); VLAN admission blocked on APKeep core.** **RE-SCOPED 2026-08-12 by the LPM correction + Phase-2 attribution ([`APKEEP_STANFORD_NP_SPEC.md`](APKEEP_STANFORD_NP_SPEC.md) Phase 2):** with NP now a faithful LPM oracle (165, not 10), APKeep's residual over-reach is **75 pairs = exactly 5 source routers × 15 dests** (`bbrb, boza, goza, roza, yozb`, each 0 in NP / 15 in APKeep). Attributed to a SINGLE mechanism — **in-port-qualified ingress admission** (P7c gap 2), **NOT VLAN-rewrite and NOT IP/5-tuple ACL** (those contribute 0 of the 75): the 5 sources attach to in-ports absent from their in-stage `(in_port,vlan)→fwd` table (e.g. roza port 32 = iface gi4/8, an unconfigured `no ip address`/no-switchport port in no VLAN); NP propagates `in_port` and drops, while APKeep `_translate_fwd_rule` (`adapter.py:204`) keys on dst only and ignores `rule.in_ports` → `/0` forward-all admits any port. **Oracle twist:** `reachable.json` is the INTENDED policy (full 240-mesh) so vs policy APKeep=240=oracle EXACT and NP under-reports the 75; vs the REAL data plane the 5 ports are genuinely dead so NP is faithful. ⇒ the 75 is half an APKeep in-port-fidelity gap, half a benchmark source-placement artifact (5 sources on unconfigured interfaces the full-mesh oracle assumes live). **FIXED 2026-08-12 (commit `38e6b79f`, spec Phase 2 fix) — in APKeep, per the principle "fix the tool not the benchmark" (gi4/8 genuinely admits nothing ⇒ NP faithful, APKeep deviated):** `adapter.py` `_capture_in_admit` records each in-stage device's admitted physical-port set; `_gate_dead_ingress` drops topology edges into unadmitted ingress ports (no-op where admit-all/admitted; inter-router trunks survive; wl_i2 unaffected). **APKeep 240→165, converges EXACTLY with NP (over=0, under=0, SOUND).** Scope = dead-port case (100% of this residual); full per-(port,VLAN) admission stays the separate intractable P7b concern. Diagnostic: re-placing the 5 sources on covered ports makes NP=240 ⇒ no VLAN/ACL residual beneath. `test_apkeep_stanford` recalibrated (user Option A): now asserts APKeep==FaVe+NetPlumber (both 165, NP in a separate process); `reachable.json` stays the all-to-all must-reach policy, the 75 dead-port pairs are genuine violations. Exactness gate green 10/10. **The VLAN-rewrite work below (240→77) was measured against the OLD non-LPM oracle (NP=10) and is superseded for the wl_stanford residual — retained for the VLAN-rewrite core it built (reusable for wl_tum/wl_up).** Historical detail follows.\n  - *(historical, pre-LPM-correction)* Cross-check (reference oracle NP): forwarding-only=240 vs NP=10 (all edge→core). **DONE:** Java VLAN-rewrite core (`Fields.vlan`, field-selecting `RewriteRule`); NAT-in-reachability (`NATElement.encodeOneRule` VLAN form, inline `addNATs` insertion, `ReachabilityChecker` rewrites through NATs; multi-rule-NAT AP-merge crash fixed via disable-able `MergeAP`); LibAPKeep `device_nats`+`target_vlan`; adapter `faithful_vlan` path (mid VLAN-rewrite NATs folding the out-reset into the effective egress VLAN + probe `vlan=0` filter). **Result 240→77 = a SOUND superset of NP's 10** (separate-process diff: under-approx=0). **VLAN admission (77→10): CORRECT but blocked on PERFORMANCE (OOM), not modelling.** Admission is drop-by-field ⇒ `ACLElement` ⇒ AP *division* (separate universe) which disagrees with the fwd-universe VLAN rewrite (`fwd∩acl∩vlan0`=∅; in-admission-alone 217, probe-alone 77, **both 0**). **Fixed** with a **single-universe** mode (`Parameters.USE_DIVISION=false` keeps ACLs in the fwd APKeeper; `ReachabilityChecker` filters the fwd AP set at ACLs) — **confirmed correct** by `NATReachabilityTest.ingressAdmissionComposesWithRewriteInOneUniverse` (ingress ACL upstream of the rewrite composes). Adapter splices a per-router `iacl_<idx>` on the `in.X→mid.X` edge. **NAT+merge crash FIXED** (consolidated all eager-merge sites — `tryMergeIfNATElement` + `transferOneAP` — into the end-of-update batch merge; guards + `updateAPSetMergeBatch`; 24 unit tests green merge-ON; full build no longer crashes/OOMs). **BLOCKED on build PERFORMANCE (modelling-efficiency wall, not a bug).** Faithful build doesn't finish in 25 min. Ruled out: per-rule batch merge (on/off both >400 s) and the ACL-rule count (a compact encoding — one ACL rule per router over the admitted-VLAN SET via `ConvertACLRule` OR, ~1800→16 rules — still >400 s). Mid-NATs alone build ~50 s, so the dominant cost is the **~3372 per-route VLAN rewrites (NATs) interacting with the VLAN-set ACLs in one AP universe**. Impractical vs NetPlumber ~1.4 s. APKeep's OWN stanford snapshot builds in <1 s (515 APs) because it does NOT model VLAN reassignment as thousands of per-route NATs; a tractable exact 10/240 needs a more efficient stanford encoding (a separate, larger effort). VLAN model is correct throughout (unit-tested). **Recommendation: ship the sound over-approximation (77 ⊇ NP's 10)**; faithful path gated, correct-but-intractable. Local NP diff needs `liblog4cxx` + SEPARATE processes (JVM+NP in one process → NP wrongly 240).
- [!] **P7c CONCLUSION OVERTURNED (2026-08-12) — see [`APKEEP_STANFORD_NP_SPEC.md`](APKEEP_STANFORD_NP_SPEC.md) Phase 1.** The premise below ("`bbra→rozb` genuinely UNREACHABLE, NetPlumber sound AND complete; APKeep over-approximates") is **WRONG**. Ground truth: the real Cisco FIBs do **longest-prefix-match**; NetPlumber as the FaVe model feeds it uses **file-order** rule priority (not LPM), so its `10/240` is a **priority artifact**. Re-prioritising NP's mid-stage FIB by prefix length flips `bbra→rozb` to reachable and raises NP `10 → 165` on the full model (`bench/stanford_priority_check.py`) — matching the real FIB and APKeep. **APKeep's LPM forwarding is FAITHFUL; NP is over-restrictive.** P7c mis-attributed the block to the out-stage because it trusted NP's file-order flow dumps and assumed NP does LPM (it does not). The real remedy is a **FaVe-model** fix (order the Stanford FIB by prefix length so NP does LPM), then measure APKeep's genuine VLAN/ACL residual against the corrected oracle. **FIX IMPLEMENTED & VALIDATED 2026-08-12** (commit follows): `bench/np_preparation.py` `_reprioritise_mid_lpm` re-prioritises each `mid.*` FIB by dst-prefix length (longest→lowest index=highest NP priority; replicates the proven `stanford_priority_check._reprioritise_lpm`). **0b: NetPlumber `10 → 165`, under-approx 0 (SOUND), over-approx `155 → 75`** — the 230-gap splits into the fixed 155-pair NP artifact and the genuine 75-pair APKeep VLAN/ACL residual (P7b, now measured vs the corrected LPM oracle). **0a exactness gate: PASS** (wl_i2 77k exact ⇒ the mid-scoped pass is a true no-op there — wl_i2 is `['in','out']`, no `mid` stage). The historical P7c analysis is retained below for provenance but should be read through this correction.
  - **Provenance of the non-LPM order + NP priority semantics VERIFIED (2026-08-12).** The shortest-first order is introduced by `np_reproduction/transform.py`'s explicit `tab['rules'].reverse()` (+ `toggle_mask_bits`); the upstream Hassel `cisco_router_parser.py` (trie `compress_ip_list` → post-order `output_compressed`) emits **longest-first**, so the vanilla NP dataset is LPM-ordered and FaVe's `stanford-json` is that reversed. Two potential objections checked and cleared: **(a) the rewrite-mask semantics change** does NOT affect this — NP's priority/overlap uses the rule `match` only (`net_plumber.cc` add_rule `r->match ∩ rule->match`), the mask only drives the `rw` rewrite (`rule_node.cc array_rewrite`); and the ordering was re-confirmed via `np_preparation`'s own `ipv4_dst=X/N` decode, not raw bits. **(b) the rule-storage list→`std::map` (keyed by index) refactor** preserved `low index → high priority` — verified by code (`r->index` from the explicit param; influence via `if (r->index < rule->index)`; ordered map keyed by index) AND by a controlled test: re-indexing the same 869 overlapping mid.bbra rules flips NP `10 ↔ 165` purely on index assignment (longer prefix → lower index ⇒ LPM 165). **A/B SETTLED then CORRECTED (2026-08-12): vanilla NetPlumber does LPM (~165); the FaVe BACKEND has the bug** (spec Phase 1d). Built vanilla NP (`bitbucket.org/peymank/hassel-public`, `-std=gnu++11`) AND python2.7 from source; ran the authentic pipeline. The authentic `.tf.json` FIB is longest-first; the canonical generator `generate_rules_json_file.py` does `insert(0)` (→ shortest-first vanilla dataset); vanilla NP `--load` front-inserts (`add_rule(index=0)`) → reverses back to longest-first → **LPM**. Generator `insert(0)` + loader front-insert are a MATCHED PAIR (cancel) ⇒ **vanilla NP = LPM ~165** (confirmed: source bbra reaches 15/16). **So vanilla's front-insertion is NOT a bug**, and my earlier "scenario A / vanilla = 10" was WRONG (it ran vanilla NP on a reconstruction that missed the generator's reversal). **APKeep (LPM), vanilla NP (LPM ~165), and the real Cisco FIB all AGREE and are faithful.** **The FaVe BACKEND (`10`) is the only non-LPM one — bug from the list→map change:** FaVe's fork changed `--load` to pass the rule's stored id/position as the NP index (`main_processes.cc:144,157`, commits `e91676ec`/`c0593fc4`) instead of vanilla's `index=0` front-insert (a hash-map can't front-insert — collisions), dropping the load-side reversal; FaVe `stanford-json/*.tf.json` = vanilla `mid.rules.json` renamed (`b2ad4fa4`, shortest-first, un-reversed) + `np_preparation.py:114` uses position as index ⇒ shortest-first as priority ⇒ default wins ⇒ non-LPM. `transform.py`'s reverse (Claas's, `059d13bd`) correctly compensates for the *reproduction* (both `--load` → LPM 165, agree); the backend never got it. **FIX (FaVe backend) — DONE 2026-08-12:** `np_preparation.py::_reprioritise_mid_lpm` re-prioritises each `mid.*` FIB by dst-prefix length (longest→lowest NP index), scoped so it's a structural no-op where there is no `mid` stage. Chose the prefix-length sort over a blind `reverse()` (order-independent; a plain reverse is LPM only if the table is already prefix-monotonic) and over C++ `--load` front-insertion changes (smaller, testable). **Gates green:** 0b FaVe stanford `10→165` agreeing with vanilla NP + APKeep (over-approx `155→75` = genuine APKeep residual, under-approx 0 SOUND); 0a exactness PASS (wl_i2 77k exact, wl_ifi, wl_stanford P7a, backend differential).
- [ ] **P7c — wl_stanford exact 10/240 needs TWO orthogonal fixes, not one (2026-07-10; full detail in [`APKEEP_BACKEND.md`](APKEEP_BACKEND.md) "Deferred merge, split/merge cost model, and the two-gap finding").** A **bounded-subset faithful cross-check** (`subset_check.py`: induced sub-topology, identical to both backends, separate processes) makes the faithful NAT model tractable and compares it to NP directly. On `{bbra_rtr, rozb_rtr}`: faithful APKeep = **2** (`bbra→rozb`, `rozb→bbra`) at 2552 APs/6 s vs NP = **1** (`rozb→bbra`). **So the faithful VLAN model over-approximates NP *even when tractable* (sound superset), correcting the P7b claim that `77→10` is only VLAN-admission performance.** There are **two independent gaps**: **(1) VLAN tractability** — the un-mergeable per-route NAT cross-product (2552 APs for 2 routers; `NATElement.isMergable` won't coalesce rewrite outputs); fix = generalize `isMergable` ("option 2"), also serves wl_up state rewrites. **(2) transfer-function fidelity** — all 6109 mid+in TF rules are in-port-qualified and NP propagates `(in_port,vlan,src,dst,proto,dport)` jointly, but the adapter uses **decoupled per-field elements** (dst-only `ForwardElement`, per-VLAN admission, out-stage VLAN dropped); fix = faithful in-port-qualified forwarding + out-stage VLAN in the **adapter**. **Closing only gap 1 → scales but still a sound superset; exact 10/240 needs BOTH.** Cost model (from the code): a single split/merge is cheap + AP-count-independent; the wall is the `O(rules × |AP|)` **build** term (`updatePortPredicateMap` does `bdd.and` per AP at the affected port), binding because |AP| is large AND un-mergeable — the query path is `retainAll` (cheap), so large |AP| is fine for analysis. Also ruled out: deferred per-table merge (still >400 s) and insertion order (moves the sweep onto the 200×-more-numerous FIB rules). **Option 1 (structural VLAN = qualified egress port)** is tractable (337 APs, ~5 s, reachable=77 sound superset) but structurally can't reach 10 (it decouples VLAN from the correlated header); kept as an env-gated throwaway (`STRUCTURAL_VLAN=1`), **not committed**. Regression oracle for gap 2: the `{bbra_rtr, rozb_rtr}` subset (single known discrepancy `bbra→rozb`), fast in both backends.
  - **Baseline validated (2026-07-10), and gap-2 localized to the OUT-STAGE via NP flow dumps.** Validated NP against independent ground truth (original Cisco config + NP's own `dump_flow_trees`), NOT `reachable.json` (artificial all-to-all) nor NP-vs-NP. **Verdict (solid): `bbra→rozb` genuinely UNREACHABLE, `rozb→bbra` genuinely REACHABLE; NetPlumber is sound AND complete on this pair; APKeep over-approximates (`bbra→rozb` false positive).** **Mechanism (corrected — flow-grounded):** NP's `source.bbra` flow *does* inject and reach `mid.bbra` (869 branches) but crosses to **no** neighbour — all transit dies at the `mid.bbra→out.bbra` transition; only self/`probe.bbra` survives. `source.rozb` *does* cross to bbra. Both cross-links exist in NP's plumbing, so it is **not a missing edge**; at a dying branch the `out.bbra` in-port *has* a rule yet **no pipe forms** → a **header-overlap failure at the out-stage**. APKeep **collapses the out-stage** (`_collapse_out_stage`/`_out_perm` wire each mid egress straight to the neighbour), bypassing that condition → over-forwards. **RETRACTED earlier mechanisms:** the "routes-via-roza / next-hop `172.20.5.33` absent" story (NP excludes `bbra→rozb` in the *full* topology too) AND the "bbra can't source (ruleless ingress port)" idea (bbra sources fine). **Still open:** the exact discriminating out-stage field (NP packed-vector decode unreliable; rule-text reading self-contradictory) — do NOT assert a VLAN value until decoded. GRE is a red herring here (flow dies before any Tunnel10 delivery). `ReachabilityChecker` instrumented with `witnessPath`/`witnessFwd` (uncommitted diagnostic); NP `dump_flow_trees` is now the per-hop oracle for the fix. Detail in [`APKEEP_BACKEND.md`](APKEEP_BACKEND.md) "Baseline validation: NetPlumber vs config-derived ground truth".
  - [x] **Discard/`Null0` drop rules — FIXED for dst-only discards (2026-07-10, commit `886a2082`).** `_translate_fwd_rule` previously skipped rules with no forward action, so APKeep didn't model Cisco `Null0`/anti-bogon discards (e.g. `192.168.0.0/16 → Null0`) that NetPlumber honours → over-approximation for genuinely-discarded ranges (safe for isolation/must-not-reach = false alarm; UNSOUND for reachability/must-reach = false assurance). Now models a dst-only discard as a blackhole forward to a dead `__drop__` port at LPM priority (default-on; uses APKeep's existing `ForwardElement`). **Validated, no regressions:** wl_ifi 3/3, wl_i2 2/2 (77k build + exact oracle), stanford P7a 2/2, adapter/acl/lib 9/9, differential 3/3; wl_ifi/wl_i2 have zero dst-only discards (no-op), stanford exercises it and still matches. **Residual:** source/proto/dport discards still skipped (need ACLElements). **Was NOT the cause of `bbra→rozb`** (NP doesn't drop `.204` — LPM `/20` forward beats the `/16` discard; the fix left the pair reachable; `.204` is in the *forwarded* `/20`). Detail in [`APKEEP_BACKEND.md`](APKEEP_BACKEND.md) "Known limitation: APKeep does not model discard / Null0 drop rules".
  - **NetPlumber `Node::propagate` read (2026-08-11).** NP *does* have split-horizon (`should_block_flow`, node.cc:385): at output-layer emission it blocks a flow from egressing the port it entered on (`f->in_port == out_port`), ingress port tracked as flow **metadata** up the `p_flow` provenance chain (NOT a header field) — **the operator's original hypothesis was right; the earlier "no port field ⇒ no split-horizon" dismissal is retracted.** BUT it is **dormant in the FaVe 3-stage model** (verified): each source sits on its peer-facing interface, so if it fired it would block both directions — yet `rozb→bbra` is reachable; the 3-stage numbering makes `in_port` (`100001`) ≠ `out_port` (`120001`), so the check never fires. So it's **not** the cause of `bbra→rozb` and not an active gap on Stanford. The active mechanisms are pipe-intersection + higher-priority `influenced_by` subtraction; NP's bbra flow dies at the **mid** stage; the single root cause stays **unpinned** (shared-`/23` × 3-stage × subset tangle). **Decision:** stop root-causing; pursue soundness by **convergence** — **(1) faithful out-stage** (respect L3 next-hop; stop the collapse fabricating direct segment-neighbour edges) + **(2) adapter split-horizon** for general correctness, iterated against NP as oracle. (1) in progress.
  - **Faithful-HSA plan (2026-08-12) — chose deep faithful modelling (option 2) over accepting the over-approximation.** Phased, risk-gated plan in [`APKEEP_FAITHFUL_PLAN.md`](APKEEP_FAITHFUL_PLAN.md): Phase 0 foundations (0a regression safety net, 0b convergence harness, **0c nail NP semantics = hard GO/NO-GO gate** — no core surgery until we have an evidence-backed spec of what "faithful" means, e.g. fix the TRACE-mode segfault or a minimal reproducer in NP's own C++ test suite); Phase 1 design (minimal missing capability + soundness & AP-count analysis + Java micro-test); Phase 2 gated core impl + adapter wiring behind a flag; Phase 3 convergence/soundness/scale validation; Phase 4 generalize + docs. Cross-cutting: wl_ifi/wl_i2 exactness tripwire on every commit; harness over-approx count as the progress metric; every reachable→unreachable flip checked vs config ground truth (no false negatives); apkeep/ changes as separate subtree commits + FAVE_CHANGES.md.
- [ ] **P8 — state-shell rewrites (now on the critical path via P7b).** The P7b VLAN rewrite *is* the general mechanism: `NATElement`/`RewriteRule` generalized off dst-IP to any declared field. Test-first; then wire the state-shell field's rewrites through the adapter + `ReachabilityChecker` and reproduce wl_ifi's `related:` cchecks exactly. Enables wl_tum.
- [ ] **P9b — general header extension / IPv6 (optional).** Generalize P9a to arbitrary fields + implement the scaffolded `ForwardingRule6` + IPv6 ACL path. Enables wl_up (IPv6 + state-shell). Highest effort.
  - **Recommendation (updated 2026-07-10):** P6 → P9a → P7a (done) → **P7b (sound 77, ship the over-approximation) → P8** (VLAN rewrite; the stanford cross-check moved P8 onto the critical path — its faithful model needs the same rewrite as wl_tum/wl_up). **Exact wl_stanford 10/240 (P7c) is deferred and needs BOTH** gap 1 (`isMergable` for scale) **and** gap 2 (in-port-qualified TF fidelity in the adapter) — orthogonal work; option 2 alone yields only a sound superset. i2 carries the scale result independently.

### 11. Alternative verification backend: ad6 (generic SAT/QBF model checking) — PLAN (see [`AD6_PLAN.md`](AD6_PLAN.md))
**STATUS 2026-09-16 — the adapter rewrite (`AD6_PLAN.md` §9) is COMPLETE through Phase 5.** The adapter no longer reconstructs meaning from FaVe's device/table names; it transcribes FaVe's model as given (a table becomes a table, a rule becomes a rule at its own `idx`). Phase 5a flipped the default (§9.24), Phase 5b deleted the old path — **−9,269 lines**, including `ad6/src/parser/favemodel.py` and 240 tests (§9.25) — and §9.26 renamed the surviving vocabulary from `structural` to `literal` (its deleted partner `semantic` → `interpreted`), because the old pair described the two paths backwards. Reproducing any pre-Phase-5 measurement means checking out commit `86114970`; asking for the deleted translation by name now raises and says so. **Phase 6 (production wiring) is DONE too (§9.27):** `--backend {netplumber,apkeep,ad6}` on the aggregator (defaulting to netplumber, so nothing existing changes), the net_plumber connection loop skipped for backends that never use it, and `--solver`/`--lite-acyclic` selectable — the latter two had become unreachable when §9.25 deleted the measurement drivers, which would have taken with them both the cadical195 configuration every wl_i2 number was measured under and the only acyclic encoding that fits i2 in memory. A solver whose PySAT wrapper silently ignores `assumptions` is now a hard refusal under rank grounding rather than a run that reports everything reachable. **A full workload now runs end-to-end on ad6 through the live aggregator (§9.28):** `FAVE_BACKEND=ad6` on any existing `bench/wl_*/benchmark.py` (an env override, because all six drivers hardcode their constructor arguments), net_plumber started only for the backend that needs it, and the anomaly step skipped-and-said-so for engines that do not implement it. Getting there fixed three defects of one family — *a step that could not run was indistinguishable from a step that found nothing*: the report rendered compliance ONLY from net_plumber's log, so a non-NetPlumber run would have reported "no violations" whatever it found (and, opening that log at offset 0, could have replayed a STALE NetPlumber log as its own verdict); `_compliance` discarded its subprocess exit status, so an aborted check still produced a clean report — **not backend-specific**, a NetPlumber run whose checker crashed did the same; and making that fatal exposed that `run()` had no `try/finally`, so a failed benchmark left the aggregator holding its ports and a stale barrier owner for the next run. **Remaining ad6 limits, now visible rather than silent:** the query path forces only `related`, so `wl_example`'s `protocol`/`port` conditions are refused, and `wl_ifi`'s `related` checks are unanswerable because its Cisco ACLs declare no such field (§9.24.2).

**The run (§9.28.5-7):** `wl_stanford`, 240 checks, on ad6 via the live aggregator — 75 violations → **165 reachable**, set-equal pair-for-pair to NetPlumber's own libnetplumber matrix; `check_compliance` 1,781.9 s with cadical195 (yolobox, directional only). That 165 is a CONSENSUS between two implementations, not an oracle — `reachable.json` is the all-reachable policy mesh this item already calls unusable as a gate, so the run corroborates ad6 and proves nothing about correctness. **New, and squarely item 1s's problem:** the same benchmark on the netplumber backend reports 231 violations → **9 reachable**, against the worker's 165 for the same model — deterministically (13 ms, 231 `DefaultComplianceLogger` lines of net_plumber's own), and the 9 are exactly the adjacent same-zone sibling pairs. So the oracle question is not merely "which artifact" but "which code path": one engine, one model, two answers. **ROOT-CAUSED AND FIXED (§9.29):** `length` and `mapping` are one setting. `length` pre-sizes net_plumber's vectors (`--hdr-len`, BYTES); `mapping` pre-sizes the ADAPTER's mapping, which every vector it builds is sized from. `wl_stanford` and `wl_i2` passed only `length`, so the engine started 16 bytes wide while the adapter's mapping started at 0 and grew — every rule emitted before it reached full width was interpreted against a wider space than it was built for, and `NetPlumber::expand` only ever grows, so nothing corrected it. **wl_tum always passed both; the correct pattern was already in the tree.** After the fix the wl_stanford benchmark reports 75 violations → 165 reachable on NetPlumber, with a violation set *identical* to ad6's. Bisected in four one-variable experiments (§9.29.1); my first hypothesis (flow-tree provenance) was wrong. **Two spin-offs:** `Mapping.from_json` consumed its caller's dict (`del jd["length"]`) — fixed, pinned; and the CORRECT run needs ~111 MB of logs where the broken one needed almost none, so fixing it overflowed the 63 MB `/dev/shm` and the run neither completed nor failed cleanly — a correctness fix became a capacity failure. **wl_i2 RE-MEASURED both ways (§9.31):** 11 violations with the fix — set-equal to the answer §5.5 corroborated three ways — against **31** without it. The buggy set is a strict SUPERSET: 20 spurious violations added, **zero real ones missed**. That is forced by the mechanism (over-constrained rules can only manufacture "does not reach", never invent a path), so an archived verdict of *no violations* was never wrong for this reason, while any archived *nonzero* list mixes real violations with artifacts. It also shows §5.5's FaVe+NetPlumber "11" did NOT come from `benchmark.py` — under the defect that path yields 31 — so the three-way corroboration stands. This defect is very plausibly what this item means by "wl_i2's verdict is wrong", though the two were not connected at the time. **Also fixed en route (§9.30):** `start_aggr.sh` tested for a stale unix socket with `-s` (size > 0, never true for a socket), so after any unclean shutdown the aggregator failed to bind and the benchmark reported the misleading "could not connect to fave"; `start_np.sh` had always used the correct `-S`. **And §9.32:** net_plumber had NO shutdown path of its own — `stop_fave.sh` reaches it only *through* the aggregator, so an aggregator that never started, died, or was killed orphaned it silently, while `_teardown` discarded the exit status and logged "fave ordered to stop" regardless. That is the **fourth** swallowed sub-step in this stretch (after `_compliance`, the report's compliance section, and `InProcessFaVe`'s backend exceptions), and the three defects chained: stale socket → aggregator cannot bind → benchmark aborts → teardown runs → stop reaches nobody → orphan reported as stopped. Fixed both halves: teardown now reports loudly (non-fatal — it runs from a `finally` and must not mask the real error), and `start_np.sh` records each pid so `stop_fave.sh` can stop net_plumber directly when the aggregator is unreachable, killing a pid only after confirming `/proc/<pid>/comm` is still `net_plumber`. **Regression check:** wl_stanford re-run on ad6 after all four fixes reproduces **byte-for-byte** (75 violations → 165 reachable, 1,835 s vs 1,781 s), so none of them touches the ad6 solving path — and all four measurement paths (ad6 ×2, NetPlumber benchmark, NetPlumber libnetplumber worker) now agree on the identical 165-pair set. **wl_i2 also run on ad6 (§9.33): 11 violations → 61/72, set-equal to both the fixed NetPlumber benchmark and §5.5's corroborated 11.** It had to be run under `--grounding flow`: the first attempt used the default rank + `--lite-acyclic` on the strength of §5.5's "3.56 h", which is the **plain** model's figure — and **§9.25 deleted the plain model**, because `faithful_vlan` is inert under the literal translation (§9.16.1) and plain mode *was* the semantic path discarding VLAN. So every i2 run is now the faithful-scale problem, where rank+lite peaks at ~18.0 GB on a 19 GB box and thrashes into swap (killed), while flow peaks at ~10.0 GB and finishes in ~67 min. **For i2, flow is not cheaper-but-optional; it is the only grounding that fits.** Recorded in the adapter comment as well as the plan, since that is where the next caller will look.

**rank vs flow, matched on two workloads (§9.34) — the Factor-A crossover, measured:** same backend, same solver, grounding the only variable. wl_stanford (240 queries): flow **3.65× faster** (502.8 s vs 1,835.4 s), violation sets identical. wl_up (11,902 queries): flow **>31.4× slower** — *killed at the 6 h timeout with no answer*, against rank's 688.4 s and 0 violations of 11,902. So the **sign** of the rank/flow ratio depends on query count, and no single "flow is N× faster" figure may be quoted; §7.5 already caught a weaker version of that error. The >6 h is a **bound, not a measurement** — true completion time unknown, deliberately not re-run. Memory was never the constraint (7.8 GB peak, swap idle); it was purely compute. **Consequence for the default:** rank stays, now for two independent reasons — it is the only property-agnostic grounding *and* the only one that scales in query count, which is what all-pairs compliance matrices are made of. Flow's place is small-n: wl_stanford yes, wl_i2 mandatory for memory (§9.33), wl_up no. Two items fell out along the way: `InProcessFaVe` was silently swallowing every backend exception (fixed, `dcd5b1a4`), and seven `ad6_encoding_bench/` axis scripts retired with the path they depended on (`df1a1920`, independently revertible).

**Scope: integrate `ad6` (the author's IPv6-firewall SAT/QBF model checker, SECRYPT'15) as a *fourth* verification family alongside NetPlumber (HSA), APKeep(BDD), and APKeep(NDD), for a controlled cross-family comparison.** Thesis future-work, not QA. The point is **not** that a generic solver is slower (foregone) but **why, by how much, and where the trade-off inverts** — with BDD-APKeep as the analytical bridge between the domain-specific and model-checking worlds. Full motivation (the 2-D design space, the two-factor cost model, the large-network/small-n hypothesis, expressiveness×performance, the incremental-SAT lever) and the phased roadmap live in [`AD6_PLAN.md`](AD6_PLAN.md); this item is the high-level tracker. **Distinct from item 8**, where ad6 appears in its *anomaly-detection* role as a cross-oracle — here it answers full source→probe reachability.

- [x] **Theory-first + GO/NO-GO gate (AD6_PLAN §1). DONE + Claas confirmed GO 2026-08-20.** Two-factor cost model written (§1.1); ad6's actual query primitives characterized from `instantiator.py`/`main.py` — `<->>` is FaVe's own policy language (thesis-only, not ad6-native; confirmed the 3-checks claim verbatim). `<->>` IS required for wl_up (3302/11902 stateful checks in `cchecks.json`); wl_stanford/wl_i2 (0/240, 0/72) stay pure existential. ad6 already has the connection-state field end to end (`IP6TablesParser` `--ctstate` + `XMLUtils.STATES` bit-vector), confirmed against `policy_translator/policy.py`'s `<->>`→`state:'RELATED,ESTABLISHED'` compilation — so building the stateful 3-check instantiator (§4.2) is query-orchestration work reusing existing ad6 machinery, not new modelling, but it is required and makes ad6's per-`<->>`-pair cost 3 independent solves. **wl_ifi dropped from ad6 scope entirely** (2nd correction): its `acls.txt` is Cisco IOS ACL syntax (IPv4, VLAN), not ip6tables — same feasibility gap as Stanford/i2, moved into that bucket. wl_up variant provenance checked: the 138 shared per-host rulesets are byte-identical between `ad6/bench/up/` and `fave/bench/wl_up/rulesets/` right now (latter is gitignored, can't prove continuity through git history) — plan is to re-run ad6 fresh rather than dating the old run; topology-wiring parity still unchecked. Confirmed scope: wl_tum (smoke/differential, non-stateful) → wl_up (headline, stateful) first; Stanford/i2/wl_ifi gated together behind a future IPv4/Cisco-ACL/VLAN spike; §6 lever only after the wl_up baseline. Details in `AD6_PLAN.md` §1/§3.2/§4.2.
- [ ] **Metric & methodology alignment (§2).** Unify all four tools on **build + query×count** (ad6 already emits the instantiate/solve split + median/stdev/yappi); native/JVM/Python fairness; SAT-solver variance protocol.
- [~] **Revive & harden ad6 (§3). §3.1/§3.3 DONE 2026-08-20 (commit `53e1f53d`).** `make test` green (46/46; fixed a stdlib-shadowing bug and a test-fixture firewall-key convention bug, both documented in `ad6/FAVE_CHANGES.md`); deps pinned in the shared `Dockerfile` (minisat, clasp, lxml, yappi, pycosat). Remaining: §3.2 reproduce the ~36 min wl_up reachability baseline (re-run fresh rather than dating the old run — see AD6_PLAN.md §3.2).
- [~] **Integrate with FaVe (§4). §4.1 decided; §4.4 major correction from Claas, incorporated 2026-08-20.** Decided (B) model translation: a new FaVe-model→ad6 translator, NOT ad6's own `IP6TablesParser`. **Correction (Claas):** I had wrongly gated wl_ifi (and implicitly Stanford/i2) on whether ad6's own parser could read their native format (Cisco IOS ACL) — wrong question, since FaVe parses everything and the adapter emits ad6's IR directly, never touching ad6's parser. Investigated ad6's actual frontend/backend coupling: `GenUtils` (`ad6/src/xml/genutils.py`) is already a clean, generic Config-tree IR builder fully decoupled from iptables-text parsing — the "major refactor" is mostly already done on ad6's side; the real work is a new translator module. Experimentally verified (built a synthetic 2-interface test, not assumed): a rule's `jump` action can target a specific declared egress interface directly, giving real per-rule forwarding/routing semantics with zero ad6 backend changes — de-risks wl_ifi's router-forwarding and Stanford/i2's FIB modelling. wl_ifi reinstated as the recommended **first** translator-development target (small, fast, exercises ACL+forwarding+VLAN together) — ahead of wl_up, not gated behind Stanford/i2's bucket. wl_tum's differential (built before this correction) stays valid as the backend/solving-path validation: ad6 and NetPlumber agree exactly on source.tum→probe.tum. Current build order: wl_ifi (translator) → wl_up (+ stateful `<->>` instantiator) → Stanford/i2 (+ LPM-at-scale/VLAN admission, the genuinely remaining scale question). **wl_ifi DONE 2026-08-20: exact match to `reachable.json` (54/54)** — `fave/ad6/adapter.py` (capture) + `ad6/src/parser/favemodel.py` (FaVe-model→ad6 translator) + `ad6/fave_bridge.py` (subprocess bridge, since ad6 never runs in-process inside FaVe) + `fave/test/test_ad6_wl_ifi.py`. Surfaced two real ad6-core gotchas along the way, **both since fixed test-first in core (2026-08-21)**: a `/0` CIDR silently produced an empty (vacuously-false-when-forced) Gamma instead of match-all, and `_CreateInitConstraints`'s chained-XOR was broken for essentially all N>3, not just an off-by-one tail. Details + full gotcha writeup: `AD6_PLAN.md` §4.4, `ad6/FAVE_CHANGES.md`. **Stateful `<->>` query-forcing BUILT 2026-08-21** (`_capture_acl`'s `related` capture, `favemodel._acl_rule`'s `GenUtils.state(...)`, `fave_bridge._state_literals`, `Ad6Adapter._cond_to_json`) and exercised end-to-end against wl_ifi's real `cchecks.json`: all 245 plain checks + all 27 related:1 checks pass; all 27 related:0 checks currently fail against a traced, state-blind real ACL rule (not a translation gap — `bench/wl_ifi/acls.txt` genuinely carries no ctstate qualifier there). Two unrelated wiring bugs found and fixed along the way (RuleField JSON round-tripping through the subprocess bridge; `cchecks.json`'s `valid`/`negated` polarity is inverted from `check_compliance`'s own convention). **Resolved by Claas:** wl_ifi's ACLs are genuinely state-blind (Cisco ACLs are stateless in practice); the 27 `related:0` failures are correct, expected findings, not a bug — wl_ifi was shipped with `<->>` operators reflecting the security official's real intent even though the ACLs don't enforce it, specifically so a tool could catch this gap. **wl_up BUILT 2026-08-21 — a structurally new translator, not an extension.** wl_up's rule-bearing devices are FaVe `packet_filter`/`host` models (not wl_ifi's Cisco-ACL `router`), but their real rulesets (`bench/wl_up/rulesets/*-ruleset`) are literal ip6tables text — byte-identical to ad6's own bundled `bench/up` rulesets — so the translator feeds them straight into ad6's own `IP6TablesParser` (proven at scale on wl_tum) rather than hand-translating FaVe's re-parsed Match objects field by field; only dst-LPM routing and a transit device's to-self/in-transit dispatch are genuinely new adapter work (`fave/ad6/adapter.py` + `ad6/src/parser/favemodel.py:_build_ruleset_firewall/_routing_table/_dispatch_table`). Three real bugs found+fixed (two IPv4-hardcoded gaps in the adapter/translator now IPv6-aware; a `CanonizeIP` trailing-"::" IPv6 bug, originally worked around, **now fixed in core 2026-08-21, test-first, at Claas's explicit request** — turned out worse than first logged: leading-`::` and `::`-alone were ALSO broken, plus a separate crash for an address with no `::` compression at all; `ad6/FAVE_CHANGES.md` §11, `AD6_PLAN.md` §8.2b — the `_ipv6_safe` workaround is removed, verified redundant first). Also found and fixed in passing: `testCIDRMatchAll` (the `/0`-bug regression test) had never actually been wired into `xmlsuite.py`, so `make test` never ran it — fixed alongside the new test. Structural correctness confirmed (159 devices, 137 generators/probes, `fave/test/test_ad6_wl_up.py`). **Open methodology question:** wl_up's real rulesets carry operationally-necessary rules (e.g. blanket admin SSH) that reach.txt's policy matrix never modelled as role-to-role reachability — traced one concrete case confirming this is real, not a bug — so `reachable.json` strict-equality (wl_ifi's approach) is the wrong bar for wl_up; `cchecks.json`'s explicit tuples are the right target instead, deferred to a bench script (~1-2 hour full run at 11902 entries). Details: `AD6_PLAN.md` §4.2/§5.1/§8.2b, `ad6/FAVE_CHANGES.md` §9-11.
- [x] **RESOLVED 2026-08-21g — GO/NO-GO decided: NO-GO on wl_up via ad6 (stateful AND
  plain).** Bug 2 (7/8 structurally identical hosts bypassing a source-scoped DROP under
  `related:0`/NEW) was root-caused: `ad6/fave_bridge.py`'s query source-address seeding
  used a bare named-alias SAT variable instead of the canonical shared bit-vector
  conjunction — only constrained anything if that exact address string happened to be
  referenced verbatim elsewhere in the whole model (true by coincidence for `adm`, false
  for the other 7). Fixed by seeding via `XMLUtils.ConvertCIDRToVariables` instead (commit
  `dfd543b0`), test-first, same discipline as every other ad6 fix this cycle; `ad6 make
  test` (9 suites) and the three `fave/test/test_ad6_wl_up.py`/`wl_ifi(_stateful)` suites
  (9/9) stay green. The fix generalizes: re-running `wl_up_cchecks_diff.py`'s sample mode
  at 3342 checks (1126 stateful) afterward found only **1 stateful violation total** (was
  ~45% before the fix).

  **But that same larger run surfaced something bigger: PLAIN (non-stateful) wl_up checks
  are almost totally broken too — 1712 of 1713 "must NOT reach" plain checks came back as
  false violations (99.94%).** Same root cause as bug 1 (§ above): every wl_up device's
  unconditional `ctstate ESTABLISHED → ACCEPT` is a free bit any unconstrained query
  satisfies for free. **So "scope wl_up down to non-stateful checks" is not a safe
  fallback — the plain path is the MORE broken one, not the safer one.** Checked directly
  (not assumed) whether FaVe+NetPlumber has the same problem: no — `bench/
  generic_benchmark.py` defaults `use_interweaving=True`, routing wl_up's ruleset text
  through FaVe's *own* `fave/iptables/generator.py` state-shell interweaving at
  model-construction time, so there's no free bit for a plain query to exploit; this
  codebase already has an exact-match, 0-diff, 3661/3661 APKeep-vs-NetPlumber result on
  wl_up's full plain reachability matrix (`bench/wl_up/eval/apkeep_up_diff.py`'s docstring,
  `[[apkeep-ndd-baseline-and-gonogo]]`) against a *sparse* (~3370-pair) reachable set — not
  ad6's near-universal answer.

  **Decision (Claas):** porting real state-shell interweaving into
  `ad6/src/parser/iptables.py` would mean re-implementing, in a 2014 codebase that has
  already produced four real core bugs in two days, a mechanism FaVe already has working —
  undercutting the "generic tool, low integration cost" thesis this evaluation exists to
  test. wl_up's correctness work moves to **FaVe+NetPlumber (oracle) / FaVe+NDD-APKeep
  (arbiter)** — already proven, nothing new to build — not to ad6. wl_tum's and wl_ifi's
  exact-match ad6 results stand unaffected (neither needed interweaving). Remaining ad6
  effort redirects to Stanford/i2 (§5, below). Full writeup: `AD6_PLAN.md` §5.1's
  resolution, §1.4(b); `ad6/FAVE_CHANGES.md` §13.
- [ ] **Extend to all benchmarks (§5).** wl_up (NO-GO via ad6, see above — moves to
  FaVe+NetPlumber/NDD-APKeep instead) + wl_tum + **wl_ifi** (both exact-match, done, ad6's
  home turf via the translator); **Stanford/Internet2 = now the primary remaining ad6
  target (2026-08-21g)**, correctly scoped as a SAT-encoding-scale question (LPM-at-scale +
  VLAN-admission cross-product tractability), not a parsing-format question, orthogonal to
  wl_up's state problem (0 stateful checks in either), oracle already in hand
  (NetPlumber==APKeep==165 on wl_stanford).
  **2026-08-21h, before any Stanford-specific translator code: (1) scoping check — the
  165-target oracle only needs LPM + a cheap dead-port admission gate, not the full
  VLAN-admission cross-product (`apkeep/adapter.py`'s `_gate_dead_ingress` is binary
  per-port, not per-(port,VLAN) rewrite; `[[apkeep-vlan-admission-tractability]]` itself
  says full admission is "NOT needed for wl_stanford" at 165); (2) a real LPM-tiebreak bug
  found test-first on the reusable `_routing_table`/`_translate_fwd_rule`/
  `_translate_routing_rule` building block (both dst-specific routes got equal `prio`, so
  an overlapping-prefix tie resolved by capture order, not prefix length — the same bug
  class as vanilla NetPlumber's own pre-fix Stanford artifact) and FIXED
  (`Ad6Adapter._lpm_prio`, `ad6/FAVE_CHANGES.md` §14); confirmed no regression on
  wl_ifi/wl_up (14/14 fave-side + 10/10 `ad6 make test` suites green — also had to
  re-`apt-get install` `bison`/`flex`/`m4`/`clasp`/`minisat` after a container reset had
  silently dropped them, `[[env-integration-tier-deps]]`). **(3) Scope correction (Claas):
  despite (1)'s narrower framing, work TOWARDS the faithful (VLAN admission + rewrite)
  variant as the actual target, not around it — faithful-VLAN variants are IN scope,
  reversing this item's prior "likely out of scope" note. `AD6_PLAN.md` §5.2/§5.3
  updated.**
  **§5.4 (2026-08-21i): staged spike planned** (expressibility synthetic test → tractability
  measurement on real Stanford data, reusing APKeep's own N=2/3/5/16 `--routers` subset
  protocol for a direct comparison). **Stage 0 DONE**: `Ad6Adapter._acl_device`/`_acl_in`/
  `_acl_out`/`_vlan_to_eport` generalized from wl_ifi-only scalars/flat-VLAN-keyed dicts to
  per-device maps — confirmed via `git stash` that the old code silently merged two devices'
  same-numbered VLAN admission groups into one, a real blocker for Stanford's 16
  admission-checked devices independent of VLAN fidelity. New regression:
  `fave/test/test_ad6_adapter_multi_device_acl.py`. No regression: 16/16 fave-side + 10/10
  `ad6 make test`. **Stage A REVISED 2026-08-21j (Claas): the original structural
  entry-point-duplication draft is not a general mutation mechanism — it only handles one
  rewrite per path and blows up combinatorially on a chain (`b=*→1→0→*`), the same failure
  shape as APKeep's BDD blow-up. Replaced with a genuine ad6 CORE extension (a real
  `rewrite` action + SSA-style per-node field copies with frame axioms and phi-joins,
  extending `Instantiator`'s existing per-edge implications) — a deliberate departure from
  this integration's "frontend only" discipline so far, and a genericity-cost finding in its
  own right.** **Stage A DONE 2026-08-21k, GO**: built test-first
  (`ad6/test/core/instantiatortest.py::testMutationChainAndJoinSSAEncoding` — not
  favemodeltest.py as first assumed, this is pure core machinery). New: `GenUtils.action`'s
  `rewrite_field`/`rewrite_value`, `KripkeNode.Rewrites`, `XMLUtils.FieldBitName`/
  `ConvertFieldToVariables`, `Instantiator._CreateMutationConstraints` +
  `InstantiateBase(..., MutableFields=...)` (opt-in, zero regression). A 3-deep rewrite
  chain (`vlan: *→1→0→2`) resolves to exactly 2 (SAT), not 1 or 3 (UNSAT); a join's
  non-rewriting predecessor stays genuinely free (SAT for two different forced values).
  Confirmed failing pre-implementation via `git stash`. No regression: 10/10 `ad6 make test`
  + 16/16 fave-side. Also found and confirmed harmless: a pre-existing order-dependent
  MiniSAT flake in `testCycle`/`testShadow` (present on the unmodified baseline too; `make
  test`'s own invocation is unaffected). §8.5 (new) flags ad6's naive non-Tseitin CNF
  conversion as a candidate general fix if a later stage's numbers show it (not the SSA
  encoding itself) is the bottleneck.
  **Stage B split into checkpointed sub-stages 2026-08-24 (no Stanford↔ad6 translator
  existed at all before this): B0 (plain translator) DONE, GO** — built one from scratch
  (ported from `fave/apkeep/adapter.py`'s own Stanford translator), reusing the already-
  fixed LPM/per-device machinery. Found and fixed two real bugs, both independent of VLAN
  fidelity: (1) multi-port/ECMP forwards were silently truncated to one port (`_out_ports`
  plural fix + `favemodel.py::wire_fanout`, a real OR/multipath Kripke-fanout — NOT "one
  rule per port", which ad6's first-match table semantics would reduce to "only the first
  port ever reachable"); (2) a probe with MORE THAN ONE real topology attachment (confirmed
  48 for one Stanford probe alone) silently checked only the first — found by hop-by-hop
  triage of a real UNSOUND result on the N=2 differential, fixed with `_attachments`
  (plural) + `wire_probe_fanout` (the same fanout idiom, mirrored). Verified on the real N=2
  slice (`bbra_rtr,rozb_rtr`, the same subset APKeep's own measurement uses) against a LIVE
  NetPlumber worker: exact match, 0 over/under-approximation. New:
  `fave/test/test_ad6_wl_stanford_plain.py` (9 unit + 2 structural/differential tests,
  confirmed failing pre-fix via `git stash`). No regression: 10/10 `ad6 make test` + 16/16
  fave-side.
  **B1 (2026-08-24): scaled to all 16 routers — found a real generator dead-port-gating bug
  (fixed, `_is_admitted`/`GenFirewallDeadPortGateTest`) AND, underneath it, a genuine
  PRE-EXISTING ad6 CORE soundness gap, orthogonal to VLAN fidelity: `Instantiator.
  InstantiateEndToEnd`'s reachability query is unsound for any topology with a cycle (proven
  in a minimal, zero-Stanford-code repro,
  `testCycleReachabilityIsUnsoundWithoutRealOrigin`) — a node in/downstream of a cycle of
  mutually-satisfiable transitions is "reachable" from ANY source, real connection or none.
  wl_ifi/wl_up's topologies are acyclic, so this never surfaced before; Stanford's real
  backbone has genuine redundant inter-router links. This gates the PLAIN target too, not
  just VLAN fidelity — bigger than anything Stage A2/B2/B3 anticipated. STOPPED here,
  reported to Claas rather than attempting core surgery unprompted (same discipline as the
  wl_up NO-GO): open options are (a) a real core fix (rank/distance variable, its own gated
  stage), (b) NO-GO on exact-match Stanford/i2 via ad6, or (c) an unidentified narrower
  mitigation. Full writeup: `AD6_PLAN.md` §5.4.**
  **B1 follow-up (2026-08-25): the core fix (option (a)) was built, test-first, and IS
  correct — but the resulting exact wl_stanford differential is a NO-GO on wall-clock
  grounds.** Claas's own proposal (reuse `_CreateCycle`, negated) was assessed and
  empirically disproven first (no discriminating power negated; a non-CNF structure
  `ConvertToCNF` can't consume unnegated). CEGAR (`SolveGroundedEndToEnd`) is correct but
  combinatorially intractable on real data (117 iterations/~45s for one query); shrinking
  the blocking clause to Destination's own backward closure helped ~0% (that closure is
  ~100% of the graph on real FIB-heavy data). A static rank/distance encoding
  (`_CreateAcyclicConstraints`) is genuinely sound (found+fixed a real
  `SATUtils._ResolveConstants` nested-equality bug along the way) but unscoped costs ~425k
  extra clauses for 3 routers; SCC-scoping (`_ComputeSCCs`, Kosaraju's) is correct but only
  cuts ~43%, because the non-trivial SCC covers **86% of nodes** even at 3-router scale
  (redundant backbone links pull a whole router's fallthrough table into one SCC — the norm
  for a resilience-engineered network, not a corner case). Shipped: a lazy/hybrid design
  (`SolveAcyclicEndToEnd`) that only escalates to the (cached, SCC-scoped) rank constraints
  when a plain solve's witness is ungrounded — verified ZERO cost for every acyclic
  benchmark (wl_ifi 289/289 fast-path). **Real-scale result, measured**: a full,
  instrumented 256-query/16-router run given a 6-hour budget did NOT finish — 74/256
  (28.9%) done, 40 escalated (7.7s–2,923s each, ~99.4% of the budget), zero errors.
  **PRIMARY finding (high confidence): does not complete within 6 hours.** A linear
  extrapolation suggests ~20-21 hours (SECONDARY, lower confidence — not independently
  measured). **Decision (Claas): the 6-hour non-completion IS the reportable NO-GO result**
  for the tool-comparison writeup — not re-run to completion ("revealing the inability to
  scale is a genuine outcome"). `test_ad6_wl_stanford.py`'s differential test now skips by
  default (`AD6_STANFORD_FULL_DIFFERENTIAL=1` to opt in). The underlying core bug IS fixed,
  generically, for any topology, on the `InstantiateEndToEnd`/`SolveAcyclicEndToEnd`
  primitive `fave_bridge.py` actually uses — kept as ad6's production query path — even
  though the exact full Stanford differential is impractically slow at this scale. **Scope
  caveat, found by a parallel session (`AD6_ENCODING_PLAN.md` §2.4):** the same grounding
  gap also confirmed to affect ad6's own `InstantiateReach`/`InstantiateShadow` (suspected
  in `InstantiateCross`) — none fixed here; `InstantiateCycle` is confirmed safe. No
  regression: `ad6 make test` (10 suites) + 27/27 fave-side ad6 tests green. Full writeup:
  `AD6_PLAN.md` §5.4, `ad6/FAVE_CHANGES.md` §20.**
- [x] **Algorithmic lever (§6) — CONFIRMED empirically 2026-08-24/25, no longer optional/deferred.** A parallel investigation (`AD6_ENCODING_PLAN.md`, `ad6_encoding_bench/`) answered §6's "if it works" question directly against the real wl_up model and its full 11,902-query `cchecks.json`: assumption-based incremental solving over one shared base collapses ad6's O(n²) query cost to near-flat, ~100–490× faster depending on solver family (Z3: ~100–140×, ad6's own Minisat via PySAT's native API: ~490×), exact-match-correct throughout, and the win survives genuine cross-source variation (not just fixed-source flooding) and holds at wl_up's real scale, not just synthetic. **Separately, tracing the real production call path found the per-query cost isn't (as first assumed) CLI-subprocess-vs-library — `fave_bridge.py` already calls `pycosat` (a native library) — it's `Instantiator.InstantiateEndToEnd`'s `deepcopy()` of the entire base CNF tree plus a full from-scratch DIMACS renumbering, both in pure Python, on every single query**, independent of solver choice; caching the base DIMACS mapping once per run and converting only each query's small delta is a smaller, lower-risk, backend-preserving step available before any full incremental-solver adoption. **2026-08-27 follow-up: the lever also rescues the Stanford/i2 wall-clock NO-GO (§5.4's B1) for the primitive tested.** Baking the same SCC-scoped rank constraints B1's escalation path uses into a persistent incremental solver's base once, then answering all 256 real Stanford source→probe pairs as single assumption-checks, completed the entire real all-pairs matrix in ~16.2 minutes (971.09s) — vs. B1's own measured 6-hour/28.9%-complete result and ~20-21h extrapolation. 0 mismatches against ad6-real's own answers, including on the two specific pairs already known to be the expensive ones (2164.64s/2259.70s under ad6-real → ~102.7s/~0.15s here, the second nearly free from clause reuse). Getting there also surfaced an unrelated, still-open bug: `SolveAcyclicEndToEnd`'s escalation path can silently segfault (C-stack overflow from `sys.setrecursionlimit(10**6)` + the shell's default 8MB `ulimit -s`) — `fave_bridge.py` runs as a subprocess inheriting its parent's ulimits, so any real cyclic-topology run is at risk of this. **2026-08-27: applied to production.** `ad6/src/solver/incremental.py` (`IncrementalSession`) replaces `fave_bridge.py`'s per-query solve with one persistent PySAT/Minisat22 session, rank constraints baked in unconditionally (sound by construction, no CEGAR needed). New dependency `python-sat` (Dockerfile, pinned `1.9.dev15`). Verified via `ad6 make test` (10 suites) + 36 real fave-side ad6 tests (wl_ifi/wl_ifi_stateful/wl_up/lpm_prio/multi_device_acl/wl_stanford_plain incl. a real N=2 live-NetPlumber differential), all green through the real `Ad6Adapter`→subprocess→`fave_bridge.py` path — wl_ifi's full 219-pair run: 0.81s. Also fixed a pre-existing environment gap (missing `liblog4cxx.so.15`) that was silently skipping the project's only live-NetPlumber ad6 differential test. **Full Stanford differential CLOSED**: all 256 real source→probe answers run through `test_ad6_wl_stanford.py`'s own live-NetPlumber oracle-comparison logic (`ad6_encoding_bench/axis8d_stanford_netplumber_diff.py`) — EXACT MATCH, 0 diffs across all 16 roles. Full findings/methodology: `AD6_ENCODING_PLAN.md` §§3.4–3.10; harness: `ad6_encoding_bench/`.
- [ ] **Write-up (§7).** "Price of genericity" section (two-factor decomposition, scaling curves, crossover analysis), expressiveness table, and the BDD-APKeep phase-split bridge figure — kept **separate** from the clean 3-engine reachability comparison.
- [~] **Architecture & design review (§8, deferred until wl_up + ideally Stanford/i2 work).** Claas, in hindsight: probably would not choose XML as ad6's primary data structure (config AND the SAT-formula AST share one generic `lxml` tree type, no type safety between them). **The two known core bugs are now FIXED (2026-08-21), test-first, ahead of the rest of this review** — Claas asked for proper fixes rather than leaving them as documented workarounds. `ConvertCIDRToVariables` now returns `constant()` for a `/0` prefix instead of an empty (silently-broken) conjunction (`ad6/FAVE_CHANGES.md` §7). `_CreateInitConstraints`'s chained-XOR turned out to be far more broken than first diagnosed — a brute-force sweep found only the very first pair of marked-INIT transitions was ever correctly mutually-excluded for any N>3, not just "the last few of >16" — fixed by replacing the chain with the same direct pairwise encoding the N∈{2,3} case already used correctly (§8). Both have dedicated regression tests (`ad6/test/xml/xmlutilstest.py`, `ad6/test/core/instantiatortest.py`, new `ad6/test/core/initconstraintstest.py`) confirmed failing before the fix. `fave_bridge.py`'s per-query exclusivity workaround is removed (verified redundant). Remaining review scope (still deferred): XML-vs-typed-AST, test coverage for the XMLUtils/SATUtils/Instantiator layer more broadly, and the frontend/backend seam now that two frontends exist.

### 14. wl_ifi's self-checks — RESOLVED on the `ai` branch, my fix was the wrong one (2026-09-18)
**Closed by `8a4f9c85`/`7706daae`/`6be4f712`, not by the work that logged it.** Recorded because the wrong turn is the instructive part.

**What I saw:** `bench/wl_ifi/benchmark.py` passed `--roles` to `reach_csv_to_checks` and `test/gen_wl_ifi_inputs.sh` did not, so the two produced different ground truth for the same workload — 70 reachable pairs against 54, 315 checks against 299 — and since `reachable.json` is gitignored, whichever ran last silently won. Running the smoke tier therefore made the *next* fast tier fail four ad6 gates.

**What I concluded, and it was wrong:** that the 70-pair oracle was intended (a subnet role's self-rule is a real compliance question), so the generator should pass `--roles` and the tests should stop discarding self-pairs. Committed as `d6718a44`, reverted as `048b50f6`.

**What is actually true:** those 16 self-checks assert *"reachability nobody wrote"*. The self-check fix is only sound for a **strict** matrix, because loose mode injects a diagonal for every atomic role — and wl_ifi runs loose with sixteen subnet roles, so it picked the injected diagonal up as positive assertions. The fix is to carry the mode across the boundary (`--strict` on `reach_csv_to_checks`, threaded from `generic_benchmark` and `gen_wl_up_inputs.sh`), which is what the `ai` branch did. wl_ifi is 299/54 again, with 54 reachable pairs and no self-pairs.

**The lesson, which is the same one `APKEEP_BACKEND.md` Sec. 10 draws:** every rule that reads meaning out of a policy matrix is reading an artifact whose provenance was discarded upstream. I had four red gates and two plausible readings of them, and picked the one that made the red go away instead of the one that explained where the assertions came from. The gates were right.

- [x] The two generation paths agree again — both go through the strict-aware `reach_csv_to_checks`.
- [x] **`fave/test/test_wl_ifi_policy_artifacts.py` — ADDED 2026-09-19**, the sibling of wl_up's. It pins two things: that the TRACKED `reachability.csv`/`reachability_stateless.csv` are what their FPL sources produce (wl_ifi's matrices are tracked inputs AND the benchmark regenerates them, so drift between the two paths is exactly how the 299/315 split hid), and the loose-mode invariant itself — a loose matrix fills every one of the 17 diagonals with `X`, and **must still yield no self-check, positive or negative**. It also asserts the benchmark's `--roles` invocation and the shell generator's `--roles`-less one produce identical artifacts, which is the divergence detector proper.

  **Verified by mutation, not by passing.** Removing the `args.strict` gate from `keep_self` — i.e. reintroducing the regression — turns three of the six red, including the path-divergence test. Perturbing one cell of the tracked matrix turns the first one red. Both mutations reverted and the files confirmed identical to HEAD.

  `ai`'s second fast pass at the end of `./test.sh all` (`314c3771`) catches the *symptom* (stale artifacts asserted on); this catches the *cause*, and the pattern now exists twice, so it generalises to any workload with generated ground truth.

---

### 13. `-o` in a FORWARD rule is inert: the packet filter chains before it routes (found 2026-09-18)
**Found by the new complement check on its first run** (item 12 / [`CLOUD_BENCH_PLAN.md`](CLOUD_BENCH_PLAN.md) §1.9.3), which is a fair argument for that check: it exposed a modelling infidelity in the *smallest* workload in the suite, one that had been invisible because nothing ever asked "and nothing else".

**The finding.** `devices/packet_filter.py` wires the pipeline `forward_filter -> routing -> post_routing`. The FORWARD chain therefore runs BEFORE the routing decision, when the packet's `out_port` field is still wildcard. A rule matching `-o <iface>` does not fail there -- it NARROWS the header space -- and the routing table then *writes* `out_port` (`post_routing`'s own comment: "forward packets according to out port field set by the routing table"; [`AD6_PLAN.md`](AD6_PLAN.md) §9.10.2 puts it the same way from ad6's side: "a decision written by one rule (`Rewrite(out_port=...)` in `routing`) and READ by a later rule in the same device"). The narrowing is overwritten, so **the `-o` match constrains nothing**.

Linux is the other way round -- netfilter routes *before* the FORWARD chain, which is exactly what makes `-o` meaningful there.

**Measured, with a controlled experiment.** wl_example's `pgf-ruleset` implements `Office <->> Internet` as `ip6tables -A FORWARD -o 1 -s 2001:db8::200/120 -j ACCEPT` -- out **port 1, the internet port**. With the complement check on, `office -> dmz` reports **261 violations** (253 naming `dport`, 8 naming `proto`): office reaches the DMZ on essentially every port and protocol, though the policy permits only HTTP and SSH. `rulesets/violation-ruleset` differs from `pgf-ruleset` in exactly that line, commented out; re-running with it drops the count to **0**, leaving only the two `Office <->> Internet` failures that ruleset exists to demonstrate.

**Direction of the error depends on the target**, so both over- and under-approximation are reachable from this one cause:
- `-o X -j ACCEPT` over-PERMITS (accepts traffic leaving other ports) -- wl_example.
- `-o X -j DROP` over-RESTRICTS (drops traffic leaving other ports) -- wl_up.

**Blast radius, measured by running the parser over every ruleset** (an earlier figure here said "wl_tum 1 of 2" -- it came from a grep for `ip6tables` and missed the IPv4 ruleset entirely):

| workload | rulesets refused | note |
|---|---|---|
| `wl_example` | 1 of 2 | `pgf-ruleset` -- breaks the **smoke** tier |
| `wl_up` | 1 of 139 | `pgf.uni-potsdam.de-ruleset`, the gateway firewall |
| `wl_tum` | **2 of 2** | `tum-ruleset` alone carries **3,286** `-o` rules |
| `wl_ifi`, `wl_generic_fw` | 0 | use no `-o` |

**wl_tum's are only PARTIALLY inert, and that matters given the count.** They are all of the form `-o eth1.110 -i eth1.152 ...`, and `iptables/generator.py` turns a VLAN-qualified interface into *two* things: an `out_port` field (inert, per above) **and** a `dvlan` match. `dvlan` is an ordinary header field that routing does not overwrite, so the egress VLAN stays constrained and only the port half is lost. Whether that is equivalent to the intended restriction depends on whether VLAN and egress port are 1:1 in these models -- **not established**. So wl_tum is blocked on 3,286 rules whose practical infidelity may be small, which is an argument for softening the refusal (see below) rather than for keeping wl_tum unrunnable.

`-i` matches are unaffected: the ingress port IS known when the chain runs.

- [x] **REFUSE it loudly — DONE 2026-09-18** (Claas's call). `iptables/generator.py` raises `OutInterfaceUnsupported` for an `-o` match in any filter chain, naming the device, the chain, the offending rule verbatim, why the model cannot represent it, and which direction the error would have gone. `fave/test/test_iptables_out_iface.py` (integration tier, needs pybison). Silently modelling it as no constraint was the worst of the available options; this is the honest interim, **not the fix**.
- [x] **`FAVE_ALLOW_OUT_IFACE=1` opt-out — DONE 2026-09-18** (Claas's call), because the refusal alone stopped three workloads: wl_example (smoke tier), wl_up and wl_tum (bench tier). Set it and the `-o` match is modelled exactly as the old code did — as NO CONSTRAINT — so the override restores the previous behaviour rather than some third thing. It is announced ONCE PER DEVICE on stderr, with a count, because wl_tum's `tum-ruleset` alone carries 3,286 and a per-rule warning would bury the run it is meant to qualify:

        [iptables] pgf: 1 `-o` match(es) modelled as NO CONSTRAINT because
        FAVE_ALLOW_OUT_IFACE is set. This device's filter chains run before
        routing, so the egress restriction is not represented: results are
        over-permissive where the rule ACCEPTs and over-restrictive where it
        DROPs. See TODO.md item 13a.

  An exported-but-empty value, `0`, `false`, `no` and `off` do NOT count as opting in — an empty exported variable is a common accident and must not silently re-enable a known infidelity. Verified: wl_example runs green again with it set. **This exists to be deleted — see item 13a.**

### 13a. The faithful fix: route BEFORE the filter chains -- and why it is not small
**This is what item 13 should eventually do**, and the refusal above is only a placeholder for it.

**Why reordering is the faithful answer.** In netfilter the routing decision happens *before* the chain that can match on egress, in both directions:

    forwarded traffic:  prerouting -> ROUTING -> FORWARD -> postrouting
    local traffic:                    ROUTING -> OUTPUT  -> postrouting

so by the time either chain runs, the egress interface is decided and `-o` means what it says. FaVe's `devices/packet_filter.py` wires it the other way round:

    (node + ".pre_routing_forward", node + ".forward_filter_in"),
    (node + ".forward_filter_accept", node + ".routing_in"),
    (node + ".internals_out",  node + ".output_filter_in"),
    (node + ".output_filter_accept", node + ".routing_in"),
    (node + ".routing_out", node + ".post_routing_in")

Routing is *downstream* of both filters. Putting it upstream would make `out_port` a real, readable field during filtering -- exactly the property that makes `-o` expressible -- and would also match the mental model a reader brings from iptables.

**Why it is not trivial, and the OUTPUT chain is the reason.** The single `routing` table is shared: `forward_filter_accept` and `output_filter_accept` both feed `routing_in`, and `routing_out` is the only path to `post_routing`. Moving routing before the filters therefore cannot be done for the forward path alone -- **the output path depends on routing in exactly the same way**, so a reordering has to give routing two upstream entry points (`pre_routing_forward` and `internals_out`) and let both filtered paths converge on `post_routing` afterwards. That is either a duplicated routing table per path, or a re-wiring in which one table is entered twice from different predecessors; NetPlumber tables are per-device singletons, so the two are not interchangeable.

Three further consequences to work through:
- `post_routing` currently does two jobs -- dispatch by the `out_port` field, and the hairpin drop (`in_port == out_port`, "do not send a packet back out the interface it arrived on"). With routing moved earlier, the dispatch half stays but the field it reads is written further upstream.
- The `routing` table's `Rewrite(out_port=...)` becomes an *input* to filtering rather than its output, which inverts the dependency `AD6_PLAN.md` §9.10.2 describes ("written by one rule ... READ by a later rule in the same device") -- and that section is about whether ad6 can express the read at all, so the ad6 translation has to be re-checked against the new order.
- **Every packet-filter result could change**, so wl_example, wl_up and wl_tum all need re-validation afterwards, and any archived number computed from them is suspect until they are. wl_tum especially: 3,286 rules currently carry an inert `-o`.

**THE OPT-OUT IS PART OF THIS ITEM'S DEFINITION OF DONE.** `FAVE_ALLOW_OUT_IFACE` exists only because `-o` is currently inexpressible. Once routing precedes the filter chains, an `-o` match becomes a real constraint on a field that is already set when the rule runs — there is then nothing to refuse and nothing to override, and **both the refusal and the opt-out should be deleted** rather than left as vestigial switches that a later reader would have to reverse-engineer. Leaving an override in place for a limitation that no longer exists is how a workaround becomes folklore.

- [ ] Decide whether to do it, and if so re-validate the three workloads against their previous results before and after.
- [ ] If done: delete `OutInterfaceUnsupported`, `_out_iface_allowed`, `_count_out_iface`, the stderr notice, `FAVE_ALLOW_OUT_IFACE` from every caller and CI job, and `fave/test/test_iptables_out_iface.py` — replacing the last with a test that `-o` now CONSTRAINS, which is the property worth pinning once it holds.
- [ ] **Re-examine wl_up's DROP rule** specifically -- an over-restrictive drop produces false "does not reach" results, which is the direction that looks like a correct verdict.

---

### 12. Benchmark-suite extension: the NoD cloud dataset + the Delta-net traces — PLAN (see [`CLOUD_BENCH_PLAN.md`](CLOUD_BENCH_PLAN.md))
**STATUS 2026-09-18 — `wl_cloud` BUILT AND GREEN on NetPlumber; the suite has an external oracle for the first time.** Two third-party datasets arrived untracked (`cloud_bench.tar.bz2`, `deltanet-NSDI17-dataset.tar.gz`). Scope decided by Claas: the `cloud/base` scenario only, and from Delta-net only the two `*-only-inserts.csv` (2.4 MB of 40 GB — `airtel2.csv` at 16 GB and `inet.csv` at 14.4 GB are each larger than the box's free disk, so the scoping is physical, not stylistic). **The archives are not kept** (2026-09-18): both datasets' in-scope parts are vendored EXTRACTED into the repository (`wl_cloud/cloud-tf/`, `wl_deltanet/deltanet-traces/`), each with a `SHA256SUMS`, and git is what reveals a change to them. No script extracts from an archive; there is deliberately no live-extraction path.

**Why the cloud dataset earns its place.** It closes two gaps at once. (1) **An external oracle.** It ships six Z3-Datalog reachability instances, each labelled sat/unsat in its own filename by a tool that predates this tree by a decade — and item 1s plus `AD6_PLAN.md` §9.28 both record that *every* correctness result here is otherwise a consensus between implementations in this repository. (2) **Header rewriting.** Its 28 `rw` rules are NAT on an ADDRESS field; no existing workload rewrites one, and rewriting is where HSA, AP/BDD and a SAT encoding diverge in cost.

**The model had to be derived, not read.** The dataset states forwarding as node-to-node rules with no interfaces and no `link$` lines, and its 128-bit match string orders its fields *differently* from `wl_stanford`'s with nothing declaring it — while agreeing on where `ipv4_dst` sits, so a wrong layout still produces plausible forwarding and goes wrong only on the ACL and NAT fields. Both the layout and the node taxonomy were measured (bit-density profile; in-/out-degree census) and are pinned by tests, because the derivation reproduces the generator parameters in the dataset's own README exactly — 5 datacenters, 8 leaf routers each, 30 hosts per leaf — while the `.tf` file states none of them. `fave/bench/wl_cloud/`, 46 new tests.

**Result: 6/6 oracle verdicts reproduced on NetPlumber, zero violations** — and verified non-vacuous rather than asserted: earlier runs of the same pipeline reported violations, all six checks are present, and a deliberate mutation of one expectation produces exactly one violation naming it.

**Three defects found in SHARED code, each invisible until a differently-shaped workload arrived.** (a) `netplumber/adapter.py` resolved a declared table index with `name.rstrip('.1')` — a CHARACTER-set strip that ate the separator and then chewed into the device name, so `lin.dc0_leaf1.1` became `lin.dc0_leaf` and raised `KeyError`; no existing workload names a device ending in `1`. (b) `bench/compliance_checker.py` hardcoded `negated=False` on every field condition, so a check could negate its reachability but never a field value. (c) **worst of the three:** with (b) fixed, `_create_compliance_rules` still built its condition with `_build_vector`, which never reads `RuleField.negated` — so "on any port other than 331" was checked as "on port 331", and the violating flow it reported carried `dport=331`, the very value being excluded. The adapter already had `_expand_negations`; the compliance path just never reached for it. All three fixed test-first; (c) now expands the complement and **refuses** a negated condition on a must-reach check rather than approximating it. This is items 1i/1n/1p's swallowed-sub-step pattern in its most expensive form: the step ran, produced a verdict, and answered a different question.

**Latent trap, NOT fixed (needs a provenance decision):** Hassel applies a rewrite as `(h & mask) | rewrite`, so mask `0` marks the replaced bits — which is what `wl_stanford/stanford-tfs/*.tf` carries. But `np_preparation._get_rewrite` tests for mask all-ONES, and the committed `stanford-json/*.tf.json` carries inverted masks. The two agree, so **no current result is wrong**; the trap is that the JSON cannot be regenerated from the `.tf` beside it — doing so turns `['vlan:2']` into `['tcp_flags:0','tcp_dst:0','tcp_src:0','ip_proto:0','ipv4_dst:0.0.0.0/32','ipv4_src:0.0.0.0/32']`, every field zeroed except the one actually rewritten.

**Cross-backend (C6) — both other families fail, in informative ways.** **ad6 REFUSES the workload**, correctly and loudly: a field that any rule rewrites must use its integer-valued mutable `fieldmatch` everywhere, and the cloud model both rewrites `ipv4_dst` (NAT) and matches it with 1,668 non-/32 prefixes. That is a structural encoding boundary reached by a workload rather than by argument — it belongs in `AD6_PLAN.md` §7's expressiveness table, and whether it is removable (ad6's `<port>` text already accepts `value/prefix`) is an owner decision. **APKeep under-approximates by 3**, dropping every reachable pair — a violation of the soundness gate `bench/apkeep_convergence.py` states in its own docstring. Diagnosis: `apkeep/adapter.py` still reconstructs meaning from FaVe's device NAMES (`in.`/`mid.`/`out.` in eleven-plus places, the internal/external link decision among them, and a literal `self._stanford = any(d.split('.', 1)[0] == 'mid' ...)` sniff at line 793), so wl_cloud's `core.`/`lin.`/`lout.`/`gw.` devices get their rules captured but never get an inter-device topology. That a NAT-free host-to-host query also fails is what rules out "APKeep cannot do NAT". **This is the same defect class `AD6_PLAN.md` §9 spent a whole phase deleting from the ad6 adapter, still live in APKeep** — found in a day by a workload that simply names things differently.

- [x] **Dataset assessment + scope decision (CLOUD_BENCH_PLAN.md §0-§2).** Owner decisions 2026-09-18: cloud oracle-first then matrix; Delta-net static-snapshot-first; extract only the two only-inserts traces; keep the source tarballs.
- [x] **Reproducibility: the whole chain is scripted (CLOUD_BENCH_PLAN.md §1.8).** Owner principle, and wl_cloud did not meet it as first built -- `oracle.json`, the artifact the entire result rests on, was transcribed BY HAND from `grep` output. Now: the raw `cloud/base` scenario is vendored whole (6.7 MB, 9 files, exactly as shipped) under a `SHA256SUMS` the run verifies BEFORE deriving anything; `oracle.json` is derived from the six `.smt2` instances by `cloud_oracle.py` (argument order read out of each file, not assumed; anything not fully understood refused rather than half-parsed) and is no longer tracked; `fave/test/gen_wl_cloud_inputs.sh` rebuilds every input, and `--from-archive` re-extracts and re-verifies against the archive (run: the vendored copy is byte-identical). Every run now stamps `eval/<engine>-<utc>.json` with the engine, its options, the model census and **the sha256 of each .smt2 its verdicts came from**. Retroactive check of the hand-written oracle against the derivation: identical on all six queries -- right answer, wrong order.
- [x] **C1-C5 `wl_cloud` built and green on NetPlumber** (`fave/bench/wl_cloud/`, `fave/test/test_cloud_{tf,preparation}.py`, `test_compliance_check_parsing.py`, `test_adapter_compliance_conditions.py`).
- [~] **C6 cross-backend.** NetPlumber only. ad6 refuses (structural); APKeep unsound (name coupling). Both written up; neither fixed.
- [x] **C7 express wl_cloud as an FPL policy — DONE 2026-09-21, by BOTH routes (CLOUD_BENCH_PLAN.md §1.9).** The workload now goes through PolicyTranslator twice over, and the two runs are different kinds of evidence: the ORACLE phase states the dataset's six questions as five FPL rules over a fabricated inventory, and the MATRIX phase states the dataset's own 26x26 ACL matrix. They were built in parallel and met at the merge; each is kept because each answers something the other cannot — the oracle carries third-party verdicts and nothing else does, the matrix asks 4,224 questions and found three facts no oracle query probes (item 16).

      **The oracle route.** Five rules over a fabricated eight-role inventory, compiled with `reach_csv_to_checks.py --complement`, 71 checks. **6/6 oracle verdicts still reproduced on NetPlumber** (CLOUD_BENCH_PLAN.md §1.7.1) — unchanged across the switch, which is what makes it a reformulation rather than a new result. q06 reproduces BY the violation its rule predicts, q04 by the complement term. The 65 self-derived expectations are stamped SEPARATELY and never summed: 56 violated, almost all of them the unconditioned cross-pair denials our fabricated default-deny generates (hosts in this datacenter reach each other freely, which the dataset never claimed otherwise). **Every internet-facing complement HELD** — "these services and nothing else" is true at the perimeter for all three internet-sourced rules, the half of a conditional permission F3 added and which no workload had yet been able to check. New: `cloud_endpoints.py` (an FPL role names ONE derived endpoint; the `_tx`/`_rx` pair folded by `node_name`'s own arithmetic, the internet by hand since its gateway is a device) and `cloud_provenance.py` (pairs each `.smt2` with the one check that asks its question and REFUSES if any query is carried by none or several — closing the vacuity the hand-built set had, where a check that went missing still counted as agreement). 26 new tests, 6 mutations all caught. **Found on the way, and FIXED 2026-09-21:** `policy_builder`'s `comment_pattern` was `[ \t]* \# [ \t]* .*`, whose second quantifier overlaps `.*` — the same language, but one extra way to match every comment line, so a run of them before a definition cost 2^n (20 lines 2.1s, 24 lines over two minutes; blank lines made it worse, not better). Redundant quantifier deleted; the same overlap one line lower (`[ \t]* = [ \t]*` against a space-containing `value_pattern`, doubling per attribute line) made possessive, since that one is load-bearing for the captured value. **All seven committed inventory/policy pairs compile byte-identically**; one pathological input changes meaning under test (`key =   ` with an all-blank value is now a syntax error rather than a value of one space). Guards run the parse in a subprocess with a hard deadline — an in-process budget cannot fail here, it hangs, and a signal handler does not interrupt a C-level regex. wl_cloud's FPL files are documented in full again. Original rationale: **C7 express wl_cloud as an FPL policy** — the 26x26 ACL matrix AND the six oracle queries — so it goes through PolicyTranslator like every other workload instead of hand-built checks (owner direction 2026-09-18). Fabricating an inventory (a role per endpoint host with its /30, a service per port) has no real-world counterpart but buys one fewer benchmark-specific transformation, a workload that exercises FaVe's POLICY layer and not just its engine, and the `reachable.json`/`cchecks.json` that `apkeep_convergence.py`, `apkeep_tum_diff.py` and `i2_structural_oracle.py` consume — wl_cloud produces neither today, which is why §1.7.3's APKeep under-approximation had to be reported by hand. **Design point (Claas):** a policy is an INTENT, not a fact, so the oracle becomes policy + an expected verdict per check — wl_ifi is the precedent, reporting 27 violations under `<->>` and none under `<-->` on the same data plane. For cloud, q06 is the expected violation and the rest are satisfied. **Every expectation must be labelled by provenance**, because only six come from the `.smt2` files and the rest are self-derived. **F1, F2 and F3 all IMPLEMENTED 2026-09-18 (CLOUD_BENCH_PLAN.md §1.9):**

      **The matrix route.** The premise changed and that is the headline: §1.9.4 costed a FABRICATED inventory at ~54 self-derived expectations of 60, and none of it was needed. `cloud-tf/README.txt` IS an inventory and a policy — 25 services with prefixes and a 26x26 authorisation matrix over them — and matrix index 25 is the Internet, **confirmed from the data** by four independently derived sets that coincide exactly (matrix row 25, the 43 source-less ACL rules, the 19 gateway DNAT rules, the 14 core SNAT rules). So the roles, the services and the policy are all the dataset's; only the endpoint NAMING is ours. `cloud_readme.py` parses the matrix mechanically (§1.9.5's first question, answered the only way §1.8 allows), `cloud_policy.py` emits the FPL, and the workload now produces the `reachable.json`/`cchecks.json` the convergence scripts consume. **26 roles over 65 (service, leaf) endpoints, 215 rules, 4,224 checks.** Operators: two `--->` per service pair (the data plane has two rules, each pinning its own dport) and `<-->` for the Internet pairs (inbound DNAT on dport, outbound SNAT on sport) — **so F1 and F2 are both load-bearing, which is what C7 was waiting on.** Two policies (owner decision): `reach.txt` reports **1,315** violations and `reach_public.txt` **3**. **The 1,312-violation delta was predicted exactly before the run** and is the finding — the generator implements "the Internet may reach service j" as an ACL rule with no source constraint, so all 11 public services are reachable from all 26 roles while the matrix authorises 102 of 286 such cells. The matrix's PRIVATE half is enforced exactly (113 1-cells, 113 rules, set-equal both ways), which is what makes the public gap a property of the generator rather than of the reading. **The remaining 3 are a real finding, not fixed** — see item 16. **A claim of this half that the merge disproved:** it read that the six oracle queries would stay as they were, because expressing them as FPL meant fabricating host roles overlapping the service roles. They were expressed, with eight roles, in the parallel session — the overlap is avoided by keeping the two phases in separate directories rather than by not doing it, and `bench/wl_cloud/matrix/` is where that lives. Superseded by the above: the original text — the 26x26 ACL matrix AND the six oracle queries — so it goes through PolicyTranslator like every other workload instead of hand-built checks (owner direction 2026-09-18). Fabricating an inventory (a role per endpoint host with its /30, a service per port) has no real-world counterpart but buys one fewer benchmark-specific transformation, a workload that exercises FaVe's POLICY layer and not just its engine, and the `reachable.json`/`cchecks.json` that `apkeep_convergence.py`, `apkeep_tum_diff.py` and `i2_structural_oracle.py` consume — wl_cloud produces neither today, which is why §1.7.3's APKeep under-approximation had to be reported by hand. **Design point (Claas):** a policy is an INTENT, not a fact, so the oracle becomes policy + an expected verdict per check — wl_ifi is the precedent, reporting 27 violations under `<->>` and none under `<-->` on the same data plane. For cloud, q06 is the expected violation and the rest are satisfied. **Every expectation must be labelled by provenance**, because only six come from the `.smt2` files and the rest are self-derived. **F1, F2 and F3 all IMPLEMENTED 2026-09-18 (CLOUD_BENCH_PLAN.md §1.9):**
  - [x] **F1 `provider` was an OR operand instead of a qualifier — FIXED.** It is the DIRECTION MARKER (`to_iptables`: `" --sport " if provider == from_ else " --dport "`), so F1 and F2 were one defect: appended as its own OR operand it leaked `provider:` into the CSV, stopped `to_iptables` ever choosing `--sport`, and forced F2's reverse-role lookup. Merged into the service condition; service now looked up on the provider. Original symptom: `policy_builder` attaches `{"provider": role_to}` and `add_reachability_policy` appends the service attributes as a SEPARATE condition — i.e. an OR operand — so `HostA ---> HostB.S350` compiles to `(provider:HostB|protocol:tcp;port:350)`, read as "provider is HostB OR tcp/350". `reach_csv_to_checks` emits it verbatim and `compliance_checker` dies with `KeyError: 'provider'`. No workload exercises this path today; four of the six proposed rules use it.
  - [x] **F2 `<-->`'s backward direction now SWAPS the service — FIXED.** `Policy._condition_to_csv` resolves direction where both role names are in scope (`port` towards the provider, `sport` away), drops the marker, and `sport`/`dport` were added to `OXM_FIELD_TO_MATCH_FIELD`. Six-rule `<-->` policy compiles, 56 checks all parse, no `provider`. No existing workload changes — wl_example/wl_ifi/wl_up matrices regenerate byte-identical. Original report: Owner specification: `A <--> B.S` yields forward A->B with S's attributes forward (`proto=tcp, dport=80`) and backward B->A with them REVERSED (`proto=tcp, sport=80`). The implementation passes `service_to` backward verbatim, so it asks for `dport` again and looks the service up on the reverse role — hence `Fehler: Service Internet.S332 unbekannt.` `--->`/`<-->` are far less exercised than `<->>`, which likely explains both this and F1. **Measurement corrected:** a first pass tested the backward direction with `dport=350` and wrongly concluded `<-->` was unusable — that measured the bug, not the semantics. With `sport=350` the backward direction IS reachable, so `<-->` holds for q05 and is the right operator for stateless TCP ACLs. `--->` stays wrong: its backward denial is unconditional and the unconstrained reverse direction is reachable (on 332, dc1_leaf6's only published port). **The `Internet` role now offers every DECLARED service (done 2026-09-18, `policy.py` `INTERNET_ROLE`, 12 tests):** reading (a), chosen because a service's conditions come from its inventory entry and never from its name — under "anything at all" the attributes could only come from well-known-name defaults, so HTTP would always mean 80 and a custom service could not be expressed. Measured: `host2 <->> Internet.*` goes from `X` to `(protocol:tcp;port:331|...332|...350|...351)`, and `Internet <--> host20.S332` compiles where it used to raise. Inert for existing workloads (nothing names a service on the Internet side or uses a wildcard). **But it was NOT the whole fix, as checked before implementing:** `Policy.default_roles` gives Internet an `interface` attribute and no services, and `offers_service` has no special case — but implementing "Internet offers everything" would not help, because `host2 <--> host1.S350` fails identically with no Internet in the rule. The backward call validates `service_to` against the original SOURCE role, and a service belongs to the server side. **Scope, precisely:** `--->`/`<-->` are fine WITHOUT a service (`cond` is None, no lookup) — that is the production form, `wl_up/reach.txt` `Internet <--> DMZPublicServers` and `wl_ifi/reach_stateless.txt` — and it is the service-carrying form of both operators that is wholly unexercised, with both defects on the one `if service_to` path. Remaining: implement the swap, then decide `<-->` vs `<->>` — `<->>` needs no fixes at all but asserts stateful return traffic the stateless cloud ACLs do not provide (the wl_ifi pattern, where the violations are the finding).
  - [x] **Inventory built, compiled and COMMITTED (CLOUD_BENCH_PLAN §1.9.4)** — it was withheld while F1-F3 were open, and they are closed. `cloud_endpoints.role_members` refuses at run time any role that names no endpoint or declares an address its generator does not inject, so the fabricated half cannot drift from the model. The measurements below are the ones taken BEFORE the fixes and are kept for what they showed: One role per endpoint host with its real /30, one service per port. `--->` compiles then crashes on `f=provider:`; `<-->` refuses to compile; **`<->>` compiles cleanly with no `provider` operand** and is the only operator that works with services today. **Five policy rules become 60 checks** (9 must-reach, 51 must-not-reach; 61 under `<->>`), of which six correspond to oracle statements — so **~54 of 60 expectations would be self-derived**, which is what makes the provenance labelling structural. Also surfaced: the diagonal fills with `X` self-reachability whenever `strict` is false, and `<->>` emits `related:0`/`related:1` conditions naming a field the cloud model does not have at all (extending the mapping at check time is item 1s/§9.29 territory — measure before relying on it). Inventory deliberately NOT committed while F1-F3 are open.
  - [x] **F3 "these services and NOTHING ELSE" — IMPLEMENTED** as `reach_csv_to_checks.py --complement`, OFF by default. Claas's framing: no legacy probe mechanics needed, the reachability tree answers it, and the invariant holds AT THE PROBE — an ACL router on the path yields leaves with other ports and that is fine, since those flows never arrive and `check_compliance` iterates `dst->source_flow`. The "unless some other rule allows it" clause needs no generator logic: `update_conditions` has already merged the cell (another conditional rule joins as an OR operand; an unconditional one wins outright and leaves a plain `X` with nothing to complement). Generalised past the third check to a property of the MATRIX — every conditionally permitted cell gets a complement against the union of its own conditions, so `<-->` with a service yields four checks and no operator-specific code exists. Complement shape: pick one field from each alternative and negate it, drop superset terms. Verified OFF-by-default changes nothing (wl_ifi/wl_up/wl_stanford byte-identical, wl_example positives identical). **Two defects it exposed, both fixed:** the `_expand_negations` same-name collision (now intersects via `_meet_all`; the error was a FALSE VIOLATION, since the survivor is a superset of the intended intersection), and `reporter._parse_cond` asserting every constrained field has a concrete value — false for a complement vector, which killed the whole report task; partial fields now render as their bit pattern. **On wl_example (the only workload with service cells): 261 violations, all on `office -> dmz`, 253 dport + 8 proto — the data plane does not restrict that pair to its permitted services.** Cause not investigated; and 261 violations of one fact argues for a summarising renderer before enabling this on a large matrix.
- [ ] **Decide: fix APKeep's name coupling?** The §9-for-APKeep question. Until then APKeep cannot answer any workload not shaped `in.`/`mid.`/`out.`, which is a live limit on the cross-family comparison, not just on this workload.
- [x] **Decide: prefix-capable `fieldmatch` in ad6? — DONE 2026-09-21, as a MASK-capable one** (Claas's call: a ternary form subsumes a prefix, so the `<fieldmatch>` path never needs a second mechanism beside it). `AD6_PLAN.md` §9.35. The boundary turned out to be the converter, not the encoding — ad6's other two (`ConvertPortToVariables`, `ConvertCIDRToVariables`) were already prefix-capable, which matters because it changes what the result claims: "a generic model checker cannot do NAT + prefixes" would not have survived a reader opening either one. Measured on wl_cloud: **2,480 of 2,480 address match values translate, 0 refused.**
  - [x] **A latent NEGATION INVERSION found and fixed as the prerequisite.** `kripke.py` never read the `negated` attribute of a `<fieldmatch>`, so `NOT (f == v)` was encoded as `(f == v)` — not a dropped match but the opposite question, in a well-formed model. Latent (no benchmark emits a negated match) and it survived because the tests pinned the PRODUCER and nothing pinned the CONSUMER. Negatives on one field also now AND rather than OR, since OR-ing them is a tautology. Found only because A′ routes addresses through `<fieldmatch>` and the compliance path negates them.
  - [x] **A guard REMOVED because mutation testing could not justify it** — the first cut copied `ConvertCIDRToVariables`'s empty-conjunction guard; removing it turned nothing red and the instance measured identical, because the hazard it documents belongs to `_ShortenPrefixes`, machinery this path never reaches.
  - [x] **Masked REWRITE — DONE 2026-09-21, the second boundary, uncovered by closing the first.** The 28 NAT rules rewrite the destination to a SUBNET (`/23`–`/25`, 24 distinct values, none a host) and `_rewrites` required an integer: 0 of 24 accepted. **Claas's ruling: the unwritten bits are PRESERVED** (Hassel's `(h & mask) | rewrite`). **IMPLEMENTED BACKWARDS, CORRECTED 2026-09-21.** The ruling is right about Hassel; the implementation applied it to the wrong bits. Which bits are "unwritten" is decided by the MASK, not by the value — net_plumber's `array_rewrite`: "a 0 in the mask means that the bit should be kept whereas a 1 means it should be rewritten", and a rewritten bit takes the value's bit INCLUDING its `x`. FaVe's model has no mask-0 bit inside a rewritten field at all (`NetPlumberAdapter` synthesises an all-ones mask per rewritten field), so a value's don't-cares are the only wildcards there are and framing them preserved bits nothing had asked to preserve. On wl_cloud that is fatal in one hop: the DNAT matches a /32 and rewrites to a /22, so the framed bits were pinned by the match and the /22 collapsed to one host — **ad6 called every internet-sourced pair unreachable**, against NetPlumber and against the dataset's own sat verdicts for q01/q03. `cloud_preparation` had already written the symptom down for the mirror-image bug (CLOUD_BENCH_PLAN.md §1.6: "leaves the low 8 bits FREE … emitting the bare address instead pins traffic to one host and every internet-sourced query answers unreachable"). After the fix ad6 agrees with NetPlumber on **all 64 cells** of wl_cloud's all-pairs matrix (was 58) and matches the dataset at q01/q02/q03. An all-don't-care rewrite is now exactly a CLEAR, so the three outcomes collapse to two and the test that pinned them apart pins them together. **No unit test could have caught this** — every piece was individually correct and the encoding test asserted the wrong behaviour in its own name — so the guard is a differential: `fave/test/test_ad6_cloud_differential.py`, integration tier, verified inverted. `AD6_PLAN.md` §9.36, CLOUD_BENCH_PLAN.md §1.7.2.
  - [x] **ad6 RUNS wl_cloud — DONE 2026-09-21, 6/6 and identical to NetPlumber on all 71 checks.** The last blocker was the query path, not the model: `_SUPPORTED_COND_FIELDS = ("related",)` could force neither the `f=related:0` the FPL check set puts on every conditional check nor the `f=!port:331` carrying q04. `AD6_PLAN.md` §9.37. Three changes, none of them an extension of the allowlist: (1) **which namespace a field lives in is a property of the MODEL** — node-scoped SSA copy vs global bit-vector, depending on whether some rule rewrites it — so the translator now ships a per-field recipe, authoritative by construction, and carries ad6's IANA name table with the protocol's (CanonizeProto looks up BY NAME and silently returns 59 for '6'); (2) **a negated condition is a CLAUSE**, so `IncrementalSession.Query` grew `extra_clauses` (selector + permanent clause under rank, plain clause under flow), and the negation is deliberately the WEAK one because `_CreateBitConstraints` pairs `=0`/`=1` only for values the model mentions; (3) **an ABSENT field is not an UNKNOWN field** — where the model has no such field the two variants are identical BY CONSTRUCTION and reporting that is correct, which the old refusal conflated with §9.23's dropped-condition bug. Absence is now a statement from the recipe map, honoured and announced per field; `scope: unsupported` still refuses. **Demonstrated on wl_ifi**, whose 54 stateful checks used to raise and now answer **27 violations — exactly NetPlumber's, and exactly the 27 §1.9.0 records under `<->>`** — with the same checks minus the condition giving identical verdicts, which is what vacuous has to mean. Two silent no-ops exposed on the way: the src-CIDR seed forced the global vector unconditionally (a no-op under source NAT, i.e. on wl_cloud), and a node-scoped seed could not take a prefix (wl_cloud's generators are /30s).
- [ ] **Translatable is not solvable — the cost question is untouched and is what remains.** Mutable addresses give every node its own 64-bit SSA copy over wl_cloud's ~2,500 nodes, plus a frame-or-rewrite axiom per bit per edge. Size the instance before attempting a solve; if it does not finish that is a COST result, which is a better answer than the refusal it replaces. Item 0a applies to any number that comes out.

- [ ] **Decide: the `stanford-tfs` mask-polarity provenance** (latent trap above). **Reframed 2026-09-18 as a REPRODUCIBILITY defect, which is what it actually is** (Claas's standing principle: every benchmark and measurement must be recreatable from the raw data, because manual edits made while debugging are how wrong inputs get in and stay in). `stanford-json/*.tf.json` is a derived artifact with no surviving derivation -- today's `tf_to_json.py` + `np_preparation` cannot rebuild it from the `stanford-tfs/*.tf` beside it, so which of the two is authoritative is unanswerable and neither can be regenerated from the `stanford-hassel/` Cisco configs that are the real raw data. No current result is wrong; the ability to reproduce one is. RECORDED, NOT FIXED -- the fix is a scoped decision (re-run the bundled `cisco_router_parser.py`? settle the convention and regenerate? treat the JSON as raw and retire the `.tf`?), and wl_i2 very likely carries the same shape.
- [ ] **D1-D5 Delta-net** (CLOUD_BENCH_PLAN.md §2.2) — not started. First step is establishing what the fourth CSV column means before any converter is written.

---

### 15. FPL silently DROPS a role whose block does not parse — FIXED 2026-09-21
**Found by C7, and it nearly shipped a policy missing 8 of 26 roles.**

**The finding.** `PolicyBuilder` finds role and service blocks with
`regex.search` over the whole file, so a block that does not match is SKIPPED —
and every block after it is still found. The result was not an error but a
smaller inventory: the policy compiled against what survived, the matrix came
out with fewer rows and columns, and **the translator exited 0.**

**Measured.** wl_cloud's generated inventory gave every role a description
listing its prefixes joined with ` + `. Nine of 25 services have two prefixes;
the 8 whose descriptions therefore carried a `+`, plus nothing else, vanished.
`reachability.csv` came out **18x18 instead of 26x26** and the only reason it
was caught is that the emitter knew how many roles it wrote. A hand-written
inventory has no such check.

This is items 1i/1n/1p's swallowed-sub-step pattern in the POLICY layer: the
step ran, produced an artifact, and answered a smaller question.

**CORRECTION to this item as first filed.** It blamed
`policy_translator/fpl_grammar.py`'s `value_text`. That module is not the live
path — `parse_fpl` is reached only from its own `__main__` and the deprecated
tests. The parser that runs is the REGEX one in `policy_builder.py`, with its
own `value_pattern`, which excludes `+` as well. Same symptom, wrong module;
the fix below is in the parser that actually runs.

- [x] **Made LOUD, in the way the item said mattered most.**
      `PolicyBuilder._assert_every_block_parsed` compares the blocks the file
      DECLARES (`block_header_regex`, matched at line starts so a commented-out
      header does not count) against the blocks the parser produced, and raises
      `UnparsedBlockException` NAMING each one that was skipped. The cause is
      irrelevant to the check, which is what stops it being a patch for one
      character: any block that fails to parse, for any reason, is refused.
- [x] **And the process now says so.** `policy_translator.py` caught
      `PolicyException`, printed `Fehler: ...` and **fell through to exit 0** —
      so *every* policy error, not just this one, reported SUCCESS to its
      caller, and every caller in this tree invokes the translator through
      `os.system`. It now `sys.exit(1)`, like the `IOError` handler three lines
      above it always did.
- [x] **A second silent-drop cause, found by the same check and closed by it.**
      `fpl_grammar.py` accepts `define`, `def`, `describe` AND `desc`;
      `PolicyBuilder.define_pattern` accepts only the first three. A `desc`
      block was therefore dropped exactly like a malformed one. It is now
      refused and named. (Whether `desc` should be *accepted* is a separate
      question — the two parsers disagreeing about the language is the defect,
      and refusing is the safe half of it.)
- [x] **Every FPL source in the tree still parses**, checked one by one:
      wl_up, wl_ifi (both variants), wl_example, wl_stanford, wl_i2,
      wl_generic_fw, wl_shadow, wl_cloud, and `examples/{ifi,up}-policy.txt`.
      `fast` 734, the full `policy_translator` suite 110, `smoke`, and both
      wl_cloud policy phases are unchanged (1,315 and 3, still agreeing with
      their derived expectations pair for pair).
- [x] **`policy_translator/test/test_unparsed_block.py`**, 7 tests at the parser
      level where the rule lives, plus the inverted pin in
      `fave/test/test_cloud_policy.py`. Verified by mutation: removing the check
      turns 4 red, comparing COUNTS instead of names 2, dropping `desc` from the
      header regex 1, and letting the header regex match mid-line (so comments
      count) 1.

**One pre-existing breakage surfaced, not fixed here.**
`policy_translator/examples/fml-paper-policy.txt` now exits 1 with `Fehler:
Service All.ARP unbekannt.` It was already producing a truncated CSV — the
build aborts partway — and simply never said so. It is referenced from
`policy_translator/README.md` and by no test or script.
*(Followed up: item 19 fixed that cause, and item 21 then refused the file for a
different and real one — its protocol values. By owner decision it stays
failing, and `policy_translator/README.md` now says so. It is covered by a test
asserting which refusal it gets.)*

#### What the value pattern accepts, and what `+` was really about (measured 2026-09-21)

**CORRECTION.** This item used to end "widen the value pattern … a language
limitation with no reason behind it", taking `+` as the example. Both halves
were wrong: `+` is not needed for anything, and the set is conservative for a
reason.

`value_pattern` is `[A-Za-z0-9 _=\-\[\]'\":.,\*/]+` — 75 printable characters:
alphanumerics, space, and ``_ = - [ ] ' " : . , * /``. It rejects 20 printable
ones — ``! # $ % & ( ) + ; < > ? @ \ ^ ` { | } ~`` — and **all non-ASCII**.

It is not binding on anything in the tree. Across every inventory (wl_up,
wl_ifi, wl_example, wl_stanford, wl_i2 and the three `examples/`), the only
non-alphanumeric characters any value uses are ``,-./:[]``. The pattern is sized
for TECHNICAL values — addresses, VLANs, host lists — and every one of those
fits with room to spare.

**`+` was mine, not the language's.** wl_cloud's generator joined a role's two
prefixes with `" + "`; joining them with a space says the same thing. Nothing
in the tree wants a `+`, and nothing would gain from one.

**Where the pattern does bite is free prose**, because `description` shares one
pattern with the technical attributes. Measured against the real parser, each of
these refuses the whole role:

    description = 'Servers (public)'            parentheses
    description = 'Mail & web servers'          ampersand
    description = 'web; mail'                   semicolon
    description = 'Do not touch!'               exclamation
    description = '100% internal'               percent
    description = 'Universität Potsdam'         any non-ASCII

The last is the one worth weighing: this project's subject is a German
university and its own error messages are German, so an umlaut in a description
is a plausible thing for its author to type. The existing descriptions are short
English sentences that happen to avoid all of the above.

**And the sharpest case is not a character at all — it is comments.** A comment
anywhere inside a role or service block refuses it, in both forms:

    def role Probe
        description = 'plain'   # the office     <- refused
    end

    def role Probe
        # the office                             <- refused
        description = 'plain'
    end

`role_content` is *either* a run of attribute/`includes`/`offers` lines *or* a
run of comments, never the two interleaved. **`policies_regex` does allow
interleaved comments**, and `wl_ifi/reach_stateless.txt` uses them — so comments
work in a policy block and not in an inventory block, which is an inconsistency
a writer meets the first time they try to annotate a role.

**Why widening is not free.** `#` cannot simply be added: an attribute's value
runs to end-of-line, so admitting `#` would swallow a trailing comment into the
value rather than enable it. Fixing comments properly means letting
`comment_pattern` interleave inside `role_content`/`service_content`, which is a
grammar change rather than a character-class change.

- [x] **Comments interleave inside role and service blocks — DONE 2026-09-21**
      (Claas's call). `role_content`/`service_content` now admit a comment line
      among the attribute/`includes`/`offers` lines, and any of those lines may
      carry a trailing one. That matches `policies_regex`, which has always
      allowed it. **Verified as a no-op on every existing inventory**: all
      eleven (wl_up, wl_ifi ×2, wl_example, wl_stanford, wl_i2, wl_generic_fw,
      wl_shadow, wl_cloud, `examples/{ifi,up}-policy.txt`) produce identical
      matrices and role dumps.

      **THE HALF THAT NEARLY WENT WRONG.** The block patterns decide whether a
      role parses; `role_attr_regex`, `role_incl_regex` and `role_offers_regex`
      decide what is read OUT of it. Teaching only the block patterns turns a
      loud refusal into a SILENT LOSS — measured mid-change: `description = 'x'
      # note` left the role with no description at all, and an annotated
      `offers` left it offering nothing, surfacing much later as "Service
      unknown" from the policy. All three extractors take the comment too, and
      every test asserts the annotated line was still read rather than only that
      the block parsed.

      `#` is kept OUT of `value_pattern`. Folding it in appears to work and
      passes every behavioural test — but only because `Role.add_attribute`
      hands the group to `ast.literal_eval`, which treats the tail as a PYTHON
      comment and drops it. A coincidence between two languages, not a property
      of this one, so the value group is pinned at the regex level.
      13 tests in `policy_translator/test/test_block_comments.py`,
      mutation-verified: reverting the block patterns turns 3 red, omitting the
      extractors 6, folding `#` into `value_pattern` 1.
- [ ] **Still open:** whether `description` should accept prose punctuation and
      non-ASCII — most cleanly by giving it its own pattern rather than widening
      the one the technical attributes share. Unchanged by the above; still a
      language question, and still not urgent because the refusal is loud.
- [x] **Not urgent, and this is why.** Every one of the cases above now fails
      LOUDLY and names the block, so a writer who hits one learns it in a single
      run instead of shipping a policy with a role silently missing. The cost of
      the limitation is now an error message, not a wrong result.

---

### 16. wl_cloud's 3 surviving violations — CLOSED 2026-09-21 (universal reading kept), and my first diagnosis was wrong
**The three are real and expected. Everything I wrote about WHY was not.**
Recorded in full because the wrong turn is the instructive part, as in item 14.

**What I claimed** (committed in `21cef327`): that services 1, 11 and 23 have two
gateway NAT rules with identical match, that NetPlumber resolves same-match by
priority while "NoD's Datalog semantics is a RELATION: both rules fire", and
that the three unreachable endpoints were therefore *a semantic difference
between the two engines* which the six-query oracle could not see.

**What is actually true.** The dataset ships its network TWICE and I compared
neither encoding against the other:

| encoding | gateway destination-NAT rules |
|---|---:|
| `network.tf` (Hassel) | **14** |
| each of the six `.smt2` (Z3-Datalog) | **11** |

The Datalog does not contain the three extra rules at all — it publishes each
public service from exactly one datacenter. And Hassel's resolution is not a
convention this repository chose: the vendored `tf.py` makes a rule
`affected_by` every EARLIER rule whose match intersects (`_find_influences`) and
`apply_rewrite_rule` subtracts each applied one's header space ("subtract off
all the higher priority rule's match patterns"). For an identical match that
subtraction is total, so the later rule yields nothing.

**Apply Hassel's own rule and `network.tf` reduces to EXACTLY the Datalog's 11 —
identical, zero differences, against all six instances.** The two encodings
agree, there is no engine disagreement, and FaVe reproduces both correctly.
`fave/test/test_cloud_encodings_agree.py` pins it; keeping the LAST rule instead
of the first turns the agreement test red on its own.

**The real finding, and it is about the DATASET.** Services 1, 11 and 23 are
exactly the public services whose prefixes span two datacenters, and the gateway
publishes only ONE prefix of each:

| service | declared | published to the Internet |
|---|---|---|
| 1 | `10.0.4.0/22` + `10.0.18.0/25` | `10.0.4.0/22` only |
| 11 | `10.0.0.0/24` + `10.0.16.0/25` | `10.0.0.0/24` only |
| 23 | `10.0.2.0/24` + `10.0.19.0/25` | `10.0.2.0/24` only |

So half of each is unreachable from the Internet in BOTH encodings, although
matrix row 25 authorises the Internet to reach the service. That is the mirror
of §1.9.6's 1,312: the generated data plane is more permissive than its matrix
for the services it publishes, and less permissive for the three it splits.

**So the three violations come from the POLICY, not the model.**
`reach_csv_to_checks` expands a role-level cell into a must-reach at EVERY
endpoint of the target role — universal, which is the right reading for a subnet
role ("Wifi may reach the DMZ" should hold for every DMZ host) and is what makes
these three red.

- [x] **DECIDED (Claas, 2026-09-21): the UNIVERSAL reading stays.** A role-level
      cell asserts reachability at EVERY endpoint of the target role. Nothing
      changes in `reach_csv_to_checks.py`; the alternative was existential
      ("the Internet may reach service 11" satisfied if it reaches any of its
      hosts), which would have made these three green at the cost of weakening
      every must-reach check in every workload — and the universal reading is
      what surfaced the finding at all. wl_cloud is the only workload where the
      two differ, since these are the only roles with a published/unpublished
      split, so the decision costs nothing elsewhere.
- [x] **The three are now a DERIVED expectation, not a remembered number.**
      `cloud_policy.expected_violations()` computes the pairs a run should
      report, from the raw data: the Internet against an endpoint the gateway
      does not publish (these three, both policies), plus every denied cell into
      a public service (1,312, `matrix` only). Every run compares its report
      against that set and stamps `expected_violations`, `unexpected`, `missing`
      and `agrees`, logging loudly on any difference. Both policies currently
      agree PAIR FOR PAIR — 3 of 3 and 1,315 of 1,315, with `unexpected` and
      `missing` both empty.

      This is what closing the item required rather than a nicety: "3
      violations" and "the RIGHT 3 violations" were the same sentence until the
      expectation was derived, which is item 1s's defect in miniature. Not made
      fatal — the bench tier exiting non-zero on a wrong verdict is item 1s's
      job for every workload, not this one's.

**The lesson.** I had two encodings of the same network in one directory and
reasoned about engine semantics instead of diffing them. `AD6_PLAN.md` §9.28 and
item 1s both say this suite's weakness is that correctness rests on consensus
between implementations in this tree; the one workload that ships an INDEPENDENT
second encoding is the one where I argued from first principles rather than
reading it. The check that settled it is eleven lines long.

---

### 17. Two benchmarks in a row could not run — FIXED 2026-09-21 (three defects), and the cause was not the one I filed
**Filed as a `start_aggr.sh` gating bug. That was real but SECONDARY; the
failure it explained was not the failure being reported.**

    util.barrier.BarrierError: FaVe will never finish the request:
    no aggregator is registered (/dev/shm/np/aggregator.owner is absent)

#### The actual cause: a predecessor deregistering its successor

`aggregator/stop.py` sends the stop request and RETURNS WITHOUT WAITING for the
aggregator process to exit. `barrier.withdraw_owner` then unlinked the owner
file unconditionally. So:

1. run A's teardown sends stop; `stop.py` returns; run A's driver exits;
2. run A's aggregator is still shutting down;
3. run B starts, wipes `/dev/shm/np/*`, starts its own aggregator, which
   publishes its registration; `start_aggr.sh` correctly waits for it;
4. run A's aggregator finishes shutting down and calls `withdraw_owner()` —
   **deleting run B's registration**;
5. run B's next barrier reports "no aggregator is registered" and, because
   `BarrierError` means "can no longer complete at all", treats a live
   aggregator as permanently dead.

A live aggregator declared dead by its predecessor. It surfaced at
`check_compliance`, not at startup, which is exactly why the startup gate looked
like the culprit.

- [x] **`withdraw_owner` only removes a registration that is still ITS OWN.**
      `publish_owner` already records the pid, so the check is exact: a reused
      pid would mean the process is gone, and a gone process is not running that
      line. A file that cannot be READ is left alone rather than removed — we
      cannot tell whose it is, and `_owner_alive` already diagnoses that case
      loudly. Six consecutive wl_cloud policy runs failed before; six pass
      after. Five tests in `fave/test/test_barrier.py`, mutation-verified:
      withdrawing unconditionally turns three red.

#### The gap I *did* file, fixed as well because it is real

`start_aggr.sh` waited for the SOCKET. `aggregator_service.py` binds and then
publishes the owner on the next statement, and `sock.bind()` is what CREATES the
socket — so the gate released between the two, and `_startup` logged "started
aggregator" and called `_wait_for_fave()` at once. **Measured: the owner file
was absent when the gate returned in 10 of 12 starts.**

- [x] **The gate now waits for the barrier owner file**, which is the artifact
      the waiter downstream reads and which `aggregator_service.py`'s own
      comment says means "an aggregator is actually up". It subsumes the socket
      wait — the publish cannot precede the bind. **0 of 8 absent after.** The
      path comes from `util.barrier.owner_path()` rather than being spelled a
      second time in shell, and a stale owner file is removed before starting
      for the same reason the stale socket already was.
- [x] **The wait is now unconditional.** It ran only for the unix path; the TCP
      path had none at all, so it raced without even the partial protection.
- [x] `fave/test/test_start_aggr_gate.py`, five tests driven by a STUB
      interpreter so they are deterministic and `fast`-tier. Mutation-verified:
      restoring the socket wait turns four red, dropping the `kill -0` liveness
      check one (and that run takes 66s instead of 7, which is the point of it),
      and not removing a stale owner one.

**Controlled experiment, because two fixes for one symptom is one too many:**
with `start_aggr.sh` reverted to the socket wait and only the `withdraw_owner`
fix in place, six back-to-back runs still pass. So the withdrawal fix is the one
that closes the reported failure, and the gate fix closes a separate, directly
measured gap. Both are kept; neither is credited with the other's effect.

#### The misleading diagnostic beside it — FIXED 2026-09-21
The teardown's failure advice was *"a net_plumber MAY still be running. Check
with `ps -C net_plumber` and kill it, or the next run will start a second one
alongside it."* In a container whose pid 1 does not reap, that reads wrong:
after a session of benchmark runs this box showed **122 `net_plumber` entries,
every one a ZOMBIE** (state `Z`, PPID 1) and **zero live**.
`scripts/start_np.sh` backgrounds net_plumber and nothing ever waits on it, so
each stopped backend leaves an entry `ps` renders identically to a running one.
A reader following the advice saw 122 apparently-running backends and concluded
the opposite of the truth.

- [x] **The teardown now REPORTS the state instead of asking the reader to
      find it.** `net_plumber_processes()` splits live from zombie off `/proc`
      and the message says which, naming live pids:

          ... -- no net_plumber is running, so nothing is orphaned and the next
          run is safe. `ps -C net_plumber` nevertheless lists 122 ZOMBIE
          entries: an exit status nobody collected, holding no socket and
          contending for nothing -- harmless, and not what to kill.

          ... -- 1 net_plumber process still RUNNING (pid 92096) -- kill it, or
          the next run will start another alongside. `ps -C net_plumber` also
          lists 122 ZOMBIE entries: ...

      `ps` is still named, but as an explanation of what the reader will see
      rather than as a question handed back to them. The state lookup shares
      `barrier.process_state()` (promoted from `_proc_identity`) rather than
      re-parsing `/proc/<pid>/stat`, whose field layout is subtle — `comm` may
      itself contain spaces and parentheses.
- [x] Five tests in `fave/test/test_generic_benchmark.py`, driven by REAL
      processes: a copy of `sleep(1)` named `net_plumber` is indistinguishable
      to the classifier (`comm` is the executable's name, so a shell script
      would not do — its `comm` is the interpreter's), and `Popen` without
      `wait()` produces exactly the unreaped state the container does. Verified
      by mutation: restoring the state-blind advice turns three red, counting
      zombies as live one, counting live as zombies two.

**Reaping them is NOT available**, which is why the other option in this item
was dropped rather than chosen: `start_np.sh` backgrounds net_plumber and then
exits, so the process is reparented to pid 1 and only pid 1 can reap it.
`stop_fave.sh` is not its parent and cannot wait on it. The entries persist
until the container restarts, and saying so is the whole fix available here.

---

### 18. PolicyTranslator's output is not reproducible for a `.*` service — DONE (found and fixed 2026-09-21)
**Found by accident**, checking that item 15's comment change had not altered
how any inventory parses. It had not — but the same file gave two different
answers across runs with UNCHANGED code:

    $ for i in 1 2 3 4; do policy_translator.py -c examples/ifi-policy.txt; done
    Intern,...,(protocol:tcp;port:80|protocol:tcp;port:443)
    Intern,...,(protocol:tcp;port:80|protocol:tcp;port:443)
    Intern,...,(protocol:tcp;port:443|protocol:tcp;port:80)
    Intern,...,(protocol:tcp;port:443|protocol:tcp;port:80)

**The cause is exact.** `policy.py` `add_reachability_policy`, the wildcard
branch:

    if service_to == "*":
        services = set()
        for offered in self.roles[owner].get_services().values():
            services.update(offered)

A `set` of service NAMES, iterated to build the condition list. Iteration order
follows string hashing, which Python randomises per process, so a role offering
two or more services under `X ---> Y.*` emits its alternatives in an order that
varies between runs.

**Scope, measured.** Only the `.*` wildcard form reaches that branch; the named
form takes the `else` and is a one-element list. **No workload in the tree uses
`.*`** — the only file that does is `policy_translator/examples/ifi-policy.txt`.
So nothing tracked or gated is affected today, and
`test_wl_example_policy_artifacts.py` is stable across eight `PYTHONHASHSEED`
values although wl_example's matrix does carry an alternative cell (it comes
from two separate FPL rules, not from `.*`).

**Why it still matters.** CLOUD_BENCH_PLAN.md §1.8's principle is that every
benchmark and measurement must be recreatable from the raw data, and the
artifact-invariant tests (TODO item 14) compare generated matrices BYTE FOR
BYTE. A translator that can emit two spellings of the same policy breaks both
the moment a workload uses `.*` — and the wildcard form is live in this
project's thinking, not hypothetical: §1.9.5's `INTERNET_ROLE` work exists so
that `Internet.*` resolves, and §1.9.4 measured `host2 <->> Internet.*`
directly. The first workload to use it would get an intermittently failing
artifact test and no obvious reason.

- [x] **Fixed in declaration order** (owner decision 2026-09-21), not
      alphabetical. Both are reproducible; only one is the order the writer put
      on the page, which is what a reader comparing a matrix against the
      inventory expects — `sorted()` would silently reorder the author's list
      for the convenience of the implementation. `get_services()` returns
      dicts, so that order was still there; `list(dict.fromkeys(...))` keeps it
      while preserving the deduplication the `set` provided for free. For
      `Internet`, whose services are the whole policy's, the same rule reads as
      the order of the `def service` blocks.
- [x] **Pinned** — `policy_translator/test/test_wildcard_service_order.py`, 8
      tests. Hash randomisation is fixed at interpreter start, so the
      reproducibility half drives the real CLI across eight `PYTHONHASHSEED`
      values (56 ms per run, so it stays in the `fast` tier). Its fixture
      declares five services in a NON-alphabetical order, which makes the tests
      distinguish the two reproducible orders instead of passing on either.
- [x] **Verified no artifact moved.** Every inventory/policy pair in the tree
      compiled before and after (9 workloads + 2 examples): exactly one output
      differs, `examples/ifi-policy.txt`, the only file in the tree that uses
      `.*`, and it now carries the declaration-order spelling
      (`port:80|port:443`, from `offers HTTP` then `offers HTTPS`).

**Mutation-verified.** Reverting to `set()` turns 4–5 of the 8 red depending on
the seed; `sorted()` in place of declaration order turns 5 red. Dropping the
`dict.fromkeys` deduplication turned **none** red when this was committed, and
that was reported rather than papered over: the only duplicate-producing shape
is one service offered by two subroles of a superrole, and that shape was
broken for a different reason (item 19 below). It was kept anyway, because
removing it would change behaviour the `set` guaranteed on a path that would
start working once item 19 was fixed. Item 19 is now fixed, the shape is
reachable, and that mutation turns red — see item 19's verification.

### 19. `X ---> Superrole.*` works in none of its three spellings — DONE (found and fixed 2026-09-21)
**Found while writing item 18's deduplication test**, which needed one service
offered by two subroles — and could not be built, because every way of writing
it fails. Characterised over a superrole `Both` including `Alpha` and `Beta`:

| written as | result of `Client ---> Both.*` |
|---|---|
| `includes Alpha` | **silently empty** — the policy is granted with NO service condition |
| `includes Alpha.*` | `ServiceUnknownException: Service Both.Telnet unbekannt.` |
| `includes Alpha.HTTPS` | `ServiceUnknownException: Service Both.HTTPS unbekannt.` |

Read the first row as a *symptom*, not as a missing feature: under the
invariant decided below, `includes Alpha` correctly gives the group nothing —
what is wrong is that "nothing" compiled to an unconditional rule instead of
being refused. The other two rows are services the group genuinely declares and
should always have resolved.

**The cause is one method.** `PolicyBuilder` passes `provider=<the superrole>`,
so `add_reachability_policy` takes `owner = 'Both'` and then guards each service
with `self.roles[owner].offers_service(service)` — and `Superrole.offers_service`
is `return False`, unconditionally, with the docstring "False. (Only roles offer
services.)". But `Superrole` *does* carry services: `add_service` propagates to
every subrole and records `subservices`, and `add_reachability_policy`'s own
docstring promises "If the reached role is a superrole, all subservices will be
considered." The two disagree, and the guard wins.

The empty-conditions row is the dangerous one. An FPL author writing
`Client ---> Both.*` asks for *the services `Both` offers*; what they get is
unconditional reachability — **wider** than they wrote, and silent. The two
exceptions are wrong but loud.

**This is not new and not mine**: `examples/fml-paper-policy.txt` — the FML
paper's own policy, tracked in this repository — declares `def role All` with
`offers ARP` / `offers SSH` over ten `includes`, writes `All ---> All.ARP`, and
**does not compile**, failing with `Service All.ARP unbekannt.` It fails
identically at `HEAD~8`, before any of this branch's translator work.

- [x] **Decided: a superrole offers what IT declares, and that travels DOWN**
      (owner, 2026-09-21). A superrole may offer services; its services are
      propagated transitively to its subroles. A subrole's own services are
      **not** reachable through the group: `R ---> SR.*` accesses only what
      `SR` offers, whether from its own `offers` lines or from a superrole
      above it. So `offers_service`/`offers_services` are now answered from
      what the superrole records rather than hard-wired to False, and
      `get_services` still returns `subservices` **as written** — an empty
      entry is a statement ("the group offers nothing through this member"),
      not a gap to be filled from the member.
      *An intermediate version of this fix had it backwards*, letting a plain
      `includes Alpha` hand the group Alpha's services; that was reverted. The
      reading is now pinned by tests — restoring the fallback turns six red.
- [x] **The empty case is loud** — `NoServicesOfferedException`, and this half
      is independent of superroles. An empty condition list is how FPL spells
      an *unconditional* rule, and `update_conditions` documents that "the
      empty list overpowers all other lists of conditions", so a `.*`
      resolving to nothing did not merely fail to restrict its own rule, it
      **erased the conditions an earlier rule had set for the same pair**.
- [x] **A third defect, found while checking that propagation is transitive:**
      `add_subrole` handed an outer group the inner group's own `subservices`
      **dict** rather than a copy, so `Outer.add_service` wrote through into
      `Mid` and `Mid.*` resolved to a service `Mid` never declared — a role's
      offering changing because something *else* included it. Copied now.
- [x] **`fml-paper-policy.txt` gets past the superrole.** `All ---> All.ARP`
      over a `def role All` whose body reads `offers ARP` used to raise
      `ServiceUnknownException`; the file could not be compiled at all, and
      still cannot at `HEAD~8`, so it predates this work.
      *(Superseded in part by item 21: the file now fails later and for a
      different, real reason — `arp` is not an IP protocol — and by owner
      decision it stays that way. The test asserts WHICH refusal it gets, so
      this item's property is still pinned.)*
- [x] **Tests:** `test/test_superrole_services.py` (13) and four rewritten or
      new `TestSuperrole` cases in `test_policy.py`. Mutation-verified five
      ways, all red: `offers_service` back to `False`; `get_services` falling
      back to the member (the overruled reading); the empty-wildcard refusal
      removed; the `subservices` dict shared again; and item 18's
      `dict.fromkeys` deduplication removed — that last one **stayed green two
      commits ago**, and `includes Alpha.*` + `includes Beta.*` where both
      offer HTTPS is now exactly the shape it needs, so item 18's
      deduplication is covered from here on.

**Artifacts:** every inventory/policy pair recompiled; **nine workloads
byte-identical**. `fml-paper-policy.txt` produced a matrix where it had produced
an error (item 21 later refuses it earlier, on its protocol values), and
`ifi-policy.txt` was corrected (below).

- [x] **`examples/ifi-policy.txt` corrected** (owner, 2026-09-21): both
      wildcard rules now name the webserver and its services directly —
      `All <->> Webserver.HTTP` / `.HTTPS` and `Internet ---> Webserver.HTTP` /
      `.HTTPS` — rather than pointing `.*` at `Server`, a group that is
      `vlan = 5` plus `includes Webserver` and declares no `offers`. Under the
      invariant that group offers nothing, so the old rules could not mean what
      the file's own comment says ("Alle Rechner können den Webserver mit HTTP
      und HTTPS erreichen"); before item 19 they compiled to an
      **unconditional** cell that had also erased the `RELATED,ESTABLISHED` an
      earlier rule set for the pair. One cell moves against the historical
      output, and it is the one that was wrong: `Internet`→`Webserver` now
      carries HTTP, HTTPS and the earlier rule's state condition.
      **No file in the tree uses `.*` any longer**, so item 18's cross-seed
      coverage runs on fixtures — noted there, since that was the workload
      argument for fixing it.
- [x] **`roles_to_csv` fixed** (2026-09-21) — and it was **not cosmetic**,
      which is worth recording because that is what I first called it. The
      renderer short-circuited to `(X)` whenever `RELATED,ESTABLISHED` was
      among a pair's conditions and dropped the rest. But
      `bench/reach_csv_to_checks.py` reads `(X)` as *related traffic and
      nothing else* and emits `! s=source.X && EF p=probe.Y && f=related:0` —
      a **must-not-reach** check. For a pair that also permits HTTP that is the
      opposite of the policy, so a correct data plane fails it: the rendering
      did not hide information, it **inverted a verification claim**.
      One path now, with `X` as the operand the stateful condition renders as,
      so a cell whose only condition is that one still prints exactly `(X)` by
      construction — the 738 such cells in the tree are untouched, and
      `wl_up`'s 18,811 generated checks are byte-identical across the change.
      The reader learned the `(X|<service>…)` form to match, complementing over
      the service alternatives only (each term is asserted under `related:0`,
      where the stateful alternative permits nothing). Operand order follows
      condition order, the same choice item 18 made. Tests:
      `policy_translator/test/test_stateful_cell_rendering.py` (6) and
      `fave/test/test_reach_csv_stateful_alternatives.py` (7), mutation-verified
      four ways.
- [x] **A comma that could not be written is refused** rather than written.
      A cell is comma-separated, so `-/->>`'s `state = NEW,INVALID` used to
      emit `(state:NEW` and `INVALID)` into adjacent columns with no error.
      `RELATED,ESTABLISHED` is the one such value with a spelling (`X`);
      anything else now raises `UnrenderableConditionException`. No inventory
      in the tree writes `-/->>`, so this refuses a shape that is reachable
      rather than one that is used.
- [ ] **Also still open** (unchanged by the above): with a `provider`
      (`Internet ---> Group.*`) the owner of the services is the GROUP;
      without one (`All <->> Group.*`) it is each MEMBER, which under this
      invariant now means the two forms read *different sets* rather than the
      same one. No tracked file distinguishes them today.

### 20. `to_iptables` drops the services of a stateful pair — DONE (found and fixed 2026-09-21)
**The same defect as item 19's rendering half, in a second renderer**, found
while fixing that one. `to_iptables` computes

    relatedrule = ({'state':'RELATED,ESTABLISHED'} in self.policies[policy].conditions)
    ...
    ip4rule = (not relatedrule) and (...)

so a pair carrying the stateful condition generates **no address rule at all**,
whatever else it permits. Measured on a two-role fixture with `ipv4` attributes:

    Watcher <->> Server
    Server  ---> Watcher.HTTP

`Server -> Watcher` holds `[{state: RELATED,ESTABLISHED}, {protocol: tcp,
port: 80, provider: Watcher}]`, and the generated firewall contains the forward
`Watcher -> Server` ACCEPT and **nothing** for the return direction — the HTTP
permission is silently absent.

**The suppression itself is right**, which I had not seen when filing this.
The generator emits `-m conntrack --ctstate ESTABLISHED -j ACCEPT` once,
unconditionally, for v4 and v6, so a direction carrying *only* the stateful
condition genuinely needs no rule of its own. `relatedrule` asked one question
where there are two, and conflated "carries state" with "carries nothing but
state" — the same conflation `roles_to_csv` made with `(X)`. The per-condition
loop was already correct: a `state` condition contributes no `serviceinfo` and
emits nothing, a `protocol` condition builds its rule. Only the
`ip4rule`/`ip6rule` guard was in the way.

- [x] **`relatedrule` narrowed** to `stateful and len(conditions) == 1`.
      Deliberately *not* "has a non-stateful condition": a pair with **no**
      conditions is a plain permission, not something the ESTABLISHED rule
      covers, and that spelling drops it — mutation-tested, it turns 11 of the
      existing 23 `to_iptables` tests red.
- [x] **`singleway` now also requires the direction not be stateful.** The half
      a one-line fix misses. `singleway` decides whether connection tracking can
      be switched off for a pair (`--ctstate NEW,NOTRACK` plus a raw/PREROUTING
      NOTRACK), and it asks that of the *reverse* direction only — sound while a
      stateful direction emitted nothing, wrong once a mixed one emits rules,
      because NOTRACK would disable the very tracking the global ESTABLISHED
      rule needs to admit the return traffic. My first draft did produce
      `--ctstate NEW,NOTRACK` on the service rule.
- [x] **Tests:** `policy_translator/test/test_iptables_stateful_pair.py` (9),
      reusing `test_to_iptables.py`'s block vocabulary. Mutation-verified three
      ways. They assert the *unchanged* half too — a state-only direction still
      emits no rule, and the global ESTABLISHED rule is present, so that
      assertion is not a hole.
- [x] **Nothing else moves.** Every existing scenario generates a
      byte-identical rule set at a fixed seed: the five in the determinism
      checker, `wl_generic_fw/default`, and `examples/ifi-policy.txt`. None of
      them contains a mixed direction, which is *why* the defect survived —
      pinned as a test that goes red if one is ever added to the benchmark
      scenario.

**On the ordering worry in the filing above: it was wrong and is withdrawn.**
`to_iptables` output does vary run to run (`get_atomic_roles` returns a set, and
`policy_builder.py:393` iterates it to add default self-reachability), but every
reordering is confined to a **uni-action** block — anti-spoofing is literal
`-j DROP`, and every access rule ends with `jumptarget`, which is loop-invariant.
Measured over 5 scenarios × 24 seeds: block sequence and per-block multisets
identical, only uni-action blocks permute. Permuting rules that share a terminal
target is semantically the identity, so the manual verification this mechanism
rests on is unaffected. `test_to_iptables.py` already said so in its module
docstring; I should have read it. (**Count corrected 2026-09-21:** THREE blocks
permute, not two — the `Access Rules` block does as well, because the
self-reachability loop reorders insertion into `Policy.policies` and
`to_iptables` walks that dict. Same argument covers it, the block being
uni-action; the census was short by one.)

- [x] **Artifact reproducibility — DONE 2026-09-21.** `sorted()` at THREE
      sites, not the two the filing named: `to_iptables`'s two anti-spoofing
      loops, plus `policy_builder.build_policies`'s self-reachability loop —
      that third one reorders INSERTION into `Policy.policies`, which
      `to_iptables` walks to emit its Access Rules block, so a set in one
      module moved rules in a file emitted by another. Measured on a five-role
      fixture: 8 seeds → **7 different rule sets** before, 12 seeds → **1**
      after, with the line multiset unchanged. Every committed pair
      (wl_example, wl_ifi ×2, wl_up, wl_cloud) regenerates a byte-identical
      **CSV**, and their firewalls differ only by a permutation confined to
      those three blocks — which is also the measurement that says the CSV
      never depended on any of it, and therefore why the item-14
      artifact-invariant tests never caught this.

      **Owner's framing, and it is the right one (2026-09-21):** sorting buys
      comparability for quality control, not correctness. A block-aware
      comparator would do the same job for tests — and in fact
      `test_to_iptables.parse_blocks` already is one. Sorting the generator was
      chosen over relying on that because a comparator fixes only comparison:
      it does not make the artifact checksummable, does not make a `git diff`
      of two runs readable, and requires every future consumer to know the rule
      exists. **A flat whole-file line-multiset comparison would NOT be safe**
      — iptables is first-match within a chain, so a rule crossing a block
      boundary changes verdicts, and a flat multiset accepts that silently.
- [x] **The safety argument is now enforced — DONE 2026-09-21**,
      `test_iptables_reproducible.py` (7 tests, 4 mutations all caught: each
      `sorted()` reverted independently, `jumptarget` made per-policy, and an
      unclassified new block). It classifies every block by WHICH argument
      makes it safe — single-action, or a fixed literal nothing can permute —
      and fails if one is added that neither covers. A per-policy `jumptarget`,
      the plausible future change, turns it red with the reason in the message.

      **One claim in `test_to_iptables.py` was wrong and is corrected:** "each
      block is single-action" is not true of `# === IPv6 Hardening ===`, which
      mixes DROP, RETURN and a jump, and where order genuinely matters. It is
      safe for the other reason. The distinction had been collapsed into one
      sentence that the file's own output contradicts.

- [ ] **Unrelated, found while measuring this: `--prosa` writes an empty
      file.** `Policy.to_prosa` (policy.py:957) `print`s each rule to stdout
      and then `return '\n'.join([])`, so `policy_translator.py -p -o FILE`
      always produces 0 bytes. Pre-existing, nothing in the tree consumes it,
      and untouched by item 20 — the artifact is identical before and after.
      Not fixed: it needs an owner decision on whether prosa output is still
      wanted at all.

### 21. `protocol` was never validated, and three renderers disagreed — DONE (found and fixed 2026-09-21)
**Pre-existing**, found while regression-testing item 20 — reproduced on the
unmodified generator, so it is not a consequence of that change.

    $ policy_translator.py -fw -o out examples/fml-paper-policy.txt
    KeyError: 'port'
    policy.py: serviceinfo = " --protocol " + cond['protocol'] + serviceport + str(cond['port'])

**It is three defects, and the crash is the least of them.** Measured on
`examples/fml-paper-policy.txt`, the only file in the tree that writes anything
but `'tcp'` or `'udp'`:

| declared | `roles_to_csv` | `to_iptables` |
|---|---|---|
| `protocol = 'arp'` | `protocol:arp` | `KeyError('port')` |
| `protocol = 1616` (int) | `protocol:1616` | `TypeError` (int + str) |
| `port = 22`, no protocol | `port:22` | **no rule at all** |

The third is silent and is the dangerous one: `serviceinfo` stayed empty and the
emission is guarded by `if serviceinfo`, so the rule vanished. Under a
default-deny ruleset the generated firewall silently withheld traffic the policy
**permits** — it no longer implements the specification it was derived from,
which is exactly what `bench/wl_generic_fw` exists to detect and cannot, because
no scenario there has a port-only service.

**And "emit `--protocol 1616`" would have been the wrong fix.** `protocol` maps
to `packet.ipv6.proto` in *both* consumers (`fave/util/match_util.py:36`,
`fave/iptables/generator.py:77`), and `normalize_ipv6_proto` accepts six names.
An IP protocol number is one byte, so 1616 is not one under any reading. Neither
target can represent these values; the matrix was compiling into checks the
verifier could not read.

- [x] **Validated at the declaration** (`UnknownProtocolException`), where the
      writer can act on it, rather than in one renderer.
      `protocol` is an IP protocol and nothing else (owner, 2026-09-21).
      Layer 2 is deliberately out of scope rather than forgotten: FPL says layer
      2 with role attributes (`vlan`), and a service-level `l2proto` would be
      the way to write ARP if a policy ever needs it — nothing does (owner).
- [x] **A protocol NUMBER is refused too**, even a valid one. 6 is tcp, but both
      consumers reach the field through a name table, so a number would be
      dropped downstream rather than understood. Refusing is honest until the
      vocabulary accepts numbers on *both* sides.
- [x] **`to_iptables` emits `--protocol <p>` with no port** when the service
      names none — icmp and gre carry none — and `str()`s the value.
- [x] **A port without a protocol is refused when writing iptables**
      (`PortWithoutProtocolException`), *not* at the declaration. The two
      targets genuinely differ: FaVe matches `packet.upper.dport` regardless of
      the upper protocol, so the shape is meaningful in the model and in the
      matrix; only iptables needs `-p` to reach a port match, and assuming tcp
      would invent policy.
- [x] **The duplicated vocabulary is pinned.** `Service.valid_protocols`
      restates `normalize_ipv6_proto`'s domain because `policy_translator/` is a
      standalone source root and must not import `fave/`.
      `fave/test/test_protocol_vocabulary_agrees.py` fails if the two drift, in
      either direction — guessing instead of checking is how `arp` and `1616`
      came to be written at all.
- [x] **Tests:** `policy_translator/test/test_service_protocol.py` (11) and the
      cross-tree test above (3). Mutation-verified four ways; widening the
      vocabulary with `arp` turns the cross-tree test red as well, which is the
      guard doing its job.
- [x] **Nothing else moves.** Every other inventory declares only `'tcp'` and
      `'udp'`: all nine workloads, `wl_generic_fw/default`, `examples/ifi-policy`
      and `examples/up-policy` produce byte-identical matrices, and every
      firewall scenario a byte-identical rule set.

**`examples/fml-paper-policy.txt` no longer compiles**, and that is the right
answer rather than a regression to absorb. It is an FML-paper policy using FML's
own notion of "protocol"; three of its services (`Prot1616`, `Prot1717`,
`Prot1818`) are not IP protocols, `ARP` is layer 2, and `SSH` names a port with
no protocol. Item 19's test on that file is replaced by one asserting **which**
refusal it gets — it now gets *past* the superrole and fails on its data — and
item 19's own property is asserted on fixtures, so no coverage is lost.

**Decided (owner, 2026-09-21): the example stays as it is and stays failing.**
Not an oversight and not a thing to tidy later — the file is an FML-paper
artifact, and what it exercises is FML's notion of "protocol", which FPL
deliberately does not have. Making it compile would mean editing published data
to fit a language it predates. If it is ever wanted as a working policy, `SSH`
needs a `protocol` and the `ProtNNNN` rules either go or wait for an
`l2proto`/raw-protocol attribute.

---

## Python codebase test expansion (fave/ + policy_translator/)

### 9. Expand Python test coverage per the testing strategy — Phase 1 + Phase 2 DONE (see [`TESTING_STRATEGY_PYTHON.md`](TESTING_STRATEGY_PYTHON.md))
**Scope: `fave/` and `policy_translator/` only — NOT `net_plumber/`** (the C++ backend's testing is items 7–8 and 1h/1i). The full module-by-module analysis, coverage table, principles, and prioritized roadmap live in `TESTING_STRATEGY_PYTHON.md`; this item is the actionable checklist.

- **Progress (2026-06-25):** Foundation + P0–P4 + the e2e `test_rpc` fix are DONE and committed on `testing`. Fast tier **136 → 248** (fave 90→189, PolicyTranslator 46→59); `test_rpc` (4 e2e tests) green against the installed backend; mypy clean throughout. 6 confirmed bugs fixed with regression tests; `remove_rule` (#5) intentionally left flagged (see below).
- **State (baseline):** ~69% measured coverage (`COVERAGE=1 ./test.sh all`), but `netplumber/adapter.py` and `aggregator/aggregator_service.py` were at **~0% (never imported by fast/integration)**, much coverage is symmetric golden-dict round-trips that hide wrong-but-consistent values, and several `__eq__`/`__hash__` methods are buggy so some tests pass by accident.
- **Guiding principles:** (1) prioritize pure verification-critical logic reachable without the native backend; (2) exploit existing seams — `FakeSocket`, `abstract_engine` (MockEngine), hand-built `Tree` ASTs (no pybison), `socket.socketpair()`; (3) assert behavior/invariants, not snapshots; (4) fix the `__eq__`/`__hash__` foundations first; (5) characterize→fix→flip for the confirmed bugs.

- [x] **Foundation: fix `__eq__`/`__hash__`.** `RuleField`/`Rule`/`AbstractDeviceModel` (fave) and `Policy`/`Role`/`Superrole` (PolicyTranslator) return `NotImplemented` on type mismatch; `Tree.__eq__` length fixed; `Policy.__eq__` now compares `policies`; `Role`/`Superrole.__eq__` compare dicts not zipped keys. (`Rule.__hash__` left as-is: coarser than `__eq__` but consistent — equal objects still hash equal, which is all the contract needs.) Commits `4e83a205`, `84e81991`.
- [x] **P0 — pure verification core.** `intersect_vectors`, `Vector.is_vector`/`from_vector_str`/`align_*`, `Match.intersect`/`RuleField.intersect`, `adapter._calc_rule_index`/`_calc_port`/`_expand_field`, `packet_util` denormalize/predicates/portrange/vlan, `ip6np_util` dispatch + normalizers. Commits `e479156c`, `9fd79a8b`.
- [x] **P1 — device models.** ALG/PF/snapshot wiring invariant (catches #2), generator/probe/ALG round-trips, snapshot `_swap_field`/`_reverse_quintuple`, firewall `add_rules` band expansion, router `_build_cidr` + `parse_cisco_acls`. (`remove_rule` (#5) left flagged; `add_state`, `parse_cisco_interfaces`, `to_iptables` edges remain as nice-to-haves.) Commits `0c040243`, `0c3943bd`.
- [x] **P2 — bridge via seams.** `aggregator_utils` framing via `socketpair`, `jsonrpc` encoders (`add_source` branch, `add_rules_batch`, `add_links_bulk` sharding), `_parse_servers`. (MockEngine-driven `_sync_diff` remains — needs a seam to skip the `Reporter` in `__init__`.) Commit `f6be8b50`.
- [x] **P3 — iptables generator.** `generate()` on hand-built ASTs: non-interweaving translation in detail + conntrack interweaving structurally. Commit `96067fea`.
- [x] **P4 — PolicyTranslator.** All 6 FPL operators' effect on `policy.policies` + the wrong-default ignored cases + non-strict self-reachability; exception paths (NameTaken/InvalidValue/InvalidSyntax/RoleUnknown). (`to_iptables` edges + `fpl_grammar` promotion remain.) Commit `9c07851c`. **Extended 2026-09-18:** the STRICT superrole path was untested in both directions and had a defect behind it — `Grp <--> Grp` granted every member a diagonal although strict mode exists to require an explicit self-rule (`TestSuperroleSelfExpansion`, APKEEP_BACKEND.md §10).
- [x] **Native/e2e tier — `test_rpc` GREEN.** single-socket→list (+ `print_np.py`), backend init lifecycle (destroy-to-clean + per-test init), `stop()` teardown (the old `stop_np.sh` never existed), source/probe `idx` threading, log path `/tmp`→`/dev/shm` + per-test truncation. Commit `6aa22ea4`. **Remaining:** negative parser tests (integration tier); make benchmark/`example.sh` sub-steps fail loudly (ties to 1p/1n — overlaps the net_plumber soundness work, coordinate).
- [x] **Coverage ratchet:** `test.sh` supports an opt-in `COVERAGE_MIN` floor (`coverage report --fail-under`); the CI `fast` job runs `COVERAGE=1 COVERAGE_MIN=79 bash test.sh fast` so coverage cannot drop below the floor. Floor currently **79%** (fast tier; raised from the 67% baseline by the backend-free test additions below + Phase 2). Bump the floor up as coverage rises, never down. A bare local `COVERAGE=1` run still just prints the report (no gate).
- [x] **Floor-raising test additions (backend-free, fast tier), 67% → 72%:** `policy.py` renderers + `to_html` + atomic/superrole resolution + `ReachabilityPolicy.update_conditions` (`test_policy_renderers.py`, policy.py 65%→82%); `to_iptables` IPv6 + list-address edges (`test_to_iptables.py`); switch CLI parse helpers + `SwitchCommand` (`test_switch.py`); `router.parse_cisco_interfaces` (`test_router.py`); the remaining `jsonrpc` encoders via `FakeSocket` (`test_jsonrpc_client.py`, jsonrpc 52%→78%); `snapshot.add_state` + iptables-`generator` pure helpers (`test_devices.py`, `test_generator.py`).

##### Phase 2 — backend/orchestration layer (DONE, see "Phase 2" in [`TESTING_STRATEGY_PYTHON.md`](TESTING_STRATEGY_PYTHON.md))
The remaining gap was the three modules exercised only by uncaptured e2e subprocesses; each is now unit-tested backend-free via a seam (assert the *contract*, not backend behavior). Sequenced with a ratchet bump per step.
- [x] **2a `netplumber/adapter.py`** (20%→67%) — `mock.patch('netplumber.adapter.jsonrpc')`; assert per-method RPC + bookkeeping for `add_tables/add_wiring/add_rules(_batch)/add_generator/add_probe` incl. the packet-filter pre/post-routing rule path and `_get_index_for_src` multi-digit-node handling. **No production change.** Commits `3747d418`, `4fadb450`.
- [x] **2b `aggregator/aggregator_service.py`** (20%→42%) — DI seam (`__init__(..., engine=None, reporter=None)`, default-preserving) drives `_sync_diff`/`_handler`/`_model_from_json` with a recording `MagicMock` engine + stub reporter; `_parse_servers` covered; pinned the `_dump_aggregator key>>12` ↔ adapter `<<12` coupling. **Found + fixed:** `SlicingCommand` never set `self.type`, so any slice routed through the aggregator crashed (`AttributeError`) before `add_slice`/`del_slice` — every sibling command sets it; demo bypasses the aggregator so it was uncaught. Commit `6aa506c5`.
- [x] **2c `reporting/reporter.py`** (→86%) — extracted `_parse_log_line(tokens)` from `run()` (pins the brittle fixed-index NetPlumber-log parse); tested `_parse_cond` (pure) and `dump_report`'s compliance + shadowed-rule paths with a `SimpleNamespace` `fave` facade over `/dev/null`. Commit `074ae8c5`.
- [x] **Bumped `COVERAGE_MIN`** after each step: 75 → 78 (2b) → 79 (2c). Fast-tier total now **79%**.

#### Confirmed bugs (→ characterize→fix→flip regression tests; full table in `TESTING_STRATEGY_PYTHON.md`)
- [x] **#1 `rule/rule_model.py`** — `Match.intersect` sorted `self` twice / had a broken merge; **live via `iptables/generator.py:472`** (conntrack). FIXED: proper ordered merge (+ regression for the multi-field edge case). Commits `23860da4`/`40059c30` (user) + `a7b46f01` (merge rewrite + tests).
- [x] **#2 `devices/application_layer_gateway.py:160`** — wired `relays_out` but port is `relay_out`. FIXED + wiring-invariant test. Commit `0c040243`.
- [x] **#3 `util/tree_util.py`** — `Tree.__eq__` `zip` ignored length. FIXED (len check) + regression. Commit `4e83a205`.
- [x] **#4 `util/match_util.py`** — `'upd_src'`→`udp_src` typo (test had enshrined it). FIXED. Commit `a7b46f01`.
- [ ] **#5 `devices/abstract_firewall.py:194` — LEFT FLAGGED (your call).** Broken beyond the `_routing`/`.routing` typo: `add_rules` buffers into `_adds` but `remove_rule` reads `self.tables` and the band-indexed `del`s would `IndexError`. Correct semantics aren't determinable from the code (likely-dead path); not auto-fixed to avoid a speculative rewrite of verification buffer logic.
- [x] **#6 (found while testing) `util/aggregator_utils.py`** — `fave_sendmsg` framed `len(chars)` not `len(bytes)`, truncating non-ASCII payloads. FIXED + socketpair regression. Commit `f6be8b50`.
- [x] **`_calc_port` fallback** — caught only `KeyError` but `port_index` raises `ValueError`, making the fallback unreachable. FIXED. Commit `a7b46f01`.
- Lower-severity (still flagged, not fixed): `bench_utils.py:134` dead `-s` append; `router._build_cidr` `round(log2)` (exact for valid contiguous masks — only non-contiguous/invalid masks are affected); router `persist` CAPACITY=16 VLAN `aid` collision; dead `else: raise` in two `ip6np_util` normalizers.

#### Field-value canonicalization — DONE (commit `a93712f2`, 2026-06-25)
- [x] **Canonicalize address/protocol field values at `RuleField` construction.**
- **Finding (design discussion w/ user):** A field value has several equivalent spellings — IPv6 syntax variants (`2001:db8::1` == `2001:db8:0:0:0:0:0:1`), CIDR compact/expanded, protocol by name vs IANA number (`tcp` == `6`). All collapse to one bit-vector in the adapter, so the **verification verdict was always representation-agnostic**. But model *equality* compares the raw value strings (`RuleField.__eq__`), and that equality drives the **aggregator's incremental diff** (`model - self.models[node]` → `AbstractDeviceModel.__sub__` → `list_sub` → `Rule.__eq__` → `RuleField.__eq__`). So two equivalent rules written differently were treated as different rules → an update could push a duplicate and fail to retract the stale one. Latent (the build pipeline is deterministic today) but a real correctness fragility on the continuous-verification path, not just a test concern. (Audit: values are bit-vectorized in only 3 places — `adapter.py`, `RuleField.intersect`, the cchecks tool — but compared as strings in the diff; no field value is used as a dict key / set member.)
- **Decision:** normalize at the input boundary (**`RuleField.__init__`**, the one chokepoint all ~8 construction paths and `from_json` funnel through) rather than on every `__eq__` — chosen over per-compare normalization for performance (the diff is O(n²)) and as standard "canonicalize at the boundary" hygiene. Contract stays broad (nothing rejected). `util/packet_util.canonicalize_field_value()` maps IPv4/IPv6 address fields → compressed form and `packet.ipv6.proto` → IANA number.
- **Properties:** total + idempotent (non-strings, unparseable addresses, unknown protocols, and other fields pass through unchanged); **bit-vector-preserving** (canonical value yields the same header space — asserted by a test, so verification is unaffected); **scoped** — fields read by keyword elsewhere (`module.state`/`module` in `generator.py:52,57,506`, port names) are deliberately left untouched (reader-audit confirmed proto has zero value-readers).
- **Follow-up:** the scoped field set lives in `_IP_ADDRESS_FIELDS` / the proto branch of `canonicalize_field_value` — extend there if a new representationally-ambiguous field type appears. Open option (not done): mirror the same canonicalization on the C++/NetPlumber side or in PolicyTranslator output if those ever feed un-normalized values into comparisons.

---

## Resolved questions

- **Is the GitLab pipeline still the active CI?** No — GitLab CI is inactive and will remain so. Migrating to GitHub Actions (item 0).
- **Is dropping Python 2 support intended?** Yes — drop Python 2 entirely and fix all `python2`/bare `python` references (item 1).

---

## Suggested order of work

1. ~~Item **1** (Python 3)~~ ✅ · ~~Item **1b** (`test.sh` runner)~~ ✅ · ~~Items **4, 5**~~ ✅ (absorbed by 1b) · Item **3** mostly ✅.
2. Item **0** (GitHub CI migration) — now thin: jobs just call `./test.sh <tier>`. Plus item **2** (gating lint). Items **1r** (done) and **1s** (open — the `bench` verdict gate, plus a grounded wl_i2 discrepancy to root-cause first) belong here too: it is the one *gating-validity* defect left in the tier design (the `bench` tier currently cannot fail on a wrong verdict), and it blocks item 0's `bench` validation.
3. Item **1c** (triage quarantined `test_grammar`) and item **6** (mypy) — structural.
4. Items **7–8** (deeper, verification-specific — `net_plumber/` C++ backend). Item **7** is planned in [`TESTING_STRATEGY_CXX.md`](TESTING_STRATEGY_CXX.md). **Done so far:** bug regressions #C1/#C2/#C3, the P0 header-space oracle/law harness (found+fixed engine bugs #C4/#C5), P1 orchestrator API contract tests, and P2 conditions/RPC-parser tests (found+fixed RPC crash #C6); `net_plumber --test` → OK (117). **All planned C++ hardening items are now done** (bug regressions #C1–#C8, the P0 oracle, P1 API contracts, P2 conditions/RPC + the depth guard + `check_compliance` hardening, the probe-transition de-chaining, the `sanitizers` job, and the `coverage-cxx` job). `net_plumber --test` → OK (118), clean under ASan+UBSan+LSan. *(Remaining ideas, optional/future: the `test_routing_remove_*` / `test_*_probe` tests still chain among themselves — only the probe-transition→routing cascade was addressed; a coverage ratchet ("must not drop") could later gate `coverage-cxx`; the engine `array.c`/`hs.c` line coverage is low (~12-14%) and could be raised by extending the oracle's law/scenario coverage.)*
5. Item **9** — expand the `fave/` + `policy_translator/` Python test coverage per [`TESTING_STRATEGY_PYTHON.md`](TESTING_STRATEGY_PYTHON.md) (the user's stated next phase). Start with the `__eq__` foundation fixes + P0.
6. Item **10** (separate research track, longer-term) — APKeep as an alternative backend, planned in [`APKEEP_BACKEND.md`](APKEEP_BACKEND.md). Start with P0 (fork+subtree+build) and P1 (`libnetplumber`, the low-risk standalone win). **APKeep→NDD follow-on is COMPLETE** — see [`APKEEP_NDD_PLAN.md`](APKEEP_NDD_PLAN.md) / [`APKEEP_NDD_EVAL.md`](APKEEP_NDD_EVAL.md) (NDD is a selectable second engine; uncapped BDD-faithful measurements done, §2.6b).
7. Item **11** (separate research track, longer-term) — ad6 as a generic SAT/QBF backend for the specialization-vs-genericity comparison, planned in [`AD6_PLAN.md`](AD6_PLAN.md). **Theory-first** (§1 cost model + GO/NO-GO gate) before any code revival.
