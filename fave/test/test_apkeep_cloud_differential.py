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

""" APKeep-vs-NetPlumber reachability on wl_cloud, anchored to the dataset.

THE GAP THIS CLOSES. APKeep answered this workload with ten of its sixty-four
cells wrong and reported them without complaint: it dropped every
internet-sourced pair and invented four of its own. The cause was that its
forwarding translation is a destination-prefix trie -- so wl_cloud's leaf tables,
which permit one service into a prefix and then deny the prefix, arrived as a
forward and a drop at the same priority, and its gateway's DNAT arrived as no
rewrite at all (CLOUD_BENCH_PLAN.md §1.7.3).

Every piece was individually right, which is why this is a differential and not
a unit test. `_translate_fwd_rule` did exactly what a FIB needs; the tables it
was handed were not FIBs, and nothing in the tree compared its answers with
anything until a workload arrived whose forwarding tables carry ACLs.

UNCONDITIONED, DELIBERATELY -- like `test_ad6_cloud_differential.py`, which this
mirrors. A plain pair per cell keeps the query-seeding path out of a comparison
that is about the MODEL. The conditioned questions are asked by the benchmark's
own 71-check FPL run.

AND ANCHORED, not merely a consensus: two engines that broke the same way would
agree and both be wrong, so the cells the dataset itself determines are asserted
against its verdicts as well.

RUNS ONE ENGINE PER PROCESS. APKeep's resident JVM and NetPlumber's native
library contaminate each other in one process -- NetPlumber then reports full
reachability -- which `bench/apkeep_convergence.py` documents and works around
the same way.
"""

import json
import os
import subprocess
import sys
import unittest

from test.backend_gate import require_or_skip

_PREFIX = 'bench/wl_cloud'
_INPUTS = ['%s/%s' % (_PREFIX, f) for f in
           ('topology.json', 'routes.json', 'sources.json', 'policies.json',
            'mapping.json')]

#: The cells the dataset determines for the UNCONDITIONED question, with the
#: same reasoning as `test_ad6_cloud_differential._ORACLE`: a `sat` verdict
#: carries over to a broader question, an `unsat` one only if the instance was
#: unconditioned to begin with.
_ORACLE = {
    ('internet', 'dc1_leaf5_host5'): True,           # q01, sat, unconditioned
    ('internet', 'dc2_leaf7_host6'): False,          # q02, unsat, unconditioned
    ('internet', 'dc1_leaf0_host20'): True,          # q03, sat on tcp/332
    ('dc1_leaf6_host2', 'dc0_leaf1_host1'): True,    # q05, sat on tcp/350
}

_WORKER = r'''
import json, logging, sys
sys.path.insert(0, %(fave)r)
from util.in_process_driver import InProcessFaVe

which, out = sys.argv[1], sys.argv[2]
log = logging.getLogger(which); log.setLevel(logging.ERROR)
mapping = json.load(open(%(prefix)r + '/mapping.json'))
if which == 'netplumber':
    from netplumber import lib_adapter
    engine = lib_adapter.NetPlumberLibAdapter(log, mapping=mapping)
else:
    from apkeep.adapter import APKeepAdapter
    engine = APKeepAdapter(log, mapping=mapping, engine=which.split(':')[1])

with InProcessFaVe(engine) as fave:
    fave.replay(%(prefix)r)
    sources = sorted(getattr(engine, '_generators', None) or engine.generators)
    probes = sorted(getattr(engine, '_probes', None) or engine.probes)
    fave.check_compliance({p: [[s, False, []] for s in sources] for p in probes})

results = engine.get_compliance_results()
if hasattr(engine, 'generators') and not hasattr(engine, '_generators'):
    sid = {i[1]: n for n, i in engine.generators.items()}
    pid = {i[1]: n for n, i in engine.probes.items()}
    missed = {(sid[s], pid[d]) for (s, d, _v, _c) in results
              if s in sid and d in pid}
else:
    missed = {(s, p) for (s, p, _m, _c) in results}

base = lambda n: n.split('.', 1)[1] if n.startswith(('source.', 'probe.')) else n
open(out, 'w').write(json.dumps(
    {'%%s|%%s' %% (base(s), base(p)): (s, p) not in missed
     for p in probes for s in sources}))
'''


def _matrix(which, tmpdir):
    """ probe x source reachability from one engine, in its own process. """
    fave_dir = os.getcwd()
    out = os.path.join(tmpdir, 'matrix-%s.json' % which.replace(':', '-'))
    script = _WORKER % {'fave': fave_dir, 'prefix': _PREFIX}
    proc = subprocess.run(
        [sys.executable, '-c', script, which, out],
        cwd=fave_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=int(os.environ.get('FAVE_CLOUD_DIFF_TIMEOUT', '1800')))
    if proc.returncode != 0 or not os.path.isfile(out):
        raise AssertionError(
            "the %s worker failed (rc=%d):\n%s"
            % (which, proc.returncode, proc.stderr.decode()[-3000:]))
    with open(out) as raw:
        return dict((tuple(k.split('|')), v) for k, v in json.load(raw).items())


@require_or_skip(all(os.path.isfile(f) for f in _INPUTS),
                 "wl_cloud inputs not generated (run test/gen_wl_cloud_inputs.sh)")
class TestAPKeepCloudDifferential(unittest.TestCase):
    """ Two engines, one model, and a dataset that predates both. """

    @classmethod
    def setUpClass(cls):
        import tempfile
        # REGENERATE the oracle-phase model first. `bench/wl_cloud/*.json` is
        # shared by both phases and rewritten by whichever ran last, so a
        # preceding `--policy matrix` run leaves the 65-endpoint model in place
        # and this would silently compare a different network. Costs 0.3 s, and
        # it is the regeneration path CLOUD_BENCH_PLAN.md §1.8 requires anyway.
        regen = subprocess.run(
            ['bash', 'test/gen_wl_cloud_inputs.sh'],
            cwd=os.getcwd(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=dict(os.environ, PYTHON=sys.executable), timeout=600)
        if regen.returncode != 0:
            raise AssertionError("could not regenerate the wl_cloud inputs:\n%s"
                                 % regen.stdout.decode()[-3000:])
        cls._tmp = tempfile.mkdtemp(prefix='apkeep-cloud-diff-')
        cls.np = _matrix('netplumber', cls._tmp)
        cls.ak = _matrix('apkeep:ndd', cls._tmp)

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def test_both_workers_answered_every_pair(self):
        """ Eight FPL endpoints, so sixty-four cells. Asserted explicitly
        because every other test here compares the two matrices, and two empty
        ones compare equal. """
        self.assertEqual(len(self.np), 64)
        self.assertEqual(len(self.ak), 64)

    def test_the_two_engines_agree_on_every_pair(self):
        self.assertEqual(sorted(self.np), sorted(self.ak),
                         "the two engines did not even see the same endpoints")
        differing = {k: (self.np[k], self.ak[k])
                     for k in self.np if self.np[k] != self.ak[k]}
        self.assertEqual(
            differing, {},
            "netplumber and apkeep disagree on %d of %d pairs (np, apkeep)"
            % (len(differing), len(self.np)))

    def test_both_engines_match_the_dataset_where_it_speaks(self):
        for pair, expected in _ORACLE.items():
            self.assertEqual(self.np[pair], expected,
                             "netplumber contradicts the oracle at %s" % (pair,))
            self.assertEqual(self.ak[pair], expected,
                             "apkeep contradicts the oracle at %s" % (pair,))

    def test_the_internet_reaches_hosts_through_the_DNAT(self):
        """ The dropped half of the original defect, as its own property. Every
        internet-sourced path crosses the gateway's DNAT; a translation that
        carries no rewrite leaves the public destination in place, and the cores
        have no route for it. """
        reached = sorted(p for (s, p), ok in self.ak.items()
                         if s == 'internet' and ok and p != 'internet')
        self.assertGreater(
            len(reached), 1,
            "apkeep has the internet reaching %s. A DNAT onto a subnet must "
            "reach more than one host; none is the signature of a rewrite that "
            "was never modelled." % reached)

    def test_a_leaf_denies_what_its_table_denies(self):
        """ The invented half. `dc2_leaf7_host6` publishes no service, so its
        leaf table denies its own prefix outright -- and under a
        destination-only translation that deny and the permits above it landed
        at one priority, which is how the cell came out reachable. """
        self.assertFalse(self.ak[('dc2_leaf7_host6', 'dc2_leaf7_host6')])
        self.assertFalse(self.ak[('dc4_leaf3_host22', 'dc2_leaf7_host6')])


if __name__ == '__main__':
    unittest.main()
