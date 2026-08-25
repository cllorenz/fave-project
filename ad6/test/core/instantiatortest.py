import unittest
import lxml.etree as et
from lxml import objectify
from src.core.instantiator import *
from src.solver.minisat import MiniSATAdapter
from src.solver.pycosat import PycoSATAdapter
from src.sat.satutils import SATUtils as sat
from src.xml.genutils import GenUtils

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



def main():
    unittest.main()


if __name__ == '__main__':
    main()
