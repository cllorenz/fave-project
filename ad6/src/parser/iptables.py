#!/usr/bin/env python3

import argparse

from lxml import etree as et
from src.xml.genutils import GenUtils
from copy import deepcopy


class IP6TablesParser:
    def parse(ruleset, fw_name):
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

        chains = {}
        chain_defaults = {}
        for line in [l for l in ruleset.splitlines() if l and not l.startswith('#')]:
            tokens = line.split()
            ip_version = '6' if tokens[0] == 'ip6tables' else '4'
            args = parser.parse_args(tokens[1:])
            if args.policy:
                chain, target = args.policy
                chain = chain.lower()
                target = target.lower()
                chains.setdefault(chain, GenUtils.table(chain))
                chain_defaults.setdefault(chain, target)
                continue
            else:
                chain = args.chain.lower()
                chains.setdefault(chain, GenUtils.table(chain))
                target = args.target.lower()

            idx = len(chains[chain])
            rule = GenUtils.rule(str(idx), key="%s_%s_r%d"%(fw_name, chain, idx), raw=line)

            rule.append(GenUtils.action('jump', "%s_%s_r0"%(fw_name, target)))

            if args.iiface:
                if '.' in args.iiface:
                    iface, vlan = args.iiface.split('.')
                    rule.append(GenUtils.vlan(vlan, direction='ingress'))
                else:
                    iface = args.iiface
                rule.append(GenUtils.interface(iface, "%s_%s"%(fw_name, iface), direction='in'))

            if args.oiface:
                if '.' in args.oiface:
                    iface, vlan = args.oiface.split('.')
                    rule.append(GenUtils.vlan(vlan, direction='egress'))
                else:
                    iface = args.oiface
                rule.append(GenUtils.interface(iface, "%s_%s"%(fw_name, iface), direction='out'))

            if args.src_ip:
                rule.append(GenUtils.address(args.src_ip, direction='src', version=ip_version))

            if args.dst_ip:
                rule.append(GenUtils.address(args.dst_ip, direction='dst', version=ip_version))

            if args.proto:
                rule.append(GenUtils.proto(args.proto))

            if args.ctstate:
                rule.append(GenUtils.state(args.ctstate))

            if args.tcp_flags:
                mask, comp = args.tcp_flags
                flags = set(mask.split(',')).intersection(set(comp.split(',')))
                rule.append(GenUtils.tcp_flags(','.join(list(flags))))

            if args.src_port:
                rule.append(GenUtils.port(args.src_port+'/16', 'src'))

            if args.dst_port:
                rule.append(GenUtils.port(args.dst_port+'/16', 'dst'))

            rules = []
            if args.src_ports:
                start, end = args.src_ports.split(':')
                prefixed_ports = _portrange_to_prefix_list(int(start), int(end))

                for i, prefixed_port in enumerate(prefixed_ports):
                    port, prefix = prefixed_port
                    tmp = deepcopy(rule)
                    tmp.attrib['name'] = 'r'+str(idx+i)
                    tmp.attrib['key'] = "%s_%s_r%d" % (fw_name, chain, idx+i)
                    tmp.append(GenUtils.port("%s/%s"%(port, prefix), 'src'))
                    rules.append(tmp)

            if args.dst_ports:
                start, end = args.dst_ports.split(':')
                prefixed_ports = _portrange_to_prefix_list(int(start), int(end))

                tmp_rules = rules if len(rules) > 1 else [rule]
                rules = []
                for i, prefixed_port in enumerate(prefixed_ports):
                    port, prefix = prefixed_port
                    for j, rule in enumerate(tmp_rules):
                        tmp = deepcopy(rule)
                        tmp.attrib['name'] = 'r'+str(idx+i+j)
                        tmp.attrib['key'] = "%s_%s_r%d" % (fw_name, chain, idx+i+j)
                        tmp.append(GenUtils.port("%s/%s"%(port, prefix), 'dst'))
                        rules.append(tmp)

            if rules:
                chains[chain].extend(rules)
            else:
                chains[chain].append(rule)

        for chain, target in chain_defaults.items():
            idx = len(chains[chain])
            rule = GenUtils.rule(str(idx), key="%s_%s_r%d"%(fw_name, chain, idx))
            rule.append(GenUtils.action("jump", target="%s_%s_r0"%(fw_name, target)))
            chains[chain].append(rule)

        firewall = GenUtils.firewall(fw_name)

        accept = GenUtils.table('accept')
        rule = GenUtils.rule('0', key="%s_accept_r0"%fw_name)
        rule.append(GenUtils.action('accept'))
        accept.append(rule)
        firewall.append(accept)

        drop = GenUtils.table('drop')
        rule = GenUtils.rule('0', key="%s_drop_r0"%fw_name)
        rule.append(GenUtils.action('drop'))
        drop.append(rule)
        firewall.append(drop)

        for chain in chains.values():
            firewall.append(chain)

        return firewall


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
