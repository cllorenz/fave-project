#!/usr/bin/env python3

""" wl_tum's service matrix, read off the ruleset INDEPENDENTLY of FaVe's
engines (owner, 2026-10-14): for a source role, a destination role, a
protocol and a port, whether any NEW connection between them is accepted.
The FPL policy (fplgen.py) states what this says, and the engines are then
graded against it -- so it must not use them.

Endpoints (endpoints()): every host a rule names as a single destination,
the rest of each inside VLAN (vlans.py), and the Internet -- an anonymous
outside prefix (INTERNET) arriving on uplink VLAN 110 and leaving by either
uplink (110, 1024). These are exactly the spaces the workload's sources and
its VLAN demultiplexer (topogen.py, routegen.py) give the model.

The ruleset (rulesets/tum-ruleset) is flat: `iptables -A FORWARD` rules,
policy DROP, targets ACCEPT and DROP, matches -i, -o, -s, -d, -p, --dport or
--dports (one port or one range), --state and --tcp-flags. A packet here is a
NEW connection's first packet: state NEW, and for TCP a SYN, so the ruleset's
one `--tcp-flags SYN,ACK,FIN,RST SYN` matches it and its one ESTABLISHED-only
rule does not. A rule matching anything else this does not know is refused.

Exact: per (source VLAN, destination VLAN, protocol, port) the rules that can
match are boxes over (source address, destination address); a packet in the
role pair's space is accepted iff its first match is an ACCEPT, so the pair
is accessible iff some ACCEPT box minus the DROP boxes before it meets the
space. Ports are split into classes by every boundary a rule names: every
port of a class meets the same rules, so one representative decides it.
"""

import ipaddress
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from bench.wl_tum import vlans  # pylint: disable=wrong-import-position

RULESET = os.path.join(HERE, 'rulesets', 'tum-ruleset')
OUT = os.path.join(HERE, 'service_matrix.json')
FULL = (0, 2 ** 32 - 1)
PROTOCOLS = ('tcp', 'udp')
#: The Internet: an ANONYMOUS outside host, not the partners some rules single
#: out (e.g. 138.246.253.5, which may reach every port of whole subnets). A
#: documentation prefix (RFC 5737, TEST-NET-2) that every rule either contains
#: whole or misses -- endpoints() asserts that -- so all its addresses are alike.
INTERNET = '198.51.100.0/24'


def prefix_range(prefix):
    net = ipaddress.ip_network(prefix, strict=False)
    return (int(net.network_address), int(net.broadcast_address))


class Rule:
    """ One `iptables -A FORWARD` line. """

    def __init__(self, line, idx):
        self.idx, self.line = idx, line
        toks = line.split()
        if toks[:3] != ['iptables', '-A', 'FORWARD']:
            raise ValueError("not a FORWARD rule: %r" % line)
        self.i = self.o = self.proto = None
        self.src, self.dst, self.ports, self.state = FULL, FULL, None, None
        self.target = None
        k = 3
        while k < len(toks):
            t = toks[k]
            v = toks[k + 1] if k + 1 < len(toks) else None
            if t == '-i':
                self.i = vlans.vlan_of(v)
            elif t == '-o':
                self.o = vlans.vlan_of(v)
            elif t == '-s':
                self.src = prefix_range(v)
            elif t == '-d':
                self.dst = prefix_range(v)
            elif t == '-p':
                self.proto = v
            elif t in ('--dport', '--dports'):
                lo, _, hi = v.partition(':')
                self.ports = (int(lo), int(hi or lo))
            elif t == '--state':
                self.state = set(v.split(','))
            elif t == '--tcp-flags':
                if (v, toks[k + 2]) != ('SYN,ACK,FIN,RST', 'SYN'):
                    raise ValueError("unknown --tcp-flags in %r" % line)
                k += 1   # its second argument
            elif t == '-m':
                if v not in ('state', 'tcp', 'udp'):
                    raise ValueError("unknown match module %r in %r" % (v, line))
            elif t == '-j':
                if v not in ('ACCEPT', 'DROP'):
                    raise ValueError("unknown target %r in %r" % (v, line))
                self.target = v
            else:
                raise ValueError("unknown option %r in %r" % (t, line))
            k += 2
        if self.target is None:
            raise ValueError("no target: %r" % line)

    def meets(self, sv, dv, proto, port):
        """ Whether the rule can match a NEW packet from VLAN sv to VLAN dv of
        this protocol and destination port (addresses aside). """
        if self.i is not None and self.i != sv:
            return False
        if self.o is not None and self.o != dv:
            return False
        if self.proto is not None and self.proto != proto:
            return False
        if self.ports is not None and not self.ports[0] <= port <= self.ports[1]:
            return False
        if self.state is not None and 'NEW' not in self.state:
            return False
        return True


def load_rules(path=RULESET):
    rules = []
    with open(path) as raw:
        for line in raw:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if line == 'iptables -P FORWARD DROP':
                continue
            if line.startswith('iptables -P'):
                raise ValueError("unexpected policy line %r" % line)
            rules.append(Rule(line, len(rules)))
    return rules


def _cut(box, hole):
    """ box minus hole, as at most four disjoint boxes. Boxes are
    ((s_lo, s_hi), (d_lo, d_hi)). """
    (s0, s1), (d0, d1) = box
    (h0, h1), (g0, g1) = hole
    if h1 < s0 or s1 < h0 or g1 < d0 or d1 < g0:
        return [box]
    out = []
    if s0 < h0:
        out.append(((s0, h0 - 1), (d0, d1)))
    if h1 < s1:
        out.append(((h1 + 1, s1), (d0, d1)))
    m0, m1 = max(s0, h0), min(s1, h1)
    if d0 < g0:
        out.append(((m0, m1), (d0, g0 - 1)))
    if g1 < d1:
        out.append(((m0, m1), (g1 + 1, d1)))
    return out


def _meet(a, b):
    lo, hi = max(a[0], b[0]), min(a[1], b[1])
    return (lo, hi) if lo <= hi else None


def accessible(rules, sv, dv, proto, port, src_space, dst_space):
    """ Whether some packet from src_space (address ranges) to dst_space,
    VLAN sv to VLAN dv, this protocol and port, NEW, is accepted. Returns the
    deciding ACCEPT rule's index, or None. """
    drops = []
    for r in rules:
        if not r.meets(sv, dv, proto, port):
            continue
        if r.target == 'DROP':
            drops.append((r.src, r.dst))
            continue
        for s in src_space:
            s2 = _meet(s, r.src)
            if s2 is None:
                continue
            for d in dst_space:
                d2 = _meet(d, r.dst)
                if d2 is None:
                    continue
                left = [(s2, d2)]
                for hole in drops:
                    left = [p for b in left for p in _cut(b, hole)]
                    if not left:
                        break
                if left:
                    return r.idx
    return None


def port_classes(rules, proto):
    """ The destination-port classes of a protocol: (lo, hi), split at every
    boundary a rule of that protocol (or of none) names. """
    cuts = {0, 65536}
    for r in rules:
        if r.ports and r.proto in (proto, None):
            cuts.add(r.ports[0])
            cuts.add(r.ports[1] + 1)
    cuts = sorted(cuts)
    return [(a, b - 1) for a, b in zip(cuts, cuts[1:])]


#: protocols the ruleset names without ports; each is one service
PORTLESS = ('icmp', 'esp', 'gre')


def services(rules):
    """ Every service: one per port class of TCP and UDP, one per portless
    protocol. {name: (proto, (lo, hi) or None)} """
    out = {}
    for proto in PROTOCOLS:
        for lo, hi in port_classes(rules, proto):
            out['%s_%d' % (proto, lo) if lo == hi else '%s_%d_%d' % (proto, lo, hi)] = (proto, (lo, hi))
    for proto in PORTLESS:
        out[proto] = (proto, None)
    return out


#: a port range at least this wide names no service in particular
#: (`1:65535`, `1024:65535`): it opens a host, it does not administer a port
WIDE = 1024


def other_service(rules, proto):
    """ The port class of `proto` that no rule names SPECIFICALLY (in a range
    narrower than WIDE): a port nobody administers, offered by every endpoint
    (owner, 2026-10-14). The widest such class above the well-known ports. """
    named = [r.ports for r in rules
             if r.ports and r.proto in (proto, None) and r.ports[1] - r.ports[0] + 1 < WIDE]
    free = [c for c in port_classes(rules, proto)
            if c[0] >= 1024 and not any(a <= c[1] and c[0] <= b for a, b in named)]
    return max(free, key=lambda c: (c[1] - c[0], -c[0]))


def endpoints(rules):
    """ The roles' address spaces, in the order the demultiplexer's rules
    take them (hosts before the rest of their VLAN):
    {name: dict(vlan, src, dst, named)} where `named` is the services the
    rules naming exactly this endpoint's destination mention. """
    inside = vlans.inside()
    hosts = {}
    for r in rules:
        if r.o in inside and r.dst != FULL and r.dst[0] == r.dst[1]:
            hosts.setdefault(r.dst, r.o)
    anon = prefix_range(INTERNET)
    for r in rules:
        for field in (r.src, r.dst):
            if _meet(field, anon) and not (field[0] <= anon[0] and anon[1] <= field[1]):
                raise ValueError("%s is not uniform under the ruleset: %r" % (INTERNET, r.line))
    out = {'Internet': dict(vlan=vlans.UPLINK, dst_vlans=list(vlans.UPLINKS), src=[anon],
                            dst=[anon], addr=INTERNET)}
    for (a, _a), v in sorted(hosts.items()):
        name = 'h%s' % ipaddress.ip_address(a)
        out[name] = dict(vlan=v, dst_vlans=[v], src=[(a, a)], dst=[(a, a)], addr=str(ipaddress.ip_address(a)))
    for v, net in sorted(inside.items()):
        mine = sorted(h for h, hv in hosts.items() if hv == v)
        rest = []
        for p in net['dst']:
            rest.extend(vlans.complement(mine, *prefix_range(p)))
        out['vlan%d' % v] = dict(vlan=v, dst_vlans=[v], src=[prefix_range(net['src'])], dst=rest,
                                 subnet=net['src'], prefixes=net['dst'])
    return out


def _named(rules, ep, svc):
    """ The services rules addressed to this endpoint's destination name: a
    rule whose -d is exactly the host, or (for a VLAN's rest) a prefix of the
    VLAN that is not a single host. """
    got = set()
    for r in rules:
        if r.o not in ep['dst_vlans'] or r.dst == FULL:
            continue
        if 'addr' in ep:
            if r.dst != ep['dst'][0]:
                continue
        elif r.dst[0] == r.dst[1] or not any(_meet(r.dst, d) for d in ep['dst']):
            continue
        for name, (proto, ports) in svc.items():
            if r.proto != proto:
                continue
            if ports is None or r.ports is None or (r.ports[0] <= ports[0] and ports[1] <= r.ports[1]):
                if r.ports is not None or ports is None:
                    got.add(name)
    return got


def reach(rules, a, b, proto, ports):
    """ The ACCEPT rule letting some NEW packet of this service from endpoint
    a to endpoint b through, or None. """
    port = ports[0] if ports else 0
    for dv in b['dst_vlans']:
        got = accessible(rules, a['vlan'], dv, proto, port, a['src'], b['dst'])
        if got is not None:
            return got
    return None


def main():
    rules = load_rules()
    svc = services(rules)
    eps = endpoints(rules)
    other = {p: other_service(rules, p) for p in PROTOCOLS}
    other_names = [n for n, (p, c) in svc.items() if p in PROTOCOLS and c == other[p]]
    internet = eps['Internet']
    table = {}
    for name, ep in eps.items():
        if name == 'Internet':
            continue
        inbound = {s: reach(rules, internet, ep, *svc[s]) for s in svc}
        accessible_in = sorted(s for s, r in inbound.items() if r is not None)
        named = _named(rules, ep, svc)
        offers = sorted(set(named) | set(accessible_in) | set(other_names))
        out_rule = next((r for s in svc for r in [reach(rules, ep, internet, *svc[s])]
                         if r is not None), None)
        table[name] = dict(vlan=ep['vlan'],
                           address=ep.get('addr') or ep.get('subnet'),
                           prefixes=ep.get('prefixes'),
                           offers=offers,
                           inbound={s: inbound[s] for s in accessible_in},
                           outbound=out_rule)
    out = {'what': __doc__.split('\n\n')[0].strip(),
           'ruleset': os.path.relpath(RULESET, HERE), 'rules': len(rules),
           'services': {n: [p, list(c) if c else None] for n, (p, c) in svc.items()},
           'other': other_names,
           'endpoints': table}
    with open(OUT, 'w') as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
    n_in = sum(len(e['inbound']) for e in table.values())
    n_off = sum(len(e['offers']) for e in table.values())
    print('rules %d, services %d (other: %s), endpoints %d; offered %d, inbound-accessible %d, '
          'outbound-accessible endpoints %d'
          % (len(rules), len(svc), other_names, len(table), n_off, n_in,
             sum(1 for e in table.values() if e['outbound'] is not None)))


if __name__ == '__main__':
    main()
