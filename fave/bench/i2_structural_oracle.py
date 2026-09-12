#!/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2026 Claas Lorenz <claas_lorenz@genua.de>

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

""" Independent structural reachability oracle for wl_i2 (AD6_PLAN.md Sec. 5.5).

Computes the wl_i2 source->probe reachability matrix DIRECTLY from the shipped
JSON model, using neither ad6 nor NetPlumber. Its purpose is to be a third
witness: ad6 (SAT/QBF) and NetPlumber (HSA) agree on 11 unreachable pairs, and
agreement between two engines is only worth as much as their independence. This
script shares no code with either.

WHAT KIND OF INDEPENDENCE THIS IS, stated so the result is not oversold
(AD6_PLAN.md Sec 5.5, "WHAT THE i2 ORACLE ACTUALLY IS"): independence of
IMPLEMENTATION and of METHOD, not of expectation. There is no external ground
truth for wl_i2's data plane -- `reachable.json` is policy intent from the same
generator as `checks.json`, not verified truth -- and the 11-pair result both
engines agree on was reached only after multiple rounds of correction to both.
This script was written AFTER that agreement, by the same project, already
knowing which answer would count as success; it is not a pre-registered
prediction. What it genuinely adds is a different route to the number -- direct
structural simulation, exhaustive over IPv4 -- and, with the manual trace to a
single misconfigured Chicago->Kansas link, a check against the RAW data rather
than against another tool's output. That last part is what a co-adapted shared
error between the two engines would not survive.

It is EXHAUSTIVE over IPv4, not a sample. Two destination addresses behave
identically iff they pick the same longest-prefix-match winner at every device,
and that equivalence is refined exactly by the binary trie over the union of all
prefixes in the model: atom(p) = range(p) minus the ranges of all deeper
prefixes. Enumerating one representative per atom therefore covers the whole
address space. wl_i2 yields 9,673 atoms over 10,020 distinct prefixes.

Model semantics, as actually encoded in the dataset:

  source.X.1 -> in.X.p       packet with free vlan and free ipv4_dst
  in.X                       admits (arrival port, vlan) pairs, then fd -> in.X.<d>00000
  in.X.<d>00000              internal stage link to out.X.<d>10000
  out.X                      longest-prefix-match on ipv4_dst; rw=vlan:M ; fd=out.X.q
  out.X.q                    probe.X is tapped on EVERY egress port, and fires iff
                             vlan == 0; the port may ALSO carry a topology link, in
                             which case the packet is both observed and forwarded

Two properties of this dataset make the walk a simple chain: every (device,
prefix) pair carries exactly one rule, so there is no ECMP fanout anywhere
(verified: fanout histogram is {1: 77451}); and the vlan a packet carries on any
link is fixed by the upstream out-stage rewrite, so it is a function of the
destination address alone.

Usage:
    python3 i2_structural_oracle.py [--data DIR] [--json OUT]
    python3 i2_structural_oracle.py --explain atla seat
"""

import argparse
import json
import os
import sys

from collections import defaultdict, Counter


# port numbering: <device-digit><stage-digit>NNNN, e.g. 220045 = out.chic.220045
DEVICE_BY_DIGIT = {
    '1': 'atla', '2': 'chic', '3': 'hous', '4': 'kans', '5': 'losa',
    '6': 'newy32aoa', '7': 'salt', '8': 'seat', '9': 'wash',
}

DEFAULT_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wl_i2', 'i2-json')


def ip2int(text):
    """ Convert a dotted-quad string to a 32 bit integer.
    """
    octets = [int(o) for o in text.split('.')]
    return (octets[0] << 24) | (octets[1] << 16) | (octets[2] << 8) | octets[3]


def int2ip(value):
    """ Convert a 32 bit integer to a dotted-quad string.
    """
    return '%d.%d.%d.%d' % (
        (value >> 24) & 0xFF, (value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF
    )


def _plen_mask(plen):
    return (0xFFFFFFFF << (32 - plen)) & 0xFFFFFFFF if plen else 0


class I2Model(object):
    """ The wl_i2 data plane, read straight from the shipped JSON.
    """

    def __init__(self, data_dir):
        self.admit = defaultdict(set)   # (in.X, port) -> {vlan}
        self.fib = defaultdict(list)    # device -> [(plen, net, vlan, port)]
        self.prefixes = set()           # (plen, net) over ALL devices
        self.fanout = Counter()

        routes = json.load(open(os.path.join(data_dir, 'routes.json')))
        staged = defaultdict(lambda: defaultdict(list))
        for table, _unused, _idx, match, actions, in_ports in routes:
            if table.startswith('in.'):
                vlan = None
                for field in match:
                    if field.startswith('vlan='):
                        vlan = int(field.split('=', 1)[1])
                for port in in_ports:
                    self.admit[(table, port.rsplit('.', 1)[1])].add(vlan)
                continue

            device = table.split('.', 1)[1]
            plen = net = vlan = port = None
            for field in match:
                if field.startswith('ipv4_dst='):
                    addr, length = field.split('=', 1)[1].split('/')
                    plen, net = int(length), ip2int(addr)
            for action in actions:
                if action.startswith('rw=vlan:'):
                    vlan = int(action.split(':', 1)[1])
                elif action.startswith('fd='):
                    port = action.split('=', 1)[1].rsplit('.', 1)[1]
            if plen is None or port is None:
                continue
            net &= _plen_mask(plen)
            staged[device][(plen, net)].append((vlan, port))
            self.prefixes.add((plen, net))

        for device, table in staged.items():
            byplen = defaultdict(dict)
            for (plen, net), hits in table.items():
                self.fanout[len(hits)] += 1
                byplen[plen][net] = hits[0]
            self.fib[device] = (sorted(byplen, reverse=True), dict(byplen))

        topology = json.load(open(os.path.join(data_dir, 'topology.json')))['topology']
        self.link = {str(e['src']): str(e['dst']) for e in topology}
        for digit in DEVICE_BY_DIGIT:                       # internal in-stage -> out-stage
            self.link[digit + '00000'] = digit + '10000'

        self.probe_ports = defaultdict(set)
        for egress, probe, _unused in json.load(
                open(os.path.join(data_dir, 'probes.json')))['links']:
            self.probe_ports[probe.split('.')[1]].add(egress.rsplit('.', 1)[1])

        self.src_port = {}
        for source, ingress, _unused in json.load(
                open(os.path.join(data_dir, 'sources.json')))['links']:
            self.src_port[source.split('.')[1]] = ingress.rsplit('.', 1)[1]

    def lookup(self, device, dst):
        """ Longest-prefix-match at out.<device>; returns ((vlan, port), plen).
        """
        plens, table = self.fib[device]
        for plen in plens:
            hit = table[plen].get(dst & _plen_mask(plen))
            if hit is not None:
                return hit, plen
        return None, None

    def walk(self, source, dst, max_hops=30):
        """ Forward-simulate one destination address from one source.

        Returns (steps, outcome, delivered) where `delivered` is the set of
        devices whose probe fires. Probe taps are PARALLEL, so a delivery does
        not stop the walk.
        """
        steps, delivered, seen = [], set(), set()
        device = source
        if not self.admit.get(('in.' + source, self.src_port[source])):
            return steps, 'no-ingress-vlan', delivered

        while len(steps) < max_hops:
            if device in seen:
                return steps, 'loop', delivered
            seen.add(device)

            hit, plen = self.lookup(device, dst)
            if hit is None:
                return steps, 'nomatch@%s' % device, delivered
            vlan, port = hit

            tapped = vlan == 0 and port in self.probe_ports.get(device, set())
            if tapped:
                delivered.add(device)
            steps.append((device, port, vlan, plen, tapped))

            nxt = self.link.get(port)
            if nxt is None:
                return steps, 'end@%s.%s(vlan=%d)' % (device, port, vlan), delivered

            peer = DEVICE_BY_DIGIT[nxt[0]]
            admitted = self.admit.get(('in.%s' % peer, nxt), set())
            if vlan not in admitted:
                return steps, 'BLOCKED@in.%s.%s(vlan=%d;admits=%s)' % (
                    peer, nxt, vlan, sorted(v for v in admitted if v is not None)
                ), delivered
            device = peer

        return steps, 'hop-limit', delivered

    def atoms(self):
        """ One representative per exact LPM equivalence class, covering all of IPv4.
        """
        class Node(object):
            __slots__ = ('child', 'is_prefix')

            def __init__(self):
                self.child = [None, None]
                self.is_prefix = False

        root = Node()
        for plen, net in self.prefixes:
            node = root
            for i in range(plen):
                bit = (net >> (31 - i)) & 1
                if node.child[bit] is None:
                    node.child[bit] = Node()
                node = node.child[bit]
            node.is_prefix = True

        def free(node, prefix, depth):
            """ An address under `node` covered by no STRICTLY deeper prefix. """
            if node.child[0] is None and node.child[1] is None:
                return prefix
            for bit in (0, 1):
                child, base = node.child[bit], prefix | (bit << (31 - depth))
                if child is None:
                    return base
                if not child.is_prefix:
                    found = free(child, base, depth + 1)
                    if found is not None:
                        return found
            return None

        reps, stack = [], [(root, 0, 0)]
        while stack:
            node, prefix, depth = stack.pop()
            if node.is_prefix or depth == 0:        # depth 0 also yields the no-match atom
                rep = free(node, prefix, depth)
                if rep is not None:
                    reps.append(rep)
            for bit in (0, 1):
                if node.child[bit] is not None:
                    stack.append((node.child[bit], prefix | (bit << (31 - depth)), depth + 1))
        return sorted(set(reps))


def solve(model):
    """ Full reachability matrix plus, per destination, the atoms that deliver there.
    """
    reps = model.atoms()
    sources = sorted(model.src_port)
    reach = defaultdict(set)
    delivering = defaultdict(set)
    for source in sources:
        for addr in reps:
            _steps, _why, delivered = model.walk(source, addr)
            reach[source] |= delivered
            for device in delivered:
                if device != source:
                    delivering[device].add(addr)
    unreachable = [
        (s, d) for s in sources for d in sources if s != d and d not in reach[s]
    ]
    return reps, reach, delivering, unreachable


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--data', default=DEFAULT_DATA, help='i2-json directory')
    parser.add_argument('--json', dest='json_out', help='write the result as JSON')
    parser.add_argument('--limit', type=int, default=12,
                        help='max atoms / fates to list under --explain (default 12)')
    parser.add_argument('--explain', nargs=2, metavar=('SRC', 'DST'),
                        help='explain one pair: every atom that delivers at DST, '
                             'and what becomes of it when sent from SRC')
    args = parser.parse_args()

    model = I2Model(args.data)
    reps, reach, delivering, unreachable = solve(model)
    sources = sorted(model.src_port)

    print('distinct prefixes        : %d' % len(model.prefixes))
    print('exact LPM atoms (all IPv4): %d' % len(reps))
    print('ECMP fanout histogram    : %s' % dict(sorted(model.fanout.items())))
    print('reachable pairs          : %d of %d' % (
        len(sources) * (len(sources) - 1) - len(unreachable),
        len(sources) * (len(sources) - 1)))
    print('\nUNREACHABLE (%d):' % len(unreachable))
    for src, dst in unreachable:
        print('   %s -> %s' % (src, dst))

    print('\natoms delivering at each probe, from some OTHER source:')
    for device in sources:
        print('   %-12s %d' % (device, len(delivering[device])))

    if args.explain:
        src, dst = args.explain
        addrs = sorted(delivering[dst])
        print('\n%s' % ('=' * 78))
        print('EXPLAIN %s -> %s' % (src, dst))
        print('%s' % ('=' * 78))
        print('%d atom(s) in all of IPv4 deliver at probe.%s from outside %s.' % (
            len(addrs), dst, dst))

        fates, arriving = Counter(), []
        for addr in addrs:
            steps, why, delivered = model.walk(src, addr)
            fates[why.split(';')[0]] += 1
            if dst in delivered:
                arriving.append((addr, steps, why))

        print('of those, %d arrive when sent from %s -- so %s -> %s is %s.\n' % (
            len(arriving), src, src, dst,
            'REACHABLE' if arriving else 'UNREACHABLE'))

        shown = arriving if arriving else [
            (a, ) + model.walk(src, a)[:2] for a in addrs[:args.limit]
        ]
        for addr, steps, why in shown[:args.limit]:
            print('  %-16s %s' % (int2ip(addr), why))
            print('        %s' % ' -> '.join(
                '%s:%s vlan=%d /%d%s' % (d, prt, v, pl, '*' if t else '')
                for d, prt, v, pl, t in steps))
        if len(shown) > args.limit:
            print('  ... %d more (raise --limit to see them)' % (len(shown) - args.limit))

        print('\nfates from %s, over all %d atoms (top %d):' % (src, len(addrs), args.limit))
        for why, count in fates.most_common(args.limit):
            print('   %-58s %5d  %5.1f%%' % (why, count, 100.0 * count / len(addrs)))
        print('\n(* marks an egress where probe.<device> fires, i.e. vlan == 0)')

    if args.json_out:
        payload = {
            'atoms': len(reps),
            'prefixes': len(model.prefixes),
            'unreachable': [list(p) for p in unreachable],
            'reachable': {s: sorted(v) for s, v in reach.items()},
            'delivering_atoms': {d: [int2ip(a) for a in sorted(v)]
                                 for d, v in delivering.items()},
        }
        with open(args.json_out, 'w') as out:
            json.dump(payload, out, indent=1)
        print('\nwrote %s' % args.json_out)

    return 0


if __name__ == '__main__':
    sys.exit(main())
