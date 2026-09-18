#!/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2023 Claas Lorenz <claas_lorenz@genua.de>

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

import argparse
import json


from util.aggregator_utils import connect_to_fave, fave_sendmsg
from util import barrier
from util.aggregator_utils import FAVE_DEFAULT_UNIX, FAVE_DEFAULT_IP, FAVE_DEFAULT_PORT
from util.match_util import OXM_FIELD_TO_MATCH_FIELD


def _parse_check(check):
    tokens = check.split()

    src = None
    dst = None
    negated = False
    cond = []

    for token in tokens:
        if token == '!': negated = True
        elif token.startswith('s='): src = token[2:]
        elif token.startswith('p='): dst = token[2:]
        elif token.startswith('f='):
            # `f=!field:value` negates the FIELD, which is independent of the
            # leading `!` that negates the reachability. RuleField has always
            # carried the flag and NetPlumberAdapter._expand_negated_field has
            # always expanded it; only this parser hardcoded False, which made
            # "reaches on any port other than X" inexpressible
            # (CLOUD_BENCH_PLAN.md §1.4, query 04).
            field, value = token[2:].split(':')
            field_negated = field.startswith('!')
            if field_negated:
                field = field[1:]
            cond.append({
                'name' : OXM_FIELD_TO_MATCH_FIELD[field],
                'value' : value,
                'negated' : field_negated
            })

    assert src is not None and dst is not None

    return (src, dst, negated, cond)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('checks_file')
    parser.add_argument(
        '-u', '--use-unix',
        dest='use_unix',
        action='store_const',
        const=True,
        default=False
    )


    args = parser.parse_args()

    checks = json.load(open(args.checks_file, 'r'))

    rules = {}

    for check in checks:
        src, dst, negated, cond = _parse_check(check)

        rules.setdefault(dst, [])
        rules[dst].append((src, negated, cond))

    fave = connect_to_fave(
        *(
            (
                FAVE_DEFAULT_UNIX, 0
            ) if args.use_unix else (
                FAVE_DEFAULT_IP, FAVE_DEFAULT_PORT
            )
        )
    )

    fave.setblocking(1)

    # Guard the request with a barrier and BLOCK on it (TODO.md item 1r):
    # posting a check and exiting only proves FaVe accepted it, so the caller
    # would go on to read a verdict that does not exist yet. Because this runs
    # as a subprocess, waiting here is what makes the benchmark's `_compliance`
    # phase actually mean "compliance has been checked".
    guard = barrier.arm()

    fave_sendmsg(
        fave, json.dumps({
            'type' : 'check_compliance', 'rules' : rules, 'barrier' : guard
        })
    )

    fave.close()

    # No timeout: waits while FaVe is provably alive, fails the moment it is
    # not. See util/barrier.py for why a wall-clock deadline is unusable here.
    barrier.wait(guard)
