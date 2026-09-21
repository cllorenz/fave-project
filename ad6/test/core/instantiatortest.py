import unittest
import lxml.etree as et
from lxml import objectify
from src.core.instantiator import *
from src.solver.minisat import MiniSATAdapter
from src.solver.pycosat import PycoSATAdapter
from src.sat.satutils import SATUtils as sat
from src.xml.genutils import GenUtils
from src.core.structure import KripkeStructure, KripkeNode
from src.solver.incremental import (
    GROUNDING_FLOW, GROUNDING_RANK, SOLVERS, IncrementalSession,
    needs_fresh_per_query)

class InstantiatorTest(unittest.TestCase):
    def deannotate(config):
        for elem in config.getiterator():
            i = elem.tag.find('}')
            if i >= 0:
                elem.tag = elem.tag[i+1:]
        objectify.deannotate(config,cleanup_namespaces=True)


    def testMatchAllReachable(self):
        """ Regression for the /0-CIDR bug (AD6_PLAN.md §4.4/ad6/FAVE_CHANGES.md §6).

        r0 matches dst=0.0.0.0/0 ("match any") and jumps to its own target;
        r1, an otherwise UNRELATED rule, matches dst=10.0.0.0/8 and jumps to
        its own target. The bug isn't confined to rules that directly use the
        /0 condition: Instantiator._ShortenPrefixes treats a /0 entry as a
        (trivial) prefix of every other same-direction CIDR and splices a
        reference to it into their conjunctions too -- so once
        ConvertCIDRToVariables's empty-conjunction bug makes the /0 variable
        unsatisfiable, it silently drags down r1's condition as well, even
        though r1 never mentions 0.0.0.0/0 itself. Both targets must be
        reachable.

        Each rule/target pair gets its OWN <table>: KripkeUtils._HandleRule
        gives same-table siblings an automatic "fallthrough" (false)
        transition to whatever rule follows them in that table's rule list,
        regardless of their own action -- putting the two pairs in one table
        would add a spurious r1->specific_target edge unrelated to the bug
        under test and manifest as a second, misleading reachability path. """
        firewall = GenUtils.firewall('mafw')

        any_table = GenUtils.table('t0')
        r0 = GenUtils.rule('0', key='mafw_t_r0')
        r0.append(GenUtils.address('0.0.0.0/0', direction='dst', version='4'))
        r0.append(GenUtils.action('jump', target='mafw_t_r_any_target'))
        any_table.append(r0)
        firewall.append(any_table)

        any_target_table = GenUtils.table('t_any')
        any_target = GenUtils.rule('any', key='mafw_t_r_any_target')
        any_target.append(GenUtils.action('accept'))
        any_target_table.append(any_target)
        firewall.append(any_target_table)

        specific_table = GenUtils.table('t1')
        r1 = GenUtils.rule('1', key='mafw_t_r1')
        r1.append(GenUtils.address('10.0.0.0/8', direction='dst', version='4'))
        r1.append(GenUtils.action('jump', target='mafw_t_r_specific_target'))
        specific_table.append(r1)
        firewall.append(specific_table)

        specific_target_table = GenUtils.table('t_spec')
        specific_target = GenUtils.rule('spec', key='mafw_t_r_specific_target')
        specific_target.append(GenUtils.action('accept'))
        specific_target_table.append(specific_target)
        firewall.append(specific_target_table)

        config = GenUtils.config()
        firewalls = GenUtils.firewalls()
        firewalls.append(firewall)
        config.append(firewalls)

        kripke, encoding = Instantiator.InstantiateBase(
            config, Inits=['mafw_t_r0', 'mafw_t_r1'], default_inits=False
        )
        solver = PycoSATAdapter()

        instance = Instantiator.InstantiateReach(kripke, encoding, 'mafw_t_r_any_target')
        self.assertTrue(bool(solver.Solve(instance)), "the /0-conditioned rule itself is unreachable")

        instance = Instantiator.InstantiateReach(kripke, encoding, 'mafw_t_r_specific_target')
        self.assertTrue(bool(solver.Solve(instance)),
                        "an unrelated dst=10.0.0.0/8 rule became unreachable -- "
                        "the /0 bug is contaminating _ShortenPrefixes's sharing")


    def testStateLiteralForcingIsMutuallyExclusive(self):
        """ Regression for AD6_PLAN.md §4.2 (the wl_up/wl_ifi stateful `<->>`
        query orchestration, ad6/fave_bridge.py's `_state_literals`): a query
        that force-asserts a <state> value other than the one an
        ESTABLISHED-only permit rule requires must NOT be able to reach that
        rule's target, and force-asserting the SAME value it requires must
        still reach it.

        This pins down the exact mechanism `_state_literals` relies on:
        appending XMLUtils.ConvertStateToVariables(value)'s FLATTENED child
        literals (not the whole <conjunction> as one nested element) onto an
        InstantiateEndToEnd instance's clause list. The whole-conjunction
        form was tried first and is a silent no-op -- instance[0] is already
        the base model's CNF'd clause list (from InstantiateBase), so a
        nested, un-flattened <conjunction> child never gets attached as
        constraining literals and asserting it can even manufacture a
        spurious UNSAT (see ad6/FAVE_CHANGES.md for the fixture that
        surfaced this). """
        firewall = GenUtils.firewall('sfw')

        table = GenUtils.table('t0')
        rule = GenUtils.rule('0', key='sfw_t_r0')
        rule.append(GenUtils.state('ESTABLISHED'))
        rule.append(GenUtils.action('jump', target='sfw_t_r_estab_target'))
        table.append(rule)
        firewall.append(table)

        target_table = GenUtils.table('t_estab')
        target = GenUtils.rule('e', key='sfw_t_r_estab_target')
        target.append(GenUtils.action('accept'))
        target_table.append(target)
        firewall.append(target_table)

        config = GenUtils.config()
        firewalls = GenUtils.firewalls()
        firewalls.append(firewall)
        config.append(firewalls)

        kripke, encoding = Instantiator.InstantiateBase(
            config, Inits=['sfw_t_r0'], default_inits=False
        )
        solver = PycoSATAdapter()

        def reachable_forcing(state_value):
            instance = Instantiator.InstantiateEndToEnd(
                kripke, encoding, 'sfw_t_r0', 'sfw_t_r_estab_target')
            for literal in XMLUtils.ConvertStateToVariables(state_value):
                instance[0].append(literal)
            return bool(solver.Solve(instance))

        self.assertTrue(
            bool(solver.Solve(Instantiator.InstantiateEndToEnd(
                kripke, encoding, 'sfw_t_r0', 'sfw_t_r_estab_target'))),
            "the ESTABLISHED-conditioned rule itself is unreachable unconstrained")
        self.assertTrue(reachable_forcing('ESTABLISHED'),
                        "forcing the SAME state the rule requires must still reach it")
        self.assertFalse(reachable_forcing('NEW'),
                         "forcing state=NEW must NOT reach an ESTABLISHED-only rule")
        self.assertFalse(reachable_forcing('RELATED'),
                         "forcing state=RELATED must NOT reach an ESTABLISHED-only rule")


    def testSrcCidrQuerySeedMustUseSharedBitVector(self):
        """ Regression for the wl_up stateful-differential "bug 2" finding
        (AD6_PLAN.md §5.1, ad6/fave_bridge.py's `_seed_conjunct`): a query
        that force-asserts the packet's source address into a specific CIDR
        MUST do so via XMLUtils.ConvertCIDRToVariables's flattened bit
        literals (the same shared `ip<version>_src_<i>=<bit>` space every
        rule's own address condition is built over) -- NOT via a bare
        named-alias variable from XMLUtils.ConvertToVariables/`variable()`.

        The alias form only carries meaning if that EXACT alias name happens
        to already be `Handled` (defined via an equality clause during
        Instantiator.InstantiateBase's scan) by some OTHER rule in the model
        referencing that exact address/CIDR string. wl_up's real bug: a
        source-seeded host address never referenced verbatim anywhere else
        in the whole 159-device ruleset corpus produces a free, unconnected
        atom -- forcing it "true" does nothing to the real header-bit
        variables, so an explicit source-scoped DROP rule for that address
        is silently bypassed (7 of 8 structurally identical wl_up singleton
        hosts; only the one host whose exact address happened to be
        referenced elsewhere, by coincidence, was correctly blocked). """
        firewall = GenUtils.firewall('sfw')

        table = GenUtils.table('t0')
        r0 = GenUtils.rule('0', key='sfw_t_r0')
        r0.append(GenUtils.address('10.0.0.0/24', direction='src', version='4'))
        r0.append(GenUtils.action('drop'))
        table.append(r0)
        r1 = GenUtils.rule('1', key='sfw_t_r1')
        r1.append(GenUtils.action('accept'))
        table.append(r1)
        firewall.append(table)

        config = GenUtils.config()
        firewalls = GenUtils.firewalls()
        firewalls.append(firewall)
        config.append(firewalls)

        kripke, encoding = Instantiator.InstantiateBase(
            config, Inits=['sfw_t_r0'], default_inits=False
        )
        solver = PycoSATAdapter()

        # sanity: with no seed at all, the fallthrough accept is reachable
        # (r0's address condition is free, solver can pick "doesn't match").
        unconstrained = Instantiator.InstantiateReach(kripke, encoding, 'sfw_t_r1')
        self.assertTrue(bool(solver.Solve(unconstrained)),
                        "the fallthrough accept is unreachable even unconstrained")

        seeded_addr = '10.0.0.5/32'  # inside r0's DROP range, never mentioned elsewhere

        def reachable_with(seed_literals):
            instance = Instantiator.InstantiateReach(kripke, encoding, 'sfw_t_r1')
            for literal in seed_literals:
                instance[0].append(literal)
            return bool(solver.Solve(instance))

        alias_elem = et.fromstring(
            '<ip xmlns="http://config" version="4" direction="src">'
            '<address>%s</address></ip>' % seeded_addr)
        InstantiatorTest.deannotate(alias_elem)
        alias_seed = [XMLUtils.ConvertToVariables(alias_elem)]

        bitvector_seed = list(XMLUtils.ConvertCIDRToVariables(seeded_addr, 'src'))

        self.assertTrue(
            reachable_with(alias_seed),
            "the bare-alias seed is a free atom and should NOT constrain "
            "anything -- this is the bug: it wrongly leaves the DROP-range "
            "address's fallthrough reachable")
        self.assertFalse(
            reachable_with(bitvector_seed),
            "the flattened shared-bit-vector seed must correctly force the "
            "address into r0's DROP range and block the fallthrough")


    def testMutationChainAndJoinSSAEncoding(self):
        """ AD6_PLAN.md §5.4 Stage A: the SSA/frame-axiom mutation encoding
        (Instantiator._CreateMutationConstraints, GenUtils.action's
        rewrite_field/rewrite_value, KripkeNode.Rewrites). Two Kripke paths
        into a shared node `join_r0`:

          entryA_r0 -> r1_r0 (rewrite vlan=1) -> r2_r0 (rewrite vlan=0)
                    -> r3_r0 (rewrite vlan=2) -> join_r0
          entryB_r0 -> alt_r0 (no rewrite)    -> join_r0

        The first path is a THREE-deep rewrite chain on one path -- the
        `b=* -> 1 -> 0 -> *`-style case a single global variable cannot
        express at all (see AD6_PLAN.md §5.4's correction of the
        superseded structural-duplication draft). The second path
        exercises the join: two predecessors with different field
        histories reaching the SAME node, one of which never rewrites
        anything, so its own field value must stay genuinely free all the
        way back to its own (unconstrained) entry.

        entryA_r0/entryB_r0 are both marked INIT -- Instantiator.
        _CreateInitConstraints's EXISTING mutual exclusion (AD6_PLAN.md
        §8, ad6/FAVE_CHANGES.md §8) then guarantees that forcing one
        path's own entry transition via InstantiateEndToEnd excludes the
        other's, without this test inventing any new exclusivity
        mechanism -- reused exactly as _ConvertNodesToImplications's own
        reachability discipline already relies on to pick a specific
        predecessor at the join. """
        def _hop(name, key, target, field=None, value=None):
            table = GenUtils.table(name)
            rule = GenUtils.rule(name, key=key)
            rule.append(GenUtils.action(
                'jump', target=target, rewrite_field=field, rewrite_value=value))
            table.append(rule)
            return table

        def _sink(name, key):
            table = GenUtils.table(name)
            rule = GenUtils.rule(name, key=key)
            rule.append(GenUtils.action('accept'))
            table.append(rule)
            return table

        firewall = GenUtils.firewall('mutfw')
        firewall.append(_hop('t0', 'entryA_r0', 'r1_r0'))
        firewall.append(_hop('t1', 'r1_r0', 'r2_r0', 'vlan', 1))
        firewall.append(_hop('t2', 'r2_r0', 'r3_r0', 'vlan', 0))
        firewall.append(_hop('t3', 'r3_r0', 'join_r0', 'vlan', 2))
        firewall.append(_hop('t4', 'entryB_r0', 'alt_r0'))
        firewall.append(_hop('t5', 'alt_r0', 'join_r0'))
        firewall.append(_sink('t6', 'join_r0'))

        config = GenUtils.config()
        firewalls = GenUtils.firewalls()
        firewalls.append(firewall)
        config.append(firewalls)

        kripke, encoding = Instantiator.InstantiateBase(
            config, Inits=['entryA_r0', 'entryB_r0'], default_inits=False,
            MutableFields={'vlan': 12}
        )
        solver = PycoSATAdapter()

        def reachable_with_vlan(source, value):
            instance = Instantiator.InstantiateEndToEnd(kripke, encoding, source, 'join_r0')
            instance[0].extend(list(XMLUtils.ConvertFieldToVariables('vlan', 'join_r0', value, 12)))
            return bool(solver.Solve(instance))

        # --- the 3-deep rewrite chain: join_r0 must be EXACTLY 2 via entryA
        self.assertTrue(
            reachable_with_vlan('entryA_r0', 2),
            "the rewrite chain (1 -> 0 -> 2) must leave vlan=2 at join_r0")
        self.assertFalse(
            reachable_with_vlan('entryA_r0', 1),
            "join_r0's vlan must NOT still be 1 -- an intermediate rewrite "
            "was dropped or not chained through to join_r0")
        self.assertFalse(
            reachable_with_vlan('entryA_r0', 3),
            "join_r0's vlan must not be forceable to an unrelated value via "
            "the rewrite path -- it is pinned to exactly 2, not free")

        # --- the join's other predecessor never rewrites: genuinely free
        self.assertTrue(
            reachable_with_vlan('entryB_r0', 5),
            "the non-rewriting path's vlan must still be forceable to an "
            "arbitrary value (5) -- it was never pinned by any rewrite")
        self.assertTrue(
            reachable_with_vlan('entryB_r0', 7),
            "...and to a DIFFERENT arbitrary value (7) too -- proving it "
            "is genuinely free, not accidentally pinned to just one value")


    def testFieldMatchGatesOnMutatedSSAValue(self):
        """ AD6_PLAN.md §5.4 Stage A2: GenUtils.fieldmatch()/
        XMLUtils.FieldMatchAliasName -- a rule's own Gamma matching against
        ITS node's per-node SSA copy of a mutable field (as set by whichever
        upstream rewrite fired), not a single global constant. This is the
        real Stanford in.X admission shape: "only admit onward if the
        packet's CURRENT vlan tag (as rewritten by the upstream mid.X hop)
        is one of the admitted set" -- Stage A alone (forcing/reading a
        per-node value from the QUERY side, via
        XMLUtils.ConvertFieldToVariables) proved the rewrite/frame-axiom
        chain but never exercised a rule's own Gamma reading that chain
        back, which is what an admission ACL actually needs.

        Three entries rewrite vlan to different values on their way into a
        SHARED admission gate node, whose own Gamma is
        fieldmatch(vlan,5) OR fieldmatch(vlan,7) -- "admit vlan in {5,7}":

          entryA_r0 --(rewrite vlan=5)--> gate_r0 --(jump)--> accept_r0
          entryB_r0 --(rewrite vlan=6)--> gate_r0 --(jump)--> accept_r0
          entryC_r0 --(rewrite vlan=7)--> gate_r0 --(jump)--> accept_r0

        entryA's/entryC's rewritten value is in the admitted set ->
        accept_r0 reachable; entryB's (6) is not -> UNSAT -- even though
        the only structural difference between the three paths is which
        value the upstream rewrite chose, proving the match reads the live
        per-node SSA value flowing in, not a build-time-fixed alias (the
        pre-Stage-A2 mechanism could not express this at all: a single
        global "vlan" alias can't hold 5, 6 AND 7 at once for the same
        model). entryA/B/C are all marked INIT -- reuses
        _CreateInitConstraints's existing mutual exclusion (already relied
        on by testMutationChainAndJoinSSAEncoding for the 2-entry case) to
        isolate one path per query, same discipline, no new mechanism. """
        def _hop(name, key, target, field=None, value=None):
            table = GenUtils.table(name)
            rule = GenUtils.rule(name, key=key)
            rule.append(GenUtils.action(
                'jump', target=target, rewrite_field=field, rewrite_value=value))
            table.append(rule)
            return table

        def _gate(name, key, target, field, values):
            table = GenUtils.table(name)
            rule = GenUtils.rule(name, key=key)
            for value in values:
                rule.append(GenUtils.fieldmatch(field, value))
            rule.append(GenUtils.action('jump', target=target))
            table.append(rule)
            return table

        def _sink(name, key):
            table = GenUtils.table(name)
            rule = GenUtils.rule(name, key=key)
            rule.append(GenUtils.action('accept'))
            table.append(rule)
            return table

        firewall = GenUtils.firewall('fieldmatchfw')
        firewall.append(_hop('t0', 'entryA_r0', 'gate_r0', 'vlan', 5))
        firewall.append(_hop('t1', 'entryB_r0', 'gate_r0', 'vlan', 6))
        firewall.append(_hop('t2', 'entryC_r0', 'gate_r0', 'vlan', 7))
        firewall.append(_gate('t3', 'gate_r0', 'accept_r0', 'vlan', [5, 7]))
        firewall.append(_sink('t4', 'accept_r0'))

        config = GenUtils.config()
        firewalls = GenUtils.firewalls()
        firewalls.append(firewall)
        config.append(firewalls)

        kripke, encoding = Instantiator.InstantiateBase(
            config, Inits=['entryA_r0', 'entryB_r0', 'entryC_r0'], default_inits=False,
            MutableFields={'vlan': 12}
        )
        solver = PycoSATAdapter()

        def reachable(source):
            instance = Instantiator.InstantiateEndToEnd(kripke, encoding, source, 'accept_r0')
            return bool(solver.Solve(instance))

        self.assertTrue(
            reachable('entryA_r0'),
            "vlan=5 is in the admitted set {5,7} -- must be admitted")
        self.assertFalse(
            reachable('entryB_r0'),
            "vlan=6 is NOT in the admitted set {5,7} -- must be blocked, "
            "not vacuously admitted by a stale/global vlan alias")
        self.assertTrue(
            reachable('entryC_r0'),
            "vlan=7 is in the admitted set {5,7} -- must be admitted "
            "(proves the OR-of-values disjunction, not just a single value)")


    def _fieldmatch_gate_model(self, gate_conditions):
        """ Shared shape for the fieldmatch-gate tests: three entries rewrite
        `vlan` to 5/6/7 on their way into ONE shared gate node, whose Gamma is
        `gate_conditions` (a list of GenUtils.fieldmatch elements). Returns a
        `reachable(entry)` predicate. Mirrors
        testFieldMatchGatesOnMutatedSSAValue's model exactly so the positive
        and negated cases differ only in the gate's conditions. """
        def _hop(name, key, target, field=None, value=None):
            table = GenUtils.table(name)
            rule = GenUtils.rule(name, key=key)
            rule.append(GenUtils.action(
                'jump', target=target, rewrite_field=field, rewrite_value=value))
            table.append(rule)
            return table

        def _gate(name, key, target, conditions):
            table = GenUtils.table(name)
            rule = GenUtils.rule(name, key=key)
            for condition in conditions:
                rule.append(condition)
            rule.append(GenUtils.action('jump', target=target))
            table.append(rule)
            return table

        def _sink(name, key):
            table = GenUtils.table(name)
            rule = GenUtils.rule(name, key=key)
            rule.append(GenUtils.action('accept'))
            table.append(rule)
            return table

        firewall = GenUtils.firewall('fieldmatchfw')
        firewall.append(_hop('t0', 'entryA_r0', 'gate_r0', 'vlan', 5))
        firewall.append(_hop('t1', 'entryB_r0', 'gate_r0', 'vlan', 6))
        firewall.append(_hop('t2', 'entryC_r0', 'gate_r0', 'vlan', 7))
        firewall.append(_gate('t3', 'gate_r0', 'accept_r0', gate_conditions))
        firewall.append(_sink('t4', 'accept_r0'))

        config = GenUtils.config()
        firewalls = GenUtils.firewalls()
        firewalls.append(firewall)
        config.append(firewalls)

        kripke, encoding = Instantiator.InstantiateBase(
            config, Inits=['entryA_r0', 'entryB_r0', 'entryC_r0'],
            default_inits=False, MutableFields={'vlan': 12}
        )
        solver = PycoSATAdapter()

        def reachable(source):
            instance = Instantiator.InstantiateEndToEnd(
                kripke, encoding, source, 'accept_r0')
            return bool(solver.Solve(instance))

        return reachable


    def testNegatedFieldMatchExcludesItsValue(self):
        """ A NEGATED <fieldmatch> must exclude its value, not admit it.

        `GenUtils.fieldmatch(field, value, negated=True)` sets negated="true"
        on the element, but KripkeUtils._HandleRule's FieldMatch branch read
        only the field name and the text and built the alias variable with
        XMLUtils.variable()'s DEFAULT polarity (negated="false"). Since
        Instantiator._HandleFieldMatches defines that alias as
        `alias <-> (per-node bits == value)`, an always-positive use site
        encodes `NOT (f == v)` as `f == v` -- an INVERSION, not a dropped
        match, so the model answers the opposite question and still looks
        well-formed.

        Latent when found (2026-09-21): fave/test/test_ad6_translate.py records
        that no benchmark emits a negated match, and the tests that existed
        pinned the PRODUCER (field_to_match emits negated="true") while nothing
        pinned this CONSUMER. Reached by making addresses mutable, since the
        compliance path negates them.

        Gate: `vlan != 6` -- the exact complement of
        testFieldMatchGatesOnMutatedSSAValue's admitted set. """
        reachable = self._fieldmatch_gate_model(
            [GenUtils.fieldmatch('vlan', 6, negated=True)])

        self.assertTrue(
            reachable('entryA_r0'),
            "vlan=5 satisfies `vlan != 6` -- must be admitted")
        self.assertFalse(
            reachable('entryB_r0'),
            "vlan=6 violates `vlan != 6` -- must be blocked. Admitting it means "
            "the negation was dropped and the match encoded positively")
        self.assertTrue(
            reachable('entryC_r0'),
            "vlan=7 satisfies `vlan != 6` -- must be admitted")


    def testNegatedFieldMatchesOnOneFieldConjoin(self):
        """ Several NEGATED matches on the SAME field must AND, not OR.

        Positive matches on one field are a disjunction -- that is the VLAN
        admission set testFieldMatchGatesOnMutatedSSAValue pins. Their
        complement is a CONJUNCTION by De Morgan: `vlan not in {5,7}` is
        `vlan != 5 AND vlan != 7`. Grouping negatives with the same OR would
        yield `vlan != 5 OR vlan != 7`, which is a TAUTOLOGY for any two
        distinct values -- the gate would admit everything, including the two
        values it names, and would do so silently.

        Gate: `vlan != 5 AND vlan != 7` -- the exact complement of that test's
        admitted set, so the three verdicts must invert. """
        reachable = self._fieldmatch_gate_model([
            GenUtils.fieldmatch('vlan', 5, negated=True),
            GenUtils.fieldmatch('vlan', 7, negated=True),
        ])

        self.assertFalse(
            reachable('entryA_r0'),
            "vlan=5 violates `vlan != 5` -- must be blocked")
        self.assertTrue(
            reachable('entryB_r0'),
            "vlan=6 satisfies both `vlan != 5` and `vlan != 7` -- must be admitted")
        self.assertFalse(
            reachable('entryC_r0'),
            "vlan=7 violates `vlan != 7` -- must be blocked. Admitting all three "
            "means the negatives were OR-ed into a tautology")


    def testMixedFieldMatchPolaritiesOnOneField(self):
        """ Positives and negatives on ONE field compose as
        (OR of positives) AND (AND of negatives).

        Gate: `vlan in {5,6} AND vlan != 6` -- admits 5 alone. If the negative
        joined the positives' disjunction the gate would read
        `5 OR 6 OR NOT 6` = true and admit everything; if the positives were
        conjoined it would admit nothing. """
        reachable = self._fieldmatch_gate_model([
            GenUtils.fieldmatch('vlan', 5),
            GenUtils.fieldmatch('vlan', 6),
            GenUtils.fieldmatch('vlan', 6, negated=True),
        ])

        self.assertTrue(
            reachable('entryA_r0'),
            "vlan=5 is in {5,6} and is not 6 -- must be admitted")
        self.assertFalse(
            reachable('entryB_r0'),
            "vlan=6 is in {5,6} but IS 6 -- the negative must veto it")
        self.assertFalse(
            reachable('entryC_r0'),
            "vlan=7 is not in {5,6} -- must be blocked")


    def testMaskedFieldMatchConstrainsOnlyItsDeterminedBits(self):
        """ A <fieldmatch> whose text is a TERNARY bit-string constrains the
        '0'/'1' positions and leaves the 'x' positions FREE.

        This is what lets a mutable field carry a prefix match. ad6 already had
        two prefix-capable converters -- ConvertPortToVariables and
        ConvertCIDRToVariables both truncate a bit-vector to a prefix -- but
        ConvertFieldToVariables, the newest, was written for exact-valued
        fields (vlan, in_port, out_port) and took an int, so a mutable field
        could only ever be matched for EQUALITY. A field rewritten anywhere
        must use <fieldmatch> everywhere, so that made "rewritten AND matched
        by prefix" inexpressible -- the boundary wl_cloud's NAT reaches
        (CLOUD_BENCH_PLAN.md Sec. 1.7.2).

        Gate: vlan matches `00000000010x` -- i.e. {4, 5}. The three entries
        rewrite vlan to 5/6/7, so only the first is admitted. A mask read as an
        exact value would admit none of them. """
        reachable = self._fieldmatch_gate_model(
            [GenUtils.fieldmatch('vlan', 'b00000000010x')])

        self.assertTrue(
            reachable('entryA_r0'),
            "vlan=5 (000000000101) matches the mask 00000000010x -- must be admitted")
        self.assertFalse(
            reachable('entryB_r0'),
            "vlan=6 (000000000110) does not match 00000000010x -- must be blocked")
        self.assertFalse(
            reachable('entryC_r0'),
            "vlan=7 (000000000111) does not match 00000000010x -- must be blocked")


    def testMaskedFieldMatchDontCaresAreGenuinelyFree(self):
        """ The 'x' positions must be UNCONSTRAINED, not implicitly zero.

        The complement of the test above: widening the mask by one bit to
        `0000000001xx` covers {4,5,6,7}, so all three entries are admitted. If
        a don't-care emitted a literal (or was zero-padded), 6 and 7 would stay
        blocked and the mask would silently narrow -- an under-approximation,
        the direction that reports unreachable what is reachable. """
        reachable = self._fieldmatch_gate_model(
            [GenUtils.fieldmatch('vlan', 'b0000000001xx')])

        for entry, value in (('entryA_r0', 5), ('entryB_r0', 6), ('entryC_r0', 7)):
            self.assertTrue(
                reachable(entry),
                "vlan=%d is in {4,5,6,7} = 0000000001xx -- must be admitted; "
                "blocking it means the don't-care bits were pinned" % value)


    def testWhollyUnconstrainedFieldMatchIsVacuouslyTrue(self):
        """ An ALL-don't-care mask constrains nothing, so it admits everything.

        The degenerate end of the mask range, pinned because it is the case a
        naive implementation gets wrong in the UNSATISFIABLE direction -- a
        condition that constrains nothing must not become a condition nothing
        satisfies.

        It does NOT pin any empty-conjunction guard. ConvertCIDRToVariables
        guards its equivalent /0 case, and the first version of this work
        copied that guard across; a mutation check then showed removing it
        changes no test, and measuring the instance showed why -- the hazard
        there is Instantiator._ShortenPrefixes splicing a /0 into other CIDRs'
        conjunctions, machinery a <fieldmatch> never reaches. The guard came
        back out. """
        reachable = self._fieldmatch_gate_model(
            [GenUtils.fieldmatch('vlan', 'b' + 'x' * 12)])

        for entry, value in (('entryA_r0', 5), ('entryB_r0', 6), ('entryC_r0', 7)):
            self.assertTrue(
                reachable(entry),
                "an all-don't-care mask constrains nothing, so vlan=%d must be "
                "admitted; blocking it means the empty conjunction went out as "
                "an unsatisfiable condition" % value)


    def testNegatedMaskedFieldMatchExcludesTheWholeRange(self):
        """ Negation and masking compose: `NOT (vlan in {4,5})` blocks 5 and
        admits 6 and 7. Pins the two changes against each other, since the
        compliance path that needs masks (wl_cloud's complement checks) is
        also the one that negates. """
        reachable = self._fieldmatch_gate_model(
            [GenUtils.fieldmatch('vlan', 'b00000000010x', negated=True)])

        self.assertFalse(
            reachable('entryA_r0'),
            "vlan=5 IS in {4,5} -- the negated mask must block it")
        self.assertTrue(
            reachable('entryB_r0'),
            "vlan=6 is not in {4,5} -- must be admitted")
        self.assertTrue(
            reachable('entryC_r0'),
            "vlan=7 is not in {4,5} -- must be admitted")


    def testReach(self):
        examinee = et.parse('./test/core/testReach.xml').getroot()
        InstantiatorTest.deannotate(examinee)
        expectation = [{
            'net0_n0_accept_r0_true_net0_n0_eth0_out': False,
            'net0_n0_output_r0_true_net0_n0_fwdin_r0': True,
            'net0_n0_fwdin_r0_false_net0_n0_fwdin_r4096': False,
            'net0_n0_fwdin_r0_true_net0_n0_drop_r0': True,
            'net0_n0_fwdin_r4096_false_net0_n0_fwdin_r8192': False,
            'net0_n0_fwdin_r4096_true_net0_n0_accept_r0': False,
            'net0_n0_fwdin_r8192_true_net0_n0_drop_r0': False,
            'proto_0=0' : False,
            'proto_0=1' : False,
            'proto_1=0' : False,
            'proto_1=1' : False,
            'proto_2=0' : False,
            'proto_2=1' : False,
            'proto_3=0' : False,
            'proto_3=1' : False,
            'proto_4=0' : False,
            'proto_4=1' : False,
            'proto_5=0' : False,
            'proto_5=1' : False,
            'proto_6=0' : False,
            'proto_6=1' : False,
            'proto_7=0' : False,
            'proto_7=1' : False,
            'proto_tcp' : False,
        }]

        solver = PycoSATAdapter()
        instances = Instantiator.Instantiate(examinee)

        self.assertEqual(solver.Solve(instances['net0_n0_drop_r0_reach']),expectation)

        expectation = []
        self.assertEqual(solver.Solve(instances['net0_n0_accept_r0_reach']),expectation)


    def testCycle(self):
        examinee = et.parse('./test/core/testCycle.xml').getroot()
        InstantiatorTest.deannotate(examinee)
        expectation = [{
            'net0_n0_accept_r0_true_net0_n0_eth0_out': False,
            'net0_n0_output_r0_true_net0_n0_fwdin_r0': True,
            'net0_n0_fwdin_r0_false_net0_n0_fwdin_r4096': True,
            'net0_n0_fwdin_r0_true_net0_n0_accept_r0': False,
            'net0_n0_fwdin_r4096_false_net0_n0_fwdin_r8192': False,
            'net0_n0_fwdin_r4096_true_net0_n0_fwdin_r0': True,
            'net0_n0_fwdin_r8192_true_net0_n0_drop_r0': False,
            'proto_0=0' : True,
            'proto_0=1' : False,
            'proto_1=0' : True,
            'proto_1=1' : False,
            'proto_2=0' : True,
            'proto_2=1' : False,
            'proto_3=0' : True,
            'proto_3=1' : False,
            'proto_4=0' : True,
            'proto_4=1' : False,
            'proto_5=0' : False,
            'proto_5=1' : True,
            'proto_6=0' : False,
            'proto_6=1' : True,
            'proto_7=0' : True,
            'proto_7=1' : False,
            'proto_tcp' : True,
            'proto_udp' : False,
        }]
        solver = MiniSATAdapter()
        instances = Instantiator.Instantiate(examinee, Reach=False, Cycle=True)
        self.assertEqual(solver.Solve(instances['cycle']),expectation)


    def testShadow(self):
        examinee = et.parse('./test/core/testShadow.xml').getroot()
        InstantiatorTest.deannotate(examinee)
        expectation = [{
            'net0_n0_accept_r0_true_net0_n0_eth0_out': False,
            'net0_n0_output_r0_true_net0_n0_fwdin_r0': True,
            'net0_n0_fwdin_r0_false_net0_n0_fwdin_r4096': False,
            'net0_n0_fwdin_r0_true_net0_n0_accept_r0': True,
            'net0_n0_fwdin_r4096_false_net0_n0_fwdin_r8192': False,
            'net0_n0_fwdin_r4096_true_net0_n0_drop_r0': False,
            'net0_n0_fwdin_r8192_true_net0_n0_drop_r0': False,
            'proto_0=0' : True,
            'proto_0=1' : False,
            'proto_1=0' : True,
            'proto_1=1' : False,
            'proto_2=0' : True,
            'proto_2=1' : False,
            'proto_3=0' : True,
            'proto_3=1' : False,
            'proto_4=0' : True,
            'proto_4=1' : False,
            'proto_5=0' : False,
            'proto_5=1' : True,
            'proto_6=0' : False,
            'proto_6=1' : True,
            'proto_7=0' : True,
            'proto_7=1' : False,
            'proto_tcp' : True,
        }]

        solver = MiniSATAdapter()
        instances = Instantiator.Instantiate(examinee, Reach=False, Shadow=True)

        self.assertEqual(solver.Solve(instances['net0_n0_accept_r0_shadow']),expectation)


        expectation = []
        self.assertEqual(solver.Solve(instances['net0_n0_fwdin_r4096_shadow']),expectation)


    def testCross(self):
        examinee = et.parse('./test/core/testCross.xml').getroot()
        InstantiatorTest.deannotate(examinee)
        expectation = [{
            'net0_n0_eth0_out_true_net0_n1_eth0_in': True,
            'net0_n0_eth0_out_true_net0_n2_eth0_in': True,
            'net0_n0_accept_r0_true_net0_n0_eth0_out': True,
            'net0_n0_output_r0_true_net0_n0_accept_r0': True,
            'net0_n1_eth0_in_true_net0_n1_input_r0': True,
            'net0_n1_eth0_out_true_net0_n0_eth0_in': False,
            'net0_n1_input_r0_false_net0_n1_input_r4096': False,
            'net0_n1_input_r0_true_net0_n1_input_r0_accept': True,
            'net0_n1_input_r4096_true_net0_n1_drop_r0': False,
            'net0_n2_eth0_in_true_net0_n2_input_r0': True,
            'net0_n2_eth0_out_true_net0_n0_eth0_in': False,
            'net0_n2_input_r0_false_net0_n2_input_r4096': False,
            'net0_n2_input_r0_true_net0_n2_drop_r0': True,
            'net0_n2_input_r4096_true_net0_n2_drop_r0': False,
            'proto_0=0' : True,
            'proto_0=1' : False,
            'proto_1=0' : True,
            'proto_1=1' : False,
            'proto_2=0' : True,
            'proto_2=1' : False,
            'proto_3=0' : True,
            'proto_3=1' : False,
            'proto_4=0' : True,
            'proto_4=1' : False,
            'proto_5=0' : False,
            'proto_5=1' : True,
            'proto_6=0' : False,
            'proto_6=1' : True,
            'proto_7=0' : True,
            'proto_7=1' : False,
            'proto_tcp' : True,
        }]
        solver = MiniSATAdapter()
        instances = Instantiator.Instantiate(examinee, Reach=False, Cross=True)
        self.assertEqual(solver.Solve(instances['cross']),expectation)


    def testCycleReachabilityIsUnsoundWithoutRealOrigin(self):
        """ AD6_PLAN.md §5.4 Stage B (B1): KNOWN, UNFIXED ad6 core
        limitation, found via wl_stanford's B1 differential (a real
        backbone network with genuine inter-router cycles). Documented
        here as a minimal, isolated CHARACTERIZATION -- not a regression
        test for something that's been fixed.

        Instantiator.InstantiateEndToEnd's reachability query does not
        require a satisfying model to trace back to a genuinely-fired
        INIT: a CYCLE of mutually-satisfiable transitions (A->B->C->A,
        none marked INIT) is a self-consistent fixed point the SAT solver
        can satisfy for free, entirely independent of whether any real
        generator's own edge fired. A generator with NO real connection to
        the cycle at all (`entry`, which only ever jumps to its own
        unrelated sink) still "reaches" any node in the cycle.

        Confirmed a genuine PRE-EXISTING ad6 core property, not a
        translator bug: this fixture uses zero Stanford-specific/Stage-0/
        Stage-A/§5.4-Stage-B machinery, pure GenUtils/Instantiator
        primitives. ad6's original 2014 design target (a single firewall's
        own rule-chain, always acyclic by construction -- a table's
        fallthrough/jump structure has no way to loop back on itself)
        never needed reachability to be grounded in a real origin.
        wl_ifi/wl_up's topologies happen to be acyclic too, so this was
        never exercised until Stanford's real backbone network (genuine
        redundant inter-router links) surfaced it -- explains why §5.4
        Stage B0's tiny 2-router slice (bbra_rtr/rozb_rtr, no cycle
        between just those two) passed cleanly while B1's full 16-router
        differential did not.

        Fixing this is real core surgery (e.g. a rank/distance variable
        enforcing strict progress along a real path -- the standard
        technique for this class of SAT-encoded-reachability pitfall,
        related to but distinct from what InstantiateCycle/_CreateCycle
        already checks for) -- deliberately NOT attempted here. This test
        exists to PIN the exact mechanism for whoever picks this up next,
        and is expected to start FAILING (a welcome failure) the day it's
        fixed -- if that happens, update this docstring and AD6_PLAN.md
        §5.4 Stage B, not just this assertion. """
        def hop(name, key, target):
            table = GenUtils.table(name)
            rule = GenUtils.rule(name, key=key)
            rule.append(GenUtils.action('jump', target=target))
            table.append(rule)
            return table

        firewall = GenUtils.firewall('cyclefw')
        firewall.append(hop('a', 'A', 'B'))
        firewall.append(hop('b', 'B', 'C'))
        firewall.append(hop('c', 'C', 'A'))
        firewall.append(hop('e', 'entry', 'unrelated_sink'))
        sink_table = GenUtils.table('sink')
        sink_rule = GenUtils.rule('sink', key='unrelated_sink')
        sink_rule.append(GenUtils.action('accept'))
        sink_table.append(sink_rule)
        firewall.append(sink_table)

        config = GenUtils.config()
        firewalls = GenUtils.firewalls()
        firewalls.append(firewall)
        config.append(firewalls)

        kripke, encoding = Instantiator.InstantiateBase(
            config, Inits=['entry'], default_inits=False)
        solver = PycoSATAdapter()

        instance = Instantiator.InstantiateEndToEnd(kripke, encoding, 'entry', 'A')
        self.assertTrue(
            bool(solver.Solve(instance)),
            "KNOWN gap regressed to being FIXED -- if this now correctly "
            "returns UNSAT (entry cannot really reach the unrelated "
            "cycle), update AD6_PLAN.md §5.4 Stage B and this test's own "
            "docstring: the Stanford B1 blocker this test documents may "
            "now be resolved.")


    def testBackwardSupportRestrictsBlockingToDestinationsOwnClosure(self):
        """ AD6_PLAN.md §5.4 Stage B (B1) perf finding: profiling a 3-router
        wl_stanford backbone slice showed a single genuinely-unreachable
        query needing ~117 solver iterations (~45s) to converge, because the
        original SolveGroundedEndToEnd blocked the ENTIRE fired-transition
        set of each rejected witness -- including transitions completely
        unrelated to why Destination looked reachable (other floating loops
        or unrelated fallthrough edges elsewhere in the same graph, free to
        vary independently). That makes each blocking clause hyper-specific
        to one exact model instead of ruling out the whole FAMILY of "same
        underlying floating loop, different irrelevant bits elsewhere"
        witnesses, so the solver re-discovers trivial variants of the same
        loop over and over.

        Instantiator._BackwardSupport(Fired, Destination) computes only the
        nodes that can reach Destination via THIS witness's own true
        transitions (a backward walk) -- Destination's own "explanation"
        for why it looks reached. _BlockWitness then restricts its clause to
        transitions landing inside that closure, dropping everything else.

        This fixture: a real, unconditionally-fired edge (origin->M, would
        be forced true in EVERY model of a query from `origin`) plus an
        unrelated floating cycle X->Y->Z->X, where Z separately also has a
        live edge into D. Support(D) must be exactly {D,Z,Y,X} -- NOT
        `origin`/`M`, which have nothing to do with D's own backward
        closure. Confirms both restriction directions: the closure is
        computed correctly, and _BlockWitness's clause only ever contains
        the closure's own edges -- never the real, mandatory `origin_true_M`
        edge (blocking that would make every future query from `origin`
        permanently, incorrectly UNSAT). """
        Fired = [
            ('origin', 'M', True),
            ('X', 'Y', True),
            ('Y', 'Z', True),
            ('Z', 'X', True),
            ('Z', 'D', True),
        ]

        Support = Instantiator._BackwardSupport(Fired, 'D')
        self.assertEqual(Support, {'D', 'Z', 'Y', 'X'})

        Block = Instantiator._BlockWitness(Fired, Support)
        BlockedNames = {Literal.attrib[XMLUtils.ATTRNAME] for Literal in Block}
        self.assertEqual(BlockedNames, {
            'Z_true_D', 'Y_true_Z', 'X_true_Y', 'Z_true_X',
        })
        self.assertNotIn(
            'origin_true_M', BlockedNames,
            "the real, unconditionally-fired source edge must never be "
            "blocked -- doing so would make every future query through "
            "this source permanently (and incorrectly) UNSAT")


    def testSolveGroundedEndToEndRejectsUngroundedCycleWitness(self):
        """ AD6_PLAN.md §5.4 Stage B (B1) fix for the gap pinned by
        testCycleReachabilityIsUnsoundWithoutRealOrigin: raw
        Instantiator.InstantiateEndToEnd/solver.Solve is unsound on cyclic
        topologies because it asserts two INDEPENDENT disjuncts (source's
        own edge fired; destination's own edge fired) rather than a single
        connected path -- a self-sustaining cycle with no real INIT is a
        free fixed point the solver can satisfy without grounding either
        disjunct in the actual query's source.

        Instantiator.SolveGroundedEndToEnd is the fix: after each solve, it
        walks the CONCRETE model's fired transitions (via the real Kripke
        graph, not string-parsing) from Source and checks Destination is
        actually reachable that way; if not, it blocks that exact
        combination of fired transitions and re-solves. Same fixture as the
        characterization test above (a floating A->B->C->A cycle plus an
        unrelated `entry`generator), same rejected pair (`entry`->`A`),
        this time via the fixed entry point -- this must return False, and
        do so within very few iterations (the model space here is tiny). """
        def hop(name, key, target):
            table = GenUtils.table(name)
            rule = GenUtils.rule(name, key=key)
            rule.append(GenUtils.action('jump', target=target))
            table.append(rule)
            return table

        firewall = GenUtils.firewall('cyclefw')
        firewall.append(hop('a', 'A', 'B'))
        firewall.append(hop('b', 'B', 'C'))
        firewall.append(hop('c', 'C', 'A'))
        firewall.append(hop('e', 'entry', 'unrelated_sink'))
        firewall.append(hop('e2', 'entry2', 'B'))
        sink_table = GenUtils.table('sink')
        sink_rule = GenUtils.rule('sink', key='unrelated_sink')
        sink_rule.append(GenUtils.action('accept'))
        sink_table.append(sink_rule)
        firewall.append(sink_table)

        config = GenUtils.config()
        firewalls = GenUtils.firewalls()
        firewalls.append(firewall)
        config.append(firewalls)

        kripke, encoding = Instantiator.InstantiateBase(
            config, Inits=['entry', 'entry2'], default_inits=False)
        solver = PycoSATAdapter()

        # entry -> A: entry has no real connection to the cycle at all --
        # must be rejected.
        instance = Instantiator.InstantiateEndToEnd(kripke, encoding, 'entry', 'A')
        self.assertFalse(
            Instantiator.SolveGroundedEndToEnd(solver, kripke, instance, 'entry', 'A'),
            "grounded solve must reject a witness that only floats through "
            "an unreachable cycle")

        # entry -> unrelated_sink: a genuine, direct, single-hop path --
        # must still be accepted (no false positives from the grounding
        # check itself).
        instance = Instantiator.InstantiateEndToEnd(
            kripke, encoding, 'entry', 'unrelated_sink')
        self.assertTrue(
            Instantiator.SolveGroundedEndToEnd(
                solver, kripke, instance, 'entry', 'unrelated_sink'),
            "grounded solve must still accept a genuine direct path")

        # entry2 -> C: a genuine MULTI-HOP path into the cycle from a real
        # generator (entry2->B->C) -- must be accepted, proving the fix
        # isn't just "reject anything more than one hop" but specifically
        # "reject witnesses not connected to the real source".
        instance = Instantiator.InstantiateEndToEnd(kripke, encoding, 'entry2', 'C')
        self.assertTrue(
            Instantiator.SolveGroundedEndToEnd(solver, kripke, instance, 'entry2', 'C'),
            "grounded solve must accept a genuine multi-hop path from a "
            "real origin into the cycle")


    def testAcyclicRankConstraintRejectsFloatingCycleStatically(self):
        """ AD6_PLAN.md §5.4 Stage B (B1), Option 2: CEGAR's naive
        exact-witness blocking (SolveGroundedEndToEnd) turned out
        combinatorially intractable on real wl_stanford data -- a single
        genuinely-unreachable pair on a 3-router backbone slice needed ~117
        solver iterations (~45s). Its "shrink blocking to Destination's own
        backward closure" refinement (Option 1) also failed: profiling
        showed that closure spans almost the ENTIRE fired-transition set on
        real FIB-table-heavy data (long per-table fallthrough chains
        backward-connect nearly everything), so it was barely smaller than
        blocking everything.

        Option 2 fixes the root cause STATICALLY instead of reactively:
        Instantiator.InstantiateBase(..., Acyclic=True) asserts, once, for
        EVERY Kripke edge, that firing it requires the target's "rank" (a
        bounded binary distance-from-origin value, brand new variables with
        no other role in the model) to be STRICTLY greater than the
        source's. A cycle of simultaneously-true edges would then require
        Rank(A) < Rank(B) < Rank(C) < Rank(A) -- impossible in any total
        order, a hard NUMERIC contradiction. This is fundamentally
        different from (and does not repeat the failure of) negating
        _CreateCycle: that formula's escape hatch was structural (an OR
        that's trivially satisfied by any edge into a dead-end/sink, i.e.
        every real ACCEPT/DROP/probe node), whereas "greater than" has no
        such escape -- there is no value assignment under which a genuine
        cycle's chained inequalities can hold, regardless of what any other
        node's rank is.

        Because this is a property of the WHOLE base model rather than one
        query's witness, a single plain solver.Solve (no CEGAR iteration at
        all) must now correctly reject the exact same fixture used
        throughout this investigation. """
        def hop(name, key, target):
            table = GenUtils.table(name)
            rule = GenUtils.rule(name, key=key)
            rule.append(GenUtils.action('jump', target=target))
            table.append(rule)
            return table

        firewall = GenUtils.firewall('cyclefw')
        firewall.append(hop('a', 'A', 'B'))
        firewall.append(hop('b', 'B', 'C'))
        firewall.append(hop('c', 'C', 'A'))
        firewall.append(hop('e', 'entry', 'unrelated_sink'))
        firewall.append(hop('e2', 'entry2', 'B'))
        sink_table = GenUtils.table('sink')
        sink_rule = GenUtils.rule('sink', key='unrelated_sink')
        sink_rule.append(GenUtils.action('accept'))
        sink_table.append(sink_rule)
        firewall.append(sink_table)

        config = GenUtils.config()
        firewalls = GenUtils.firewalls()
        firewalls.append(firewall)
        config.append(firewalls)

        kripke, encoding = Instantiator.InstantiateBase(
            config, Inits=['entry', 'entry2'], default_inits=False, Acyclic=True)
        solver = PycoSATAdapter()

        # entry -> A: no CEGAR involved here at all -- a PLAIN solve must
        # already be UNSAT, because the floating cycle's edges can no
        # longer be simultaneously true.
        instance = Instantiator.InstantiateEndToEnd(kripke, encoding, 'entry', 'A')
        self.assertFalse(
            bool(solver.Solve(instance)),
            "the static rank constraint must make the floating cycle's "
            "edges impossible to fire all at once, so a plain solve is "
            "UNSAT for the ungrounded pair")

        # entry -> unrelated_sink: a genuine, direct, single-hop path must
        # still be plainly SAT (no false positives from the new
        # constraint).
        instance = Instantiator.InstantiateEndToEnd(
            kripke, encoding, 'entry', 'unrelated_sink')
        self.assertTrue(
            bool(solver.Solve(instance)),
            "the rank constraint must not reject a genuine direct path")

        # entry2 -> C: a genuine multi-hop path into the cycle from a real
        # origin must still be plainly SAT (proves this isn't "cycles in
        # the graph are forbidden", just "a witness can't use one").
        instance = Instantiator.InstantiateEndToEnd(kripke, encoding, 'entry2', 'C')
        self.assertTrue(
            bool(solver.Solve(instance)),
            "the rank constraint must not reject a genuine multi-hop path "
            "from a real origin into the cycle")


    def testComputeSCCsFindsOnlyGenuineCyclesNotLongAcyclicChains(self):
        """ AD6_PLAN.md §5.4 Stage B (B1), Option 2 scoping: profiling the
        unscoped rank constraint on a real 3-router wl_stanford slice found
        it applying to EVERY Kripke edge -- including the huge number of
        intra-table fallthrough edges (a FIB table's rules falling through
        one by one is a straight line, never a cycle by itself) -- made
        the encoding far bigger than necessary (425k extra clauses for just
        3 routers) and correspondingly slow to build and solve. Only edges
        with BOTH endpoints in the SAME non-trivial strongly-connected
        component (SCC) can ever be part of a real cycle -- a long acyclic
        chain (however many hops) is provably never part of one, by
        definition of what an SCC is -- so restricting the expensive
        comparator to just those edges is lossless for soundness while
        potentially cutting the encoding by orders of magnitude on real
        Stanford-shaped data (a few backbone routers cyclically
        interconnected, surrounded by a much larger number of ordinary
        acyclic per-table rule chains).

        Instantiator._ComputeSCCs(Kripke) is Kosaraju's algorithm run over
        the Kripke graph's plain adjacency (both true/false transitions are
        real graph edges for connectivity purposes; which one fired is
        irrelevant here). Fixture: a genuine 3-cycle A->B->C->A, a long
        UNRELATED acyclic chain D->E->F (six hops would make the same
        point; three is enough to prove "chain, not cycle"), and a
        single-node self-loop X->X (a degenerate but genuine 1-node cycle,
        the edge case a naive "size > 1" check would miss). """
        kripke = KripkeStructure()
        for key in ['A', 'B', 'C', 'D', 'E', 'F', 'X']:
            kripke.Put(key, KripkeNode(Props=[key], Gamma=XMLUtils.constant()))
        kripke.Put('A', ('B', True))
        kripke.Put('B', ('C', True))
        kripke.Put('C', ('A', True))
        kripke.Put('D', ('E', True))
        kripke.Put('E', ('F', True))
        kripke.Put('X', ('X', True))

        SccOf, NonTrivial = Instantiator._ComputeSCCs(kripke)

        self.assertEqual(SccOf['A'], SccOf['B'])
        self.assertEqual(SccOf['B'], SccOf['C'])
        self.assertIn(SccOf['A'], NonTrivial,
                      "a genuine 3-cycle must be recognised as non-trivial")

        self.assertIn(SccOf['X'], NonTrivial,
                      "a self-loop is a genuine (degenerate) cycle too")

        for Left, Right in [('D', 'E'), ('E', 'F'), ('D', 'F')]:
            self.assertNotEqual(
                SccOf[Left], SccOf[Right],
                "a long ACYCLIC chain must not be merged into one SCC")
        self.assertNotIn(SccOf['D'], NonTrivial)
        self.assertNotIn(SccOf['E'], NonTrivial)
        self.assertNotIn(SccOf['F'], NonTrivial)


    def testAcyclicRankConstraintScopesToNonTrivialSCCsOnly(self):
        """ Companion to testComputeSCCsFindsOnlyGenuineCyclesNotLongAcyclicChains:
        confirms _CreateAcyclicConstraints actually USES the SCC scoping --
        no rank/comparator variable should ever be generated that mentions
        a node from the acyclic D->E->F chain, while the genuine A->B->C
        cycle's nodes must still get real constraints (otherwise the whole
        point of the fix -- rejecting a floating cycle -- would be lost by
        over-aggressively scoping it away). """
        def hop(name, key, target):
            table = GenUtils.table(name)
            rule = GenUtils.rule(name, key=key)
            rule.append(GenUtils.action('jump', target=target))
            table.append(rule)
            return table

        firewall = GenUtils.firewall('sccfw')
        firewall.append(hop('a', 'A', 'B'))
        firewall.append(hop('b', 'B', 'C'))
        firewall.append(hop('c', 'C', 'A'))
        firewall.append(hop('d', 'D', 'E'))
        firewall.append(hop('e', 'E', 'F'))
        sink_table = GenUtils.table('sink')
        sink_rule = GenUtils.rule('sink', key='F')
        sink_rule.append(GenUtils.action('accept'))
        sink_table.append(sink_rule)
        firewall.append(sink_table)

        config = GenUtils.config()
        firewalls = GenUtils.firewalls()
        firewalls.append(firewall)
        config.append(firewalls)

        kripke = KripkeUtils.ConvertToKripke(config, default_inits=False)
        Constraints = Instantiator._CreateAcyclicConstraints(kripke)

        def mentions(node_key):
            for Constraint in Constraints:
                for Variable in Constraint.iter(XMLUtils.VARIABLE):
                    Name = Variable.attrib[XMLUtils.ATTRNAME]
                    if ("#%s_" % node_key) in Name or ("#%s#" % node_key) in Name:
                        return True
            return False

        for cyclic_node in ['A', 'B', 'C']:
            self.assertTrue(
                mentions(cyclic_node),
                "%s is part of a genuine cycle and must still get a rank "
                "constraint" % cyclic_node)

        for acyclic_node in ['D', 'E', 'F']:
            self.assertFalse(
                mentions(acyclic_node),
                "%s is only ever on a straight acyclic chain and must be "
                "scoped OUT of the (expensive) rank constraint entirely" %
                acyclic_node)


    def testAcyclicRankConstraintLiteMatchesGeneralEncoding(self):
        """ AD6_PLAN.md Sec 5.5 C2 NO-GO fix attempt: _CreateAcyclicConstraintsLite
        hand-emits plain-Python clauses instead of building/CNF-converting an
        lxml formula tree per edge, to avoid the ~0.14-0.18 MB/edge retained-memory
        cost that OOMs on wl_i2 at full scale (confirmed genuine, not reclaimable
        garbage -- see memory 'ad6-wl-i2-c2-nogo-oom'). That's only safe if it
        produces the EXACT SAME clause set as _CreateAcyclicConstraints, not merely
        "a plausible-looking one" -- this test is the thing that actually establishes
        that, by canonicalizing both outputs into (name, negated)-literal frozensets
        and comparing the resulting clause sets for exact equality, on the same
        genuine-cycle-plus-acyclic-chain fixture
        testAcyclicRankConstraintScopesToNonTrivialSCCsOnly already uses. """
        def hop(name, key, target):
            table = GenUtils.table(name)
            rule = GenUtils.rule(name, key=key)
            rule.append(GenUtils.action('jump', target=target))
            table.append(rule)
            return table

        firewall = GenUtils.firewall('sccfw')
        firewall.append(hop('a', 'A', 'B'))
        firewall.append(hop('b', 'B', 'C'))
        firewall.append(hop('c', 'C', 'A'))
        firewall.append(hop('d', 'D', 'E'))
        firewall.append(hop('e', 'E', 'F'))
        sink_table = GenUtils.table('sink')
        sink_rule = GenUtils.rule('sink', key='F')
        sink_rule.append(GenUtils.action('accept'))
        sink_table.append(sink_rule)
        firewall.append(sink_table)

        config = GenUtils.config()
        firewalls = GenUtils.firewalls()
        firewalls.append(firewall)
        config.append(firewalls)

        kripke = KripkeUtils.ConvertToKripke(config, default_inits=False)

        General = Instantiator._CreateAcyclicConstraints(kripke)
        Lite = Instantiator._CreateAcyclicConstraintsLite(kripke)

        def canonicalize_general(Constraints):
            ClauseSet = set()
            for Constraint in Constraints:
                Literals = [Constraint] if Constraint.tag == XMLUtils.VARIABLE \
                    else list(Constraint.iter(XMLUtils.VARIABLE))
                ClauseSet.add(frozenset(
                    (Variable.attrib[XMLUtils.ATTRNAME], Variable.attrib[XMLUtils.ATTRNEGATED] == 'true')
                    for Variable in Literals))
            return ClauseSet

        def canonicalize_lite(Constraints):
            return set(frozenset(Clause) for Clause in Constraints)

        GeneralClauses = canonicalize_general(General)
        LiteClauses = canonicalize_lite(Lite)

        self.assertEqual(len(General), len(GeneralClauses),
                          "sanity check on the fixture: no accidental duplicate clauses "
                          "in the general encoding's own output")
        self.assertEqual(len(Lite), len(LiteClauses),
                          "sanity check on the fixture: no accidental duplicate clauses "
                          "in the lite encoding's own output")
        self.assertEqual(GeneralClauses, LiteClauses,
                          "_CreateAcyclicConstraintsLite must produce the IDENTICAL clause "
                          "set as _CreateAcyclicConstraints -- any difference here is a "
                          "potential soundness regression, not just a performance one")


    def testSolveAcyclicEndToEndTakesFastPathWhenAlreadyGrounded(self):
        """ AD6_PLAN.md §5.4 Stage B (B1), Option 2's lazy/hybrid
        refinement: baking the (expensive, SCC-scoped) rank constraints
        into the SHARED base model made every query pay for them, even
        queries whose witness is already grounded on a plain solve --
        profiling showed genuinely-reachable pairs on the real 3-router
        slice cost ~6s each once the constraints were present, vs ~0.3s
        with nothing added at all. Most real queries (any pair whose
        destination has NO real connection at all to an ungrounded cycle)
        never need the rank machinery, so Instantiator.SolveAcyclicEndToEnd
        tries a PLAIN solve + cheap grounding check first, and only
        escalates to the rank constraints if THAT witness turns out
        ungrounded.

        Fixture: the same `entry -> unrelated_sink` pair used throughout
        this investigation -- a genuine, direct, one-hop path with no
        cycle anywhere near it. Passing an (initially empty) Cache dict and
        asserting it is STILL EMPTY afterward is the proof that
        _CreateAcyclicConstraints was never even invoked. """
        def hop(name, key, target):
            table = GenUtils.table(name)
            rule = GenUtils.rule(name, key=key)
            rule.append(GenUtils.action('jump', target=target))
            table.append(rule)
            return table

        firewall = GenUtils.firewall('cyclefw')
        firewall.append(hop('a', 'A', 'B'))
        firewall.append(hop('b', 'B', 'C'))
        firewall.append(hop('c', 'C', 'A'))
        firewall.append(hop('e', 'entry', 'unrelated_sink'))
        sink_table = GenUtils.table('sink')
        sink_rule = GenUtils.rule('sink', key='unrelated_sink')
        sink_rule.append(GenUtils.action('accept'))
        sink_table.append(sink_rule)
        firewall.append(sink_table)

        config = GenUtils.config()
        firewalls = GenUtils.firewalls()
        firewalls.append(firewall)
        config.append(firewalls)

        kripke, encoding = Instantiator.InstantiateBase(
            config, Inits=['entry'], default_inits=False)
        solver = PycoSATAdapter()

        Cache = {}
        instance = Instantiator.InstantiateEndToEnd(kripke, encoding, 'entry', 'unrelated_sink')
        self.assertTrue(
            Instantiator.SolveAcyclicEndToEnd(
                solver, kripke, instance, 'entry', 'unrelated_sink', Cache=Cache))
        self.assertEqual(
            Cache, {},
            "a genuinely direct, already-grounded witness must never "
            "trigger building the (expensive) rank constraints at all")


    def testSolveAcyclicEndToEndEscalatesOnlyOnceAndCachesAcrossQueries(self):
        """ Companion to testSolveAcyclicEndToEndTakesFastPathWhenAlreadyGrounded:
        when a query's PLAIN solve IS ungrounded (the same known
        floating-cycle bug this whole investigation is about),
        SolveAcyclicEndToEnd must still resolve it correctly by escalating
        to the SCC-scoped rank constraints -- but build them only ONCE per
        Cache and reuse the SAME built list for every subsequent escalated
        query in the run, rather than rebuilding per query (which is
        exactly the cost the lazy design exists to amortise across a whole
        benchmark's query set). Verified by identity (the cached object
        must be the literal SAME list after a second escalated call, not a
        fresh rebuild) rather than by instrumenting/mocking, since identity
        is a direct, unambiguous observation. """
        def hop(name, key, target):
            table = GenUtils.table(name)
            rule = GenUtils.rule(name, key=key)
            rule.append(GenUtils.action('jump', target=target))
            table.append(rule)
            return table

        firewall = GenUtils.firewall('cyclefw')
        firewall.append(hop('a', 'A', 'B'))
        firewall.append(hop('b', 'B', 'C'))
        firewall.append(hop('c', 'C', 'A'))
        firewall.append(hop('e', 'entry', 'unrelated_sink'))
        sink_table = GenUtils.table('sink')
        sink_rule = GenUtils.rule('sink', key='unrelated_sink')
        sink_rule.append(GenUtils.action('accept'))
        sink_table.append(sink_rule)
        firewall.append(sink_table)

        config = GenUtils.config()
        firewalls = GenUtils.firewalls()
        firewalls.append(firewall)
        config.append(firewalls)

        kripke, encoding = Instantiator.InstantiateBase(
            config, Inits=['entry'], default_inits=False)
        solver = PycoSATAdapter()
        Cache = {}

        # First escalated query: entry -> A. Must still be correctly
        # rejected (False), same as SolveGroundedEndToEnd's own fix, and
        # must populate the cache.
        instance = Instantiator.InstantiateEndToEnd(kripke, encoding, 'entry', 'A')
        self.assertFalse(
            Instantiator.SolveAcyclicEndToEnd(
                solver, kripke, instance, 'entry', 'A', Cache=Cache))
        self.assertIn('AcyclicConstraints', Cache)
        Built = Cache['AcyclicConstraints']

        # Second escalated query: entry -> B (same underlying floating
        # cycle, also rejected). The cache's built constraints must be
        # REUSED (same object), not rebuilt.
        instance = Instantiator.InstantiateEndToEnd(kripke, encoding, 'entry', 'B')
        self.assertFalse(
            Instantiator.SolveAcyclicEndToEnd(
                solver, kripke, instance, 'entry', 'B', Cache=Cache))
        self.assertIs(
            Cache['AcyclicConstraints'], Built,
            "the rank constraints must be built once and reused across "
            "every subsequent escalated query in the same run, not "
            "rebuilt per query")


    def testSolveAcyclicEndToEndReportsEscalationPerQueryViaStats(self):
        """ AD6_PLAN.md §5.4 Stage B (B1): a caller driving many queries
        (fave_bridge.py's per-query loop) needs to know, PER QUERY, whether
        THIS specific call actually took the fast path or had to escalate
        -- e.g. to log progress on a long run. Merely checking
        'AcyclicConstraints' in Cache after the call is NOT enough once the
        cache is already warm from an earlier query: it stays present
        (correctly reused) even for a LATER query that itself took the
        fast path, so that alone can't distinguish "this query escalated"
        from "some earlier query escalated". `Stats` (an optional dict,
        None by default so existing callers/tests are unaffected) is
        SolveAcyclicEndToEnd's own direct report of what THIS call did. """
        def hop(name, key, target):
            table = GenUtils.table(name)
            rule = GenUtils.rule(name, key=key)
            rule.append(GenUtils.action('jump', target=target))
            table.append(rule)
            return table

        firewall = GenUtils.firewall('cyclefw')
        firewall.append(hop('a', 'A', 'B'))
        firewall.append(hop('b', 'B', 'C'))
        firewall.append(hop('c', 'C', 'A'))
        firewall.append(hop('e', 'entry', 'unrelated_sink'))
        sink_table = GenUtils.table('sink')
        sink_rule = GenUtils.rule('sink', key='unrelated_sink')
        sink_rule.append(GenUtils.action('accept'))
        sink_table.append(sink_rule)
        firewall.append(sink_table)

        config = GenUtils.config()
        firewalls = GenUtils.firewalls()
        firewalls.append(firewall)
        config.append(firewalls)

        kripke, encoding = Instantiator.InstantiateBase(
            config, Inits=['entry'], default_inits=False)
        solver = PycoSATAdapter()
        Cache = {}

        # entry -> unrelated_sink: already grounded on a plain solve --
        # Stats must report no escalation.
        Stats = {}
        instance = Instantiator.InstantiateEndToEnd(kripke, encoding, 'entry', 'unrelated_sink')
        Instantiator.SolveAcyclicEndToEnd(
            solver, kripke, instance, 'entry', 'unrelated_sink', Cache=Cache, Stats=Stats)
        self.assertFalse(Stats['Escalated'])

        # entry -> A: ungrounded on a plain solve -- Stats must report
        # escalation, and the cache is now warm.
        Stats = {}
        instance = Instantiator.InstantiateEndToEnd(kripke, encoding, 'entry', 'A')
        Instantiator.SolveAcyclicEndToEnd(
            solver, kripke, instance, 'entry', 'A', Cache=Cache, Stats=Stats)
        self.assertTrue(Stats['Escalated'])

        # entry -> unrelated_sink again, cache now warm from the previous
        # query: this query STILL takes the fast path itself (it never
        # needed the rank constraints), so Stats must report False even
        # though Cache already has 'AcyclicConstraints' -- the exact
        # distinction a bare cache-membership check can't make.
        Stats = {}
        instance = Instantiator.InstantiateEndToEnd(kripke, encoding, 'entry', 'unrelated_sink')
        Instantiator.SolveAcyclicEndToEnd(
            solver, kripke, instance, 'entry', 'unrelated_sink', Cache=Cache, Stats=Stats)
        self.assertFalse(Stats['Escalated'])


    def testRunWithBigStackIsATransparentWrapper(self):
        """ AD6_PLAN.md §5.4 Stage B, B1's "third item" / AD6_ENCODING_PLAN.md
        §3.10: `src.bigstack.run_with_big_stack` runs a callable in a new
        thread with a large explicit stack, so `main.py`/`fave_bridge.py`'s
        deep XML-tree-recursive operations (e.g. Instantiator.
        SolveAcyclicEndToEnd's escalation path -- confirmed to silently
        segfault on a real ~450k-clause wl_stanford instance under the
        shell's default 8MB `ulimit -s`, see AD6_ENCODING_PLAN.md §3.10)
        can't blow the OS stack regardless of the launching shell's own
        ulimit. That real crash isn't reproducible here as a fast,
        deterministic unit test (calibrated attempts at a minimal
        synthetic cyclic topology large enough to reproduce it did not
        finish in reasonable time -- CEGAR's own cost dominates before the
        stack does, at any scale small enough to stay a fast unit test);
        the fix's justification is the real A/B-tested Stanford run
        itself (crashes under the default ulimit, succeeds under
        `ulimit -s unlimited`, both runs otherwise identical). What IS
        unit-testable, and matters just as much for a change on this
        entry-point call path: that the wrapper is behavior-preserving --
        same return value, same raised exception -- for the ordinary,
        non-crashing case every existing benchmark already exercises. """
        from src.bigstack import run_with_big_stack

        def returns_a_value(x, y=None):
            return (x, y)

        self.assertEqual(run_with_big_stack(returns_a_value, 1, y=2), (1, 2))

        class _MarkerError(Exception):
            pass

        def raises():
            raise _MarkerError("propagated across the thread boundary")

        with self.assertRaises(_MarkerError):
            run_with_big_stack(raises)


def main():
    unittest.main()


if __name__ == '__main__':
    main()


class FlowPathConstraintTest(unittest.TestCase):
    """ AD6_PLAN.md §5.4 B1 / §5.5: `Instantiator._CreateFlowPathConstraints`,
    the single-unit s-t FLOW alternative to the rank encoding for closing the
    SECRYPT'15 grounding gap (ad6/FAVE_CHANGES.md §20).

    Deliberately uses the SAME fixture the rank encoding is proven on
    (`testAcyclicRankConstraintRejectsFloatingCycleStatically`), so the two
    mechanisms are held to identical ground truth: the ungrounded pair must be
    refused, and both genuine paths -- including the one that legitimately ends
    INSIDE the cycle -- must still be accepted. That last case is what
    separates "a witness may not USE a cycle" from "cycles in the graph are
    forbidden"; an encoding that failed it would be sound and useless.

    The fixture is also exactly the minimal counterexample recorded in §20:
    `entry -> unrelated_sink` is the dead-end out-edge that discharges the
    query's source-side conjunct, while `A` sits in a self-supporting cycle
    that discharges the destination-side conjunct, with no path between them.
    """

    @staticmethod
    def _fixture():
        def hop(name, key, target):
            table = GenUtils.table(name)
            rule = GenUtils.rule(name, key=key)
            rule.append(GenUtils.action('jump', target=target))
            table.append(rule)
            return table

        firewall = GenUtils.firewall('flowfw')
        firewall.append(hop('a', 'A', 'B'))
        firewall.append(hop('b', 'B', 'C'))
        firewall.append(hop('c', 'C', 'A'))
        firewall.append(hop('e', 'entry', 'unrelated_sink'))
        firewall.append(hop('e2', 'entry2', 'B'))
        sink_table = GenUtils.table('sink')
        sink_rule = GenUtils.rule('sink', key='unrelated_sink')
        sink_rule.append(GenUtils.action('accept'))
        sink_table.append(sink_rule)
        firewall.append(sink_table)

        config = GenUtils.config()
        firewalls = GenUtils.firewalls()
        firewalls.append(firewall)
        config.append(firewalls)
        return config

    def _solve(self, source, destination, with_flow=True):
        """ Base encoding with Acyclic=False (so the rank constraints are NOT
        doing the work), converted to DIMACS, then the flow clauses resolved
        against the same variable table and appended -- mirroring how
        `bench/ad6_i2_measure.py` merges `_CreateAcyclicConstraintsLite`. """
        config = self._fixture()
        kripke, encoding = Instantiator.InstantiateBase(
            config, Inits=['entry', 'entry2'], default_inits=False, Acyclic=False)
        instance = Instantiator.InstantiateEndToEnd(
            kripke, encoding, source, destination)

        adapter = MiniSATAdapter()
        variables, dimacs = adapter._ConvertToDIMACS(instance)
        name_to_index = {name: i + 1 for i, name in enumerate(variables)}
        nxt = [len(variables) + 1]

        def index_for(name):
            idx = name_to_index.get(name)
            if idx is None:
                idx = nxt[0]
                name_to_index[name] = idx
                nxt[0] += 1
            return idx

        if with_flow:
            for clause in Instantiator._CreateFlowPathConstraints(
                    kripke, source, destination):
                dimacs.append([
                    -index_for(n) if neg else index_for(n) for n, neg in clause])

        import pycosat
        return pycosat.solve(dimacs) != "UNSAT"

    # --- the gap the flow constraint exists to close ------------------------

    def test_the_ungrounded_pair_is_refused(self):
        """ THE regression. `entry` reaches only `unrelated_sink`; `A` is fed
        by the self-supporting cycle A->B->C->A. Without a grounding
        constraint this is SAT (see the companion test below), which is
        precisely the SECRYPT'15 formalism's gap. """
        self.assertFalse(
            self._solve('entry', 'A'),
            "no unit of flow can reach A from entry -- the cycle cannot "
            "manufacture one, because a cycle node's in-flow requires "
            "out-flow and at-most-one forbids it absorbing a second unit")

    def test_without_the_flow_constraint_the_same_pair_is_satisfiable(self):
        """ Proves the test above measures the FLOW constraint and not some
        other part of the encoding: identical fixture, identical query,
        Acyclic=False, flow clauses omitted -> SAT via the floating cycle. """
        self.assertTrue(
            self._solve('entry', 'A', with_flow=False),
            "without any grounding constraint the floating cycle satisfies "
            "the query -- this is the published formalism's own behaviour")

    def test_a_genuine_direct_path_is_accepted(self):
        self.assertTrue(
            self._solve('entry', 'unrelated_sink'),
            "a real one-hop path must carry the unit")

    def test_a_genuine_path_ending_inside_the_cycle_is_accepted(self):
        """ Separates "a witness may not USE a cycle" from "cycles are
        forbidden". entry2 -> B is real, and B is a cycle member. """
        self.assertTrue(
            self._solve('entry2', 'C'),
            "a genuine multi-hop path from a real origin INTO the cycle must "
            "still be accepted")

    # --- structure ----------------------------------------------------------

    def test_source_equals_destination_is_a_noop(self):
        config = self._fixture()
        kripke, _enc = Instantiator.InstantiateBase(
            config, Inits=['entry'], default_inits=False, Acyclic=False)
        self.assertEqual(
            Instantiator._CreateFlowPathConstraints(kripke, 'A', 'A'), [],
            "degenerate: 'emits one and accepts none' plus 'accepts one and "
            "emits none' would be contradictory, so this must not be emitted")

    def test_an_endpoint_with_no_usable_edge_is_an_empty_clause(self):
        """ `unrelated_sink` has no outgoing edges, so it can never emit the
        unit. Reported as an empty clause (immediate UNSAT) rather than an
        exception, so the caller's solve refutes it like any other pair. """
        config = self._fixture()
        kripke, _enc = Instantiator.InstantiateBase(
            config, Inits=['entry'], default_inits=False, Acyclic=False)
        self.assertEqual(
            Instantiator._CreateFlowPathConstraints(kripke, 'unrelated_sink', 'A'),
            [()])

    def test_every_flow_edge_implies_its_transition(self):
        config = self._fixture()
        kripke, _enc = Instantiator.InstantiateBase(
            config, Inits=['entry'], default_inits=False, Acyclic=False)
        clauses = Instantiator._CreateFlowPathConstraints(kripke, 'entry', 'A')
        # The f_e -> InAux/OutAux clauses have the same 2-literal shape, so
        # the conclusion must be screened for being a flow variable at all.
        gates = [c for c in clauses
                 if len(c) == 2 and c[0][0].startswith(Instantiator.FLOWEDGEPREFIX)
                 and c[0][1] and not c[1][1]
                 and not c[1][0].startswith(Instantiator.FLOWINPREFIX)
                 and not c[1][0].startswith(Instantiator.FLOWOUTPREFIX)]
        self.assertTrue(gates, "expected f_e -> y_e gate clauses")
        for (flow, _neg), (trans, _n2) in gates:
            self.assertEqual(flow[len(Instantiator.FLOWEDGEPREFIX):], trans,
                             "the gate must name the edge's OWN transition")

    # --- the at-most-one helper --------------------------------------------

    def test_at_most_one_is_pairwise_for_small_sets(self):
        clauses = Instantiator._AtMostOneClauses(['a', 'b', 'c'], 'aux#')
        self.assertEqual(len(clauses), 3)
        self.assertFalse(any('aux#' in n for c in clauses for n, _ in c),
                         "small sets must not introduce auxiliaries")

    def test_at_most_one_switches_to_sequential_when_wide(self):
        """ wl_i2 has probe aggregates with 18-36 attachments; pairwise would
        be quadratic exactly where the graph is widest. """
        names = ['x%d' % i for i in range(10)]
        clauses = Instantiator._AtMostOneClauses(names, 'aux#')
        self.assertTrue(any('aux#' in n for c in clauses for n, _ in c))
        self.assertLess(len(clauses), 10 * 9 // 2,
                        "sequential must beat pairwise at this width")

    def test_at_most_one_actually_forbids_two(self):
        import pycosat
        names = ['x%d' % i for i in range(8)]
        idx = {n: i + 1 for i, n in enumerate(names)}
        nxt = [len(names) + 1]

        def index_for(n):
            if n not in idx:
                idx[n] = nxt[0]
                nxt[0] += 1
            return idx[n]

        clauses = [[-index_for(n) if neg else index_for(n) for n, neg in c]
                   for c in Instantiator._AtMostOneClauses(names, 'aux#')]
        self.assertNotEqual(pycosat.solve(clauses + [[idx['x0']]]), "UNSAT",
                            "one must be allowed")
        self.assertEqual(pycosat.solve(clauses + [[idx['x0']], [idx['x5']]]),
                         "UNSAT", "two must be forbidden")

    def test_at_most_one_of_zero_or_one_is_vacuous(self):
        self.assertEqual(Instantiator._AtMostOneClauses([], 'aux#'), [])
        self.assertEqual(Instantiator._AtMostOneClauses(['a'], 'aux#'), [])


class IncrementalSessionGroundingTest(unittest.TestCase):
    """ AD6_PLAN.md §5.4 B1 / §5.5: `IncrementalSession`'s grounding selector
    -- the PRODUCTION path's choice between the two constraints that close the
    SECRYPT'15 formalism's grounding gap (ad6/FAVE_CHANGES.md §20).

    Before this, the single-unit s-t flow existed ONLY in the two measurement
    drivers (`bench/ad6_i2_measure.py --flow-path`,
    `bench/ad6_faithful_measure.py --flow-path`), which sit off the production
    path by design -- so nothing driven through FaVe could use it and the
    approach was one cleanup away from being lost. These tests hold both
    strategies to the SAME ground truth on the SAME fixture the rank encoding
    and the raw flow constraint are each already proven on
    (`FlowPathConstraintTest._fixture`), so "the production session can now
    pick either" is a checked claim rather than a plumbing assertion. """

    @staticmethod
    def _session(grounding, inits=('entry', 'entry2')):
        config = FlowPathConstraintTest._fixture()
        # Acyclic=False: the base carries NO rank constraints, so whichever
        # grounding the session applies is doing the work on its own.
        kripke, encoding = Instantiator.InstantiateBase(
            config, Inits=list(inits), default_inits=False, Acyclic=False)
        return IncrementalSession(kripke, encoding, grounding=grounding)

    def _answer(self, grounding, source, destination):
        session = self._session(grounding)
        try:
            return session.Query(source, destination)
        finally:
            session.Close()

    # --- the gap, through the production session ---------------------------

    def test_flow_grounding_refuses_the_ungrounded_pair(self):
        """ THE new regression. `entry` reaches only `unrelated_sink`; `A` is
        fed by the self-supporting cycle A->B->C->A. The flow grounding must
        refuse it through `IncrementalSession`, not merely when a bench driver
        merges the clauses by hand. """
        self.assertFalse(
            self._answer(GROUNDING_FLOW, 'entry', 'A'),
            "no unit of flow can reach A from entry -- the floating cycle "
            "cannot manufacture one")

    def test_rank_grounding_refuses_the_ungrounded_pair(self):
        """ The same pair under the default strategy: identical ground truth,
        which is what makes the two interchangeable for reachability. """
        self.assertFalse(
            self._answer(GROUNDING_RANK, 'entry', 'A'),
            "the rank encoding's numeric contradiction must refuse the same "
            "floating cycle")

    def test_both_groundings_agree_on_every_pair_of_the_fixture(self):
        """ Not just the headline pair: the fixture's genuine paths must stay
        accepted under both -- including `entry2 -> C`, which legitimately
        ENDS INSIDE the cycle and separates "a witness may not use a cycle"
        from "cycles are forbidden". """
        expected = {
            ('entry', 'A'): False,             # ungrounded: the gap itself
            ('entry', 'unrelated_sink'): True,  # a real one-hop path
            ('entry2', 'B'): True,              # real, into the cycle
            ('entry2', 'C'): True,              # real, through the cycle
        }
        for (source, destination), want in expected.items():
            for grounding in (GROUNDING_RANK, GROUNDING_FLOW):
                self.assertEqual(
                    self._answer(grounding, source, destination), want,
                    "%s -> %s under grounding=%r" % (
                        source, destination, grounding))

    # --- the architectural hazard the flow strategy has to handle ----------

    def test_flow_grounding_does_not_leak_between_queries(self):
        """ THE reason `--flow-path` requires `--fresh-per-query`, asserted on
        the session rather than left to a CLI check: the flow constraint names
        its own endpoints, so a REUSED solver would still be asserting query
        1's flow during query 2. Ask a satisfiable pair first, then the
        ungrounded one on the SAME session -- if the first query's constraints
        survived, the second's answer would be wrong. """
        session = self._session(GROUNDING_FLOW)
        try:
            self.assertTrue(session.Query('entry2', 'C'),
                            "a genuine path must be accepted")
            self.assertFalse(
                session.Query('entry', 'A'),
                "the ungrounded pair must still be refused after an unrelated "
                "query -- a leaked flow constraint would corrupt this")
            self.assertTrue(
                session.Query('entry', 'unrelated_sink'),
                "and a genuine path must still be accepted after a refutation")
        finally:
            session.Close()

    def test_flow_grounding_refutes_an_endpoint_with_no_usable_edge(self):
        """ `_CreateFlowPathConstraints` reports "this endpoint can never emit
        the unit" as a single EMPTY clause. The session must turn that into an
        ordinary False instead of handing an empty clause to the solver. """
        self.assertFalse(
            self._answer(GROUNDING_FLOW, 'unrelated_sink', 'A'),
            "unrelated_sink has no outgoing edge, so it can emit no unit")

    # --- the contract -------------------------------------------------------

    def test_the_default_grounding_is_rank(self):
        """ Back-compatibility, and deliberate: 'rank' is property-agnostic
        while the flow is reachability-specific, and every archived
        wl_ifi/wl_up/wl_tum/wl_stanford result was produced under it. """
        config = FlowPathConstraintTest._fixture()
        kripke, encoding = Instantiator.InstantiateBase(
            config, Inits=['entry', 'entry2'], default_inits=False,
            Acyclic=False)
        session = IncrementalSession(kripke, encoding)   # no grounding argument
        try:
            self.assertEqual(session.grounding, GROUNDING_RANK)
            self.assertFalse(
                session.Query('entry', 'A'),
                "and the default must actually ground a witness, not just "
                "carry the right label")
        finally:
            session.Close()

    def test_an_unknown_grounding_is_refused(self):
        """ A typo must fail loudly at construction -- silently falling back to
        a default would mis-stamp whatever measurement followed. """
        config = FlowPathConstraintTest._fixture()
        kripke, encoding = Instantiator.InstantiateBase(
            config, Inits=['entry'], default_inits=False, Acyclic=False)
        with self.assertRaises(ValueError):
            IncrementalSession(kripke, encoding, grounding='acyclic')

    def test_close_is_safe_under_the_flow_grounding(self):
        """ The flow strategy holds no persistent solver; Close must be a
        no-op there rather than an AttributeError, and stay idempotent. """
        session = self._session(GROUNDING_FLOW)
        session.Close()
        session.Close()


class RuleOrderSemanticsTest(unittest.TestCase):
    """ AD6_PLAN.md §9, Phase 0.1 -- the question that GATES the adapter
    rewrite's design, pinned as a test rather than left as an assumption.

    The adapter rewrite (§9.1) replaces semantic reconstruction with a
    STRUCTURAL translation: each FaVe rule becomes an ad6 rule at FaVe's own
    `idx` position. That is only sound if ad6 evaluates a table's rules
    first-match-wins in DOCUMENT ORDER, computing genuine RESIDUALS -- a later
    rule stays reachable on whatever packet space the earlier rules did not
    already claim.

    Why it is load-bearing rather than a nicety (§9.2a): FaVe's
    `iptables/generator.py:_interweave_state_shell` STRIPS the conntrack
    matches and re-emits the derived ESTABLISHED rules as ordinary stateless
    rules carrying a plain `related` header field. The stateful semantics
    therefore survive PURELY AS RULE POSITION. If ad6's ordering were
    approximate, every interwoven ruleset would be silently mis-modelled --
    and it would look fine on wl_ifi, whose ACLs are state-blind.

    `ad6/src/core/kripke.py:_HandleTable` enumerates a table's rules in
    document order; these tests pin the SEMANTICS that ordering produces. """

    @staticmethod
    def _config(order):
        """ One table whose rules all jump to a distinct target, so "was this
        rule reached" is answerable as plain reachability of its target. `dst`
        None means a rule with no condition at all. """
        firewall = GenUtils.firewall('ofw')
        table = GenUtils.table('t0')
        for pos, (suffix, dst) in enumerate(order):
            rule = GenUtils.rule(str(pos), key='ofw_t_r%d' % pos)
            if dst is not None:
                rule.append(GenUtils.address(dst, direction='dst', version='4'))
            rule.append(GenUtils.action('jump', target='ofw_t_r_%s' % suffix))
            table.append(rule)
        firewall.append(table)

        for suffix, _ in order:
            target_table = GenUtils.table('t_%s' % suffix)
            target = GenUtils.rule(suffix, key='ofw_t_r_%s' % suffix)
            target.append(GenUtils.action('accept'))
            target_table.append(target)
            firewall.append(target_table)

        config = GenUtils.config()
        firewalls = GenUtils.firewalls()
        firewalls.append(firewall)
        config.append(firewalls)
        return config

    def _reached(self, order):
        """ {suffix: bool} -- which of the ordered rules can be reached at all,
        entering the table at position 0. """
        config = RuleOrderSemanticsTest._config(order)
        kripke, encoding = Instantiator.InstantiateBase(
            config, Inits=['ofw_t_r0'], default_inits=False)
        solver = PycoSATAdapter()
        return {
            suffix: bool(solver.Solve(Instantiator.InstantiateReach(
                kripke, encoding, 'ofw_t_r_%s' % suffix)))
            for suffix, _ in order}

    _DST = '10.0.0.1/32'

    def testAnIdenticallyMatchingLaterRuleIsShadowed(self):
        """ The discriminator. Two rules over the IDENTICAL packet space: under
        first-match-wins only the first is reachable. If ad6 treated a table's
        rules as independent entry points instead, BOTH would come back
        reachable and §9's structural translation would be unsound. """
        reached = self._reached([('A', self._DST), ('B', self._DST)])
        self.assertTrue(reached['A'], "the first of two identical rules must be reachable")
        self.assertFalse(reached['B'],
                         "a rule fully shadowed by an identical earlier rule must be "
                         "UNREACHABLE -- ad6 is not first-match-wins, and §9's "
                         "position-preserving translation cannot be sound")

    def testSwappingTheOrderSwapsTheVerdict(self):
        """ The control for the test above: the asymmetry must come from
        POSITION, not from anything about the rules themselves. """
        reached = self._reached([('B', self._DST), ('A', self._DST)])
        self.assertTrue(reached['B'])
        self.assertFalse(reached['A'])

    def testDisjointRulesAreBothReachable(self):
        """ Shadowing must be about overlap, not about mere precedence --
        otherwise every rule after the first would be dead. """
        reached = self._reached([('A', '10.0.0.1/32'), ('B', '10.0.0.2/32')])
        self.assertTrue(reached['A'])
        self.assertTrue(reached['B'])

    def testAWiderLaterRuleStaysReachableOnItsResidual(self):
        """ The property LPM ordering actually depends on: a /8 placed AFTER a
        /24 it contains is still reachable, on the part of the /8 the /24 did
        not claim. A model that shadowed wholesale on any overlap would make
        every less-specific route dead and silently re-introduce the LPM class
        of bug (ad6/FAVE_CHANGES.md §14). """
        reached = self._reached([('A', '10.0.0.0/24'), ('B', '10.0.0.0/8')])
        self.assertTrue(reached['A'])
        self.assertTrue(reached['B'],
                        "a wider later rule must stay reachable on its residual")

    def testANarrowerLaterRuleIsShadowedByAWiderEarlierOne(self):
        """ The converse: a /24 placed after the /8 containing it has no
        residual left and is dead. This is the shape `_reprioritise_fib_lpm`
        exists to prevent in the FIB. """
        reached = self._reached([('A', '10.0.0.0/8'), ('B', '10.0.0.0/24')])
        self.assertTrue(reached['A'])
        self.assertFalse(reached['B'])

    def testAMatchAllEarlierRuleShadowsEverythingAfterIt(self):
        """ Both spellings of "any": the explicit /0 FaVe emits for an `any`
        match, and a rule carrying no condition element at all. Pinned
        together because `favemodel._is_constrained` treats /0 as unconstrained
        and drops the element, so the two must not diverge. """
        for label, first in (("explicit /0", '0.0.0.0/0'), ("no condition", None)):
            reached = self._reached([('A', first), ('B', self._DST)])
            self.assertTrue(reached['A'], label)
            self.assertFalse(reached['B'],
                             "%s: nothing after a match-all rule can be reached" % label)


class TerminalConditionTest(unittest.TestCase):
    """ AD6_PLAN.md §9.9.1: a rule's own condition gates its OUTGOING edges, so
    a rule with NO outgoing edge has its condition enforced by NOTHING.

    `_ConvertNodesToImplications` makes a node's proposition follow from its
    INCOMING transitions, and a transition carries the condition of the node it
    LEAVES. Asking whether a terminal rule's node is reachable therefore asks
    only whether a packet ARRIVED there -- never whether it satisfied that
    rule's own match.

    This is not a defect to fix; it is what "reachable" means here, and the
    encoding is consistent about it. It is pinned because it is INVISIBLE and
    the failure it causes is silent over-approximation -- the direction a
    soundness error must never go. It was found the hard way while translating
    FaVe probes (§9.9): a probe demanding a destination the network could not
    deliver came back REACHABLE.

    Two existing pieces of this codebase are explained by it. It is why
    `favemodel.probe_vlan_literals` forces a probe's declared VLAN as explicit
    per-bit literals onto the QUERY instance rather than relying on the probe
    node's own condition. And it is why `fave/ad6/translate.py`'s
    `probe_device` currently carries no match at all: a filtering condition
    placed on a terminal rule would be silently ignored, so filtering must
    instead put the condition on a real transition -- see that function for
    what adding it would require. """

    @staticmethod
    def _config(terminal_jumps_onward):
        """ entry (dst 10/8) -> terminal (dst 192.168/16, DISJOINT), optionally
        continuing to a third node. The two conditions cannot hold together, so
        anything downstream of the terminal rule must be unreachable. """
        firewall = GenUtils.firewall('tfw')

        table = GenUtils.table('t0')
        entry = GenUtils.rule('0', key='tfw_t_r0')
        entry.append(GenUtils.address('10.0.0.0/8', direction='dst', version='4'))
        entry.append(GenUtils.action('jump', target='tfw_t_terminal'))
        table.append(entry)
        firewall.append(table)

        terminal_table = GenUtils.table('t_term')
        terminal = GenUtils.rule('term', key='tfw_t_terminal')
        terminal.append(GenUtils.address('192.168.0.0/16', direction='dst', version='4'))
        if terminal_jumps_onward:
            terminal.append(GenUtils.action('jump', target='tfw_t_after'))
        else:
            terminal.append(GenUtils.action('accept'))
        terminal_table.append(terminal)
        firewall.append(terminal_table)

        after_table = GenUtils.table('t_after')
        after = GenUtils.rule('after', key='tfw_t_after')
        after.append(GenUtils.action('accept'))
        after_table.append(after)
        firewall.append(after_table)

        config = GenUtils.config()
        firewalls = GenUtils.firewalls()
        firewalls.append(firewall)
        config.append(firewalls)
        return config

    def _reaches(self, config, node):
        kripke, encoding = Instantiator.InstantiateBase(
            config, Inits=['tfw_t_r0'], default_inits=False)
        return bool(PycoSATAdapter().Solve(
            Instantiator.InstantiateReach(kripke, encoding, node)))

    def testATerminalRulesOwnConditionIsNotEnforced(self):
        """ The finding itself. `tfw_t_terminal` demands dst 192.168/16 and is
        only reachable through a rule demanding dst 10/8 -- contradictory -- yet
        it comes back REACHABLE, because nothing ever evaluates its condition. """
        self.assertTrue(
            self._reaches(self._config(terminal_jumps_onward=False),
                          'tfw_t_terminal'),
            "if this ever starts failing, ad6 has begun enforcing a terminal "
            "rule's own condition -- a real semantic change, and probe "
            "filtering could then be expressed directly (see translate.py's "
            "probe_device)")

    def testTheSameConditionISEnforcedOnceTheRuleHasAnOutgoingEdge(self):
        """ The other half, and the fix it implies: give the rule an outgoing
        edge and its condition lands on a real transition, so the contradiction
        bites and whatever follows is correctly UNREACHABLE. """
        config = self._config(terminal_jumps_onward=True)
        self.assertFalse(
            self._reaches(config, 'tfw_t_after'),
            "no packet matches both 10.0.0.0/8 and 192.168.0.0/16, so nothing "
            "downstream of the terminal rule may be reachable")

    def testTheContradictionIsGenuineAndNotAnArtefactOfTheFixture(self):
        """ Control: the identical shape with a CONSISTENT terminal condition
        must reach the node after it. Without this, the test above would also
        pass if the fixture were simply broken. """
        firewall = GenUtils.firewall('cfw')
        table = GenUtils.table('t0')
        entry = GenUtils.rule('0', key='cfw_t_r0')
        entry.append(GenUtils.address('10.0.0.0/8', direction='dst', version='4'))
        entry.append(GenUtils.action('jump', target='cfw_t_terminal'))
        table.append(entry)
        firewall.append(table)
        terminal_table = GenUtils.table('t_term')
        terminal = GenUtils.rule('term', key='cfw_t_terminal')
        terminal.append(GenUtils.address('10.0.0.0/24', direction='dst', version='4'))
        terminal.append(GenUtils.action('jump', target='cfw_t_after'))
        terminal_table.append(terminal)
        firewall.append(terminal_table)
        after_table = GenUtils.table('t_after')
        after = GenUtils.rule('after', key='cfw_t_after')
        after.append(GenUtils.action('accept'))
        after_table.append(after)
        firewall.append(after_table)
        config = GenUtils.config()
        firewalls = GenUtils.firewalls()
        firewalls.append(firewall)
        config.append(firewalls)

        kripke, encoding = Instantiator.InstantiateBase(
            config, Inits=['cfw_t_r0'], default_inits=False)
        self.assertTrue(bool(PycoSATAdapter().Solve(
            Instantiator.InstantiateReach(kripke, encoding, 'cfw_t_after'))))


class ClearedFieldTest(unittest.TestCase):
    """ AD6_PLAN.md §9.10.2 option 1: a CLEARED field becomes UNCONSTRAINED
    downstream, not zero and not frozen.

    FaVe's `post_routing` clears `in_port`/`out_port` before a packet leaves a
    device. That is not housekeeping: the next device's `routing` table READS
    `out_port` (318 such reads in wl_up) before overwriting it, so a stale
    egress surviving the hop would be read as if it were this device's own
    decision.

    In ad6's SSA encoding "unconstrained" is the ABSENCE of an axiom on that
    edge -- neither a REWRITE (forcing the target's bits to a constant) nor a
    FRAME (copying the source's bits across). These tests pin all three cases
    against each other, because the two failure modes are opposite and both
    silent: frame-instead-of-clear wrongly REFUTES, and zero-instead-of-clear
    wrongly matches a rule testing for port 0. """

    @staticmethod
    def _config(first_action_rewrites, match_value):
        """ r0 (rewrites/clears `f`) -> r1 (fieldmatch f == match_value). """
        firewall = GenUtils.firewall('cfw')

        table = GenUtils.table('t0')
        rule = GenUtils.rule('0', key='cfw_t_r0')
        rule.append(GenUtils.action('jump', target='cfw_t_second',
                                    rewrites=first_action_rewrites))
        table.append(rule)
        firewall.append(table)

        second_table = GenUtils.table('t_second')
        second = GenUtils.rule('s', key='cfw_t_second')
        second.append(GenUtils.fieldmatch('f', match_value))
        second.append(GenUtils.action('jump', target='cfw_t_third'))
        second_table.append(second)
        firewall.append(second_table)

        third_table = GenUtils.table('t_third')
        third = GenUtils.rule('t', key='cfw_t_third')
        third.append(GenUtils.action('accept'))
        third_table.append(third)
        firewall.append(third_table)

        config = GenUtils.config()
        firewalls = GenUtils.firewalls()
        firewalls.append(firewall)
        config.append(firewalls)
        return config

    def _reaches_third(self, rewrites, match_value):
        kripke, encoding = Instantiator.InstantiateBase(
            self._config(rewrites, match_value), Inits=['cfw_t_r0'],
            default_inits=False, MutableFields={'f': 8})
        return bool(PycoSATAdapter().Solve(
            Instantiator.InstantiateReach(kripke, encoding, 'cfw_t_third')))

    def testAnAssignedValueIsFramedAcrossTheEdge(self):
        """ Control: assignment works and survives. """
        self.assertTrue(self._reaches_third([('f', 10)], 10))

    def testAnAssignedValueRefutesADifferentMatch(self):
        """ Control: the frame axiom really does pin the value, so the test
        below is measuring the CLEAR and not a vacuous encoding. """
        self.assertFalse(self._reaches_third([('f', 10)], 20))

    def testAClearedFieldMatchesAnyValue(self):
        """ The property itself: after a clear, downstream is free to be
        anything, so a match on a value the field never held is satisfiable. """
        self.assertTrue(
            self._reaches_third([('f', None)], 20),
            "a cleared field must be UNCONSTRAINED downstream -- if this "
            "refutes, CLEAR is being treated as a frame and every post_routing "
            "clear silently under-approximates")

    def testAClearedFieldIsNotZero(self):
        """ The other failure mode. A reserved sentinel value would still be a
        VALUE: a rule testing for port 0 would match it. Clearing must not make
        0 special in either direction. """
        self.assertTrue(self._reaches_third([('f', None)], 0))
        self.assertTrue(self._reaches_third([('f', None)], 255))

    def testClearingOneFieldLeavesAnotherFramed(self):
        """ A clear is per FIELD, not per edge -- wl_ifi's routing rules set
        out_port and vlan together, and its post_routing rules clear both
        while other fields must keep flowing. """
        config = self._config([('f', None), ('g', 7)], 20)
        kripke, encoding = Instantiator.InstantiateBase(
            config, Inits=['cfw_t_r0'], default_inits=False,
            MutableFields={'f': 8, 'g': 8})
        solver = PycoSATAdapter()
        self.assertTrue(bool(solver.Solve(
            Instantiator.InstantiateReach(kripke, encoding, 'cfw_t_third'))),
            "f is cleared, so the f==20 match must still be satisfiable")
        self.assertEqual(kripke.GetNode('cfw_t_r0').Rewrites,
                         {'f': XMLUtils.CLEAR, 'g': 7})


class EncodingIsolationTest(unittest.TestCase):
    """ One model's variables must never leak into the next model's encoding.

    `Instantiator._GetVariables(Formula, Variables={})` carried a MUTABLE
    DEFAULT. Python evaluates a default once, at def time, so that dict was
    process-global: `_CreateGlobalConstraints` calls `_GetVariables(Encoding)`
    without a second argument, so EVERY model instantiated in a process
    accumulated into the same dict, and `_CreateBitConstraints` then emitted
    per-bit constraints for every variable ever seen anywhere.

    Why it went unnoticed for so long: the leaked constraints are
    (not x_i=0 or not x_i=1) over variables the current model never mentions.
    Those are trivially satisfiable, so no reachability answer changes -- it
    is an encoding-size and reported-model leak, not a wrong answer. What it
    DID do is make four exact-model tests order-dependent: testReach, testCycle,
    testShadow and testCross assert one specific solver model each, and they
    failed only when they ran after a test that had introduced IPv4 address
    variables (testMatchAllReachable), which is why they passed in isolation
    and failed under `make test`. """

    @staticmethod
    def _ipv4_model():
        """ A model whose encoding introduces ip4_* variables -- the shape that
        exposed the leak. """
        firewall = GenUtils.firewall('leakfw')
        table = GenUtils.table('t0')
        rule = GenUtils.rule('0', key='leakfw_t_r0')
        rule.append(GenUtils.address('10.0.0.0/8', direction='dst', version='4'))
        rule.append(GenUtils.action('accept'))
        table.append(rule)
        firewall.append(table)
        firewalls = GenUtils.firewalls()
        firewalls.append(firewall)
        config = GenUtils.config()
        config.append(firewalls)
        return config

    @staticmethod
    def _reach_variables():
        examinee = et.parse('./test/core/testReach.xml').getroot()
        InstantiatorTest.deannotate(examinee)
        instances = Instantiator.Instantiate(examinee)
        return {v.attrib[XMLUtils.ATTRNAME]
                for v in instances['net0_n0_drop_r0_reach'][0].iter(XMLUtils.VARIABLE)}

    def testGetVariablesDoesNotAccumulateAcrossCalls(self):
        """ The unit-level statement of the bug. """
        first = XMLUtils.conjunction()
        first.append(XMLUtils.variable('alpha=0'))
        second = XMLUtils.conjunction()
        second.append(XMLUtils.variable('beta=0'))

        self.assertEqual(set(Instantiator._GetVariables(first)), {'alpha=0'})
        self.assertEqual(
            set(Instantiator._GetVariables(second)), {'beta=0'},
            "the previous call's variables leaked in -- _GetVariables is "
            "accumulating into a shared default dict")

    def testTheDefaultIsNotASharedMutableObject(self):
        """ Directly: calling it must not grow a default that outlives the call. """
        before = Instantiator._GetVariables.__defaults__
        formula = XMLUtils.conjunction()
        formula.append(XMLUtils.variable('gamma=1'))
        Instantiator._GetVariables(formula)
        after = Instantiator._GetVariables.__defaults__
        self.assertFalse(
            any(isinstance(d, dict) and d for d in (after or ())),
            "a non-empty dict survives as a default argument: %r" % (after,))
        self.assertEqual(before, after)

    def testAModelsEncodingDoesNotInheritAnotherModelsVariables(self):
        """ End-to-end, and the exact order that broke testReach under
        `make test`: the same model instantiated before and after an unrelated
        IPv4 model must encode to the same variable set. """
        baseline = EncodingIsolationTest._reach_variables()

        config = EncodingIsolationTest._ipv4_model()
        Instantiator.InstantiateBase(config)

        after = EncodingIsolationTest._reach_variables()
        leaked = sorted(after - baseline)
        self.assertEqual(
            after, baseline,
            "an unrelated model's variables leaked into this encoding: %s" % leaked)


class IncrementalSessionSolverTest(unittest.TestCase):
    """ AD6_PLAN.md §9.3 Phase 6: `IncrementalSession`'s SOLVER selector.

    Before this the session hardcoded `Minisat22` in two places, so the
    production path could not reproduce the cadical195 configuration every
    wl_i2 number was measured under -- the measurement drivers could pick a
    backend and FaVe could not, which is backwards.

    Held to the same ground truth on the same fixture the grounding selector
    uses, so "production can now pick a backend" is a checked claim and not a
    plumbing assertion. """

    @staticmethod
    def _session(**kwargs):
        config = FlowPathConstraintTest._fixture()
        kripke, encoding = Instantiator.InstantiateBase(
            config, Inits=['entry', 'entry2'], default_inits=False,
            Acyclic=False)
        return IncrementalSession(kripke, encoding, **kwargs)

    def test_the_default_solver_is_minisat22(self):
        """ Back-compatibility: every archived result came from it. """
        session = self._session()
        try:
            self.assertEqual(session.solver, 'minisat22')
        finally:
            session.Close()

    def test_an_unknown_solver_is_refused(self):
        """ Loudly, at construction -- a silent fallback would mis-stamp
        whatever measurement followed. """
        with self.assertRaises(ValueError):
            self._session(solver='minisat')          # sic: the PySAT name is minisat22

    def test_every_declared_solver_agrees_with_the_default(self):
        """ The point of the selector: a different backend must answer the
        SAME question, not merely run. Any solver that disagrees here is
        mis-plumbed, and on a no-assumptions backend that is exactly how the
        silent all-reachable failure would show up. """
        pairs = [('entry', 'A'), ('entry', 'B'), ('entry2', 'A')]
        expected = {}
        session = self._session()
        try:
            for source, destination in pairs:
                expected[(source, destination)] = session.Query(source, destination)
        finally:
            session.Close()

        for name in SOLVERS:
            for grounding in (GROUNDING_RANK, GROUNDING_FLOW):
                if grounding == GROUNDING_RANK and needs_fresh_per_query(name):
                    continue        # refused by construction; covered below
                with self.subTest(solver=name, grounding=grounding):
                    session = self._session(solver=name, grounding=grounding)
                    try:
                        for source, destination in pairs:
                            self.assertEqual(
                                session.Query(source, destination),
                                expected[(source, destination)],
                                "%s/%s disagrees with the minisat22 baseline on "
                                "%s->%s" % (name, grounding, source, destination))
                    finally:
                        session.Close()

    def test_a_no_assumptions_solver_is_REFUSED_under_rank(self):
        """ THE TRAP THIS SELECTOR MUST NOT OPEN, and the reason the refusal is
        a hard error rather than a warning.

        The rank grounding answers a query by assumption-solving the persistent
        session on `[src_lit, dst_lit]`. Kissat404's PySAT wrapper SILENTLY
        IGNORES `assumptions` (it emits a RuntimeWarning and solves anyway), so
        both endpoint literals would be dropped and EVERY query would be solved
        against the bare base encoding -- satisfiable for essentially any
        model. Nothing crashes; the run just reports everything reachable.

        Under the flow grounding the endpoints go in as unit clauses on a fresh
        per-query solver instead, so the same backend is fine there -- which is
        why this refuses the COMBINATION and not the solver. """
        with self.assertRaises(ValueError) as caught:
            self._session(solver='kissat404', grounding=GROUNDING_RANK)
        message = str(caught.exception)
        self.assertIn('kissat404', message)
        self.assertIn('assumption', message.lower())
        self.assertIn(GROUNDING_FLOW, message,
                      "the refusal must name the grounding that DOES work, or "
                      "it reads as 'this backend is unusable'")

    def test_the_same_no_assumptions_solver_is_accepted_under_flow(self):
        session = self._session(solver='kissat404', grounding=GROUNDING_FLOW)
        try:
            self.assertFalse(session.Query('entry', 'A'))
        finally:
            session.Close()


class IncrementalSessionLiteAcyclicTest(unittest.TestCase):
    """ AD6_PLAN.md §9.3 Phase 6: `lite_acyclic` through the PRODUCTION session.

    `_CreateAcyclicConstraintsLite` had ZERO callers after Phase 5b deleted the
    two measurement drivers -- and it is MANDATORY on wl_i2, where the general
    lxml/Tseitin path OOMs before reaching DIMACS conversion (~0.14 MB per
    qualifying edge, ~22 GB projected for i2's 140,613-edge set). So without
    this, i2 through FaVe was possible only under flow grounding.

    It stayed opt-in for an architectural reason, not an evidentiary one: it
    returns plain (name, negated) clause tuples, which do not compose with the
    lxml-Element formula lists the general path extends. The session resolves
    them to DIMACS itself -- the same thing its flow path already does with
    `_CreateFlowPathConstraints`' identically-shaped output. """

    @staticmethod
    def _session(**kwargs):
        config = FlowPathConstraintTest._fixture()
        kripke, encoding = Instantiator.InstantiateBase(
            config, Inits=['entry', 'entry2'], default_inits=False,
            Acyclic=False)
        return IncrementalSession(kripke, encoding, **kwargs)

    def test_the_default_is_off(self):
        session = self._session()
        try:
            self.assertFalse(session.lite_acyclic)
        finally:
            session.Close()

    def test_lite_answers_EXACTLY_what_the_general_encoding_answers(self):
        """ The whole claim. The two encodings are proven clause-identical at
        the unit level (LiteAcyclicEquivalenceTest); this pins that the
        SESSION's two paths through them agree on real verdicts, which is what
        a caller actually depends on. """
        pairs = [('entry', 'A'), ('entry', 'B'), ('entry2', 'A'), ('A', 'B')]

        general = self._session(lite_acyclic=False)
        lite = self._session(lite_acyclic=True)
        try:
            for source, destination in pairs:
                with self.subTest(pair=(source, destination)):
                    self.assertEqual(
                        lite.Query(source, destination),
                        general.Query(source, destination),
                        "lite and general acyclic disagree on %s->%s"
                        % (source, destination))
        finally:
            general.Close()
            lite.Close()

    def test_lite_still_grounds_the_witness(self):
        """ Guards the test above: two encodings that both ground NOTHING also
        agree. The fixture's 'entry'->'A' is the pair the grounding gap turns
        on -- unreachable only if a floating cycle is forbidden. """
        session = self._session(lite_acyclic=True)
        try:
            self.assertFalse(
                session.Query('entry', 'A'),
                "lite acyclic must forbid the floating cycle, or it is not "
                "grounding anything and the agreement above is vacuous")
        finally:
            session.Close()

    def test_lite_is_ignored_under_the_flow_grounding_and_says_so(self):
        """ The flow grounding builds no rank constraints at all, so
        `lite_acyclic` cannot apply. Reporting it as applied would mis-stamp
        the result -- the same reason `faithful_vlan` was removed rather than
        ignored at §9.25. """
        session = self._session(lite_acyclic=True, grounding=GROUNDING_FLOW)
        try:
            self.assertFalse(
                session.lite_acyclic,
                "a flow-grounded session must not claim a rank-encoding "
                "option it never applied")
        finally:
            session.Close()
