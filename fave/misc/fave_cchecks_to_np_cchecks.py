#!/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2022 Claas Lorenz <claas_lorenz@genua.de>

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
import json

from rule.rule_model import RuleField
from netplumber.vector import Vector, set_field_in_vector
from util.ip6np_util import field_value_to_bitvector


def _node_to_id(node, node_ids):
    return int(node_ids[node])


def _cond_to_vector(cond, mapping):
    if not cond: return None

    vec = Vector(mapping['length'])

    cond = cond.pop()
    field = RuleField(*(cond.split(':')))

    set_field_in_vector(mapping, vec, field.name, field_value_to_bitvector(field).vector)

    return vec.vector

argv = sys.argv[1:]
cchecks = json.load(open(argv[0], 'r'))
fave = json.load(open(argv[1], 'r'))

mapping = fave['mapping']
generator_to_id = {v:k for k,v in list(fave['id_to_generator'].items())}

probe_to_id = {v:k for k,v in list(fave['id_to_probe'].items())}

np_cchecks = {}

for src, rules in list(cchecks.items()):
    src = _node_to_id(src, generator_to_id)

    for rule in rules:
        dst, valid, cond = rule
        dst = _node_to_id(dst, probe_to_id)

        np_cchecks.setdefault(dst, [])
        np_cchecks[dst].append((src, valid, _cond_to_vector(cond, mapping)))

json.dump(np_cchecks, open(argv[2], 'w'))
