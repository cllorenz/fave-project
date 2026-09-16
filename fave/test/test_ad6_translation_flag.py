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

""" AD6_PLAN.md §9 Phase 2: the `translation` selector on Ad6Adapter, and the
boundary the structural payload crosses. """

import logging
import unittest

import lxml.etree as et

from ad6.adapter import (
    Ad6Adapter, TRANSLATIONS, TRANSLATION_SEMANTIC, TRANSLATION_STRUCTURAL,
)
from util.in_process_driver import InProcessFaVe


def _adapter(**kwargs):
    log = logging.getLogger("test_ad6_translation_flag")
    log.setLevel(logging.CRITICAL)
    return Ad6Adapter(log, **kwargs)


class TestTranslationSelector(unittest.TestCase):

    def test_the_default_is_structural(self):
        """ AD6_PLAN.md §9.3 Phase 5. The default flipped once the differential
        agreed on every benchmark in scope; before that it was 'semantic',
        because switching earlier would have silently re-measured every
        archived result. It still would -- which is why `semantic` remains
        selectable and why this pins the direction rather than merely checking
        that SOME default exists. """
        self.assertEqual(_adapter().translation, TRANSLATION_STRUCTURAL)

    def test_semantic_is_still_reachable(self):
        """ Guards the flip: archived numbers came from the semantic path, so
        reproducing one must stay possible without editing the adapter. """
        self.assertEqual(_adapter(translation=TRANSLATION_SEMANTIC).translation,
                         TRANSLATION_SEMANTIC)

    def test_both_translations_are_accepted(self):
        for translation in TRANSLATIONS:
            with self.subTest(translation=translation):
                self.assertEqual(
                    _adapter(translation=translation).translation, translation)

    def test_an_unknown_translation_is_refused(self):
        """ Loudly, at construction. A silent fallback would mis-stamp whatever
        measurement followed. """
        with self.assertRaises(ValueError):
            _adapter(translation='structrual')          # sic

    def test_the_vocabulary_matches_translate_pys_own(self):
        """ adapter.py keeps a LOCAL tuple so it imports nothing from ad6/ at
        module scope. This pins the two spellings together, the same guard
        test_ad6_grounding.py applies to GROUNDINGS. """
        self.assertEqual(TRANSLATIONS,
                         (TRANSLATION_SEMANTIC, TRANSLATION_STRUCTURAL))
        self.assertEqual((TRANSLATION_SEMANTIC, TRANSLATION_STRUCTURAL),
                         ('semantic', 'structural'))


class TestFaithfulVlanDoesNotApplyToStructural(unittest.TestCase):
    """ AD6_PLAN.md §9.16.1. `faithful_vlan` is a property of the SEMANTIC
    path, not of the model: its plain mode deliberately discards VLAN, while
    the structural path translates FaVe's rules as given and they carry VLAN
    whatever the flag says.

    Measured on wl_i2: plain SEMANTIC reports all 72 pairs reachable, plain
    STRUCTURAL reports the 11 unreachable pairs that ad6, NetPlumber and
    bench/i2_structural_oracle.py independently agree on. A structural result
    stamped `faithful_vlan: false` would therefore be MISLABELLED, and the
    generality-debt gate's whole rule is that a stamp must say what produced
    the number. """

    def test_the_stamp_reports_faithful_vlan_as_not_applicable(self):
        stamp = _adapter(faithful_vlan=False,
                         translation=TRANSLATION_STRUCTURAL).configuration_stamp()
        self.assertFalse(stamp['faithful_vlan_applies'])
        self.assertIsNone(stamp['faithful_vlan'],
                          "reporting the value that was passed and ignored is "
                          "exactly the mislabelling this guards against")

    def test_the_stamp_reports_it_normally_for_the_semantic_path(self):
        for value in (True, False):
            with self.subTest(faithful_vlan=value):
                stamp = _adapter(faithful_vlan=value,
                                 translation=TRANSLATION_SEMANTIC).configuration_stamp()
                self.assertTrue(stamp['faithful_vlan_applies'])
                self.assertEqual(stamp['faithful_vlan'], value)

    def test_the_flag_really_does_not_change_the_structural_model(self):
        """ The empirical claim behind the stamp, asserted rather than trusted:
        the two settings must produce a BYTE-IDENTICAL config. If this ever
        fails, `faithful_vlan` has started to matter and the stamp above is
        wrong. """
        configs = []
        for value in (False, True):
            engine = _adapter(faithful_vlan=value, translation=TRANSLATION_STRUCTURAL)
            with InProcessFaVe(engine) as fave:
                fave.replay("bench/wl_ifi")
                configs.append(engine._build_structural()['config'])
        self.assertEqual(configs[0], configs[1])


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
