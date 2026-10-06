#!/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2026 Claas Lorenz <claas_lorenz@genua.de>

# This file is part of FaVe.

# FaVe is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# FaVe is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with FaVe.  If not, see <https://www.gnu.org/licenses/>.

""" VeriFlow-FR as a production backend (VERIFLOW_PLAN.md V4).

Every measurement-affecting choice must reach the run's own record (TODO item
0a; VERIFLOW_PLAN.md §8): the aggregator logs `configuration_stamp()` next to
the backend name, as it does ad6's, and the adapter logs the stamps that only a
built model can know -- field order, the trie/scan split, the in-port expansion.
Needs libveriflow_fr; skips without it.
"""

import logging
import unittest

from test.backend_gate import require_or_skip
from veriflow.adapter import available


@require_or_skip(available(), "libveriflow_fr is not built")
class TestConfigurationStamp(unittest.TestCase):

    def test_the_static_choices_are_stamped(self):
        from veriflow.adapter import VeriFlowAdapter
        stamp = VeriFlowAdapter(logging.getLogger("t")).configuration_stamp()
        self.assertEqual(stamp, {"impl": "reimpl-literature", "vf_fields": "4+10",
                                 "vf_revisit": "state", "vf_slicing": "device",
                                 "vf_budget": 0, "vf_invert_lpm": False})

    def test_the_model_stamps_are_logged_at_build(self):
        from devices.switch import SwitchModel
        from rule.rule_model import Forward, Match, Rule, RuleField
        from veriflow.adapter import VeriFlowAdapter
        log = logging.getLogger("test_veriflow_adapter")
        with self.assertLogs(log, level="INFO") as caught:
            eng = VeriFlowAdapter(log)
            model = SwitchModel("s1", ports=["1"], rules=[Rule(
                "s1", "s1.1", 1, match=Match([RuleField("packet.upper.dport", "22")]),
                actions=[Forward(["s1.1"])])])
            eng.add_tables(model)
            eng.add_rules(model)
            eng.build()
        line = "\n".join(caught.output)
        self.assertIn("vf_field_order", line)
        self.assertIn("scan=['packet.upper.dport']", line)


if __name__ == '__main__':
    unittest.main()
