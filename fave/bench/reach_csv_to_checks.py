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


import sys
import csv
import json
import argparse


# The one role whose self-reachability is not a question anyone can answer: the
# Internet is external by definition, outside the administrative reach of any
# organisation writing an FPL policy, so whether it reaches itself is not
# verifiable and not meaningful. Every OTHER role's self-rule is an ordinary
# compliance question -- see _abstracts_a_subnet.
_INTERNET = 'Internet'


def _load_role_attributes(path):
    """ {role name: attributes} from a `policy_translator --roles` dump, which
    the translator derives from the FPL inventory (roles_and_services.txt). No
    file => {}, and every self-rule is treated as degenerate, exactly as before
    this argument existed. """
    if not path:
        return {}
    with open(path, 'r') as raw:
        return {role['name']: role.get('attributes', {}) for role in json.load(raw)}


def _abstracts_a_subnet(attributes):
    """ True iff the role's declared address is a PROPER subnet: more than one
    address, but not the whole space.

    This decides whether a role's self-rule (`R <--> R`) states something real.
    A role is one node in the model; what that node STANDS FOR is the question:

      * a bare address, /32 or /128 -- one device. `R <--> R` is then a host
        talking to itself, which is not a network question.
      * a match-all prefix (`0.0.0.0/0`, `::/0`) -- a PLACEHOLDER that carries no
        cardinality at all. wl_i2 and wl_stanford give every router role
        `ipv4 = '0.0.0.0/0'` because those models have no per-role addressing, so
        it is not evidence of many devices either.
      * anything in between -- a subnet, whose single node stands for all the
        devices in it. wl_up's `Wifi` is this case (`ipv6 = 2001:db8:abc:2::0/64`,
        and deliberately no `hosts` list): `Wifi <--> Wifi` says wifi clients may
        talk to each other, which is how wifi networks work -- L2 is generally
        unrestricted, you either have access or you do not -- and is a compliance
        question like any other.
    """
    for field, width in (('ipv4', 32), ('ipv6', 128)):
        value = attributes.get(field)
        if not value:
            continue
        _address, _, length = str(value).partition('/')
        if not length:
            continue                      # a bare address is a single device
        if 0 < int(length) < width:
            return True
    return False


def _peers(sources, target, keep_self):
    """ The sources a check is emitted for against one target.

    A host is not its own peer, so the self-pair is normally dropped: for a role
    listing several hosts this leaves exactly the cross-pairs, which is what the
    self-rule means. But where the role's ONE node stands for a whole subnet,
    that self-pair is the only representation of the intra-subnet traffic the
    rule is about, and dropping it discards the rule entirely. """
    return [s for s in sources if s != target or keep_self]


def _generate_cchecks(checks):
    cchecks = {}

    for check in checks:
        valid = not check.startswith("! ")
        check = check.lstrip('! ')

        cond = []

        tokens = check.split(" && ")
        if len(tokens) == 2:
            src, dst = tokens
        elif len(tokens) == 3:
            src, dst, cond = tokens
            cond = [cond.lstrip("f=")]
        elif len(tokens) > 3:
            src = tokens[0]
            dst = tokens[1]
            cond = [c.lstrip("f=") for c in tokens[2:]]
        else:
            raise Exception("unsupported amount of operands: %s (%s)" % (len(tokens), tokens))

        src = src.lstrip("s").lstrip('=')
        dst = dst.lstrip("EF p").lstrip('=')

        cchecks.setdefault(src, [])
        cchecks[src].append((dst, valid, cond))

    return cchecks


if __name__ == '__main__':
    checks = []

    parser = argparse.ArgumentParser()

    parser.add_argument(
        '-c', '--checks',
        dest='checks_file',
        default='checks.json'
    )
    parser.add_argument(
        '--cchecks',
        dest='cchecks_file',
        default='cchecks.json'
    )
    parser.add_argument(
        '-j', '--reach-json',
        dest='reach_file',
        default='reachable.json'
    )
    parser.add_argument(
        '-m', '--inventory-mapping',
        dest='inventory_file',
        default='inventory.json'
    )
    parser.add_argument(
        '-p', '--policy-csv',
        dest='policy_file',
        default='policy.csv'
    )
    parser.add_argument(
        '-s', '--suffix',
        dest='suffix',
        default=''
    )
    parser.add_argument(
        '--roles',
        dest='roles_file',
        default=None,
        help='Atomic-role dump from `policy_translator --roles`. Lets a role '
             'whose single node stands for a whole subnet carry a self-check; '
             'without it every self-rule is treated as degenerate.'
    )

    args = parser.parse_args(sys.argv[1:])

    mapping = json.load(open(args.inventory_file, 'r'))
    role_attributes = _load_role_attributes(args.roles_file)

    checks = []
    reach_json = {}
    with open(args.policy_file, 'r') as csv_file:
        reader = csv.reader(csv_file, delimiter=',')

        header = next(reader)[1:]

        for row in reader:

            row_iter = iter(row)

            source_role = source = next(row_iter)
            sources = [s+args.suffix if s != 'Internet' else s for s in mapping[source]] if mapping else [source+args.suffix if source != 'Internet' else source]

            if source != 'Internet':
                source += args.suffix

            for idx, flag in enumerate(row_iter):
                target_role = target = header[idx]
                targets = [t+args.suffix if t != 'Internet' else t for t in mapping[target]] if mapping else [target+args.suffix if target != 'Internet' else target]

                # The Internet's self-reachability is omitted: it is an external
                # entity, out of administrative reach of whoever writes the
                # policy, so the question is not answerable (and FPL carries
                # `Internet` as a builtin role, so it appears in most policies).
                if source == _INTERNET and source == target: continue

                if target != 'Internet': target += args.suffix

                # Does this cell's self-pair carry a check? Only on a role's own
                # diagonal, and only where that role's single node stands for a
                # subnet rather than one device -- see _abstracts_a_subnet.
                keep_self = (
                    source_role == target_role
                    and source_role != _INTERNET
                    and len(sources) == 1 and len(targets) == 1
                    and _abstracts_a_subnet(role_attributes.get(source_role, {}))
                )

                for target in targets:
                    reach_json.setdefault(target, [])

                fstr = 's=source.%s && EF p=probe.%s'
                if flag == 'X':
                    for target in targets:
                        reach_json[target].extend(_peers(sources, target, keep_self))
                        checks.extend([fstr % (s, target) for s in _peers(sources, target, keep_self)])

                elif flag == '(X)':
                    for target in targets:
                        reach_json[target].extend(_peers(sources, target, keep_self))
                        checks.extend([fstr % (s, target) + ' && f=related:1'
                                       for s in _peers(sources, target, keep_self)])
                        checks.extend(['! ' + fstr % (s, target) + ' && f=related:0'
                                       for s in _peers(sources, target, keep_self)])

                elif flag.startswith('(') and flag.endswith(')'):
                    for target in targets:
                        reach_json[target].extend(_peers(sources, target, keep_self))
                        for condition in flag.lstrip('(').rstrip(')').split('|'):
                            checks.extend([
                                fstr % (s, target) + ' && f=related:0 && ' + ' && '.join(['f='+f for f in
                                    condition.split(';')
                                ]) for s in _peers(sources, target, keep_self)
                            ])

                else:
                    checks.extend(['! ' + fstr % (s, target) for s in sources])


    with open(args.checks_file, 'w') as checks_file:
        checks_file.write(json.dumps(checks, indent=2) + '\n')

    with open(args.reach_file, 'w') as rf:
        rf.write(json.dumps(reach_json, indent=2) + '\n')

    cchecks = _generate_cchecks(checks)

    with open(args.cchecks_file, "w") as cchecks_file:
        cchecks_file.write(json.dumps(cchecks, indent=2) + '\n')
