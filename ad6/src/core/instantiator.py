#/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2015 Claas Lorenz <claas_lorenz@genua.de>

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

from copy import deepcopy
from functools import reduce

from src.xml.xmlutils import XMLUtils
from src.sat.satutils import SATUtils
from src.core.kripke import KripkeUtils


class Instantiator:
    _REACH = 'reach'
    _CYCLE = 'cycle'
    _SHADOW = 'shadow'
    _CROSS = 'cross'
    _KRIPKE = 'kripke'
    _BASE = 'base'
    GAMMA = 'gamma'


    def Instantiate(Config,Reach=True,Cycle=False,Shadow=False,Cross=False):
        """ DEPRECATED: Reads a distributed firewall Configuration and transforms it into model checking Instances.
        """
        Kripke,Encoding = Instantiator.InstantiateBase(Config)
        Instances = {}

        if Reach:
            ReachInstances = Instantiator.InstantiateReach(Kripke,Encoding)
            for Instance in ReachInstances:
                Instances[Instance+'_'+Instantiator._REACH] = ReachInstances[Instance]

        if Cycle:
            Instances[Instantiator._CYCLE] = Instantiator.InstantiateCycle(Kripke,Encoding)

        if Shadow:
            ShadowInstances = Instantiator.InstantiateShadow(Kripke,Encoding,Instances)
            for Instance in ShadowInstances:
                Instances[Instance+'_'+Instantiator._SHADOW] = ShadowInstances[Instance]

        if Cross:
            Instances[Instantiator._CROSS] = Instantiator.InstantiateCross(Kripke,Encoding)

        return Instances


    def InstantiateBase(Config, Inits=[], default_inits=True, MutableFields=None, Acyclic=False):
        Kripke = KripkeUtils.ConvertToKripke(Config, default_inits=default_inits)

        for Init in Inits:
            InitNode = Kripke.GetNode(Init)
            if XMLUtils.INIT not in InitNode.Props: InitNode.Props.append(XMLUtils.INIT)
            Kripke.PutInit(Init, InitNode)

        Encoding = Instantiator._InstantiateBase(Kripke)

        # AD6_PLAN.md §5.4 Stage A: MutableFields, e.g. {"vlan": 12} --
        # opt-in (None changes nothing for every existing caller/benchmark,
        # none of which declare a mutable field), so this cannot regress
        # wl_ifi/wl_up/wl_tum. Appended pre-CNF'd (each edge's constraint is
        # already flat, mirroring _ConvertNodesToImplications's own
        # per-edge discipline), same reasoning as the naive-CNF-conversion
        # guardrail in AD6_PLAN.md §5.4/§8.5: this must not itself introduce
        # new alternation depth into the global encoding.
        if MutableFields:
            Encoding[0].extend(Instantiator._CreateMutationConstraints(Kripke, MutableFields))

        # AD6_PLAN.md §5.4 Stage B (B1), Option 2: opt-in (False changes
        # nothing for every existing caller/benchmark), same reasoning as
        # MutableFields above -- cannot regress wl_ifi/wl_up/wl_tum unless
        # they explicitly opt in. See _CreateAcyclicConstraints and
        # instantiatortest.py::testAcyclicRankConstraintRejectsFloatingCycleStatically.
        if Acyclic:
            Encoding[0].extend(Instantiator._CreateAcyclicConstraints(Kripke))

        Variables = Encoding.iterdescendants(XMLUtils.VARIABLE)
        Handled = {}

        for Variable in Variables:
            Instantiator._HandlePrefixes(Variable, Handled)
            Instantiator._HandlePorts(Variable, Handled)
            Instantiator._HandleVlans(Variable, Handled)
            Instantiator._HandleFieldMatches(Variable, Handled, MutableFields)
            Instantiator._HandleOthers(Variable, Handled)

        Keys = list(Handled)

        SrcKeys = [key for key in Keys if key.startswith('src_')]
        DstKeys = [key for key in Keys if key.startswith('dst_')]

        Instantiator._ShortenPrefixes(Handled,SrcKeys)
        Instantiator._ShortenPrefixes(Handled,DstKeys)

        Encoding[0].extend(list(Handled.values()))

        Encoding[0].extend(Instantiator._CreateGlobalConstraints(Kripke,Encoding))

        SATUtils.ConvertToCNF(Encoding)

        return Kripke,Encoding


    def InstantiateReach(Kripke,Encoding,Node=""):
        if Node != "":
            Instance = deepcopy(Encoding)

            if XMLUtils.INIT in Kripke.GetNode(Node).Props:
                return Instance

            try:
                BTransitions = Kripke.IterBTransitions(Node)
                Transitions = [XMLUtils.CreateTransition(Transition,Node,Flag) for Transition,Flag in BTransitions]
            except KeyError:
                if XMLUtils.INIT in Kripke.GetNode(Node).Props:
                    Transitions = [XMLUtils.constant()]
                else:
                    Transitions = [XMLUtils.unsat()]

            if len(Transitions) > 1:
                Disjunction = XMLUtils.disjunction()
                Disjunction.extend(Transitions)
            elif len(Transitions) == 1:
                if Transitions[0].tag == XMLUtils.CONSTANT:
                    Disjunction = XMLUtils.variable('a')
                else:
                    Disjunction = Transitions[0]
            else:
                Disjunction = XMLUtils.unsat()

            Conjunction = Instance[0]
            Conjunction.append(Disjunction)

            return Instance

        Instances = {}
        Nodes = Kripke.IterNodes()
        for Node in Nodes:
            Disjunction = XMLUtils.disjunction()
            try:
                BTransitions = Kripke.IterBTransitions(Node)
                for Transition,Flag in BTransitions:
                    Disjunction.append(XMLUtils.CreateTransition(Transition,Node,Flag))

                if len(list(Disjunction)) == 1:
                    tmp = Disjunction[0]
                    Disjunction.remove(tmp)
                    Disjunction = tmp
            except KeyError:
                if XMLUtils.INIT in Kripke.GetNode(Node).Props:
                    Disjunction = XMLUtils.constant()
                else:
                    Disjunction = XMLUtils.unsat()

            Instance = deepcopy(Encoding)
            Conjunction = Instance[0]
            Conjunction.append(Disjunction)

            Instances[Node] = Instance

        return Instances


    def InstantiateEndToEnd(Kripke, Encoding, Source, Destination):
        Instance = deepcopy(Encoding)

        FTransitions = Kripke.IterFTransitions(Source)
        Transitions = [XMLUtils.CreateTransition(Source, Transition, Flag) for Transition, Flag in FTransitions]

        if len(Transitions) > 1:
            DisjSrc = XMLUtils.disjunction()
            DisjSrc.extend(Transitions)
        elif len(Transitions) == 1:
            if Transitions[0].tag == XMLUtils.CONSTANT:
                DisjSrc = XMLUtils.variable('a')
            else:
                DisjSrc = Transitions[0]
        else:
            DisjSrc = XMLUtils.unsat()

        BTransitions = Kripke.IterBTransitions(Destination)
        Transitions = [XMLUtils.CreateTransition(Transition, Destination, Flag) for Transition, Flag in BTransitions]

        if len(Transitions) > 1:
            DisjDst = XMLUtils.disjunction()
            DisjDst.extend(Transitions)
        elif len(Transitions) == 1:
            if Transitions[0].tag == XMLUtils.CONSTANT:
                DisjDst = XMLUtils.variable('a')
            else:
                DisjDst = Transitions[0]
        else:
            DisjDst = XMLUtils.unsat()

        Conjunction = Instance[0]
        Conjunction.append(DisjSrc)
        Conjunction.append(DisjDst)

        return Instance


    def _WitnessTransitions(Kripke, Model):
        """ The concrete list of (Source, Target, Flag) Kripke transitions
        that fired TRUE in a solved `Model` (a var-name -> bool dict, as
        returned by AbstractSolver.Solve()[0]). Walks the real graph
        structure (Kripke.IterFTransitions) rather than string-parsing
        variable names, so it can't be confused by a node key that happens
        to contain "_true_"/"_false_" itself; keeps Flag so the exact fired
        variable (not just its endpoints) can be reconstructed later. """
        Fired = []
        for NodeKey in Kripke.IterFTransitions(None):
            for Target, Flag in Kripke.IterFTransitions(NodeKey):
                Name = XMLUtils.CreateTransition(NodeKey, Target, Flag).attrib[XMLUtils.ATTRNAME]
                if Model.get(Name):
                    Fired.append((NodeKey, Target, Flag))
        return Fired


    def _Reachable(Fired, Source):
        Edges = {}
        for Node, Target, _Flag in Fired:
            Edges.setdefault(Node, []).append(Target)

        Seen = {Source}
        Frontier = [Source]
        while Frontier:
            Next = []
            for Node in Frontier:
                for Target in Edges.get(Node, []):
                    if Target not in Seen:
                        Seen.add(Target)
                        Next.append(Target)
            Frontier = Next
        return Seen


    def _BackwardSupport(Fired, Destination):
        """ The nodes that can reach Destination via THIS witness's own
        fired (true) transitions -- a backward walk from Destination, using
        only the concrete edges gathered by _WitnessTransitions. This is
        Destination's own "explanation" for why it looks reached in this
        specific model: exactly the closure _BlockWitness should restrict
        its clause to (AD6_PLAN.md §5.4 Stage B, B1 perf finding -- see
        testBackwardSupportRestrictsBlockingToDestinationsOwnClosure).

        Note this closure is always disjoint from Source's own
        forward-reachable set (_Reachable(Fired, Source)) whenever
        Destination was rejected as ungrounded: if some node were in both,
        chaining the two walks would make Destination forward-reachable
        from Source after all, contradicting the rejection. So this never
        includes any of Source's own (possibly mandatory) outgoing edges. """
        Reverse = {}
        for Node, Target, _Flag in Fired:
            Reverse.setdefault(Target, []).append(Node)

        Seen = {Destination}
        Frontier = [Destination]
        while Frontier:
            Next = []
            for Node in Frontier:
                for Pred in Reverse.get(Node, []):
                    if Pred not in Seen:
                        Seen.add(Pred)
                        Next.append(Pred)
            Frontier = Next
        return Seen


    def _BlockWitness(Fired, Support):
        """ A clause forbidding the combination of transitions, among those
        fired in this witness, that land inside Destination's own backward
        closure (_BackwardSupport) -- i.e., the edges actually responsible
        for its (spurious) claim of being reached, rather than every
        unrelated transition that merely happened to be true elsewhere in
        the model. Still guarantees progress (the current witness's own
        Support-closure edges are, by construction, all fired and inside
        Support, so this clause is violated by -- and thus excludes -- the
        exact witness just rejected) while being far more general: it also
        excludes every OTHER witness sharing this same floating closure
        with different, irrelevant bits set elsewhere, which is what made
        the unrestricted (whole-fired-set) version need ~117 iterations on
        a real 3-router wl_stanford slice for a single rejected query. """
        Literals = [XMLUtils.CreateTransition(Node, Target, Flag)
                    for Node, Target, Flag in Fired if Target in Support]
        for Literal in Literals:
            XMLUtils.NegateVariable(Literal)
        Disjunction = XMLUtils.disjunction()
        Disjunction.extend(Literals)
        return Disjunction


    def SolveGroundedEndToEnd(Solver, Kripke, Instance, Source, Destination, MaxIterations=10000):
        """ AD6_PLAN.md §5.4 Stage B (B1): fixes the gap pinned by
        instantiatortest.py::testCycleReachabilityIsUnsoundWithoutRealOrigin.

        InstantiateEndToEnd asserts two INDEPENDENT disjuncts (source's own
        forward edge fired; destination's own backward edge fired) rather
        than one connected path -- on any topology containing a cycle, a
        self-sustaining loop with no real INIT is a free fixed point that
        satisfies both disjuncts without either ever being grounded in the
        actual query's source. A single static formula can't fix this (see
        AD6_PLAN.md §5.4/ad6/FAVE_CHANGES.md's writeup on why negating
        _CreateCycle either breaks every real terminal node or reduces to a
        near-universal no-op) because groundedness is a property of the
        concrete witness the solver picks, not of the symbolic model.

        Fixes it CEGAR-style instead: solve, walk the concrete model's fired
        transitions from Source via the real Kripke graph
        (_WitnessTransitions/_Reachable), and accept only if Destination is
        actually reached that way. Otherwise, block Destination's own
        backward-closure of fired transitions (_BackwardSupport/
        _BlockWitness) and re-solve -- since each iteration permanently
        rules out at least the current witness (and generally a whole
        family of variants sharing the same floating closure) out of a
        finite space, this always terminates in either a grounded witness
        (True) or UNSAT (False, once every remaining model is ungrounded).
        `MaxIterations` is a pure safety backstop against a latent bug
        turning this into an infinite loop; it is not expected to bite in
        practice -- rejected witnesses are rare (only cyclic topologies
        produce them at all) and each one is blocked for good. """
        Instance = deepcopy(Instance)
        for _ in range(MaxIterations):
            Result = Solver.Solve(Instance)
            if not Result:
                return False
            Model = Result[0]
            Fired = Instantiator._WitnessTransitions(Kripke, Model)
            if Destination in Instantiator._Reachable(Fired, Source):
                return True
            Support = Instantiator._BackwardSupport(Fired, Destination)
            Instance[0].append(Instantiator._BlockWitness(Fired, Support))
        raise RuntimeError(
            "SolveGroundedEndToEnd did not converge within %d iterations "
            "(%s -> %s)" % (MaxIterations, Source, Destination))


    def SolveAcyclicEndToEnd(Solver, Kripke, Instance, Source, Destination, Cache=None, Stats=None):
        """ AD6_PLAN.md §5.4 Stage B (B1), Option 2's lazy/hybrid
        refinement: baking _CreateAcyclicConstraints into the SHARED base
        model (so every query pays for it, whether it needs it or not)
        measured at ~40-45s of extra build+solve time PER QUERY on a real
        3-router wl_stanford slice, even for pairs that were already
        genuinely, plainly reachable -- a cost that would apply to EVERY
        query of EVERY benchmark sharing this bridge (wl_ifi/wl_up/wl_tum
        included), not just the handful of pairs the floating-cycle bug
        actually affects.

        Most queries don't need the rank machinery at all: a plain solve's
        witness is either already grounded (Destination genuinely
        reachable from Source), or the raw query is outright UNSAT for an
        ordinary reason (e.g. a real ACL/admission DROP -- Destination's
        OWN required incoming edge, or Source's own required outgoing edge,
        is unsatisfiable on its own merits, with no floating cycle involved
        at all). The rank constraints are only actually NEEDED for the
        narrow case this whole investigation is about: a plain solve is SAT
        but the witness is ungrounded (see
        testCycleReachabilityIsUnsoundWithoutRealOrigin).

        So: try a plain solve first, accept immediately if grounded, return
        False immediately if outright UNSAT. Only on a REJECTED witness,
        lazily build (once, via `Cache` -- a plain dict the caller creates
        ONCE per Kripke/benchmark run and passes into every query) the
        SCC-scoped rank constraints, append them to a fresh copy of this
        instance, and fall back to SolveGroundedEndToEnd (now just a
        defensive backstop -- with the rank constraints present, a floating
        cycle is outright UNSAT, so this should resolve within its very
        first iteration, not the combinatorial blowup of relying on CEGAR
        alone). `Cache` is optional (None rebuilds every time, e.g. for a
        single one-off query) but should always be supplied by a caller
        driving many queries against the same Kripke (see
        testSolveAcyclicEndToEndEscalatesOnlyOnceAndCachesAcrossQueries).

        `Stats` (optional, None by default -- existing callers are
        unaffected) is filled in with {'Escalated': bool}: whether THIS
        specific call needed to escalate. A caller can't tell that from
        `Cache` alone once it's warm from an earlier query -- membership
        stays true for every later, even fast-path, query too (see
        testSolveAcyclicEndToEndReportsEscalationPerQueryViaStats) -- so a
        caller logging per-query progress (fave_bridge.py's query loop)
        needs this direct report instead. """
        Result = Solver.Solve(Instance)
        if not Result:
            if Stats is not None:
                Stats['Escalated'] = False
            return False

        Model = Result[0]
        Fired = Instantiator._WitnessTransitions(Kripke, Model)
        if Destination in Instantiator._Reachable(Fired, Source):
            if Stats is not None:
                Stats['Escalated'] = False
            return True

        if Stats is not None:
            Stats['Escalated'] = True

        if Cache is not None and 'AcyclicConstraints' in Cache:
            AcyclicConstraints = Cache['AcyclicConstraints']
        else:
            AcyclicConstraints = Instantiator._CreateAcyclicConstraints(Kripke)
            if Cache is not None:
                Cache['AcyclicConstraints'] = AcyclicConstraints

        Amended = deepcopy(Instance)
        Amended[0].extend(deepcopy(AcyclicConstraints))
        return Instantiator.SolveGroundedEndToEnd(Solver, Kripke, Amended, Source, Destination)


    def _CreateCycle(Kripke):
        Implications = []
        FTransitions = Kripke.IterFTransitions(None)
        for Transition in FTransitions:

            Targets = Kripke.IterFTransitions(Transition)
            for Target,Flag in Targets:
                Implication = XMLUtils.disjunction()

                try:
                    NextTargets = list(Kripke.IterFTransitions(Target))
                    if len(NextTargets) > 1:
                        Disjunction = []
                        for NextTarget,NextFlag in NextTargets:
                            Disjunction.append(XMLUtils.CreateTransition(Target,NextTarget,NextFlag))
                    elif len(NextTargets) == 1:
                        NextTarget,NextFlag = NextTargets[0]
                        Disjunction = [XMLUtils.CreateTransition(Target,NextTarget,NextFlag)]
                    else:
                        Disjunction = []
                except KeyError:
                    Disjunction = []

                Implicant = XMLUtils.CreateTransition(Transition,Target,Flag)
                Implicant.attrib[XMLUtils.ATTRNEGATED] = 'true'
                if Disjunction != []:
                    Implication.append(Implicant)
                    Implication.extend(Disjunction)
                    Implications.append(Implication)
                else:
                    Implications.append(Implicant)

        return Implications


    def InstantiateCycle(Kripke,Encoding):
        Instance = deepcopy(Encoding)
        Cycle = Instantiator._CreateCycle(Kripke)
        Conjunction = Instance[0]
        Conjunction.extend(Cycle)


        Disjunction = XMLUtils.disjunction()
        Inits = Kripke.IterInits(None)
        for Init in Inits:
            FTransitions = Kripke.IterFTransitions(Init)
            for Target,Flag in FTransitions:
                Disjunction.append(XMLUtils.CreateTransition(Init,Target,Flag))

        if len(Disjunction) == 1:
            tmp = Disjunction[0]
            Disjunction.remove(tmp)
            Disjunction = tmp

        Conjunction.append(Disjunction)

        return Instance


    def _GetVariables(Formula,Variables={}):
        if Formula.tag == XMLUtils.VARIABLE:
            Variables[Formula.attrib[XMLUtils.ATTRNAME]] = True
        else:
            for SubFormula in Formula:
                Instantiator._GetVariables(SubFormula,Variables)

        return Variables


    def InstantiateShadow(Kripke,Encoding,Instances={},Node=""):
        if Node != "":
            Instance = Instantiator.InstantiateReach(Kripke,Encoding,Node)
            Instance[0].append(XMLUtils.variable(Node+'_'+Instantiator.GAMMA))
            return Instance

        if not any(map(lambda x: x.endswith('_'+Instantiator._REACH),Instances)):
            ShadowInstances = Instantiator.InstantiateReach(Kripke,Encoding)
        else:
            ShadowInstances = { Instance[:len(Instance)-6] : deepcopy(Instances[Instance]) for Instance in Instances if Instance.endswith('_'+Instantiator._REACH)}

        for Instance in ShadowInstances:
            Formula = ShadowInstances[Instance]
            Formula[0].append(XMLUtils.variable(Instance+'_'+Instantiator.GAMMA))

        return ShadowInstances


    def InstantiateCross(Kripke,Encoding):
        Instance = deepcopy(Encoding)
        Conjunction = []

        Accepts = filter(lambda x: 'accept' in Kripke.GetNode(x).Props, Kripke.IterNodes())
        Drops = filter(lambda x: 'drop' in Kripke.GetNode(x).Props, Kripke.IterNodes())

        Disjunction = XMLUtils.disjunction()
        for Accept in Accepts:
            try:
                BTransitions = Kripke.IterBTransitions(Accept)
                for Transition,Flag in BTransitions:
                    Disjunction.append(XMLUtils.CreateTransition(Transition,Accept,Flag))
            except KeyError:
                continue

        if len(Disjunction) > 1:
            Conjunction.append(Disjunction)
        elif len(Disjunction) == 1:
            tmp = Disjunction[0]
            Disjunction.remove(tmp)
            Conjunction.append(tmp)

        Disjunction = XMLUtils.disjunction()
        for Drop in Drops:
            try:
                BTransitions = Kripke.IterBTransitions(Drop)
                for Transition,Flag in BTransitions:
                    Disjunction.append(XMLUtils.CreateTransition(Transition,Drop,Flag))
            except KeyError:
                continue

        if len(Disjunction) > 1:
            Conjunction.append(Disjunction)
        elif len(Disjunction) == 1:
            tmp = Disjunction[0]
            Disjunction.remove(tmp)
            Conjunction.append(tmp)

        Instance[0].extend(Conjunction)

        return Instance


    def _ConvertNodesToImplications(Kripke):
        Implications = []

        FTransitions = Kripke.IterFTransitions(None)
        for NodeKey in FTransitions:
            Node = Kripke.GetNode(NodeKey)
            Targets = Kripke.IterFTransitions(NodeKey)
            NodeImplications = []
            for Target,Flag in Targets:
                Implication = XMLUtils.implication()
                Implicant = XMLUtils.CreateTransition(NodeKey,Target,Flag)
                Conclusio = XMLUtils.conjunction()
                Equality = XMLUtils.equality()
                Equality.append(XMLUtils.constant(Flag))
                Equality.append(XMLUtils.variable(NodeKey+'_'+Instantiator.GAMMA))

                Predecessors = Kripke.IterBTransitions(NodeKey)
                Transitions = []
                for Predecessor,Flag in Predecessors:
                    Transition = XMLUtils.CreateTransition(Predecessor,NodeKey,Flag)
                    Transitions.append(Transition)

                if len(Transitions) > 1:
                    Disjunction = XMLUtils.disjunction()
                    Disjunction.extend(Transitions)
                elif len(Transitions) == 1:
                    Disjunction = Transitions[0]
                else:
                    if XMLUtils.INIT in Node.Props:
                        Disjunction = XMLUtils.constant()
                    else:
                        Disjunction = XMLUtils.constant(False)

                Conclusio.extend([Equality,Disjunction])
                Implication.extend([Implicant,Conclusio])

                Dummy = XMLUtils.formula()
                Conjunction = XMLUtils.conjunction()
                Dummy.append(Conjunction)
                Conjunction.append(Implication)

                SATUtils.ConvertToCNF(Dummy)
                Conjunction = Dummy[0]
                Dummy.remove(Conjunction)

                if Conjunction.tag == XMLUtils.CONJUNCTION:
                    NodeImplications.extend(list(Conjunction))
                else:
                    NodeImplications.append(Conjunction)

            Implications.extend(NodeImplications)

        return Implications


    def _CreateMutationConstraints(Kripke, MutableFields):
        """ AD6_PLAN.md §5.4 Stage A: SSA-style mutation support for fields
        a rule's action can rewrite (e.g. VLAN) -- ad6's variables are
        otherwise single global propositional constants, which can express
        a field being matched, but not a field being ASSIGNED a different
        value at different points along one path (a real rewrite chain,
        `b=* -> 1 -> 0 -> *`, needs as many distinct values as rewrite
        points; a global variable only ever has one).

        `MutableFields`: {field_name: bit_width}, e.g. {"vlan": 12}. For
        EVERY edge in the Kripke graph and EVERY declared mutable field,
        asserts exactly one of:
          - a REWRITE axiom, if the edge is the TRUE/jump transition of a
            node whose own rule declares `Node.Rewrites[field]` (see
            GenUtils.action/kripke.py._HandleRule): the target's per-node
            copy of the field (XMLUtils.FieldBitName(field, target, i))
            is forced to the rewritten value's bits, gated on this edge's
            transition literal actually having fired.
          - a FRAME axiom otherwise (including every FALSE/fallthrough
            edge, which by construction never rewrites anything): the
            target's copy equals the SOURCE's own per-node copy, gated the
            same way -- "the field survives unchanged across an edge that
            doesn't touch it".
        A node with several predecessors (a join) gets one such
        implication PER incoming edge, independently gated on that edge's
        own transition literal -- exactly the same mechanism
        _ConvertNodesToImplications already uses for reachability itself,
        so two predecessors asserting different histories simultaneously
        is a real, correctly-detected contradiction (UNSAT for that specific
        combination) rather than something requiring a new exclusivity
        constraint; the model is always free to leave the transition that
        would conflict false, exactly as it already is for reachability.
        A node with NO predecessor that ever pins the field (e.g. a
        generator/entry node) leaves its per-node copy as a genuinely free
        variable -- "don't care", the same semantics every other unmatched
        field already has.

        Each edge's constraint is built and CNF-converted in its own small
        "Dummy" formula, mirroring _ConvertNodesToImplications's own
        per-edge discipline exactly (AD6_PLAN.md §5.4/§8.5's naive-CNF
        guardrail: this must stay as shallow as the existing per-edge
        implications, not introduce new alternation depth of its own). """
        Constraints = []

        FTransitions = Kripke.IterFTransitions(None)
        for NodeKey in FTransitions:
            Node = Kripke.GetNode(NodeKey)
            Targets = Kripke.IterFTransitions(NodeKey)
            for Target, Flag in Targets:
                for Field, Width in MutableFields.items():
                    # A fresh transition-literal element per field: lxml
                    # elements have exactly one parent, so reusing the same
                    # element across multiple <implication>s (one per
                    # field) would silently MOVE it out of the earlier
                    # one instead of copying it.
                    TransitionLit = XMLUtils.CreateTransition(NodeKey, Target, Flag)
                    RewriteValue = Node.Rewrites.get(Field) if Flag else None

                    Conjunction = XMLUtils.conjunction()
                    if RewriteValue is not None:
                        BitVector = XMLUtils._CanonizeBitvector(RewriteValue, Width).split(' ')
                    else:
                        BitVector = None

                    for Index in range(Width):
                        TargetBit = XMLUtils.variable(XMLUtils.FieldBitName(Field, Target, Index))
                        if BitVector is not None:
                            SourceBit = XMLUtils.constant(BitVector[Index] == '1')
                        else:
                            SourceBit = XMLUtils.variable(XMLUtils.FieldBitName(Field, NodeKey, Index))
                        Equality = XMLUtils.equality()
                        Equality.append(TargetBit)
                        Equality.append(SourceBit)
                        Conjunction.append(Equality)

                    Implication = XMLUtils.implication()
                    Implication.extend([TransitionLit, Conjunction])

                    Dummy = XMLUtils.formula()
                    TopConjunction = XMLUtils.conjunction()
                    Dummy.append(TopConjunction)
                    TopConjunction.append(Implication)

                    SATUtils.ConvertToCNF(Dummy)
                    TopConjunction = Dummy[0]
                    Dummy.remove(TopConjunction)

                    if TopConjunction.tag == XMLUtils.CONJUNCTION:
                        Constraints.extend(list(TopConjunction))
                    else:
                        Constraints.append(TopConjunction)

        return Constraints


    def _PostOrder(Nodes, Neighbors):
        """ Iterative post-order DFS (no recursion-depth risk on graphs
        with thousands of nodes) -- the first pass of Kosaraju's SCC
        algorithm. `Neighbors(node)` returns an iterable of successors. """
        Visited = set()
        Order = []
        for Start in Nodes:
            if Start in Visited:
                continue
            Visited.add(Start)
            Stack = [(Start, iter(Neighbors(Start)))]
            while Stack:
                Node, It = Stack[-1]
                Advanced = False
                for Next in It:
                    if Next not in Visited:
                        Visited.add(Next)
                        Stack.append((Next, iter(Neighbors(Next))))
                        Advanced = True
                        break
                if not Advanced:
                    Stack.pop()
                    Order.append(Node)
        return Order


    def _CollectReachable(Start, Neighbors, Visited):
        """ Iterative DFS collecting every node reachable from `Start` that
        isn't already in `Visited` (which this also populates) -- the
        second pass of Kosaraju's SCC algorithm, run over the REVERSE
        graph so each call yields exactly one SCC. """
        Visited.add(Start)
        Component = [Start]
        Stack = [Start]
        while Stack:
            Node = Stack.pop()
            for Next in Neighbors(Node):
                if Next not in Visited:
                    Visited.add(Next)
                    Component.append(Next)
                    Stack.append(Next)
        return Component


    def _ComputeSCCs(Kripke):
        """ AD6_PLAN.md §5.4 Stage B (B1), Option 2 scoping: only edges with
        BOTH endpoints in the SAME non-trivial strongly-connected component
        (SCC) can ever be part of a real cycle -- a long acyclic chain
        (e.g. a FIB table's rules falling through one by one) is never part
        of one, by definition of what an SCC is. Restricting
        _CreateAcyclicConstraints's (expensive) per-edge comparator to just
        those edges is therefore lossless for soundness, while potentially
        cutting the encoding by orders of magnitude on real Stanford-shaped
        data (see testComputeSCCsFindsOnlyGenuineCyclesNotLongAcyclicChains
        and AD6_PLAN.md §5.4 for the profiling that found the UNscoped
        version too expensive to build/solve at real scale).

        Kosaraju's algorithm (both true/false Kripke transitions count as
        graph edges here -- which one fired is irrelevant to connectivity):
        a post-order DFS on the forward graph, then a DFS on the REVERSE
        graph taken in reverse post-order; each reverse-graph DFS tree is
        exactly one SCC. Both passes are iterative (explicit stacks, not
        Python recursion) since real Stanford-scale graphs have thousands
        of nodes.

        Returns (SccOf, NonTrivial): SccOf maps every node key to an
        integer SCC id; NonTrivial is the set of SCC ids that are either
        larger than one node, or a single node with a self-loop (a
        degenerate but genuine 1-node cycle) -- exactly the SCCs whose
        internal edges can actually participate in a cycle. """
        Nodes = list(Kripke.IterNodes())

        Forward = {}
        Reverse = {}
        for NodeKey in Nodes:
            try:
                Targets = [Target for Target, _Flag in Kripke.IterFTransitions(NodeKey)]
            except KeyError:
                Targets = []
            Forward[NodeKey] = Targets
            for Target in Targets:
                Reverse.setdefault(Target, []).append(NodeKey)

        Order = Instantiator._PostOrder(Nodes, lambda N: Forward.get(N, []))

        SccOf = {}
        NonTrivial = set()
        Visited = set()
        NextSccId = 0
        for NodeKey in reversed(Order):
            if NodeKey in Visited:
                continue
            Component = Instantiator._CollectReachable(
                NodeKey, lambda N: Reverse.get(N, []), Visited)

            SccId = NextSccId
            NextSccId += 1
            for Member in Component:
                SccOf[Member] = SccId

            IsSelfLoop = len(Component) == 1 and Component[0] in Forward.get(Component[0], [])
            if len(Component) > 1 or IsSelfLoop:
                NonTrivial.add(SccId)

        return SccOf, NonTrivial


    def _CreateAcyclicConstraints(Kripke, ProgressCallback=None):
        """ AD6_PLAN.md §5.4 Stage B (B1), Option 2: a STATIC, always-safe
        fix for the same root cause SolveGroundedEndToEnd patches
        reactively -- see that function's docstring and
        testAcyclicRankConstraintRejectsFloatingCycleStatically for the
        full story of why CEGAR (both the naive exact-witness-blocking
        version and its "shrink to Destination's own closure" refinement)
        turned out combinatorially intractable on real wl_stanford data.

        Gives every Kripke node a brand-new "rank" field -- a bounded
        unsigned binary number with NO other role anywhere else in the
        model (XMLUtils.FieldBitName('rank', Node, i), the same per-node
        bit-vector shape AD6_PLAN.md §5.4 Stage A's mutation encoding
        already uses) -- and asserts, for EVERY Kripke edge (Node,Target),
        that firing it requires Rank(Target) > Rank(Node). `Width` bits are
        enough to represent every node exactly once (the longest possible
        SIMPLE/acyclic path visits each node at most once), so this can
        never reject a genuine acyclic witness, no matter how long.

        Unlike negating _CreateCycle (see AD6_PLAN.md §5.4's writeup), this
        has no structural escape hatch: _CreateCycle's own formula could
        always be satisfied for free by any edge into a dead end (every
        real ACCEPT/DROP/probe node), giving zero discriminating power.
        "Greater than" has no analogous free pass -- a cycle of
        simultaneously-true edges (A_true_B, B_true_C, C_true_A) forces
        Rank(B)>Rank(A), Rank(C)>Rank(B), Rank(A)>Rank(C), which chain into
        Rank(A)>Rank(A): an outright numeric contradiction, regardless of
        what value any node's rank takes. Since ad6's existing per-edge
        implications already force firing ONE cycle edge to also force the
        REST of the same cycle's edges (the exact mechanism that makes a
        floating cycle satisfiable at all -- see
        testCycleReachabilityIsUnsoundWithoutRealOrigin), this makes the
        WHOLE cycle simultaneously-true combination UNSAT outright, in the
        base model itself -- no query-side change and no CEGAR needed.

        Encoded via an explicit auxiliary-variable chain (standard
        bitwise-comparator CNF technique: eq_i tracks whether the two
        numbers' bits 0..i are equal so far, gt_i whether bit i is the
        first place Target's bit is 1 where Node's is 0) rather than one
        big nested formula, so SATUtils.ConvertToCNF's distribution stays
        LINEAR in Width per edge -- a naive OR-of-ANDs comparator would
        risk the exact exponential-blowup AD6_PLAN.md §5.4/§8.5's
        naive-CNF-conversion guardrail warns about. Built and CNF-converted
        per edge (its own small Dummy formula), same discipline as
        _CreateMutationConstraints, so this stays additive to the global
        encoding's own alternation depth. Aux variable names are scoped by
        a per-edge index so two different edges' comparators can never
        collide.

        IMPORTANT: every eq_i/gt_i definition here is a ONE-DIRECTIONAL
        implication (aux_var -> real_condition), built with
        XMLUtils.implication()+XMLUtils.conjunction() of hand-built flat
        disjunctions -- deliberately NEVER XMLUtils.equality() for a
        non-constant "aux_var <-> composite_formula" biconditional.
        Empirically confirmed broken: SATUtils._ResolveConstants's general
        (neither-operand-constant) EQUALITY branch produces a correct
        result only when that equality is the OUTERMOST formula; nested
        inside another equality (as "aux_var <-> (bit_a <-> bit_b)" would
        be), the inner equality's resolution replaces itself in-place
        *while the outer equality's own child-iteration is still in
        progress*, so the newly-built substructure never gets its own
        resolution pass -- the outer equality's general-case branch then
        deepcopies that still-composite (non-literal) operand straight
        into a new top-level disjunction, leaving a disjunction with a
        raw nested conjunction inside it (invalid CNF, and exactly what
        AbstractSolver._ConvertToDIMACS rejects). One-directional
        implications don't need the reverse direction for soundness here
        either: eq_i/gt_i are brand-new variables with no other role, so
        the solver already has complete freedom to set one true whenever
        it ALSO picks bit values that satisfy its condition (exactly what
        happens automatically while it constructs a genuinely increasing
        rank assignment for a real witness) -- what must be prevented is
        only the reverse (gt_i true WITHOUT the real bits agreeing), which
        "aux_var -> real_condition" already rules out on its own.

        SCC-scoped (AD6_PLAN.md §5.4 Stage B, B1 Option 2 perf finding):
        only edges with both endpoints in the SAME non-trivial
        strongly-connected component (_ComputeSCCs) get this treatment --
        an edge that can never be part of any cycle (e.g. a FIB table's
        rules falling through one by one) needs no rank constraint at all,
        by definition of what an SCC is. This is lossless for soundness
        while, on real Stanford-shaped data, cutting both which edges need
        the comparator AND `Width` itself (sized off the largest cyclic
        SCC, not the whole graph) by orders of magnitude -- see
        testAcyclicRankConstraintScopesToNonTrivialSCCsOnly. """
        SccOf, NonTrivial = Instantiator._ComputeSCCs(Kripke)
        MaxSccSize = 0
        if NonTrivial:
            Sizes = {}
            for Member, SccId in SccOf.items():
                if SccId in NonTrivial:
                    Sizes[SccId] = Sizes.get(SccId, 0) + 1
            MaxSccSize = max(Sizes.values())
        Width = max(1, (MaxSccSize + 1).bit_length())
        Constraints = []

        EdgeIndex = 0
        FTransitions = Kripke.IterFTransitions(None)
        for NodeKey in FTransitions:
            for Target, Flag in Kripke.IterFTransitions(NodeKey):
                if SccOf.get(NodeKey) != SccOf.get(Target) or SccOf.get(NodeKey) not in NonTrivial:
                    continue

                EdgeIndex += 1
                TransitionLit = XMLUtils.CreateTransition(NodeKey, Target, Flag)

                def TargetBit(i, Negated=False):
                    return XMLUtils.variable(XMLUtils.FieldBitName('rank', Target, i), value=not Negated)

                def NodeBit(i, Negated=False):
                    return XMLUtils.variable(XMLUtils.FieldBitName('rank', NodeKey, i), value=not Negated)

                def AuxEq(i):
                    return XMLUtils.variable('rankeq#%d_%d' % (EdgeIndex, i))

                def AuxGt(i):
                    return XMLUtils.variable('rankgt#%d_%d' % (EdgeIndex, i))

                def BitsEqual(i):
                    """ Two flat disjunctions standing for "Target's bit i
                    == Node's bit i" -- hand-built, deliberately never
                    XMLUtils.equality() (see this function's own docstring
                    for why that's unsafe here), so this can be safely
                    embedded as extra conjuncts inside an implication's
                    conclusion. """
                    Left = XMLUtils.disjunction()
                    Left.append(TargetBit(i, Negated=True))
                    Left.append(NodeBit(i))
                    Right = XMLUtils.disjunction()
                    Right.append(TargetBit(i))
                    Right.append(NodeBit(i, Negated=True))
                    return [Left, Right]

                # One-directional implications only (never
                # XMLUtils.equality() with a non-constant operand -- see
                # this function's docstring note on why that's unsafe here).
                # Soundness doesn't need the reverse direction: eq_i/gt_i
                # are brand-new variables with no other role, so the solver
                # already has complete freedom to set them true whenever it
                # ALSO chooses bit values that satisfy their defining
                # condition -- exactly what happens automatically when it
                # constructs a genuinely increasing rank assignment for a
                # real witness. What must never happen is the REVERSE: a
                # gt_i true WITHOUT the real bit condition holding, which
                # is exactly what "eq_i/gt_i -> (real bit condition)" rules
                # out.
                Defs = XMLUtils.conjunction()

                # eq_0 -> (Target's bit 0 == Node's bit 0)
                Eq0 = XMLUtils.implication()
                Eq0Conj = XMLUtils.conjunction()
                Eq0Conj.extend(BitsEqual(0))
                Eq0.extend([AuxEq(0), Eq0Conj])
                Defs.append(Eq0)

                # gt_0 -> (Target's bit 0 AND NOT Node's bit 0)
                Gt0Conj = XMLUtils.conjunction()
                Gt0Conj.append(TargetBit(0))
                Gt0Conj.append(NodeBit(0, Negated=True))
                Gt0 = XMLUtils.implication()
                Gt0.extend([AuxGt(0), Gt0Conj])
                Defs.append(Gt0)

                for Index in range(1, Width):
                    # eq_i -> (eq_{i-1} AND bits equal so far)
                    EqConj = XMLUtils.conjunction()
                    EqConj.append(AuxEq(Index - 1))
                    EqConj.extend(BitsEqual(Index))
                    EqDef = XMLUtils.implication()
                    EqDef.extend([AuxEq(Index), EqConj])
                    Defs.append(EqDef)

                    # gt_i -> (eq_{i-1} AND Target's bit i AND NOT Node's bit i)
                    GtConj = XMLUtils.conjunction()
                    GtConj.append(AuxEq(Index - 1))
                    GtConj.append(TargetBit(Index))
                    GtConj.append(NodeBit(Index, Negated=True))
                    GtDef = XMLUtils.implication()
                    GtDef.extend([AuxGt(Index), GtConj])
                    Defs.append(GtDef)

                GtAny = XMLUtils.disjunction()
                for Index in range(Width):
                    GtAny.append(AuxGt(Index))

                Gated = XMLUtils.implication()
                Gated.extend([TransitionLit, GtAny])
                Defs.append(Gated)

                Dummy = XMLUtils.formula()
                Dummy.append(Defs)

                SATUtils.ConvertToCNF(Dummy)
                Defs = Dummy[0]
                Dummy.remove(Defs)

                if Defs.tag == XMLUtils.CONJUNCTION:
                    Constraints.extend(list(Defs))
                else:
                    Constraints.append(Defs)

                if ProgressCallback is not None:
                    ProgressCallback(EdgeIndex)

        return Constraints


    def _CreateGlobalConstraints(Kripke,Encoding):
        Constraints = []
        Variables = Instantiator._GetVariables(Encoding)

        Constraints.extend(Instantiator._CreateBitConstraints(Variables))
        Constraints.extend(Instantiator._CreateInitConstraints(Kripke))

        return Constraints


    def _xor(Variables):
        Implications = []

        Variables = set(Variables)

        for Variable in Variables:
            Others = Variables - {Variable}

            for Other in Others:
                # a xor b = a implies not b = not a or not b
                Implication = XMLUtils.disjunction()

                var = XMLUtils.variable(Variable.attrib['name'], value=False)

                other = XMLUtils.variable(Other.attrib['name'], value=False)

                Implication.extend([var,other])
                Implications.append(Implication)

        return Implications


    def _CreateInitConstraints(Kripke):
        Constraints = []
        InitTransitions = []
        for Init in Kripke.IterInits():
            InitTransitions.extend(map(lambda x: (Init,) + x, Kripke.IterFTransitions(Init)))

        # At most one of the N init transitions may fire simultaneously
        # (mutual exclusion; a query supplies "at least one" itself by
        # asserting a specific transition -- see
        # ad6/test/core/initconstraintstest.py). _xor(Transitions) builds
        # this directly as O(N^2) pairwise "not both" clauses, exactly like
        # the Length in [2,3] case below always did.
        #
        # Length>3 used to instead build a linear chain of auxiliary
        # "xor_i" variables (presumably to trade the O(N^2) clause count for
        # O(N) at the cost of the extra variables) via `for i in
        # range(2, Length-3): ...`. That construction was broken beyond
        # repair: for every N>=4 it left almost every NON-ADJACENT pair of
        # transitions completely unconstrained -- only (T[0],T[1]) was ever
        # correctly excluded -- not just "the last few" as first suspected
        # from the N=17 case that surfaced this (AD6_PLAN.md §4.4/
        # ad6/FAVE_CHANGES.md §6,§8). The straightforward pairwise encoding
        # is what's proven correct (property-tested up to N=40, and spot-
        # checked at N=137 -- FaVe's wl_up scale, ~18.6k clauses, ~2s to
        # build+CNF-convert); reach for something cleverer only if profiling
        # ever shows this is a real bottleneck.
        Length = len(InitTransitions)
        if Length > 1:
            Transitions = [XMLUtils.CreateTransition(*InitTransitions[i]) for i in range(Length)]
            Constraints.extend(Instantiator._xor(Transitions))

        elif Length == 1:
            Constraints.append(XMLUtils.CreateTransition(*InitTransitions[0]))

        else:
            Constraints.append(XMLUtils.unsat())

        return Constraints


    def _HandleGammas(Kripke):
        Gammas = []
        Nodes = Kripke.IterNodes()
        for NodeKey in Nodes:
            Equality = XMLUtils.equality()
            Equality.append(XMLUtils.variable(NodeKey+'_'+Instantiator.GAMMA))
            Equality.append(deepcopy(Kripke.GetNode(NodeKey).Gamma))

            Dummy = XMLUtils.formula()
            Conjunction = XMLUtils.conjunction()
            Dummy.append(Conjunction)
            Conjunction.append(Equality)

            SATUtils.ConvertToCNF(Dummy)
            Conjunction = Dummy[0]
            Dummy.remove(Conjunction)

            if Conjunction.tag == XMLUtils.CONJUNCTION:
                Gammas.extend(list(Conjunction))
            else:
                Gammas.append(Conjunction)

        return Gammas


    def _CreateBitConstraints(Variables):
        Handled = {}
        Constraints = []
        for Variable in Variables:
            Varbody = Variable.rstrip('01')
            if '=' in Variable and not Varbody in Handled:
                Disjunction = XMLUtils.disjunction()
                v0 = XMLUtils.variable(Varbody + '0', False)
                v1 = XMLUtils.variable(Varbody + '1', False)
                Disjunction.extend([v0,v1])
                Constraints.append(Disjunction)
                Handled[Varbody] = True
        return Constraints

    def _InstantiateBase(Kripke):
        Encoding = XMLUtils.formula()
        Conjunction = XMLUtils.conjunction()
        Conjunction.extend(Instantiator._ConvertNodesToImplications(Kripke))
        Conjunction.extend(Instantiator._HandleGammas(Kripke))

        Encoding.append(Conjunction)

        return Encoding


    def _HandlePorts(Variable, Handled):
        Name = Variable.attrib[XMLUtils.ATTRNAME]
        if Name in Handled or not Name.startswith(('dst_port_','src_port_')):
            return

        Equality = XMLUtils.equality()
        var = deepcopy(Variable)
        var.attrib[XMLUtils.ATTRNEGATED] = 'false'
        Equality.append(var)

        Direction,tmp,Port = Name.split('_')
        Equality.append(XMLUtils.ConvertPortToVariables(Port,Direction))

        Handled[Name] = Equality


    def _HandleVlans(Variable, Handled):
        Name = Variable.attrib[XMLUtils.ATTRNAME]
        if Name in Handled or not Name.startswith(('ingress_vlan_', 'egress_vlan_')):
            return

        Equality = XMLUtils.equality()
        var = deepcopy(Variable)
        var.attrib[XMLUtils.ATTRNEGATED] = 'false'
        Equality.append(var)

        Direction,tmp,Vlan = Name.split('_')
        Equality.append(XMLUtils.ConvertVLANToVariables(Vlan,Direction))

        Handled[Name] = Equality


    def _HandleFieldMatches(Variable, Handled, MutableFields):
        """ AD6_PLAN.md §5.4 Stage A2: resolves a GenUtils.fieldmatch()
        alias (XMLUtils.FieldMatchAliasName, built by kripke.py's
        FieldMatchFilter branch) into an equality against the SAME
        per-node SSA copy _CreateMutationConstraints already threads
        through the model (XMLUtils.ConvertFieldToVariables) -- the match-
        side counterpart of _HandleVlans/_HandleOthers's own deferred-
        alias-expansion pattern, except node-scoped instead of global (see
        FieldMatchAliasName's docstring for why). `MutableFields` must be
        the SAME dict passed to InstantiateBase (so the bit-width used to
        resolve a match agrees with the one used to build the rewrite/frame
        axioms) -- a fieldmatch on a field InstantiateBase was never told
        is mutable has no known width to resolve against, so this raises
        rather than silently leaving the alias an unconstrained free
        variable (which would make the admission check vacuously
        satisfiable either way -- exactly the class of silent-blowup bug
        this whole integration has repeatedly had to hunt down). """
        Name = Variable.attrib[XMLUtils.ATTRNAME]
        if Name in Handled or not Name.startswith(XMLUtils.FIELDMATCHPREFIX):
            return

        Field, Node, Value = XMLUtils.ParseFieldMatchAliasName(Name)
        if not MutableFields or Field not in MutableFields:
            raise ValueError(
                "fieldmatch on field %r at node %r requires %r to be "
                "declared in InstantiateBase's MutableFields (e.g. "
                "{%r: 12}) -- got %r" % (Field, Node, Field, Field, MutableFields))
        Width = MutableFields[Field]

        Equality = XMLUtils.equality()
        var = deepcopy(Variable)
        var.attrib[XMLUtils.ATTRNEGATED] = 'false'
        Equality.append(var)
        Equality.append(XMLUtils.ConvertFieldToVariables(Field, Node, int(Value), Width))

        Handled[Name] = Equality


    def _HandleOthers(Variable, Handled):
        Name = Variable.attrib[XMLUtils.ATTRNAME]
        if Name in Handled or not any(Name.startswith(x) for x in XMLUtils.OTHERS):
            return

        Equality = XMLUtils.equality()
        var = deepcopy(Variable)
        var.attrib[XMLUtils.ATTRNEGATED] = 'false'
        Equality.append(var)

        Prefix,Postfix = Name.split('_')
        Functions = {
            XMLUtils.PROTO : XMLUtils.ConvertProtoToVariables,
            XMLUtils.ICMP6TYPE : XMLUtils.ConvertICMP6TypeToVariables,
            XMLUtils.ICMP6LIMIT : XMLUtils.ConvertICMP6LimitToVariables,
            XMLUtils.STATE : XMLUtils.ConvertStateToVariables,
            XMLUtils.RTTYPE : XMLUtils.ConvertRTTypeToVariables,
            XMLUtils.RTSEGSLEFT : XMLUtils.ConvertRTSegsLeftToVariables,
            XMLUtils.TCPFLAGS : XMLUtils.ConvertTCPFlagsToVariables
        }

        try:
            Equality.append(Functions[Prefix](Postfix))
        except KeyError:
            Equality.append(deepcopy(Variable))

        Handled[Name] = Equality


    def _HandlePrefixes(Variable, Handled):
        Name = Variable.attrib['name']
        if Name in Handled or not Name.startswith(('dst_ip','src_ip')):
            return

        Equality = XMLUtils.equality()
        var = deepcopy(Variable)
        var.attrib['negated'] = 'false'
        Equality.append(var)

        Direction,IPType,CIDR = Name.split('_')
        Equality.append(XMLUtils.ConvertCIDRToVariables(CIDR,Direction))

        Handled[Name] = Equality


    def _ShortenPrefixes(Handled,Keys):
        Splits = []
        Mapping = {}

        Concat = lambda x,y: x+'_'+y
        Stringify = lambda collection: reduce(Concat,map(str,collection))
        Canonize6 = lambda x: '{:016b}'.format(int(x,16))
        Canonize4 = lambda x: '{:08b}'.format(int(x,10))

        # bring addresses into canonical form and add them to mapping
        for Key in Keys:
            if '/' in Key:
                Addr,CIDR = Key.split('_')[-1].split('/')
            else:
                Addr = Key.split('_')[-1]
                CIDR = 32

            if Key[6] == '6':
                SplitAddr = Addr.split(':')
                CanonAddr = ''.join(map(Canonize6,SplitAddr))
            else:
                SplitAddr = Addr.split('.')
                CanonAddr = ''.join(map(Canonize4,SplitAddr))

            Split = (CanonAddr,int(CIDR))

            Splits.append(Split)
            Mapping[Stringify(Split)] = Key

        # sort addresses according to their significance
        Splits.sort(key = lambda x: x[0][:x[1]],reverse=True)

        # retrieve last element (least significant)
        if Splits != []:
            LastSplit = Splits.pop()
            LastAddr,lastCIDR = LastSplit

        while Splits != []:
            StLastSplit = Splits.pop()
            StLastAddr,StLastCIDR = StLastSplit

            # if less significant Prefix is included in more significant Prefix
            if StLastAddr[:StLastCIDR].startswith(LastAddr[:lastCIDR]):
                LastKey = Mapping[Stringify(LastSplit)]
                StLastKey = Mapping[Stringify(StLastSplit)]

                Equality = Handled[StLastKey]
                Conjunction = Equality[1]

                # remove Prefix of more significant address
                for Variable in Conjunction[:lastCIDR]:
                    Conjunction.remove(Variable)

                # and substitute with less significant address
                Conjunction.insert(0,XMLUtils.variable(LastKey))

            LastSplit,LastAddr,lastCIDR = StLastSplit,StLastAddr,StLastCIDR
