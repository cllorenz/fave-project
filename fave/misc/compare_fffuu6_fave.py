#!/usr/bin/env python2

import sys
import json

from dd.autoref import BDD

from netplumber.mapping import Mapping
from netplumber.vector import HeaderSpace, get_field_from_vector
from util.packet_util import normalize_ipv6_address


bdd = BDD()
bdd.declare(*(range(128)))

def _addr_str_to_int(addr):
    res = 0
    for i in range(128):
        if addr[127-i] == '1':
            res += 1 << i

    return res

import pprint

def _range_to_prefixes(start, end):
    start_int = _addr_str_to_int(start)
    end_int = _addr_str_to_int(end)

    res = []

    while start_int < end_int:
        i = 0
        for i in range(128):
            if start_int % (1 << (i+1)) or (start_int + (1 << (i+1)) - 1) > end_int: break
        res.append((start_int, 128 - i))
        start_int += 1 << i

    return res


def _int_prefix_to_bdd(addr, prefix):
    res = bdd.true
    for i in range(127, prefix, -1):
        res &= bdd.var(i) if ((1 << i) & addr != 0) else ~bdd.var(i)

    return res


def _range_to_bdd(start, end):
    prefixes = _range_to_prefixes(start, end)

    res = bdd.true
    for prefix in prefixes:
        res |= _int_prefix_to_bdd(*prefix)

    return res


def _prefix_addr_to_bdd(addr):
    res = bdd.true
    cnt = 0
    while cnt < 128 and addr[cnt] != 'x':
        res &= bdd.var(cnt) if addr[cnt] == '1' else ~bdd.var(cnt)
        cnt += 1

    return res


def _addr_to_bdd(addr):
    res = bdd.true
    for i in range(128):
        if addr[i] != 'x':
            res &= bdd.var(i) if addr[i] == '1' else ~bdd.var(i)

    return res


def _is_subset_eq(sub, sup):
    return bdd.apply('diff', sub, sup) == bdd.false


def _read_fffuu6(fffuu):
    lines = fffuu.split('\n')

    nets = {}
    matrix = {}

    for line in lines:
        if '|->' in line:
            net = line[0]
            nets.setdefault(net, bdd.false)
            ranges = line[6:].split(' u ')
            for range in ranges:
                if range.startswith('{'):
                    start, end = range.strip('{}').split(' .. ')
                    sv = normalize_ipv6_address(start)
                    ev = normalize_ipv6_address(end)
                    nets[net] |= _range_to_bdd(sv, ev)
                else:
                    sv = ev = normalize_ipv6_address(range)
                    nets[net] |= _range_to_bdd(sv, ev)


        elif line.startswith('('):
            source, target = line.strip('()').split(',')
            matrix[source] = target

    return (nets, matrix)


def _flow_addr_to_bdd(flow, mapping, direction):
    hs = HeaderSpace.from_str(flow)
    hs.pprint(mapping=mapping)

    hs_list = set()
    hs_diff = set()

    for vec in hs.hs_list:
        hs_list.add(get_field_from_vector(mapping, vec, direction))

    for vec in hs.hs_diff:
        hs_diff.add(get_field_from_vector(mapping, vec, direction))

    res = bdd.true
    for addr in hs_list:
        res |= _addr_to_bdd(addr)

    tmp = bdd.true
    for addr in hs_diff:
        tmp |= _addr_to_bdd(addr)

    return bdd.apply('diff', res, tmp)


def _get_leaves(tree, mapping, probe):
    if 'children' not in tree and tree['node'] == probe:
        source =  _flow_addr_to_bdd(tree['flow'], mapping, 'packet.ipv6.source')
        dest = _flow_addr_to_bdd(tree['flow'], mapping, 'packet.ipv6.destination')
        return [(source, dest)]

    elif 'children' not in tree:
        return []

    else:
        return reduce(
            lambda x, y: x + y,
            [_get_leaves(child, mapping, probe) for child in tree['children']]
        )


def _read_fave(tree, mapping, probe):
    return _get_leaves(tree, mapping, probe)


def main(argv):
    fffuu = open(argv[0], 'r').read()
    tree = json.load(open(argv[1], 'r'))['flows'][0]
    fave = json.load(open(argv[2], 'r'))
    mapping = Mapping.from_json(fave['mapping'])
    probe = int(fave['id_to_probe'].keys()[0])


    fffuu_nets, fffuu_matrix = _read_fffuu6(fffuu)
    fave_reach = _read_fave(tree, mapping, probe)

    # fave subseteq fffuu6
    print all([
        any([
            all([
                _is_subset_eq(source, fffuu_nets[src]),
                _is_subset_eq(dest, fffuu_nets[dst])
            ]) for src, dst in fffuu_matrix.items()
        ]) for source, dest in fave_reach
    ])

    # fffuu6 subseteq fave
#    fave_aggr_src = reduce(lambda x, y: x | y, [s for s, _d in fave_reach])
#    fave_aggr_dst = reduce(lambda x, y: x | y, [d for _s, d in fave_reach])

    for source, dest in fffuu_matrix.items():
        src_net, dst_net = fffuu_nets[source], fffuu_nets[dest]

        for fave_src, fave_dst in fave_reach:
            src_net = bdd.apply('diff', src_net, fave_src)
            dst_net = bdd.apply('diff', dst_net, fave_dst)

        if not src_net == bdd.false or dst_net == bdd.false:
            print source, dest
#            bdd.dump('src.%s.pdf' % source, roots=[src_net])
#            bdd.dump('dst.%s.pdf' % dest, roots=[dst_net])


if __name__ == '__main__':
    main(sys.argv[1:])
