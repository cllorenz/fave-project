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


class MultiRewriteTest(unittest.TestCase):
    """ AD6_PLAN.md §9.10.2 option 1: a rule may rewrite SEVERAL fields, and
    may CLEAR a field rather than assign it.

    Both come from FaVe's port bookkeeping, whose lifecycle is explicit in its
    own rules: `pre_routing` sets `in_port`, `routing` sets `out_port` (and
    reads it), `post_routing` reads both and then clears both. The clear is not
    cosmetic -- without it a stale egress would survive into the next device,
    where `routing` reads `out_port` before overwriting it (318 such reads in
    wl_up).

    A CLEAR is "this field becomes unconstrained", which in ad6's SSA encoding
    is the ABSENCE of any axiom for that field on that edge -- neither a rewrite
    (forcing bits to a constant) nor a frame (copying the source's bits). It is
    therefore spelled as a <rewrite> with no value, not as a reserved sentinel
    value: a sentinel would still be a VALUE, and a later equality match could
    read it. """

    @staticmethod
    def _rule_with(rewrites, target='tgt'):
        """ `rewrites`: list of (field, value) with value None meaning CLEAR. """
        firewall = GenUtils.firewall('rfw')
        table = GenUtils.table('t0')
        rule = GenUtils.rule('0', key='rfw_t_r0')
        rule.append(GenUtils.action('jump', target=target, rewrites=rewrites))
        table.append(rule)
        firewall.append(table)
        target_table = GenUtils.table('t_tgt')
        target_rule = GenUtils.rule('t', key=target)
        target_rule.append(GenUtils.action('accept'))
        target_table.append(target_rule)
        firewall.append(target_table)
        config = GenUtils.config()
        firewalls = GenUtils.firewalls()
        firewalls.append(firewall)
        config.append(firewalls)
        return config

    def _rewrites(self, rewrites):
        kripke = KripkeUtils.ConvertToKripke(self._rule_with(rewrites),
                                            default_inits=False)
        return kripke.GetNode('rfw_t_r0').Rewrites

    def testASingleRewriteStillWorksThroughTheAttributeForm(self):
        """ Backward compatibility: every rule ad6 emitted before this change
        carries the rewrite as a pair of ATTRIBUTES on the action. """
        firewall = GenUtils.firewall('afw')
        table = GenUtils.table('t0')
        rule = GenUtils.rule('0', key='afw_t_r0')
        rule.append(GenUtils.action('jump', target='tgt',
                                    rewrite_field='vlan', rewrite_value=10))
        table.append(rule)
        firewall.append(table)
        target_table = GenUtils.table('t_tgt')
        target_rule = GenUtils.rule('t', key='tgt')
        target_rule.append(GenUtils.action('accept'))
        target_table.append(target_rule)
        firewall.append(target_table)
        config = GenUtils.config()
        firewalls = GenUtils.firewalls()
        firewalls.append(firewall)
        config.append(firewalls)
        kripke = KripkeUtils.ConvertToKripke(config, default_inits=False)
        self.assertEqual(kripke.GetNode('afw_t_r0').Rewrites, {'vlan': 10})

    def testSeveralFieldsAreRewrittenByOneAction(self):
        """ wl_ifi's `routing` rules set `out_port` AND `vlan` together (10 of
        them); the attribute form can carry only one pair. """
        self.assertEqual(self._rewrites([('vlan', 10), ('out_port', 7)]),
                         {'vlan': 10, 'out_port': 7})

    def testAClearIsRecordedDistinctlyFromAnyValue(self):
        rewrites = self._rewrites([('in_port', None)])
        self.assertIn('in_port', rewrites)
        self.assertIs(rewrites['in_port'], XMLUtils.CLEAR)

    def testAClearAndAnAssignmentCoexistOnOneAction(self):
        self.assertEqual(self._rewrites([('vlan', 3), ('in_port', None)]),
                         {'vlan': 3, 'in_port': XMLUtils.CLEAR})

    def testTheChildFormAndTheAttributeFormAgree(self):
        """ Two spellings of one thing must not drift. """
        firewall = GenUtils.firewall('bfw')
        table = GenUtils.table('t0')
        rule = GenUtils.rule('0', key='bfw_t_r0')
        rule.append(GenUtils.action('jump', target='tgt',
                                    rewrite_field='vlan', rewrite_value=10))
        table.append(rule)
        firewall.append(table)
        tt = GenUtils.table('t_tgt')
        tr = GenUtils.rule('t', key='tgt')
        tr.append(GenUtils.action('accept'))
        tt.append(tr)
        firewall.append(tt)
        config = GenUtils.config()
        fws = GenUtils.firewalls()
        fws.append(firewall)
        config.append(fws)
        attribute_form = KripkeUtils.ConvertToKripke(
            config, default_inits=False).GetNode('bfw_t_r0').Rewrites
        self.assertEqual(attribute_form, self._rewrites([('vlan', 10)]))


class OpaqueConditionTest(unittest.TestCase):
    """ AD6_PLAN.md §9.18: `<opaque field="F">V</opaque>` -- a condition ad6
    carries as an uninterpreted proposition.

    Some FaVe field values are not numbers in any base and have no bit
    encoding: wl_up matches `module.limit` = '900/min' (436 rules) and
    `module.ipv6header.header` = 'ipv6-route' (10). A bit-vector is impossible
    and DROPPING them would weaken the model silently, so they become one
    boolean per (field, value) instead: the packet either satisfies that
    condition or it does not, consistently everywhere.

    SOUND ONLY FOR A SINGLE-VALUED FIELD, which is why these tests pin the
    independence too. Two different values of one field become two INDEPENDENT
    booleans, so a packet could satisfy both -- nonsense for a real field, and
    an over-approximation. `fave/ad6/translate.py` therefore refuses an opaque
    field that carries more than one value across the model; here we pin the
    ad6-level behaviour that makes that refusal necessary. """

    @staticmethod
    def _config(first, second):
        """ r0 (opaque `first`) -> target; r1 (opaque `second`) -> target2. """
        firewall = GenUtils.firewall('ofw')
        table = GenUtils.table('t0')
        rule = GenUtils.rule('0', key='ofw_t_r0')
        rule.append(GenUtils.opaque('module.limit', first))
        rule.append(GenUtils.action('jump', target='ofw_t_hit'))
        table.append(rule)
        second_rule = GenUtils.rule('1', key='ofw_t_r1')
        second_rule.append(GenUtils.opaque('module.limit', second))
        second_rule.append(GenUtils.action('jump', target='ofw_t_hit2'))
        table.append(second_rule)
        firewall.append(table)
        for key in ('ofw_t_hit', 'ofw_t_hit2'):
            t = GenUtils.table('t_' + key)
            r = GenUtils.rule(key, key=key)
            r.append(GenUtils.action('accept'))
            t.append(r)
            firewall.append(t)
        config = GenUtils.config()
        firewalls = GenUtils.firewalls()
        firewalls.append(firewall)
        config.append(firewalls)
        return config

    def testAnOpaqueConditionBecomesAPropositionOnTheRule(self):
        kripke = KripkeUtils.ConvertToKripke(self._config('900/min', '900/min'),
                                            default_inits=False)
        gamma = et.tostring(kripke.GetNode('ofw_t_r0').Gamma).decode()
        self.assertIn('opaque', gamma)
        self.assertIn('900/min', gamma)

    def testTheSameValueIsTheSameProposition(self):
        """ Two rules testing the same condition must agree about it. """
        kripke = KripkeUtils.ConvertToKripke(self._config('900/min', '900/min'),
                                             default_inits=False)
        first = et.tostring(kripke.GetNode('ofw_t_r0').Gamma).decode()
        second = et.tostring(kripke.GetNode('ofw_t_r1').Gamma).decode()
        self.assertEqual(first, second)

    def testDifferentValuesAreDIFFERENTPropositions(self):
        kripke = KripkeUtils.ConvertToKripke(self._config('900/min', '60/sec'),
                                             default_inits=False)
        first = et.tostring(kripke.GetNode('ofw_t_r0').Gamma).decode()
        second = et.tostring(kripke.GetNode('ofw_t_r1').Gamma).decode()
        self.assertNotEqual(first, second)

    def testDifferentValuesAreNOTMutuallyExclusive(self):
        """ The limitation, pinned rather than left implicit: nothing stops a
        packet satisfying two different values of one opaque field at once.
        That is why translate.py refuses a multi-valued opaque field, and this
        test is what makes that refusal justified rather than cautious. """
        config = self._config('900/min', '60/sec')
        kripke, encoding = Instantiator.InstantiateBase(
            config, Inits=['ofw_t_r0'], default_inits=False)
        solver = PycoSATAdapter()
        self.assertTrue(bool(solver.Solve(
            Instantiator.InstantiateReach(kripke, encoding, 'ofw_t_hit'))))

    def testAFieldNameWithUnderscoresDoesNotCollideWithOthersHandling(self):
        """ `_HandleOthers` splits a variable name on '_' and unpacks into two,
        so an opaque name joined with '_' would raise there for any field whose
        name contains one. The separator is '#', which no other naming
        convention in XMLUtils uses. """
        kripke, encoding = Instantiator.InstantiateBase(
            self._config('900/min', '900/min'), Inits=['ofw_t_r0'],
            default_inits=False)
        self.assertTrue(bool(PycoSATAdapter().Solve(
            Instantiator.InstantiateReach(kripke, encoding, 'ofw_t_hit'))))
