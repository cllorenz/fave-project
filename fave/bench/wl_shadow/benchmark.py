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

""" Shadowing benchmark.
"""


import os
import argparse
import logging
import time
import json


from bench.generic_benchmark import GenericBenchmark


class ShadowingBenchmark(GenericBenchmark):
    def _reachability(self):
        pass


    def _post_preparation(self):
        os.system("python3 bench/wl_shadow/topogen.py %s %s" % (
            self.ip, self.files['shadow_ruleset']
        ))


    def _generate_policy_matrix(self):
        pass


    def _convert_policy_to_checks(self):
        pass


    def _compliance(self):
        pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-u', '--use-unix',
        dest='use_unix',
        action='store_const',
        const=True,
        default=False
    )
    parser.add_argument(
        '-v', '--verbose',
        dest='verbose',
        action='store_const',
        const=True,
        default=False
    )
    parser.add_argument(
        '-r', '--ruleset',
        dest='ruleset',
        default='bench/wl_shadow/rules.ipt'
    )
    parser.add_argument(
        '-i', '--inventory',
        dest='inventory',
        default='bench/wl_shadow/inventory.txt'
    )
    parser.add_argument(
        '-p', '--policy',
        dest='policy',
        default='bench/wl_shadow/policy.txt'
    )
    parser.add_argument(
        '--interfaces',
        dest='interfaces',
        default='bench/wl_shadow/interfaces.json'
    )
    parser.add_argument(
        '-6', '--ipv6',
        dest='ip',
        action='store_const',
        const=6,
        default=6
    )
    parser.add_argument(
        '-4', '--ipv4',
        dest='ip',
        action='store_const',
        const=4,
        default=6
    )
    parser.add_argument(
        '-d', '--disable-shadow',
        dest='disable_shadow',
        action='store_const',
        const=True,
        default=False
    )
    parser.add_argument(
        '--reach',
        dest='use_reach',
        action='store_const',
        const=True,
        default=False
    )
    parser.add_argument(
        '--general',
        dest='use_general',
        action='store_const',
        const=True,
        default=False
    )

    args = parser.parse_args()

    files = {
        'shadow_ruleset' : args.ruleset
    }

    anomalies = {'use_shadow' : not args.disable_shadow}
    if args.use_reach: anomalies['use_reach'] = True
    if args.use_general: anomalies['use_use_general'] = True

    ShadowingBenchmark(
        "bench/wl_shadow",
        logger=logging.getLogger("shadow"),
        extra_files=files,
        use_unix=args.use_unix,
        ip=args.ip,
        use_interweaving=False,
        anomalies=anomalies
    ).run()

#    os.system("python3 bench/wl_generic_fw/benchmark.py -6 -n -r %s -i %s -p %s -m %s %s %s" % (
#        args.ruleset,
#        args.inventory,
#        args.policy,
#        args.interfaces,
#        "-u" if args.use_unix else "",
#        "-v" if args.verbose else ""
#    ))
