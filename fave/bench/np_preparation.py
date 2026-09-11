#!/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2021 Claas Lorenz <claas_lorenz@genua.de>

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


import ipaddress
import json

from netplumber.mapping import FIELD_SIZES
from netplumber.vector import Vector
from bench.bench_helpers import array_ipv4_to_cidr, array_vlan_to_number, array_to_int


# field : (short_field, dontcares, conv_func, rw_default)
_CONVERSION = {
    'packet.ipv4.source' : ('ipv4_src', ['x'], array_ipv4_to_cidr, '0.0.0.0/0'),
    'packet.ipv4.destination' : ('ipv4_dst', ['x'], array_ipv4_to_cidr, '0.0.0.0/0'),
    'packet.ether.vlan' : ('vlan', ['x'], array_vlan_to_number, None),
    'packet.ipv6.proto' : ('ip_proto', ['x', '0'], array_to_int, None),
    'packet.upper.sport' : ('tcp_src', ['x'], array_to_int, None),
    'packet.upper.dport' : ('tcp_dst', ['x'], array_to_int, None),
    'packet.upper.tcp.flags' : ('tcp_flags', ['x'], array_to_int, None)
}


def _port_no_to_port_name(
        port,
        table_id_to_name,
        intervals,
        skip_table_name=False
    ):

    table_id = int(port / 100000)
    port_id = port % 100000

    for interval, ttype in list(intervals.items()):
        i1, i2 = interval
        if (i1 <= port_id and port_id < i2):
            return '%s.%d' % (
                table_id_to_name[table_id*10+ttype],
                port
            ) if not skip_table_name else str(port)

    raise Exception('invalid port: %d' % port)



def _probe_port_to_port_name(port, tables, first=False):
    if first:
        return 'probe.%s.1' % (tables[int((port % 10000) / 100) - 1])
    else:
        return 'probe.%s.%d.1' % (tables[int((port % 10000) / 100) - 1], port)


def _source_port_to_port_name(port, tables):
    return 'source.%s.1' % (tables[int((port % 20000) / 100) - 1])


def _probe_id_to_name(id, tables, first=False):
    if first:
        return 'probe.%s' % (tables[int((id % 10000) / 100) - 1])
    else:
        return 'probe.%s.%d' % (tables[int((id % 10000) / 100) - 1], id)


def _source_id_to_name(id, tables):
    return 'source.%s' % tables[int((id % 20000) / 100) - 1]


def get_start_end(field, mapping):
    start = mapping[field]
    end = start + FIELD_SIZES[field]
    return start, end


def _get_field_from_match(match, fname, sname, convert, mapping, dontcares=['x']):
    res = None
    start, end = get_start_end(fname, mapping)
    field_match = match[start:end]
    if all([field_match != dc*FIELD_SIZES[fname] for dc in dontcares]):
        res = "%s=%s" % (sname, convert(field_match))
    return res


def _get_rewrite(rewrite, mask, fname, sname, convert, mapping, default=None):
    res = None
    start, end = get_start_end(fname, mapping)
    field_mask = mask[start:end]
    field_rewrite = rewrite[start:end]
    if field_mask == '1'*FIELD_SIZES[fname]:
        res = "%s:%s" % (sname, convert(field_rewrite))

    return res



def rule_to_route(rule, table_id_to_name, mapping, intervals):
    rid = int(rule['id']) & 0xffffffff
    table_name = table_id_to_name[int(rule['id']) >> 32]

    in_ports = [
        _port_no_to_port_name(
            p,
            table_id_to_name,
            intervals
        ) for p in rule['in_ports']
    ]
    out_ports = [
        _port_no_to_port_name(
            p,
            table_id_to_name,
            intervals
        ) for p in rule['out_ports']
    ]

    match_fields = []

    match = rule['match'].replace(',', '')

    for field in list(mapping.keys()):
        short_field, dontcares, conv_func, _rw_default = _CONVERSION[field]
        match_field = _get_field_from_match(
            match, field, short_field, conv_func, mapping, dontcares=dontcares
        )
        if match_field: match_fields.append(match_field)

    actions = []

    if rule['action'] == 'rw':
        mask = rule['mask'].replace(',', '')
        rewrite = rule['rewrite'].replace(',', '')

        fields = []

        for field in list(mapping.keys()):
            short_field, dontcares, conv_func, rw_default = _CONVERSION[field]
            rw_field = _get_rewrite(
                rewrite,
                mask,
                field,
                short_field,
                conv_func,
                mapping,
                default=rw_default
            )
            if rw_field: fields.append(rw_field)

        if fields != []:
            actions.append("rw=%s" % ';'.join(fields))

    actions.extend(["fd=%s" % p for p in out_ports])

    return (table_name, 1, rid, match_fields, actions, in_ports)


def _prefix_len(match_fields):
    """ IP-prefix length of a route's ipv4_dst match; -1 for match-all/no-dst
    (so the default/wildcard route sorts to the lowest priority). """
    for clause in match_fields:
        if clause.startswith('ipv4_dst='):
            pfx = clause.split('=', 1)[1]
            return int(pfx.split('/')[1]) if '/' in pfx else 32
    return -1


class FibDeclarationError(ValueError):
    """ Raised when a raw-table benchmark's `config.json` does not declare which
    of its table types are FIBs, or declares one that does not exist. Loud by
    design: see `_reprioritise_fib_lpm`. """


def _net_of(match_fields):
    """ The ipv4_dst network of a route, or the match-all default. """
    for clause in match_fields:
        if clause.startswith('ipv4_dst='):
            return ipaddress.ip_network(clause.split('=', 1)[1], strict=False)
    return ipaddress.ip_network('0.0.0.0/0')


def _forwards(actions):
    return any(a.startswith('fd=') for a in actions)


def fib_tables(routes, fib_table_types):
    """ The device names in `routes` whose table type is declared a FIB.

    Table type is the dotted stage prefix a raw-table benchmark composes its
    devices from (`mid.bbra_rtr` -> `mid`), matching `config.json`'s own
    `table_types`. """
    return {
        r[0] for r in routes
        if r[0].split('.', 1)[0] in set(fib_table_types)
    }


def _reprioritise_fib_lpm(routes, fib_table_types):
    """ FaVe-backend LPM fix (see APKEEP_STANFORD_NP_SPEC.md Phase 1d, and
    AD6_PLAN.md §5.5 for why this function's PREDECESSOR silently skipped wl_i2).

    NetPlumber resolves rule priority by rule index (lower index = higher
    priority). A raw-table dataset that feeds its FIB in FILE ORDER
    (shortest prefix first) therefore lets the `0.0.0.0/0` default outrank the
    specific routes, and NP forwards by the WRONG rule -- a non-LPM artifact
    (wl_stanford reachability collapses to ~10 pairs). Vanilla NetPlumber avoids
    this because its `--load` front-inserts every rule, reversing file order back
    to longest-first; the FaVe fork's list->map `--load` keys priority by the
    stored rule id/file position instead and dropped that reversal. This restores
    longest-prefix-match by reassigning each declared FIB table's rule index so
    that longer dst prefixes get the lower index, stable within a prefix length.

    WHICH TABLES: declared, never inferred. `fib_table_types` comes from the
    benchmark's own `config.json` (`"fib_table_types": ["mid"]` for wl_stanford,
    `["out"]` for wl_i2). The predecessor hardcoded `dev.startswith('mid.')`,
    which silently did NOTHING on wl_i2 -- whose FIB is the `out` stage -- so
    every FaVe+NetPlumber wl_i2 number was computed on a non-LPM forwarding
    model (3,731 rules shadowed by an earlier containing prefix). An EARLIER
    design of this function inferred FIB-ness from rule shape ("matches only
    ipv4_dst"); that was rejected, correctly, because a packet filter can have
    the same shape and reordering one changes its filtering semantics -- and
    because shape-matching on match fields is blind to ACTIONS, which is where
    permit/deny lives.

    SAFETY, because a declared FIB may still be impure: wl_stanford's `mid.*`
    tables carry 3,372 forwarding rules AND 472 no-action DROPS, every one of
    which overlaps a forwarding rule at a different prefix length (e.g.
    `224.0.0.0/3` against the `0.0.0.0/0` default). Reordering them is only safe
    because those drops are MORE SPECIFIC than what they shadow, so prefix order
    agrees with the intended deny-before-permit precedence -- a property of that
    data, not an invariant. So this refuses to reorder a table when doing so
    would FLIP the relative order of any overlapping forwarding/non-forwarding
    pair, rather than trusting the declaration blindly.

    Raises FibDeclarationError on a missing or unknown declaration -- omission
    must be loud, since a silent skip is precisely the bug this replaces. """
    fibs = fib_tables(routes, fib_table_types)

    by_dev = {}
    for pos, route in enumerate(routes):
        by_dev.setdefault(route[0], []).append(pos)

    for dev in sorted(fibs):
        positions = by_dev.get(dev, [])
        order = sorted(positions, key=lambda p: -_prefix_len(routes[p][3]))
        _assert_reorder_preserves_filtering(routes, dev, positions, order)
        for new_idx, p in enumerate(order, start=1):
            t = routes[p]
            routes[p] = (t[0], t[1], new_idx, t[3], t[4], t[5])


def _assert_reorder_preserves_filtering(routes, dev, before, after):
    """ Refuse a reorder that would swap an overlapping forwarding rule past a
    non-forwarding one (or vice versa) -- that is a permit/deny precedence
    change, not a longest-prefix-match correction. Overlapping pairs within one
    class are exactly what LPM is meant to reorder and are left alone. """
    # "Before" is the rule's CURRENT NP priority -- its idx field -- not its
    # position in the routes ARRAY. The two differ (a table's rules are not
    # stored in idx order), and idx is what NetPlumber resolves priority by, so
    # comparing array positions here compares the wrong thing entirely.
    rank_before = {p: routes[p][2] for p in before}
    rank_after = {p: i for i, p in enumerate(after)}
    fwd = [p for p in before if _forwards(routes[p][4])]
    other = [p for p in before if not _forwards(routes[p][4])]
    for a in other:
        net_a = _net_of(routes[a][3])
        for b in fwd:
            net_b = _net_of(routes[b][3])
            if not net_a.overlaps(net_b):
                continue
            if (rank_before[a] < rank_before[b]) != (rank_after[a] < rank_after[b]):
                raise FibDeclarationError(
                    "refusing to LPM-reorder %s: it would flip %s (%s) past %s "
                    "(%s), changing permit/deny precedence on overlapping "
                    "prefixes. Either this table is not a FIB, or its filtering "
                    "rules need handling before reordering." % (
                        dev, net_a,
                        "forward" if _forwards(routes[a][4]) else "no-forward",
                        net_b,
                        "forward" if _forwards(routes[b][4]) else "no-forward"))


def prepare_benchmark(
        json_dir,
        topology_file,
        sources_file,
        probes_file,
        routes_file,
        mapping,
        intervals
    ):
    config_file = json_dir + '/config.json'
    topo_file = json_dir + '/topology.json'

    config_json = json.load(open(config_file, 'r'))
    tables = config_json['tables']
    table_types = config_json['table_types']
    # AD6_PLAN.md §5.5: which table types are FIBs is DECLARED by the benchmark,
    # never inferred from rule shape. Absent = hard error, because a silent skip
    # is exactly the bug this replaces (the predecessor hardcoded `mid.` and did
    # nothing at all on wl_i2, whose FIB is the `out` stage).
    if 'fib_table_types' not in config_json:
        raise FibDeclarationError(
            "%s must declare 'fib_table_types' (a subset of 'table_types' %s) so "
            "the LPM re-prioritisation knows which tables are forwarding tables. "
            "Use [] for a dataset with no FIB stage." % (config_file, table_types))
    fib_table_types = config_json['fib_table_types']
    unknown = sorted(set(fib_table_types) - set(table_types))
    if unknown:
        raise FibDeclarationError(
            "%s declares fib_table_types %s not present in table_types %s"
            % (config_file, unknown, table_types))

    # map table indices to table file names
    table_id_to_name = {
        tid*10 + ttid : "%s.%s" % (
            ttype, tname
        ) for ttid, ttype in enumerate(table_types) for tid, tname in enumerate(tables, start=1)
    }

    topology = {
        'devices' : [],
        'links' : []
    }

    # create devices for topology and transform rule tables
    routes = []
#    for tid, table in enumerate(sorted(tables, reverse=True)):
#        for ttid, ttype in enumerate(sorted(table_types, reverse=True), start=1):
#            etid = (len(tables) - tid) * 10 + (len(table_types) - ttid)
    for tid, table in enumerate(tables, start=1):
        for ttid, ttype in enumerate(table_types):
            etid = tid * 10 + ttid

            table_json = json.load(
                open("%s/%s.tf.json" % (json_dir, etid), 'r')
            )
            assert etid == table_json['id']
            table_id = table_json['id']
            table_name = table_id_to_name[table_id]
            device_ports = [
                _port_no_to_port_name(
                    p, table_id_to_name, intervals, skip_table_name=True
                ) for p in table_json['ports']
            ]

            topology['devices'].append((
                table_name,
                "switch",
                device_ports,
                { table_name : table_id }
            ))

            for rule in table_json['rules']:
                routes.append(
                    rule_to_route(rule, table_id_to_name, mapping, intervals)
                )

    # FaVe-backend LPM fix: re-prioritise the DECLARED FIB tables by prefix
    # length so NetPlumber forwards by longest-prefix-match. See
    # _reprioritise_fib_lpm / Phase 1d / AD6_PLAN.md §5.5.
    _reprioritise_fib_lpm(routes, fib_table_types)


    # transform policy
    policy_json = json.load(open('%s/policy.json' % json_dir, 'r'))
    sources = {
        'devices' : [],
        'links' : []
    }

    probes = {
        'devices' : [],
        'links' : []
    }

    first_probes = set()
    probe_links = set()

    port_is_source = {}
    source_ports = set()
    probe_ports = set()

    for command in policy_json['commands']:
        if command['method'] == 'add_source_probe':

            probe_name = _probe_id_to_name(command['params']['id'], tables, first=True)
            is_first = not probe_name in first_probes
            if not is_first:
                probe_name = _probe_id_to_name(command['params']['id'], tables, first=False)
            else:
                first_probes.add(probe_name)

            probe_test_path = [".*(port in (%s))$" % ','.join([
                _port_no_to_port_name(
                    p, table_id_to_name, intervals
                ) for p in command['params']['test']['pathlets'][0]['ports']
            ])] if 'pathlets' in command['params']['test'] else None

            probes['devices'].append((
                probe_name,
                'probe',
                'existential',
                None, # match
                None, # filter fields
                ['vlan=0'], # test fields
                probe_test_path # test path
            ))

            for port in command['params']['ports']:
                probe_ports.add(port)


        elif command['method'] == 'add_source':

            sources['devices'].append((
                _source_id_to_name(command['params']['id'], tables),
                'generator',
                ['ipv4_dst=0.0.0.0/0']
            ))

            for port in command['params']['ports']:
                source_ports.add(port)

    for command in policy_json['commands']:
        if command['method'] == 'add_link':
            src_port_num = command['params']['from_port']
            if src_port_num in source_ports:
                src_port = _source_port_to_port_name(
                    src_port_num, tables
                )
            else:
                src_port = _port_no_to_port_name(
                    src_port_num, table_id_to_name, intervals
                )

            dst_port_num = command['params']['to_port']
            if dst_port_num in probe_ports:
                dst_port = _probe_port_to_port_name(
                    dst_port_num, tables
                )
            else:
                dst_port = _port_no_to_port_name(
                    dst_port_num, table_id_to_name, intervals
                )

            if src_port_num in source_ports:
                sources['links'].append((src_port, dst_port, True))

            elif dst_port_num in probe_ports:
                if _probe_id_to_name(dst_port_num, tables, first=True) in first_probes:
                    dst_port = _probe_port_to_port_name(dst_port_num, tables, first=True)

                probe_links.add((src_port, dst_port, False))

            else:
                print(("cannot add link: %s -> %s" % (src_port, dst_port)))

    probes['links'] = list(probe_links)

    # transform link topology
    topo_json = json.load(open(topo_file, 'r'))
    for link in topo_json['topology']:

        src_port_num = link['src']
        if src_port_num in source_ports:
            src_port = _source_port_to_port_name(
                src_port_num, tables
            )
        else:
            src_port = _port_no_to_port_name(
                src_port_num, table_id_to_name, intervals
            )

        dst_port_num = link['dst']
        if dst_port_num in probe_ports:
            dst_port = _probe_port_to_port_name(
                dst_port_num, tables
            )
        else:
            dst_port = _port_no_to_port_name(
                dst_port_num, table_id_to_name, intervals
            )

        topology['links'].append((src_port, dst_port, False))

    # write json files
    with open(topology_file, 'w') as tf:
        tf.write(
            json.dumps(topology, indent=2) + '\n'
        )

    with open(sources_file, 'w') as sf:
        sf.write(
            json.dumps(sources, indent=2) + '\n'
        )

    with open(probes_file, 'w') as pf:
        pf.write(
            json.dumps(probes, indent=2) + '\n'
        )

    with open (routes_file, 'w') as rf:
        rf.write(json.dumps(routes, indent=2)+'\n')
