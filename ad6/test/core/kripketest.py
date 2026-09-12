import unittest
import lxml.etree as et
from lxml import objectify
from src.core.kripke import *
from src.xml.xmlutils import XMLUtils
from src.xml.genutils import GenUtils
from src.core.instantiator import Instantiator
from src.solver.pycosat import PycoSATAdapter


class KripkeTest(unittest.TestCase):
    def testKripke(self):
        examinee = et.parse('./test/core/testKripke.xml').getroot()
        
        for elem in examinee.getiterator():
            i = elem.tag.find('}')
            if i >= 0:
                elem.tag = elem.tag[i+1:]
        objectify.deannotate(examinee,cleanup_namespaces=True)

        outiface = KripkeNode(Props=['net0_n0_eth0_out'],Gamma = XMLUtils.constant())
        n0_fw0_drop_r0 = KripkeNode(Props=['net0_n0_drop_r0','drop'], Gamma = XMLUtils.constant())
        n0_fw0_accept_r0 = KripkeNode(Props=['net0_n0_accept_r0','out'], Gamma = XMLUtils.constant())
        n0_fw0_fwdin_r2 = KripkeNode(Props=['net0_n0_fwdin_r8192'], Gamma = XMLUtils.constant())
        n0_fw0_fwdin_r1 = KripkeNode(Props=['net0_n0_fwdin_r4096'], Gamma = XMLUtils.variable('tcp'))
        n0_fw0_fwdin_r0 = KripkeNode(Props=['net0_n0_fwdin_r0'], Gamma = XMLUtils.constant())
        n0_fw0_forward_r0 = KripkeNode(Props=['net0_n0_output_r0','output','init'], Gamma = XMLUtils.constant())
        iniface = KripkeNode(Props=['net0_n0_eth0_in'],Gamma = XMLUtils.constant())

        expnodes = {
            'net0_n0_eth0_out' : outiface,
            'net0_n0_drop_r0' : n0_fw0_drop_r0,
            'net0_n0_accept_r0' : n0_fw0_accept_r0,
            'net0_n0_fwdin_r8192' : n0_fw0_fwdin_r2,
            'net0_n0_fwdin_r4096' : n0_fw0_fwdin_r1,
            'net0_n0_fwdin_r0' : n0_fw0_fwdin_r0,
            'net0_n0_output_r0' : n0_fw0_forward_r0,
            'net0_n0_eth0_in' : iniface,
        }

        expftrans = {
            'net0_n0_accept_r0': [('net0_n0_eth0_out', True)],
            'net0_n0_fwdin_r8192' : [('net0_n0_drop_r0',True)],
            'net0_n0_fwdin_r4096' : [('net0_n0_drop_r0',True),('net0_n0_fwdin_r8192',False)],
            'net0_n0_fwdin_r0' : [('net0_n0_accept_r0',True),('net0_n0_fwdin_r4096',False)],
            'net0_n0_output_r0' : [('net0_n0_fwdin_r0',True)],
        }

        expbtrans = {
            'net0_n0_eth0_out' : [('net0_n0_accept_r0',True)],
            'net0_n0_drop_r0' : [('net0_n0_fwdin_r4096',True),('net0_n0_fwdin_r8192',True)],
            'net0_n0_fwdin_r4096' : [('net0_n0_fwdin_r0',False)],
            'net0_n0_fwdin_r8192' : [('net0_n0_fwdin_r4096',False)],
            'net0_n0_fwdin_r0' : [('net0_n0_output_r0',True)],
            'net0_n0_accept_r0' : [('net0_n0_fwdin_r0',True)],
        }

        expinits = {'net0_n0_output_r0' : n0_fw0_forward_r0 }

        kripke = KripkeUtils.ConvertToKripke(examinee)

        self.assertEqual(expnodes.keys(),kripke._Nodes.keys())
        self.assertEqual(expftrans,kripke._FTransitions)
        self.assertEqual(expbtrans,kripke._BTransitions)
        self.assertEqual(expinits,kripke._Inits)


def main():
    unittest.main()


if __name__ == '__main__':
    main()


class MultiActionRuleTest(unittest.TestCase):
    """ AD6_PLAN.md §9.7.2 option B: one <action> per forwarding target, read
    as one TRUE transition each.

    WHY THIS EXISTS. FaVe rules genuinely fan out -- wl_stanford has rules
    carrying up to 16 `Forward` actions (10,120 forwards over 8,792 rules),
    552 of them alongside a rewrite. `KripkeUtils._HandleRule` used to read
    `Rule.xpath(ACTIONPATH)[0]`, the FIRST action only, silently ignoring the
    rest -- so a 16-way fanout would have been modelled as a 1-way forward and
    the other 15 ports' reachability would simply have been missing.

    The semantics being pinned are OR/existential: several simultaneous TRUE
    edges out of one node mean the packet may follow any of them, which is the
    correct reading for a reachability question (does SOME path arrive) and the
    same reading NetPlumber gives a branching flow. `KripkeStructure.Put` has
    always appended rather than replaced (`_AppendTransition`), so the Kripke
    layer supported this before the XML reader did; §9.7.2 option C -- one ad6
    rule per port -- is REJECTED and must not be re-proposed, because tables are
    first-match-wins (RuleOrderSemanticsTest) and only the first such rule would
    ever fire. """

    @staticmethod
    def _config(targets, rewrites=None, condition=True):
        """ One rule with one <action> per entry in `targets`, plus a following
        rule so the FALSE fall-through edge is present too. `rewrites` is an
        optional list, parallel to `targets`, of (field, value) or None. """
        firewall = GenUtils.firewall('mfw')
        table = GenUtils.table('t0')

        rule = GenUtils.rule('0', key='mfw_t_r0')
        if condition:
            rule.append(GenUtils.address('10.0.0.0/8', direction='dst', version='4'))
        for index, target in enumerate(targets):
            rewrite = (rewrites[index] if rewrites else None)
            if rewrite is None:
                rule.append(GenUtils.action('jump', target=target))
            else:
                field, value = rewrite
                rule.append(GenUtils.action('jump', target=target,
                                            rewrite_field=field, rewrite_value=value))
        table.append(rule)

        follow = GenUtils.rule('1', key='mfw_t_r1')
        follow.append(GenUtils.action('accept'))
        table.append(follow)
        firewall.append(table)

        for target in targets:
            target_table = GenUtils.table('t_%s' % target)
            target_rule = GenUtils.rule(target, key=target)
            target_rule.append(GenUtils.action('accept'))
            target_table.append(target_rule)
            firewall.append(target_table)

        config = GenUtils.config()
        firewalls = GenUtils.firewalls()
        firewalls.append(firewall)
        config.append(firewalls)
        return config

    @staticmethod
    def _kripke(config):
        return KripkeUtils.ConvertToKripke(config, default_inits=False)

    def _transitions(self, kripke, key='mfw_t_r0'):
        true_edges = [t for t, flag in kripke.IterFTransitions(key) if flag]
        false_edges = [t for t, flag in kripke.IterFTransitions(key) if not flag]
        return true_edges, false_edges

    def testASingleActionRuleIsUnchanged(self):
        """ The backward-compatibility guarantee that made option B safe to
        take: every rule ad6 emitted before this change carries exactly one
        action, so iterating must be indistinguishable from taking [0]. """
        kripke = self._kripke(self._config(['tgt_a']))
        true_edges, false_edges = self._transitions(kripke)
        self.assertEqual(true_edges, ['tgt_a'])
        self.assertEqual(false_edges, ['mfw_t_r1'],
                         "the fall-through edge must survive untouched")

    def testEveryActionBecomesItsOwnTrueTransition(self):
        kripke = self._kripke(self._config(['tgt_a', 'tgt_b', 'tgt_c']))
        true_edges, _ = self._transitions(kripke)
        self.assertEqual(sorted(true_edges), ['tgt_a', 'tgt_b', 'tgt_c'],
                         "a rule's 2nd and later actions must not be dropped -- "
                         "that is exactly the fanout bug this change fixes")

    def testFanoutCoexistsWithTheFallthroughEdge(self):
        """ N TRUE edges must not displace the FALSE one: a fanning-out rule
        still has to let non-matching traffic reach the next rule, or every
        rule after a fanout becomes dead. """
        kripke = self._kripke(self._config(['tgt_a', 'tgt_b']))
        true_edges, false_edges = self._transitions(kripke)
        self.assertEqual(len(true_edges), 2)
        self.assertEqual(false_edges, ['mfw_t_r1'])

    def testAllFanoutTargetsAreReachable(self):
        """ The semantic assertion, not just the graph shape: OR/existential,
        so every target is reachable -- not merely the first. """
        config = self._config(['tgt_a', 'tgt_b', 'tgt_c'])
        kripke, encoding = Instantiator.InstantiateBase(
            config, Inits=['mfw_t_r0'], default_inits=False)
        solver = PycoSATAdapter()
        for target in ('tgt_a', 'tgt_b', 'tgt_c'):
            with self.subTest(target=target):
                self.assertTrue(
                    bool(solver.Solve(Instantiator.InstantiateReach(
                        kripke, encoding, target))),
                    "%s unreachable -- fanout is not OR semantics" % target)

    def testARuleWithNoActionHasNoTrueTransitionButStillFallsThrough(self):
        """ Newly EXPRESSIBLE, and deliberate rather than incidental. `[0]`
        raised IndexError on an action-less rule; the loop makes it a rule that
        matches and goes nowhere -- a drop. FaVe has many such rules (2,315 in
        wl_up, 690 in wl_stanford N=16), so the translator needs this shape to
        mean something definite. """
        firewall = GenUtils.firewall('nfw')
        table = GenUtils.table('t0')
        rule = GenUtils.rule('0', key='nfw_t_r0')
        rule.append(GenUtils.address('10.0.0.0/8', direction='dst', version='4'))
        table.append(rule)
        follow = GenUtils.rule('1', key='nfw_t_r1')
        follow.append(GenUtils.action('accept'))
        table.append(follow)
        firewall.append(table)
        config = GenUtils.config()
        firewalls = GenUtils.firewalls()
        firewalls.append(firewall)
        config.append(firewalls)

        kripke = self._kripke(config)
        true_edges, false_edges = self._transitions(kripke, 'nfw_t_r0')
        self.assertEqual(true_edges, [], "an action-less rule must not forward")
        self.assertEqual(false_edges, ['nfw_t_r1'],
                         "but it must still fall through, or it would swallow "
                         "everything after it")

    def testOneRewriteSharedAcrossEveryFanoutAction(self):
        """ Measured across all four benchmarks: no rule anywhere carries more
        than ONE Rewrite action, so a fanning-out rule's single rewrite applies
        to all of its targets. Repeating it on each action must therefore land
        as one per-node entry, not N conflicting ones. """
        kripke = self._kripke(self._config(
            ['tgt_a', 'tgt_b'], rewrites=[('vlan', 10), ('vlan', 10)]))
        self.assertEqual(kripke.GetNode('mfw_t_r0').Rewrites, {'vlan': 10})

    def testConflictingRewritesOnOneRuleAreRefused(self):
        """ The one genuinely new failure mode the loop introduces. With `[0]`
        a second, disagreeing rewrite was unreachable; under the loop it would
        silently last-write-wins. No benchmark produces this, which is exactly
        why it must fail loudly if one ever does -- a silently-picked rewrite is
        a wrong answer that looks like a normal run. """
        with self.assertRaises(ValueError):
            self._kripke(self._config(
                ['tgt_a', 'tgt_b'], rewrites=[('vlan', 10), ('vlan', 20)]))
