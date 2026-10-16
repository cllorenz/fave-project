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

""" The APKeep adapter's engines by name, without loading any of them.

`--apkeep-engine` (the aggregator, `bench/cell_run.py`, the campaigns) names
an engine by an OPTION value; the adapter, its stamps and every record written
since 2026-10-16 name it by the ENGINE's own name. Since that date (owner) the
option `ndd` selects NDD-APKeep, and NDD-Flood -- the option `ndd` before --
is `ndd-flood`. An engine name is never a bare `ndd`, so a record that says
`ndd` predates the rename and means NDD-Flood (`recorded_engine`).
"""

#: `--apkeep-engine` value -> engine name
ENGINE_OPTIONS = {'bdd': 'bdd', 'ndd': 'ndd-apkeep', 'ndd-flood': 'ndd-flood'}


def recorded_engine(name):
    """ The engine a record's `engine` names: a bare `ndd`, written before
    2026-10-16, is NDD-Flood. """
    return 'ndd-flood' if name == 'ndd' else name
