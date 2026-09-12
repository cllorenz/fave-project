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

""" AD6_PLAN.md §9 Phase 0.2: the IR characterization tripwires, plus unit
tests for the snapshot tool's own comparison logic.

READ THIS BEFORE "FIXING" A FAILURE HERE. A failing snapshot does NOT mean
something broke. It means `Ad6Adapter._build_ir()` now emits something
different, which during the §9 rewrite is the EXPECTED outcome of nearly every
commit. The correct response is to adjudicate the change (§9 Phase 0.3:
NetPlumber's own matrix, and on wl_i2 additionally
`bench/i2_structural_oracle.py`) and then re-record with

    PYTHONPATH=. python3 bench/ad6_ir_snapshot.py --all \\
        --out bench/ad6_ir_snapshots.json

in the SAME commit as the change that moved it, so the diff shows both halves
together. Re-recording separately, or before adjudicating, destroys the only
thing these tests provide.

The wl_i2 recipes cost ~8 s each and are therefore opt-in, behind
AD6_IR_SNAPSHOT_FULL=1; everything else runs in the fast tier. """

import json
import os
import unittest

import bench.ad6_ir_snapshot as snap


_STORED_PATH = os.path.join("bench", "ad6_ir_snapshots.json")

# ~8 s apiece (the i2 replay), against ~0.1-1.7 s for everything else.
_HEAVY = {"wl_i2_plain", "wl_i2_faithful", "wl_i2_faithful_untag"}
_FULL = bool(os.environ.get("AD6_IR_SNAPSHOT_FULL"))


def _stored():
    with open(_STORED_PATH) as raw:
        return json.load(raw)


class TestSnapshotComparison(unittest.TestCase):
    """ The tool's own logic, with no model build -- so a bug in the tripwire
    itself cannot masquerade as a bug in the adapter. """

    def test_identical_snapshots_compare_equal(self):
        one = {"sha256": "a" * 64, "shape": {"devices": {"type": "list", "len": 3}}}
        self.assertEqual(snap._compare(one, dict(one)), [])

    def test_a_changed_hash_is_reported_with_the_key_that_moved(self):
        old = {"sha256": "a" * 64, "shape": {"devices": {"type": "list", "len": 3}}}
        new = {"sha256": "b" * 64, "shape": {"devices": {"type": "list", "len": 4}}}
        diffs = snap._compare(new, old)
        self.assertTrue(diffs, "a changed hash must be reported")
        self.assertTrue(any("devices" in line for line in diffs),
                        "the report must localize WHICH key moved, or every diff "
                        "becomes a bisection: %s" % diffs)

    def test_an_added_or_removed_key_is_reported(self):
        old = {"sha256": "a" * 64, "shape": {"devices": {"type": "list", "len": 3}}}
        new = {"sha256": "b" * 64, "shape": {"devices": {"type": "list", "len": 3},
                                             "mid_rw": {"type": "dict", "len": 1}}}
        diffs = snap._compare(new, old)
        self.assertTrue(any("mid_rw" in line and "<absent>" in line for line in diffs),
                        "a NEW IR key must be visible as new: %s" % diffs)
        self.assertTrue(any("mid_rw" in line for line in snap._compare(old, new)),
                        "and a REMOVED one as removed")

    def test_canonical_form_ignores_insertion_order(self):
        """ The hash must answer "did the content move", not "was it built in a
        different order" -- otherwise a harmless refactor trips every tripwire
        at once and they stop being read. """
        self.assertEqual(snap._canonical({"b": [1, 2], "a": 1}),
                         snap._canonical({"a": 1, "b": [1, 2]}))

    def test_shape_summarizes_containers_and_keeps_scalars(self):
        self.assertEqual(snap._shape([1, 2, 3]), {"type": "list", "len": 3})
        self.assertEqual(snap._shape(True), {"type": "bool", "value": True})
        self.assertEqual(snap._shape({"a": [1, 2]})["len"], 1)


class TestStoredSnapshotFile(unittest.TestCase):
    """ Properties of the recorded file itself, independent of any rebuild. """

    def test_every_recipe_has_a_stored_snapshot(self):
        missing = sorted(set(snap.RECIPES) - set(_stored()))
        self.assertEqual(missing, [],
                         "recipes without a stored snapshot are silently untracked: %s"
                         % missing)

    def test_no_stored_snapshot_lacks_a_recipe(self):
        orphans = sorted(set(_stored()) - set(snap.RECIPES))
        self.assertEqual(orphans, [],
                         "stored snapshots for removed recipes go stale unnoticed: %s"
                         % orphans)

    def test_the_i2_faithful_untag_snapshot_differs_from_untag_off(self):
        """ A tripwire that cannot distinguish two configurations is not a
        tripwire. probe_untag adds literals, so these two MUST differ; if they
        ever hash the same, the snapshot is not covering the flag. """
        stored = _stored()
        self.assertNotEqual(stored["wl_i2_faithful"]["sha256"],
                            stored["wl_i2_faithful_untag"]["sha256"])

    def test_plain_and_faithful_snapshots_differ_on_both_benchmarks(self):
        stored = _stored()
        for plain, faithful in (("wl_i2_plain", "wl_i2_faithful"),
                                ("wl_stanford_n16_plain", "wl_stanford_n16_faithful")):
            self.assertNotEqual(stored[plain]["sha256"], stored[faithful]["sha256"],
                                "%s and %s must not hash alike" % (plain, faithful))


class TestIRSnapshotsUnchanged(unittest.TestCase):
    """ The tripwires themselves: rebuild each IR and compare. See this
    module's docstring before changing anything in response to a failure. """

    def _assert_unchanged(self, name):
        stored = _stored()
        self.assertIn(name, stored, "no stored snapshot for %s" % name)
        diffs = snap._compare(snap.snapshot(name), stored[name])
        self.assertEqual(
            diffs, [],
            "%s's IR changed. This is EXPECTED during the §9 rewrite -- adjudicate "
            "it (AD6_PLAN.md §9 Phase 0.3), then re-record with "
            "`python3 bench/ad6_ir_snapshot.py --all --out %s` in the SAME commit. "
            "Differences:\n%s" % (name, _STORED_PATH, "\n".join(diffs)))

    def test_wl_ifi(self):
        self._assert_unchanged("wl_ifi")

    def test_wl_up(self):
        self._assert_unchanged("wl_up")

    def test_wl_stanford_n2_plain(self):
        self._assert_unchanged("wl_stanford_n2_plain")

    def test_wl_stanford_n2_faithful(self):
        self._assert_unchanged("wl_stanford_n2_faithful")

    def test_wl_stanford_n16_plain(self):
        self._assert_unchanged("wl_stanford_n16_plain")

    def test_wl_stanford_n16_faithful(self):
        self._assert_unchanged("wl_stanford_n16_faithful")

    @unittest.skipUnless(_FULL, "wl_i2 IR replay costs ~8 s; set AD6_IR_SNAPSHOT_FULL=1")
    def test_wl_i2_plain(self):
        self._assert_unchanged("wl_i2_plain")

    @unittest.skipUnless(_FULL, "wl_i2 IR replay costs ~8 s; set AD6_IR_SNAPSHOT_FULL=1")
    def test_wl_i2_faithful(self):
        self._assert_unchanged("wl_i2_faithful")

    @unittest.skipUnless(_FULL, "wl_i2 IR replay costs ~8 s; set AD6_IR_SNAPSHOT_FULL=1")
    def test_wl_i2_faithful_untag(self):
        self._assert_unchanged("wl_i2_faithful_untag")


if __name__ == "__main__":
    unittest.main()
