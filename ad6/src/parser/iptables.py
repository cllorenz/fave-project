#!/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2015 Claas Lorenz <claas_lorenz@genua.de>

# This file is part of ad6.

# ad6 is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# ad6 is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with ad6.  If not, see <https://www.gnu.org/licenses/>.

import argparse
import json
import os

from lxml import etree as et
from src.xml.genutils import GenUtils
from copy import deepcopy


class IP6TablesParser:
    def parse(ruleset, fw_name, dump_mappings=False):
        parser = argparse.ArgumentParser(prog='ip6tables', description='Parse ip6tables rulesets.')
        parser.add_argument('-i', dest='iiface', action='store')
        parser.add_argument('-o', dest='oiface', action='store')
        parser.add_argument('-s', dest='src_ip', action='store')
        parser.add_argument('-d', dest='dst_ip', action='store')
        parser.add_argument('-p', dest='proto', action='store')
        parser.add_argument('--sport', dest='src_port', action='store')
        parser.add_argument('--sports', dest='src_ports', action='store')
        parser.add_argument('--dport', dest='dst_port', action='store')
        parser.add_argument('--dports', dest='dst_ports', action='store')
        parser.add_argument('-m', dest='module', action='append')
        parser.add_argument('--state', dest='ctstate', action='store')
        parser.add_argument('--ctstate', dest='ctstate', action='store')
        parser.add_argument('--limit', dest='limit', action='store')
        parser.add_argument('--header', dest='header', action='store')
        parser.add_argument('--rt-type', dest='rttype', action='store')
        parser.add_argument('--rt-segsleft', dest='rtsegs', action='store')
        parser.add_argument('--icmp6type', dest='icmp6type', action='store')
        parser.add_argument('--icmpv6-type', dest='icmp6type', action='store')
        parser.add_argument('--tcp-flags', dest='tcp_flags', nargs=2, metavar=('MASK', 'COMP'), action='store')

        parser.add_argument('-P', '--policy', dest='policy', nargs=2, metavar=('CHAIN', 'ACTION'), action='store')
        parser.add_argument('-A', dest='chain', action='store')
        parser.add_argument('-j', dest='target', action='store')

        original = {}
        extended = {}
        if os.access('/tmp/mappings.json', os.F_OK):
            mappings = json.load(open('/tmp/mappings.json', 'r'))
            original = mappings['original']
            extended = mappings['extended']

        chains = {}
        chain_defaults = {}
        rule_counts = {}
        line_count = 1

        for line in [l for l in ruleset.splitlines() if l and not l.startswith('#')]:
            tokens = line.split()
            negated_fields = _get_negated_fields(tokens)
            tokens = [t for t in tokens if t != '!']

            ip_version = '6' if tokens[0] == 'ip6tables' else '4'

            args = parser.parse_args(tokens[1:])
            if args.policy:
                chain, target = args.policy
                chain = chain.lower()
                rule_counts.setdefault(chain, 0)
                target = target.lower()
                chains.setdefault(chain, GenUtils.table(chain))
                chain_defaults.setdefault(chain, (target, line, line_count))
                rule_counts[chain] += 1
                line_count += 1
                continue

            else:
                chain = args.chain.lower()
                chains.setdefault(chain, GenUtils.table(chain))
                target = args.target.lower()

            rule_counts.setdefault(chain, 0)
            raw_line_no = line_count

            idx = (rule_counts[chain] - 1) << 12
            key = "%s_%s_r%d" % (fw_name, chain, idx)
            rule = GenUtils.rule(
                str(idx),
                key=key,
                raw="%s (%s)" % (line, fw_name),
                raw_line_no=raw_line_no
            )

            extended.setdefault(chain, {})
            extended[chain].setdefault(key, [])
            extended[chain][key].append(key)
            original.setdefault(chain, {})
            original[chain][key] = key

            rule.append(GenUtils.action('jump', "%s_%s_r0"%(fw_name, target)))

            if args.iiface:
                if '.' in args.iiface:
                    iface, vlan = args.iiface.split('.')
                    rule.append(GenUtils.vlan(vlan, direction='ingress', negated=('-i' in negated_fields)))
                else:
                    iface = args.iiface
                rule.append(GenUtils.interface(iface, "%s_%s"%(fw_name, iface), direction='in', negated=('-i' in negated_fields)))

            if args.oiface:
                if '.' in args.oiface:
                    iface, vlan = args.oiface.split('.')
                    rule.append(GenUtils.vlan(vlan, direction='egress', negated=('-o' in negated_fields)))
                else:
                    iface = args.oiface
                rule.append(GenUtils.interface(iface, "%s_%s"%(fw_name, iface), direction='out', negated=('-o' in negated_fields)))

            if args.src_ip:
                rule.append(GenUtils.address(args.src_ip, direction='src', version=ip_version, negated=('-s' in negated_fields)))

            if args.dst_ip:
                rule.append(GenUtils.address(args.dst_ip, direction='dst', version=ip_version, negated=('-d' in negated_fields)))

            if args.proto:
                rule.append(GenUtils.proto(args.proto, negated=('-p' in negated_fields)))

            if args.ctstate:
                rule.append(GenUtils.state(args.ctstate, negated=('--state' in negated_fields or '--ctstate' in negated_fields)))

            if args.limit:
                rule.append(GenUtils.icmp6limit(args.limit, negated=('--limit' in negated_fields)))

            if args.header:
                rule.append(GenUtils.ipv6header(negated=('--header' in negated_fields)))

            if args.rttype:
                rule.append(GenUtils.rttype(args.rttype, negated=('--rt-type' in negated_fields)))

            if args.rtsegs:
                rule.append(GenUtils.rtsegsleft(args.rtsegs, negated=('--rt-segsleft' in negated_fields)))

            if args.icmp6type:
                rule.append(GenUtils.icmp6type(args.icmp6type, negated=('--icmp6type' in negated_fields)))

            if args.tcp_flags:
                mask, comp = args.tcp_flags
                flags = set(mask.split(',')).intersection(set(comp.split(',')))
                rule.append(GenUtils.tcp_flags(','.join(list(flags)), negated=('--tcp-flags' in negated_fields)))

            if args.src_port:
                rule.append(GenUtils.port(args.src_port+'/16', 'src', negated=('--sport' in negated_fields)))

            if args.dst_port:
                rule.append(GenUtils.port(args.dst_port+'/16', 'dst', negated=('--dport' in negated_fields)))

            rules = []
            if args.src_ports:
                start, end = args.src_ports.split(':')
                prefixed_ports = _portrange_to_prefix_list(int(start), int(end))

                for i, prefixed_port in enumerate(prefixed_ports):
                    port, prefix = prefixed_port
                    tmp = deepcopy(rule)
                    tmp_idx = idx+(i<<6)
                    tmp_key = "%s_%s_r%d" % (fw_name, chain, tmp_idx)
                    tmp.attrib['name'] = 'r'+str(tmp_idx)
                    tmp.attrib['key'] = tmp_key
                    tmp.append(GenUtils.port("%s/%s"%(port, prefix), 'src', negated=('--sports' in negated_fields)))
                    rules.append(tmp)
                    extended[chain][key].append(tmp_key)
                    original[chain][tmp_key] = key

            if args.dst_ports:
                start, end = args.dst_ports.split(':')
                prefixed_ports = _portrange_to_prefix_list(int(start), int(end))

                tmp_rules = rules if len(rules) > 1 else [rule]
                rules = []
                for i, prefixed_port in enumerate(prefixed_ports):
                    port, prefix = prefixed_port
                    for j, rule in enumerate(tmp_rules):
                        tmp = deepcopy(rule)
                        tmp_idx = idx+(j<<6)+i
                        tmp_key = "%s_%s_r%d" % (fw_name, chain, tmp_idx)
                        tmp.attrib['name'] = 'r'+str(tmp_idx)
                        tmp.attrib['key'] = tmp_key
                        tmp.append(GenUtils.port("%s/%s"%(port, prefix), 'dst', negated=('--dports' in negated_fields)))
                        rules.append(tmp)
                        extended[chain][key].append(tmp_key)
                        original.setdefault(chain, {})
                        original[chain][tmp_key] = key

            if rules:
                chains[chain].extend(rules)
            else:
                chains[chain].append(rule)


            rule_counts[chain] += 1
            line_count += 1

        for chain, default in chain_defaults.items():
            target, line, lineno = default
            idx = (rule_counts[chain] - 1) << 12
            key = "%s_%s_r%d" % (fw_name, chain, idx)
            rule = GenUtils.rule('r'+str(idx), key=key, raw="%s (%s)" % (line, fw_name), raw_line_no=lineno)
            rule.append(GenUtils.action("jump", target="%s_%s_r0"%(fw_name, target)))
            chains[chain].append(rule)
            extended.setdefault(chain, {})
            extended[chain].setdefault(key, [])
            extended[chain][key].append(key)
            original.setdefault(chain, {})
            original[chain][key] = key

        firewall = GenUtils.firewall(fw_name)

        accept = GenUtils.table('accept')
        rule = GenUtils.rule('r0', key="%s_accept_r0"%fw_name)
        rule.append(GenUtils.action('accept'))
        accept.append(rule)
        firewall.append(accept)

        drop = GenUtils.table('drop')
        rule = GenUtils.rule('r0', key="%s_drop_r0"%fw_name)
        rule.append(GenUtils.action('drop'))
        drop.append(rule)
        firewall.append(drop)

        for chain in chains.values():
            firewall.append(chain)

        if dump_mappings:
            json.dump(
                {'original' : original, 'extended' : extended},
                open('/tmp/mappings.json', 'w')
            )

        return firewall


def _get_negated_fields(tokens):
    res = []
    for i, token in enumerate(tokens):
        if token == '!':
            res.append(tokens[i+1])

    return res


_PORT_BITS = 16
def _portrange_to_prefix_list(lower, upper):
    """ Converts a range of ports to a list of prefixes.

    Keyword arguments:
    lower - the lowest port
    upper - the highest port
    """
    assert all([lower >= 0, lower <= 65535, upper >= 0, upper <= 65535, lower <= upper])

    res = []

    if lower == upper:
        return [(lower, _PORT_BITS)]

    while lower < upper:
        postfix = 0
        for postfix in range(_PORT_BITS):
            if (lower % (1 << (postfix + 1)) != 0) or (lower + (1 << (postfix + 1)) - 1 > upper):
                break

        res.append((lower, _PORT_BITS - postfix))
        lower += (1 << postfix)

    return res


def _print_help():
    print("usage: python3 iptables.py <ruleset>")

if __name__ == '__main__':
    import sys
    if len(sys.argv) == 2:
        ruleset = sys.argv[1]
    else:
        _print_help()
        sys.exit(1)

    with open(ruleset) as f:
        policy = IP6TablesParser.parse(f.read(), 'tum_fw')
        print(et.tostring(policy, pretty_print=True).decode('utf-8'))
