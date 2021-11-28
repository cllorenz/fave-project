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

import os
import sys
import logging
import getopt

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


def _print_help():
    options = [
        "-4 - use ipv4 for the packet filter",
        "-6 - use ipv6 for the packet filter (default)",
        "-i <inventory> - an inventory file specified in FPL",
        "-p <policy> - a policy file specified in FPL",
        "-r <ruleset> - an iptables rule set",
        "-s - FPL policies should be handled in strict mode",
        "-m <map> - a mapping file with internal and external to interface mappings of the form { \"external\" : \"eth0\", \"internal\" : \"eth1\" }",
        "-v - verbose output"
    ]
    print "usage:\nPYTHONPATH=. python2 bench/wl_generic_fw/benchmark [OPTIONS]\nOptions:"
    for opt in options:
        print " ", opt


if __name__ == '__main__':
    import json
    import os
    import sys

    verbose = False
    ip = 'ipv6'
    strict = ''
    ruleset = "bench/wl_generic_fw/default/ruleset"
    policy = "bench/wl_generic_fw/default/policy.txt"
    inventory = "bench/wl_generic_fw/default/inventory.txt"
    interfaces = "bench/wl_generic_fw/default/interfaces.json"
    np_config = "bench/wl_generic_fw/default/np.conf"

    use_internet = True
    use_state_snapshots = False
    use_unix = False

    try:
        opts, args = getopt.getopt(sys.argv[1:], "hvsr:p:i:m:nu46")
    except getopt.GetoptError as err:
        print "unknown arguments"
        print err
        sys.exit(1)

    for opt, arg in opts:
        if opt == '-v':
            verbose = True
        if opt == '-r':
            ruleset = arg
        if opt == '-p':
            policy = arg
        if opt == '-i':
            inventory = arg
        if opt == '-4':
            ip = 'ipv4'
        if opt == '-6':
            ip = 'ipv6'
        if opt == '-s':
            strict = '--strict '
        if opt == '-m':
            interfaces = arg
        if opt == '-n':
            use_internet = False
            use_state_snapshots = True
        if opt == '-h':
            _print_help()
            sys.exit(0)
        if opt == '-u':
            use_unix = True

    files = {
        'roles_json' : 'bench/wl_generic_fw/roles.json',
        'genfw_ruleset' : ruleset,
        'genfw_interfaces' : interfaces,
        'reach_policies' : policy,
        'roles_services' : inventory,
        'np_config' : np_config
    }

    GenericFirewallBenchmark(
        "bench/wl_generic_fw",
        logger=logging.getLogger("generic_fw"),
        extra_files=files,
        use_internet=use_internet,
        use_interweaving=not use_state_snapshots,
        use_unix=use_unix,
        strict=strict,
        ip=ip
    ).run()
