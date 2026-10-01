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

""" The accommodation registry stays complete (TODO item 31; VERIFLOW_PLAN.md V4).

`ACCOMMODATIONS.md` is the one document the write-up cites for every way a
tool was helped to run the suite or a workload was changed for it. Every
measurement-affecting choice VeriFlow-FR stamps must have an entry there, so a
new choice cannot reach a result cell undocumented. Pure Python: the stamps
come from the translation, and the adapter's configuration keys are named here.
"""

import os
import re
import unittest

from devices.switch import SwitchModel
from rule.rule_model import Forward, Match, Rule, RuleField
from veriflow.translate import Translator

_REGISTRY = os.path.join(os.path.dirname(__file__), "..", "..", "ACCOMMODATIONS.md")

#: VeriFlowAdapter.configuration_stamp()'s keys (it needs the native engine).
_CONFIG_KEYS = ("impl", "vf_fields", "vf_revisit", "vf_slicing", "vf_budget")


class TestRegistryCoversEveryStamp(unittest.TestCase):

    def test_every_veriflow_stamp_has_an_entry(self):
        with open(_REGISTRY) as raw:
            text = raw.read()
        documented = set(re.findall(r"`(vf_[a-z_]+|impl)`", text))
        tr = Translator()
        model = SwitchModel("s1", ports=["1"], rules=[Rule(
            "s1", "s1.1", 1, match=Match([RuleField("packet.upper.dport", "22")]),
            actions=[Forward(["s1.1"])])])
        tr.add_tables(model)
        tr.add_rules(model)
        stamped = set(tr.translate().stamps) | set(_CONFIG_KEYS)
        self.assertEqual(stamped - documented, set(),
                         "stamped but not in ACCOMMODATIONS.md")


if __name__ == '__main__':
    unittest.main()
