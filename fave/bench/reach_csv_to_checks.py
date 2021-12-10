#!/usr/bin/env python2

import sys
import csv
import json
import argparse


if __name__ == '__main__':
    checks = []

    parser = argparse.ArgumentParser()

    parser.add_argument(
        '-c', '--checks',
        dest='checks_file',
        default='checks.json'
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

            source = row_iter.next()
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
