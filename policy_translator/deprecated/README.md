# Deprecated

Code kept for reference but **not part of the active codebase or test suite**.
This directory is outside the pytest collection root and is excluded from tooling
(see the repo-wide `pytest.ini` `norecursedirs` and `lint_test.sh`).

## Contents

- `test_grammar.py` — AI-generated (CodiumAI) FPL-grammar tests from an
  unfinished experiment. Never wired into a test runner, never ran; its expected
  parse trees do not match `fpl_grammar.parse_fpl()` output (stale expectations,
  not a dependency-version issue). Kept in case a proper FPL-grammar test effort
  is revisited.
