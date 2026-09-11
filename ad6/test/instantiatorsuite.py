import unittest
from unittest import TestSuite

import sys
import os


from core.instantiatortest import InstantiatorTest, FlowPathConstraintTest

class InstantiatorSuite(TestSuite):
    def addTests(self):
        tests = [
            'testReach',
            'testCycle',
            'testShadow',
            'testCross',
            'testMatchAllReachable',
            'testStateLiteralForcingIsMutuallyExclusive',
            'testSrcCidrQuerySeedMustUseSharedBitVector',
            'testMutationChainAndJoinSSAEncoding',
            'testFieldMatchGatesOnMutatedSSAValue',
            'testCycleReachabilityIsUnsoundWithoutRealOrigin',
            'testSolveGroundedEndToEndRejectsUngroundedCycleWitness',
            'testBackwardSupportRestrictsBlockingToDestinationsOwnClosure',
            'testAcyclicRankConstraintRejectsFloatingCycleStatically',
            'testComputeSCCsFindsOnlyGenuineCyclesNotLongAcyclicChains',
            'testAcyclicRankConstraintScopesToNonTrivialSCCsOnly',
            'testAcyclicRankConstraintLiteMatchesGeneralEncoding',
            'testSolveAcyclicEndToEndTakesFastPathWhenAlreadyGrounded',
            'testSolveAcyclicEndToEndEscalatesOnlyOnceAndCachesAcrossQueries',
            'testSolveAcyclicEndToEndReportsEscalationPerQueryViaStats',
            'testRunWithBigStackIsATransparentWrapper'
        ]
        self._suite.addTests(map(InstantiatorTest,tests))
        # AD6_PLAN.md §5.4 B1 / §5.5: the single-unit s-t flow grounding
        # constraint. MANUAL registry -- a class added to instantiatortest.py
        # without an entry here is silently never run by `make test` (the way
        # testCIDRMatchAll went unexercised, ad6/FAVE_CHANGES.md §11).
        tests = [
            'test_the_ungrounded_pair_is_refused',
            'test_without_the_flow_constraint_the_same_pair_is_satisfiable',
            'test_a_genuine_direct_path_is_accepted',
            'test_a_genuine_path_ending_inside_the_cycle_is_accepted',
            'test_source_equals_destination_is_a_noop',
            'test_an_endpoint_with_no_usable_edge_is_an_empty_clause',
            'test_every_flow_edge_implies_its_transition',
            'test_at_most_one_is_pairwise_for_small_sets',
            'test_at_most_one_switches_to_sequential_when_wide',
            'test_at_most_one_actually_forbids_two',
            'test_at_most_one_of_zero_or_one_is_vacuous',
        ]
        self._suite.addTests(map(FlowPathConstraintTest,tests))


    def run(self):
        return self._runner.run(self._suite)


    def __init__(self):
        self._suite = TestSuite()
        self.addTests()
        self._runner = unittest.TextTestRunner(verbosity=2)


if __name__ == "__main__":
    suite = InstantiatorSuite()
    suite.run()
