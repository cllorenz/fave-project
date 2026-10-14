# Deprecated

Code kept for reference but **not part of the active codebase or test suite**.
Nothing live imports it. It is outside the pytest collection (`pytest.ini`
`norecursedirs`), pruned by `lint_test.sh`, and omitted from the `fast` tier's
coverage scope (`coverage-fast.ini`). Moved here 2026-10-14 by owner decision
(TODO item 47).

## Contents

- `dynamic_distribution.py` — distributed NetPlumber node/link dispatch. Built on
  `asyncore`, which Python 3.12 removed, so it no longer imports. Its call sites in
  `netplumber/jsonrpc.py` and `aggregator/aggregator_service.py` were already
  commented out.
- `parallel_utils.py` — SLURM node-list parsing and NetPlumber instance shutdown
  for the distributed set-up. Referenced only from commented-out benchmark code.
- `aggregator_mock.py` — a stand-in aggregator socket. No users.
