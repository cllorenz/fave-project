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

""" Ad6Adapter._lpm_prio (AD6_PLAN.md §5.2): pins the real longest-prefix-
match priority fix -- ad6/fave_bridge.py's own table evaluation is
sequential first-match ordered by ascending `prio`, so a genuine LPM
decision requires the MORE SPECIFIC (longer-prefix) of two overlapping
dst-specific routes on one device to get the LOWER `prio`, unconditionally
(not merely "any dst-specific route before the no-dst default", which is
all a prior binary 0-vs-65535 scheme guaranteed -- exact for wl_ifi/wl_up
only because neither happens to carry two overlapping-prefix routes on the
same device; Stanford's real FIBs do, AD6_PLAN.md §5.2).

This is the producer-side half of the fix; ad6/test/parser/favemodeltest.py
(a separate PYTHONPATH root -- fave/ad6/adapter.py cannot be imported from
inside ad6/'s own test tree, see that module's docstring) pins the
consumer side: that favemodel._routing_table/_build_device_table actually
honour whatever `prio` they are handed, end to end through a real SAT
query, regardless of capture order. """

import unittest

from ad6.adapter import _lpm_prio, _prefix_len


class TestAd6AdapterLpmPrio(unittest.TestCase):

    def test_no_dst_is_lowest_priority(self):
        """ The match-all default must sort LAST (highest prio number)
        against any real dst-specific route, of any prefix length. """
        self.assertGreater(_lpm_prio(None), _lpm_prio("0.0.0.0/0"))
        self.assertGreater(_lpm_prio(None), _lpm_prio("10.0.0.0/8"))
        self.assertGreater(_lpm_prio(None), _lpm_prio("2001:db8::/128"))

    def test_longer_prefix_sorts_first(self):
        """ The core fix: given two overlapping dst-specific routes, the
        longer (more specific) prefix must always get the lower prio,
        regardless of which family or which one is textually "first". """
        self.assertLess(
            _lpm_prio("2001:db8:0:1::/64"), _lpm_prio("2001:db8::/32"))
        self.assertLess(_lpm_prio("10.0.1.0/24"), _lpm_prio("10.0.0.0/8"))
        self.assertLess(_lpm_prio("172.28.0.0/14"), _lpm_prio("172.16.0.0/12"))

    def test_equal_prefix_length_ties(self):
        """ Two same-length prefixes (never overlapping in a valid FIB) get
        equal priority -- ties are harmless here since they cannot both
        match the same destination. """
        self.assertEqual(_lpm_prio("10.0.0.0/24"), _lpm_prio("192.168.1.0/24"))

    def test_prefix_len_explicit_mask(self):
        self.assertEqual(_prefix_len("10.0.0.0/8"), 8)
        self.assertEqual(_prefix_len("2001:db8::/32"), 32)
        self.assertEqual(_prefix_len("0.0.0.0/0"), 0)

    def test_prefix_len_defaults_to_host_route_when_mask_absent(self):
        """ Defensive fallback for a bare address with no explicit mask
        (not observed in practice -- every capture site emits "/<len>",
        confirmed against favemodel.py's own `_MATCH_ALL` convention -- but
        this must not silently misparse if it ever occurs). """
        self.assertEqual(_prefix_len("10.0.0.1"), 32)
        self.assertEqual(_prefix_len("2001:db8::1"), 128)


if __name__ == '__main__':
    unittest.main()
