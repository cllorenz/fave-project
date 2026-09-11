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
     the acyclic rank constraints ONCE (under the default
     `grounding='rank'` -- SCC-scoped, so this is cheap on an
     essentially-acyclic real topology like wl_up/wl_ifi/wl_tum, and the
     cost that made B1's per-query rebuild+CEGAR architecture a NO-GO for
     wl_stanford specifically). Under `grounding='flow'` no rank
     constraints are built at all and the grounding is a per-query
     single-unit s-t flow instead -- see GROUNDINGS below;
  2. converts that combined base to DIMACS ONCE
     (AbstractSolver._ConvertToDIMACS, the exact numbering
     MiniSATAdapter/ClaspAdapter/PycoSATAdapter already use) and loads it
     into ONE persistent PySAT Minisat22 instance under `grounding='rank'`
     (its real native
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


# AD6_PLAN.md §5.4 B1 / §5.5: the two grounding strategies that close the
# SECRYPT'15 formalism's gap (ad6/FAVE_CHANGES.md §20). They answer the SAME
# question and are held to identical ground truth by
# instantiatortest.py::IncrementalSessionGroundingTest -- they differ in cost
# and in scope:
#
#   'rank' -- Instantiator._CreateAcyclicConstraints, a per-edge rank
#       comparator baked into the SHARED base. Property-agnostic (it forbids
#       every floating cycle regardless of what is asked afterwards), so it is
#       the only option for a query that is not a single source->destination
#       reachability question, and the default for that reason.
#   'flow' -- Instantiator._CreateFlowPathConstraints, a single-unit s-t flow.
#       Reachability-SPECIFIC: it names the endpoints, so it is per-query by
#       construction and cannot live in a shared base. Measured on
#       wl_stanford N=16 faithful-VLAN under a MATCHED configuration (both
#       cadical195, same model, same 256 queries, same answer of 165
#       reachable pairs): 163.5s wall / 117.2s query / 1,491 MB peak against
#       the rank encoding's 1,136.9s / 1,086.2s / 2,051 MB -- 7.0x wall, 9.3x
#       query, 1.4x memory -- WHILE giving up incremental reuse across
#       queries. (An earlier 21.7x figure compared the two under DIFFERENT
#       solvers and encodings; see AD6_PLAN.md §7.5.)
GROUNDING_RANK = 'rank'
GROUNDING_FLOW = 'flow'
GROUNDINGS = (GROUNDING_RANK, GROUNDING_FLOW)


class IncrementalSession:
    """ One persistent incremental-solving session for one Kripke/base-
    encoding pair -- built once per benchmark run (mirrors the scope
    `fave_bridge.py`'s old `acyclic_cache` dict had), reused across every
    query. Not thread-safe (PySAT's Minisat22 isn't); one session per
    process, matching `fave_bridge.py`'s own single-threaded query loop. """

    def __init__(self, kripke, encoding, grounding=GROUNDING_RANK):
        if grounding not in GROUNDINGS:
            raise ValueError(
                "unknown grounding strategy %r -- expected one of %s" % (
                    grounding, ', '.join(repr(g) for g in GROUNDINGS)))
        self._kripke = kripke
        # Public on purpose: a caller reporting a measurement has to be able to
        # stamp WHICH grounding produced it (AD6_PLAN.md's generality-debt
        # gate -- the encoding is measurement-affecting configuration).
        self.grounding = grounding

        combined = encoding
        if grounding == GROUNDING_RANK:
            acyclic_constraints = Instantiator._CreateAcyclicConstraints(kripke)
            combined = deepcopy(encoding)
            combined[0].extend(deepcopy(acyclic_constraints))

        adapter = AbstractSolver()
        # Read-only on its argument, so 'flow' hands it `encoding` directly and
        # skips the deepcopy the rank path needs in order to extend it.
        variables, dimacs_clauses = adapter._ConvertToDIMACS(combined)
        self._name_to_index = {name: i + 1 for i, name in enumerate(variables)}
        self._next_index = len(variables) + 1

        if grounding == GROUNDING_RANK:
            self._dimacs_clauses = None
            self._solver = Minisat22(bootstrap_with=dimacs_clauses)
        else:
            # The flow constraint names THIS query's endpoints, so a reused
            # solver would still assert query 1's flow during query 2 (see
            # _CreateFlowPathConstraints' own docstring, and
            # test_flow_grounding_does_not_leak_between_queries). Retain the
            # base DIMACS and bootstrap a fresh solver per query instead --
            # the architecture `bench/ad6_i2_measure.py --flow-path
            # --fresh-per-query` is validated under, and measured CHEAPER in
            # peak RSS than the persistent session on wl_i2 despite the
            # retained clause list (9,183 MB vs 13,432 MB).
            self._dimacs_clauses = dimacs_clauses
            self._solver = None

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
        `_seed_literals`/`_state_literals` already produce).

        Under GROUNDING_FLOW this answers the identical question through
        a fresh per-query solver carrying that query's own single-unit
        s-t flow constraint; under GROUNDING_RANK through the shared,
        rank-constrained persistent session. Both are held to the same
        ground truth by
        instantiatortest.py::IncrementalSessionGroundingTest. """
        f_trans = [XMLUtils.CreateTransition(source, target, flag)
                   for target, flag in self._kripke.IterFTransitions(source)]
        b_trans = [XMLUtils.CreateTransition(predecessor, destination, flag)
                   for predecessor, flag in self._kripke.IterBTransitions(destination)]

        src_lit, src_clauses = self._or_gate(f_trans)
        dst_lit, dst_clauses = self._or_gate(b_trans)

        if self.grounding == GROUNDING_RANK:
            for clause in src_clauses + dst_clauses:
                self._solver.add_clause(clause)
            assumptions = [src_lit, dst_lit] + [self._literal(v) for v in extra_vars]
            return bool(self._solver.solve(assumptions=assumptions))

        flow_clauses = Instantiator._CreateFlowPathConstraints(
            self._kripke, source, destination)
        if any(not clause for clause in flow_clauses):
            # A single EMPTY clause is how _CreateFlowPathConstraints reports
            # "the source can emit no unit" / "the destination can accept
            # none" -- an unreachable endpoint by construction. Refute it here
            # rather than handing an empty clause to the solver, so the answer
            # comes back as an ordinary False like any other refutation.
            return False

        solver = Minisat22(bootstrap_with=self._dimacs_clauses)
        try:
            for clause in src_clauses + dst_clauses:
                solver.add_clause(clause)
            # Units, not assumptions: this solver is discarded at the end of
            # the query, so there is nothing to retract, and it keeps the shape
            # identical to the validated `--flow-path --fresh-per-query` driver
            # path (which needs units because Kissat404 has no assumptions API).
            solver.add_clause([src_lit])
            solver.add_clause([dst_lit])
            for clause in flow_clauses:
                solver.add_clause([
                    -self._index_for(name) if negated else self._index_for(name)
                    for name, negated in clause])
            for xml_var in extra_vars:
                solver.add_clause([self._literal(xml_var)])
            return bool(solver.solve())
        finally:
            solver.delete()

    def Close(self):
        # 'flow' holds no persistent solver -- each query builds and deletes
        # its own -- so Close stays a no-op there rather than an AttributeError.
        if self._solver is not None:
            self._solver.delete()
            self._solver = None
