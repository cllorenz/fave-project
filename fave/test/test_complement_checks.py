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

""" The other half of a conditional permission: these services and NOTHING ELSE.

A cell like `(protocol:tcp;port:331)` says the only traffic permitted between
that pair is TCP/331. Until now only the confirming half was checked -- "331
reaches" -- so the cell passed whether or not 332 also got through. A pair that
is *wholly* denied is checked (the empty-cell branch), and a pair that is
permitted is checked; a pair that is PARTIALLY permitted was checked in one
direction only.

The engine offers no positive form for it: its one condition primitive is
existential overlap, with no universal counterpart, and probe filters and header
tests are deactivated. So "only 331" is expressible only as "nothing outside
331" -- a must-not-reach over the complement.

THE SHAPE OF THE COMPLEMENT. `not (a and b)` is `not a or not b`, and the
complement of a union is the intersection of complements, so complementing a
cell means contradicting every alternative at once: pick one field from each
alternative and negate it, for every combination. Multiple check entries OR
together, so each combination becomes its own must-not-reach check.

OFF BY DEFAULT. Emitting these changes the check set of every workload with a
conditionally permitted cell, and therefore what those workloads are expected to
report. That is a decision per workload, not a silent upgrade.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

from bench.reach_csv_to_checks import complement_terms


_HERE = os.path.dirname(os.path.abspath(__file__))
_FAVE = os.path.dirname(_HERE)


class TestComplementTerms(unittest.TestCase):

    def test_a_single_service_needs_two_terms(self):
        """ `not (tcp and 331)` is `not tcp or not 331`. """
        self.assertEqual(
            complement_terms('(protocol:tcp;port:331)'),
            [('port:331',), ('protocol:tcp',)])

    def test_alternatives_sharing_a_protocol_collapse_to_two(self):
        """ The four raw combinations include `not tcp` twice over and two
        terms that are supersets of it; only the minimal ones survive. """
        self.assertEqual(
            complement_terms('(protocol:tcp;port:80|protocol:tcp;port:22)'),
            [('port:22', 'port:80'), ('protocol:tcp',)])

    def test_alternatives_differing_in_protocol_need_all_four(self):
        """ Nothing is subsumed here, and dropping any term would admit traffic
        the cell forbids. """
        self.assertEqual(
            complement_terms('(protocol:tcp;port:80|protocol:udp;port:53)'),
            [('port:53', 'port:80'),
             ('port:53', 'protocol:tcp'),
             ('port:80', 'protocol:udp'),
             ('protocol:tcp', 'protocol:udp')])

    def test_no_term_is_a_superset_of_another(self):
        """ More negations describe a smaller set, so a superset term is
        already covered by the subset one and only inflates the check count. """
        terms = complement_terms(
            '(protocol:tcp;port:80|protocol:tcp;port:22|protocol:tcp;port:443)')

        for one in terms:
            for other in terms:
                if one != other:
                    self.assertFalse(set(other) < set(one), (other, one))

    def test_the_result_is_deterministic(self):
        flag = '(protocol:tcp;port:80|protocol:udp;port:53)'
        self.assertEqual(complement_terms(flag), complement_terms(flag))

    def test_a_repeated_field_within_a_term_collapses(self):
        """ Contradicting two alternatives on the same field yields one
        negation, not two identical ones. """
        for term in complement_terms(
                '(protocol:tcp;port:80|protocol:tcp;port:22)'):
            self.assertEqual(len(term), len(set(term)))


class TestTheFlagGatesIt(unittest.TestCase):
    """ The safety property: nothing changes unless a workload asks. """

    CSV = (
        ",client,server\n"
        "client,X,(protocol:tcp;port:350)\n"
        "server,,X\n"
    )

    def _run(self, *extra):
        workdir = tempfile.mkdtemp()
        self.addCleanup(
            lambda: [os.unlink(os.path.join(workdir, f))
                     for f in os.listdir(workdir)] and os.rmdir(workdir))
        policy = os.path.join(workdir, 'policy.csv')
        checks = os.path.join(workdir, 'checks.json')
        with open(policy, 'w') as out:
            out.write(self.CSV)

        subprocess.check_call(
            [sys.executable, 'bench/reach_csv_to_checks.py',
             '-p', policy, '-m', 'bench/empty.json',
             '-c', checks,
             '--cchecks', os.path.join(workdir, 'cchecks.json'),
             '-j', os.path.join(workdir, 'reachable.json')] + list(extra),
            cwd=_FAVE,
            env=dict(os.environ, PYTHONPATH=_FAVE))

        with open(checks) as raw:
            return json.load(raw)

    def test_by_default_no_complement_check_is_emitted(self):
        checks = self._run()

        self.assertFalse([c for c in checks if 'f=!' in c])

    def test_with_the_flag_the_complement_is_emitted(self):
        checks = self._run('--complement')
        negated = [c for c in checks if 'f=!' in c]

        self.assertEqual(len(negated), 2)
        self.assertTrue(all(c.startswith('! ') for c in negated))
        self.assertTrue(any('f=!port:350' in c for c in negated))
        self.assertTrue(any('f=!protocol:tcp' in c for c in negated))

    def test_the_positive_checks_are_unchanged_by_the_flag(self):
        plain = [c for c in self._run() if 'f=!' not in c]
        with_flag = [c for c in self._run('--complement') if 'f=!' not in c]

        self.assertEqual(plain, with_flag)

    def test_every_emitted_check_parses(self):
        from bench.compliance_checker import _parse_check

        for check in self._run('--complement'):
            _parse_check(check)


if __name__ == '__main__':
    unittest.main()
