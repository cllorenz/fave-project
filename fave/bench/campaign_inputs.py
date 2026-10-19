#!/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2026 Claas Lorenz <claas_lorenz@genua.de>

# This file is part of FaVe.

# FaVe is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# FaVe is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with FaVe.  If not, see <https://www.gnu.org/licenses/>.

""" A campaign's inputs, generated once and recorded (INCREMENTAL_PLAN.md
D17.3): every cell reads them as they were when the protocol was declared.

    python3 bench/campaign_inputs.py berkeley <campaign dir> 30 10 3 1
        wl_berkeley at each size (`keep_every`), each into
        <campaign dir>/inputs/wl_berkeley_k<k>/ -- the generator writes one
        size into bench/wl_berkeley, so the sizes cannot share it
    python3 bench/campaign_inputs.py record <campaign dir> <workload dir>...
        INPUTS.txt: the sha256 of every input of each workload (its role
        files, its checks, the configurations its topology names); a
        workload dir may be `dir:topology=...,policies=...` for split files
    python3 bench/campaign_inputs.py check <campaign dir>    # exit 1 on a change

Run from fave/. The grid workloads' inputs are the ones the integration tier
generated on the code the protocol names (its gate); they are recorded here,
not generated again.
"""

import argparse
import json
import os
import shutil
import sys
from typing import Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from util import provenance  # noqa: E402

#: the files the in-process replay reads, by role (util/in_process_driver.py)
ROLES = {'topology': 'topology.json', 'routes': 'routes.json',
         'policies': 'policies.json', 'sources': 'sources.json'}
#: copied beside them: the checks and the generator's stamp
BESIDE = ('checks.json', 'SOURCE.json')


def berkeley(directory: str, sizes: List[int]) -> List[str]:
    """ Generate wl_berkeley at each size into the campaign directory. """
    from bench.deltanet.workload import generate_inputs, prefix_of
    src = prefix_of('wl_berkeley')
    made = []
    for k in sizes:
        target = os.path.join(directory, 'inputs', 'wl_berkeley_k%d' % k)
        if os.path.exists(target):
            raise SystemExit("%s exists: inputs are generated once" % target)
        generate_inputs('wl_berkeley', keep_every=k)
        with open(os.path.join(src, 'SOURCE.json')) as raw:
            if json.load(raw).get('keep_every') != k:
                raise SystemExit("the generator did not write keep_every=%d" % k)
        os.makedirs(target)
        for name in list(ROLES.values()) + list(BESIDE):
            shutil.copy2(os.path.join(src, name), os.path.join(target, name))
        made.append(target)
    return made


def _parse(spec: str) -> Tuple[str, Dict[str, str]]:
    prefix, _sep, files = spec.partition(':')
    names = dict(ROLES)
    if files:
        names.update(dict(item.split('=', 1) for item in files.split(',')))
    return prefix, names


def hashes(specs: List[str]) -> Dict[str, Optional[str]]:
    out: Dict[str, Optional[str]] = {}
    for spec in specs:
        prefix, names = _parse(spec)
        checks = os.path.join(prefix, 'checks.json')
        if not os.path.exists(checks):
            checks = os.path.join(os.path.dirname(prefix), 'checks.json')
        out.update(provenance.inputs(prefix, names, checks if os.path.exists(checks) else None))
    return out


def record(directory: str, specs: List[str]) -> str:
    path = os.path.join(directory, 'INPUTS.txt')
    if os.path.exists(path):
        raise SystemExit("%s exists: a record is not overwritten" % path)
    lines = ['# Inputs, generated once for this campaign (INCREMENTAL_PLAN.md D17.3)',
             '# workloads: ' + ' '.join(specs)]
    for name, digest in sorted(hashes(specs).items()):
        lines.append('  %s  %s' % (digest or '(missing)', name))
    with open(path, 'w') as out:
        out.write('\n'.join(lines) + '\n')
    return path


def check(directory: str) -> List[str]:
    """ What changed since INPUTS.txt was written. """
    with open(os.path.join(directory, 'INPUTS.txt')) as raw:
        lines = raw.read().splitlines()
    specs = lines[1].split(': ', 1)[1].split()
    recorded = {}
    for line in lines[2:]:
        digest, name = line.split()
        recorded[name] = None if digest == '(missing)' else digest
    now = hashes(specs)
    return ['%s: %s -> %s' % (n, recorded.get(n), now.get(n))
            for n in sorted(set(recorded) | set(now)) if recorded.get(n) != now.get(n)]


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('action', choices=('berkeley', 'record', 'check'))
    parser.add_argument('directory')
    parser.add_argument('rest', nargs='*')
    args = parser.parse_args(argv)
    if args.action == 'berkeley':
        for path in berkeley(args.directory, [int(k) for k in args.rest]):
            print(path)
        return 0
    if args.action == 'record':
        print(record(args.directory, args.rest))
        return 0
    changed = check(args.directory)
    for line in changed:
        print("CHANGED " + line)
    if not changed:
        print("inputs unchanged since INPUTS.txt")
    return 1 if changed else 0


if __name__ == '__main__':
    sys.exit(main())
