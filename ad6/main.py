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

import lxml.etree as et
import sys
import time
import argparse
import yappi
import json

from src.core.instantiator import Instantiator
from src.solver.minisat import MiniSATAdapter
from src.solver.clasp import ClaspAdapter
from src.solver.pycosat import PycoSATAdapter
from src.core.kripke import *
from src.xml.xmlutils import XMLUtils as xml
from src.xml.genutils import GenUtils
from src.parser.iptables import IP6TablesParser

from statistics import mean,median,stdev,variance


class Main:
    def clear(self,elem):
        for child in elem:
            self.clear(child)

        elem.clear()


    def _run_cycle(self, kripke, encoding):
        t1 = time.time()
        instance = Instantiator.InstantiateCycle(kripke,encoding)
        t2 = time.time()

        t3 = time.time()
        results = self._solver.Solve(instance)
        t4 = time.time()

        return {'cycle' : results}, [t2-t1], [t4-t3]


    def _run_cross(self, kripke, encoding):
        t1 = time.time()
        instance = Instantiator.InstantiateCross(kripke,encoding)
        t2 = time.time()

        t3 = time.time()
        results = self._solver.Solve(instance)
        t4 = time.time()

        return {'cross' : results}, [t2-t1], [t4-t3]


    def _run_reach(self, kripke, encoding):
        results = {}
        instm = []
        solvingm = []
        unreach = []

        nodes = list(kripke.IterNodes())
        for i, node in enumerate(nodes, start=1):
            t1 = time.time()
            instance = Instantiator.InstantiateReach(kripke,encoding,node)
            t2 = time.time()
            instm.append(t2 - t1)

            t1 = time.time()
            result = self._solver.Solve(instance)
            t2 = time.time()
            results[node+'_reach'] = result
            solvingm.append(t2 - t1)

            if result == []:
                unreach.append(node)

            print("reach (%d/%d)" % (i, len(nodes)), end='\r', flush=True, file=sys.stderr)

        return results, unreach, instm, solvingm


    def _run_long_path_reach(self, kripke, encoding):
        results = {}
        instm = []
        solvingm = []
        unreach = []

        nodes = list(kripke.IterNodes())
        nodes_no = len(nodes)
        no = 0
        while nodes != []:
            no += 1
            node = nodes.pop()
            if 'init' in kripke.GetNode(node).Props:
                continue

            t1 = time.time()
            instance = Instantiator.InstantiateReach(kripke,encoding,node)
            t2 = time.time()
            instm.append(t2 - t1)

            t1 = time.time()
            result = self._solver.Solve(instance)
            t2 = time.time()
            results[node+'_lppreach'] = result
            solvingm.append(t2 - t1)

            if result == []:
                if not reach:
                    unreach.append(node)
                    print('long path reach (%d/%d)' % (
                        nodes_no - len(nodes), nodes_no
                    ), end='\r', flush=True, file=sys.stderr)
                continue

            result = result[0]

            transitions = [
                transition for transition in result if result[
                    transition
                ] and (
                    '_true_' in transition or '_false_' in transition
                )
            ]
            for transition in transitions:
                pos = transition.find('_false_')
                if pos == -1:
                    pos = transition.find('_true_')
                    pos2 = pos + len('_true_')
                else:
                    pos2 = pos + len('_false_')

                try:
                    nodes.remove(transition[:pos])
                except ValueError:
                    pass

                try:
                    nodes.remove(transition[pos2:])
                except ValueError:
                    pass

            print('long path reach (%d/%d)' % (
                nodes_no - len(nodes), nodes_no
            ), end='\r', flush=True, file=sys.stderr)

        print('    saved %s of %s calculations' % (
            len(list(kripke.IterNodes()))-no,
            len(list(kripke.IterNodes()))
        ), flush=True, file=sys.stderr)

        return results, unreach, instm, solvingm


    def _run_long_path_shadow(self, kripke, encoding, unreach):
        results = {}
        instm = []
        solvingm = []

        nodes = list(kripke.IterNodes())
        no = 0
        for i, node in enumerate(nodes, start=1):
            if 'init' in kripke.GetNode(node).Props or node in unreach:
                continue

            no += 1

            t1 = time.time()
            instance = Instantiator.InstantiateShadow(kripke,encoding,{},node)
            t2 = time.time()
            instm.append(t2 - t1)

            t1 = time.time()
            result = self._solver.Solve(instance)
            t2 = time.time()
            results[node+'_lppshadow'] = result
            solvingm.append(t2-t1)

            print('long path shadow (%d/%d)' % (
                i, len(nodes)
            ), end='\r', flush=True, file=sys.stderr)

        print('    saved %s of %s calculations' % (
            len(nodes)-no, len(nodes)
        ), flush=True, file=sys.stderr)

        return results, instm, solvingm


    def _run_shadow(self, kripke, encoding):
        results = {}
        instm = []
        solvingm = []
        nodes = list(kripke.IterNodes())

        for i, node in enumerate([n for n in nodes if n not in [
            'tum_fw_input_r0_accept'
        ]], start=1):
            t1 = time.time()
            instance = Instantiator.InstantiateShadow(kripke,encoding,{},node)
            t2 = time.time()
            instm.append(t2 - t1)

            t1 = time.time()
            result = self._solver.Solve(instance)
            t2 = time.time()
            results[node+'_shadow'] = result
            solvingm.append(t2 - t1)

            print("shadow (%d/%d)" % (i, len(nodes)), end='\r', flush=True, file=sys.stderr)

        return results, instm, solvingm


    def main(self):
        reach = self._anomalies['reach']
        cycle = self._anomalies['cycle']
        shadow = self._anomalies['shadow']
        cross = self._anomalies['cross']
        lppreach = self._anomalies['lppreach']
        lppshadow = self._anomalies['lppshadow']
        end_to_end = self._anomalies['end_to_end']

        for network in self._networks:
            results = {}

            XMLUtils.deannotate(network)
            instantiation = []

            print('Instantiate...', end='', flush=True, file=sys.stderr)
            t1 = time.time()
            kripke, encoding = Instantiator.InstantiateBase(
                network, Inits=["tum_fw_eth0_in", "tum_fw_eth1_in"]
            )
            t2 = time.time()
            print(' done', flush=True, file=sys.stderr)
            base = t2-t1
            print('Base instantiation: {:.4f}'.format(base), flush=True, file=sys.stderr)
            instantiation.append(base)
            print('  nodes: ' + str(len(list(kripke.IterNodes()))), flush=True, file=sys.stderr)
            transitions = []
            for transition in kripke.IterFTransitions():
                transitions.extend(kripke.IterFTransitions(transition))
            print('  transitions: ' + str(len(transitions)), flush=True, file=sys.stderr)

            solvingm = []
            solvingc = []

            if cycle:
                print('cycle', flush=True)
                cycle_results, instm, solvingm = self._run_cycle(kripke, encoding)
                results.update(cycle_results)
                Main._print_stats("Cycle", instm, solvingm)


            if cross:
                print('cross', flush=True)
                cross_results, instm, solvingm = self._run_cross(kripke, encoding)
                results.update(cross_results)
                Main._print_stats("Cross", instm, solvingm)


            unreach = []

            if reach:
                print('reach', flush=True)
                reach_results, unreach, instm, solvingm = self._run_reach(kripke, encoding)
                results.update(reach_results)
                Main._print_stats("Reach", instm, solvingm)
                print('  Unreachable Nodes (' + str(len(unreach)) + '): ')
                for node in unreach:
                    print('    ' + node + ': ' + str(kripke.GetNode(node).Desc))

            if lppreach:
                print('long path reach', flush=True)
                reach_results, unreach, instm, solvingm = self._run_long_path_reach(kripke, encoding)
                results.update(reach_results)

                Main._print_stats("Long Path Reach", instm, solvingm)
                print('  Unreachable Nodes (' + str(len(unreach)) + '): ')
                for node in unreach:
                    print('    ' + node + ': ' + str(kripke.GetNode(node).Desc))

            if lppshadow and (reach or lppreach):
                print('long path shadow', flush=True)

                shadow_results, instm, solvingm = self._run_long_path_shadow(kripke, encoding, unreach)
                results.update(shadow_results)

                Main._print_stats("Long Path Shadow", instm, solvingm)
                shadowed = [
                    n for n, r in results.items() if n.endswith('_lppshadow') and r == []
                ]
                print('  Shadowed Nodes ({:d})'.format(len(shadowed)))
                for node in shadowed:
                    print('    ' + node + ': ' + str(kripke.GetNode(node[:-10]).Desc))

            if shadow:
                print('shadow', flush=True)
                instm = []
                solvingm = []
                shadow_results, instm, solvingm = self._run_shadow(kripke, encoding)
                results.update(shadow_results)

                Main._print_stats("Shadow", instm, solvingm)
                shadowed = [n for n, r in results.items() if n.endswith('_shadow') and r == []]

                mappings = json.load(open('/tmp/mappings.json', 'r'))
                original = mappings['original']
                extended = {c : {r : set(e) for r, e in ce.items()} for c, ce in mappings['extended'].items()}

                shadowed_rules = {chain : set() for chain in original}
                shadowed_nodes = set([s[:-7] for s in shadowed])
                for node in shadowed_nodes:
                    chain = node.split('_')[-2]
                    try:
                        original_rule = original[chain][node]
                    except KeyError:
                        continue
                    extended_rules = extended[chain][original_rule]

                    if extended_rules.issubset(shadowed_nodes):
                        shadowed_rules[chain].add(original_rule)

                print('  Shadowed Rules ({:d})'.format(sum([len(s) for _c, s in shadowed_rules.items()])))

                for chain in shadowed_rules:
                    for rule in sorted(
                        shadowed_rules[chain], key=lambda r: int(r.split('_')[-1].lstrip('r'))
                    ):
                        print("    {}: {}".format(
                            kripke.GetNode(rule).RawRuleNo, kripke.GetNode(rule).Desc
                        ))

            if end_to_end:
                print("end to end", flush=True)
                instm = []
                solvingm = []

                reach = Main._gen_up_reach()

                source = lambda src: "%s_output_r0" % src
                target = lambda dst: "%s_input_r0_accept" % dst

                for src, targets in reach.items():
                    for dst in reach.keys():

                        t1 = time.time()
                        instance = Instantiator.InstantiateEndToEnd(kripke, encoding, source(src), target(dst))
                        t2 = time.time()
                        td = t2 - t1
                        instm.append(td)

                        t1 = time.time()
                        result = self._solver.Solve(instance)
                        t2 = time.time()
                        td = t2 - t1
                        solvingm.append(td)

                        results['%s_to_%s' % (src, dst)] = result

                        if dst in targets and result:
                            print('  correct for %s -> %s' % (src, dst), file=sys.stderr, flush=True)
                        elif dst in targets and not result:
                            print('  failed for %s -> %s' % (src, dst), file=sys.stderr, flush=True)
                        elif dst not in targets and result:
                            print('  failed for ! %s -> %s' % (src, dst), file=sys.stderr, flush=True)
                        elif dst not in targets and not result:
                            print('  correct for ! %s -> %s' % (src, dst), file=sys.stderr, flush=True)
                        else:
                            print('  should never occur but did for %s -> %s' % (src, dst), file=sys.stderr, flush=True)

                Main._print_stats("End to End", instm, solvingm)


    def _print_stats(anomaly, instantiation, solving):
        print("  {:21s}\tmean\tmedian\tstddev\tvar\ttotal".format(anomaly))
        print("  Instantiation:\t{:.4f}\t{:.4f}\t{:.4f}\t{:.4f}\t{:.4f}".format(
            mean(instantiation),
            median(instantiation),
            stdev(instantiation) if len(instantiation) > 1 else 0.0,
            variance(instantiation) if len(instantiation) > 1 else 0.0,
            sum(instantiation)
        ))
        print("  Solving:\t\t{:.4f}\t{:.4f}\t{:.4f}\t{:.4f}\t{:.4f}".format(
                mean(solving),
                median(solving),
                stdev(solving) if len(solving) > 1 else 0.0,
                variance(solving) if len(solving) > 1 else 0.0,
                sum(solving)
            ),
            flush=True
        )


    def __init__(self, networks, solver=PycoSATAdapter(), anomalies={}):
        self._solver = solver
        self._networks = networks
        self._anomalies = {
            'reach' : False,
            'cycle' : False,
            'shadow' : False,
            'cross' : False,
            'lppreach' : False,
            'lppshadow' : False,
            'end_to_end' : False
        }
        self._anomalies.update(anomalies)


    def _gen_up_reach():
        internet = ["internet_provider_fw"]
        dns = ["ups_dns_fw"]
        dmz_servers = [
            "ups_admin_fw", "ups_data_fw", "ups_file_fw",
            "ups_ldap_fw", "ups_mail_fw", "ups_mail_fw", "ups_vpn_fw",
            "ups_web_fw"
        ]
        subnet_servers = [
            "api_server_fw", "asta_server_fw", "bgp_server_fw", "chem_server_fw",
            "cs_server_fw", "geog_server_fw", "geo_server_fw", "hgp_server_fw",
            "hpi_server_fw", "hssp_server_fw", "intern_server_fw",
            "intern_server_fw", "jura_server_fw", "ling_server_fw",
            "math_server_fw", "mmz_server_fw", "physik_server_fw",
            "pogs_server_fw", "psych_server_fw", "sq_server_fw",
            "stud_server_fw", "ub_server_fw", "welc_server_fw"
        ]
        res = {
            "api_client_fw" : internet + dns + dmz_servers + subnet_servers,
            "api_server_fw" : dns,
            "asta_client_fw" : internet + dns + dmz_servers + subnet_servers,
            "asta_server_fw" : dns,
            "bgp_client_fw" : internet + dns + dmz_servers + subnet_servers,
            "bgp_server_fw" : dns,
            "chem_client_fw" : internet + dns + dmz_servers + subnet_servers,
            "chem_server_fw" : dns,
            "cs_client_fw" : internet + dns + dmz_servers + subnet_servers,
            "cs_server_fw" : dns,
            "geo_client_fw" : internet + dns + dmz_servers + subnet_servers,
            "geog_server_fw" : dns,
            "geog_client_fw" : internet + dns + dmz_servers + subnet_servers,
            "geo_server_fw" : dns,
            "hgp_client_fw" : internet + dns + dmz_servers + subnet_servers,
            "hgp_server_fw" : dns,
            "hpi_client_fw" : internet + dns + dmz_servers + subnet_servers,
            "hpi_server_fw" : dns,
            "hssp_client_fw" : internet + dns + dmz_servers + subnet_servers,
            "hssp_server_fw" : dns,
            "intern_client_fw" : internet + dns + dmz_servers + subnet_servers,
            "internet_provider_fw" : internet + dns + dmz_servers + subnet_servers,
            "intern_server_fw" : dns,
            "jura_client_fw" : internet + dns + dmz_servers + subnet_servers,
            "jura_server_fw" : dns,
            "ling_client_fw" : internet + dns + dmz_servers + subnet_servers,
            "ling_server_fw" : dns,
            "math_client_fw" : internet + dns + dmz_servers + subnet_servers,
            "math_server_fw" : dns,
            "mmz_client_fw" : internet + dns + dmz_servers + subnet_servers,
            "mmz_server_fw" : dns,
            "physik_client_fw" : internet + dns + dmz_servers + subnet_servers,
            "physik_server_fw" : dns,
            "pogs_client_fw" : internet + dns + dmz_servers + subnet_servers,
            "pogs_server_fw" : dns,
            "psych_client_fw" : internet + dns + dmz_servers + subnet_servers,
            "sq_client_fw" : internet + dns + dmz_servers + subnet_servers,
            "sq_server_fw" : dns,
            "stud_client_fw" : internet + dns + dmz_servers + subnet_servers,
            "stud_server_fw" : dns,
            "ub_client_fw" : internet + dns + dmz_servers + subnet_servers,
            "ub_server_fw" : dns,
            "upc_client0_fw" : internet + dns + dmz_servers + subnet_servers,
            "upc_client1_fw" : internet + dns + dmz_servers + subnet_servers,
            "up_gateway_fw" : dns,
            "ups_admin_fw" : internet + dns + dmz_servers + ["up_gateway_fw"],
            "ups_data_fw" : dns,
            "ups_dns_fw" : dns,
            "ups_file_fw" : dns,
            "ups_ldap_fw" : dns,
            "ups_mail_fw" : dns,
            "ups_vpn_fw" : dns,
            "ups_web_fw" : dns,
            "welc_client_fw" : internet + dns + dmz_servers + subnet_servers,
            "welc_server_fw" : dns
        }

        return res


def _gen_config(rulesets, network, dump_mappings=False):
    fws = [
        IP6TablesParser.parse(
            open(r).read(),
            n,
            dump_mappings=dump_mappings
        ) for n, r in rulesets.items()
    ]
    network = et.parse(network)

    config = GenUtils.config()
    firewalls = GenUtils.firewalls()
    firewalls.extend(fws)
    config.append(firewalls)
    config.append(network.getroot())

    return config


if __name__ == "__main__":
    sys.setrecursionlimit(10**6)

    parser = argparse.ArgumentParser()
    parser.add_argument('--networks', dest='networks', type=str, nargs='+', default=[])
    parser.add_argument('--solver', dest='solver', choices=['clasp', 'mini', 'pyco'], default='pyco')
    parser.add_argument('--profile', dest='profile', action='store_const', const=True, default=False)
    if sys.version_info.major == 3 and sys.version_info.minor >= 8:
        parser.add_argument('--anomalies', dest='anomalies', action='extend', nargs='+', choices=[
            'reach', 'cycle', 'shadow', 'cross', 'lppreach', 'lppshadow', 'end_to_end'
        ], default=[])
    else:
        parser.add_argument('--anomalies', dest='anomalies', default=[], type=lambda a: a.split(','))
    parser.add_argument(
        '--rulesets',
        dest='rulesets',
        type=lambda rs: dict([r.split(':') for r in rs.split(',')]),
        default={'tum_fw' : 'bench/tum/tum-ruleset'}
    )
    parser.add_argument(
        '--ruleset',
        dest='rulesets',
        type=lambda r: dict([r.split(':')]),
        default={'tum_fw' : 'bench/tum/tum-ruleset'}
    )
    parser.add_argument('--network', dest='network', default='bench/tum/tum.xml')

    args = parser.parse_args(sys.argv[1:])

    if args.solver == 'clasp':
        solver = ClaspAdapter('/dev/shm/solver.in')
    elif args.solver == 'mini':
        solver = MiniSATAdapter('/dev/shm/solver.in','/dev/shm/solver.out')
    elif args.solver == 'pyco':
        solver = PycoSATAdapter()
    else:
        solver = PycoSATAdapter()

    networks = [
        et.ElementTree(
            _gen_tum_config(
                network,
                dump_mappings=any([
                    'reach' in args.anomalies,
                    'lppreach' in args.anomalies
                ])
            )
        ) for network in args.networks
    ]

    networks = [et.ElementTree(
        _gen_config(args.rulesets, args.network, dump_mappings=True)
    )]

    anomalies = {
        'reach' : False,
        'cycle' : False,
        'shadow' : False,
        'cross' : False,
        'lppreach' : False,
        'lppshadow' : False,
        'end_to_end' : False
    }
    for anomaly in args.anomalies: anomalies[anomaly] = True

    if args.profile:
        yappi.start()

    main = Main(networks, solver=solver, anomalies=anomalies)
    main.main()

    if args.profile:
        yappi.stop()
        yappi.get_func_stats().save(parser.profile, type='pstat')
