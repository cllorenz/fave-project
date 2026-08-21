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


def main():
    unittest.main()


if __name__ == '__main__':
    main()
