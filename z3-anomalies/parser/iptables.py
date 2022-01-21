#!/usr/bin/env python3

import argparse

from model.packet_filter_model import PacketFilterModel
from model.rule import Rule, Flag, Proto, State


def _ipv4_to_int_tuple(ip_str):
    if '/' in ip_str:
        addr, prefix = ip_str.split('/')
        prefix = int(prefix)
    else:
        addr = ip_str
        prefix = 32

    decs = [int(dec) for dec in addr.split('.')]

    ip_int = 0
    for idx, dec in enumerate(decs):
        ip_int += dec << ((3-idx)*8)

    return (
        ip_int >> (32-prefix) << (32-prefix),
        (ip_int << (32-prefix) >> (32-prefix)) | 0xffffffff >> prefix
    ) if prefix != 32 else (
        ip_int,
        ip_int
    )


class IP6TablesParser:
    def parse(ruleset):
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
        parser.add_argument('--tcp-flags', dest='tcp_flags', nargs=2, metavar=('MASK', 'COMP'), action='store')

        parser.add_argument('-P', '--policy', dest='policy', nargs=2, metavar=('CHAIN', 'ACTION'), action='store')
        parser.add_argument('-A', dest='chain', action='store')
        parser.add_argument('-j', dest='target', action='store')

        model = PacketFilterModel()

        chain_defaults = {}

        line_count = 1

        for line in [l for l in ruleset.splitlines() if l and not l.startswith('#')]:
            tokens = line.split()
            ip_version = '6' if tokens[0] == 'ip6tables' else '4'
            args = parser.parse_args(tokens[1:])
            if args.policy:
                chain, target = args.policy
                chain = chain.lower()
                target = target.lower()
                rule = Rule(65535, action=target, raw=line, raw_rule_no=line_count)
                model.setdefault(chain, [])
                chain_defaults.setdefault(chain, rule)
                line_count += 1
                continue
            else:
                chain = args.chain.lower()
                model.setdefault(chain, [])
                target = args.target.lower()

            idx = len(model[chain])
            rule = Rule(idx, target, raw=line, raw_rule_no=line_count)

            if args.iiface:
                if '.' in args.iiface:
                    iface, vlan = args.iiface.split('.')
                    vlan = int(vlan)
                    rule.match.add_field('ingress_vlan', vlan)
                else:
                    iface = args.iiface

                model.add_interface(iface)
                iface = model.interfaces[iface]
                rule.match.add_field('ingress_interface', iface)

            if args.oiface:
                if '.' in args.oiface:
                    iface, vlan = args.oiface.split('.')
                    vlan = int(vlan)
                    rule.match.add_field('egress_vlan', vlan)
                else:
                    iface = args.oiface

                model.add_interface(iface)
                iface = model.interfaces[iface]
                rule.match.add_field('egress_interface', iface)

            if args.src_ip:
                start, end = _ipv4_to_int_tuple(args.src_ip)
                rule.match.add_field_tuple('src_ip', start, end)

            if args.dst_ip:
                start, end = _ipv4_to_int_tuple(args.dst_ip)
                rule.match.add_field_tuple('dst_ip', start, end)

            if args.proto:
                proto = Proto[args.proto].value
                rule.match.add_field('proto', proto)

            if args.ctstate:
                state = State[args.ctstate].value
                rule.match.add_field('state', state)

            if args.tcp_flags:
                mask, comp = args.tcp_flags
                flags = set(mask.split(',')).intersection(set(comp.split(',')))
                flags_sum = sum([Flag[f] for f in flags])
                rule.match.add_field('tcp_flags', flags_sum)

            if args.src_port:
                src_port = int(args.src_port)
                rule.match.add_field('src_port', src_port)

            if args.dst_port:
                dst_port = int(args.dst_port)
                rule.match.add_field('dst_port', dst_port)

            if args.src_ports:
                start, end = args.src_ports.split(':')
                rule.match.add_field_tuple('src_port', int(start), int(end))

            if args.dst_ports:
                start, end = args.dst_ports.split(':')
                rule.match.add_field_tuple('dst_port', int(start), int(end))

            model.add_rule(rule, chain)
            line_count += 1

        for chain, target in chain_defaults.items():
#            idx = len(model[chain])
#            rule = Rule(idx, action=target)
            model.add_rule(target, chain)

        return model
