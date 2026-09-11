#!/usr/bin/env python3

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

""" Provenance stamps shared by ad6's measurement drivers (AD6_PLAN.md's
generality-debt gate: "every collapse of the configuration space must be a
stamped field, never an undocumented habit").

Shared rather than duplicated because the whole POINT of these fields is that
two result files can be compared -- `bench/ad6_i2_measure.py` and
`bench/ad6_faithful_measure.py` computing "port-scoped" by two slightly
different rules would defeat the stamp more quietly than omitting it. """


def admission_stamp(ir):
    """ AD6_PLAN.md §5.5: how `ir["in_vlans"]` gates admission, as three
    provenance fields for a result file.

    WHY THIS EXISTS. `faithful_vlan: true` alone does NOT identify the
    encoding any more. Before 2026-09-10 `in_vlans` was a per-DEVICE VLAN
    set; it is now the per-(port, VLAN) relation, and the two produce
    genuinely different reachability on i2 -- the pre-fix model admitted
    2,555 of the 2,564 route-crossings a real per-port configuration rejects.
    Both models stamp `faithful_vlan: true` and `probe_untag: false`, so
    without this a reader comparing
    `eval/ad6_i2_faithful_untagoff_3pairs_sandbox.json` (pre-fix) against a
    post-fix run of the SAME command has only `kripke_nodes` (78,078 vs
    78,524) to tell them apart -- derivable, but implicit, and exactly the
    kind of silent ambiguity between two archived artifacts the other stamps
    exist to prevent.

    Returns `port_scoped` False for a plain IR too (no `in_vlans` at all), so
    the field never reads as "port-scoped" for a model that does no VLAN
    admission whatsoever. """
    in_vlans = ir.get("in_vlans") or {}
    relations = [v for v in in_vlans.values() if isinstance(v, dict)]
    return {
        # True iff EVERY device carries the relation shape. Mixed would mean a
        # partially-migrated IR, which should read as not-port-scoped rather
        # than quietly claiming the stronger model.
        "in_admission_port_scoped": bool(in_vlans) and len(relations) == len(in_vlans),
        "in_admission_ports": sum(len(v) for v in relations),
        "in_admission_pairs": sum(
            len(vlans) for v in relations for vlans in v.values()),
    }
