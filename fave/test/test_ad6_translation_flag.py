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

""" AD6_PLAN.md §9: the `translation` selector on Ad6Adapter, and the boundary
the structural payload crosses.

Since §9.25 there is only ONE translation. The selector survives the deletion
of the second one because a result file must still say what produced it -- a
number stamped `structural` is not comparable with one stamped `semantic`, and
the tree can no longer produce the latter at all. """

import logging
import unittest

import lxml.etree as et

from ad6.adapter import Ad6Adapter, TRANSLATIONS, TRANSLATION_STRUCTURAL
from util.in_process_driver import InProcessFaVe


def _adapter(**kwargs):
    log = logging.getLogger("test_ad6_translation_flag")
    log.setLevel(logging.CRITICAL)
    return Ad6Adapter(log, **kwargs)


class TestTranslationSelector(unittest.TestCase):

    def test_the_default_is_structural(self):
        self.assertEqual(_adapter().translation, TRANSLATION_STRUCTURAL)

    def test_structural_is_the_only_vocabulary(self):
        self.assertEqual(TRANSLATIONS, (TRANSLATION_STRUCTURAL,))
        self.assertEqual(TRANSLATION_STRUCTURAL, 'structural')

    def test_every_accepted_translation_round_trips(self):
        for translation in TRANSLATIONS:
            with self.subTest(translation=translation):
                self.assertEqual(
                    _adapter(translation=translation).translation, translation)

    def test_an_unknown_translation_is_refused(self):
        """ Loudly, at construction. A silent fallback would mis-stamp whatever
        measurement followed. """
        with self.assertRaises(ValueError):
            _adapter(translation='structrual')          # sic

    def test_the_DELETED_semantic_translation_is_refused_by_name(self):
        """ §9.25. Asking for the deleted path must not quietly get the
        surviving one: that would answer a DIFFERENT question under the
        requested label, which is the whole failure mode §9.23 documents. The
        refusal names the commit that still has it, because "reproduce the
        archived number" is the only reason to ask. """
        with self.assertRaises(ValueError) as caught:
            _adapter(translation='semantic')

        message = str(caught.exception)
        self.assertIn('semantic', message)
        self.assertIn('86114970', message,
                      "the refusal must say WHERE the deleted path still "
                      "lives, or an archived measurement is simply lost")
        self.assertIn('§9.25', message)

    def test_the_stamp_reports_the_translation_and_grounding(self):
        """ And nothing else: `faithful_vlan`/`probe_untag` were semantic-path
        flags (§9.16.1 -- they never applied to a structural model) and went
        with it. An archived stamp carrying them came from a run this tree
        cannot reproduce. """
        self.assertEqual(_adapter().configuration_stamp(),
                         {"translation": "structural", "grounding": "rank"})

    def test_the_deleted_flags_are_gone_from_the_constructor(self):
        """ Not silently ignored -- gone. A caller still passing
        `faithful_vlan=True` was configuring the semantic path and must hear
        about it rather than get an unflagged structural answer. """
        for flag in ('faithful_vlan', 'probe_untag'):
            with self.subTest(flag=flag):
                with self.assertRaises(TypeError):
                    _adapter(**{flag: True})


class TestStructuralPayloadBoundary(unittest.TestCase):
    """ The serialized config has to survive the subprocess boundary, and the
    way it can fail is SILENT. """

    def test_the_namespace_does_not_survive_serialization(self):
        """ GenUtils.config() declares xmlns="http://config" on the root while
        every child carries no namespace -- consistent in memory, where ad6's
        unprefixed xpaths match. Serialize it and that declaration becomes the
        document's DEFAULT namespace, so on re-parse every descendant is in it
        and every one of those xpaths matches NOTHING: no error, just an empty
        model. The adapter re-roots onto a plain <config>; this pins that. """
        from ad6 import translate
        from rule.rule_model import Forward, Match, Rule, RuleField

        devices = {'a': {'tables': {'a.t0': [Rule('a', 'a.t0', 0,
                                                  in_ports=['a.in'],
                                                  match=Match([RuleField(
                                                      'packet.ipv4.destination',
                                                      '10.0.0.0/8')]),
                                                  actions=[Forward(['a.out'])])]},
                         'ports': ['in', 'out'], 'wiring': []}}
        config, _edges = translate.model_to_config(devices, [])

        plain = et.Element('config')
        for child in list(config):
            plain.append(child)
        round_tripped = et.fromstring(et.tostring(plain))

        self.assertTrue(round_tripped.xpath('//firewall[@key]'),
                        "ad6's own unprefixed xpaths must match after a round "
                        "trip, or the bridge silently builds an empty model")

    def test_the_namespaced_root_WOULD_have_broken_it(self):
        """ The negative control: without re-rooting, the same xpath finds
        nothing -- which is exactly the silent failure above. """
        from ad6 import translate
        config, _edges = translate.model_to_config({}, [])
        round_tripped = et.fromstring(et.tostring(config))
        self.assertEqual(round_tripped.xpath('//firewalls'), [],
                         "if this ever starts matching, lxml's namespace "
                         "round-trip changed and the re-rooting can be revisited")


if __name__ == '__main__':
    unittest.main()
