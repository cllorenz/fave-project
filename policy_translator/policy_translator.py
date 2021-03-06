# -*- coding: utf-8 -*-

# Copyright 2018 Vera Clemens
# List of co-authors:
#    Claas Lorenz <claas_lorenz@genua.de>
#    Benjamin Plewka <plewka@uni-potsdam.de>

# This file is part of Policy Translator.

# Policy Translator is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# Policy Translator is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with Policy Translator.  If not, see <https://www.gnu.org/licenses/>.

import sys
import argparse
import logging
import csv
import json

from policy import Policy
from policy_builder import PolicyBuilder
from policy_exceptions import PolicyException
from policy_logger import PT_LOGGER


def main(argv):
    """Builds a Policy object out of an inventory and policy file and optionally
    generates reachability tables in HTML or CSV formats."""

    parser = argparse.ArgumentParser(description='Liest Policies aus einer Datei und übersetzt sie wahlweise in HTML oder CSV.')
    parser.add_argument('files', metavar='FILE', nargs='+', help='Either an inventory file followed by a policy file, or a single file that combines both.')
    parser.add_argument('-c', '--csv', dest='generate_csv', action='store_const', const=True, default=False, help='Generate the csv file.')
    parser.add_argument('-d', '--debug', dest='debug', action='store_const', const=True, default=False, help='Enable debug output.')
    parser.add_argument('-i', '--inv', dest='generate_inv', action='store_const', const=True, default=False, help='Generate inventory mapping.')
    parser.add_argument('--no-internet', dest='use_internet', default=True, const=False, action='store_const', help='Disable default role for the Internet.')
    parser.add_argument('-o', '--out', dest='out_file', default='reachability.html', help='Store output in a prefixed file.')
    parser.add_argument('-r', '--report', dest='report_csv', default=None, help='Read report input from a csv file.')
    parser.add_argument('--roles', dest='roles_json', default=None, help='Dump roles as json file.')
    parser.add_argument('-s', '--strict', dest='strict', action='store_const', const=True, default=False, help='Use strict mode.')
    parser.add_argument('-t', '--trace', dest='trace', action='store_const', const=True, default=False, help='Enable trace output.')
    parser.add_argument('-w', '--html', dest='generate_html', action='store_const', const=True, default=False, help='Generate the html file.')
    parser.add_argument('-fw', '--firewall', dest='generate_iptables', action='store_const', const=True, default=False, help='Generate the iptables file.')
    args = parser.parse_args(argv)

    if args.trace:
        PT_LOGGER.setLevel(logging.TRACE)
    elif args.debug:
        PT_LOGGER.setLevel(logging.DEBUG)

    files = []
    try:
        for i in range(min(2, len(args.files))):
            files.append(open(args.files[i], 'r'))
    except IOError:
        print("Fehler: Datei(en) konnte(n) nicht gelesen werden.")
        sys.exit(1)

    PT_LOGGER.debug("fetch data from files")
    policy_chars = "".join([f.read() for f in files])
    for file_ in files:
        file_.close()
    if args.report_csv:
        with open(args.report_csv, 'rb') as csv_file:
            rows = csv.reader(csv_file, delimiter=' ', quotechar='|')
            report_csv = [row[0].split(',') for row in rows]

    PT_LOGGER.debug("create policy object")
    policy = Policy(strict=args.strict, use_internet=args.use_internet)
    try:
        PT_LOGGER.debug("build policy")
        PolicyBuilder.build(policy_chars, policy)
        if args.report_csv:
            PolicyBuilder.replace_policy_with_csv(report_csv, policy)

        if args.generate_html:
            with open(args.out_file, 'w') as html_file:
                PT_LOGGER.debug("create and write html output")
                html_file.write(policy.to_html())



        if args.generate_csv:
            with open(args.out_file, 'w') as csv_file:
                PT_LOGGER.debug("create and write csv output")
#                csv_file.write(policy.vlans_to_csv())
                csv_file.write(policy.roles_to_csv())

        if args.roles_json:
            with open(args.roles_json, 'w') as json_file:
                PT_LOGGER.debug("dump roles as json")
                json.dump(policy.roles_to_json(), json_file)

        if args.generate_inv:
            with open(args.out_file, 'w') as mapping_file:
                PT_LOGGER.debug("create and write inventory mapping output")
                mapping_file.write(policy.to_mapping())

        if args.generate_iptables:
            with open(args.out_file, 'w') as iptables_file:
                PT_LOGGER.debug("create and write iptables output")
                iptables_file.write(policy.to_iptables())

    except PolicyException, exception:
        print("Fehler: %s" % exception)

if __name__ == "__main__":
    main(sys.argv[1:])
