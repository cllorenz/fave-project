#!/usr/bin/env python2

import sys
import csv
import json
import getopt

def print_help():
    print "synopsis: %s [-h][-c <checkfile>][-m <mapfile>][-p <policyfile>]" % sys.argv[0]
    print "-h - prints help message and exits"
    print "-c <checkfile> - specifies the json file to write the checks (default: checks.json)."
    print "-m <mapfile> - specifies the json file containing a mapping between vlan tags and domain names (default: mapping.json)."
    print "-p <policyfile> - specifies the csv file containing the policy (default: policy.csv)."


if __name__ == '__main__':
    mapping = None
    checks = []

    checks_file = 'checks.json'
    map_file = 'mapping.json'
    policy_file = 'policy.csv'

    try:
        opts, _args = getopt.getopt(sys.argv[1:], "hc:m:p:")
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

        elif arg == '-m':
            map_file = opt

        elif arg == '-p':
            policy_file = opt

        else:
            print "unknown argument: %s %s" % (arg, opt)
            print_help()
            sys.exit(2)


    with open(map_file, 'r') as map_file:
        mapping = json.loads('\n'.join([line for line in map_file.read().split('\n') if not line.startswith('#')]))

    checks = []
    with open(policy_file, 'r') as csv_file:
        reader = csv.reader(csv_file, delimiter=',')

        header = reader.next()

        for row in reader:

            row_iter = iter(row)

            source = row_iter.next()

            for idx, flag in enumerate(row_iter):
                target = header[idx+1]

                fstr = 's=source.%s && EF p=probe.%s'
                if flag != 'X':
                    fstr = '! ' + fstr

                try:
                    checks.append(fstr % (mapping[source], mapping[target]))
                except KeyError:
                    continue

    with open(checks_file, 'w') as checks_file:
        checks_file.write(json.dumps(checks, indent=2) + '\n')
