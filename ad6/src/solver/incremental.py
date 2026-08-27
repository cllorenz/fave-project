#/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2026 Claas Lorenz <claas_lorenz@genua.de>

# This file is part of ad6.

# ad6 is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# ad6 is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with ad6.  If not, see <https://www.gnu.org/licenses/>.

""" AD6_PLAN.md §6 / AD6_ENCODING_PLAN.md §§3.4-3.10: the incremental/
assumption-based solving lever, confirmed empirically against ad6's real
production models -- ~100-490x faster on wl_up's full real 11,902-query
`cchecks.json` (§3.7-3.9), and rescues wl_stanford's B1 wall-clock NO-GO
for `SolveAcyclicEndToEnd`'s own reachability question (~16 min for the
full real 256-pair all-pairs matrix vs. a 6-hour/28.9%-complete measured
result and ~20-21h extrapolation, §3.10) -- WITHOUT needing CEGAR at all,
because the SCC-scoped acyclic rank constraints
(Instantiator._CreateAcyclicConstraints) are sound by construction via a
PLAIN solve (see that function's own docstring): a cycle of
simultaneously-true edges forces a numeric contradiction in the rank
encoding regardless of what any node's rank value is, so there is no
structural escape hatch the way `_CreateCycle`'s negation has.

This session, per query:
  1. builds the base encoding ONCE (favemodel.instantiate_base's
     `encoding`, exactly what fave_bridge.py already builds today) plus
     the acyclic rank constraints ONCE (baked in unconditionally --
     SCC-scoped, so this is cheap on an essentially-acyclic real topology
     like wl_up/wl_ifi/wl_tum, and the cost that made B1's per-query
     rebuild+CEGAR architecture a NO-GO for wl_stanford specifically);
  2. converts that combined base to DIMACS ONCE
     (AbstractSolver._ConvertToDIMACS, the exact numbering
     MiniSATAdapter/ClaspAdapter/PycoSATAdapter already use) and loads it
     into ONE persistent PySAT Minisat22 instance (its real native
     incremental library API -- add_clause/solve(assumptions=...)
     reusing internal state across calls, confirmed to survive genuine
     cross-source variation, not just fixed-source flooding, §3.5);
  3. answers each query as a single incremental solve, adding only that
     query's own small delta (an OR-gate Tseitin auxiliary per
     disjunction, since PySAT assumptions must be single literals, unlike
     Z3's arbitrary-formula assumptions -- §3.9) -- no deepcopy of the
     base, no from-scratch DIMACS reconversion, no CEGAR loop.

Empirically validated (AD6_ENCODING_PLAN.md §3.10, `ad6_encoding_bench/
axis8c_stanford_pysat.py`/`axis8d_stanford_netplumber_diff.py`): 0
mismatches against ad6's own current architecture on wl_stanford's real
16-router topology, including the two specific pairs known to require
escalation under the old architecture. """

from src.core.instantiator import Instantiator
from src.solver.solver import AbstractSolver
from src.xml.xmlutils import XMLUtils

from pysat.solvers import Minisat22

from copy import deepcopy


class IncrementalSession:
    """ One persistent incremental-solving session for one Kripke/base-
    encoding pair -- built once per benchmark run (mirrors the scope
    `fave_bridge.py`'s old `acyclic_cache` dict had), reused across every
    query. Not thread-safe (PySAT's Minisat22 isn't); one session per
    process, matching `fave_bridge.py`'s own single-threaded query loop. """

    def __init__(self, kripke, encoding):
        self._kripke = kripke
        acyclic_constraints = Instantiator._CreateAcyclicConstraints(kripke)
        combined = deepcopy(encoding)
        combined[0].extend(deepcopy(acyclic_constraints))

        adapter = AbstractSolver()
        variables, dimacs_clauses = adapter._ConvertToDIMACS(combined)
        self._name_to_index = {name: i + 1 for i, name in enumerate(variables)}
        self._next_index = len(variables) + 1
        self._solver = Minisat22(bootstrap_with=dimacs_clauses)

    def _index_for(self, name):
        index = self._name_to_index.get(name)
        if index is None:
            index = self._next_index
            self._name_to_index[name] = index
            self._next_index += 1
        return index

    def _literal(self, xml_var):
        index = self._index_for(xml_var.attrib[XMLUtils.ATTRNAME])
        return -index if xml_var.attrib.get(XMLUtils.ATTRNEGATED) == 'true' else index

    def _or_gate(self, xml_vars):
        """ Returns (literal, extra_clauses) for the disjunction of
        xml_vars -- 0 vars is UNSAT (a fresh aux var forced false), 1 var
        needs no gate, >1 gets a fresh Tseitin OR-gate aux var. Mirrors
        `ad6_encoding_bench/axis7_native_incremental.py`'s DimacsBridge,
        validated there first. """
        literals = [self._literal(v) for v in xml_vars]
        if not literals:
            aux = self._next_index
            self._next_index += 1
            return aux, [[-aux]]
        if len(literals) == 1:
            return literals[0], []
        aux = self._next_index
        self._next_index += 1
        clauses = [[-lit, aux] for lit in literals] + [[-aux] + literals]
        return aux, clauses

    def Query(self, source, destination, extra_vars=()):
        """ source->destination existential reachability (the same
        question `Instantiator.InstantiateEndToEnd`/`SolveAcyclicEndToEnd`
        answer), plus any already-canonical extra XML `<variable>`
        literals to force (the same shape `fave_bridge.py`'s
        `_seed_literals`/`_state_literals` already produce). """
        f_trans = [XMLUtils.CreateTransition(source, target, flag)
                   for target, flag in self._kripke.IterFTransitions(source)]
        b_trans = [XMLUtils.CreateTransition(predecessor, destination, flag)
                   for predecessor, flag in self._kripke.IterBTransitions(destination)]

        src_lit, src_clauses = self._or_gate(f_trans)
        dst_lit, dst_clauses = self._or_gate(b_trans)
        for clause in src_clauses + dst_clauses:
            self._solver.add_clause(clause)

        assumptions = [src_lit, dst_lit] + [self._literal(v) for v in extra_vars]
        return bool(self._solver.solve(assumptions=assumptions))

    def Close(self):
        self._solver.delete()
