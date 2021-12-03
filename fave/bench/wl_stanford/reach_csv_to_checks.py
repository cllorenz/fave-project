#!/usr/bin/env python2

import sys
import csv
import json
import getopt


def print_help():
    print "synopsis: %s [-h][-c <checkfile>][-m <mapfile>][-p <policyfile>]" % sys.argv[0]
    print "-h - prints help message and exits"
    print "-c <checkfile> - specifies the json file to write the checks (default: checks.json)."
    print "-p <policyfile> - specifies the csv file containing the policy (default: policy.csv)."


if __name__ == '__main__':
    mapping = None
    checks = []

    checks_file = 'checks.json'
    inventory_file = 'inventory.json'
    policy_file = 'policy.csv'
    reach_file = 'reachable.json'

    try:
        opts, _args = getopt.getopt(sys.argv[1:], "hc:j:m:p:")
    except ValueError:
        print "unknown arguments"
        print_help()
        sys.exit(1)

    for arg, opt in opts:
        if arg == '-h':
            print_help()
            sys.exit(0)

        elif arg == '-c':
            checks_file = opt

        elif arg == '-p':
            policy_file = opt

        elif arg == '-m':
            pass

        elif arg == '-j':
            pass

        else:
            print "unknown argument: %s %s" % (arg, opt)
            print_help()
            sys.exit(2)

    checks = []
    reach_json = {}
    with open(policy_file, 'r') as csv_file:
        reader = csv.reader(csv_file, delimiter=',')

        header = reader.next()[1:]

        for row in reader:

            row_iter = iter(row)

            source = row_iter.next()

            for idx, flag in enumerate(row_iter):
                target = header[idx]

                if source == 'Internet' and source == target: continue

                reach_json.setdefault(target, [])

                fstr = 's=source.%s && EF p=probe.%s'
                if flag == 'X':
                     checks.append(fstr % (source, target))

                elif flag == '(X)':
                     checks.append(fstr % (source, target) + ' && f=related:1')
                     checks.append('! ' + fstr % (source, target) + ' && f=related:0')

                elif flag.startswith('(') and flag.endswith(')'):
                    for condition in flag.lstrip('(').rstrip(')').split('|'):
                        checks.append(
                            fstr % (source, target) + ' && f=related:0 && ' + ' && '.join(['f='+f for f in condition.split(';')])
                        )
                else:
                    checks.append('! ' + fstr % (source, target))

    with open(checks_file, 'w') as checks_file:
        checks_file.write(json.dumps(checks, indent=2) + '\n')
