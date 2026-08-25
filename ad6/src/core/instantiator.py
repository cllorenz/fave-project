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


    def InstantiateBase(Config, Inits=[], default_inits=True, MutableFields=None):
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

        Variables = Encoding.iterdescendants(XMLUtils.VARIABLE)
        Handled = {}

        for Variable in Variables:
            Instantiator._HandlePrefixes(Variable, Handled)
            Instantiator._HandlePorts(Variable, Handled)
            Instantiator._HandleVlans(Variable, Handled)
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
