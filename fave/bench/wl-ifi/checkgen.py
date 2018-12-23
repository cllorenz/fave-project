#!/usr/bin/env python2

import json

OFILE="bench/wl-ifi/checks.json"

def _generate_reachability_tests():
    tests = [
        "s=source.internet && EF p=probe.ifi",
        "! s=source.internet && EF p=probe.internet",
        "s=source.ifi && EF p=probe.internet",
        "! s=source.ifi && EF p=probe.ifi"
    ]

    stests = iter(sorted(tests))
    prev = stests.next()
    cnt = 0
    for next in stests:
        if prev == next:
            cnt += 1
            print "  duplicate: %s" % prev
        prev = next
    print "number of tests:\t%s\nduplicates:\t%s" % (len(tests), cnt)

    return tests


if __name__ == '__main__':
    checks = _generate_reachability_tests()

    with open(OFILE, "w") as of:
        of.write(json.dumps(checks))
