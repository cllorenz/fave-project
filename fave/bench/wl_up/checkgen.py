#!/usr/bin/env python2

import json

from bench.wl_up.inventory import AD6

OFILE="bench/wl_up/checks.json"

def _generate_reachability_tests(config):
    """ XXX flow tests:
    Internet <--> PublicHosts - ok
    Internet ---> PublicSubHosts
    Internet !--> PrivateSubHosts - (ok)
    PublicHost ---> PublicHosts - ok
    PublicSubHosts ---> PublicSubHosts
    PrivateSubHosts(X) <->> PrivateSubHosts(X)
    PrivateSubHosts(X) !--> PrivateSubHosts(Y) - (ok)
    SubClients <->> Internet - (ok)
    SubClients <->> PublicHosts - (ok)
    SubClients <->> PublicSubHosts (ok)
    SubClients <->> PrivateSubHosts (ok)
    SubClients(X) !--> SubClients(Y) - ok
    """

    tests = []
    hosts, subnets, subhosts = config

    label = lambda x: x[0]

    for host in hosts:
        hlabel = label(host)
        # public servers may be reached from the internet
        tests.append("s=source.internet && EF p=probe.%s.dmz" % hlabel)
        # public servers may reach the internet, TODO: allow stateful
        tests.append("! s=source.%s.dmz && EF p=probe.internet" % hlabel)
        # public servers may reach each other
        tests.extend([
            "s=source.%s.dmz && EF p=probe.%s.dmz" % (
                hlabel,
                label(h)
            ) for h in hosts if label(h) != hlabel
        ])

    for subnet in subnets:
        # clients may reach the internet
        tests.append("s=source.clients.%s && EF p=probe.internet" % subnet)

        # clients may not be reached from the internet, TODO: allow stateful
        tests.append("! s=source.internet && EF p=probe.clients.%s" % subnet)

        # clients may reach public servers
        tests.extend([
            "s=source.clients.%s && EF p=probe.%s.dmz" % (
                subnet,
                label(h)
            ) for h in hosts
        ])

        # public hosts may not reach internal clients, TODO: allow stateful
        tests.extend([
            "! s=source.%s.dmz && EF p=probe.clients.%s" % (
                label(h),
                subnet
            ) for h in hosts
        ])

        # internal clients may reach internal servers
        tests.extend([
            "s=source.clients.%s && EF p=probe.%s.%s" % (
                subnet,
                label(subhost),
                subnet
            ) for subhost in subhosts
        ])

        # internal servers may not reach internal clients, TODO: allow stateful
        tests.extend([
            "! s=source.%s.%s && EF p=probe.clients.%s" % (
                label(subhost),
                subnet,
                subnet
            ) for subhost in subhosts
        ])

        # internal clients may not reach other subnet's internal clients
        tests.extend([
            "! s=source.clients.%s %% EF p=probe.clients.%s" % (
                osn,
                subnet
            ) for osn in subnets if osn != subnet
        ])

        # other subnet's internal clients may not reach internal clients
        tests.extend([
            "! s=source.clients.%s && EF p=probe.clients.%s" % (
                osn,
                subnet
            ) for osn in subnets if osn != subnet
        ])

        # the internet may not reach internal servers
        tests.extend([
            "! s=source.internet && EF p=probe.%s.%s" % (
                label(subhost),
                subnet
            ) for subhost in subhosts
        ])
        # internal servers may not reach the internet
        tests.extend([
            "! s=source.%s.%s && EF p=probe.internet" % (
                label(subhost),
                subnet
            ) for subhost in subhosts
        ])

        # internal servers may not reach other subnet's internal servers
        tests.extend([
            "! s=source.%s.%s && EF p=probe.%s.%s" % (
                subhost,
                subnet,
                osh,
                osn
            ) for subhost, osh, osn in [(
                label(x),
                label(y),
                z
            ) for x in subhosts for y in subhosts for z in subnets if label(x) != label(y)]
        ])

    stests = iter(sorted(tests))
    prev = next(stests)
    cnt = 0
    for next in stests:
        if prev == next:
            cnt += 1
            print("  duplicate: %s" % prev)
        prev = next
    print("number of tests:\t%s\nduplicates:\t%s" % (len(tests), cnt))

    return tests


if __name__ == '__main__':
    checks = _generate_reachability_tests(AD6)

    with open(OFILE, "w") as of:
        of.write(json.dumps(checks))
