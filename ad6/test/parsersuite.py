import unittest
from unittest import TestSuite

import sys
import os


from parser.favemodeltest import (
    RoutingTableLPMTest, GenFirewallDeadPortGateTest, FaithfulVlanWiringTest,
    FaithfulVlanOutRewriteWiringTest, FaithfulVlanProbeUntagTest, WitnessPathTest,
    PortScopedAdmissionTest
)

class ParserSuite(TestSuite):
    def addTests(self):
        tests = [
            'testGeneralInsertedFirst',
            'testSpecificInsertedFirst',
            'testNonOverlappingRoutesUnaffectedByOrder'
        ]
        self._suite.addTests(map(RoutingTableLPMTest,tests))
        tests = [
            'test_generator_on_dead_port_jumps_to_drop',
            'test_generator_on_admitted_port_uses_normal_entry',
            'test_generator_on_admit_all_device_uses_normal_entry'
        ]
        self._suite.addTests(map(GenFirewallDeadPortGateTest,tests))
        tests = [
            'test_admitted_vlan_reaches',
            'test_non_admitted_vlan_is_blocked',
            'test_second_admitted_value_also_reaches',
            'test_mid_rewrite_gates_downstream_admission',
            'test_downstream_admission_rejects_stale_upstream_vlan',
            'test_plain_mode_ignores_faithful_vlan_fields_entirely',
        ]
        self._suite.addTests(map(FaithfulVlanWiringTest,tests))
        # AD6_PLAN.md §5.5 C4: the wl_i2-shaped OUT-stage rewrite. Registered
        # here explicitly -- this suite is a MANUAL registry, and a class
        # added to favemodeltest.py without a matching entry is silently
        # never run by `make test` (exactly how testCIDRMatchAll went
        # unexercised, ad6/FAVE_CHANGES.md §11).
        tests = [
            'test_first_routes_rewrite_reaches_when_admitted',
            'test_second_routes_rewrite_reaches_when_admitted',
            'test_admitting_neither_rewritten_vlan_blocks',
            'test_rewrite_to_vlan_zero_gates_downstream_admission',
            'test_a_route_without_a_rewrite_entry_passes_the_vlan_through',
            'test_downstream_gate_sees_the_rewritten_value_not_the_source_value',
            'test_plain_mode_ignores_the_out_rewrite_entirely',
        ]
        self._suite.addTests(map(FaithfulVlanOutRewriteWiringTest,tests))
        # AD6_PLAN.md §5.5 C4 (part 2): the probe-side VLAN untag. Manual
        # registry -- see the note above.
        tests = [
            'test_default_is_off',
            'test_plain_mode_produces_no_literals',
            'test_no_recorded_probe_vlan_produces_no_literals',
            'test_literals_are_flat_per_bit_variables_of_the_declared_width',
            'test_the_forced_variables_exist_in_the_base_encoding',
            'test_untagged_route_still_reaches',
            'test_only_tagged_routes_are_blocked_by_the_untag',
            'test_same_model_reaches_when_the_untag_is_off',
            'test_a_non_zero_untag_value_is_honoured',
            'test_multi_attachment_probe_is_gated_at_the_aggregate_node',
            'test_untag_holds_through_the_production_incremental_session',
        ]
        self._suite.addTests(map(FaithfulVlanProbeUntagTest,tests))
        # AD6_PLAN.md §5.5 "ROOT-CAUSING PLAN": the shared witness-path
        # primitive. Manual registry -- see the note above.
        tests = [
            'test_a_true_transition_name_parses',
            'test_a_false_transition_name_parses',
            'test_a_non_transition_name_is_not_a_transition',
            'test_only_positive_literals_count_as_taken_edges',
            'test_unknown_indices_are_ignored_rather_than_fatal',
            'test_a_walk_is_found_inside_the_true_edge_set',
            'test_the_shortest_walk_is_returned',
            'test_a_walk_is_found_despite_unrelated_true_edges',
            'test_no_walk_returns_none',
            'test_a_cycle_does_not_hang_the_search',
            'test_source_equal_destination_is_a_single_node_walk',
            'test_a_firewall_rule_node_maps_to_its_fave_device',
            'test_an_interface_node_maps_to_its_fave_device',
            'test_a_generator_node_maps_to_its_source',
            'test_a_probe_aggregate_node_maps_to_its_probe',
            'test_an_unknown_node_maps_to_none_rather_than_a_guess',
            'test_the_longest_matching_device_prefix_wins',
            'test_the_device_walk_collapses_consecutive_nodes_of_one_device',
            'test_unknown_nodes_are_dropped_from_the_device_walk',
            'test_a_device_revisited_after_leaving_is_not_collapsed_away',
        ]
        self._suite.addTests(map(WitnessPathTest,tests))
        # AD6_PLAN.md §5.5: per-(port, VLAN) ingress admission -- the wl_i2
        # root cause. Manual registry -- see the note above.
        tests = [
            'test_vlan_admitted_on_this_port_reaches',
            'test_the_same_vlan_on_a_port_that_does_not_admit_it_is_blocked',
            'test_the_other_port_is_gated_the_other_way_round',
            'test_a_port_with_no_admitted_vlans_at_all_is_blocked',
            'test_the_i2_root_cause_shape_is_blocked',
            'test_the_archived_flat_shape_still_gates_device_wide',
            'test_a_port_agnostic_admission_falls_back_to_device_wide',
            'test_plain_mode_ignores_the_relation_entirely',
            'test_entry_key_is_the_ports_own_gate',
            'test_entry_key_drops_a_port_with_no_admitted_vlans',
            'test_entry_key_is_unchanged_for_the_fallback_shapes',
            'test_the_gate_group_ends_in_an_unconditional_deny',
            'test_the_permit_carries_exactly_its_own_ports_vlans',
            'test_no_gate_and_a_device_wide_fieldmatch_for_the_flat_shape',
            'test_the_gate_precedes_the_ingress_acl_rather_than_replacing_it',
        ]
        self._suite.addTests(map(PortScopedAdmissionTest,tests))


    def run(self):
        return self._runner.run(self._suite)


    def __init__(self):
        self._suite = TestSuite()
        self.addTests()
        self._runner = unittest.TextTestRunner(verbosity=2)


if __name__ == "__main__":
    suite = ParserSuite()
    suite.run()
