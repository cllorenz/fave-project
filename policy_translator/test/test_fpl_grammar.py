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

""" `fpl_grammar.py` is the REFERENCE FPL grammar, and it still agrees with
`PolicyBuilder` on every committed policy it can read (owner, 2026-10-14).

Two parsers read FPL: the old pyparsing grammar here and the regex parser in
`policy_builder.py`, which is the one the translator uses. The owner kept the
grammar as the reference, which only means something while the two agree, so
this file parses every COMMITTED FPL input with both and compares what they
say the file contains:

  * the same roles, and the same split into atomic roles and superroles;
  * each superrole's members, after flattening nested superroles;
  * each atomic role's services and attributes, once a superrole's `offers`
    and attributes are pushed down onto its members -- the semantics
    `Superrole.add_service` / `Superrole.add_attribute` implement, applied
    to the grammar's tree by `_inventory_model` below;
  * the same services with the same protocol and port;
  * the same default policy and the same set of (from, to, service, operator)
    rules -- `Policy.raw_policies` is the builder's verbatim record of them.

Values are compared as text: the grammar keeps `vlan = 1` as `'1'` and strips
the quotes of `'tcp'`; the builder `ast.literal_eval`s both. That is a
difference of representation, not of content.

The inputs are `examples/ifi-policy.txt`, `examples/up-policy.txt`, and the
committed inventory+policy pairs of `wl_shadow` and `wl_generic_fw`.

`examples/fml-paper-policy.txt` is the one they DISAGREE on, and it is pinned
separately (`TestFmlPaperPolicy`): the builder refuses it, the grammar returns
the first nine roles and drops the rest of the file without an error.

`print_prosa` and `main` are covered too, including one defect in
`print_prosa`'s operator table (`TestPrintProsa.test_forbidding_stateful...`).
"""

import contextlib
import io
import os
import runpy
import sys
import tempfile
import unittest
import warnings

import pyparsing as pp

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fpl_grammar
from policy import Policy, Superrole
from policy_builder import PolicyBuilder
from policy_exceptions import UnknownProtocolException


_PT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO = os.path.dirname(_PT)

# Committed (`git ls-files`) FPL inputs, as the file lists the translator is
# given: an inventory followed by a policy, or one file holding both.
_CORPORA = {
    'ifi': [os.path.join(_PT, 'examples', 'ifi-policy.txt')],
    'up': [os.path.join(_PT, 'examples', 'up-policy.txt')],
    'wl_shadow': [
        os.path.join(_REPO, 'fave', 'bench', 'wl_shadow', 'inventory.txt'),
        os.path.join(_REPO, 'fave', 'bench', 'wl_shadow', 'policy.txt'),
    ],
    'wl_generic_fw': [
        os.path.join(_REPO, 'fave', 'bench', 'wl_generic_fw', 'default',
                     'inventory.txt'),
        os.path.join(_REPO, 'fave', 'bench', 'wl_generic_fw', 'default',
                     'policy.txt'),
    ],
}

_FML = os.path.join(_PT, 'examples', 'fml-paper-policy.txt')


def _read(paths):
    """ Joined like `policy_translator.py` joins its FILE arguments. """
    chunks = []
    for path in paths:
        with open(path, 'r') as f:
            chunks.append(f.read())
    return "\n".join(chunks)


@contextlib.contextmanager
def _quiet(out=None):
    """ Captures stdout, and silences pyparsing's deprecation warnings: the
    grammar uses the camelCase API pyparsing 3 deprecated, which says nothing
    about the grammar and would put ~900 warnings in the tier's log. """
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', pp.PyparsingDeprecationWarning)
        with contextlib.redirect_stdout(out if out is not None else io.StringIO()):
            yield


def _parse(text):
    """ `parse_fpl` prints its result; keep that out of the test log. """
    with _quiet():
        return fpl_grammar.parse_fpl(text)


def _prosa(tree):
    out = io.StringIO()
    with _quiet(out):
        fpl_grammar.print_prosa(tree)
    return out.getvalue().splitlines()


def _norm(value):
    """ Text form of a value: a list of strings or a string. """
    if isinstance(value, list):
        return [str(v) for v in value]
    return str(value)


def _inventory_model(tree):
    """ Applies FPL's inheritance to the grammar's tree.

    Returns (atomic roles -> {'attrs', 'offers'}, superroles -> member set,
    services -> attributes), in the shape `_built` reads off a Policy. A
    superrole's members are flattened (an included superrole contributes its
    members), and its `offers` and attributes are written into every member,
    in file order -- as `PolicyBuilder.build_roles_and_services` does.
    """
    atomic, supers, services = {}, {}, {}
    for entry in tree:
        if entry[0] == 'service':
            services[entry[1]] = {k: _norm(v) for k, v in entry[2:]}
        elif entry[0] == 'role':
            name, body = entry[1], entry[2:]
            includes = [v for k, v in body if k == 'includes']
            offers = [v for k, v in body if k == 'offers']
            fields = [(k, v) for k, v in body if k not in ('includes', 'offers')]
            if includes:
                members = []
                for inc in includes:
                    members += supers[inc] if inc in supers else [inc]
                supers[name] = members
            else:
                atomic[name] = {'attrs': {}, 'offers': set()}
                members = [name]
            for member in members:
                if member in atomic:
                    atomic[member]['offers'] |= set(offers)
                    atomic[member]['attrs'].update(
                        {k: _norm(v) for k, v in fields})
    return atomic, {k: set(v) for k, v in supers.items()}, services


def _built(policy):
    """ The same three views read off a built Policy (without the implicit
    `Internet` role, which the grammar knows nothing about). """
    atomic = {
        name: {
            'attrs': {k: _norm(v) for k, v in role.attributes.items()},
            'offers': set(role.services),
        }
        for name, role in policy.roles.items()
        if not isinstance(role, Superrole) and name != 'Internet'
    }
    supers = {
        name: set(role.subroles)
        for name, role in policy.roles.items() if isinstance(role, Superrole)
    }
    services = {
        name: {k: _norm(v) for k, v in service.attributes.items()}
        for name, service in policy.services.items()
    }
    return atomic, supers, services


def _grammar_rules(tree):
    """ (default, {(from, to, service, operator)}) of the policies block. """
    blocks = [entry for entry in tree if entry[0] == 'policies']
    assert len(blocks) == 1, blocks
    default, rules = blocks[0][1], blocks[0][2:]
    return default, {
        (subject, obj[0], obj[1] if len(obj) > 1 else None, operator)
        for subject, operator, obj in rules
    }


class TestGrammarAgreesWithBuilder(unittest.TestCase):
    """ Both parsers read the same content out of every committed policy. """

    def _both(self, name):
        text = _read(_CORPORA[name])
        policy = Policy()
        PolicyBuilder.build(text, policy)
        return _parse(text), policy

    def test_corpora_are_committed_inputs(self):
        for name, paths in _CORPORA.items():
            for path in paths:
                self.assertTrue(os.path.isfile(path), (name, path))

    def test_same_roles_and_services(self):
        for name in _CORPORA:
            with self.subTest(corpus=name):
                tree, policy = self._both(name)
                self.assertEqual(
                    sorted(e[1] for e in tree if e[0] == 'role'),
                    sorted(r for r in policy.roles if r != 'Internet'))
                self.assertEqual(
                    sorted(e[1] for e in tree if e[0] == 'service'),
                    sorted(policy.services))

    def test_same_inventory_content(self):
        for name in _CORPORA:
            with self.subTest(corpus=name):
                tree, policy = self._both(name)
                model, built = _inventory_model(tree), _built(policy)
                self.assertEqual(model[0], built[0], "atomic roles")
                self.assertEqual(model[1], built[1], "superrole members")
                self.assertEqual(model[2], built[2], "services")

    def test_same_policy_rules(self):
        for name in _CORPORA:
            with self.subTest(corpus=name):
                tree, policy = self._both(name)
                default, rules = _grammar_rules(tree)
                self.assertEqual(policy.default_policy, default == 'allow')
                self.assertEqual(rules, set(policy.raw_policies))
                self.assertTrue(rules)

    def test_inventory_sizes_are_pinned(self):
        """ So an agreement on two EMPTY parses could not pass unnoticed. """
        sizes = {}
        for name in _CORPORA:
            tree = _parse(_read(_CORPORA[name]))
            sizes[name] = (
                sum(1 for e in tree if e[0] == 'role'),
                sum(1 for e in tree if e[0] == 'service'),
                len(_grammar_rules(tree)[1]),
            )
        self.assertEqual(sizes, {
            'ifi': (9, 2, 10),
            'up': (116, 36, 33),
            'wl_shadow': (2, 0, 1),
            'wl_generic_fw': (3, 2, 3),
        })

    def test_all_six_operators_agree(self):
        """ The committed corpora use three operators; this covers the other
        three, under `default: allow` where they mean something. """
        text = (
            "def role A\n\toffers S\nend\n\n"
            "def role B\n\toffers S\nend\n\n"
            "def role G\n\tincludes A\n\tincludes B\nend\n\n"
            "def service S\n\tprotocol = 'tcp'\n\tport = 22\nend\n\n"
            "def policies(default: allow)\n"
            "\tA --/-> B.S\n"
            "\tA <-/-> B.*\n"
            "\tB -/->> A\n"
            "\tG ---> A\n"
            "\tG <--> B.S\n"
            "\tA <->> G\n"
            "end\n"
        )
        policy = Policy()
        PolicyBuilder.build(text, policy)
        tree = _parse(text)
        default, rules = _grammar_rules(tree)
        self.assertEqual(default, 'allow')
        self.assertEqual(rules, set(policy.raw_policies))
        self.assertEqual(
            {op for _f, _t, _s, op in rules},
            {'--/->', '<-/->', '-/->>', '--->', '<-->', '<->>'})
        model, built = _inventory_model(tree), _built(policy)
        self.assertEqual(model, built)


class TestFmlPaperPolicy(unittest.TestCase):
    """ `examples/fml-paper-policy.txt`, which both parsers refuse.

    The builder refuses it: `protocol = 'arp'` is not an IP protocol (TODO
    item 21), and the file also has `protocol = 1616`, `port = '67'` and a
    service without a protocol. The grammar refuses it too, since TODO item 53.
    `parse_fpl` once called `parseString` without `parseAll=True`, so it
    stopped at the first block it could not read -- `port = '67'` in `def
    service DHCP` -- and returned nine of thirteen roles, no services and no
    policies, as if that were the whole file.
    """

    def setUp(self):
        with open(_FML, 'r') as f:
            self.text = f.read()

    def test_builder_refuses_it(self):
        with self.assertRaises(UnknownProtocolException):
            PolicyBuilder.build(self.text, Policy())

    def test_grammar_rejects_what_it_cannot_consume(self):
        with self.assertRaises(pp.ParseException):
            _parse(self.text)


class TestGrammarShape(unittest.TestCase):
    """ What the grammar accepts and rejects, as the reference. """

    def test_policy_only_file_is_rejected(self):
        """ An inventory is required (`inventory` is `OneOrMore`); the builder
        refuses the same input with InvalidSyntaxException. """
        with self.assertRaises(pp.ParseException):
            _parse(_read(_CORPORA['wl_shadow'][1:]))

    def test_all_four_definition_keywords(self):
        tree = _parse(
            "def role A\nend\ndefine role B\nend\n"
            "describe role C\nend\ndesc role D\nend\n")
        self.assertEqual(tree, [['role', 'A'], ['role', 'B'],
                                ['role', 'C'], ['role', 'D']])

    def test_comments_and_wildcard_objects(self):
        tree = _parse(
            "# leading comment\n"
            "def role A\n\t# inside a role\n\tipv6 = 2001:db8::1/128\nend\n"
            "# between blocks\n"
            "def policies(default: deny)\n\t# inside\n\tA ---> A.*\nend\n")
        self.assertEqual(tree, [
            ['role', 'A', ['ipv6', '2001:db8::1/128']],
            ['policies', 'deny', ['A', '--->', ['A', '*']]],
        ])

    def test_self_tests_parse_every_production(self):
        out = io.StringIO()
        with _quiet(out):
            self.assertIsNone(fpl_grammar.parse_fpl('', use_tests=True))
        text = out.getvalue()
        self.assertEqual(text.count('test parsing '), 31)
        self.assertIn("['policies', 'deny', ['Clients', '<->>', "
                      "['WebServer', 'HTTP']]]", text)


class TestPrintProsa(unittest.TestCase):
    """ `print_prosa` renders the grammar's tree as English sentences. """

    def test_ifi_policy(self):
        lines = _prosa(_parse(_read(_CORPORA['ifi'])))
        self.assertEqual(len(lines), 22)
        self.assertEqual(lines[0], "The role AdminNetz has the attributes "
                         "hosts=['admin.cs.uni-potsdam.de'] and vlan=1.")
        self.assertIn("The service HTTPS runs on TCP port 443.", lines)
        self.assertIn("The role Webserver offers the services HTTP and HTTPS "
                      "and has the attributes "
                      "hosts=['webserver.cs.uni-potsdam.de'].", lines)
        self.assertIn("The role MitInternetzugriff includes the roles "
                      "AdminNetz, Sekretariate, UntrustedClients, "
                      "TrustedClients, Intern, and Server.", lines)
        self.assertIn("By default the policy denies accesses.", lines)
        self.assertIn("The role AdminNetz may access the role All "
                      "statefully.", lines)
        self.assertEqual(lines[-1], "The role Internet may access service "
                         "HTTPS offered by the role Webserver "
                         "unidirectionally.")

    def test_default_allow_and_wildcard_and_portless_service(self):
        lines = _prosa(_parse(
            "def role A\n\toffers S\nend\n"
            "desc service S\n\tprotocol = 'tcp'\n\tport = 22\nend\n"
            "desc service I\n\tprotocol = 'icmp'\nend\n"
            "define policies(default: allow)\n"
            "\tA --/-> A.S\n\tA <-/-> A.*\n\tA <-/-> A\nend\n"))
        self.assertEqual(lines, [
            "The role A offers the services S.",
            "The service S runs on TCP port 22.",
            "The service I runs on ICMP.",
            "By default the policy allows accesses.",
            "The role A may not access service S offered by the role A "
            "unidirectionally.",
            "The role A may not access all services offered by the role A "
            "bidirectionally.",
            "The role A may not access the role A bidirectionally.",
        ])

    def test_unknown_entry_aborts(self):
        lines = _prosa([['role', 'A'], ['bogus', 'x'], ['role', 'B']])
        self.assertEqual(lines, ["The role A.",
                                 "cannot handle entry: ['bogus', 'x']. Abort!"])

    def test_forbidding_stateful_operator_is_rendered(self):
        """ The operator table once spelled it `<-/->>`, which the grammar
        never produces, so this raised KeyError (TODO item 53). """
        lines = _prosa(_parse(
            "def role A\nend\n"
            "define policies(default: allow)\n\tA -/->> A\nend\n"))
        self.assertEqual(lines[-1],
                         "The role A may not access the role A statefully.")


class TestMain(unittest.TestCase):
    """ The command line: pprint of the tree, or prosa with `-p`. """

    def _run(self, argv, as_script=False):
        out = io.StringIO()
        with _quiet(out):
            if as_script:
                saved = sys.argv
                sys.argv = ['fpl_grammar.py'] + argv
                try:
                    runpy.run_path(os.path.join(_PT, 'fpl_grammar.py'),
                                   run_name='__main__')
                finally:
                    sys.argv = saved
            else:
                fpl_grammar.main(argv)
        return out.getvalue()

    def test_prosa_for_each_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            second = os.path.join(tmp, 'second.txt')
            with open(second, 'w') as f:
                f.write("def role Z\n\thosts = ['z']\nend\n")
            text = self._run(['-p', _CORPORA['ifi'][0], second])
        self.assertIn("By default the policy denies accesses.\n", text)
        self.assertTrue(text.endswith(
            "The role Z has the attributes hosts=['z'].\n"))

    def test_pprint_by_default(self):
        text = self._run([_CORPORA['wl_generic_fw'][0]])
        self.assertIn("[   ['service', 'HTTP', ['protocol', 'tcp'], "
                      "['port', '80']],", text)

    def test_script_entry_point_runs_self_tests(self):
        text = self._run(['-t', _CORPORA['ifi'][0]], as_script=True)
        self.assertEqual(text.count('test parsing '), 31)
        self.assertTrue(text.endswith('None\n'))

    def test_missing_file_argument_is_a_usage_error(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                fpl_grammar.main([])
        self.assertEqual(cm.exception.code, 2)


if __name__ == '__main__':
    unittest.main()
