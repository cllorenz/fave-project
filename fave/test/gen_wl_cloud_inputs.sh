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
#     -> topology/routes/sources/policies.json + mapping.json
#                                   DERIVED from network.tf and from the FPL
#                                   policy, which decides which endpoints are
#                                   instantiated (cloud_tf.py,
#                                   cloud_endpoints.py, cloud_preparation.py)
#     -> reachability.csv + checks.json
#                                   the translator's matrix and the checks it
#                                   compiles to. The two FPL files it reads
#                                   (roles_and_services.txt, reach.txt) are the
#                                   one thing here NOT derived: a policy is an
#                                   intent, so they are hand-written and
#                                   tracked. The MATRIX phase's pair under
#                                   matrix/ is derived, from cloud-tf/README.txt
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

# model: network.tf + the ORACLE PHASE's FPL -> FaVe's topology/routes/probes.
#
# The FPL comes first, and not for tidiness: the policy decides which of the
# 1,201 endpoints are instantiated, and every generator costs a full flow
# propagation whether a check asks about it or not. `roles.json` is the
# translator's own record of what each role resolved to, which is what
# `role_members` checks the model against.
"$PYTHON" ../policy_translator/policy_translator.py --strict \
    --roles bench/wl_cloud/roles.json \
    --csv --out bench/wl_cloud/reachability.csv \
    bench/wl_cloud/roles_and_services.txt bench/wl_cloud/reach.txt

"$PYTHON" - <<'PY'
import json
from bench.wl_cloud.benchmark import _PREFIX
from bench.wl_cloud.cloud_endpoints import derive_endpoints, role_members
from bench.wl_cloud.cloud_preparation import build_model, write_model
from bench.wl_cloud.cloud_tf import FAVE_MAPPING, classify_nodes, parse_tf

files = {
    'topology': '%s/topology.json' % _PREFIX,
    'routes': '%s/routes.json' % _PREFIX,
    'sources': '%s/sources.json' % _PREFIX,
    'policies': '%s/policies.json' % _PREFIX,
}
rules = parse_tf(open('%s/cloud-tf/network.tf' % _PREFIX, 'r'))
model = classify_nodes(rules)
members = role_members('%s/roles.json' % _PREFIX, derive_endpoints(model))

write_model(build_model(rules, model, role_members=sorted(
    members.values(), key=lambda m: m.name)), files)

with open('%s/inventory.json' % _PREFIX, 'w') as out:
    out.write(json.dumps(
        dict((role, [member.name]) for role, member in members.items()),
        indent=2) + '\n')
with open('%s/mapping.json' % _PREFIX, 'w') as out:
    out.write(json.dumps(FAVE_MAPPING, indent=2) + '\n')

print("model: %d devices, %d rules, %d roles" % (
    len(model.devices), len(rules), len(members)))
PY

"$PYTHON" bench/reach_csv_to_checks.py --strict --complement \
    -p bench/wl_cloud/reachability.csv -m bench/wl_cloud/inventory.json \
    --roles bench/wl_cloud/roles.json -c bench/wl_cloud/checks.json \
    --cchecks bench/wl_cloud/cchecks.json -j bench/wl_cloud/reachable.json

# The POLICY phase's sources (C7, CLOUD_BENCH_PLAN.md §1.9.6). Emitted here as
# well as by the benchmark, so the FPL can be inspected -- and the inventory
# round-trip checked -- without a backend. Both policies, because they are two
# measurements of the same data plane and neither is the default. Under
# matrix/, because these are GENERATED and the two files of the same name one
# level up are hand-written inputs the oracle phase reads.
"$PYTHON" - <<'POLICY'
import os

from bench.wl_cloud.cloud_policy import (
    cloud_inventory, emit_inventory, emit_policy, role_endpoints)
from bench.wl_cloud.cloud_readme import read_readme

readme = read_readme('bench/wl_cloud/cloud-tf/README.txt')
inventory = emit_inventory(readme)

os.makedirs('bench/wl_cloud/matrix', exist_ok=True)

for name, text in (
        ('roles_and_services.txt', inventory),
        ('reach.txt', emit_policy(readme)),
        ('reach_public.txt', emit_policy(readme, public=True)),
):
    with open('bench/wl_cloud/matrix/%s' % name, 'w') as out:
        out.write(text)

# The FPL is the authority, not `role_endpoints`: the benchmark reads its
# inventory back out of the file the translator parsed, so drift between the
# two is what this asserts away (TODO item 14's defect).
assert cloud_inventory(inventory) == role_endpoints(readme), \
    "the emitted inventory does not read back as the endpoint mapping"

print("policy: %d roles, %d endpoints, %d authorised pairs" % (
    len(readme.roles),
    sum(len(v) for v in role_endpoints(readme).values()),
    len(readme.authorised_pairs())))
POLICY

echo "wl_cloud inputs generated under bench/wl_cloud/"
