# -*- coding: utf-8 -*-

# Copyright 2026 Claas Lorenz <claas_lorenz@genua.de>

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

""" What the PLAIN wl_i2 model may be held to, against the structural oracle.

Shared by `test_apkeep_i2.py` (BDD) and `test_apkeep_ndd_fwd.py` (NDD), which
gate the same model on two engines and so must judge it the same way.

The plain model drops the VLAN dimension, so it over-approximates by
construction: it reaches all 72 source->probe pairs where the real Internet2
data plane delivers 61. Both gates used to assert equality with
`bench/wl_i2/reachable.json`, the all-to-all POLICY mesh -- which any
over-approximation satisfies by construction, and which reads as a claim that
the model is exact.

`plain_model_violations` states the three properties separately instead. On
their STRENGTH, precisely: while the model reaches every pair, soundness and the
surplus follow algebraically from "reaches all", so this detects exactly what the
`reachable.json` comparison detected -- no more. That is measured, not assumed
(`test_i2_oracle_classification.py`, and the oracle-perturbation case in it, is
what caught an earlier version of this claiming otherwise).

What it buys is ATTRIBUTION, and that is a real difference: a model that sheds
one of the 11 reports only drift, while one that loses a DELIVERABLE pair also
reports unsoundness. `reachable.json` reported those two identically.
"""

import json


def load_unreachable(path):
    """ The (source, probe) base-name pairs the real wl_i2 data plane does NOT
    deliver: exhaustive over IPv4, agreed by NetPlumber and ad6. """
    with open(path) as raw:
        return {tuple(pair) for pair in json.load(raw)["unreachable"]}


def plain_model_violations(got, all_pairs, unreachable):
    """ The properties `got` fails, as a list of human-readable strings (empty
    when the plain model is behaving as documented).

    `got` and `all_pairs` are sets of (source, probe) base-name pairs with
    self-pairs excluded; `unreachable` is the oracle's set.
    """
    truly_reachable = all_pairs - unreachable
    violations = []

    # The measured fact, and the only one of the three with detection power
    # while the model reaches everything.
    missing = all_pairs - got
    if missing:
        violations.append(
            "the VLAN-blind plain model no longer reaches every pair "
            "(%d missing, e.g. %s)" % (len(missing), sorted(missing)[:5]))

    # SOUNDNESS: whatever it relaxes, it may never lose a pair the network
    # really delivers. This is what separates a benign tightening from a bug.
    unsound = truly_reachable - got
    if unsound:
        violations.append(
            "UNSOUND: %d pair(s) the wl_i2 data plane delivers are dropped: %s"
            % (len(unsound), sorted(unsound)))

    # The gap, named rather than left implicit.
    surplus = got - truly_reachable
    if surplus != unreachable:
        violations.append(
            "the over-approximation changed: expected exactly the %d "
            "VLAN-blocked pairs, got %d (%s)"
            % (len(unreachable), len(surplus), sorted(surplus)))

    return violations
