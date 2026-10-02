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

""" This module benchmarks FaVe using an generic workload.
"""

import json
import os
import sys
import logging
import argparse

from bench.generic_benchmark import GenericBenchmark, PYTHON, run_step


class GenericFirewallBenchmark(GenericBenchmark):
    """ This class provides a generic benchmark to check compliance for firewall
        rule sets.
    """

    def _pre_preparation(self):
        run_step(
            'cp %s bench/wl_generic_fw/interfaces.json' % self.files['genfw_interfaces'],
            self.logger, "copying the interface mapping")


    def _post_preparation(self):
        # The ONLY workload-specific step. `topogen.py` defaults to ipv6 and the
        # default ruleset, which is what the base class's zero-argument call
        # gets; this is how `-4` and `-r` reach the model, so it runs second and
        # wins.
        #
        # `PYTHON`, not a bare `python3`: the latter is whatever PATH resolves,
        # which in a container whose venv is not activated is the system
        # interpreter with none of FaVe's dependencies.
        run_step(
            "%s bench/wl_generic_fw/topogen.py %s %s" % (
                PYTHON, self.ip, self.files['genfw_ruleset']),
            self.logger, "generating the wl_generic_fw topology")

        # A SECOND CONVERSION USED TO FOLLOW, and it is gone rather than fixed
        # (TODO item 32). It ran `bench/wl_generic_fw/reach_csv_to_checks.py`,
        # which has never existed -- the script is `bench/reach_csv_to_checks.py`
        # -- so `os.system` printed "can't open file" to a stderr nobody read
        # and the run carried on with the base class's `checks.json`.
        #
        # Correcting the path would have made it WORSE, not better, because the
        # call is a lossy duplicate of `GenericBenchmark._convert_policy_to_
        # checks`, which has already run by this point:
        #   * it omits `--roles`, so a role whose single node stands for a whole
        #     subnet loses its self-check;
        #   * it omits `--strict`, which decides whether a filled diagonal means
        #     anything at all;
        #   * it omits `-m`, so `--inventory-mapping` falls back to
        #     `inventory.json` RELATIVE TO THE CWD -- `fave/inventory.json`,
        #     which does not exist -- where the base class passes this
        #     workload's own `bench/empty.json`;
        #   * it omits `--cchecks`, so the conditional checks would be written
        #     to `fave/cchecks.json`, INTO THE SOURCE TREE. That is the same
        #     defect TODO item 37 fixed in `inventorygen.py`.
        # The base class's conversion is simply the right one for this
        # workload, and there was never a second question to ask.


if __name__ == '__main__':
    np_config = "bench/wl_generic_fw/default/np.conf"

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
    # RESTORED 2026-10-02 (TODO item 32). `6408fcb1` (2021) converted this
    # benchmark to argparse and inverted this flag's default on the way: before
    # it, `use_state_snapshots` started False and `-n` set it True; after it,
    # the default was True, so EVERY default run behaved as though `-n` had been
    # passed. With `use_internet` then False, the policy translator rejects the
    # default policy's `Internet` role ("Error: Role Internet is unknown"), and
    # with no reachability matrix and no `roles.json` the topology, policy and
    # check generation all fail after it -- every one of them silently, which is
    # why a four-year-old regression left no trace.
    parser.add_argument(
        '-n', '--no-internet',
        dest='use_state_snapshots',
        action='store_true',
        default=False
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

    use_internet = not args.use_state_snapshots

    files = {
        'roles_json' : 'bench/wl_generic_fw/roles.json',
        'genfw_ruleset' : args.ruleset,
        'genfw_interfaces' : args.interfaces,
        'reach_policies' : args.policy,
        'roles_services' : args.inventory,
        'np_config' : np_config,
        'inventory' : 'bench/empty.json'
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
