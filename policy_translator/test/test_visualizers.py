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

""" The two Graphviz visualizers are user tools the owner KEPT (2026-10-14);
this pins the DOT source each one builds.

Both are scripts run in-process with `runpy.run_path` and a patched
`sys.argv`. No Graphviz binary is needed: `graphviz.Digraph.render` is
replaced by a stub that records the DOT source it was asked to render, and
`os.popen` (their `inkscape` call) is mocked. Nothing is written anywhere.

Both read FPL through `PolicyBuilder`, the translator's own parser, since
TODO item 53. Before, each had a tokenizer of its own that read only `def`
blocks (every committed `wl_*/inventory.txt` uses `describe`), needed a
port on every service, skipped rules not written as exactly three
space-separated tokens, and failed on `Role.Service` targets.
"""

import contextlib
import io
import os
import runpy
import sys
import tempfile
import unittest
from unittest import mock

import graphviz


_PT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_POLICIES = os.path.join(_PT, 'visualize_policies.py')
_ROLES_AND_SERVICES = os.path.join(_PT, 'visualize_roles_and_services.py')
_IFI = os.path.join(_PT, 'examples', 'ifi-policy.txt')
_GENERIC_FW = os.path.join(
    os.path.dirname(_PT), 'fave', 'bench', 'wl_generic_fw', 'default')

_INVENTORY = """describe role Clients
end

def role Office
\tincludes Clients
end

def role Web
\toffers HTTP
end

def service HTTP
\tprotocol = 'tcp'
\tport = 80
end
"""

_POLICY = """describe policies(default: deny)
\tClients ---> Web.HTTP
\tOffice    <->>   Web
\tWeb ---> Clients
end
"""


def _run(script, args):
    """ Runs `script` as `__main__`. Returns (DOT source or None, render
    call args, popen mock, stdout, exit code). """
    rendered = {}

    def fake_render(self, *a, **k):
        rendered['source'] = self.source
        rendered['call'] = (a, k)

    out = io.StringIO()
    saved = sys.argv
    sys.argv = [script] + args
    code = None
    try:
        with mock.patch.object(graphviz.Digraph, 'render', fake_render), \
                mock.patch('os.popen') as popen, \
                contextlib.redirect_stdout(out):
            runpy.run_path(script, run_name='__main__')
    except SystemExit as exc:
        code = exc.code
    finally:
        sys.argv = saved
    return (rendered.get('source'), rendered.get('call'), popen,
            out.getvalue(), code)


class TestVisualizePolicies(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.inventory = os.path.join(self._tmp.name, 'inventory.txt')
        self.policy = os.path.join(self._tmp.name, 'policy.txt')
        with open(self.inventory, 'w') as f:
            f.write(_INVENTORY)
        with open(self.policy, 'w') as f:
            f.write(_POLICY)

    def tearDown(self):
        self._tmp.cleanup()

    def test_dot_source(self):
        """ Every rule is an edge labelled with its operator and service,
        whatever its spacing; a drawn group is linked to its drawn members. """
        source, call, popen, _out, code = _run(
            _POLICIES, [self.inventory, self.policy])
        self.assertIsNone(code)
        self.assertEqual(source.splitlines(), [
            'digraph {',
            '\tClients [shape=rectangle]',
            '\tWeb [shape=rectangle]',
            '\tClients -> Web [label="---> HTTP" color=red]',
            '\tOffice [shape=rectangle]',
            '\tOffice -> Web [label="<->>" color=red]',
            '\tWeb -> Clients [label="--->" color=red]',
            '\tOffice -> Clients [arrowhead=open arrowtail=odiamond dir=both]',
            '}',
        ])
        self.assertEqual(call, (('policies',), {'cleanup': True}))
        popen.assert_called_once_with(
            'inkscape --export-pdf=policies.pdf policies.svg')

    def test_a_forbidding_rule_is_blue_and_dashed(self):
        with open(self.policy, 'w') as f:
            f.write("describe policies(default: allow)\n\tClients --/-> Web\nend\n")
        source, _c, _p, _o, code = _run(_POLICIES, [self.inventory, self.policy])
        self.assertIsNone(code)
        self.assertIn('\tClients -> Web [label="--/->" color=blue style=dashed]',
                      source.splitlines())

    def test_a_committed_workload(self):
        source, _c, _p, _o, code = _run(_POLICIES, [
            os.path.join(_GENERIC_FW, 'inventory.txt'),
            os.path.join(_GENERIC_FW, 'policy.txt')])
        self.assertIsNone(code)
        self.assertIn('\tAllClients -> WebServer [label="<->> HTTP" color=red]',
                      source.splitlines())

    def test_wrong_argument_count_exits_1(self):
        source, _call, popen, out, code = _run(_POLICIES, [self.inventory])
        self.assertEqual((code, out), (1, "no file to visualize. quit.\n"))
        self.assertIsNone(source)
        popen.assert_not_called()

    def test_missing_files_exit_2(self):
        missing = os.path.join(self._tmp.name, 'missing.txt')
        _s, _c, _p, out, code = _run(_POLICIES, [missing, self.policy])
        self.assertEqual((code, out), (2, "not a file: %s. quit.\n" % missing))
        _s, _c, _p, out, code = _run(_POLICIES, [self.inventory, missing])
        self.assertEqual((code, out), (2, "not a file: %s. quit.\n" % missing))


class TestVisualizeRolesAndServices(unittest.TestCase):

    def test_dot_source_of_ifi_policy(self):
        source, call, popen, _out, code = _run(_ROLES_AND_SERVICES, [_IFI])
        self.assertIsNone(code)
        lines = source.splitlines()
        self.assertEqual((lines[0], lines[-1]), ('digraph {', '}'))
        for role in ('Internet', 'AdminNetz', 'Sekretariate', 'TrustedClients',
                     'UntrustedClients', 'Webserver', 'Server', 'Intern',
                     'MitInternetzugriff', 'All'):
            self.assertIn('\t%s [shape=rectangle]' % role, lines)
        incl = ' [arrowhead=open arrowtail=odiamond dir=both]'
        self.assertIn('\tServer -> Webserver' + incl, lines)
        self.assertIn('\tHTTP [label="HTTP,\nproto: tcp,\nport: 80"]', source)
        self.assertIn('\tHTTPS [label="HTTPS,\nproto: tcp,\nport: 443"]', source)
        offer = ' [arrowhead=open style=dashed]'
        self.assertEqual(
            [line for line in lines if line.endswith(offer)],
            ['\tWebserver -> HTTP' + offer, '\tWebserver -> HTTPS' + offer])
        self.assertEqual(call, (('roles_and_services',), {'cleanup': True}))
        popen.assert_called_once_with(
            'inkscape --export-pdf=roles_and_services.pdf '
            'roles_and_services.svg')

    def test_each_node_is_declared_once(self):
        """ The old tokenizer declared a member twice when its group came
        first (TODO item 53). """
        with tempfile.TemporaryDirectory() as tmp:
            inventory = os.path.join(tmp, 'inventory.txt')
            with open(inventory, 'w') as f:
                f.write("def role Member\n\toffers SSH\nend\n\n"
                        "def role Group\n\tincludes Member\nend\n\n"
                        "def service SSH\n\tprotocol = 'tcp'\n\tport = 22\n"
                        "end\n")
            source, _c, _p, _o, code = _run(_ROLES_AND_SERVICES, [inventory])
        self.assertIsNone(code)
        self.assertEqual(source.splitlines(), [
            'digraph {',
            '\tInternet [shape=rectangle]',
            '\tMember [shape=rectangle]',
            '\tGroup [shape=rectangle]',
            '\tGroup -> Member [arrowhead=open arrowtail=odiamond dir=both]',
            '\tSSH [label="SSH,',
            'proto: tcp,',
            'port: 22"]',
            '\tMember -> SSH [arrowhead=open style=dashed]',
            '}',
        ])

    def test_service_without_port(self):
        """ `protocol = 'icmp'` alone is valid FPL; it once raised KeyError. """
        with tempfile.TemporaryDirectory() as tmp:
            inventory = os.path.join(tmp, 'inventory.txt')
            with open(inventory, 'w') as f:
                f.write("def service ICMP\n\tprotocol = 'icmp'\nend\n")
            source, _c, _p, _o, code = _run(_ROLES_AND_SERVICES, [inventory])
        self.assertIsNone(code)
        self.assertIn('\tICMP [label="ICMP,\nproto: icmp"]', source)

    def test_describe_spelled_inventory(self):
        """ Every committed wl_*/inventory.txt uses `describe`; it once raised
        KeyError. """
        source, _c, _p, _o, code = _run(
            _ROLES_AND_SERVICES, [os.path.join(_GENERIC_FW, 'inventory.txt')])
        self.assertIsNone(code)
        self.assertIn('\tWebServer -> HTTP [arrowhead=open style=dashed]',
                      source.splitlines())

    def test_wrong_argument_count_exits_1(self):
        source, _c, popen, out, code = _run(_ROLES_AND_SERVICES, [])
        self.assertEqual((code, out), (1, "no file to visualize. quit.\n"))
        self.assertIsNone(source)
        popen.assert_not_called()

    def test_missing_file_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = os.path.join(tmp, 'missing.txt')
            _s, _c, _p, out, code = _run(_ROLES_AND_SERVICES, [missing])
        self.assertEqual((code, out), (2, "not a file: %s. quit.\n" % missing))


if __name__ == '__main__':
    unittest.main()
