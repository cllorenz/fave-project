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

""" A re-sent device must not leave its parse behind in the measured process.

pybison 0.6.4 leaks every parse tree whole in the process that parses
(`InProcessFaVe._client_process`). The in-process harness used to parse a
re-sent packet filter in the process it measures: on wl_up S2 every engine
grew by 4-11 MB per re-send, on wl_tum by about 90 MB, and the calibration's
VeriFlow-FR cell on wl_tum stopped at its RSS limit after 12 re-sends
(bench/campaigns/results_inc_dev_fave_calibration_20261016). Real FaVe runs a
client as a process of its own; so does the harness now.

Ten re-sends of wl_up packet filters, to an engine that keeps nothing: the
Python heap they leave behind is measured by tracemalloc. With the client in
this process it was 38.3 MB over the ten (2026-10-17); the bound is 5 MB.
"""

import gc
import tempfile
import tracemalloc
import unittest

from bench.feature_survey import RecordingEngine
from test.backend_gate import require_or_skip
from test.incremental_oracle import inputs_present
from util import fave_streams as fs
from util.in_process_driver import InProcessFaVe

_PREFIX = 'bench/wl_up'


class _Null(RecordingEngine):
    """ Takes every update and keeps nothing: what remains is FaVe's. """
    built = False

    def add_rules(self, model):
        pass

    def delete_rule(self, *_args, **_kwargs):
        pass

    def insert_rule(self, *_args, **_kwargs):
        pass

    def takes_updates(self):
        return self.built


@require_or_skip(inputs_present(_PREFIX), "wl_up inputs not generated")
class TestResendMemory(unittest.TestCase):

    def test_ten_resends_leave_no_parse_behind(self):
        engine = _Null()
        with tempfile.TemporaryDirectory() as work, InProcessFaVe(engine) as fave:
            wl = fs.FaveWorkload(_PREFIX, work)
            fave.replay(wl.zero_prefix())
            engine.built = True
            msgs = [m for m in wl.messages(fs.build_stream('s2', wl, 0.2, 1))
                    if m[1][0][0] == 'line'][:10]
            self.assertEqual(len(msgs), 10)
            gc.collect()
            tracemalloc.start()
            try:
                before = tracemalloc.get_traced_memory()[0]
                for op, units in msgs:
                    wl.send(fave, op, units)
                gc.collect()
                grown = tracemalloc.get_traced_memory()[0] - before
            finally:
                tracemalloc.stop()
        self.assertLess(grown, 5 * 2**20,
                        "ten re-sends left %.1f MB behind" % (grown / 2**20))


if __name__ == '__main__':
    unittest.main()
