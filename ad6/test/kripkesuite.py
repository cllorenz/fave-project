import unittest
from unittest import TestSuite

import sys
import os


from core.kripketest import KripkeTest, MultiActionRuleTest, MultiRewriteTest

class KripkeSuite(TestSuite):
    def addTests(self):
        tests = [
            'testKripke'
        ]
        self._suite.addTests(map(KripkeTest,tests))

        # AD6_PLAN.md §9.7.2 option B: one <action> per forwarding target, read
        # as one TRUE transition each. MANUAL registry -- a test not listed here
        # does not run under this suite, however green it looks under pytest.
        tests = [
            'testASingleActionRuleIsUnchanged',
            'testEveryActionBecomesItsOwnTrueTransition',
            'testFanoutCoexistsWithTheFallthroughEdge',
            'testAllFanoutTargetsAreReachable',
            'testARuleWithNoActionHasNoTrueTransitionButStillFallsThrough',
            'testOneRewriteSharedAcrossEveryFanoutAction',
            'testConflictingRewritesOnOneRuleAreRefused',
        ]
        self._suite.addTests(map(MultiActionRuleTest,tests))

        # AD6_PLAN.md §9.10.2 option 1: several rewrites per action, and CLEAR.
        tests = [
            'testASingleRewriteStillWorksThroughTheAttributeForm',
            'testSeveralFieldsAreRewrittenByOneAction',
            'testAClearIsRecordedDistinctlyFromAnyValue',
            'testAClearAndAnAssignmentCoexistOnOneAction',
            'testTheChildFormAndTheAttributeFormAgree',
        ]
        self._suite.addTests(map(MultiRewriteTest,tests))


    def run(self):
        return self._runner.run(self._suite)


    def __init__(self):
        self._suite = TestSuite()
        self.addTests()
        self._runner = unittest.TextTestRunner(verbosity=2)


if __name__ == "__main__":
    suite = KripkeSuite()
    suite.run()
