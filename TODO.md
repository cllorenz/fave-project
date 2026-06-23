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
- **Decision (with user):** chose explicit output headers over a test-side pattern classifier. Justified as an independent **readability/audit** feature for human reviewers, not test-only scaffolding. Headers reflect the *current* (per-protocol) block structure; they will be revised together with item 1f if the generator is restructured to match Algorithm 7.1's functional blocks.

### 1f. Generator structure diverges from Algorithm 7.1 (Suppress list) — OBSERVE, defer
- [ ] **Reconcile `to_iptables()` structure with Algorithm 7.1's `Suppress + Main`.**
- **Finding:** Algorithm 7.1 (thesis §7.3) prepends a separate `Suppress` list and returns `Suppress + Main`. The code instead inlines stateless suppression as `raw PREROUTING ... -j NOTRACK` rules adjacent to each access rule, rather than as a prepended block. Different table/chain, so semantically equivalent, but the *structure* differs from the documented concept. Not material to item 1d; flagged for later review (does the concept or the code need updating?).

### 1g. `test_rpc` backend dependency — RESOLVED via e2e tier split
- [x] **Introduced an `e2e` tier and made `integration` deterministic + gating.**
  - [x] `test.sh` now has three native-stack tiers split by dependency footprint: `integration` = NetPlumber C++ `make test` + bison tests (`test_topology`, `test_packet_filter`, `test_iptables_parser`) — needs build + pybison but **no live backend** → deterministic, **gates**; `e2e` = `test_rpc` + smoke (`example.sh`, `wl_example`, `wl_ifi`) — needs a running net_plumber + `/dev/shm` → **non-gating** for now.
  - [x] Fixed the `test_rpc` port mismatch: it called `start_np.sh` (defaults to `44001`) but connected to `1234`. Now starts with `-p 1234` to match the connect port. (The `jsonrpc.py` format bug fixed earlier was masking this as a `TypeError`.)
  - [x] Fixed `test_packet_filter::TestSwitchModel` (`test_to_json`/`test_from_json`): removed `raw_line`/`raw_line_no` from the **device-level** expected dicts. **Root cause confirmed via git history (user-verified):** origin tracking is a *rule* property — added to the `Rule` model by `ee07118f` and correctly emitted there. Commit `de8e5311` ("Fix broken tests due to model changes") updated test expectations for the new rule-level field but **over-applied** it to the device/switch-level dicts (before `'type':'switch'`); `AbstractDeviceModel`/`SwitchModel` never carried those fields (no commit ever touched `raw_line` under `fave/devices/`). The broken assertions went unnoticed because `test_packet_filter` (bison-dependent) wasn't being run. Confirmed design: **rules carry origin, devices don't.** All remaining `raw_line` in the file is rule-level and correct. (Verified by reading + history, not run — needs pybison; next CI run confirms.)
  - [x] CI: `integration` job gates (no `continue-on-error`); new `e2e` job is `continue-on-error: true`. Extracted a composite action `.github/actions/setup-fave-native` so integration/e2e/bench share the heavy native setup (DRY).
  - [ ] **Client-contract test (agreed, still TODO):** add a fast-tier mock-socket test for `jsonrpc.py` (validates request encoding / response parsing without a backend). See item 1k.
  - [ ] **Promote `e2e` to gating** once backend startup is proven reliable on real CI.
- **Note:** `integration` gating is currently effective for the build + bison Python tests; the C++ `make test` failures are still *silent* (exit 0), so the gate does not yet catch them — see items 1h (triage) and 1i (make `make test` propagate).

### 1h. C++ `test_compact_regression` fails (2 assertions) — TO DISCUSS
- [ ] **Triage `HeaderspaceTest::test_compact_regression` (`hs_unit.cc:1936`, `:1965`).**
- **Finding:** `make test` reported "Run: 92, Failures: 2" but **exited 0**, so the failures were silent (did not fail the job). Real C++ test failures on Ubuntu 24.04 — need to determine if code regression or test/platform assumption.

### 1i. Silent failures / non-gating commands — TO ADDRESS
- [ ] **Make `make test` propagate C++ failures** (currently exits 0 despite failures — see 1h) so `test.sh integration` actually gates on them.
- [ ] **Surface `example.sh` flow-test failures**: the script does `... || echo "some example flow tests failed"` and exits 0. "some example flow tests failed" appeared in CI but was swallowed. Decide: make it fail, or move to the backend-dependent tier (1g).
- **Theme:** same "checks that don't gate" smell as the lint script (item 2) and the old coverage report (item 3).

### 1j. `\-` SyntaxWarning (py3 cleanliness) — confirmed in two files
- [ ] **Make the regex strings raw strings.** `fave/iptables/parser.py:487` and `policy_translator/policy_builder.py:33` both emit `SyntaxWarning: invalid escape sequence '\-'`. Trivial; batch with a broader raw-string sweep if desired.

### 1k. Fast-tier RPC client-contract test — TODO (agreed)
- [ ] **Add a mock-socket test for `netplumber/jsonrpc.py` in the fast tier.**
- **Rationale (with user):** mocking is the right tool for the *client/protocol* surface (does each RPC function emit the correct JSON request, and parse responses?), but NOT for replacing `test_rpc` (whose log assertions validate NetPlumber's engine — a mock there would either assert nothing or reimplement the engine → false confidence). The mock must be derived from the **JSON-RPC interface contract**, not the C++ internals (keeps the maintenance surface small/stable). Fast, local, no backend.

### 1l. NetPlumber port convention is inconsistent — TODO
- [ ] **Pick one default port and apply it consistently.** `1234` is used by `test_rpc`, `scripts/test_all.sh`, `print_np.py`, `check_compliance.py`, `demo_slicing.py`; `44001` is `jsonrpc.NET_PLUMBER_DEFAULT_PORT` and `start_np.sh`'s default. `test_rpc` was relying on a mismatch (now patched locally with `-p 1234`). Consolidate to avoid the next surprise.

### 1m. pandoc PDF report needs a LaTeX engine — TODO (low priority, e2e/non-gating)
- [ ] **Decide how report PDFs are produced in CI.** With pandoc now installed, `pandoc report.md -o report.pdf` fails: `pdflatex not found ... install pdflatex`. Our `--no-install-recommends` skipped the recommended `texlive-*`. Options: install a LaTeX engine (e.g. `texlive-latex-base`/`texlive-xetex`), switch pandoc to a non-PDF target (HTML) or `--pdf-engine`, or accept it as non-fatal (it is — only the smoke report PDF). Lives in the e2e tier, so non-blocking.

### 1n. wl_ifi smoke: PolicyTranslator input not read + swallowed failure — TODO (e2e/non-gating)
- [ ] **Fix the wl_ifi policy-matrix input path (CI) and stop the benchmark swallowing the failure.** `policy_translator.py:67` prints `"Fehler: Datei(en) konnte(n) nicht gelesen werden."` and `sys.exit(1)` when it can't open its input files; in CI the wl_ifi benchmark passes a path that doesn't resolve (likely CWD/relative-path), yet proceeds ("generated policy matrix") — the non-zero exit is ignored. Two sub-issues: (a) the input path resolution in CI; (b) the benchmark swallowing a failed sub-step (same "silent failure" theme as 1i). Minor extra: the error string is hardcoded German in an otherwise-English codebase.

### 2. Make linting gate the pipeline
- [ ] **Make lint failures fail CI**
  - [ ] Commit a `.pylintrc` (pin the rules that matter).
  - [ ] Make `fave/test/lint_test.sh` exit non-zero when `$FAILS` is non-empty (or gate on a minimum score).
- **Finding:** `fave/test/lint_test.sh` records pass/fail counts but always exits 0, so `lint_fave` can never fail. No committed `.pylintrc`, so pylint runs on defaults with no enforced floor.

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

### 6. Add static type checking
- [ ] **Add `mypy` to the lint stage for core modules**
- **Finding:** Only 3 files use type hints. A silent type/shape error undermines the soundness story of a verification tool.
- **Fix:** Add `mypy` (even lenient) to the lint stage, focused on core `rule/`, `devices/`, `netplumber/` modules.

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
