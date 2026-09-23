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

""" An AbstractVerificationEngine backed by APKeep (via libapkeep / JPype).

Translates a FaVe model to APKeep (approach B in APKEEP_BACKEND.md): FaVe device
models -> APKeep ForwardElements + dst-IP forwarding rules, FaVe links -> APKeep
topology, and FaVe source->probe compliance checks -> APKeep existential
reachability (ReachabilityChecker, P3).

The AbstractVerificationEngine methods are called incrementally, but APKeep
builds the whole network at once (Network.initializeNetwork), so this BUFFERS
the FaVe model as it arrives and builds the APKeep network lazily on the first
check_compliance().

SCOPE (P4, first milestone): IPv4 dst-IP forwarding only (routers + switches),
matching wl_ifi. VLANs are dropped (redundant -- every role has a distinct IPv4
range). ACLs, slices, anomalies and flow dumps are not yet translated; see the
NotImplemented stubs and APKEEP_BACKEND.md.
"""

from __future__ import annotations

import logging

from typing import Any, Dict, FrozenSet, List, Optional, Tuple, Set

from aggregator.abstract_engine import AbstractVerificationEngine
from aggregator.aggregator_abstract import TraceLogger
from rule.rule_model import Forward, Rewrite
from devices.abstract_device import LPM

from apkeep.lib_apkeep import LibAPKeep, available  # noqa: F401  (available re-exported)

_DST = 'packet.ipv4.destination'


def _cidr_to_apkeep(cidr: str) -> Tuple[int, int]:
    """ "10.0.13.0/23" -> (prefix_as_uint32, prefix_len). A bare address is /32. """
    addr, _, length = cidr.partition('/')
    plen = int(length) if length else 32
    octets = [int(o) for o in addr.split('.')]
    prefix = (octets[0] << 24) | (octets[1] << 16) | (octets[2] << 8) | octets[3]
    return prefix, plen


_VLAN = 'packet.ether.vlan'
_SRC = 'packet.ipv4.source'
_SRC6 = 'packet.ipv6.source'      # P9b: IPv6 source (wl_up)
_DST6 = 'packet.ipv6.destination'
_PROTO = 'packet.ipv6.proto'      # shared IPv4/IPv6 protocol field (Stanford ACLs)
_DPORT = 'packet.upper.dport'
# Cisco first-match ACLs map to APKeep's higher-priority-wins ACLElement by
# inverting the FaVe rule index: a lower index (earlier, higher precedence) must
# get a higher APKeep priority. The base exceeds the largest FaVe ACL index.
_ACL_PRIO_BASE = 70000


def _cidr_to_cisco(cidr: Optional[str]) -> Tuple[str, str]:
    """ "10.0.14.0/23" -> ("10.0.14.0", "0.0.1.255") (cisco inverse-mask
    wildcard). None or 0.0.0.0/0 -> match-any ("0.0.0.0", "255.255.255.255"). """
    if cidr is None:
        return "0.0.0.0", "255.255.255.255"
    addr, _, length = cidr.partition('/')
    plen = int(length) if length else 32
    wild = (1 << (32 - plen)) - 1
    wstr = "%d.%d.%d.%d" % (
        (wild >> 24) & 255, (wild >> 16) & 255, (wild >> 8) & 255, wild & 255
    )
    return addr, wstr


def _acl_rule_string(element: str, permit: bool, src: Optional[str],
                     dst: Optional[str], idx: int,
                     vlan: Optional[str] = None) -> str:
    """ One FaVe ACL rule -> an APKeep "+ acl <element> ..." update string
    (accessList/number are dummies; protocol any = 0..255; ports unconstrained;
    the source/destination become cisco IP+wildcard pairs). An optional VLAN tag
    (P9a) is appended as the trailing token when given. """
    sip, swild = _cidr_to_cisco(src)
    dip, dwild = _cidr_to_cisco(dst)
    vlan_tok = "" if vlan is None else " " + str(vlan)
    return "+ acl %s acl 0 %s 0 255 %s %s null null %s %s null null %d%s" % (
        element, "permit" if permit else "deny",
        sip, swild, dip, dwild, _ACL_PRIO_BASE - int(idx), vlan_tok
    )


_SPORT = 'packet.upper.sport'
_OUT_PORT = 'out_port'
_RELATED = 'related'                 # Phase 5: connection-state match (0=NEW, 1=ESTABLISHED)
_IPV6HDR = 'module.ipv6header'       # RH0 anti-spoofing (extension-header) match fields
_IN_PORT = 'in_port'                 # Phase 3: ingress-port qualifier (anti-spoofing)
# forward_filter is first-match on rule index (lower index wins); APKeep's
# FilterElement is higher-priority-wins, so invert the index. The base exceeds
# the largest forward_filter index (a TUM ruleset has ~5k rules).
_FILTER_PRIO_BASE = 10_000_000

# The only compliance-check CONDITION this backend can force onto a query. Both
# engines carry `related` as a real header field (APKeep: BDDACLWrapper's
# relatedVar; NDD: field REL), so a `related:N` check can be answered as the
# conditioned question. Nothing else can -- see _cond_related.
_SUPPORTED_COND_FIELDS = (_RELATED,)

#: The other check conditions this backend can force, and the FilterElement slot
#: each one occupies. `related` is not here: it has a dedicated, cheaper path in
#: both engines (a single header bit) and keeps its own parsing in
#: `_cond_related`. Everything in this table becomes an arrival constraint built
#: from the same 5-tuple encoding the model's own rules use, so a condition and
#: a rule mean the same thing by construction.
_COND_SLOTS = {
    _PROTO: 'proto',
    _SPORT: 'sport',
    _DPORT: 'dport',
    _SRC: 'src', _SRC6: 'src',
    _DST: 'dst', _DST6: 'dst',
}

# --- what a dst-LPM ForwardElement can and cannot say ------------------------
#
# APKeep's ForwardElement is a destination-prefix trie: one match field, and the
# longest prefix wins. A forwarding TABLE that says anything else -- a source, a
# protocol, a port, or a header rewrite -- is a first-match list, and the two are
# not interchangeable. Translating the second as the first drops the extra match
# fields AND replaces the rule order with the prefix length, which widens some
# rules and silently reorders others.
#
# wl_cloud is where that stopped being theoretical: its leaf tables read
#
#     1  dst=10.0.6.128/25, proto=6, dport=332  -> forward
#     2  dst=10.0.6.128/25                      -> drop
#     3  (default)                              -> forward upstream
#
# and dst-only translation turns rules 1 and 2 into a forward and a drop on the
# SAME prefix at the SAME priority, which leaves the outcome to whichever the
# engine happens to keep. It kept the drop, and nothing in the datacenter
# reached anything (CLOUD_BENCH_PLAN.md §1.7.3).
#
# So the table decides the element, by what it matches rather than by what the
# device is called. These two sets are what the ForwardElement path can carry:
# a destination prefix, plus the fields another mechanism already handles --
# `vlan` and `in_port` are structural here (the VLAN stage and
# `_gate_dead_ingress`), and an `out_port` rewrite IS the forward.
_LPM_MATCH_FIELDS = frozenset({_DST, _DST6, _VLAN, _IN_PORT})
_LPM_REWRITE_FIELDS = frozenset({_OUT_PORT, _VLAN})

#: Header fields a NATElement can rewrite, and the token each takes in the
#: `+ nat <dev> <port> match <field> ...` rule string.
_NAT_IP_FIELDS = {_SRC: 'src', _DST: 'dst'}

#: What a FilterElement rule can match (see `_filter_rule_string`). A forwarding
#: table that needs first-match and carries anything else is refused, not
#: approximated.
_FILTER_MATCH_FIELDS = frozenset({
    _PROTO, _SRC, _SRC6, _DST, _DST6, _SPORT, _DPORT, _RELATED})


class UntranslatedSemantics(Exception):
    """ Something the FaVe model states that this translation does not carry.

    Raised, never swallowed, for the reason `ad6/translate.UnsupportedField`
    gives: a dropped constraint is a SILENTLY WEAKER model, and a weaker
    forwarding model still answers every query -- just wrongly, and in the
    direction that looks like a result. Every APKeep gap this project has spent
    time on has that shape (the out-stage in-port permutation, the dead-ingress
    admission, and now the in-port-qualified forwarding wl_deltanet exposed).

    The contract is NOT "APKeep must express everything". It is that an
    approximation must be DECLARED: `_ingress_accounted` records, per device,
    which mechanism accounts for a semantic this element type cannot carry and
    whether that account is complete. An undeclared one is refused here rather
    than discovered later as a wrong number.
    """


#: How completely a declared mechanism accounts for a semantic it stands in for.
ACCOUNT_COMPLETE = 'complete'
ACCOUNT_APPROXIMATE = 'approximate'


def _is_full_space(value: Any) -> bool:
    """ True iff an injected generator field constrains nothing. Only an address
    can be the full space: a port or a protocol names one value. """
    text = str(value)
    return text.endswith('/0') or text in ('0.0.0.0', '::', '0::0')


def _is_dst_lpm_table(rows: List[Dict[str, Any]]) -> bool:
    """ True iff every rule in this forwarding table fits a dst-prefix trie.

    Deliberately a property of the RULES, not of the device: nothing here reads
    a device name, so a workload that names its switches differently gets the
    same decision. The cost of being wrong is asymmetric -- a table that needs
    first-match and gets LPM answers a different question, while a pure FIB that
    took the first-match path would merely be slower -- so anything unrecognised
    counts as needing first-match.
    """
    for row in rows:
        if set(row['match']) - _LPM_MATCH_FIELDS:
            return False
        if set(row['rw']) - _LPM_REWRITE_FIELDS:
            return False
    return True


def _nat_ip_rule_string(device: str, port: str, field: str,
                        new: str, match_body: str) -> str:
    """ One address rewrite -> a "+ nat <dev> <port> match <src|dst> <ip> <len>
    <match...>" string, where `match_body` is the SAME 5-tuple the rule matched
    (a `+ filter` rule string with its "+ filter <device> " head removed).

    The match has to be the whole 5-tuple, not the prefix of the rewritten
    field. Two of wl_cloud's source-NAT rules leave `core.dc0_core` by the same
    port with the same source /24 and differ only in `tcp_src` (342 vs 350) --
    keyed on the address alone they would be the same rule twice, rewriting to
    two different public addresses, and which one won would be an accident.

    The NATElement sits INLINE on (device, port): `addNATs` re-points that
    port's downstream through it, so a rewrite applies to what leaves by that
    port and to nothing else.

    The rewritten value is a PREFIX, and the bits it does not fix come out FREE.
    That is Hassel's `(h & mask) | rewrite` with the mask naming the rewritten
    bits, and it is the same semantics AD6_PLAN.md §9.36 had to correct in ad6:
    a DNAT onto a /22 reaches the whole /22, and framing the low bits from the
    matched /32 instead collapses it to one host.
    """
    new_ip, new_len = new.partition('/')[::2]
    return "+ nat %s %s match %s %s %s %s" % (
        device, port, field, new_ip, new_len or '32', match_body)


def _cond_field(field: Any, key: str) -> Any:
    """ One `cond` entry's attribute. Real dispatch (aggregator_service's
    `_handler`) hands us RuleField objects; a test driving check_compliance
    directly may hand us the plain RuleField.to_json() dicts. """
    if isinstance(field, dict):
        return field.get(key)
    return getattr(field, key, None)


def _cond_related(cond: Any, source: str, probe: str) -> Optional[int]:
    """ The connection state a compliance check's `cond` restricts the query to
    (0 = NEW, 1 = ESTABLISHED), or None for an unconditioned check. REFUSES
    anything this backend cannot force onto the query.

    Nothing is ever skipped. A dropped condition does not fail -- it answers the
    UNCONDITIONED question and returns a confident number, which is the most
    expensive shape of bug this codebase has produced. `check_compliance` used to
    unpack `cond` out of the triple and never look at it again, so all 3302 of
    wl_up's state-conditioned checks were answered unconditioned and the
    `related:0` half came back as 1651 phantom violations where FaVe+NetPlumber
    and FaVe+ad6 both report none. ad6/fave_bridge.py's `_validated_conditions`
    is the same guard against the same failure (AD6_PLAN.md 9.23 is a post-mortem
    of one such published number).

    So either a condition is honoured, or the caller hears about it. """
    value: Optional[int] = None
    for field in (cond or []):
        where = "check %s -> %s" % (source, probe)

        name = _cond_field(field, "name")
        if name is None:
            raise ValueError(
                "malformed query condition %r on %s: expected a RuleField (or "
                "its to_json() dict) carrying a 'name'. Skipping it would "
                "answer the UNCONDITIONED question." % (field, where))

        if name not in _SUPPORTED_COND_FIELDS:
            raise ValueError(
                "query condition %r on %s cannot be honoured: APKeep forces "
                "only %s, not %r. It is NOT dropped, because answering the "
                "unconditioned question looks like a result."
                % (field, where, "/".join(_SUPPORTED_COND_FIELDS), name))

        if _cond_field(field, "negated"):
            raise ValueError(
                "negated query condition %r on %s is not supported: a negated "
                "match is not the same query, and answering the positive one "
                "silently would be a wrong number." % (field, where))

        raw = _cond_field(field, "value")
        try:
            parsed = int(raw)
        except (TypeError, ValueError):
            raise ValueError(
                "malformed query condition %r on %s: 'related' value %r is not "
                "an integer." % (field, where, raw)) from None
        if parsed not in (0, 1):
            raise ValueError(
                "query condition %r on %s: 'related' is a single bit, 0 (NEW) "
                "or 1 (ESTABLISHED), not %r." % (field, where, parsed))

        if value is not None and value != parsed:
            raise ValueError(
                "contradictory query conditions on %s: 'related' constrained to "
                "both %d and %d. The conjunction is empty, so answering either "
                "one would be a different question." % (where, value, parsed))
        value = parsed

    return value


def _ternary_port_range(val: Any) -> Tuple[int, int]:
    """ A FaVe transport-port match value -> (lo, hi). It is either a decimal
    ("22") or a 16-bit ternary bitmask ("000000000000001x", the trailing-x prefix
    masks a port range decomposes into). For a prefix mask x->0 is the low bound
    and x->1 the high bound (exact for the contiguous prefix ranges FaVe emits). """
    s = str(val)
    if len(s) == 16 and set(s) <= {'0', '1', 'x'}:   # 16-bit ternary bitmask
        return int(s.replace('x', '0'), 2), int(s.replace('x', '1'), 2)
    return int(s), int(s)                            # plain decimal port


def _addr_tokens(val: Optional[str]) -> Tuple[str, str]:
    """ (address, wildcard) tokens for an ACL/filter rule's src or dst slot. IPv6
    (a value containing ':') is emitted as "addr/len" with a "null" wildcard -- the
    APKeep BDDACLWrapper.ConvertACLRule detects the ':' and encodes it over srcIP6/
    dstIP6 (P9b). IPv4 becomes a cisco addr + inverse-mask wildcard; None = any. """
    if val is None:
        return "0.0.0.0", "255.255.255.255"
    if ':' in str(val):
        return str(val), "null"
    return _cidr_to_cisco(val)


_FILTER_DROP = "__drop__"   # FilterElement's drop sink (matches FilterElement.DROP_PORT)


def _filter_rule_string(device: str, out_port: str, proto: Optional[Any],
                        src: Optional[str], dst: Optional[str],
                        sport: Optional[Any], dport: Optional[Any],
                        related: Optional[Any], idx: int) -> str:
    """ One packet_filter chain rule -> an APKeep "+ filter <device> ..." update
    string for a FilterElement. Token layout matches an ACL rule (accessList number
    action protoLo protoHi src srcWild sPortLo sPortHi dst dstWild dPortLo dPortHi
    priority [vlan] [related]) except the action slot carries the out_port (ACCEPT)
    or __drop__. The trailing VLAN slot is unused here (null); the `related`
    connection-state bit (Phase 5) follows it. """
    sip, swild = _addr_tokens(src)
    dip, dwild = _addr_tokens(dst)
    plo, phi = ("0", "255") if proto is None else (str(proto), str(proto))
    slo, shi = ("null", "null") if sport is None else tuple(str(p) for p in _ternary_port_range(sport))
    dlo, dhi = ("null", "null") if dport is None else tuple(str(p) for p in _ternary_port_range(dport))
    rel = "null" if related is None else str(related)
    return "+ filter %s filter 0 %s %s %s %s %s %s %s %s %s %s %s %d null %s" % (
        device, out_port, plo, phi, sip, swild, slo, shi, dip, dwild, dlo, dhi,
        _FILTER_PRIO_BASE - int(idx), rel
    )


def _is_acceptall_filter_rule(tokens: List[str]) -> bool:
    """ True iff a parsed "+ filter ..." rule matches the ENTIRE header space and
    forwards (does not drop) -- i.e. an accept-all pass-through rule. Token layout
    (see _filter_rule_string): + filter <dev> filter 0 <out> <plo> <phi> <sip>
    <swild> <slo> <shi> <dip> <dwild> <dlo> <dhi> <prio> [null] [rel]. All match
    fields wildcard (proto 0-255; src/dst 0.0.0.0/255.255.255.255 -- our IPv6
    wildcard is emitted in that IPv4 form too; ports/rel null) and out != drop. """
    if len(tokens) < 17 or tokens[1] != "filter":
        return False
    out = tokens[5]
    plo, phi = tokens[6], tokens[7]
    sip, swild = tokens[8], tokens[9]
    slo, shi = tokens[10], tokens[11]
    dip, dwild = tokens[12], tokens[13]
    dlo, dhi = tokens[14], tokens[15]
    rel = tokens[18] if len(tokens) > 18 else "null"
    return (out != _FILTER_DROP
            and plo == "0" and phi == "255"
            and slo == "null" and shi == "null"
            and dlo == "null" and dhi == "null" and rel == "null"
            and sip == "0.0.0.0" and swild == "255.255.255.255"
            and dip == "0.0.0.0" and dwild == "255.255.255.255")


def _fib_name(device: str) -> str:
    """ Companion ForwardElement/FIB device name for a transit packet_filter. """
    return device + '.fib'


def _fib_rule_string(fib_dev: str, egress: str, dst: Optional[str], plen: int) -> str:
    """ One routing entry -> a "+ filter" string on the companion dst-LPM FIB
    element: match dst only (proto/src/ports wildcard), forward out `egress` (or
    __drop__). Priority = prefix length so a longer prefix outranks a shorter one
    (FilterElement resolves overlaps higher-priority-wins => longest-prefix-match). """
    dip, dwild = _addr_tokens(dst)
    sip, swild = _addr_tokens(None)
    return "+ filter %s filter 0 %s 0 255 %s %s null null %s %s null null %d" % (
        fib_dev, egress, sip, swild, dip, dwild, plen)


def _split_port(fave_port: str) -> Tuple[str, str]:
    """ Map a FaVe port "device.port" to APKeep (device, port). The device may
    itself contain dots (e.g. "source.external.ifi.1"), so split on the last.

    The aggregator hands routers' link endpoints through RouterModel.ingress_/
    egress_port, which suffix the physical port with "_ingress"/"_egress"
    (e.g. "ifi.2_ingress"); strip that so the APKeep port is the bare number.
    Switch/generator/probe ports are passed through unchanged. """
    for suffix in ("_ingress", "_egress"):
        if fave_port.endswith(suffix):
            fave_port = fave_port[:-len(suffix)]
            break
    device, _, port = fave_port.rpartition('.')
    return device, port


def _dedup(items: List[str]) -> List[str]:
    """ Order-preserving de-duplication. The wl_stanford in. (ingress) stage
    emits one identical pass-through forward per ACL rule (thousands of copies
    of the same default route to the mid.-facing port); collapse them. """
    seen: set = set()
    out: List[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


class APKeepAdapter(AbstractVerificationEngine):
    """ Drive APKeep as a FaVe verification backend (forwarding-only, P4). """

    def __init__(self, logger: TraceLogger, mapping: Optional[Any] = None,
                 faithful_vlan: bool = True, engine: str = 'ndd') -> None:
        self.logger = logger
        # One shared adapter, two backend ENGINES (APKEEP_NDD_PLAN §2.5e). The
        # model construction below is engine-agnostic (it emits neutral "+ filter"
        # rule strings + "dev port dev port" edges); only the build/query target
        # differs. 'bdd' -> APKeep (LibAPKeep); 'ndd' -> the per-field NDD engine
        # (LibNDD), which drops APKeep's atomic-predicate cross-product. The NDD
        # engine currently covers the single-universe forwarding case (wl_up: no
        # ACL/NAT); _build() guards this and raises otherwise.
        if engine not in ('bdd', 'ndd'):
            raise ValueError("engine must be 'bdd' or 'ndd', got %r" % engine)
        self._engine = engine
        if engine == 'ndd':
            from apkeep.lib_ndd import LibNDD
            self._ndd = LibNDD()
            self._lib = None
            self._ndd_fwd_mode = False   # pure-+fwd -> AtomForwarding path
        else:
            self._lib = LibAPKeep()
            self._ndd = None
        # P7b: model the wl_stanford/wl_i2 VLAN semantics faithfully (VLAN rewrite
        # via NAT + admission ACLs + probe untag) instead of the forwarding-only
        # out-stage collapse (P7a, which only matches the artificial all-to-all
        # policy). ON by default since 2026-09-18: ad6 and NetPlumber both model
        # VLANs, so the plain model is not a like-for-like comparand, and the
        # differential that found this (APKEEP_BACKEND.md, production-path parity)
        # measured the plain model only because it was the sole one reachable.
        # Pass False for the P7a path and the convergence harness, which measure
        # the plain model deliberately -- and note it is inert on a workload with
        # no VLAN stage (wl_up, wl_tum, wl_ifi): `_i2_faithful` additionally
        # requires `_out_rw` and an `out.` forwarding device.
        self._faithful_vlan = faithful_vlan
        # mid.X -> [(dst_cidr, egress_port, vlan_N)] ; out.X reset set {(inport130, vlan)}
        self._mid_rw: Dict[str, List[Tuple[Optional[str], str, str]]] = {}
        self._out_reset: Dict[str, set] = {}
        # wl_i2 faithful (dst x VLAN): out.X routes match dst + rewrite the egress
        # VLAN (rw=vlan:M). out.X -> [(dst_cidr, egress_port, vlan_M)] (like _mid_rw
        # but i2 has no mid stage -- out.X IS the dst FIB).
        self._out_rw: Dict[str, List[Tuple[Optional[str], str, str]]] = {}
        self._in_vlans: Dict[str, set] = {}   # in.X -> admitted (permit) VLAN tags
        # (in.X, physical ingress port) -> admitted VLAN tags. The per-DEVICE set
        # above is the union over every port, which is what wl_i2's in-stage is
        # NOT: in.kans admits {11,20,21,30,31,32,40,60,70} on port 400029 and 10
        # on ports 400007/400019/400022/400025/400026, and a packet is checked
        # against the set of the port it actually arrives on. Keying the gate by
        # device admits any VLAN any port admits -- see _build_i2_faithful.
        self._in_port_vlans: Dict[Tuple[str, Optional[str]], set] = {}
        # in.X -> set of physical ingress ports with an admission rule (None once
        # an in-port-agnostic rule is seen => the device admits every port). Traffic
        # entering an in-stage port ABSENT from this set is admitted by no rule, so
        # a real router drops it; APKeep's in-port-agnostic ForwardElement would
        # forward it. See _gate_dead_ingress (fixes the wl_stanford dead-port
        # over-approximation, e.g. a source on an unconfigured interface).
        self._in_admit: Dict[str, Optional[set]] = {}
        # buffered FaVe model -> APKeep input
        self._fwd_devices: set = set()       # ForwardElement device names
        self._filter_devices: set = set()    # packet_filter device names (FilterElement)
        # A FaVe packet_filter is an internal pipeline of filter chains
        # (input/output/forward) + a routing table, wired via internal ports (see
        # devices/packet_filter.py). We reproduce it as a small subgraph of APKeep
        # FilterElements per device (_build_pf_pipeline). Per (device, chain) we
        # buffer the parsed rules; the element they land on and the internal links
        # are decided at build from the device's role (host sink/origin vs transit
        # router), which the L1 links reveal. device -> chain -> [(out_port, proto,
        # src, dst, sport, dport, idx)].
        self._pf_rules: Dict[str, Dict[str, List[Tuple]]] = {}
        # A plain router that routes IPv6 cannot use APKeep's dst-IP ForwardElement
        # (its trie is 32/64-bit). Such devices become dst-LPM FilterElement FIBs;
        # here we buffer their routes and mark them. device -> [(dst, egress, plen)].
        # device -> [(dst, egress, prefix_len, ingress)]. `ingress` is the set of
        # ports the entry holds at, or None for "everywhere" -- recorded for the
        # same reason `_fwd_ingress` is: a FilterElement is keyed by DEVICE and
        # has nowhere to put it, so `_demux_ingress` needs it to split the
        # device correctly instead of dropping the qualification.
        self._router_fib: Dict[
            str, List[Tuple[Optional[str], str, int, Optional[FrozenSet[str]]]]] = {}
        self._ipv6_fib_devices: set = set()
        # A transit packet_filter (wl_up: pgf, dept routers) both filters AND routes:
        # its forward_filter accepts to the internal `forward_filter_accept` port,
        # which FaVe wires (internally) to a routing table (dst-IP LPM -> physical
        # egress). A terminal filter (wl_tum: fw.tum) instead has an L1 link
        # accept->probe, so no routing is needed. For transit filters we model the
        # routing as a companion FilterElement (a first-match dst-LPM FIB) chained
        # off the accept port -- see _build_pf_pipeline. device -> [(dst, egress, plen)].
        self._filter_fib: Dict[str, List[Tuple[Optional[str], str, int]]] = {}
        # device -> (ACCOUNT_*, why). Which mechanism stands in for a semantic
        # the chosen element type cannot carry, and how completely. Read by
        # `_assert_ingress_accounted`; an unlisted device that needs one is
        # refused rather than silently approximated.
        self._ingress_accounted: Dict[str, Tuple[str, str]] = {}
        self._fwd_rules: List[str] = []      # APKeep "+ fwd ..." strings
        # "+ fwd ..." string -> the ingress ports it applies at, or None for
        # "everywhere". Keyed by the STRING rather than by position because
        # `_build` filters copies of `_fwd_rules` (the stanford out-stage drop,
        # the first-match split) and a positional index would not survive that.
        # Two rules that produce the identical string necessarily share device,
        # prefix and egress, so merging their ingress sets is not a loss: the
        # string genuinely applies at the union.
        self._fwd_ingress: Dict[str, Optional[Set[str]]] = {}
        # Every forwarding-table rule VERBATIM, per device: {'idx', 'ports',
        # 'match', 'rw'}. The dst-LPM translation above throws away whatever it
        # cannot express, so the decision of WHICH element a table becomes has to
        # be made from something that still has the whole rule -- see
        # _is_dst_lpm_table and _build_first_match_tables.
        self._fwd_table: Dict[str, List[Dict[str, Any]]] = {}
        # Devices whose FORWARDING table the model DECLARES longest-prefix-match
        # (TABLE_SEMANTICS_PLAN.md S2). Not used to decide the element -- the
        # shape still does that -- but to cross-check the decision, so a
        # declaration and the rules disagreeing is a refusal rather than a
        # silent choice between them.
        self._declared_lpm: Set[str] = set()
        self._edges: List[str] = []          # topology "dev port dev port"
        self._generators: Dict[str, str] = {}  # name -> ingress port (FaVe)
        self._probes: Dict[str, str] = {}      # name -> port (FaVe)
        self._built = False
        self._single_universe = False           # Phase 7: set in _build()
        self._build_metrics: Dict[str, int] = {}
        self._results: List[Tuple[int, int, bool, str]] = []
        # ACL translation (router acl_in/acl_out -> per-port APKeep ACLElements).
        # The VLAN is structural -- which port's element -- not a match field,
        # so it never reaches APKeep (which has no VLAN). acl_in/acl_out group
        # the FaVe ACL rules by their (ingress/egress) VLAN.
        self._acl_device: Optional[str] = None
        self._acl_in: Dict[str, List[Tuple[int, bool, Optional[str], Optional[str]]]] = {}
        self._acl_out: Dict[str, List[Tuple[int, bool, Optional[str], Optional[str]]]] = {}
        self._vlan_to_eport: Dict[str, str] = {}  # egress VLAN -> router port
        self._iport_vlan: Dict[str, str] = {}     # ingress port -> VLAN (pre_routing)
        self._gen_src: Dict[str, str] = {}        # source node -> src CIDR
        # source node -> every header field its generator INJECTS. A generator
        # states what the source emits, and constraining the query to less than
        # all of it asks a broader question than the model does: wl_cloud's
        # service endpoints inject `tcp_src` as well as an address, and its leaf
        # ACLs match on it, so ignoring it made 293 denied pairs look reachable.
        self._gen_fields: Dict[str, Dict[str, Any]] = {}
        self._gen_vlan: Dict[str, str] = {}       # source node -> ingress VLAN
        # wl_stanford: the HSA model splits every router into in./mid./out.
        # switches. in.=ingress ACL (pass-through here), mid.=dst-IP FIB, and
        # out.=an input-port->output-port permutation (a pure wire) that a dst-IP
        # ForwardElement cannot express. We recognise the out. stage and collapse
        # it into the topology (mid egress port -> external neighbour) at build.
        self._stanford = False
        self._i2_faithful = False   # wl_i2 dst x VLAN faithful mode (set in _build)
        self._out_perm: Dict[str, Dict[str, set]] = {}  # out_dev -> {inPort: {outPort}}
        # Surface the aggregator's dispatch (aggregator_service._sync_diff)
        # touches on the engine when wiring links: a `links` adjacency dict it
        # mutates directly, an `asyncore_socks` map it checks for dynamic
        # distribution (empty -> static, like a single-process NetPlumber), and
        # `global_port` to key that adjacency. APKeep addresses ports by name,
        # so global_port is identity.
        self.links: Dict[Any, List[Any]] = {}
        self.asyncore_socks: Dict[Any, Any] = {}

    def global_port(self, port: Any) -> Any:
        return port

    # --- translation helpers -------------------------------------------------

    def _out_ports(self, rule: Any) -> List[str]:
        """ APKeep output port name(s) for a forwarding rule. A router routing
        rule rewrites out_port=<dev.port>_egress; a switch rule forwards to
        <dev.port>(s). Return the bare APKeep port name(s). """
        for action in rule.actions:
            if isinstance(action, Rewrite):
                for field in action.rewrite:
                    if field.name == 'out_port':
                        phys = str(field.value)
                        if phys.endswith('_egress'):
                            phys = phys[:-len('_egress')]
                        return [_split_port(phys)[1]]
        for action in rule.actions:
            if isinstance(action, Forward):
                return [_split_port(p)[1] for p in action.ports]
        return []

    @staticmethod
    def _rule_ingress(rule: Any) -> Optional[FrozenSet[str]]:
        """ The ports a rule holds at, or None when it holds everywhere. """
        named = frozenset(_split_port(p)[1] for p in (rule.in_ports or []))
        return named or None

    def _emit_fwd(self, rule_string: str, rule: Any) -> None:
        """ Append a "+ fwd" string and remember which ingress ports it holds at.

        The ingress is what `_demux_ingress` needs and what the string itself
        cannot carry -- APKeep's ForwardElement has nowhere to put it.
        """
        self._fwd_rules.append(rule_string)
        named = {_split_port(p)[1] for p in (rule.in_ports or [])}
        if not named:
            self._fwd_ingress[rule_string] = None          # applies everywhere
            return
        if rule_string not in self._fwd_ingress:
            self._fwd_ingress[rule_string] = named
            return
        previous = self._fwd_ingress[rule_string]
        if previous is not None:                           # None stays None
            self._fwd_ingress[rule_string] = previous | named

    def _translate_fwd_rule(self, device: str, rule: Any) -> None:
        out_ports = self._out_ports(rule)
        if not out_ports:
            # A forwarding-table rule with no forward action is a DISCARD (Cisco
            # Null0 / anti-bogon aggregate, e.g. `192.168.0.0/16 -> Null0`).
            # NetPlumber and real routers honour these; not modelling them lets
            # APKeep forward traffic to genuinely-discarded ranges (an
            # over-approximation -> reachability false positives). Model a
            # *dst-only* discard as a blackhole forward to a dead "__drop__" port
            # (no topology link => a sink) at LPM priority, so it shadows
            # shorter-prefix forwards while a longer-prefix forward still wins by
            # LPM -- exactly the forwarding semantics NetPlumber applies.
            # Soundness guard: skip discards that constrain non-dst fields
            # (source/proto/dport) -- a dst-LPM ForwardElement cannot express
            # those and a dst-only approximation would over-drop (false
            # negatives); those need ACLElements (out of scope). VLAN admission is
            # modelled separately, so a dst(+vlan) discard is safe to key on dst.
            # A match-all discard (no dst) needs no rule -- unmatched space is
            # already un-forwarded.
            fnames = {f.name for f in (rule.match or [])}
            if _DST not in fnames or (fnames - {_DST, _VLAN}):
                return  # not a pure dst(/vlan) discard
            dst = next(f.value for f in rule.match if f.name == _DST)
            prefix, plen = _cidr_to_apkeep(str(dst))
            self._emit_fwd(
                "+ fwd %s %d %d __drop__ %d" % (device, prefix, plen, plen), rule)
            return
        dst = None
        dst6 = None
        for field in (rule.match or []):
            if field.name == _DST:
                dst = field.value
            elif field.name == _DST6:
                dst6 = field.value
        # An IPv6 route cannot go on APKeep's dst-IP ForwardElement (its trie is
        # 32/64-bit prefix based). Buffer it as a dst-LPM FIB (realised as a
        # FilterElement at build -- _build, see _router_fib) and mark the device.
        # Ordinary IPv4 routers keep the ForwardElement fast path below.
        if dst6 is not None:
            tail = str(dst6).partition('/')[2]
            plen6 = int(tail) if tail else 128
            for port in out_ports:
                self._router_fib.setdefault(device, []).append(
                    (dst6, port, plen6, self._rule_ingress(rule)))
            self._ipv6_fib_devices.add(device)
            return
        # A forwarding rule with no dst match is the default route (FIB idx
        # 65535 / match=null): a 0.0.0.0/0 catch-all. APKeep's prefix trie does
        # the longest-prefix match, so /0 naturally loses to any specific route.
        # Also buffer a no-dst default in the generic FIB so an IPv6 router (whose
        # specific routes went to _router_fib above) still gets its default; it is
        # ignored for ordinary IPv4 routers (which use the ForwardElement below).
        if dst is None:
            for port in out_ports:
                self._router_fib.setdefault(device, []).append(
                    (None, port, 0, self._rule_ingress(rule)))
        prefix, plen = (0, 0) if dst is None else _cidr_to_apkeep(str(dst))
        # APKeep's ForwardElement is higher-priority-wins, so the priority must
        # encode longest-prefix-match: a longer prefix must outrank a shorter
        # one regardless of rule arrival order. Use the prefix length directly
        # -- otherwise a later-added default route (/0) can shadow a specific
        # route and the device forwards everything to its default port.
        for port in out_ports:
            self._emit_fwd(
                "+ fwd %s %d %d %s %d" % (device, prefix, plen, port, plen), rule)

    # --- AbstractVerificationEngine: model construction (buffered) -----------

    def _capture_declared_semantics(self, model: Any) -> None:
        """ Record a DECLARED longest-prefix-match forwarding table.

        Asked of the two table names that carry real dst forwarding -- a
        switch's `<node>.1` and a router's `<node>.routing` -- rather than
        iterating `model.tables`, because `semantics_of` answers for any name
        (first-match by default) and those are the only two this adapter
        translates as a FIB anyway.
        """
        semantics_of = getattr(model, 'semantics_of', None)
        if semantics_of is None:
            # Not every object reaching this adapter is an AbstractDeviceModel:
            # the unit tests build models as `SimpleNamespace`, and a producer is
            # free to hand over anything with `.node` and `.tables`. Such an
            # object cannot carry a declaration in the first place, so there is
            # nothing to record -- and nothing is lost, because the cross-check
            # only ever CONSTRAINS a table that was declared. Treating this as an
            # error instead cost 22 failures and 13 errors in the integration
            # tier the first time round.
            return
        for table in (model.node + '.1', model.node + '.routing'):
            if semantics_of(table) == LPM:
                self._declared_lpm.add(model.node)


    def add_tables(self, model: Any) -> None:
        # Routers and switches all become dst-IP ForwardElements. The wl_stanford
        # out. stage is an in-port permutation (not a FIB) collapsed into the
        # topology at build -- but that is decided THERE, keyed on the mid. stage
        # (unique to stanford; wl_i2 is in/out only and its out. stage is a real
        # dst-IP FIB that must be kept). Add every device here.
        self._fwd_devices.add(model.node)
        self._capture_declared_semantics(model)

    def add_rules(self, model: Any) -> None:
        # Only the router's routing table and the switch's flat table hold real
        # dst-IP forwarding. The router's pre_routing/post_routing carry VLAN/
        # egress plumbing, and acl_in/acl_out carry ACL rules that "forward" to
        # internal pipeline ports (e.g. ifi.acl_in_out) -- translating those
        # would emit bogus APKeep ports. So restrict to the forwarding tables.
        if model.node.split('.', 1)[0] == 'out':
            # wl_stanford: record the in-port permutation (+ VLAN resets) for
            # `_build_stanford_faithful`, which still owns this stage because it
            # also has to model the egress VLAN reset. PLAIN mode no longer
            # reads `_out_perm` -- `_demux_ingress` handles the permutation as
            # the general case it is (CLOUD_BENCH_PLAN.md §2.8) -- so the
            # capture is kept for the faithful path alone, and is a small unused
            # dict otherwise. Fall through either way so the out. rules are ALSO
            # translated as a FIB: required for wl_i2, whose out. stage IS one,
            # and in plain wl_stanford those forwards are now kept and split
            # rather than dropped.
            self._capture_out_perm(model)
            if self._faithful_vlan:
                self._capture_out_reset(model)
        fwd_tables = (model.node + '.routing', model.node + '.1')
        acl_in_t = model.node + '.acl_in'
        acl_out_t = model.node + '.acl_out'
        for table, rules in model.tables.items():
            if table in fwd_tables:
                for rule in rules:
                    # A packet_filter device's `routing` table is NOT a plain dst-IP
                    # FIB: its egress is selected by an `out_port` MATCH field (over
                    # IPv6 dst), feeding the internal forward_filter_accept -> routing
                    # pipeline. Capture it as a companion FIB (used at build only for
                    # devices that turn out to be filters -- see
                    # _build_pf_pipeline). This is a no-op for ordinary routers,
                    # whose routing rewrites out_port (not an out_port match). The
                    # dst-FIB `_translate_fwd_rule` still runs but its filter-device
                    # output is dropped at build.
                    self._capture_fwd_table_rule(model.node, rule)
                    self._translate_fib_rule(model.node, rule)
                    self._translate_fwd_rule(model.node, rule)
                    self._capture_vlan_port(rule)
                    if self._faithful_vlan and model.node.split('.', 1)[0] == 'mid':
                        self._capture_mid_rewrite(model.node, rule)
                    if self._faithful_vlan and model.node.split('.', 1)[0] == 'out':
                        self._capture_out_rewrite(model.node, rule)
                    if self._faithful_vlan and model.node.split('.', 1)[0] == 'in':
                        self._capture_in_admission(model.node, rule)
                    if model.node.split('.', 1)[0] == 'in':
                        self._capture_in_admit(model.node, rule)
            elif table == acl_in_t:
                self._acl_device = model.node
                self._capture_acl(self._acl_in, rules)
            elif table == acl_out_t:
                self._acl_device = model.node
                self._capture_acl(self._acl_out, rules)
            elif table == model.node + '.pre_routing':
                self._capture_iport_vlan(rules)
            elif table in (model.node + '.input_filter',
                           model.node + '.output_filter',
                           model.node + '.forward_filter'):
                # A packet_filter chain: a first-match, multi-field table
                # (accept -> chain-accept port / drop). Buffer per chain; the
                # elements + internal wiring are built in _build_pf_pipeline.
                self._filter_devices.add(model.node)
                chain = table.rsplit('.', 1)[1]
                for rule in rules:
                    self._capture_pf_rule(model.node, chain, rule)

    def _capture_fwd_table_rule(self, device: str, rule: Any) -> None:
        """ Buffer one forwarding-table rule whole, before anything is dropped.

        `_translate_fwd_rule` runs beside this and keeps only the destination
        prefix, which is the right thing for a FIB and a silent widening for a
        table that also matches a source, a protocol or a port. Keeping the rule
        as written is what lets `_build` decide, per device, which of the two a
        table actually is.
        """
        row: Dict[str, Any] = {
            'idx': rule.idx,
            'ports': self._out_ports(rule),
            # The INGRESS ports the rule applies at. Kept because APKeep's
            # ForwardElement is a per-DEVICE trie and cannot carry them, which
            # is precisely why they have to be accounted for rather than
            # dropped -- see `_assert_ingress_accounted`.
            'in_ports': [_split_port(p)[1] for p in (rule.in_ports or [])],
            'match': {},
            'rw': {},
        }
        for field in (rule.match or []):
            row['match'][field.name] = field.value
        for action in (rule.actions or []):
            if isinstance(action, Rewrite):
                for field in action.rewrite:
                    row['rw'][field.name] = field.value
        self._fwd_table.setdefault(device, []).append(row)

    def _capture_pf_rule(self, device: str, chain: str, rule: Any) -> None:
        """ Buffer one packet_filter chain rule (input/output/forward). ACCEPT is a
        Forward to the chain's internal accept port (e.g. <dev>.forward_filter_accept);
        a rule with no forward action is a DROP (-> __drop__). Matches the 5-tuple +
        the connection-state `related` bit (Phase 5). A rule that matches an IPv6
        extension-header (module.ipv6header.*, RH0 anti-spoofing) is SKIPPED: it drops
        only routing-header attack packets, which no reachability depends on, and
        modelling only its other fields would collapse it to a match-all drop that
        shadows the accepts. """
        proto = src = dst = sport = dport = related = None
        in_qual = out_qual = None
        for field in (rule.match or []):
            if field.name.startswith(_IPV6HDR):
                return                            # RH0 rule: irrelevant to reachability
            if field.name == _PROTO:
                proto = field.value
            elif field.name in (_SRC, _SRC6):    # IPv4 xor IPv6 per rule
                src = field.value
            elif field.name in (_DST, _DST6):
                dst = field.value
            elif field.name == _SPORT:
                sport = field.value
            elif field.name == _DPORT:
                dport = field.value
            elif field.name == _RELATED:
                related = field.value
            elif field.name == _IN_PORT:
                in_qual = _split_port(str(field.value))[1]
            elif field.name == _OUT_PORT:
                out_qual = _split_port(str(field.value))[1]
        out_ports = self._out_ports(rule)
        out_port = out_ports[0] if out_ports else _FILTER_DROP
        self._pf_rules.setdefault(device, {}).setdefault(chain, []).append(
            (out_port, proto, src, dst, sport, dport, related, in_qual, out_qual, rule.idx))

    def _translate_fib_rule(self, device: str, rule: Any) -> None:
        """ One packet_filter `routing` rule -> a companion-FIB entry
        (dst-prefix -> physical egress). The routing rule carries the egress in an
        `out_port` MATCH field (e.g. "<dev>.2") and forwards to the internal
        routing_out; a rule with a dst but no out_port and no action is an internal
        "route unknown -> drop" (FaVe FIB idx 65534). dst may be IPv4 or IPv6; a
        rule with no dst is the default route (0/0). Stored as (dst, egress, plen)
        and realised as a dst-LPM FilterElement in _build_pf_pipeline. """
        dst = None
        egress = None
        for field in (rule.match or []):
            if field.name in (_DST, _DST6):
                dst = field.value
            elif field.name == _OUT_PORT:
                egress = _split_port(str(field.value))[1]
        has_fwd = any(isinstance(a, Forward) for a in (rule.actions or []))
        if egress is not None:
            # A routing entry is a real route only if it actually forwards (to
            # routing_out). The routing table also holds action-less `out_port=N`
            # rules (rejects / connected-route placeholders) -- capturing their
            # out_port as a route would create bogus 0/0 -> N default routes.
            if not has_fwd:
                return
        else:
            # No out_port: a dst-only, action-less rule is a route-unknown discard.
            if dst is not None and not rule.actions:
                egress = _FILTER_DROP     # internal "route unknown" discard
            else:
                return                    # nothing routable (e.g. pipeline plumbing)
        if dst is None:
            plen = 0
        else:
            tail = str(dst).partition('/')[2]
            plen = int(tail) if tail else (128 if ':' in str(dst) else 32)
        self._filter_fib.setdefault(device, []).append((dst, egress, plen))

    def _capture_out_perm(self, model: Any) -> None:
        """ wl_stanford out. stage: each rule maps an input port (fed by a mid.
        egress interface) to a physical output port (an external wire), possibly
        under an ACL/VLAN match. For forwarding we only need the port
        permutation input->output; the egress ACL/VLAN-rewrite are ignored here.
        """
        perm = self._out_perm.setdefault(model.node, {})
        for _table, rules in model.tables.items():
            for rule in rules:
                out_ports = self._out_ports(rule)
                if not out_ports or not rule.in_ports:
                    continue  # a drop (empty action) or a rule with no in port
                in_port = _split_port(rule.in_ports[0])[1]
                perm.setdefault(in_port, set()).update(out_ports)

    def _capture_in_admit(self, node: str, rule: Any) -> None:
        """ Record which physical ingress ports an in-stage device admits. Each
        wl_stanford in-stage rule is in-port-qualified (it lists the ingress
        ports it permits for a VLAN); the union over all rules is the set of
        ports the router accepts traffic on. A rule with no in-port qualifies
        every port, so it marks the device admit-all (None) -- never gated. """
        cur = self._in_admit.get(node, set())
        if cur is None:
            return
        if not rule.in_ports:
            self._in_admit[node] = None
            return
        for port in rule.in_ports:
            cur.add(_split_port(port)[1])
        self._in_admit[node] = cur
        # DECLARED, and deliberately as APPROXIMATE. `_gate_dead_ingress` drops
        # an edge to a port NO rule admits, which is the dead-interface half of
        # the in-stage's ingress dependence. It does not model the other half --
        # a port that admits a DIFFERENT VLAN set from its neighbour keeps its
        # edge, and the element then applies every in-stage rule to it. That is
        # the over-approximation P7b/P7c record (240 -> 77, sound but not
        # exact); the faithful path upgrades this to complete below.
        self._ingress_accounted[node] = (
            ACCOUNT_APPROXIMATE,
            "_gate_dead_ingress (dead interfaces only; per-port VLAN admission "
            "is the known P7b/P7c over-approximation)")

    def _ingress_ports(self, edges: List[str]) -> Dict[str, Set[str]]:
        """ device -> the ports traffic ARRIVES on, from the final wiring.

        Taken from `edges` rather than from the declared device ports because
        the collapses and gates above rewrite the topology, and what matters is
        the network as built.
        """
        arriving: Dict[str, Set[str]] = {}
        for edge in edges:
            _sdev, _sport, ddev, dport = edge.split()
            arriving.setdefault(ddev, set()).add(dport)
        return arriving

    def _ingress_qualified(self, edges: List[str]) -> Dict[str, List[int]]:
        """ Forwarding devices whose rules DISCRIMINATE among their ingress ports.

        A rule qualifies ingress when it names at least one port the device
        actually receives on AND omits at least one other. Both halves matter:

          * omitting all of them is not discrimination, it is a rule keyed to
            something else entirely. FaVe's router and packet_filter models
            key their pipeline stages to INTERNAL ports -- `r.routing_in`,
            `ifi.acl_in_out` -- which are not topology ingress at all, and
            comparing those against the physical ports flagged every router in
            the tree. That was this check's first form and it was wrong.
          * naming all of them is not discrimination either: the rule applies
            wherever traffic arrives, which is exactly what a per-device trie
            does.

        **The stated limit of this contract**, so it is a decision and not an
        oversight: it covers discrimination among PHYSICAL ingress ports, which
        is what `ForwardElement` provably cannot carry. A rule keyed only to an
        internal pipeline port is a different question -- the pipeline is
        modelled as separate elements (`_build_pf_pipeline`, `_splice_acls`) --
        and is out of scope here rather than silently in it.
        """
        arriving = self._ingress_ports(edges)
        qualified: Dict[str, List[int]] = {}
        # PACKET FILTERS ARE COVERED TOO (2026-09-22). They used to be excluded
        # wholesale, which §2.7 flagged as "a scope statement, not a claim that
        # the pipeline honours in-ports". It is now a checked claim: a
        # packet_filter's `routing` table lands in `_fwd_table` like any other,
        # and it is measured here rather than waved past.
        #
        # `_build_pf_pipeline` DOES carry ingress qualification, but by a
        # different mechanism and from a different field: an `in_port` MATCH
        # (`-i eth0`) becomes a per-port prefilter element `<elem>.inP` that
        # only that port's ingress traverses. That is not `rule.in_ports`, which
        # is what this contract measures, so neither subsumes the other.
        # Measured across wl_up (136 filter devices) and wl_tum (1): ZERO rules
        # discriminate among physical ingress ports via `rule.in_ports`, so this
        # refuses nothing today and stands as a guard for a shape no workload
        # has yet.
        for device, rows in self._fwd_table.items():
            if device not in self._fwd_devices:
                continue                      # not realised as a ForwardElement
            ingress = arriving.get(device, set())
            restricted = []
            for row in rows:
                named = set(row['in_ports'])
                if named & ingress and (ingress - named):
                    restricted.append(row['idx'])
            if restricted:
                qualified[device] = restricted
        return qualified

    #: Separator between a device and the ingress class it was split into.
    #:
    #: NOT `|`, and that cost a debugging session worth recording. The NDD
    #: engine keys its per-hop cache as `device + "|" + port` and recovers the
    #: device with `indexOf('|')` -- the FIRST bar (`AtomForwarding.java:47`
    #: and `:153`, `NddReachabilityEngine.java:89`). An element named
    #: `sw.s1|101` makes the key `sw.s1|101|151`, which parses back as device
    #: `sw.s1`, port `101|151`. The BDD path was unaffected, so the model built,
    #: the run completed, and every must-reach check failed -- a silently wrong
    #: answer produced by a naming choice.
    #:
    #: NOT `.` either: device names already contain dots (`sw.s1`, `in.bbra_rtr`)
    #: and `_fib_name` appends `.fib`, so a dotted suffix is ambiguous with a
    #: port reference.
    INGRESS_CLASS_SEP = '@'

    def _element_name(self, device: str, ports: Set[str]) -> str:
        """ The APKeep element a device's ingress class becomes.

        NO class keeps the bare device name, deliberately. A leftover reference
        to `device` anywhere then fails loudly (APKeep has no such element)
        instead of quietly binding to one arbitrary class of it.
        """
        return '%s%s%s' % (device, self.INGRESS_CLASS_SEP,
                           min(ports, key=lambda p: (len(p), p)))

    def _device_tokens(
            self, device: str, fwd_rules: List[str],
    ) -> List[Tuple[Any, Optional[FrozenSet[str]]]]:
        """ Everything that forwards at `device`, each with where it holds.

        BOTH stores, because a device's forwarding can live in either and a
        split that saw only one would drop the other. `+ fwd` strings become a
        `ForwardElement`; `_router_fib` entries become a dst-LPM
        `FilterElement` -- and neither element type carries an ingress port, so
        both have to be split the same way.
        """
        tokens: List[Tuple[Any, Optional[FrozenSet[str]]]] = [
            (('fwd', rule), self._fwd_ingress.get(rule))
            for rule in fwd_rules if rule.split()[2] == device
        ]
        tokens.extend(
            (('fib', entry[:3]), entry[3])
            for entry in self._router_fib.get(device, [])
        )
        return tokens

    def _ingress_classes(
            self, device: str, ingress: Set[str],
            tokens: List[Tuple[Any, Optional[FrozenSet[str]]]],
    ) -> Dict[str, Set[str]]:
        """ Ingress ports grouped by the rules that apply at them.

        Two ports belong together exactly when the same rules hold there, which
        is the coarsest split that loses nothing -- a device whose rules do not
        discriminate yields one class and is not split at all.
        """
        classes: Dict[frozenset, Set[str]] = {}
        for port in ingress:
            applying = frozenset(
                token for token, held in tokens
                if held is None or port in held
            )
            classes.setdefault(applying, set()).add(port)
        return {self._element_name(device, ports): ports
                for ports in classes.values()}

    def _demux_ingress(
            self, edges: List[str], fwd_rules: List[str],
    ) -> Tuple[List[str], List[str]]:
        """ Split a device whose forwarding discriminates among ingress ports.

        **Phase (b).** APKeep's `ForwardElement` is a destination-prefix trie
        keyed by DEVICE: `Checker.traverseFowardingGraph` uses the arrival port
        only to look the element up and then discards it, so an element is a
        function of (element, packet) and never of (element, in_port, packet).
        The semantics ARE expressible in APKeep -- just not in one element -- so
        the adapter emits one element per ingress class and wires the arriving
        links to the right one.

        **This is a translation, not a model change** (owner, 2026-09-22). The
        FaVe model keeps its devices: 16 realistic switches for wl_deltanet, not
        68. Splitting the BENCHMARK model would have shaped the data around the
        weakest backend and voided the cross-family comparison the suite exists
        for. Splitting the TRANSLATION is the adapter's own business, and this
        file already does it for ACLs, which become per-port `ACLElement`s.

        After the split every element is ingress-uniform by construction, so
        `_assert_ingress_accounted` passes because there is nothing left to
        account for -- not because anything was declared.

        The element count is a REAL cost of the atomic-predicate model and is
        logged rather than absorbed: 16 devices become 68 elements on
        wl_deltanet, which is exactly the node count Delta-net's own paper
        reports for this network.
        """
        qualified = self._ingress_qualified(edges)
        if not qualified:
            return edges, fwd_rules

        arriving = self._ingress_ports(edges)
        split: Dict[str, Dict[str, Set[str]]] = {}
        for device in sorted(qualified):
            # A packet_filter is NOT split here. This pass re-keys `_fwd_rules`
            # and `_router_fib`; a filter device's behaviour also lives in
            # `_pf_rules` and `_filter_fib`, which it does not touch, so
            # splitting one would drop its chain rules -- the wl_up defect of
            # §2.8, committed again one store further along. It falls through to
            # the refusal instead, which is the honest outcome: the pipeline
            # carries an `in_port` MATCH, not `rule.in_ports`, and nothing in
            # the tree currently needs the latter.
            if device in self._filter_devices:
                self.logger.warning(
                    "apkeep: %s discriminates among its ingress ports and is a "
                    "packet_filter, whose chain rules this pass cannot re-key; "
                    "leaving it to the refusal", device)
                continue
            classes = self._ingress_classes(
                device, arriving.get(device, set()),
                self._device_tokens(device, fwd_rules))
            if len(classes) < 2:
                continue                       # nothing to gain from a split
            split[device] = classes

        if not split:
            return edges, fwd_rules

        # --- the rules ---------------------------------------------------
        new_rules: List[str] = []
        for rule in fwd_rules:
            device = rule.split()[2]
            if device not in split:
                new_rules.append(rule)
                continue
            held = self._fwd_ingress.get(rule)
            tokens = rule.split()
            for name, ports in split[device].items():
                if held is None or (held & ports):
                    new_rules.append(' '.join(
                        tokens[:2] + [name] + tokens[3:]))

        # --- the wiring ---------------------------------------------------
        port_element: Dict[Tuple[str, str], str] = {}
        for device, classes in split.items():
            for name, ports in classes.items():
                for port in ports:
                    port_element[(device, port)] = name

        new_edges: List[str] = []
        for edge in edges:
            sdev, sport, ddev, dport = edge.split()
            # Arriving: the link lands on exactly the class that owns the port.
            destinations = [port_element.get((ddev, dport), ddev)]
            # Leaving: every class of the source device can forward out of it,
            # so the egress link is duplicated across them.
            sources = ([sdev] if sdev not in split
                       else sorted(split[sdev]))
            for source in sources:
                for destination in destinations:
                    new_edges.append(
                        '%s %s %s %s' % (source, sport, destination, dport))

        # `_router_fib` is keyed by device and consumed per element, so it is
        # re-keyed here in lockstep. Without this a split device's IPv6 routes
        # would stay filed under a name that no longer exists as an element and
        # vanish -- the silent rule-dropping this whole contract is about.
        for device, classes in split.items():
            entries = self._router_fib.pop(device, [])
            if entries:
                for name, ports in classes.items():
                    held = [e for e in entries if e[3] is None or (e[3] & ports)]
                    if held:
                        self._router_fib[name] = held
            if device in self._ipv6_fib_devices:
                self._ipv6_fib_devices.discard(device)
                self._ipv6_fib_devices.update(
                    name for name in classes if name in self._router_fib)

        for device, classes in split.items():
            self._fwd_devices.discard(device)
            self._fwd_devices.update(classes)
            self.logger.info(
                "apkeep: %s discriminates among its ingress ports; "
                "demultiplexed into %d element(s): %s",
                device, len(classes), ', '.join(sorted(classes)))
        self.logger.info(
            "apkeep: ingress demultiplexing split %d device(s) into %d "
            "element(s) -- a representational cost of the AP model, not a "
            "change to the FaVe model",
            len(split), sum(len(c) for c in split.values()))

        return _dedup(new_edges), new_rules

    def _assert_ingress_accounted(self, edges: List[str]) -> None:
        """ Refuse a model whose ingress qualification nothing accounts for.

        APKeep's `ForwardElement` is a destination-prefix trie keyed by DEVICE:
        `Checker.traverseFowardingGraph` uses the arrival port only to look the
        element up and then discards it, so an element is a function of
        (element, packet) and never of (element, in_port, packet). A rule
        restricted to some ingress ports therefore applies at all of them, which
        OVER-approximates and yields reachability false positives.

        Three outcomes, and the middle one is the point:

          * nothing qualified -- silence;
          * qualified and DECLARED -- logged, at WARNING when the declared
            account is approximate, so the approximation travels with the
            result instead of being rediscovered;
          * qualified and UNDECLARED -- refused.

        wl_deltanet is the third case and is why this exists: its 14 false
        positives were exactly the devices carrying an ingress-restricted rule.
        """
        qualified = self._ingress_qualified(edges)
        if not qualified:
            return

        undeclared = {d: r for d, r in qualified.items()
                      if d not in self._ingress_accounted}
        if undeclared:
            device = sorted(undeclared)[0]
            raise UntranslatedSemantics(
                "APKeep cannot express in-port-qualified forwarding: %d device(s) "
                "carry rules that apply at some ingress ports and not others, and "
                "nothing accounts for it. Its ForwardElement is a per-DEVICE "
                "destination-prefix trie, so those rules would apply at EVERY "
                "ingress port -- an over-approximation, i.e. reachability false "
                "positives that read as results. First: %s, %d restricted rule(s) "
                "(idx %s). Devices: %s. Either declare a mechanism in "
                "`_ingress_accounted` that stands in for it, or the model needs "
                "the ingress demultiplexing this refusal is the placeholder for."
                % (len(undeclared), device, len(undeclared[device]),
                   ', '.join(str(i) for i in sorted(undeclared[device])[:5]),
                   ', '.join(sorted(undeclared))))

        for device in sorted(qualified):
            kind, why = self._ingress_accounted[device]
            if kind == ACCOUNT_APPROXIMATE:
                self.logger.warning(
                    "apkeep: %s has %d ingress-restricted forwarding rule(s); "
                    "%s accounts for them only APPROXIMATELY -- this run "
                    "over-approximates here", device, len(qualified[device]), why)
            else:
                self.logger.info(
                    "apkeep: %s has %d ingress-restricted forwarding rule(s), "
                    "accounted for by %s", device, len(qualified[device]), why)

    def _gate_dead_ingress(self, edges: List[str]) -> List[str]:
        """ Drop topology edges delivering traffic to an in-stage device on a
        physical port that no admission rule covers.

        The wl_stanford in-stage is in-port-qualified: a port absent from every
        rule (an unconfigured interface, member of no VLAN -- e.g. roza gi4/8)
        admits nothing, so a real router and NetPlumber both drop traffic
        entering there. APKeep's dst-only ForwardElement is in-port-agnostic and
        would forward it -- the sole source of the wl_stanford APKeep-over-NP
        residual (5 sources attached to dead ports => 75 spurious pairs). Honour
        the admission by removing those ingress edges. No-op where the in-stage
        admits all ports (None) or the target port is admitted; inter-router
        links land on real (admitted) trunk ports and are unaffected. """
        kept: List[str] = []
        dropped = 0
        for edge in edges:
            _s_dev, _s_port, d_dev, d_port = edge.split()
            admit = self._in_admit.get(d_dev)
            if admit is not None and d_port not in admit:
                dropped += 1
                continue
            kept.append(edge)
        if dropped:
            self.logger.debug(
                "apkeep: gated %d ingress edge(s) to unadmitted in-stage ports",
                dropped
            )
        return kept

    def _capture_mid_rewrite(self, node: str, rule: Any) -> None:
        """ P7b: a mid-stage rule forwards a dst-IP prefix to an egress port and
        rewrites the egress VLAN (rw=vlan:N). Record (dst_cidr, egress_port, N) so
        the build can emit an inline NAT that sets vlan:=N on that route. """
        vlan_n = None
        for action in rule.actions:
            if isinstance(action, Rewrite):
                for field in action.rewrite:
                    if field.name == _VLAN:
                        vlan_n = str(field.value)
        if vlan_n is None:
            return
        ports = self._out_ports(rule)
        if not ports:
            return
        dst = None
        for field in (rule.match or []):
            if field.name == _DST:
                dst = str(field.value)
        self._mid_rw.setdefault(node, []).append((dst, ports[0], vlan_n))

    def _capture_out_rewrite(self, node: str, rule: Any) -> None:
        """ wl_i2 faithful: an out-stage rule matches a dst-IP prefix, forwards to
        an egress port, and rewrites the egress VLAN (rw=vlan:M). Record
        (dst_cidr, egress_port, M) so the build emits an inline NAT setting
        vlan:=M on that route -- the same shape as _capture_mid_rewrite, but for
        i2's out. FIB (there is no mid. stage). """
        vlan_m = None
        for action in rule.actions:
            if isinstance(action, Rewrite):
                for field in action.rewrite:
                    if field.name == _VLAN:
                        vlan_m = str(field.value)
        if vlan_m is None:
            return
        ports = self._out_ports(rule)
        if not ports:
            return
        dst = None
        for field in (rule.match or []):
            if field.name in (_DST, _DST6):
                dst = str(field.value)
        self._out_rw.setdefault(node, []).append((dst, ports[0], vlan_m))

    def _declare_faithful_admission(self) -> None:
        """ The faithful VLAN paths model per-port admission as real ACLs.

        `_build_stanford_faithful` / `_build_i2_faithful` splice a per-router
        ACLElement carrying the admitted VLANs, so the in-stage's ingress
        dependence is then carried rather than approximated.
        """
        for node in self._in_admit:
            self._ingress_accounted[node] = (
                ACCOUNT_COMPLETE,
                "faithful VLAN admission (per-port ACLElement)")

    def _capture_in_admission(self, node: str, rule: Any) -> None:
        """ P7b: an in-stage rule admits (permits, forwards to mid) traffic on a
        given ingress VLAN. Record the VLANs a router's ingress permits, so the
        build can filter arriving transit VLANs (a VLAN an upstream mid assigned
        propagates only if the next router's ingress admits it -- the gate that
        keeps reachability from over-spreading). """
        if not any(isinstance(a, Forward) and a.ports for a in rule.actions):
            return  # a drop (no forward) -- not an admission
        for field in (rule.match or []):
            if field.name == _VLAN:
                vlan = str(field.value)
                self._in_vlans.setdefault(node, set()).add(vlan)
                # ... and per ingress port, which is the granularity the gate
                # needs. An in-port-agnostic rule admits the VLAN everywhere, so
                # record it against every port the device is later seen to have
                # (the sentinel port None, resolved at build).
                for port in (rule.in_ports or [None]):
                    key = (node, None if port is None else _split_port(port)[1])
                    self._in_port_vlans.setdefault(key, set()).add(vlan)

    def _capture_out_reset(self, model: Any) -> None:
        """ P7b: the out-stage mostly passes the mid-assigned VLAN through, but a
        few rules reset it to 0 (rw=vlan:0) -- and probes require vlan=0. Record
        the (in_port, vlan) pairs that reset, so the mid NAT can fold the reset
        into the effective egress VLAN for those routes. """
        reset = self._out_reset.setdefault(model.node, set())
        for _table, rules in model.tables.items():
            for rule in rules:
                resets = any(
                    isinstance(a, Rewrite)
                    and any(f.name == _VLAN and str(f.value) == '0' for f in a.rewrite)
                    for a in rule.actions
                )
                if not resets or not rule.in_ports:
                    continue
                in_port = _split_port(rule.in_ports[0])[1]
                for field in (rule.match or []):
                    if field.name == _VLAN:
                        reset.add((in_port, str(field.value)))

    def _capture_iport_vlan(self, rules: Any) -> None:
        """ pre_routing assigns an ingress VLAN per ingress port (e.g. the
        Internet/transit port gets 4095). Other ports carry the VLAN from the
        source generator instead; this only records the ones pre_routing sets,
        which is how the anti-spoofing acl_in lands on the right port. """
        for rule in rules:
            if not rule.in_ports:
                continue
            port = _split_port(rule.in_ports[0])[1]
            for action in rule.actions:
                if isinstance(action, Rewrite):
                    for field in action.rewrite:
                        if field.name == _VLAN:
                            self._iport_vlan[port] = str(field.value)

    def _capture_vlan_port(self, rule: Any) -> None:
        """ A routing rule rewrites the egress VLAN and the out_port; record the
        VLAN -> egress port so acl_out groups can be wired to the right port. """
        vlan = None
        for action in rule.actions:
            if isinstance(action, Rewrite):
                for field in action.rewrite:
                    if field.name == _VLAN:
                        vlan = str(field.value)
        if vlan is None:
            return
        ports = self._out_ports(rule)
        if ports:
            self._vlan_to_eport[vlan] = ports[0]

    @staticmethod
    def _capture_acl(store: Dict[str, List[Any]], rules: Any) -> None:
        """ Group FaVe ACL rules by their VLAN match into (idx, permit, src, dst)
        tuples. permit == forwards to a (non-empty) internal pipeline port; an
        empty/absent forward is a drop. """
        for rule in rules:
            vlan = src = dst = None
            for field in (rule.match or []):
                if field.name == _VLAN:
                    vlan = str(field.value)
                elif field.name == _SRC:
                    src = field.value
                elif field.name == _DST:
                    dst = field.value
            permit = any(isinstance(a, Forward) and a.ports for a in rule.actions)
            store.setdefault(vlan, []).append((rule.idx, permit, src, dst))

    def add_wiring(self, model: Any) -> None:
        # The device-internal pipeline (pre_routing->acl->routing->post_routing)
        # is a NetPlumber/header-space construct; APKeep's flat dst-IP model has
        # no equivalent, and the physical egress port is taken directly from the
        # routing rule's out_port rewrite. So internal wiring is intentionally
        # not translated.
        pass

    def add_link(self, sport: str, dport: str) -> None:
        self._edges.append("%s %s %s %s" % (_split_port(sport) + _split_port(dport)))

    def add_links_bulk(self, links: Any, use_dynamic: bool = False) -> None:
        for sport, dport in links:
            self.add_link(sport, dport)

    def add_generator(self, model: Any) -> None:
        self._generators[model.node] = model.node + '.1'
        # Capture the injected source IP (for ACL src-seeding) and ingress VLAN
        # (to wire acl_in onto this source's ingress port). Hand-built generators
        # without fields are forwarding-only and need neither.
        fields = getattr(model, 'fields', None)
        if fields:
            for fname, rfields in fields.items():
                if not rfields:
                    continue
                if fname == _VLAN:
                    # Structural: the VLAN decides which ingress element this
                    # source is wired to, not what its packets match.
                    self._gen_vlan[model.node] = str(rfields[0].value)
                    continue
                if fname in (_SRC, _SRC6):
                    self._gen_src[model.node] = rfields[0].value
                elif fname not in _FILTER_MATCH_FIELDS:
                    raise ValueError(
                        "generator %s injects %s, which the source-seed element "
                        "cannot express. It is NOT ignored: a source that emits "
                        "less than the full space and is queried as if it emitted "
                        "everything answers a broader question, and the run still "
                        "reports a number." % (model.node, fname))
                self._gen_fields.setdefault(model.node, {})[fname] = \
                    rfields[0].value

    def add_generators_bulk(self, models: Any, use_dynamic: bool = False) -> None:
        for model in models:
            self.add_generator(model)

    def add_probe(self, model: Any) -> None:
        self._probes[model.node] = model.node + '.1'

    # --- build + query -------------------------------------------------------

    def _build(self) -> None:
        if self._built:
            return
        # wl_stanford (and only it) has a mid. stage; its out. stage is an in-port
        # permutation to collapse. wl_i2 is in/out only -- its out. stage is a real
        # FIB, so it must NOT be collapsed. Decide here, now all devices are known.
        self._stanford = any(d.split('.', 1)[0] == 'mid' for d in self._fwd_devices)
        edges = list(self._edges)
        fwd_rules = list(self._fwd_rules)
        device_acls = None
        device_nats = None
        acl_rules: List[str] = []
        nat_rules: List[str] = []
        # PLAIN mode no longer special-cases the out stage. It is an
        # in-port -> out-port permutation, which is the general case of what
        # `_demux_ingress` does, so the collapse that used to splice it into the
        # topology is redundant: with it removed entirely, wl_stanford's
        # reachability still matches NetPlumber exactly (CLOUD_BENCH_PLAN.md
        # §2.8's subsumption gate, and `test_apkeep_stanford.py`).
        #
        # The FAITHFUL path still owns the stage, because there the out stage
        # also resets the egress VLAN and `_build_stanford_faithful` models that
        # as NATs and per-router ACLs -- which demultiplexing ingress does not
        # and should not do. `_out_perm`/`_capture_out_perm` therefore stay:
        # they feed that path too, not only the deleted collapse.
        if self._stanford and self._faithful_vlan:
            # Drop the out devices and the (broken /0) forwards translated from
            # their permutation rules; the faithful build re-wires the mid.
            # egress interfaces itself.
            self._fwd_devices = {d for d in self._fwd_devices
                                 if d.split('.', 1)[0] != 'out'}
            fwd_rules = [r for r in fwd_rules
                         if r.split()[2].split('.', 1)[0] != 'out']
            (edges, device_nats, nat_rules,
             device_acls, acl_rules) = self._build_stanford_faithful(edges)
        # wl_i2 faithful (dst x VLAN): no mid stage; out.X is the dst FIB and also
        # rewrites the egress VLAN, in.X admits VLANs. Emit the VLAN rewrite as
        # inline NATs and the admission as per-router ACLs (keeping the dst FIB).
        self._i2_faithful = (self._faithful_vlan and not self._stanford
                             and bool(self._out_rw)
                             and any(d.split('.', 1)[0] == 'out'
                                     for d in self._fwd_devices))
        if self._i2_faithful:
            (edges, device_nats, nat_rules,
             device_acls, acl_rules) = self._build_i2_faithful(edges)
        if self._acl_device is not None:
            edges, device_acls, acl_rules = self._splice_acls(edges)
        # A forwarding table that is not a destination-prefix trie is realised as
        # a first-match FilterElement (plus a NATElement per address rewrite)
        # instead of a ForwardElement. Decided from the RULES -- see
        # _is_dst_lpm_table -- so it needs no device naming convention and fires
        # on any workload whose forwarding tables carry ACL matches, rather than
        # on the one that first needed it.
        # Cross-check the declarations before anything acts on a table's shape.
        self._assert_declared_lpm_is_triable()
        first_match = self._first_match_devices()
        fm_rules: List[str] = []
        if first_match:
            fm_rules, fm_nats, fm_nat_rules = self._build_first_match_tables(
                first_match)
            self._fwd_devices -= first_match
            fwd_rules = [r for r in fwd_rules if r.split()[2] not in first_match]
            if fm_nats:
                # The stanford/i2 paths hand back sorted LISTS; normalise before
                # merging so a workload that needed both kinds of rewrite would
                # not fail on the container type.
                merged = dict((d, set(p)) for d, p in (device_nats or {}).items())
                for dev, ports in fm_nats.items():
                    merged.setdefault(dev, set()).update(ports)
                device_nats = merged
                nat_rules += fm_nat_rules
            self.logger.info(
                "apkeep: %d forwarding table(s) are first-match, not dst-LPM "
                "(%d rules, %d address rewrites)",
                len(first_match), len(fm_rules), len(fm_nat_rules))
        # Honour in-stage admission: drop traffic entering an ingress port no rule
        # admits (a real router drops it; our in-port-agnostic ForwardElement would
        # not). No-op unless an in-stage device has a finite admitted-port set.
        edges = self._gate_dead_ingress(edges)
        if self._faithful_vlan and (self._stanford or self._i2_faithful):
            self._declare_faithful_admission()
        # Phase (b): express what one ForwardElement cannot, by using more than
        # one. After this every element is ingress-uniform, so the contract
        # below passes because there is nothing left to account for.
        edges, fwd_rules = self._demux_ingress(edges, fwd_rules)
        # Nothing the model states may go missing in silence: refuse a device
        # whose ingress-qualified forwarding no declared mechanism accounts for.
        self._assert_ingress_accounted(edges)
        # ForwardElement device names not implied by a topology edge still need
        # to exist; pass them all explicitly.
        # The faithful VLAN model builds far more BDD nodes (per-route rewrites +
        # per-VLAN ACLs); give it a larger table.
        bdd_table = 16_000_000 if (self._faithful_vlan
                                   and (self._stanford or self._i2_faithful)) else 1_000_000
        # Each packet_filter becomes a small subgraph of FilterElements (its
        # input/output/forward chains + a dst-LPM routing FIB), wired per the
        # device's role. Terminal filters (wl_tum) stay a single FilterElement.
        edges, pf_elems, pf_rules = self._build_pf_pipeline(
            edges, sorted(self._filter_devices))
        # A generator injects the full header space, but a real source emits only
        # its own src-IP. Splice a src-constraining FilterElement at each source
        # (permit src=address, default-drop) so a source cannot reach a probe via a
        # spoofed src (NetPlumber seeds the source's src; here the packet_filters
        # filter on src in the forwarding AP universe, so we constrain it there).
        edges, sf_elems, sf_rules = self._source_seed_filters(edges)
        pf_elems += sf_elems
        pf_rules += sf_rules
        # Plain IPv6 routers become dst-LPM FilterElement FIBs (the device itself);
        # their IPv4-collapsed `+ fwd` rules are dropped below.
        ipv6_routers = sorted(self._ipv6_fib_devices - self._filter_devices)
        router_fib_rules: List[str] = []
        for dev in ipv6_routers:
            for dst, egress, plen, _ingress in self._router_fib.get(dev, []):
                # `_ingress` is not read here: after `_demux_ingress` every
                # element is ingress-uniform, so the entry holds wherever its
                # element is entered. A device that could NOT be split never
                # reaches this point -- the contract refuses it first.
                router_fib_rules.append(_fib_rule_string(dev, egress, dst, plen))
        filter_devices = pf_elems + ipv6_routers + sorted(first_match)
        as_filter = self._filter_devices | set(ipv6_routers) | first_match
        fwd_devices = sorted(self._fwd_devices - as_filter)
        # A device modelled as a FilterElement must not also carry its (IPv4-only,
        # here mis-collapsed) `+ fwd` dst-FIB rules -- a `+ fwd` dispatches by device
        # name and would land on the FilterElement and fail to parse. Drop them.
        fwd_rules = [r for r in fwd_rules if r.split()[2] not in as_filter]
        # Phase C1 Lever A: contract pure pass-through (accept-all) filter elements
        # -- semantic identities (per-host default-route FIBs, unrestricted output
        # filters) -- out of the graph. Fewer elements => a smaller per-split
        # multiplier in APKeeper.updateSplitAP (the C1 PPM hotspot), at zero
        # correctness cost. Operates on the combined filter-rule universe.
        filter_rules_all = pf_rules + router_fib_rules + fm_rules
        edges, filter_devices, filter_rules_all = self._elide_passthrough_filters(
            edges, filter_devices, filter_rules_all)
        # The combined, engine-neutral rule IR (identical to what the BDD engine's
        # run() receives, and to what wl_up_dump2.py captures for the NDD tests).
        all_rules = _dedup(fwd_rules) + acl_rules + nat_rules + filter_rules_all
        if self._engine == 'ndd':
            # The NDD engine covers forwarding (+fwd/+filter), ACLs (+acl,
            # permit/deny as a residual out_port), and VLAN rewrite (+nat, an
            # inline per-field exist+set on the egress port) -- i.e. every element
            # type these benchmarks emit.
            #
            # A PURE dst-IP FIB (only +fwd rules: wl_i2's 77k routes,
            # wl_stanford-P7a) blows up the monolithic residual, so route it to
            # the atomic-predicate forwarding engine (AtomForwarding): elementary
            # dst intervals + per-device LPM + signature-merge -> the minimal atom
            # partition, atom-set flood. Everything else uses the general engine.
            self._ndd_fwd_mode = bool(all_rules) and all(
                len(r.split()) > 1 and r.split()[1] == 'fwd' for r in all_rules)
            if self._ndd_fwd_mode:
                self._ndd.build_fwd_atoms(all_rules, edges)
                self._build_metrics = {"atoms": self._ndd.atom_count()}
            else:
                self._ndd.build(all_rules, edges)
            self._single_universe = True
            self._build_metrics = {}
            self._built = True
            return
        self._lib.init_in_memory("fave", edges, fwd_devices,
                                 device_acls, device_nats,
                                 device_filters=filter_devices or None,
                                 bdd_table_size=bdd_table)
        # Apply ACLs BEFORE the VLAN-rewrite NATs: the ACLs split atomic predicates
        # on VLAN, and the NAT rewrite table must be built over that final
        # partition (a later ACL split would leave APs the NAT never rewrites).
        self._lib.run(all_rules)
        # Phase 7 fail-safe: the per-source reachability fixpoint is exact only in
        # a SINGLE AP universe -- no ACLElement/NATElement divides the space, so the
        # join at path merges is exact union. Read it back from the BUILT network
        # (not the adapter's intent): guard keys on element presence, not the
        # division flag (wl_up has division_activated=True yet zero ACLElements).
        m = self._lib.element_metrics()
        self._single_universe = (m["ACLElement"] == 0 and m["NATElement"] == 0)
        self._build_metrics = m
        self._built = True

    def single_universe(self) -> bool:
        """ True iff the built network has no ACLElement/NATElement -- the
        precondition under which the per-source reachability fixpoint (Phase B)
        is provably identical to the per-pair DFS. Requires _build() first. """
        self._build()
        return self._single_universe

    def _assert_declared_lpm_is_triable(self) -> None:
        """ A table the model DECLARES longest-prefix-match must be one this
        adapter can realise as a destination-prefix trie.

        Shape decides what is POSSIBLE and the declaration decides among what
        shape cannot distinguish -- so agreeing is unremarkable and disagreeing
        is a refusal, never a silent preference for one of them. A table
        declared `lpm` whose rules match a source, a protocol or a port is not a
        FIB under any backend, and translating it as one would answer a
        different question (CLOUD_BENCH_PLAN.md §1.7.3 is what that costs).

        The converse is deliberately NOT checked: an UNDECLARED dst-only table
        still becomes a `ForwardElement`, as it always has. Making the
        declaration authoritative for undeclared tables would change every
        workload that declares nothing, and belongs to a later step
        (TABLE_SEMANTICS_PLAN.md §9.7) once every producer declares.
        """
        for device in sorted(self._declared_lpm & set(self._fwd_table)):
            rows = self._fwd_table[device]
            if _is_dst_lpm_table(rows):
                continue
            offending = sorted({
                f for row in rows
                for f in (set(row['match']) - _LPM_MATCH_FIELDS)
                          | (set(row['rw']) - _LPM_REWRITE_FIELDS)
            })
            raise UntranslatedSemantics(
                "%s declares its forwarding table longest-prefix-match, but its "
                "rules match or rewrite %s, which a destination-prefix trie "
                "cannot express. Either the declaration is wrong or the table "
                "is not a FIB; this adapter will not choose between them."
                % (device, ', '.join(offending))
            )


    def _first_match_devices(self) -> set:
        """ The devices whose forwarding table is a first-match list.

        The HSA in./mid./out. stages are exempt, and only because something
        else already claims them: `_build_stanford_faithful` and
        `_build_i2_faithful` rewrite those tables themselves, and in plain mode
        `_demux_ingress` splits them -- so the approximation those paths make is
        a decision already taken (APKEEP_STANFORD_NP_SPEC.md), not one to
        re-open here.

        Keyed on the STAGE PREFIX rather than on whether a faithful path is
        active, because the plain path (`faithful_vlan=False`, the convergence
        harness and `test_apkeep_i2.py`) claims the same tables and would
        otherwise get a second, conflicting treatment.

        That exemption is the last device-name test left in this decision, and
        it is a real limit: a new workload that happened to call a device
        `in.something` would inherit it.

        This used to say removing it meant "giving the FilterElement a VLAN
        field, which is its own piece of work". **That is no longer true and was
        already half-wrong when written**: `FilterElement` encodes through
        `ACLRule`, which has carried a VLAN match since P9a, so the BDD engine
        always honoured one. Only the NDD engine dropped it, and that is fixed
        (TABLE_SEMANTICS_PLAN.md §8; `test/test_ndd_vlan_slot.py` pins both
        engines to the same reading). What remains in the way is upstream of the
        element: `_translate_fwd_rule` keeps only the destination, so an
        in-stage rule's VLAN is gone before any element could carry it -- 2,063
        wl_stanford in-stage rules collapse to 52 identical default routes.
        Retiring the exemption is therefore a TRANSLATION change, not an element
        one.

        A packet_filter and an IPv6 router are exempt for a plainer reason:
        their `routing` table is not a forwarding table at all. It carries the
        egress in an `out_port` MATCH feeding the device's internal pipeline,
        which `_translate_fib_rule` reads and `_build_pf_pipeline` realises as a
        companion dst-LPM element -- and `_build` drops their `+ fwd` output
        already. Classifying one here would refuse `out_port` as an
        unexpressible match (wl_up's `adm.uni-potsdam.de` rule 65535) and take
        the device away from the mechanism that does model it.
        """
        staged = {d for d in self._fwd_table
                  if d.split('.', 1)[0] in ('in', 'mid', 'out')}
        owned = self._filter_devices | self._ipv6_fib_devices
        return {dev for dev, rows in self._fwd_table.items()
                if dev not in staged and dev not in owned
                and not _is_dst_lpm_table(rows)}

    def _build_first_match_tables(self, devices: set):
        """ Realise each first-match forwarding table as a FilterElement, and
        each address rewrite on it as a NATElement on the egress port.

        Returns (filter_rules, {device: {port}}, nat_rules).

        The rule ORDER is carried by the priority (`_FILTER_PRIO_BASE - idx`),
        which is what makes this a first-match table rather than a set of
        independent matches: wl_cloud's leaves permit one service and then deny
        the whole prefix, and only the order distinguishes that from denying
        everything.

        REFUSES a match or a rewrite it cannot express, rather than emitting the
        rule without it. A silently dropped match field answers a broader
        question and returns a confident number -- the failure mode this file's
        `_cond_related` exists to prevent, and the one that produced §1.7.3's
        result in the first place.
        """
        rules: List[str] = []
        nats: Dict[str, set] = {}
        nat_rules: List[str] = []
        for device in sorted(devices):
            for row in sorted(self._fwd_table[device],
                              key=lambda r: int(r['idx'])):
                match = row['match']
                unsupported = set(match) - _FILTER_MATCH_FIELDS
                if unsupported:
                    raise ValueError(
                        "%s rule %s matches %s, which a first-match "
                        "FilterElement cannot express. The rule is NOT emitted "
                        "without it: a dropped match field widens the rule and "
                        "the run still reports a number."
                        % (device, row['idx'], sorted(unsupported)))
                rewritten = set(row['rw']) - _NAT_IP_FIELDS.keys() - {_OUT_PORT}
                if rewritten:
                    raise ValueError(
                        "%s rule %s rewrites %s on a first-match table; only "
                        "%s can be modelled here (as a NATElement on the egress "
                        "port). Dropping the rewrite would leave the header "
                        "unchanged and the answer wrong in whichever direction "
                        "the rewrite mattered."
                        % (device, row['idx'], sorted(rewritten),
                           sorted(_NAT_IP_FIELDS)))
                ports = row['ports'] or [_FILTER_DROP]
                for port in ports:
                    rule_str = _filter_rule_string(
                        device, port,
                        match.get(_PROTO),
                        match.get(_SRC, match.get(_SRC6)),
                        match.get(_DST, match.get(_DST6)),
                        match.get(_SPORT), match.get(_DPORT),
                        match.get(_RELATED), int(row['idx']))
                    rules.append(rule_str)
                    # The NAT reuses this rule's own match, so it rewrites
                    # exactly the packets the rule matched -- see
                    # _nat_ip_rule_string on why the address alone will not do.
                    body = rule_str.split(' ', 3)[3]
                    for field, token in sorted(_NAT_IP_FIELDS.items()):
                        if field not in row['rw'] or port == _FILTER_DROP:
                            continue
                        nats.setdefault(device, set()).add(port)
                        nat_rules.append(_nat_ip_rule_string(
                            device, port, token, str(row['rw'][field]), body))
        return rules, nats, nat_rules

    def _build_pf_pipeline(self, edges: List[str], filter_devices: List[str]):
        """ Realise each FaVe packet_filter's internal pipeline as a subgraph of
        APKeep FilterElements. FaVe wires a packet_filter as
            phys-ingress -> pre_routing -> {input_filter (to-self) |
                                            forward_filter (transit)}
            forward_filter_accept / output_filter_accept -> routing -> phys-egress
            input_filter_accept -> host (probe)
            source -> output_filter_in -> output_filter
        and exposes the boundary ports (physical N, output_filter_in,
        input_filter_accept, forward_filter_in/accept) as L1 links.

        Per device we pick, from its L1 links, the chains that are actually on a
        path and map each to an element, adding the internal links:

          * host SINK (has `<dev> input_filter_accept ...`): physical ingress ->
            element <dev> = INPUT filter; accept -> input_filter_accept -> probe.
          * host ORIGIN (has `... <dev> output_filter_in`): source -> element
            <dev>.out = OUTPUT filter; accept -> routing.
          * TRANSIT router (physical egress, no input sink -- e.g. pgf): physical
            ingress -> element <dev> = FORWARD filter; accept -> routing.
          * routing (any device with physical egress): element <dev>.fib = a
            dst-LPM FIB FilterElement (priority = prefix length); physical egress
            edges are moved onto it.
          * TERMINAL filter (wl_tum fw.tum: forward_filter_in/accept wired by L1,
            no physical egress/routing): a single element <dev> = FORWARD filter,
            left exactly as before.

        Returns (edges, all_filter_elements, all_filter_rule_strings). """
        all_elems: List[str] = []
        rule_strings: List[str] = []

        def emit(elem: str, chain: str, handle_quals: bool = True):
            # Emit a chain's rules onto `elem`. With handle_quals (a transit/sink
            # device that has physical ports + routing): in_port/out_port-qualified
            # rules (anti-spoofing, e.g. `in_port=internet & src=uni -> drop`) must
            # NOT apply port-agnostically or they drop all internal traffic --
            # out_port-qualified rules are dropped (redundant with routing: their
            # dst never egresses the qualified port), and in_port-qualified rules
            # become per-port PREFILTERS <elem>.inP that only port-P ingress
            # traverses (drop the qualified subset, default-pass the rest to
            # <elem>). Without handle_quals (a terminal filter like wl_tum, no
            # physical ports/routing) every rule is emitted port-agnostically onto
            # the one element. Returns ({port: prefilter_elem}, pre_edges).
            all_elems.append(elem)
            in_by: Dict[str, List[Tuple]] = {}
            for t in self._pf_rules.get(dev, {}).get(chain, []):
                if handle_quals and t[8] is not None:   # out_port-qualified -> skip
                    continue
                if handle_quals and t[7] is not None:   # in_port-qualified -> prefilter
                    in_by.setdefault(t[7], []).append(t)
                    continue
                rule_strings.append(_filter_rule_string(
                    elem, t[0], t[1], t[2], t[3], t[4], t[5], t[6], t[9]))
            port_target: Dict[str, str] = {}
            pre_edges: List[str] = []
            for port, prules in in_by.items():
                pre = "%s.in%s" % (elem, port)
                all_elems.append(pre)
                for t in prules:
                    rule_strings.append(_filter_rule_string(
                        pre, t[0], t[1], t[2], t[3], t[4], t[5], t[6], t[9]))
                # default: pass everything the qualified rules did not drop
                rule_strings.append(_filter_rule_string(
                    pre, 'fpass', None, None, None, None, None, None, _FILTER_PRIO_BASE))
                pre_edges.append("%s fpass %s in" % (pre, elem))
                port_target[port] = pre
            return port_target, pre_edges

        new_edges = list(edges)
        for dev in filter_devices:
            has_input_sink = any(e.split()[0] == dev
                                 and e.split()[1] == 'input_filter_accept'
                                 for e in new_edges)
            has_output_src = any(e.split()[2] == dev
                                 and e.split()[3] == 'output_filter_in'
                                 for e in new_edges)
            phys_egress = [e for e in new_edges if e.split()[0] == dev
                           and e.split()[1].isdigit()]
            # Physical ports the device is wired on (as source or dest). A device
            # that forwards between DIFFERENT physical ports is a transit router
            # (pgf); a host has a single uplink port (origin/sink only) and never
            # forwards -- so it needs no forward chain.
            phys_ports = {e.split()[1] for e in new_edges
                          if e.split()[0] == dev and e.split()[1].isdigit()}
            phys_ports |= {e.split()[3] for e in new_edges
                           if e.split()[2] == dev and e.split()[3].isdigit()}
            is_transit = len(phys_ports) >= 2
            fib = self._filter_fib.get(dev)
            has_routing = bool(phys_egress and fib)
            fib_dev = _fib_name(dev)

            # --- routing FIB: move physical egress edges onto <dev>.fib ---
            if has_routing:
                moved: List[str] = []
                for edge in new_edges:
                    s_dev, s_port, d_dev, d_port = edge.split()
                    if s_dev == dev and s_port.isdigit():
                        moved.append("%s %s %s %s" % (fib_dev, s_port, d_dev, d_port))
                    else:
                        moved.append(edge)
                new_edges = moved
                all_elems.append(fib_dev)
                for dst, egress, plen in fib:
                    rule_strings.append(_fib_rule_string(fib_dev, egress, dst, plen))

            # A packet_filter's physical ingress feeds two independent paths that
            # FaVe's pre_routing splits by dst: to-self -> INPUT chain -> probe;
            # in-transit -> FORWARD chain -> routing. A host has only the first, a
            # transit router (pgf) both, a pure-forward terminal (wl_tum) only the
            # second (wired accept -> probe by an L1 link).
            input_tgt: Dict[str, str] = {}
            fwd_tgt: Dict[str, str] = {}
            fwd_elem = dev + '.fwd'

            # --- SINK: physical ingress -> INPUT filter (element <dev>) -> probe ---
            if has_input_sink:
                input_tgt, pe = emit(dev, 'input_filter')
                new_edges += pe

            # --- TRANSIT: physical ingress ALSO -> FORWARD filter -> routing ---
            if is_transit:
                fwd_tgt, pe = emit(fwd_elem, 'forward_filter')
                new_edges += pe
                if has_routing:
                    new_edges.append("%s forward_filter_accept %s in" % (fwd_elem, fib_dev))
                    for pre in fwd_tgt.values():   # a qualified ACCEPT still reaches routing
                        new_edges.append("%s forward_filter_accept %s in" % (pre, fib_dev))

            # --- TERMINAL (no sink, no transit): single FORWARD element <dev>.
            # No physical ports/routing, so qualifiers cannot be split per-port --
            # emit every rule port-agnostically (matches NP; wl_tum fw.tum). ---
            if not has_input_sink and not is_transit:
                emit(dev, 'forward_filter', handle_quals=False)
                if has_routing:
                    new_edges.append("%s forward_filter_accept %s in" % (dev, fib_dev))

            # --- physical-ingress fan: each port -> its input AND forward target
            # (a prefilter if the port has in_port-qualified rules, else the chain
            # element). Replaces the raw physical ingress edge to <dev>. ---
            if has_input_sink or is_transit:
                fanned: List[str] = []
                for edge in new_edges:
                    s_dev, s_port, d_dev, d_port = edge.split()
                    if d_dev == dev and d_port.isdigit():
                        if has_input_sink:
                            fanned.append("%s %s %s %s" % (
                                s_dev, s_port, input_tgt.get(d_port, dev), d_port))
                        if is_transit:
                            fanned.append("%s %s %s %s" % (
                                s_dev, s_port, fwd_tgt.get(d_port, fwd_elem), d_port))
                    else:
                        fanned.append(edge)
                new_edges = fanned

            # --- host ORIGIN element <dev>.out: OUTPUT filter -> routing ---
            if has_output_src:
                out_elem = dev + '.out'
                emit(out_elem, 'output_filter')   # output has no physical ingress -> no fan
                # retarget the source's L1 link onto the OUTPUT element
                new_edges = [
                    ("%s %s %s output_filter_in" % (e.split()[0], e.split()[1], out_elem)
                     if (e.split()[2] == dev and e.split()[3] == 'output_filter_in')
                     else e)
                    for e in new_edges]
                if has_routing:
                    new_edges.append("%s output_filter_accept %s in" % (out_elem, fib_dev))

        return new_edges, all_elems, rule_strings

    def _src_seeded_source(self, cidr: Optional[str]) -> bool:
        """ Phase C1 Lever B: True iff this source's src constraint is applied at
        QUERY time (an exact src-IPv6 BDD seeded into the reachability query and
        intersected at arrival) rather than by a structural .sf FilterElement. This
        holds for the single-universe IPv6 forwarding case (no ACL division): the
        forwarding-universe arrival intersection is exact regardless of AP-partition
        alignment, so the address need not split the partition. Full-space / IPv4 /
        ACL-division sources fall back to the .sf element. """
        if cidr is None or self._acl_device is not None:
            return False
        s = str(cidr)
        if _is_full_space(s):
            return False
        return ':' in s

    def _source_seed_filters(self, edges: List[str]):
        """ Splice a FilterElement onto each source, permitting exactly the header
        space its generator INJECTS and dropping the rest.

        A generator states what a source emits. APKeep's query injects the full
        space, so without this the question asked is "can ANY packet get from
        here to there", which is a broader question than the model states and
        wider in the only direction that matters: it invents reachability.

        It used to carry the source ADDRESS alone, which was enough while every
        workload's generators injected only that. wl_cloud's matrix phase injects
        `tcp_src` too -- each service endpoint emits from its own port -- and its
        leaf tables match on it, so dropping it made **293 denied pairs look
        reachable** (1,608 violations against NetPlumber's 1,315). Nothing said
        so; the field was simply not read.

        Returns (edges, elems, rules).
        """
        seeds: Dict[str, Dict[str, Any]] = {}
        for node, injected in self._gen_fields.items():
            constrained = dict(
                (name, value) for name, value in injected.items()
                if not _is_full_space(value))
            # Phase C1 Lever B: a single-universe IPv6 source has its ADDRESS
            # constrained at QUERY time (check_compliance seeds acl_aps with the
            # exact src BDD, intersected at arrival) rather than by a structural
            # .sf element, which would split the AP partition on the address
            # (~80% of the wl_up partition). Only the address; any other injected
            # field still needs the element.
            if self._src_seeded_source(self._gen_src.get(node)):
                constrained.pop(_SRC, None)
                constrained.pop(_SRC6, None)
            if constrained:
                seeds[node] = constrained
        elems: List[str] = []
        rules: List[str] = []
        new_edges: List[str] = []
        for edge in edges:
            s_dev, s_port, d_dev, d_port = edge.split()
            if s_dev in seeds:
                sf = s_dev + '.sf'
                if sf not in elems:
                    injected = seeds[s_dev]
                    elems.append(sf)
                    rules.append(_filter_rule_string(
                        sf, 'sfpass',
                        injected.get(_PROTO),
                        injected.get(_SRC, injected.get(_SRC6)),
                        injected.get(_DST, injected.get(_DST6)),
                        injected.get(_SPORT), injected.get(_DPORT),
                        injected.get(_RELATED), 0))
                new_edges.append("%s %s %s in" % (s_dev, s_port, sf))
                new_edges.append("%s sfpass %s %s" % (sf, d_dev, d_port))
            else:
                new_edges.append(edge)
        return new_edges, elems, rules

    def _elide_passthrough_filters(self, edges: List[str], elems: List[str],
                                   rules: List[str]):
        """ Phase C1 Lever A: contract every PURE PASS-THROUGH FilterElement out of
        the graph. A filter element whose ONLY emitted rule is accept-all -> one
        port P (all match fields wildcard) forwards every packet, on any ingress, to
        P -- it is a semantic IDENTITY. In wl_up the per-host default-route FIBs
        (0/0 -> uplink) and unrestricted output filters are exactly this.

        Eliding is provably correctness-neutral: for each ingress edge `X -> E.q`
        and each egress edge `E.P -> Y` we splice `X -> Y`, then drop E, its edges,
        and its rule. This removes E from APKeep's element set -- and APKeeper.
        updateSplitAP touches EVERY element per AP split (PPM cost ~ splits x
        elements, the C1 mechanism), so each elided identity element is one fewer
        multiplier on every split, at zero semantic cost. GENERIC (fires on any
        accept-all chain; indifferent to addresses -> survives workload
        perturbation), so it does not overfit the benchmark.

        Restricted to the FILTER universe: ForwardElement sources/probes/switches
        are never touched (they are query endpoints / real forwarders, not identity
        filters). Iterated to a fixpoint so chains of pass-throughs collapse.
        Returns (edges, kept_elems, kept_rules). """
        rules_by_elem: Dict[str, List[List[str]]] = {}
        for r in rules:
            t = r.split()
            if t[1] == "filter":
                rules_by_elem.setdefault(t[2], []).append(t)

        elem_set = set(elems)
        dropped: set = set()
        edges = list(edges)
        changed = True
        while changed:
            changed = False
            for elem in list(elem_set - dropped):
                ers = rules_by_elem.get(elem, [])
                # pass-through iff exactly one explicit rule and it is accept-all
                # (the FilterElement's implicit default-drop is then never reached)
                if len(ers) != 1 or not _is_acceptall_filter_rule(ers[0]):
                    continue
                out_port = ers[0][5]
                ingress = [e.split() for e in edges if e.split()[2] == elem]
                egress = [e.split() for e in edges
                          if e.split()[0] == elem and e.split()[1] == out_port]
                spliced = ["%s %s %s %s" % (i[0], i[1], o[2], o[3])
                           for i in ingress for o in egress]
                edges = [e for e in edges
                         if e.split()[0] != elem and e.split()[2] != elem]
                edges.extend(spliced)
                dropped.add(elem)
                changed = True

        kept_elems = [e for e in elems if e not in dropped]
        kept_rules = [r for r in rules if r.split()[2] not in dropped]
        self._build_metrics_elided = len(dropped)
        return edges, kept_elems, kept_rules

    def _build_stanford_faithful(self, edges: List[str]):
        """ P7b: faithful wl_stanford VLAN model. Collapse the out-stage into the
        topology (as P7a) AND emit the mid-stage VLAN rewrite as inline NATs.

        The egress VLAN of a mid route is folded with the out-stage reset: the
        effective egress VLAN is 0 iff the out-stage resets (in_port, N) to 0
        (probes require vlan=0), else N (the transit VLAN that propagates on).
        Returns (collapsed_edges, device_nats, nat_rules). """
        mid_to_out: Dict[Tuple[str, str], Tuple[str, str]] = {}
        mid_port_to_outin: Dict[Tuple[str, str], str] = {}
        out_ext: Dict[Tuple[str, str], List[Tuple[str, str]]] = {}
        kept: List[str] = []
        for edge in edges:
            s_dev, s_port, d_dev, d_port = edge.split()
            if d_dev.split('.', 1)[0] == 'out':          # mid.X -> out.X (internal)
                mid_to_out[(d_dev, d_port)] = (s_dev, s_port)
                mid_port_to_outin[(s_dev, s_port)] = d_port
            elif s_dev.split('.', 1)[0] == 'out':        # out.X -> in.Y / probe
                out_ext.setdefault((s_dev, s_port), []).append((d_dev, d_port))
            else:
                kept.append(edge)
        for out_dev, perm in self._out_perm.items():
            for in_port, out_ports in perm.items():
                mid = mid_to_out.get((out_dev, in_port))
                if mid is None:
                    continue
                m_dev, m_port = mid
                for out_port in out_ports:
                    for d_dev, d_port in out_ext.get((out_dev, out_port), []):
                        kept.append("%s %s %s %s" % (m_dev, m_port, d_dev, d_port))

        device_nats: Dict[str, set] = {}
        nat_rules: List[str] = []
        for mid_dev, rws in self._mid_rw.items():
            router = mid_dev.split('.', 1)[1]
            reset = self._out_reset.get('out.' + router, set())
            for dst, egress_port, vlan_n in rws:
                out_inport = mid_port_to_outin.get((mid_dev, egress_port))
                effective = '0' if (out_inport is not None
                                    and (out_inport, vlan_n) in reset) else vlan_n
                ip = "0.0.0.0" if dst is None else dst.partition('/')[0]
                plen = 0 if dst is None else int((dst.partition('/')[2] or "32"))
                device_nats.setdefault(mid_dev, set()).add(egress_port)
                nat_rules.append("+ nat %s %s vlan %s %d %s" % (
                    mid_dev, egress_port, ip, plen, effective))

        # Ingress VLAN admission: one ACLElement per (in.X, physical ingress
        # port), spliced onto EVERY edge delivering there -- source and transit
        # alike -- permitting only the VLANs that port admits; the rest drop.
        # This gates transit propagation: a VLAN an upstream mid assigned
        # survives only where the next router's ingress admits it, on the port it
        # actually arrives on. Single-universe (no ACL division, set in
        # LibAPKeep) lets this compose with the mid VLAN rewrite. The element is
        # named "iacl_<idx>" (no dots/underscores in the device part) so APKeep's
        # "<a>_<b>_..._{in,out}" node convention resolves it -- stanford device
        # names like in.bbra_rtr would break the 2-token split.
        #
        # Keyed by PORT, not by device, and gated at the ARRIVAL edge rather than
        # on the one in.X -> mid.X internal edge this used to splice. The
        # per-device union is what the in-stage is NOT: every one of wl_stanford's
        # 16 routers admits a different set on each ingress port (in.goza_rtr: 151
        # tags in the union, at most 128 on any single port), so a union gate
        # admits tags the arrival port does not. The funnel could not carry a
        # per-port gate at all -- it sits downstream of the merge, where the
        # arrival port is already lost -- which is why this moves rather than
        # tightens. wl_i2's builder had the same port-blind keying and lost 11
        # pairs to it (sec. 9); here the surplus tags happened to be ones nothing
        # upstream assigns towards those ports, so it cost nothing observable.
        device_acls: Dict[str, List[str]] = {}
        acl_rules: List[str] = []
        # An in-port-agnostic admission rule (key port None) applies to every
        # port of that device, so fold it into each concrete port's set.
        anyport = {dev: vlans for (dev, port), vlans in self._in_port_vlans.items()
                   if port is None}

        def admitted(dev: str, port: str) -> set:
            return (self._in_port_vlans.get((dev, port), set())
                    | anyport.get(dev, set()))

        keys = sorted({(d_dev, d_port) for d_dev, d_port in
                       (tuple(e.split()[2:4]) for e in kept)
                       if admitted(d_dev, d_port)})
        idx_of = {k: i for i, k in enumerate(keys)}
        acl_names: set = set()
        spliced: List[str] = []
        for edge in kept:
            s_dev, s_port, d_dev, d_port = edge.split()
            idx = idx_of.get((d_dev, d_port))
            if idx is None:
                spliced.append(edge)
                continue
            node = "iacl_%d_i_in" % idx
            acl_names.add(str(idx))
            spliced.append("%s %s %s inport" % (s_dev, s_port, node))
            spliced.append("%s permit %s %s" % (node, d_dev, d_port))
        for (dev, port), idx in idx_of.items():
            # One permit rule matching the whole admitted-VLAN SET (APKeep ORs
            # the comma-separated tags), not one rule per VLAN -- far fewer
            # atomic-predicate splits, so the faithful build stays tractable.
            vlan_set = ",".join(sorted(admitted(dev, port), key=int))
            acl_rules.append(_acl_rule_string(
                "iacl_%d" % idx, True, None, None, 0, vlan=vlan_set))
        if acl_names:
            device_acls["iacl"] = sorted(acl_names, key=int)
        return (spliced, {d: sorted(p) for d, p in device_nats.items()}, nat_rules,
                device_acls, acl_rules)

    def _build_i2_faithful(self, edges: List[str]):
        """ wl_i2 faithful dst x VLAN. Unlike stanford there is no mid stage and no
        out-collapse: out.X is the real dst FIB (kept as +fwd) that ALSO rewrites
        the egress VLAN (rw=vlan:M), and in.X admits a VLAN set. Emit:

          * a NAT per out.X route: `+ nat out.X <egress_port> vlan <dstIP> <plen>
            <M>` (device_nats[out.X] = the rewritten ports); and
          * a VLAN-admission ACL on EVERY edge delivering to an in.X stage --
            transit hops (out.Y:p -> in.X:q) as much as source hops -- each
            permitting the VLAN set that in.X admits ON THAT ARRIVAL PORT
            (`iadm_<idx>`). Sources inject VLAN-unconstrained, so this
            independent admission is what makes the joint (dst,VLAN) partition a
            cross-product for BDD-APKeep while NDD keeps the fields separate.
            ACL element names avoid dots ("iadm_<idx>") for APKeep's
            `<a>_<b>_..._{in,out}` node convention.

        Both the per-port keying and the transit gate are load-bearing, and this
        used to get each of them wrong: the gate was keyed by DEVICE (the union
        over its ports) and spliced only onto source->in.X edges, so a transit
        VLAN was never checked at all. Either mistake alone turns wl_i2's true
        61 reachable pairs into 72 -- confirmed by re-running
        `bench/i2_structural_oracle.py` with one relaxed at a time, and it is
        precisely the over-approximation APKEEP_BACKEND.md Sec. 9 recorded.
        wl_stanford funnels all ingress through one in.X -> mid.X edge and gates
        there (_build_stanford_faithful), which is why only wl_i2 was affected.

        Returns (edges, device_nats, nat_rules, device_acls, acl_rules). """
        device_nats: Dict[str, set] = {}
        nat_rules: List[str] = []
        for out_dev, rws in self._out_rw.items():
            for dst, egress_port, vlan_m in rws:
                ip = "0.0.0.0" if dst is None else dst.partition('/')[0]
                plen = 0 if dst is None else int((dst.partition('/')[2] or "32"))
                device_nats.setdefault(out_dev, set()).add(egress_port)
                nat_rules.append("+ nat %s %s vlan %s %d %s" % (
                    out_dev, egress_port, ip, plen, vlan_m))

        # One admission element per (in.X, arrival port) actually reached by an
        # edge. An in-port-agnostic admission rule (key port None) applies to
        # every port of that device, so fold it into each concrete port's set.
        anyport = {dev: vlans for (dev, port), vlans in self._in_port_vlans.items()
                   if port is None}

        def admitted(dev: str, port: str) -> set:
            return (self._in_port_vlans.get((dev, port), set())
                    | anyport.get(dev, set()))

        keys = sorted({(d_dev, d_port) for d_dev, d_port in
                       (tuple(e.split()[2:4]) for e in edges)
                       if admitted(d_dev, d_port)})
        idx_of = {k: i for i, k in enumerate(keys)}
        device_acls: Dict[str, List[str]] = {}
        acl_rules: List[str] = []
        acl_names: set = set()
        spliced: List[str] = []
        for edge in edges:
            s_dev, s_port, d_dev, d_port = edge.split()
            idx = idx_of.get((d_dev, d_port))
            if idx is None:
                spliced.append(edge)
                continue
            node = "iadm_%d_i_in" % idx
            acl_names.add(str(idx))
            spliced.append("%s %s %s inport" % (s_dev, s_port, node))
            spliced.append("%s permit %s %s" % (node, d_dev, d_port))
        for (dev, port), idx in idx_of.items():
            # One permit rule carrying the whole admitted-VLAN set (APKeep ORs
            # the comma-separated tags), not one rule per VLAN -- far fewer
            # atomic-predicate splits, so the faithful build stays tractable.
            vlan_set = ",".join(sorted(admitted(dev, port), key=int))
            acl_rules.append(_acl_rule_string(
                "iadm_%d" % idx, True, None, None, 0, vlan=vlan_set))
        if acl_names:
            device_acls["iadm"] = sorted(acl_names, key=int)
        return (spliced, {d: sorted(p) for d, p in device_nats.items()}, nat_rules,
                device_acls or None, acl_rules)

    def _splice_acls(self, edges: List[str]):
        """ Wire the router's acl_in/acl_out as per-port APKeep ACLElements.

        APKeep has no VLAN field, so the VLAN becomes structural: each ingress/
        egress router port gets its own ACLElement carrying that port's VLAN
        group, spliced into the L1 link via APKeep's naming convention -- an
        "<dev>_<acl>_{in,out}" node whose "permit" port leads onward and whose
        "deny" port is unwired (denied traffic dies). Returns the rewritten edge
        list, the device_acls map and the "+ acl ..." rule strings.
        """
        dev = self._acl_device

        # Trace each source to its ingress router port: source -> switch (or the
        # router directly, e.g. the Internet source) -> router port.
        src_next: Dict[str, Tuple[str, str]] = {}
        switch_rport: Dict[str, str] = {}
        for edge in edges:
            s_dev, s_port, d_dev, d_port = edge.split()
            if s_dev in self._generators:
                src_next[s_dev] = (d_dev, d_port)
            if d_dev == dev and s_dev != dev:
                switch_rport[s_dev] = d_port  # switch's router-facing port

        def ingress_port(source: str) -> Optional[str]:
            nxt = src_next.get(source)
            if nxt is None:
                return None
            ndev, nport = nxt
            return nport if ndev == dev else switch_rport.get(ndev)

        # Map router ports -> the VLAN group to enforce there. Ports whose
        # ingress VLAN is set by pre_routing (e.g. the Internet port -> 4095)
        # come first; the rest are traced from each source's generator VLAN.
        in_port_vlan: Dict[str, str] = {
            port: vlan for port, vlan in self._iport_vlan.items()
            if vlan in self._acl_in
        }
        for source, vlan in self._gen_vlan.items():
            if vlan in self._acl_in:
                port = ingress_port(source)
                if port is not None:
                    in_port_vlan[port] = vlan
        out_port_vlan: Dict[str, str] = {
            port: vlan for vlan, port in self._vlan_to_eport.items()
            if vlan in self._acl_out
        }

        # Emit ACLElements + their rules.
        acl_names: set = set()
        acl_rules: List[str] = []
        for port, vlan in in_port_vlan.items():
            element = "%s_inACLp%s" % (dev, port)
            acl_names.add("inACLp%s" % port)
            for idx, permit, src, dst in self._acl_in[vlan]:
                acl_rules.append(_acl_rule_string(element, permit, src, dst, idx))
        for port, vlan in out_port_vlan.items():
            element = "%s_outACLp%s" % (dev, port)
            acl_names.add("outACLp%s" % port)
            for idx, permit, src, dst in self._acl_out[vlan]:
                acl_rules.append(_acl_rule_string(element, permit, src, dst, idx))

        # Splice the ACL nodes into the router's directed edges.
        new_edges: List[str] = []
        for edge in edges:
            s_dev, s_port, d_dev, d_port = edge.split()
            if d_dev == dev and d_port in in_port_vlan:        # ingress hop
                node = "%s_inACLp%s_in" % (dev, d_port)
                new_edges.append("%s %s %s inport" % (s_dev, s_port, node))
                new_edges.append("%s permit %s %s" % (node, dev, d_port))
            elif s_dev == dev and s_port in out_port_vlan:     # egress hop
                node = "%s_outACLp%s_out" % (dev, s_port)
                new_edges.append("%s %s %s inport" % (s_dev, s_port, node))
                new_edges.append("%s permit %s %s" % (node, d_dev, d_port))
            else:
                new_edges.append(edge)

        return new_edges, {dev: sorted(acl_names)}, acl_rules

    def _rewritten_fields(self) -> set:
        """ Every header field some rule in this model rewrites (`out_port`
        excluded -- rewriting it IS the forward). Read by `_query_conditions`. """
        fields: set = set()
        for rows in self._fwd_table.values():
            for row in rows:
                fields |= set(row['rw'])
        return fields - {_OUT_PORT}

    def _query_conditions(self, cond: Any, source: str, probe: str):
        """ One check's `cond` -> (related, [(rule_string, negated), ...]).

        `related` keeps its own path (`_cond_related`): both engines carry it as
        a single header bit, and it is the one condition that provably cannot be
        rewritten. Everything else becomes a FilterElement rule string the engine
        turns into a packet space and intersects with what ARRIVES at the probe.

        Two refusals, both loud, because the alternative to each is a number that
        answers a question nobody asked:

          * a field neither engine can express. Dropping it answers the
            UNCONDITIONED question -- the failure `_cond_related` was written for,
            and the one AD6_PLAN.md 9.23 is a post-mortem of.
          * a field THIS MODEL REWRITES. Constraining at arrival is equivalent to
            injecting only that traffic exactly while nothing rewrites the field:
            if something does, the two questions come apart and neither the
            arrival form nor the seed form is the check as written. wl_cloud
            rewrites both addresses, so a source- or destination-conditioned
            check on it is refused here rather than answered.
        """
        related_fields: List[Any] = []
        extra_fields: List[Any] = []
        for field in (cond or []):
            name = _cond_field(field, "name")
            # A nameless field goes to _cond_related, which already says the
            # right thing about it.
            if name is None or name == _RELATED:
                related_fields.append(field)
            else:
                extra_fields.append(field)

        related = _cond_related(related_fields, source, probe)

        rewritten = self._rewritten_fields()
        conditions: List[Tuple[str, bool]] = []
        for field in extra_fields:
            where = "check %s -> %s" % (source, probe)
            name = _cond_field(field, "name")
            if name not in _COND_SLOTS:
                raise ValueError(
                    "query condition %r on %s cannot be honoured: APKeep forces "
                    "%s, not %r. It is NOT dropped, because answering the "
                    "unconditioned question looks like a result."
                    % (field, where, "/".join(
                        list(_SUPPORTED_COND_FIELDS) + sorted(_COND_SLOTS)), name))
            if name in rewritten:
                raise ValueError(
                    "query condition %r on %s names %s, which this model "
                    "REWRITES. The condition is forced on the traffic ARRIVING "
                    "at the probe, which equals injecting only that traffic "
                    "exactly while nothing rewrites the field -- and here "
                    "something does, so the two are different questions."
                    % (field, where, name))
            slot = _COND_SLOTS[name]
            args: Dict[str, Any] = {
                'proto': None, 'src': None, 'dst': None,
                'sport': None, 'dport': None,
            }
            args[slot] = _cond_field(field, "value")
            conditions.append((
                _filter_rule_string(
                    'cond', 'cond', args['proto'], args['src'], args['dst'],
                    args['sport'], args['dport'], None, 0),
                bool(_cond_field(field, "negated"))))
        return related, conditions

    def check_compliance(self, rules: Any) -> None:
        """ rules: {probe_name: [(source_name, negated, cond), ...]}. For each
        pair, existential reachability source->probe; a violation is recorded
        when reachability disagrees with the rule's expectation.

        A check's `cond` RESTRICTS that question (wl_up asks reachability
        separately for NEW and ESTABLISHED traffic). It is honoured, or refused
        loudly -- never dropped; see _cond_related. """
        self._build()
        for probe_name, src_rules in rules.items():
            pdev, pport = _split_port(self._probes[probe_name])
            for source_name, negated, cond in src_rules:
                sdev, sport = _split_port(self._generators[source_name])
                related, conditions = self._query_conditions(
                    cond, source_name, probe_name)
                # With ACLs present, seed reachability with the source's actual
                # src-IP so source-matching ACLs bite (a 0.0.0.0/0 source -> len
                # 0 -> full space, the unconstrained case).
                src_cidr = self._gen_src.get(source_name)
                # wl_stanford probes accept only vlan=0 (traffic whose egress VLAN
                # the out-stage reset to 0); the faithful model enforces that at
                # the probe as a target-header constraint.
                tvlan = 0 if (self._stanford and self._faithful_vlan) else None
                if self._engine == 'ndd' and self._ndd_fwd_mode:
                    # pure dst-IP FIB: AtomForwarding floods the full dst space
                    # (forwarding is source-independent), no src/VLAN constraint.
                    if related is not None or conditions:
                        # This model has ONE dimension (the dst prefix); there is
                        # no other field to force, so the condition cannot be
                        # answered. Refusing beats returning the unconditioned
                        # number. (No conditioned benchmark uses this mode -- it
                        # serves wl_i2/wl_stanford's pure FIBs.)
                        raise ValueError(
                            "check %s -> %s carries a condition, but the dst-IP "
                            "atomic-forwarding model has only the destination "
                            "prefix to force it onto."
                            % (source_name, probe_name))
                    reachable = self._ndd.fwd_is_reachable(sdev, sport, pdev, pport)
                elif self._engine == 'ndd':
                    # The NDD engine takes the source's src space directly as the
                    # query-time seed (Lever B for every source); target_vlan
                    # enforces the faithful wl_stanford probe's vlan=0 at arrival.
                    reachable = self._ndd.is_reachable(
                        sdev, sport, pdev, pport, src_cidr=src_cidr,
                        target_vlan=tvlan, related=related,
                        conditions=conditions)
                elif self._acl_device is not None and src_cidr is not None:
                    prefix, plen = _cidr_to_apkeep(src_cidr)
                    reachable = self._lib.is_reachable(
                        sdev, sport, pdev, pport, prefix, plen, target_vlan=tvlan,
                        related=related, conditions=conditions)
                elif self._src_seeded_source(src_cidr):
                    # Phase C1 Lever B: single-universe IPv6 source -> seed the
                    # exact src-IPv6 BDD into the query (excludes spoofed-src
                    # reachability at arrival) instead of a partition-splitting .sf.
                    reachable = self._lib.is_reachable(
                        sdev, sport, pdev, pport, target_vlan=tvlan,
                        src_cidr=str(src_cidr), related=related,
                        conditions=conditions)
                else:
                    reachable = self._lib.is_reachable(
                        sdev, sport, pdev, pport, target_vlan=tvlan,
                        related=related, conditions=conditions)
                # `negated` True means "must not reach"; violation if the
                # observed reachability contradicts the expectation.
                must_reach = not negated
                if reachable != must_reach:
                    self._results.append((source_name, probe_name, must_reach, cond or ""))

    def get_compliance_results(self) -> List[Tuple[Any, Any, bool, str]]:
        """ Compliance violations: (source, probe, expected_reachable, cond). """
        return list(self._results)

    def clear_results(self) -> None:
        self._results = []

    # --- not yet supported (not exercised by the forwarding-only smoke) ------

    def check_anomalies(self, *args: Any, **kwargs: Any) -> None:
        raise NotImplementedError("APKeepAdapter: check_anomalies not supported")

    def add_slice(self, *args: Any, **kwargs: Any) -> None:
        raise NotImplementedError("APKeepAdapter: slices not supported")

    def del_slice(self, *args: Any, **kwargs: Any) -> None:
        raise NotImplementedError("APKeepAdapter: slices not supported")

    def dump_flows(self, *args: Any, **kwargs: Any) -> None:
        pass

    def dump_flow_trees(self, *args: Any, **kwargs: Any) -> None:
        pass

    def dump_pipes(self, *args: Any, **kwargs: Any) -> None:
        pass

    def dump_plumbing_network(self, *args: Any, **kwargs: Any) -> None:
        pass

    def remove_link(self, sport: Any, dport: Any) -> None:
        # buffered-build model: removal before build just edits the adjacency
        if sport in self.links and dport in self.links[sport]:
            self.links[sport].remove(dport)

    def delete_generator(self, node: str) -> None:
        self._generators.pop(node, None)

    def delete_probe(self, node: str) -> None:
        self._probes.pop(node, None)

    def stop(self) -> None:
        pass
