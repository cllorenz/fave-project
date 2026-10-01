#!/usr/bin/env python3

""" wl_up's FPL inventory: role -> the model hosts that role stands for.

Reads the FPL inventory and the reachability matrix derived from it, and writes
`inventory.json` for `bench/reach_csv_to_checks.py`.

THE THREE PATHS ARE ARGUMENTS (TODO item 37). They used to be string literals in
the body, which made this script runnable against exactly one tree -- the real
one. `test_wl_up_policy_artifacts.py` built a matrix in a temporary directory and
then invoked this script under the comment "inventorygen reads the matrix, so it
runs against the one just built", which was not true: it read
`bench/wl_up/reachability.csv` and wrote `bench/wl_up/inventory.json`, so the
test validated the tracked matrix rather than the one it had derived, and a unit
test wrote into the source tree. The defaults below are those former literals, so
the two zero-argument callers -- `test/gen_wl_up_inputs.sh` and
`GenericBenchmark._preparation` -- are unchanged.
"""

import argparse
import ast
import csv
import json

_W = 'bench/wl_up'

#: Roles with no `hosts` line in the FPL, because each stands for a whole subnet
#: rather than for enumerated machines: `Internet` for everything off-campus and
#: `Wifi` for the client /64. Their model node is named here instead.
_SUBNET_ROLES = {
    'Internet': ['internet'],
    'Wifi': ['clients.wifi.uni-potsdam.de'],
}


def build_inventory(fpl_path, matrix_path):
    """ role -> model hosts, from the FPL inventory, checked against the matrix.

    Every column of the matrix must be a role the FPL defines; a column that is
    not means the two have drifted apart, and the check set built from them
    would silently address a role with no members.
    """
    roles = {role: list(hosts) for role, hosts in _SUBNET_ROLES.items()}

    with open(fpl_path, 'r') as handle:
        role = None
        for line in handle.read().splitlines():
            token = line.lstrip().split(' ')
            if len(token) == 3 and token[0] == 'def':
                role = token[2]
            elif len(token) > 2 and token[0] == 'hosts':
                roles.setdefault(role, [])
                roles[role].extend(ast.literal_eval(' '.join(token[2:])))

    with open(matrix_path, 'r') as handle:
        for role in next(csv.reader(handle, delimiter=','))[1:]:
            assert role in roles, (
                "%s has a column for role %r, which %s does not define"
                % (matrix_path, role, fpl_path))

    return roles


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--fpl', default='%s/roles_and_services.txt' % _W,
                        help="the FPL inventory to read roles from")
    parser.add_argument('--matrix', default='%s/reachability.csv' % _W,
                        help="the reachability matrix whose columns are checked")
    parser.add_argument('--out', default='%s/inventory.json' % _W,
                        help="where to write the role -> hosts mapping")
    args = parser.parse_args(argv)

    with open(args.out, 'w') as out:
        json.dump(build_inventory(args.fpl, args.matrix), out, indent=2)


if __name__ == '__main__':
    main()
