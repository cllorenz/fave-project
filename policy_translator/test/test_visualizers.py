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

Both are scripts with all their logic under `if __name__ == '__main__'`, so
they are run in-process with `runpy.run_path` and a patched `sys.argv`. No
Graphviz binary is needed: `graphviz.Digraph.render` is replaced by a stub
that records the DOT source it was asked to render, and `os.popen` (their
`inkscape` call) is mocked. Nothing is written anywhere.

Both scripts tokenise lines with `split(' ')` and recognise only the `def`
keyword, which is narrower than FPL:

  * `visualize_roles_and_services.py` reads `examples/ifi-policy.txt` as
    expected, but on an inventory spelled with `describe` -- every committed
    `fave/bench/wl_*/inventory.txt` -- it fails with KeyError('') at line 58,
    because the `describe service` header was not recognised; and a service
    without a `port` (`protocol = 'icmp'`) fails with KeyError('port') at
    line 81. Both pinned as expectedFailures.
  * `visualize_policies.py` reads rules of exactly three space-separated
    tokens, and looks the target up as a ROLE: a rule naming a service
    (`X <->> Web.HTTP`) fails with KeyError('Web.HTTP') at line 104. A rule
    aligned with extra blanks or tabs between its tokens, as in
    `examples/*.txt`, is silently skipped. So it is fed a small policy written in the
    style it reads, plus an expectedFailure for the service form.
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
_GENERIC_FW_INVENTORY = os.path.join(
    os.path.dirname(_PT), 'fave', 'bench', 'wl_generic_fw', 'default',
    'inventory.txt')

_INVENTORY = """# roles in the style the visualizers read
def role Clients
end

def role Office
\tincludes Clients
end

def role Web
end

def role Team
	includes Clients
end
"""

_POLICY = """describe policies(default: deny)
# Clients first: a sub-edge is drawn only to a role already drawn.
Clients ---> Web
Office <->> Web
Office <-->  Web
\tWeb ---> Clients
Web ---> Team
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
        source, call, popen, _out, code = _run(
            _POLICIES, [self.inventory, self.policy])
        self.assertIsNone(code)
        # Every operator is drawn alike, and the rule with two blanks before
        # its target is not read at all (four tokens).
        reach = ' [arrowhead=openopen arrowtail=open color=red dir=both]'
        self.assertEqual(source.splitlines(), [
            'digraph {',
            '\tClients [shape=rectangle]',
            '\tWeb [shape=rectangle]',
            '\tClients -> Web' + reach,
            '\tOffice [shape=rectangle]',
            '\tOffice -> Web' + reach,
            '\tOffice -> Clients [arrowhead=open arrowtail=odiamond dir=both]',
            '\tWeb -> Clients' + reach,
            '\tTeam [shape=rectangle]',
            '\tWeb -> Team' + reach,
            '\tTeam -> Clients [arrowhead=open arrowtail=odiamond dir=both]',
            '}',
        ])
        self.assertEqual(call, (('policies',), {'cleanup': True}))
        popen.assert_called_once_with(
            'inkscape --export-pdf=policies.pdf policies.svg')

    # DEFECT (visualize_policies.py:104): the target of `X ---> Y.SERVICE` is
    # looked up as a role. Remove the decorator once `Y.SERVICE` is read.
    @unittest.expectedFailure
    def test_rule_naming_a_service(self):
        with open(self.policy, 'w') as f:
            f.write("Clients <->> Web.HTTP\n")
        source, _call, _popen, _out, _code = _run(
            _POLICIES, [self.inventory, self.policy])
        self.assertIn('Clients ->', source)

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
        self.assertEqual(lines[0], 'digraph {')
        self.assertEqual(lines[-1], '}')
        for role in ('AdminNetz', 'Sekretariate', 'TrustedClients',
                     'UntrustedClients', 'Webserver', 'Server', 'Intern',
                     'MitInternetzugriff', 'All'):
            self.assertIn('\t%s [shape=rectangle]' % role, lines)
        incl = ' [arrowhead=open arrowtail=odiamond dir=both]'
        self.assertIn('\tServer -> Webserver' + incl, lines)
        self.assertEqual(
            sum(1 for line in lines if line.endswith(incl)), 13)
        # The protocol keeps its FPL quotes.
        self.assertIn('\tHTTP [label="HTTP,\nproto: \'tcp\',\nport: 80"]',
                      source)
        self.assertIn('\tHTTPS [label="HTTPS,\nproto: \'tcp\',\nport: 443"]',
                      source)
        offer = ' [arrowhead=open style=dashed]'
        self.assertEqual(
            [line for line in lines if line.endswith(offer)],
            ['\tWebserver -> HTTP' + offer, '\tWebserver -> HTTPS' + offer])
        self.assertEqual(call, (('roles_and_services',), {'cleanup': True}))
        popen.assert_called_once_with(
            'inkscape --export-pdf=roles_and_services.pdf '
            'roles_and_services.svg')

    def test_group_declared_before_its_member(self):
        """ A member not yet drawn is drawn on the spot. Line 75 then records
        the GROUP as seen instead of the member (`seen.append(role)`), so the
        member's own block declares its node a second time -- harmless in
        DOT, pinned so a fix shows up here. """
        with tempfile.TemporaryDirectory() as tmp:
            inventory = os.path.join(tmp, 'inventory.txt')
            with open(inventory, 'w') as f:
                f.write("def role Group\n\tincludes Member\n\toffers SSH\n"
                        "end\n\ndef role Member\nend\n\n"
                        "def service SSH\n\tprotocol = 'tcp'\n\tport = 22\n"
                        "end\n")
            source, _c, _p, _o, code = _run(_ROLES_AND_SERVICES, [inventory])
        self.assertIsNone(code)
        self.assertEqual(source.splitlines(), [
            'digraph {',
            '\tGroup [shape=rectangle]',
            '\tMember [shape=rectangle]',
            '\tGroup -> Member [arrowhead=open arrowtail=odiamond dir=both]',
            '\tMember [shape=rectangle]',
            '\tSSH [label="SSH,',
            "proto: 'tcp',",
            'port: 22"]',
            '\tGroup -> SSH [arrowhead=open style=dashed]',
            '}',
        ])

    # DEFECT (visualize_roles_and_services.py:81): the label reads
    # services[s]['port'], so a service without a port -- `protocol =
    # 'icmp'`, valid FPL -- raises KeyError('port'). Remove the decorator
    # once a missing port is rendered.
    @unittest.expectedFailure
    def test_service_without_port(self):
        with tempfile.TemporaryDirectory() as tmp:
            inventory = os.path.join(tmp, 'inventory.txt')
            with open(inventory, 'w') as f:
                f.write("def service ICMP\n\tprotocol = 'icmp'\nend\n")
            source, _c, _p, _o, _code = _run(_ROLES_AND_SERVICES, [inventory])
        self.assertIn('ICMP', source)

    # DEFECT (visualize_roles_and_services.py:58): only `def` opens a block,
    # so `describe service HTTP` is not seen and its `protocol` line indexes
    # services[''] -- KeyError. Every committed wl_*/inventory.txt is written
    # with `describe`. Remove the decorator once `describe` is accepted.
    @unittest.expectedFailure
    def test_describe_spelled_inventory(self):
        source, _c, _p, _o, _code = _run(
            _ROLES_AND_SERVICES, [_GENERIC_FW_INVENTORY])
        self.assertIn('WebServer -> HTTP', source)

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
