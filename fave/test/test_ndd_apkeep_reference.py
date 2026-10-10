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

""" NDD-APKeep against the authors' reference APKeep(NDD), on a FaVe workload
(APKEEP_INCREMENTAL_SCOPE.md §4; owner decision B, 2026-10-10).

NDD-APKeep is APKeep's own elements over an atom layer ported from the NDD
repository's reference code. This holds the port to the original: the same
forwarding workload -- wl_airtel1's 39,600 routes, as the APKeep adapter
translates them -- is built by the reference (`NetworkNDDAP`, its own batch
insertion and re-atomization) and by NDD-APKeep (`Network(name, "ndd")`, rule
by rule), each in its own JVM because the two declare different NDD field
layouts. Every element port's destination set must be the same -- compared as
canonical lists of maximal prefixes, so the layouts do not matter -- and so
must the number of destination atoms after re-atomization.

Insertions only, and destination FIBs only: that is all the reference
implements (`APKEEP_INCREMENTAL_SCOPE.md` §1). Harness:
`org.ants.jndd.fave.ReferenceApkeepDump` and `apkeep.ndd.IrDump`.
"""

import logging
import os
import shutil
import subprocess
import tempfile
import unittest

from apkeep.adapter import APKeepAdapter
from apkeep.lib_apkeep import _APKEEP_JAR, _NDD_JAR
from test.backend_gate import require_or_skip
from test.incremental_oracle import inputs_present

_JAVA_HOME = os.environ.get('JAVA_HOME') or '/usr/lib/jvm/java-11-openjdk-amd64'
_JAVA = os.path.join(_JAVA_HOME, 'bin', 'java')
if not os.path.exists(_JAVA):
    _JAVA = shutil.which('java')

_ready = bool(_JAVA) and os.path.isfile(_APKEEP_JAR) and os.path.isfile(_NDD_JAR)


def _write_inputs(prefix, out):
    """ The adapter's translation of `prefix`, in the dump tools' text files. """
    from util.in_process_driver import InProcessFaVe
    log = logging.getLogger("test_ndd_apkeep_reference")
    log.setLevel(logging.ERROR)
    adapter = APKeepAdapter(log, engine='bdd', _shadow=True)   # translates only
    with InProcessFaVe(adapter) as fave:
        fave.replay(prefix)
        t = adapter._translate()
    assert all(r.split()[1] == 'fwd' for r in t['rules']), "destination FIBs only"
    edge_ports = sorted({' '.join(e.split()[:2]) for e in t['edges']
                         if e.split()[2].startswith('probe.')})
    for name, lines in (('topology', t['edges']), ('devices', t['fwd_devices'] or []),
                        ('rules', t['rules']), ('edge_ports', edge_ports)):
        with open(os.path.join(out, name + '.txt'), 'w') as handle:
            handle.write('\n'.join(lines) + '\n')
    return t


def _dump(main, classpath, inputs, out):
    subprocess.run([_JAVA, '-Xmx8g', '-cp', classpath, main, inputs, out],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                   timeout=3600)
    ports, meta = {}, {}
    with open(out) as handle:
        for line in handle:
            if line.startswith('#'):
                key, value = line[1:].split()
                meta[key] = value
                continue
            element, port, consistent, prefixes = line.rstrip('\n').split(' ', 3)
            ports[(element, port)] = (consistent, prefixes)
    return ports, meta


@require_or_skip(_ready, "a JDK, the APKeep jar or the NDD jar is unavailable")
class TestAgainstTheReference(unittest.TestCase):

    def test_wl_airtel1(self):
        prefix = 'bench/wl_airtel1'
        if not inputs_present(prefix):
            require_or_skip(False, "%s inputs not generated" % prefix)(lambda: None)()
            self.skipTest("%s inputs not generated" % prefix)
        work = tempfile.mkdtemp(prefix='ndd_apkeep_ref_')
        try:
            t = _write_inputs(prefix, work)
            ref, ref_meta = _dump('org.ants.jndd.fave.ReferenceApkeepDump', _NDD_JAR,
                                  work, os.path.join(work, 'ref.txt'))
            ours, our_meta = _dump('apkeep.ndd.IrDump', _APKEEP_JAR + os.pathsep + _NDD_JAR,
                                   work, os.path.join(work, 'ours.txt'))
        finally:
            shutil.rmtree(work, ignore_errors=True)
        self.assertEqual(set(ref), set(ours), "the two networks have different ports")
        # non-vacuous: every route ends up on some port
        self.assertGreater(sum(len(p.split(',')) for _c, p in ours.values() if p != '-'),
                           len(t['rules']))
        differing = [k for k in ours if ours[k][1] != ref[k][1]]
        self.assertEqual(differing, [], "ports whose destination sets differ")
        self.assertTrue(all(c == 'true' for c, _p in ours.values()),
                        "an NDD-APKeep molecule differs from its predicate")
        self.assertTrue(all(c == 'true' for c, _p in ref.values()),
                        "a reference molecule differs from its predicate")
        self.assertEqual(our_meta['atoms'], ref_meta['atoms'],
                         "destination atoms after re-atomization")


if __name__ == '__main__':
    unittest.main()
