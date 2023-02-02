#!/usr/bin/env python3

import sys

rules = [
    "ip6tables -P FORWARD DROP",
    "ip6tables -P INPUT DROP",
    "ip6tables -P OUTPUT DROP"
]
with open(sys.argv[1]) as ifile:
    for line in ifile.readlines():
        tokens = line.split()
        src = tokens[0].lstrip('@')
        dst = tokens[1]
        srange = (tokens[2], tokens[4])
        drange = (tokens[5], tokens[7])
        proto = int(tokens[8].split('/')[0], 16)

        use_multiport = False

        rule = ["ip6tables", "-A", "FORWARD", "-p", str(proto)]

        if src != '::/0':
            rule.extend(['-s', src])

        if dst != '::/0':
            rule.extend(['-d', dst])

        if srange[0] == srange[1]:
            rule.extend(["--sport", srange[0]])
        elif srange == ("0", "65535"):
            pass
        else:
            rule.extend(["--sports", "%s:%s" % srange])
            use_multiport = True

        if drange[0] == drange[1]:
            rule.extend(["--dport", drange[0]])
        elif drange == ("0", "65535"):
            pass
        else:
            rule.extend(["--dports", "%s:%s" % drange])
            use_multiport = True

        if use_multiport:
            rule.append('-m multiport')

        rule.extend(['-j', 'ACCEPT'])
        rules.append(' '.join(rule))

with open(sys.argv[2], 'w') as ofile:
    ofile.write('\n'.join(rules)+'\n')
