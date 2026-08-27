import unittest
from unittest import TestSuite

import sys
import os


from parser.favemodeltest import (
    RoutingTableLPMTest, GenFirewallDeadPortGateTest, FaithfulVlanWiringTest
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


    def run(self):
        self._runner.run(self._suite)


    def __init__(self):
        self._suite = TestSuite()
        self.addTests()
        self._runner = unittest.TextTestRunner(verbosity=2)


if __name__ == "__main__":
    suite = ParserSuite()
    suite.run()
