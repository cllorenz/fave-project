#!/usr/bin/env python2

# -*- coding: utf-8 -*-

# Copyright 2021 Claas Lorenz <claas_lorenz@genua.de>

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


import sys
import csv
import json
import argparse


def _generate_cchecks(checks):
    cchecks = {}

    for check in checks:
        valid = not check.startswith("! ")
        check = check.lstrip('! ')

        cond = None

        tokens = check.split(" && ")
        if len(tokens) == 2:
            src, dst = tokens
        elif len(tokens) == 3:
            src, dst, cond = tokens
            cond = cond.lstrip("f=")
        else:
            raise Exception("unsupported amount of operands: %s (%s)" % (len(tokens), tokens))

        src = src.lstrip("s").lstrip('=')
        dst = dst.lstrip("EF p").lstrip('=')

        cchecks.setdefault(src, [])
        cchecks[src].append((dst, valid, cond))

    return cchecks


if __name__ == '__main__':
    checks = []

    parser = argparse.ArgumentParser()

    parser.add_argument(
        '-c', '--checks',
        dest='checks_file',
        default='checks.json'
    )
    parser.add_argument(
        '--cchecks',
        dest='cchecks_file',
        default='cchecks.json'
    )
    parser.add_argument(
        '-j', '--reach-json',
        dest='reach_file',
        default='reachable.json'
    )
    parser.add_argument(
        '-m', '--inventory-mapping',
        dest='inventory_file',
        default='inventory.json'
    )
    parser.add_argument(
        '-p', '--policy-csv',
        dest='policy_file',
        default='policy.csv'
    )
    parser.add_argument(
        '-s', '--suffix',
        dest='suffix',
        default=''
    )

    args = parser.parse_args(sys.argv[1:])

    mapping = json.load(open(args.inventory_file, 'r'))

    checks = []
    reach_json = {}
    with open(args.policy_file, 'r') as csv_file:
        reader = csv.reader(csv_file, delimiter=',')

        header = reader.next()[1:]

        for row in reader:

            row_iter = iter(row)

            source = next(row_iter)
            sources = [s+args.suffix if s != 'Internet' else s for s in mapping[source]] if mapping else [source+args.suffix if source != 'Internet' else source]

            if source != 'Internet':
                source += args.suffix

            for idx, flag in enumerate(row_iter):
                target = header[idx]
                targets = [t+args.suffix if t != 'Internet' else t for t in mapping[target]] if mapping else [target+args.suffix if target != 'Internet' else target]

                if source == 'Internet' and source == target: continue

                if target != 'Internet': target += args.suffix

                for target in targets:
                    reach_json.setdefault(target, [])

                fstr = 's=source.%s && EF p=probe.%s'
                if flag == 'X':
                    for target in targets:
                        reach_json[target].extend([s for s in sources if s != target])
                        checks.extend([fstr % (s, target) for s in sources if s != target])

                elif flag == '(X)':
                    for target in targets:
                        reach_json[target].extend([s for s in sources if s != target])
                        checks.extend([fstr % (s, target) + ' && f=related:1' for s in sources if s != target])
                        checks.extend(['! ' + fstr % (s, target) + ' && f=related:0' for s in sources if s != target])

                elif flag.startswith('(') and flag.endswith(')'):
                    for target in targets:
                        reach_json[target].extend([s for s in sources if s != target])
                        for condition in flag.lstrip('(').rstrip(')').split('|'):
                            checks.extend([
                                fstr % (s, target) + ' && f=related:0 && ' + ' && '.join(['f='+f for f in
                                    condition.split(';')
                                ]) for s in sources if s != target
                            ])

                else:
                    checks.extend(['! ' + fstr % (s, target) for s in sources])


    with open(args.checks_file, 'w') as checks_file:
        checks_file.write(json.dumps(checks, indent=2) + '\n')

    with open(args.reach_file, 'w') as rf:
        rf.write(json.dumps(reach_json, indent=2) + '\n')

    cchecks = _generate_cchecks(checks)

    with open(args.cchecks_file, "w") as cchecks_file:
        cchecks_file.write(json.dumps(cchecks, indent=2) + '\n')
