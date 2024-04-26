#!/usr/bin/env python3

""" This module generates FaVe checks from the PolicyTranslator's CSV.
"""

import json

OFILE="bench/wl_ifi/checks.json"

def _generate_reachability_tests():
    nets_with_ip = [
        'internal.ifi', 'admin.ifi', 'office.ifi', 'staff-1.ifi', 'staff-2.ifi',
        'pool.ifi', 'lab.ifi'
    ]
    nets_without_ip = [
        'hpc-mgt.ifi', 'hpc-ic.ifi', 'slb.ifi', 'mgt.ifi', 'san.ifi', 'vmo.ifi',
        'prt.ifi', 'cam.ifi'
    ]

    subnets = nets_with_ip + nets_without_ip

    tests = [
        "! s=source.up && EF p=probe.up"
    ]

    # do not reach subnets from themselves
    tests.extend([
        "! s=source.%s && EF p=probe.%s" % (sub, sub) for sub in subnets
    ])

    # reach ip subnet from campus network
    tests.extend([
        "s=source.up && EF p=probe.%s" % sub for sub in nets_with_ip
    ])

    # do not reach non ip subnets from campus network
    tests.extend([
        "! s=source.up && EF p=probe.%s" % sub for sub in nets_without_ip
    ])

    stests = iter(sorted(tests))
    prev = next(stests)
    cnt = 0
    for next in stests:
        if prev == next:
            cnt += 1
            print(("  duplicate: %s" % prev))
        prev = next
    print(("number of tests:\t%s\nduplicates:\t%s" % (len(tests), cnt)))

    return tests


if __name__ == '__main__':
    checks = _generate_reachability_tests()

    with open(OFILE, "w") as of:
        of.write(json.dumps(checks))
