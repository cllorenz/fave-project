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
  - [ ] **Map GitLab stages to jobs with `needs:`** (GitHub has no global `stages:` — use job dependencies):
    - [ ] `build-np` → `make -j -C net_plumber/build` (depends on `build-image`).
    - [ ] `lint-fave` → `bash fave/test/lint_test.sh` (see item 2 — must actually gate).
    - [ ] `test-np` → `make -j -C net_plumber/build test`.
    - [ ] `test-fave` → `python3 -m coverage run fave/test/unit_tests.py` then `python3 -m coverage report` (see items 1 & 3; no more `python2-coverage`).
    - [ ] `test-fpl` → `python3 policy_translator/test/unit_tests.py` with `PYTHONPATH=policy_translator`.
    - [ ] `deploy-fave` → `make install` + `python3 fave/test/test_rpc.py` + `bash fave/examples/example.sh`.
    - [ ] `bench-*` → the example/ifi/up/tum benchmark invocations (`python3 …/benchmark.py`).
  - [ ] **Set env once.** Use a workflow-level `env:` for `DIRPATH` and `PYTHONPATH` (job-level override for `test-fpl`). Drop all `python2`/bare `python` calls in favor of `python3`.
  - [ ] **Gate vs. non-gate.** Make `build`, `lint`, and `test` jobs required for merge (branch protection). Make the heavy `bench-*` jobs non-blocking — either `workflow_dispatch`-only, scheduled (`on: schedule`), or `continue-on-error: true` — so PRs aren't held up by long benchmark runs.
  - [ ] **Artifacts & reporting.** Upload the coverage report and pylint logs via `actions/upload-artifact`. Optionally add a coverage summary to the job step summary.
  - [ ] **Verify, then retire GitLab.** Once the GitHub workflow is green, delete `.gitlab-ci.yml` and update the README/badges to point at GitHub Actions.
- **Depends on / pairs with:** item 1 (Python 3 only), item 2 (lint must gate), item 3 (coverage report), item 4 (a `requirements.txt` would let the workflow install deps without rebuilding the whole image for pure-Python jobs).

### 1. Resolve Python 2 vs 3 drift (CONFIRMED: drop Python 2)
- [ ] **Drop Python 2 entirely; make everything Python 3**
  - [ ] Delete the remaining 10 py2 shebangs.
  - [ ] Replace any `python2`/bare `python` references with `python3` wherever found (scripts, docs, CI).
  - [ ] Reconcile `fave/examples/example.sh` vs `example/example.sh` path drift.
  - [ ] Fold corrected commands into the new GitHub workflow rather than the retired `.gitlab-ci.yml`.
- **Finding:** Code is Python 3 (129 py3 shebangs vs 10 py2; `Dockerfile` installs `python3*` and runs `python3 fave/test/unit_tests.py`; README uses `python3`). The old `.gitlab-ci.yml` still calls `python2`, `python2-coverage`, and bare `python` in 9 places.
- **Decision:** GitLab CI is inactive and stays that way → migrate to GitHub CI (see item 0). Drop Python 2 entirely.

### 2. Make linting gate the pipeline
- [ ] **Make lint failures fail CI**
  - [ ] Commit a `.pylintrc` (pin the rules that matter).
  - [ ] Make `fave/test/lint_test.sh` exit non-zero when `$FAILS` is non-empty (or gate on a minimum score).
- **Finding:** `fave/test/lint_test.sh` records pass/fail counts but always exits 0, so `lint_fave` can never fail. No committed `.pylintrc`, so pylint runs on defaults with no enforced floor.

### 3. Re-enable coverage reporting
- [ ] **Report (and optionally gate) coverage**
  - [ ] Re-enable and print `coverage report` in the test job.
  - [ ] Optionally add `--fail-under` so coverage cannot silently regress.
- **Finding:** CI runs `coverage run` but `coverage report` is commented out (`# && python2-coverage report`). Coverage is paid for but never seen.

---

## Medium priority — structural improvements

### 4. Add a dependency manifest
- [ ] **Add a pinned dependency manifest**
  - [ ] Add a pinned `requirements.txt` (or `pyproject.toml`).
  - [ ] Have the `Dockerfile` install from it instead of unpinned inline `pip` lines.
- **Finding:** No `requirements.txt` / `pyproject.toml` anywhere; dependencies live only as unpinned `apt`/`pip` lines in the `Dockerfile`. Env is not reproducible outside Docker.

### 5. Replace the manual test registry with discovery
- [ ] **Use test discovery instead of a hand-maintained registry**
- **Finding:** `fave/test/unit_tests.py` hand-imports and hand-registers every `TestCase`; new tests silently don't run until someone edits this file.
- **Fix:** Switch to `unittest` discovery (`python3 -m unittest discover`) or adopt `pytest` (better output, fixtures, parametrization).

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

1. Item **0** (GitHub CI migration) together with items **1–3** (Python 3, gating lint, coverage) — the new workflow should embed these fixes rather than port the broken ones.
2. Items **4–6** (structural).
3. Items **7–8** (deeper, verification-specific).
