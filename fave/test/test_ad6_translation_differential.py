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

""" AD6_PLAN.md §9 Phase 3: the semantic and structural translations must
answer every query the same way, on real benchmark models.

THIS IS THE TEST PHASE 2 EXISTED TO MAKE POSSIBLE. Every other test of the
translator works on hand-built objects; this one runs both paths over a real
FaVe model and compares verdicts. Nothing else can catch a translation that is
individually plausible at every step and wrong as a whole -- which is precisely
what §9.10 through §9.13 were: three successive port designs, each internally
consistent, each caught only by a matrix that moved.

The comparison is TWO-SIDED on purpose. A difference in either direction is a
failure, but they mean different things: structural finding MORE reachable is
an over-approximation (a constraint went missing), structural finding LESS is
an under-approximation (something is over-constrained). Both have happened
here, and reporting which one it is saves the next reader a bisection.

`reachable.json` is also checked independently, so a shared bug that moved both
paths together would still be caught -- agreement alone is not correctness
(§5.5's note on what an oracle earned by process is worth). """

import json
import logging
import os
import unittest

from ad6.adapter import Ad6Adapter, TRANSLATION_SEMANTIC, TRANSLATION_STRUCTURAL
from util.in_process_driver import InProcessFaVe


_PREFIX = "bench/wl_ifi"


def _matrix(translation):
    """ {(source, probe)} that the model calls UNREACHABLE, plus the source and
    probe lists, from one full all-pairs sweep. """
    log = logging.getLogger("test_ad6_translation_differential")
    log.setLevel(logging.CRITICAL)
    engine = Ad6Adapter(log, translation=translation)
    with InProcessFaVe(engine) as fave:
        fave.replay(_PREFIX)
        sources = sorted(engine._generators)
        probes = sorted(engine._probes)
        engine.check_compliance(
            {probe: [[source, False, []] for source in sources] for probe in probes})
        unreachable = {(s, p) for s, p, _must, _cond in engine.get_compliance_results()}
    return sources, probes, unreachable


class TestWlIfiDifferential(unittest.TestCase):
    """ wl_ifi: 17 sources x 17 probes = 289 pairs, ~4 s per sweep. """

    @classmethod
    def setUpClass(cls):
        cls.sources, cls.probes, cls.semantic = _matrix(TRANSLATION_SEMANTIC)
        _s, _p, cls.structural = _matrix(TRANSLATION_STRUCTURAL)
        cls.expected = json.load(open(os.path.join(_PREFIX, "reachable.json")))

    def test_the_two_translations_agree_on_every_pair(self):
        extra = sorted(self.semantic - self.structural)   # structural says reachable
        missing = sorted(self.structural - self.semantic)  # structural says unreachable
        self.assertEqual(
            (extra, missing), ([], []),
            "the translations disagree. %d pairs where STRUCTURAL is more "
            "permissive (a constraint went missing): %s. %d where it is more "
            "restrictive (something is over-constrained): %s"
            % (len(extra), extra[:5], len(missing), missing[:5]))

    def test_the_sweep_is_not_vacuous(self):
        """ Guards the test above: two empty matrices also agree. wl_ifi must
        produce both verdicts, or agreement proves nothing. """
        total = len(self.sources) * len(self.probes)
        self.assertEqual(total, 289)
        self.assertTrue(0 < len(self.semantic) < total,
                        "the sweep must contain both reachable and unreachable "
                        "pairs, got %d unreachable of %d" % (len(self.semantic), total))

    def _roles(self, unreachable):
        return {src[len('source.'):]: sorted(
            {p[len('probe.'):] for p in self.probes
             if (src, p) not in unreachable and p[len('probe.'):] != src[len('source.'):]})
            for src in self.sources}

    def test_both_translations_match_reachable_json_independently(self):
        """ Agreement alone is not correctness -- a shared bug would move both
        paths together. Each is therefore also held to ground truth. """
        for label, unreachable in (('semantic', self.semantic),
                                   ('structural', self.structural)):
            got = self._roles(unreachable)
            diffs = {role: {'missing': sorted(set(self.expected.get(role, [])) - set(got.get(role, []))),
                            'extra': sorted(set(got.get(role, [])) - set(self.expected.get(role, [])))}
                     for role in sorted(set(got) | set(self.expected))
                     if set(got.get(role, [])) != set(self.expected.get(role, []))}
            with self.subTest(translation=label):
                self.assertEqual(diffs, {},
                                 "%s differs from reachable.json: %s" % (label, diffs))


if __name__ == '__main__':
    unittest.main()
