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

### 0. Migration to GitHub CI
- [ ] **Migrate CI from GitLab to GitHub Actions**
- **Decision:** GitLab CI is inactive and will remain so. The project moves to GitHub Actions. The old `.gitlab-ci.yml` is the reference for *what* to run, but should be retired once the GitHub workflow is in place.
- **Source of truth for steps:** the existing `.gitlab-ci.yml` (stages `pre → build → test → deploy → bench`) and the `Dockerfile` (already Python 3, builds NetPlumber, runs unit tests + example + benches).

  Implementation steps:
  - [ ] **Create the workflow skeleton.** Add `.github/workflows/ci.yml` triggered on `push` and `pull_request` (and `workflow_dispatch` for manual runs). Pin `runs-on: ubuntu-24.04` to match the `Dockerfile` base and the README's tested platform.
  - [ ] **Build the container once, reuse it.** Add a `build-image` job that builds the `Dockerfile` and pushes it to GHCR (`ghcr.io/<owner>/fave`), using `docker/build-push-action` with GitHub Actions layer caching (`cache-from`/`cache-to: type=gha`). Downstream jobs run with `container: ghcr.io/<owner>/fave:<sha>` so they don't rebuild. (Replaces the GitLab `build_docker` job and the `sudo docker run …` pattern in every job.)
  - [ ] **Map jobs to `test.sh` tiers with `needs:`** (GitHub has no global `stages:` — use job dependencies). CI invokes `test.sh`, it does *not* redefine tests:
    - [ ] `build-np` → `make -j -C net_plumber/build` (depends on `build-image`).
    - [ ] `lint-fave` → `bash fave/test/lint_test.sh` (see item 2 — must actually gate).
    - [ ] `test-fast` → `./test.sh fast` (can even run outside the image, on a plain `pip install -r requirements.txt`).
    - [ ] `test-integration` → `COVERAGE=1 ./test.sh integration` inside the image (covers C++ `make test`, bison tests, RPC, smoke; emits coverage).
    - [ ] `bench` → `./test.sh bench` (non-blocking — see gating below).
  - [ ] **Set env once.** Use a workflow-level `env:` for `DIRPATH` and `PYTHONPATH` (job-level override for `test-fpl`). Drop all `python2`/bare `python` calls in favor of `python3`.
  - [ ] **Gate vs. non-gate.** Make `build`, `lint`, and `test` jobs required for merge (branch protection). Make the heavy `bench-*` jobs non-blocking — either `workflow_dispatch`-only, scheduled (`on: schedule`), or `continue-on-error: true` — so PRs aren't held up by long benchmark runs.
  - [ ] **Artifacts & reporting.** Upload the coverage report and pylint logs via `actions/upload-artifact`. Optionally add a coverage summary to the job step summary.
  - [ ] **Verify, then retire GitLab.** Once the GitHub workflow is green, delete `.gitlab-ci.yml` and update the README/badges to point at GitHub Actions.
- **Depends on / pairs with:** item 1 (Python 3 only), item 2 (lint must gate), item 3 (coverage report), item 4 (a `requirements.txt` would let the workflow install deps without rebuilding the whole image for pure-Python jobs).

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
