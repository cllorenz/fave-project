""" wl_tum's VLANs, read off the original ruleset dump
(iptables-save-2015-05-15_15-23-41_tum), which the flattened tum-ruleset no
longer states: per inside VLAN, the source subnet its anti-spoofing chain
admits (`-s <net> -i eth1.<v> -j mac_<v>`) and the destination prefixes its
filter chain guards (`-d <net> -o eth1.<v> -j filter_<v>`, multicast left
out); the uplinks are the VLANs the dump sends through NOTFROMHERE.
"""

import ipaddress
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
DUMP = os.path.join(HERE, 'iptables-save-2015-05-15_15-23-41_tum')
#: the uplinks to the Internet; sources from the Internet arrive on the first
UPLINKS = (110, 1024)
UPLINK = UPLINKS[0]
MULTICAST = ipaddress.ip_network('224.0.0.0/4')


def vlan_of(interface):
    """ `eth1.109` -> 109 """
    m = re.fullmatch(r'eth1\.(\d+)', interface)
    if not m:
        raise ValueError("not a VLAN interface of eth1: %r" % interface)
    return int(m.group(1))


def inside(dump=DUMP):
    """ {vlan: {'src': prefix, 'dst': [prefixes]}} for the inside VLANs. """
    src, dst, uplinks = {}, {}, set()
    with open(dump) as raw:
        for line in raw:
            m = re.match(r'-A FORWARD -s (\S+) -i (eth1\.\d+) -j mac_\d+$', line.strip())
            if m:
                src[vlan_of(m.group(2))] = m.group(1)
            m = re.match(r'-A FORWARD -d (\S+) -o (eth1\.\d+) -j filter_\d+$', line.strip())
            if m and not ipaddress.ip_network(m.group(1)).subnet_of(MULTICAST):
                dst.setdefault(vlan_of(m.group(2)), []).append(m.group(1))
            m = re.match(r'-A FORWARD -i (eth1\.\d+) -j NOTFROMHERE$', line.strip())
            if m:
                uplinks.add(vlan_of(m.group(1)))
    if uplinks != set(UPLINKS):
        raise ValueError("the dump's uplinks are %s, not %s" % (sorted(uplinks), UPLINKS))
    if set(src) != set(dst):
        raise ValueError("VLANs with a source subnet %s and with destinations %s differ"
                         % (sorted(src), sorted(dst)))
    return {v: {'src': src[v], 'dst': dst[v]} for v in sorted(src)}


def tum_ranges(dump=DUMP):
    """ Every inside destination prefix, as merged integer ranges. """
    nets = [ipaddress.ip_network(p) for net in inside(dump).values() for p in net['dst']]
    out = []
    for net in sorted(ipaddress.collapse_addresses(nets)):
        out.append((int(net.network_address), int(net.broadcast_address)))
    return out


def complement(ranges, lo=0, hi=2 ** 32 - 1):
    """ The ranges of [lo, hi] outside the given sorted, disjoint ranges. """
    out, at = [], lo
    for a, b in ranges:
        if a > at:
            out.append((at, a - 1))
        at = max(at, b + 1)
    if at <= hi:
        out.append((at, hi))
    return out
