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


# PORT PROVENANCE AND INTENT ARE FIELDS, WITH DENSE INTERNAL IDS.
#
# An earlier cut of this module made both structural -- an <interface>
# condition rather than a value (§9.8.1). That is right for `in_port`, which
# records where a packet HAS BEEN and really is a property of the path, and
# WRONG for `out_port`, which records where it IS GOING: written by a `routing`
# rule and read by a later `post_routing` rule in the same device. ad6 has no
# "where am I headed" register, so translating that match as "the path already
# traversed that egress interface" is CIRCULAR -- the rule that leads to the
# egress node demands the path had been through it. Measured on wl_ifi: the
# model crossed the whole router and died at `favenet_ifi_5_egress_out`, whose
# own condition is `constant true` (§9.10.2).
#
# Both are therefore ordinary mutable fields here, and FaVe's own rules supply
# the whole lifecycle -- nothing is synthesised:
#
#     pre_routing   in_port  := <this ingress port>
#     routing       out_port := <chosen egress>      (and reads out_port)
#     post_routing  reads both, then CLEARS both
#
# Values are DENSE IDS this module assigns (PortGraph.port_id), not FaVe's own
# port numbers: the field is only ever compared for equality against values
# assigned here, so a dense numbering is sound and far cheaper -- wl_up has
# 4,808 declared ports, 13 bits, against the 32 FIELD_SIZES gives the field.
#
# The CLEAR is not housekeeping. The next device's `routing` READS `out_port`
# before overwriting it (318 such reads in wl_up), so a stale egress surviving
# the hop would be read as that device's own decision. ad6 spells it as a
# <rewrite> with no value, meaning "no axiom on this edge" -- see
# XMLUtils.CLEAR and instantiatortest.ClearedFieldTest.
_PORT_FIELDS = frozenset({'in_port', 'out_port'})

# FaVe names a router port "<device>.<port>_ingress"/"_egress"; the direction is
# carried by the suffix, and ad6 wants it as an attribute.
_PORT_SUFFIX_DIRECTION = {'_ingress': 'in', '_egress': 'out'}


def split_port_direction(port: str) -> Any:
    """ "ifi.10_egress" -> ("ifi.10", "out"); "dev.1" -> ("dev.1", None).
    The direction is None when the name carries no suffix, which is how
    switch-style ports and FaVe's own table ports are spelled. """
    for suffix, direction in _PORT_SUFFIX_DIRECTION.items():
        if port.endswith(suffix):
            return port[:-len(suffix)], direction
    return port, None


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

    if name in _PORT_FIELDS:
        raise UnsupportedField(
            "%r carries a port NAME, which only the model-wide id map can turn "
            "into a value (ports are compared for equality against dense ids "
            "this module assigns -- see the _PORT_FIELDS comment). rule_to_ad6 "
            "resolves it; field_to_match has no id map and must not guess."
            % name)

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


class UnsupportedAction(Exception):
    """ A FaVe action with no ad6 representation. Raised for the same reason as
    UnsupportedField: silently ignoring an action changes where packets go. """


def _forward_ports(rule: Any) -> Any:
    """ Every port this rule forwards to, in action order, deduplicated.

    The `Forward` actions are the authoritative forwarding decision -- measured:
    every rule carrying an `out_port` rewrite also carries exactly one Forward,
    so the rewrite is never the sole record of an egress (see _PORT_FIELDS). """
    ports = []
    for action in (getattr(rule, 'actions', None) or []):
        if type(action).__name__ != 'Forward':
            continue
        for port in (getattr(action, 'ports', None) or []):
            if port not in ports:
                ports.append(port)
    return ports


def _is_wildcard(value: Any) -> bool:
    """ FaVe spells "forget this field" as an all-`x` mask of the field's own
    width (`"x"*32` for a port). """
    text = str(value)
    return bool(text) and set(text) == {'x'}


def _rewrites(rule: Any, port_id: Any) -> Any:
    """ Every field this rule rewrites, as [(ad6_field_name, value_or_None)],
    where None means CLEAR.

    `port_id(port)` maps a port name to its dense id; it is passed in rather
    than looked up here so this stays a pure function of the rule.

    Measured across all four benchmarks: no rule carries more than ONE
    `Rewrite` action, so there is never a per-target disagreement, and every
    value is either an integer, a port name, or an all-`x` wildcard. Anything
    else is refused rather than guessed -- ad6 stores a rewrite as an integer,
    so a value it cannot represent must not be silently dropped. """
    collected = []
    seen = {}
    for action in (getattr(rule, 'actions', None) or []):
        for field in (getattr(action, 'rewrite', None) or []):
            name = rewrite_field_for(field.name)
            if _is_wildcard(field.value):
                value = None
            elif field.name in _PORT_FIELDS:
                value = port_id(str(field.value))
            else:
                try:
                    value = int(field.value)
                except (TypeError, ValueError):
                    raise UnsupportedAction(
                        "rewrite of %r to %r: ad6 stores a rewrite as an "
                        "integer and this value is neither one nor a wildcard."
                        % (field.name, field.value))
            if name in seen and seen[name] != value:
                raise UnsupportedAction(
                    "rule rewrites %r to both %r and %r; a rule's actions share "
                    "one per-node rewrite set and cannot disagree."
                    % (name, seen[name], value))
            if name not in seen:
                seen[name] = value
                collected.append((name, value))
    return collected


def rule_to_ad6(rule: Any, key: str, resolve_target: Any, resolve_interface: Any,
                port_id: Any, mutable: Iterable[str] = (),
                position: Optional[int] = None) -> Any:
    """ One FaVe `Rule` -> one ad6 <rule>, at its own position.

    `resolve_target(port)` maps a FaVe forward port to the ad6 node key to jump
    to (a port's `_out` interface node); `resolve_interface(port)` maps one to
    the UNSUFFIXED interface key an <interface direction=...> condition names.
    They are separate arguments on purpose -- passing the jump key to a
    condition would name a node that exists but is never on the path, making
    the rule quietly unsatisfiable. `model_to_config` supplies both, so this
    function stays pure and independent of how the port graph is laid out.

    The rule's POSITION is its semantics, not decoration: ad6 evaluates a
    table's rules first-match-wins in document order with an implicit
    fall-through to the next (instantiatortest.RuleOrderSemanticsTest), and
    FaVe's own interwoven rulesets encode their state semantics purely as rule
    order (AD6_PLAN.md 9.2a). The caller must therefore emit rules in FaVe's
    `idx` order and never re-sort them.

    Emits one <action type="jump"> per forwarded port -- ad6 reads every action
    as its own TRUE edge, giving OR/existential semantics across the fanout
    (9.7.2 option B). A rule that forwards nowhere gets no action at all, which
    ad6 reads as "matches, goes nowhere": a drop. """
    element = GenUtils.rule(str(position if position is not None else 0), key=key)

    for field in (getattr(rule, 'match', None) or []):
        if field.name in _PORT_FIELDS:
            # An ordinary field match against this port's dense id. NOT an
            # <interface> condition: `out_port` is where the packet is GOING,
            # which no interface on the path has been through yet.
            element.append(GenUtils.fieldmatch(
                rewrite_field_for(field.name), port_id(str(field.value)),
                negated=bool(getattr(field, 'negated', False))))
            continue
        match = field_to_match(field, mutable=mutable)
        if match is not None:
            element.append(match)

    # `in_ports` is deliberately NOT emitted as a condition. It is handled
    # STRUCTURALLY instead, by `PortGraph.chains()` giving each entering port
    # its own chain of applicable rules -- see that method. An <interface>
    # condition would be UNSOUND: ad6 turns it into a plain free variable and
    # ties it to nothing, so the solver may simply assert that a packet came in
    # on whichever port suits it (AD6_PLAN.md §9.12.2, where that let a wl_ifi
    # packet fire a rule written for the Internet uplink, relabel its VLAN and
    # walk past the deny meant for it).

    rewrites = _rewrites(rule, port_id)
    for port in _forward_ports(rule):
        element.append(GenUtils.action('jump', target=resolve_target(port),
                                       rewrites=rewrites))

    for action in (getattr(rule, 'actions', None) or []):
        kind = type(action).__name__
        if kind not in ('Forward', 'Rewrite', 'Miss'):
            raise UnsupportedAction(
                "no ad6 representation for action %r on rule %s -- never drop "
                "an action, it changes where packets go" % (kind, key))

    return element


def table_key(device: str, table: str) -> str:
    """ The ad6 key prefix for one FaVe table. Deterministic from (device,
    table) alone, so `model_to_config` can resolve a jump target without
    needing a second pass or a position re-derivation. """
    safe = lambda part: str(part).replace('.', '_').replace('-', '_')
    return "fw_%s_%s" % (safe(device), safe(table))


def chain_key(device: str, table: str, port: Optional[str]) -> str:
    """ The ad6 key prefix for ONE chain: a (table, entering port) pair.

    The port is part of the identity because a table is compiled once per port
    that enters it, each copy holding only the rules applicable to that port
    (see PortGraph.chains). `port=None` is the chain of a table no port enters
    -- a generator's own injection table. """
    base = table_key(device, table)
    return base if port is None else "%s__%s" % (base, _safe(port))


def rule_key(device: str, table: str, port: Optional[str], position: int) -> str:
    return "%s_r%d" % (chain_key(device, table, port), position)


def table_to_ad6(device: str, table: str, port: Optional[str], rules: Any,
                 resolve_target: Any, resolve_interface: Any, port_id: Any,
                 mutable: Iterable[str] = ()) -> Any:
    """ One FaVe table -> one ad6 <table>, rules ordered by ASCENDING `idx`.

    `Rule.idx` IS A PRIORITY, NOT A LIST POSITION -- measured on real data
    (2026-09-13), and the first cut of this function got it wrong by assuming
    the two coincided. FaVe hands rules out in an order that often disagrees
    with their own indices: 4 of wl_ifi's 38 tables, 9 of wl_i2's 36, 16 of
    wl_stanford's 96 and 138 of wl_up's 1,134. Lower index wins -- 65535 is
    FaVe's max-priority default rule, and `np_preparation._reprioritise_fib_lpm`
    repairs a FIB by REASSIGNING indices in descending prefix-length order, so
    the longest prefix gets the lowest index and is evaluated first.

    That matters more here than in most models, because ad6 evaluates a table
    first-match-wins in DOCUMENT order with an implicit fall-through
    (instantiatortest.RuleOrderSemanticsTest): emitting the list as handed over
    would silently evaluate a default rule before the specific rule it is meant
    to back up. FaVe's own interwoven rulesets encode their state semantics
    purely as order too (§9.2a), so getting this wrong is not a cosmetic error.

    Indices must be UNIQUE within a table, since two rules sharing one would
    leave the order genuinely ambiguous. Measured: no table in any benchmark has
    a duplicate, so this is refused rather than broken arbitrarily. """
    element = GenUtils.table(
        _safe(table) if port is None else "%s__%s" % (_safe(table), _safe(port)))

    indexed = list(enumerate(rules))
    seen = {}
    for original, rule in indexed:
        index = getattr(rule, 'idx', None)
        if index is None:
            continue
        if index in seen:
            raise ValueError(
                "%s/%s has two rules with idx=%s (list positions %d and %d). "
                "The index is the evaluation ORDER, so a duplicate makes it "
                "ambiguous -- refusing rather than picking one."
                % (device, table, index, seen[index], original))
        seen[index] = original

    # Only an entirely-indexed table is reordered. A table with no indices at
    # all keeps exactly the order it was handed, and a PARTIALLY indexed one is
    # refused above rather than silently interleaved -- there is no sensible
    # place to put an unindexed rule among prioritised ones.
    if len(seen) == len(indexed):
        indexed.sort(key=lambda pair: pair[1].idx)
    elif seen:
        raise ValueError(
            "%s/%s mixes %d rules carrying an idx with %d that do not. The "
            "index is the evaluation order, and there is no defensible place "
            "to interleave an unindexed rule among prioritised ones."
            % (device, table, len(seen), len(indexed) - len(seen)))

    for position, (_original, rule) in enumerate(indexed):
        element.append(rule_to_ad6(rule, rule_key(device, table, port, position),
                                   resolve_target, resolve_interface, port_id,
                                   mutable=mutable, position=position))
    return element


# --- the port graph -------------------------------------------------------

_NET = 'favenet'


def _safe(part: Any) -> str:
    return str(part).replace('.', '_').replace('-', '_')


def iface_key(device: str, port: str) -> str:
    """ The ad6 interface key for one FaVe port. Must match what
    `KripkeUtils._HandleInterface` derives for the <node>/<interface> this
    module emits: NetKey + '_' + node name + '_' + interface name. The two
    Kripke nodes it creates are this key plus '_in' and '_out'. """
    return "%s_%s_%s" % (_NET, _safe(device), _safe(port))


class PortGraph:
    """ Resolves FaVe ports to ad6 node keys, from DECLARED structure only.

    Everything `Ad6Adapter` recovers by recognising names -- which table is an
    ACL, which device is a transit router, which stage a `mid.*` prefix means --
    is recovered here from three declared facts: a rule's own `in_ports`, a
    device's own `wiring`, and the topology's own links. Nothing reads a device
    or table name.

    THE STRUCTURAL FACT THIS RESTS ON (measured across wl_ifi/wl_up/
    wl_stanford, AD6_PLAN.md §9.8.2): `port -> table` is a FUNCTION. No port
    appearing in any rule's `in_ports` maps to more than one table, so a port
    names an unambiguous table entry and a jump target resolves in one pass. It
    is checked here rather than assumed -- a workload that broke it would raise,
    not silently pick one.

    The three device shapes in the benchmarks look different and resolve
    identically: wl_up declares a full packet-filter pipeline (952 wiring pairs
    over 136 devices), wl_ifi declares only its router's four-stage chain, and
    wl_stanford declares NO wiring at all because its pipeline is spread across
    separate devices joined by inter-device links. """

    def __init__(self, devices: Dict[str, Any], links: Iterable[Any] = ()) -> None:
        self._devices = dict(devices)
        self._table_of_port: Dict[str, Any] = {}
        self._wiring: Dict[str, str] = {}
        self._links: Dict[str, Any] = {}

        for device, model in sorted(self._devices.items()):
            for table, rules in model.get('tables', {}).items():
                for rule in rules:
                    for port in (getattr(rule, 'in_ports', None) or []):
                        owner = self._table_of_port.get(port)
                        if owner is not None and owner != (device, table):
                            raise ValueError(
                                "port %r is the entry of two different tables "
                                "(%s and %s). `port -> table` must be a function "
                                "for a jump target to resolve unambiguously -- "
                                "see AD6_PLAN.md §9.8.2." % (port, owner,
                                                             (device, table)))
                        self._table_of_port[port] = (device, table)

            for pair in (model.get('wiring') or []):
                source, target = pair[0], pair[1]
                existing = self._wiring.get(source)
                if existing is not None and existing != target:
                    raise ValueError(
                        "port %r is wired to both %r and %r; a FaVe wiring pair "
                        "is a unidirectional link, so this is ambiguous"
                        % (source, existing, target))
                # Duplicates are expected, not exceptional: FaVe replays a
                # device's wiring once per add_wiring call and wl_ifi's router
                # arrives twice.
                self._wiring[source] = target

        for pair in links:
            source, target = pair[0], pair[1]
            targets = self._links.setdefault(source, [])
            if target not in targets:
                targets.append(target)

    # --- port naming ------------------------------------------------------

    def split(self, port: str) -> Any:
        """ "adm.uni-potsdam.de.1_egress" -> ("adm.uni-potsdam.de", "1_egress").

        A FaVe port is its device's name plus one final dotted component, so the
        last dot splits it -- checked against the declared device set rather
        than trusted, since a device name containing no dot and a port name
        containing one would otherwise be indistinguishable. """
        device, _dot, name = str(port).rpartition('.')
        if device in self._devices:
            return device, name
        # Fall back to the longest declared device that prefixes this port.
        best = None
        for candidate in self._devices:
            if str(port).startswith(candidate + '.') and (
                    best is None or len(candidate) > len(best)):
                best = candidate
        if best is None:
            raise KeyError(
                "port %r belongs to no declared device. Ports are resolved "
                "against the device set, never parsed by convention." % (port,))
        return best, str(port)[len(best) + 1:]

    def target(self, port: str) -> str:
        """ Where a rule forwarding to `port` jumps: that port's egress
        interface node. Uniform for every port -- an inter-device egress, an
        intra-device pipeline port, a switch port -- so nothing downstream has
        to know which kind it is. """
        device, name = self.split(port)
        return iface_key(device, name) + '_out'

    def interface(self, port: str) -> str:
        """ The UNSUFFIXED key an <interface direction=...> condition names.
        `kripke.py` turns <interface direction="in">K</interface> into the
        variable K_in, which is the ingress node's own proposition -- so the
        condition holds exactly when the path went through that node. """
        device, name = self.split(port)
        return iface_key(device, name)

    def port_id(self, port: str) -> int:
        """ This port's DENSE id, the value `in_port`/`out_port` are compared
        against. 1-based, assigned in sorted order so a model always produces
        the same ids.

        Dense rather than FaVe's own port numbers because the field is only
        ever compared for equality against ids assigned here, so the numbering
        is free -- and much cheaper: wl_up declares 4,808 ports (13 bits)
        against the 32 that FIELD_SIZES gives the field, and ad6 pays that
        width per node per mutable field.

        An unknown port raises rather than getting an id on the fly: a port no
        rule, link or declaration ever mentioned cannot be matched by anything,
        so seeing one means the caller resolved a name this graph never saw. """
        ids = self._port_ids()
        try:
            return ids[str(port)]
        except KeyError:
            raise KeyError(
                "port %r has no id: it appears in no rule, link or port "
                "declaration this graph was built from." % (port,))

    def port_id_width(self) -> int:
        """ Bits needed to hold every assigned id. """
        count = len(self._port_ids())
        width = 1
        while (1 << width) <= count:
            width += 1
        return width

    def _port_ids(self) -> Dict[str, int]:
        if getattr(self, '_port_id_cache', None) is not None:
            return self._port_id_cache
        names = sorted(
            "%s.%s" % (device, port)
            for device, ports in self._ports_by_device().items()
            for port in ports)
        self._port_id_cache = {name: index
                               for index, name in enumerate(names, start=1)}
        return self._port_id_cache

    def chains(self) -> Any:
        """ [(device, table, port, rules)] -- one chain per (table, ENTERING
        PORT), holding only the rules that port can reach.

        THIS IS WHERE INGRESS DISCRIMINATION LIVES, and it has to be structural.
        FaVe says which ports a rule is reachable from with `in_ports`; the
        obvious translation, an <interface> condition on the rule, is UNSOUND
        because ad6 makes that a free variable tied to nothing -- the solver can
        assert a packet arrived anywhere it likes (AD6_PLAN.md §9.12.2). Giving
        each port its own chain puts the distinction in the GRAPH, where the
        solver cannot wish it away, and is what the semantic path's
        `entry_key(device, port, ir)` does by a different route.

        A rule with NO `in_ports` is reachable from every port entering its
        table, so it appears in every chain (155 such rules in wl_up). A table
        no port enters at all yields one chain with `port=None` -- a generator's
        own injection table, entered by key rather than by arrival.

        The cost is small because heterogeneous `in_ports` are rare. Measured
        2026-09-13, total rules before -> after: wl_i2 77,841 -> 78,047 (1.00x),
        wl_up 7,828 -> 7,892 (1.01x), wl_ifi 191 -> 223 (1.17x), wl_stanford
        8,792 -> 14,821 (1.69x, its `in.*` stage carrying the whole spread). A
        table whose rules agree on their ports compiles to exactly one chain,
        which is what most tables do. """
        if getattr(self, '_chain_cache', None) is not None:
            return self._chain_cache
        result = []
        for device, model in sorted(self._devices.items()):
            for table, rules in sorted(model.get('tables', {}).items()):
                rules = list(rules)
                ports = set()
                for rule in rules:
                    ports |= {str(p) for p in (getattr(rule, 'in_ports', None) or [])}
                if not ports:
                    result.append((device, table, None, rules))
                    continue
                for port in sorted(ports):
                    applicable = [
                        rule for rule in rules
                        if not (getattr(rule, 'in_ports', None) or [])
                        or port in {str(p) for p in rule.in_ports}]
                    result.append((device, table, port, applicable))
        self._chain_cache = result
        return result

    def entry(self, port: str) -> Optional[str]:
        """ The rule a packet arriving at `port` starts at: rule 0 of the table
        that port enters, or None if no table declares it.

        Rule 0 OF THAT PORT'S OWN CHAIN, not of the whole table: each entering
        port gets its own copy of the applicable rules (see `chains`), so the
        arrival port decides WHICH chain is walked rather than being asked about
        inside a shared one. """
        owner = self._table_of_port.get(port)
        if owner is None:
            return None
        device, table = owner
        return rule_key(device, table, str(port), 0)

    # --- edges ------------------------------------------------------------

    def edges(self) -> Any:
        """ The (from_key, to_key) Kripke edges that XML cannot express, to be
        applied with `Kripke.Put(from, (to, True))` after ConvertToKripke.

        A post-pass rather than declarative <connection keyref=...> elements,
        for a specific reason: `KripkeUtils._HandleInterface` wires a connection
        in BOTH directions (kripke.py, `IFaceKey_out -> ConKey_in` AND
        `ConKey_out -> IFaceKey_in`), while a FaVe link is UNIDIRECTIONAL.
        Declaring them would add edges the model does not have, and an extra
        edge is an over-approximation -- it reports reachable what is not, the
        one direction a soundness error must never go. This is also why
        `favemodel.wire_edges` exists, so the shape is not new.

        Two kinds, resolved identically:
          * `_out(source) -> _in(target)` for every wiring pair and every link;
          * `_in(port) -> entry(port)` for every port that enters a table.
        """
        result = []
        seen = set()

        def add(source_key, target_key):
            pair = (source_key, target_key)
            if pair not in seen:
                seen.add(pair)
                result.append(pair)

        for source, target in sorted(self._wiring.items()):
            add(self.target(source), self.interface(target) + '_in')
        for source in sorted(self._links):
            for target in self._links[source]:
                add(self.target(source), self.interface(target) + '_in')
        for port in sorted(self._table_of_port):
            entry = self.entry(port)
            if entry is not None:
                add(self.interface(port) + '_in', entry)
        return result

    def ports_of(self, device: str) -> Any:
        """ Every port of `device` this model needs an interface node for --
        declared ports, plus any port actually referenced by a rule or a link.
        Referenced-but-undeclared ports are INCLUDED rather than rejected: FaVe
        names a router's pipeline ports (`.acl_in_in`) without listing them in
        `ports`, and a jump to a node that does not exist is a dead end that
        looks like a legitimate refutation. """
        return sorted(self._ports_by_device().get(device, set()))

    def _ports_by_device(self) -> Dict[str, Any]:
        if getattr(self, '_ports_cache', None) is not None:
            return self._ports_cache
        ports: Dict[str, Any] = {device: set() for device in self._devices}

        def note(port):
            try:
                device, name = self.split(port)
            except KeyError:
                return
            ports.setdefault(device, set()).add(name)

        for device, model in self._devices.items():
            for port in (model.get('ports') or []):
                note(port if str(port).startswith(device + '.')
                     else "%s.%s" % (device, port))
            for _table, rules in model.get('tables', {}).items():
                for rule in rules:
                    for port in (getattr(rule, 'in_ports', None) or []):
                        note(port)
                    for port in _forward_ports(rule):
                        note(port)
                    for field in (getattr(rule, 'match', None) or []):
                        if field.name in _PORT_FIELDS:
                            note(str(field.value))
        for source, target in self._wiring.items():
            note(source)
            note(target)
        for source, targets in self._links.items():
            note(source)
            for target in targets:
                note(target)
        self._ports_cache = ports
        return ports


def model_to_config(devices: Dict[str, Any], links: Iterable[Any] = ()) -> Any:
    """ The whole FaVe model -> (ad6 config, Kripke edges).

    `devices` maps a device name to `{'tables': {name: [Rule]}, 'ports': [...],
    'wiring': [(from, to)]}` -- FaVe's own captured model, not an interpreted
    IR. `links` are the topology's unidirectional (from_port, to_port) pairs.

    Returns the config ready for `KripkeUtils.ConvertToKripke` (after
    `XMLUtils.deannotate`) together with the edge list `PortGraph.edges()`
    describes, which the caller applies afterwards -- see that method for why
    those cannot be declared in the XML.

    The mutable-field set is computed over EVERY rule of EVERY device before
    any rule is translated: a field rewritten on one device must be matched
    node-scoped on all of them, or the same field would resolve against a
    global alias in one place and an SSA copy in another (§9.6). """
    graph = PortGraph(devices, links)

    every_rule = [rule
                  for model in devices.values()
                  for rules in model.get('tables', {}).values()
                  for rule in rules]
    mutable = rewritten_fields(every_rule)

    config = GenUtils.config()

    firewalls = GenUtils.firewalls()
    for device in sorted(devices):
        firewall = GenUtils.firewall("fw_" + _safe(device))
        for chain_device, table, port, rules in graph.chains():
            if chain_device != device:
                continue
            firewall.append(table_to_ad6(device, table, port, rules,
                                         graph.target, graph.interface,
                                         graph.port_id, mutable=mutable))
        firewalls.append(firewall)
    config.append(firewalls)

    networks = GenUtils.networks()
    network = GenUtils.network(_NET)
    for device in sorted(devices):
        node = GenUtils.node(_safe(device))
        for port in graph.ports_of(device):
            node.append(GenUtils.interface(port, iface_key(device, port)))
        node.append(GenUtils.nodeFirewall("fw_" + _safe(device)))
        network.append(node)
    networks.append(network)
    config.append(networks)

    return config, graph.edges()


# `vlan` is the one genuinely mutable field (§9.7.1); the width matches ad6's
# own global VLAN encoding (XMLUtils.ConvertVLANToVariables) deliberately, so a
# <fieldmatch> and the structural <vlan> primitive can never disagree about how
# many bits a tag needs. Kept equal to favemodel.MUTABLE_FIELDS.
MUTABLE_FIELD_WIDTHS = {'vlan': 12}


def mutable_field_widths(mutable: Iterable[str],
                         port_width: Optional[int] = None) -> Dict[str, int]:
    """ The `MutableFields` declaration ad6 needs for a model whose rules
    rewrite `mutable`, keyed by ad6's own field names.

    Derived from what the TRANSLATION actually emitted, never from a benchmark
    flag. `Ad6Adapter`'s semantic path declares mutable fields only under
    `faithful_vlan`, which is right for it -- that is the only mode where it
    emits a `<fieldmatch>`. The structural path emits one whenever some rule
    rewrites the field, which on wl_ifi is true in PLAIN mode too, so tying the
    declaration to the flag would leave ad6 raising on a fieldmatch it was never
    told about.

    Port fields take `port_width`, which the caller gets from
    `PortGraph.port_id_width()` -- their values are dense ids this module
    assigns, so only the graph knows how many bits they need. Anything else
    without a known width is refused: ad6 encodes a mutable field as a
    fixed-width bit vector, and guessing would silently truncate or
    over-widen it. """
    widths: Dict[str, int] = {}
    for field in sorted(set(mutable)):
        name = rewrite_field_for(field)
        if field in _PORT_FIELDS:
            if port_width is None:
                raise UnsupportedField(
                    "field %r is a port, whose values are dense ids assigned by "
                    "the PortGraph -- pass port_width=graph.port_id_width()."
                    % (field,))
            widths[name] = port_width
            continue
        width = MUTABLE_FIELD_WIDTHS.get(name)
        if width is None:
            raise UnsupportedField(
                "field %r is rewritten by some rule but has no declared bit "
                "width in MUTABLE_FIELD_WIDTHS. ad6 encodes a mutable field as "
                "a fixed-width bit vector; guessing would silently truncate or "
                "over-widen it." % (field,))
        widths[name] = width
    return widths


def instantiate_base(config: Any, edges: Iterable[Any], inits: Iterable[str],
                     mutable_fields: Optional[Dict[str, int]] = None) -> Any:
    """ `Instantiator.InstantiateBase`'s body with this module's own edges
    spliced in between `ConvertToKripke` and the base-implication build.

    The splice is unavoidable, not a shortcut: the edges reference interface
    NODES, which do not exist until conversion has run, and there is no public
    seam between the two halves -- the same reason `favemodel.instantiate_base`
    exists and calls the same ad6-internal helpers. Keep in sync with
    `src/core/instantiator.py:InstantiateBase` if that changes.

    Returns (kripke, encoding). """
    from src.core.kripke import KripkeUtils
    from src.core.instantiator import Instantiator
    from src.sat.satutils import SATUtils
    from src.xml.xmlutils import XMLUtils

    kripke = KripkeUtils.ConvertToKripke(config, default_inits=False)

    for init in inits:
        node = kripke.GetNode(init)
        if XMLUtils.INIT not in node.Props:
            node.Props.append(XMLUtils.INIT)
        kripke.PutInit(init, node)

    for source, target in edges:
        kripke.Put(source, (target, True))

    encoding = Instantiator._InstantiateBase(kripke)

    if mutable_fields:
        encoding[0].extend(
            Instantiator._CreateMutationConstraints(kripke, dict(mutable_fields)))

    # THE VARIABLE-EXPANSION PASS, and it is not optional. Up to here a CIDR is
    # still one opaque alias variable ("dst_ip4_10.0.0.0/8"); two different
    # prefixes are two INDEPENDENT booleans, so nothing makes 10.0.0.0/8 and
    # 192.168.0.0/16 mutually exclusive and every disjoint chain comes back
    # spuriously REACHABLE. `_HandlePrefixes` and friends expand each alias into
    # the shared per-bit encoding that gives prefixes their overlap semantics.
    #
    # Omitting this was a real bug in the first cut of this function, caught by
    # test_a_chain_with_DISJOINT_matches_is_REFUTED -- which is exactly why that
    # test asserts a REFUTATION: every other test here would have passed, since
    # dropping a constraint only ever makes more things reachable.
    handled: Dict[str, Any] = {}
    for variable in encoding.iterdescendants(XMLUtils.VARIABLE):
        Instantiator._HandlePrefixes(variable, handled)
        Instantiator._HandlePorts(variable, handled)
        Instantiator._HandleVlans(variable, handled)
        Instantiator._HandleFieldMatches(variable, handled, mutable_fields)
        Instantiator._HandleOthers(variable, handled)

    keys = list(handled)
    Instantiator._ShortenPrefixes(handled, [k for k in keys if k.startswith('src_')])
    Instantiator._ShortenPrefixes(handled, [k for k in keys if k.startswith('dst_')])

    encoding[0].extend(list(handled.values()))
    encoding[0].extend(Instantiator._CreateGlobalConstraints(kripke, encoding))
    SATUtils.ConvertToCNF(encoding)

    return kripke, encoding


# --- generators and probes ------------------------------------------------
#
# Neither needs a mechanism of its own. A generator is a device with ONE rule
# that forwards to its own port; a probe is a device with one TERMINAL rule
# that forwards nowhere. The topology's existing links carry a generator onward
# and a probe inward, and `PortGraph` resolves both exactly as it resolves any
# other device -- so `model_to_config` needs no generator or probe case at all.
#
# That is the design working rather than a coincidence. `Ad6Adapter` needs
# `_gen_firewall` with four branches (is this a ruleset device? is the
# attachment FaVe's `output_filter_in` marker port? is the port admitted? which
# entry_key applies?) precisely because it reconstructs meaning; a translator
# that carries the declared structure has nothing left to decide.

GENERATOR_TABLE = 'generator'
PROBE_TABLE = 'probe'
PROBE_PORT = '1'


def _single_valued(fields: Any, kind: str) -> Any:
    """ Flattens a FaVe {name: [RuleField]} map, refusing a field that carries
    several values.

    Measured across wl_ifi/wl_up/wl_i2/wl_stanford: every generator and probe
    field has exactly ONE value. Several would mean a disjunction, which ad6
    expresses for some match kinds (kripke.py ORs repeated <vlan>/<port>
    elements) and not for others (two <ip> elements CONJOIN, so a two-value
    address would silently become unsatisfiable rather than either value).
    Refused rather than half-supported -- this is unmeasured territory, not
    impossible territory, and the message says so. """
    flat = []
    for name, values in sorted((fields or {}).items()):
        values = list(values or [])
        if len(values) > 1:
            raise UnsupportedField(
                "%s field %r carries %d values %r. A multi-valued field is a "
                "DISJUNCTION, which ad6 expresses for some match kinds and not "
                "others -- two <ip> elements conjoin, so an address would "
                "silently become unsatisfiable. No benchmark produces this; add "
                "support deliberately, with a test, rather than by accident."
                % (kind, name, len(values), [str(v.value) for v in values]))
        flat.extend(values)
    return flat


def generator_device(name: str, fields: Any = None, mutable: Iterable[str] = (),
                     port: str = '1') -> Dict[str, Any]:
    """ A FaVe generator -> a one-rule device that injects into its own port.

    Its rule has NO `in_ports`, so nothing can point into it and its node has
    zero backward transitions. That is load-bearing rather than incidental:
    ad6's INIT exemption ("was this node entered") only applies to a node with
    no predecessors, and every real device entry point HAS one once the topology
    is wired -- so a generator needs a node of its own to be a usable query
    source at all (the finding `favemodel.gen_entry_key`'s docstring records).

    A constraint on a MUTABLE field becomes a REWRITE on the injection edge, not
    a match. A match would leave the field a free SSA variable that any
    downstream admission check could satisfy by picking a convenient value --
    silently over-approximating reachability instead of gating it (AD6_PLAN.md
    §5.4 B2, found the hard way there). Immutable fields stay ordinary matches.
    `mutable` is the model-wide rewritten-field set, same as everywhere else. """
    mutable = set(mutable)
    matched, rewritten = [], []
    for field in _single_valued(fields, 'generator'):
        (rewritten if field.name in mutable else matched).append(field)

    from rule.rule_model import Forward, Match, Rewrite, Rule

    actions = []
    if rewritten:
        actions.append(Rewrite(rewritten))
    actions.append(Forward(["%s.%s" % (name, port)]))

    rule = Rule(name, "%s.%s" % (name, GENERATOR_TABLE), 0,
                in_ports=None, match=Match(matched), actions=actions)
    return {'tables': {"%s.%s" % (name, GENERATOR_TABLE): [rule]},
            'ports': [port], 'wiring': []}


def probe_device(name: str, *, port: str = '1') -> Dict[str, Any]:
    """ A FaVe probe -> a one-rule device that receives and terminates.

    THE PROBE ACCEPTS ANY INCOMING TRAFFIC (owner decision 2026-09-13:
    *"Please make the probe accept any incoming traffic. If we need filtering at
    probes, we can implement that later, e.g., when used in a benchmark."*).
    Its rule carries no match, so `probe_entry_key` is reachable exactly when a
    packet arrives at the probe's port -- which is the reachability question
    every benchmark in scope actually asks.

    WHAT ANYONE ADDING PROBE FILTERING MUST KNOW FIRST. A terminal rule's own
    match would be enforced by NOTHING. In ad6 a rule's condition gates its
    OUTGOING edges -- `_ConvertNodesToImplications` makes a node's proposition
    follow from its INCOMING transitions, and a transition carries the condition
    of the node it LEAVES -- so a filtering condition placed on this rule would
    be silently ignored and every probe would report REACHABLE. Measured, not
    reasoned about: a probe demanding dst 192.168.0.0/16 behind a router
    forwarding only 10.0.0.0/8 came back reachable. The property is pinned
    independently of probes by
    `ad6/test/core/instantiatortest.py::TerminalConditionTest`.

    `port` is KEYWORD-ONLY on purpose: this function used to take a `fields`
    dict second, and a caller still passing one positionally would otherwise
    have bound it silently to `port` -- an unfiltered probe on a nonsense port,
    with no error anywhere.

    The fix, when filtering is wanted, is to give the probe one outgoing edge to
    a dedicated accept port and query THAT node, so the condition sits on a real
    transition -- the structural equivalent of what
    `favemodel.probe_vlan_literals` does query-side today. What to enforce is
    then a measurement-affecting choice that belongs to the caller and must be
    stamped: FaVe keeps `filter_fields` (which flows the probe considers) and
    `test_fields` (the condition it tests on arrival) separately, and choosing
    between them is AD6_PLAN.md's generality-debt item 4. Measured shapes, for
    whoever implements it: wl_i2 and wl_stanford probes declare
    `test_fields={'packet.ether.vlan': ['0']}`, 21 wl_up probes declare
    `filter_fields={'packet.upper.dport': ['22']}`, and wl_ifi declares
    neither. """
    from rule.rule_model import Match, Rule

    rule = Rule(name, "%s.%s" % (name, PROBE_TABLE), 0,
                in_ports=["%s.%s" % (name, port)],
                match=Match([]), actions=[])
    return {'tables': {"%s.%s" % (name, PROBE_TABLE): [rule]},
            'ports': [port], 'wiring': []}


def generator_entry_key(name: str) -> str:
    """ The node a query from this source starts at -- its own injection rule.
    Pass it to `instantiate_base`'s `inits`. """
    return rule_key(name, "%s.%s" % (name, GENERATOR_TABLE), None, 0)


def probe_entry_key(name: str) -> str:
    """ The node a query to this probe targets -- its own terminal rule,
    reachable exactly when a packet arrives at the probe's port. Adding probe
    filtering would change this: see probe_device. """
    return rule_key(name, "%s.%s" % (name, PROBE_TABLE),
                    "%s.%s" % (name, PROBE_PORT), 0)
