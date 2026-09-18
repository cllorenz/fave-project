#!/usr/bin/env bash

# Regenerate every wl_cloud input from the vendored RAW scenario -- nothing this
# workload reads is written by hand.
#
# Chain, all of it scripted:
#
#   bench/wl_cloud/cloud-tf/        the raw cloud/base scenario, TRACKED,
#                                   covered byte-for-byte by SHA256SUMS. This
#                                   IS the raw data as far as the repository is
#                                   concerned -- the source archive is not kept,
#                                   and git is what reveals an edit to these
#                                   files (owner decision 2026-09-18).
#     -> oracle.json                DERIVED from the six .smt2 instances
#                                   (cloud_oracle.py): source, target, header
#                                   constraints and the sat/unsat verdict each
#                                   filename carries
#     -> topology/routes/sources/policies.json + mapping.json + checks.json
#                                   DERIVED from network.tf + oracle.json
#                                   (cloud_tf.py + cloud_preparation.py)
#
# Everything after the first arrow is gitignored, and this script rebuilds it.
# The point is CLOUD_BENCH_PLAN.md §1.8: a benchmark that cannot be recreated
# from its raw data is a measurement resting on whatever someone edited last.
#
# Usage:
#   bash fave/test/gen_wl_cloud_inputs.sh

set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # -> fave/
PYTHON="${PYTHON:-python3}"
export PYTHONPATH="$(pwd)"

RAW=bench/wl_cloud/cloud-tf

# Integrity BEFORE derivation. A byte that changed here silently changes what
# the benchmark measures, and a manual edit made while debugging is exactly how
# that happens. Complementary to git rather than a replacement for it: git
# reveals a committed change to the raw scenario, this catches an uncommitted
# one at the moment it would affect a measurement.
echo "verifying the raw scenario against $RAW/SHA256SUMS"
( cd "$RAW" && sha256sum -c SHA256SUMS --quiet )

# oracle: the six .smt2 instances -> oracle.json.
"$PYTHON" - <<'PY'
import json
from bench.wl_cloud.cloud_oracle import derive_oracle
oracle = derive_oracle('bench/wl_cloud/cloud-tf')
with open('bench/wl_cloud/oracle.json', 'w') as out:
    out.write(json.dumps(oracle, indent=2) + '\n')
print("oracle: %d queries derived (%s)" % (
    len(oracle['queries']),
    ", ".join("%s=%s" % (q['name'], q['expect']) for q in oracle['queries'])))
PY

# model: network.tf + oracle.json -> FaVe's topology/routes/sources/probes.
"$PYTHON" - <<'PY'
import json
from bench.wl_cloud.benchmark import load_queries, build_checks, _PREFIX
from bench.wl_cloud.cloud_preparation import build_model, write_model
from bench.wl_cloud.cloud_tf import CLOUD_MAPPING, classify_nodes, parse_tf

files = {
    'topology': '%s/topology.json' % _PREFIX,
    'routes': '%s/routes.json' % _PREFIX,
    'sources': '%s/sources.json' % _PREFIX,
    'policies': '%s/policies.json' % _PREFIX,
}
rules = parse_tf(open('%s/cloud-tf/network.tf' % _PREFIX, 'r'))
model = classify_nodes(rules)
queries, spec = load_queries('%s/oracle.json' % _PREFIX)

write_model(build_model(rules, model, queries=queries), files)

with open('%s/checks.json' % _PREFIX, 'w') as out:
    out.write(json.dumps(build_checks(queries, spec), indent=2) + '\n')
with open('%s/mapping.json' % _PREFIX, 'w') as out:
    out.write(json.dumps(CLOUD_MAPPING, indent=2) + '\n')

print("model: %d devices, %d rules" % (len(model.devices), len(rules)))
PY

echo "wl_cloud inputs generated under bench/wl_cloud/"
