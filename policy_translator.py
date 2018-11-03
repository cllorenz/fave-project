#! /usr/bin/env python2
# -*- coding: utf-8 -*-

# Copyright 2018 Vera Clemens

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

from policy import Policy
from policybuilder import PolicyBuilder
from policy_exceptions import PolicyException
import sys
import argparse

def main():
    """Builds a Policy object out of an inventory and policy file and optionally
    generates reachability tables in HTML or CSV formats."""

    parser = argparse.ArgumentParser(description='Liest Policies aus einer Datei und übersetzt sie wahlweise in HTML oder CSV.')
    parser.add_argument('files', metavar='FILE', nargs='+', help='Either an inventory file followed by a policy file, or a single file that combines both.')
    parser.add_argument('--html', dest='generate_html', action='store_const', const=True, default=False, help='Generate the html file.')
    parser.add_argument('--csv', dest='generate_csv', action='store_const', const=True, default=False, help='Generate the csv file.')
    args = parser.parse_args()

    files = []
    try:
        for i in range(min(2, len(args.files))):
            files.append(open(args.files[i], 'r'))
    except IOError:
        print("Fehler: Datei(en) konnte(n) nicht gelesen werden.")
        sys.exit(1)

    policy_chars = "".join([file.read() for file in files])
    policy = Policy()
    try:
        PolicyBuilder.build(policy_chars, policy)

        prefix = args.files[-1].rsplit('.', 1)[0]

        if args.generate_html:
            html_file = open(prefix + '-reachability.html', 'w')
            html_file.write(policy.to_html())

        if args.generate_csv:
            csv_file = open(prefix + '-reachability.csv', 'w')
            csv_file.write(policy.vlans_to_csv())
    except PolicyException, exception:
        print("Fehler: %s" % exception)

if __name__ == "__main__":
	main()
