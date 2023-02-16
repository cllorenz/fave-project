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
            field, value = token[2:].split(':')
            cond.append({'name' : field, 'value' : value, 'negated' : False})

    assert src is not None and dst is not None

    return (src, dst, negated, cond)



if __name__ == '__main__':
    checks = json.load(open(sys.argv[1], 'r'))

    rules = {}

    for check in checks:
        src, dst, negated, cond = _parse_check(check)

        rules.setdefault(dst, [])
        rules[dst].append((src, negated, cond if cond else None))

    fave = connect_to_fave()
    fave.sendmsg({'type' : 'check_compliance', 'rules' : rules})
