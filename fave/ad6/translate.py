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

""" AD6_PLAN.md §9 Phase 1: STRUCTURAL translation of FaVe's model into ad6's
XML vocabulary.

The contrast that defines this module (§9.1). `fave/ad6/adapter.py` RECOGNISES
FaVe's naming conventions and rebuilds meaning from them -- `in.*`/`mid.*`/
`out.*` stage prefixes, `.acl_in`/`.routing` table suffixes -- emitting an IR
of interpreted CONCEPTS. This module recognises nothing. A FaVe field becomes
an ad6 match, a FaVe rule becomes an ad6 rule at its own position, a FaVe table
becomes an ad6 table. Nothing here may branch on a device name, a table name,
or a benchmark.

Pure by construction: no I/O, no adapter state, every function a value ->
value map over `rule/rule_model.py` objects and `lxml` elements. That is what
makes the tests in `fave/test/test_ad6_translate.py` cheap enough to be written
first.

THE SEMANTIC DISTINCTION THAT DRIVES THE FIELD TABLE. ad6 offers two ways to
match a field and they are NOT interchangeable:

  * the TYPED primitives (`GenUtils.address`/`port`/`proto`/...) resolve
    against one model-wide global alias per field. Correct, and much cheaper,
    for a field whose value never changes along a path.
  * `GenUtils.fieldmatch` resolves NODE-SCOPED, against this node's own SSA
    copy of the field as carried in by whichever edge fired into it (see its
    own docstring and Instantiator._CreateMutationConstraints). This is the
    only correct form for a field that some rule somewhere REWRITES, because
    the same field then legitimately holds different values at different points
    along one path.

So the choice is a property of the WHOLE MODEL, not of the field in isolation:
a field that is rewritten anywhere must be matched with `fieldmatch`
everywhere. `field_to_match` therefore takes the model's rewritten-field set as
an argument rather than hardcoding one -- hardcoding it would be exactly the
workload assumption §9 exists to remove. Measured on 2026-09-12 across
wl_ifi/wl_up/wl_i2/wl_stanford, that set is
{`packet.ether.vlan`, `in_port`, `out_port`}, and 17 distinct fields are
matched in total -- but nothing here depends on those numbers. """

from __future__ import annotations

import sys
import os

from typing import Any, Dict, Iterable, Optional, Set

_HERE = os.path.dirname(os.path.abspath(__file__))          # .../fave/ad6
_AD6 = os.path.join(os.path.dirname(os.path.dirname(_HERE)), 'ad6')

if _AD6 not in sys.path:                                     # ad6/ is a sibling of fave/
    sys.path.insert(0, _AD6)

from src.xml.genutils import GenUtils                        # noqa: E402


class UnsupportedField(Exception):
    """ A match field with no defined ad6 representation.

    Raised, never swallowed: a dropped match is a SILENTLY WEAKER model, which
    shows up as spurious reachability that looks like a real verdict. Every
    failure mode this project has spent time on (the LPM tiebreak, the /0 CIDR,
    the per-device admission projection) was of exactly this shape -- a
    constraint that quietly went missing. Adding a field here is a deliberate
    act with a test; letting one through is not. """


# --- the field table ------------------------------------------------------
# A typed primitive is used ONLY where the mapping is unambiguous AND
# value-preserving. Everything else goes to `fieldmatch`, which carries the
# value verbatim. `module.ipv6header.header` is the instructive case:
# GenUtils.ipv6header() takes no value at all, so using it would silently drop
# the one this field carries -- precisely the failure UnsupportedField exists
# to prevent, just spelled differently. `module.limit` is deliberately generic
# too: GenUtils.icmp6limit emits <icmp6-limit>, and this field is the generic
# limit module, a correspondence this module is not in a position to assert.

_ADDRESSES = {
    'packet.ipv4.source':      ('src', '4'),
    'packet.ipv4.destination': ('dst', '4'),
    'packet.ipv6.source':      ('src', '6'),
    'packet.ipv6.destination': ('dst', '6'),
}

_PORTS = {
    'packet.upper.sport': 'src',
    'packet.upper.dport': 'dst',
}

# PROTOCOL NUMBER -> the NAME ad6 knows it by. This map is not a convenience:
# it closes a silent wrong-answer hazard found 2026-09-12 while writing this
# module's tests. FaVe canonicalises a protocol at RuleField construction
# ("tcp" -> "6"), while ad6's XMLUtils.CanonizeProto looks the value up in its
# IANA table BY NAME and, on a miss, silently returns the NONEXT (59) code
# under a `# TODO: error handling` comment. Measured:
#
#     CanonizeProto('tcp')      -> 0 0 0 0 0 1 1 0   (6)  correct
#     CanonizeProto('6')        -> 0 0 1 1 1 0 1 1   (59) WRONG, no error
#     CanonizeProto('nonsense') -> 0 0 1 1 1 0 1 1   (59) indistinguishable
#
# So handing ad6 FaVe's own canonical value would turn EVERY tcp/udp/icmp match
# into a "no next header" match, with nothing downstream able to detect it --
# '6' and a typo produce byte-identical output. Translating back to the name,
# and REFUSING anything not in ad6's table, is the only safe direction.
# ad6's IANA table holds exactly these four; measured values across the
# benchmarks are 6, 17 and 58, all covered.
_PROTO_NAMES = {
    '1':  'icmp',
    '6':  'tcp',
    '17': 'udp',
    '58': 'icmp6',
}


def _proto(value: str, negated: bool = False) -> Any:
    name = _PROTO_NAMES.get(str(value))
    if name is None:
        raise UnsupportedField(
            "protocol %r has no name in ad6's IANA table (known: %s). It must NOT "
            "be passed through: XMLUtils.CanonizeProto silently returns the "
            "no-next-header code for anything it cannot look up, so an unmapped "
            "protocol becomes a wrong answer rather than an error. Add it to ad6's "
            "IANA table and to _PROTO_NAMES, with a test."
            % (value, ', '.join(sorted(_PROTO_NAMES.values()))))
    return GenUtils.proto(name, negated=negated)


_SIMPLE = {
    'packet.ipv6.proto':             _proto,
    'packet.ipv6.icmpv6.type':       GenUtils.icmp6type,
    'packet.upper.tcp.flags':        GenUtils.tcp_flags,
    'module.ipv6header.rt.type':     GenUtils.rttype,
    'module.ipv6header.rt.segsleft': GenUtils.rtsegsleft,
}

# FaVe's field name -> the name ad6 knows the field by in a <fieldmatch> and in
# an <action rewrite_field=...>. The two MUST agree or a rewrite would write a
# field no match ever reads; `rewrite_field_for` is the single source of both.
_AD6_FIELD_NAME = {
    'packet.ether.vlan': 'vlan',
}

_GENERIC = {
    'related',
    'in_port',
    'out_port',
    'module.limit',
    'module.ipv6header.header',
    # VLAN is here rather than among the typed primitives even though
    # GenUtils.vlan() exists, for a reason independent of mutability:
    # that primitive REQUIRES an ingress/egress direction which FaVe's
    # `packet.ether.vlan` does not carry, so it is not value-preserving.
    # Listing it also means a model that happens never to rewrite VLAN still
    # translates, instead of raising UnsupportedField for the single most
    # common field in wl_stanford and wl_i2.
    'packet.ether.vlan',
}

# A match-all address constrains nothing, so ad6 omits the element entirely
# rather than emitting a vacuous one (favemodel._is_constrained does the same).
# Both spellings of the IPv6 default route occur in real FaVe output.
_MATCH_ALL = frozenset({'0.0.0.0/0', '::/0', '0::0/0'})


def rewrite_field_for(name: str) -> str:
    """ The name ad6 uses for a FaVe field, in both <fieldmatch field="..."> and
    <action rewrite_field="...">. One function so the two can never drift. """
    return _AD6_FIELD_NAME.get(name, name)


def rewritten_fields(rules: Iterable[Any]) -> Set[str]:
    """ Every field any of `rules` rewrites -- the model-wide set
    `field_to_match` needs in order to decide fieldmatch vs a typed primitive.
    Collected over the WHOLE model, never per device: a field rewritten on one
    device is mutable for every match of it anywhere. """
    mutable: Set[str] = set()
    for rule in rules:
        for action in (getattr(rule, 'actions', None) or []):
            for field in (getattr(action, 'rewrite', None) or []):
                mutable.add(field.name)
    return mutable


def field_to_match(field: Any, mutable: Iterable[str] = ()) -> Optional[Any]:
    """ One FaVe `RuleField` -> one ad6 match element, or None when the field
    expresses no constraint at all (a match-all address).

    `mutable` is the model's rewritten-field set, from `rewritten_fields`. A
    field in it is matched node-scoped via <fieldmatch> regardless of whether a
    typed primitive exists for it -- see this module's docstring for why that
    is a correctness requirement and not a preference.

    Raises UnsupportedField for anything with no defined representation. """
    name = field.name
    value = field.value
    negated = bool(getattr(field, 'negated', False))

    if name in _ADDRESSES and str(value) in _MATCH_ALL and not negated:
        # A NEGATED match-all is the empty set, not the universe, so it must
        # never take this shortcut -- it stays a real (and unsatisfiable)
        # constraint.
        return None

    if name in set(mutable) or name in _GENERIC:
        return GenUtils.fieldmatch(rewrite_field_for(name), str(value), negated=negated)

    if name in _ADDRESSES:
        direction, version = _ADDRESSES[name]
        return GenUtils.address(str(value), direction=direction, version=version,
                                negated=negated)

    if name in _PORTS:
        return GenUtils.port(str(value), _PORTS[name], negated=negated)

    if name in _SIMPLE:
        return _SIMPLE[name](str(value), negated=negated)

    raise UnsupportedField(
        "no ad6 representation for match field %r (value %r). Add it to "
        "fave/ad6/translate.py's field table WITH A TEST -- never let it "
        "through, since a dropped match is a silently weaker model." % (name, value))


def supported_fields() -> Set[str]:
    """ Every field name `field_to_match` can represent without being told the
    model's mutable set. Used by the test suite to assert the table covers the
    vocabulary the real benchmarks actually use. """
    return set(_ADDRESSES) | set(_PORTS) | set(_SIMPLE) | set(_GENERIC)
