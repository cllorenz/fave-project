import unittest
from unittest import TestSuite

import sys
import os


from core.instantiatortest import (
    InstantiatorTest, FlowPathConstraintTest, IncrementalSessionGroundingTest,
    RuleOrderSemanticsTest, TerminalConditionTest, ClearedFieldTest)

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
        # AD6_PLAN.md §5.4 B1 / §5.5: the PRODUCTION session's grounding
        # selector -- same MANUAL registry caveat as above.
        tests = [
            'test_flow_grounding_refuses_the_ungrounded_pair',
            'test_rank_grounding_refuses_the_ungrounded_pair',
            'test_both_groundings_agree_on_every_pair_of_the_fixture',
            'test_flow_grounding_does_not_leak_between_queries',
            'test_flow_grounding_refutes_an_endpoint_with_no_usable_edge',
            'test_the_default_grounding_is_rank',
            'test_an_unknown_grounding_is_refused',
            'test_close_is_safe_under_the_flow_grounding',
        ]
        self._suite.addTests(map(IncrementalSessionGroundingTest,tests))

        # AD6_PLAN.md §9 Phase 0.1: the rule-order semantics the adapter
        # rewrite's structural translation rests on -- same MANUAL registry
        # caveat as above.
        tests = [
            'testAnIdenticallyMatchingLaterRuleIsShadowed',
            'testSwappingTheOrderSwapsTheVerdict',
            'testDisjointRulesAreBothReachable',
            'testAWiderLaterRuleStaysReachableOnItsResidual',
            'testANarrowerLaterRuleIsShadowedByAWiderEarlierOne',
            'testAMatchAllEarlierRuleShadowsEverythingAfterIt',
        ]
        self._suite.addTests(map(RuleOrderSemanticsTest,tests))

        # AD6_PLAN.md §9.9.1: a terminal rule's own condition is enforced by
        # nothing. Same MANUAL registry caveat as above.
        tests = [
            'testATerminalRulesOwnConditionIsNotEnforced',
            'testTheSameConditionISEnforcedOnceTheRuleHasAnOutgoingEdge',
            'testTheContradictionIsGenuineAndNotAnArtefactOfTheFixture',
        ]
        self._suite.addTests(map(TerminalConditionTest,tests))

        # AD6_PLAN.md §9.10.2 option 1: a cleared field is unconstrained
        # downstream. Same MANUAL registry caveat as above.
        tests = [
            'testAnAssignedValueIsFramedAcrossTheEdge',
            'testAnAssignedValueRefutesADifferentMatch',
            'testAClearedFieldMatchesAnyValue',
            'testAClearedFieldIsNotZero',
            'testClearingOneFieldLeavesAnotherFramed',
        ]
        self._suite.addTests(map(ClearedFieldTest,tests))


    def run(self):
        return self._runner.run(self._suite)


    def __init__(self):
        self._suite = TestSuite()
        self.addTests()
        self._runner = unittest.TextTestRunner(verbosity=2)


if __name__ == "__main__":
    suite = InstantiatorSuite()
    suite.run()
