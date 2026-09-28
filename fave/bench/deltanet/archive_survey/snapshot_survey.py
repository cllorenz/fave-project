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

""" Measure a static snapshot in the trace format BEFORE anything is built on it.

The three questions `CLOUD_BENCH_PLAN.md` §2.14 left open for an insert-block
snapshot (2026-09-28), answered for any file of `+<prefix>,<router>,<next_hop>,
<field4>` rows:

* **adjacency** -- the directed `(router, next_hop)` edges the rules use, and
  whether the relation is symmetric. This is what a port assignment would
  rename (one port per neighbour); it is not a stated topology.
* **delivery** -- per prefix, follow every router's next-hop chain. A chain
  ends where a router carries no rule for the prefix, which §2.4 reads as
  DELIVERED there; or it revisits a router, which is a loop. Reported: how many
  distinct delivery points a prefix has, loops, and routers that carry no rule
  and are reached by no chain (they would read as a second home).
* **layout** -- how many runs of one delivery point the prefixes form in
  address order: one per point means the homing is a sorted list cut into
  chunks rather than anything routing produced.
* **LPM** -- nested prefix pairs, and of those, how many a model could get
  wrong observably: a router where the two forward differently, and a pair
  delivered at different places (§3's guardrail asks for the latter).

Deliberately NOT `bench/deltanet/trace.py`: that parser asserts D1's airtel
priority identity and refuses every other trace, which is right for it.
Field 4 is not read here at all.

Stdlib only; one pass over the file, then per-prefix work in memory. A prefix's
forwarding is held as one byte per router, so ~600k prefixes x ~20 routers stays
in the tens of megabytes.

Usage:  python3 snapshot_survey.py <snapshot.csv> [--switch-prefix]

`--switch-prefix` additionally groups delivery points by the part of the name
before '-', which is airtel's `s<i>-<j>` -> switch `s<i>` (§2.4); it is what the
airtel validation needs and means nothing for other traces.
"""

import sys
from collections import Counter

NONE = 255


def parse_prefix(text):
    """ '1.2.3.0/24' -> (network int, length); also reports host bits set. """
    addr, _, plen = text.partition('/')
    a, b, c, d = (int(x) for x in addr.split('.'))
    value = (a << 24) | (b << 16) | (c << 8) | d
    length = int(plen)
    mask = ((1 << length) - 1) << (32 - length) if length else 0
    return value & mask, length, value != (value & mask)


def main(argv):
    path = argv[1]
    by_switch = '--switch-prefix' in argv[2:]

    index = {}          # name -> router id
    names = []
    table = {}          # prefix text -> bytearray(next-hop id per router id)
    edges = Counter()
    rules = 0
    duplicates = 0
    host_bits = 0
    plen_hist = Counter()

    def rid(name):
        if name not in index:
            if len(names) >= NONE:
                raise SystemExit("more than %d names; widen the encoding" % NONE)
            index[name] = len(names)
            names.append(name)
            for row in table.values():
                row.append(NONE)
        return index[name]

    with open(path) as handle:
        for line in handle:
            if line[0] != '+':
                raise SystemExit("not an insert-only snapshot: %r" % line[:60])
            pfx, router, hop, _ = line[1:].rstrip('\n').split(',')
            r, h = rid(router), rid(hop)
            row = table.get(pfx)
            if row is None:
                row = table[pfx] = bytearray([NONE] * len(names))
                _, length, dirty = parse_prefix(pfx)
                plen_hist[length] += 1
                host_bits += dirty
            if row[r] != NONE:
                duplicates += 1
            row[r] = h
            edges[(r, h)] += 1
            rules += 1

    n = len(names)
    routers = {r for r, _ in edges}
    hops = {h for _, h in edges}
    pairs = set(edges)
    asym = sorted((names[a], names[b]) for a, b in pairs if (b, a) not in pairs)
    self_loops = sum(1 for a, b in pairs if a == b)
    degree = Counter(a for a, _ in pairs)

    def group(i):
        return names[i].split('-')[0] if by_switch else names[i]

    # --- delivery -------------------------------------------------------------
    points_hist = Counter()      # distinct delivery groups per prefix
    looping_prefixes = 0
    loop_starts = 0
    orphan_prefixes = 0          # a rule-less router no chain reaches
    orphans = Counter()          # ... and which router that is
    hops_hist = Counter()        # chain length, in hops, to delivery
    homes = Counter()            # delivery group -> prefixes delivered there
    delivered_at = {}            # prefix -> frozenset of delivery groups
    for pfx, row in table.items():
        carriers = [r for r in range(n) if r < len(row) and row[r] != NONE]
        ends = set()
        looped = False
        for start in carriers:
            seen = set()
            cur = start
            while True:
                if cur in seen:
                    looped = True
                    loop_starts += 1
                    break
                seen.add(cur)
                nxt = row[cur] if cur < len(row) else NONE
                if nxt == NONE:
                    ends.add(cur)
                    hops_hist[len(seen) - 1] += 1
                    break
                cur = nxt
        reached = set()
        for start in carriers:
            cur = start
            steps = 0
            while cur < len(row) and row[cur] != NONE and steps <= n:
                cur = row[cur]
                steps += 1
                reached.add(cur)
        rule_less = {r for r in routers | hops if r >= len(row) or row[r] == NONE}
        unreached = rule_less - reached - ends
        if unreached:
            orphan_prefixes += 1
            orphans.update(group(u) for u in unreached)
        looping_prefixes += looped
        groups = frozenset(group(e) for e in ends)
        delivered_at[pfx] = groups
        points_hist[len(groups)] += 1
        if len(groups) == 1:
            homes[next(iter(groups))] += 1

    # How delivery is laid out over the address space: sort the prefixes by
    # (network, length) and count runs of one delivery group. A routing-derived
    # homing scatters; a list cut into chunks gives one run per group.
    runs = 0
    run_order = []
    previous = None
    for pfx in sorted(table, key=lambda t: parse_prefix(t)[:2]):
        groups = delivered_at[pfx]
        if groups != previous:
            runs += 1
            run_order.append('+'.join(sorted(groups)))
            previous = groups

    # --- LPM ------------------------------------------------------------------
    nets = {}
    for pfx in table:
        value, length, _ = parse_prefix(pfx)
        nets[(value, length)] = pfx
    nested = 0
    rule_visible = 0
    delivery_visible = 0
    witness = None
    for (value, length), pfx in nets.items():
        for shorter in range(length - 1, -1, -1):
            mask = ((1 << shorter) - 1) << (32 - shorter) if shorter else 0
            container = nets.get((value & mask, shorter))
            if container is None:
                continue
            nested += 1
            a, b = table[pfx], table[container]
            width = min(len(a), len(b))
            if any(a[r] != b[r] for r in range(width)
                   if a[r] != NONE and b[r] != NONE):
                rule_visible += 1
            if delivered_at[pfx] != delivered_at[container]:
                delivery_visible += 1
                if witness is None:
                    witness = (pfx, container)

    out = [
        ("rules", rules),
        ("duplicate_router_prefix", duplicates),
        ("prefixes", len(table)),
        ("prefixes_with_host_bits_set", host_bits),
        ("names", n),
        ("routers", len(routers)),
        ("next_hops", len(hops)),
        ("next_hops_carrying_no_rules", len(hops - routers)),
        ("routers_nobody_forwards_to", len(routers - hops)),
        ("directed_edges", len(pairs)),
        ("self_loops", self_loops),
        ("asymmetric_edges", len(asym)),
        ("undirected_links", len({frozenset(p) for p in pairs if p[0] != p[1]})),
        ("unlinked_router_pairs",
         (lambda miss: miss if len(miss) <= 5 else len(miss))(sorted(
             (names[a], names[b]) for a in routers for b in routers
             if a < b and (a, b) not in pairs and (b, a) not in pairs))),
        ("out_degree_min_max", "%d/%d" % (min(degree.values()), max(degree.values()))),
        ("prefixes_by_delivery_points", dict(sorted(points_hist.items()))),
        ("prefixes_with_a_loop", looping_prefixes),
        ("chains_that_loop", loop_starts),
        ("chain_hops_to_delivery", dict(sorted(hops_hist.items()))),
        ("prefixes_with_an_unreached_ruleless_router", orphan_prefixes),
        ("unreached_ruleless_routers",
         dict(orphans.most_common(5)) if len(orphans) <= 5 else
         "%d distinct" % len(orphans)),
        ("delivery_groups_used", len(homes)),
        ("groups_delivering_nothing",
         sorted({group(i) for i in range(n)} - set(homes))),
        ("prefixes_per_delivery_group_min_max",
         "%d/%d" % (min(homes.values()), max(homes.values())) if homes else "-"),
        ("prefixes_per_delivery_group",
         dict(sorted(homes.items())) if len(homes) <= 30 else "-"),
        ("delivery_runs_in_address_order", runs),
        ("delivery_run_order", run_order if runs <= 30 else "-"),
        ("nested_pairs", nested),
        ("nested_pairs_forwarded_differently_somewhere", rule_visible),
        ("nested_pairs_delivered_differently", delivery_visible),
        ("delivery_witness", witness),
        ("prefix_lengths", dict(sorted(plen_hist.items()))),
    ]
    if by_switch:
        sw = {(group(a), group(b)) for a, b in pairs}
        out.insert(13, ("switch_level_edges", len(sw)))
        out.insert(14, ("switch_level_asymmetric",
                        sum(1 for a, b in sw if (b, a) not in sw)))
        out.insert(15, ("switch_level_links",
                        len({frozenset(p) for p in sw if p[0] != p[1]})))
    for key, value in out:
        print("%s=%s" % (key, value))
    if asym:
        print("asymmetric_sample=%s" % asym[:5])


if __name__ == '__main__':
    main(sys.argv)
