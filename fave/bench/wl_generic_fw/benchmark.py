#!/usr/bin/env python2

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

""" This module benchmarks FaVe using an generic workload.
"""

import json
import os
import sys
import logging
import argparse

from bench.generic_benchmark import GenericBenchmark


class GenericFirewallBenchmark(GenericBenchmark):
    """ This class provides a generic benchmark to check compliance for firewall
        rule sets.
    """

    def _pre_preparation(self):
        os.system(
            'cp %s bench/wl_generic_fw/interfaces.json' % self.files['genfw_interfaces']
        )


    def _post_preparation(self):
        os.system(
            "python2 bench/wl_generic_fw/topogen.py %s %s" % (
                self.ip, self.files['genfw_ruleset']
            )
        )

        os.system(
            "python2 bench/wl_generic_fw/reach_csv_to_checks.py " + ' '.join([
                '-p', self.files['reach_csv'],
                '-c', self.files['checks'],
                '-j', self.files['reach_json']
            ])
        )


if __name__ == '__main__':
    np_config = "bench/wl_generic_fw/default/np.conf"

    use_internet = True

    parser = argparse.ArgumentParser()

    parser.add_argument(
        '-v', '--verbose',
        dest='verbose',
        action='store_const',
        const=True,
        default=False
    )
    parser.add_argument(
        '-u', '--use-unix',
        dest='use_unix',
        action='store_const',
        const=True,
        default=False
    )
    parser.add_argument(
        '-n', '--no-internet',
        dest='use_state_snapshots',
        action='store_const',
        const=False,
        default=True
    )
    parser.add_argument(
        '-s', '--strict',
        dest='strict',
        action='store_const',
        const=True,
        default=False
    )
    parser.add_argument(
        '-r', '--ruleset',
        dest='ruleset',
        default="bench/wl_generic_fw/default/ruleset"
    )
    parser.add_argument(
        '-p', '--policy',
        dest='policy',
        default="bench/wl_generic_fw/default/policy.txt"
    )
    parser.add_argument(
        '-i', '--inventory',
        dest='inventory',
        default="bench/wl_generic_fw/default/inventory.txt"
    )
    parser.add_argument(
        '-m', '--interface-mapping',
        dest='interfaces',
        default="bench/wl_generic_fw/default/interfaces.json"
    )
    parser.add_argument(
        '-4', '--ipv4',
        dest='ip',
        action='store_const',
        const='ipv4',
        default='ipv4'
    )
    parser.add_argument(
        '-6', '--ipv6',
        dest='ip',
        action='store_const',
        const='ipv6',
        default='ipv4'
    )

    args = parser.parse_args(sys.argv[1:])

    if args.use_state_snapshots:
        use_internet = False

    files = {
        'roles_json' : 'bench/wl_generic_fw/roles.json',
        'genfw_ruleset' : args.ruleset,
        'genfw_interfaces' : args.interfaces,
        'reach_policies' : args.policy,
        'roles_services' : args.inventory,
        'np_config' : np_config
    }

    GenericFirewallBenchmark(
        "bench/wl_generic_fw",
        logger=logging.getLogger("generic_fw"),
        extra_files=files,
        use_internet=use_internet,
        use_interweaving=not args.use_state_snapshots,
        use_unix=args.use_unix,
        strict='--strict' if args.strict else '',
        ip=args.ip
    ).run()
