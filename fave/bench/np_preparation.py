#!/usr/bin/env python2

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

    table_id = port / 100000
    port_id = port % 100000

    for interval, ttype in intervals.iteritems():
        i1, i2 = interval
        if (i1 <= port_id and port_id < i2):
            return '%s.%d' % (
                table_id_to_name[table_id*10+ttype],
                port
            ) if not skip_table_name else str(port)

    raise Exception('invalid port: %d' % port)



def _probe_port_to_port_name(port, tables, first=False):
    if first:
        return 'probe.%s.1' % (tables[((port % 10000) / 100) - 1])
    else:
        return 'probe.%s.%d.1' % (tables[((port % 10000) / 100) - 1], port)


def _source_port_to_port_name(port, tables):
    return 'source.%s.1' % (tables[((port % 20000) / 100) - 1])


def _probe_id_to_name(id, tables, first=False):
    if first:
        return 'probe.%s' % (tables[((id % 10000) / 100) - 1])
    else:
        return 'probe.%s.%d' % (tables[((id % 10000) / 100) - 1], id)


def _source_id_to_name(id, tables):
    return 'source.%s' % tables[((id % 20000) / 100) - 1]


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

    for field in mapping.keys():
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

        for field in mapping.keys():
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


def prepare_benchmark(
        json_dir,
        topology_file,
        sources_file,
        routes_file,
        mapping,
        intervals
    ):
    config_file = json_dir + '/config.json'
    topo_file = json_dir + '/topology.json'

    config_json = json.load(open(config_file, 'r'))
    tables = config_json['tables']
    table_types = config_json['table_types']

    # map table indices to table file names
    table_id_to_name = {
        tid*10 + ttid : "%s.%s" % (
            ttype, tname
        ) for ttid, ttype in enumerate(table_types) for tid, tname in enumerate(tables, start=1)
    }

    topology = {
        'devices' : [('probe.Internet', "probe", "universal", None, None, ['vlan=0'], None)],
        'links' : []
    }

    # create devices for topology and transform rule tables
    routes = []
    for tid, table in enumerate(tables, start=1):
        for ttid, ttype in enumerate(table_types):
            table_json = json.load(
#                open("%s/%s.%s.rules.json" % (json_dir, table, ttype), 'r')
                open("%s/%s.tf.json" % (json_dir, tid * 10 + ttid), 'r')
            )
            assert tid * 10 + ttid == table_json['id']
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
                device_ports
            ))

            for rule in table_json['rules']:
                routes.append(
                    rule_to_route(rule, table_id_to_name, mapping, intervals)
                )


    # transform policy
    policy_json = json.load(open('%s/policy.json' % json_dir, 'r'))
    sources = {
        'devices' : [
            ('source.Internet', "generator", ["ipv4_dst=0.0.0.0/0"])
        ],
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

            topology['devices'].append((
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
                print "cannot add link: %s" % (src_port, dst_port)

    # transform link topology
    topo_json = json.load(open(topo_file, 'r'))
    topo_links = []
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

        if src_port_num in source_ports:
            sources['links'].append((src_port, dst_port, True))
            continue

        elif dst_port_num in probe_ports:
            if _probe_id_to_name(dst_port_num, tables, first=True) in first_probes:
                dst_port = _probe_port_to_port_name(dst_port_num, tables, first=True)

        topo_links.append((src_port, dst_port, False))

    topology['links'] = topo_links
    topology['links'] += probe_links

    # write json files
    with open(topology_file, 'w') as tf:
        tf.write(
            json.dumps(topology, indent=2) + '\n'
        )

    with open(sources_file, 'w') as tf:
        tf.write(
            json.dumps(sources, indent=2) + '\n'
        )

    with open (routes_file, 'w') as rf:
        rf.write(json.dumps(routes, indent=2)+'\n')
