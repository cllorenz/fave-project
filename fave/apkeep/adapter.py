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

from typing import Any, Dict, List, Optional, Tuple

from aggregator.abstract_engine import AbstractVerificationEngine
from aggregator.aggregator_abstract import TraceLogger
from rule.rule_model import Forward, Rewrite

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
# forward_filter is first-match on rule index (lower index wins); APKeep's
# FilterElement is higher-priority-wins, so invert the index. The base exceeds
# the largest forward_filter index (a TUM ruleset has ~5k rules).
_FILTER_PRIO_BASE = 10_000_000


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
                 faithful_vlan: bool = False) -> None:
        self.logger = logger
        self._lib = LibAPKeep()
        # P7b: when set, model the wl_stanford VLAN semantics faithfully (mid-stage
        # VLAN rewrite via NAT + probe vlan=0 filter) instead of the forwarding-only
        # out-stage collapse (P7a, which only matches the artificial all-to-all
        # policy). Off by default so the P7a path/test are unchanged.
        self._faithful_vlan = faithful_vlan
        # mid.X -> [(dst_cidr, egress_port, vlan_N)] ; out.X reset set {(inport130, vlan)}
        self._mid_rw: Dict[str, List[Tuple[Optional[str], str, str]]] = {}
        self._out_reset: Dict[str, set] = {}
        self._in_vlans: Dict[str, set] = {}   # in.X -> admitted (permit) VLAN tags
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
        self._router_fib: Dict[str, List[Tuple[Optional[str], str, int]]] = {}
        self._ipv6_fib_devices: set = set()
        # A transit packet_filter (wl_up: pgf, dept routers) both filters AND routes:
        # its forward_filter accepts to the internal `forward_filter_accept` port,
        # which FaVe wires (internally) to a routing table (dst-IP LPM -> physical
        # egress). A terminal filter (wl_tum: fw.tum) instead has an L1 link
        # accept->probe, so no routing is needed. For transit filters we model the
        # routing as a companion FilterElement (a first-match dst-LPM FIB) chained
        # off the accept port -- see _build_pf_pipeline. device -> [(dst, egress, plen)].
        self._filter_fib: Dict[str, List[Tuple[Optional[str], str, int]]] = {}
        self._fwd_rules: List[str] = []      # APKeep "+ fwd ..." strings
        self._edges: List[str] = []          # topology "dev port dev port"
        self._generators: Dict[str, str] = {}  # name -> ingress port (FaVe)
        self._probes: Dict[str, str] = {}      # name -> port (FaVe)
        self._built = False
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
        self._gen_vlan: Dict[str, str] = {}       # source node -> ingress VLAN
        # wl_stanford: the HSA model splits every router into in./mid./out.
        # switches. in.=ingress ACL (pass-through here), mid.=dst-IP FIB, and
        # out.=an input-port->output-port permutation (a pure wire) that a dst-IP
        # ForwardElement cannot express. We recognise the out. stage and collapse
        # it into the topology (mid egress port -> external neighbour) at build.
        self._stanford = False
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
            self._fwd_rules.append(
                "+ fwd %s %d %d __drop__ %d" % (device, prefix, plen, plen)
            )
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
                self._router_fib.setdefault(device, []).append((dst6, port, plen6))
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
                self._router_fib.setdefault(device, []).append((None, port, 0))
        prefix, plen = (0, 0) if dst is None else _cidr_to_apkeep(str(dst))
        # APKeep's ForwardElement is higher-priority-wins, so the priority must
        # encode longest-prefix-match: a longer prefix must outrank a shorter
        # one regardless of rule arrival order. Use the prefix length directly
        # -- otherwise a later-added default route (/0) can shadow a specific
        # route and the device forwards everything to its default port.
        for port in out_ports:
            self._fwd_rules.append(
                "+ fwd %s %d %d %s %d" % (device, prefix, plen, port, plen)
            )

    # --- AbstractVerificationEngine: model construction (buffered) -----------

    def add_tables(self, model: Any) -> None:
        # Routers and switches all become dst-IP ForwardElements. The wl_stanford
        # out. stage is an in-port permutation (not a FIB) collapsed into the
        # topology at build -- but that is decided THERE, keyed on the mid. stage
        # (unique to stanford; wl_i2 is in/out only and its out. stage is a real
        # dst-IP FIB that must be kept). Add every device here.
        self._fwd_devices.add(model.node)

    def add_rules(self, model: Any) -> None:
        # Only the router's routing table and the switch's flat table hold real
        # dst-IP forwarding. The router's pre_routing/post_routing carry VLAN/
        # egress plumbing, and acl_in/acl_out carry ACL rules that "forward" to
        # internal pipeline ports (e.g. ifi.acl_in_out) -- translating those
        # would emit bogus APKeep ports. So restrict to the forwarding tables.
        if model.node.split('.', 1)[0] == 'out':
            # wl_stanford: record the in-port permutation (+ VLAN resets) for the
            # build-time collapse. Harmless for wl_i2 (never collapsed). Fall
            # through so the out. rules are ALSO translated as a FIB -- correct for
            # wl_i2; the stanford permutation forwards are dropped at collapse.
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
                    self._translate_fib_rule(model.node, rule)
                    self._translate_fwd_rule(model.node, rule)
                    self._capture_vlan_port(rule)
                    if self._faithful_vlan and model.node.split('.', 1)[0] == 'mid':
                        self._capture_mid_rewrite(model.node, rule)
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
        out_ports = self._out_ports(rule)
        out_port = out_ports[0] if out_ports else _FILTER_DROP
        self._pf_rules.setdefault(device, {}).setdefault(chain, []).append(
            (out_port, proto, src, dst, sport, dport, related, rule.idx))

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
        if egress is None:
            has_action = bool(rule.actions)
            if dst is not None and not has_action:
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
                self._in_vlans.setdefault(node, set()).add(str(field.value))

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
                if fname == _SRC:
                    self._gen_src[model.node] = rfields[0].value
                elif fname == _VLAN:
                    self._gen_vlan[model.node] = str(rfields[0].value)

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
        if self._stanford:
            # The out. stage is not a ForwardElement: drop its devices and the
            # (broken /0) forwards translated from its permutation rules; the
            # collapse re-wires the mid. egress interfaces to the neighbours.
            self._fwd_devices = {d for d in self._fwd_devices
                                 if d.split('.', 1)[0] != 'out'}
            fwd_rules = [r for r in fwd_rules
                         if r.split()[2].split('.', 1)[0] != 'out']
            if self._faithful_vlan:
                (edges, device_nats, nat_rules,
                 device_acls, acl_rules) = self._build_stanford_faithful(edges)
            else:
                edges = self._collapse_out_stage(edges)
        if self._acl_device is not None:
            edges, device_acls, acl_rules = self._splice_acls(edges)
        # Honour in-stage admission: drop traffic entering an ingress port no rule
        # admits (a real router drops it; our in-port-agnostic ForwardElement would
        # not). No-op unless an in-stage device has a finite admitted-port set.
        edges = self._gate_dead_ingress(edges)
        # ForwardElement device names not implied by a topology edge still need
        # to exist; pass them all explicitly.
        # The faithful VLAN model builds far more BDD nodes (per-route rewrites +
        # per-VLAN ACLs); give it a larger table.
        bdd_table = 16_000_000 if (self._stanford and self._faithful_vlan) else 1_000_000
        # Each packet_filter becomes a small subgraph of FilterElements (its
        # input/output/forward chains + a dst-LPM routing FIB), wired per the
        # device's role. Terminal filters (wl_tum) stay a single FilterElement.
        edges, pf_elems, pf_rules = self._build_pf_pipeline(
            edges, sorted(self._filter_devices))
        # Plain IPv6 routers become dst-LPM FilterElement FIBs (the device itself);
        # their IPv4-collapsed `+ fwd` rules are dropped below.
        ipv6_routers = sorted(self._ipv6_fib_devices - self._filter_devices)
        router_fib_rules: List[str] = []
        for dev in ipv6_routers:
            for dst, egress, plen in self._router_fib.get(dev, []):
                router_fib_rules.append(_fib_rule_string(dev, egress, dst, plen))
        filter_devices = pf_elems + ipv6_routers
        as_filter = self._filter_devices | set(ipv6_routers)
        fwd_devices = sorted(self._fwd_devices - as_filter)
        # A device modelled as a FilterElement must not also carry its (IPv4-only,
        # here mis-collapsed) `+ fwd` dst-FIB rules -- a `+ fwd` dispatches by device
        # name and would land on the FilterElement and fail to parse. Drop them.
        fwd_rules = [r for r in fwd_rules if r.split()[2] not in as_filter]
        self._lib.init_in_memory("fave", edges, fwd_devices,
                                 device_acls, device_nats,
                                 device_filters=filter_devices or None,
                                 bdd_table_size=bdd_table)
        # Apply ACLs BEFORE the VLAN-rewrite NATs: the ACLs split atomic predicates
        # on VLAN, and the NAT rewrite table must be built over that final
        # partition (a later ACL split would leave APs the NAT never rewrites).
        self._lib.run(_dedup(fwd_rules) + acl_rules + nat_rules
                      + pf_rules + router_fib_rules)
        self._built = True

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

        def emit(elem: str, chain: str) -> None:
            all_elems.append(elem)
            for (out_port, proto, src, dst, sport, dport, related, idx) in \
                    self._pf_rules.get(dev, {}).get(chain, []):
                rule_strings.append(_filter_rule_string(
                    elem, out_port, proto, src, dst, sport, dport, related, idx))

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
            # second (wired accept -> probe by an L1 link). We model each present
            # path as its own element sharing the physical ingress.

            # --- SINK: physical ingress -> INPUT filter (element <dev>) -> probe ---
            if has_input_sink:
                emit(dev, 'input_filter')

            # --- TRANSIT: physical ingress ALSO -> FORWARD filter -> routing ---
            if is_transit:
                fwd_elem = dev + '.fwd'
                emit(fwd_elem, 'forward_filter')
                if has_routing:
                    new_edges.append("%s forward_filter_accept %s in" % (fwd_elem, fib_dev))
                # fan every physical ingress edge to the forward element too
                extra = []
                for edge in new_edges:
                    s_dev, s_port, d_dev, d_port = edge.split()
                    if d_dev == dev and d_port.isdigit():
                        extra.append("%s %s %s %s" % (s_dev, s_port, fwd_elem, d_port))
                new_edges += extra

            # --- TERMINAL (no sink, no transit): single FORWARD element <dev> ---
            if not has_input_sink and not is_transit:
                emit(dev, 'forward_filter')     # accept -> forward_filter_accept (L1 -> probe)
                if has_routing:
                    new_edges.append("%s forward_filter_accept %s in" % (dev, fib_dev))

            # --- host ORIGIN element <dev>.out: OUTPUT filter -> routing ---
            if has_output_src:
                out_elem = dev + '.out'
                emit(out_elem, 'output_filter')
                # retarget the source's L1 link onto the OUTPUT element
                new_edges = [
                    ("%s %s %s output_filter_in" % (e.split()[0], e.split()[1], out_elem)
                     if (e.split()[2] == dev and e.split()[3] == 'output_filter_in')
                     else e)
                    for e in new_edges]
                if has_routing:
                    new_edges.append("%s output_filter_accept %s in" % (out_elem, fib_dev))

        return new_edges, all_elems, rule_strings

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

        # Ingress VLAN admission: splice a per-router ACLElement onto the single
        # in.X -> mid.X internal edge (all ingress funnels through it), permitting
        # only the VLANs the in-stage admits; the rest drop. This gates transit
        # propagation -- a VLAN an upstream mid assigned survives only where the
        # next router's ingress admits it. Single-universe (no ACL division, set
        # in LibAPKeep) lets this compose with the mid VLAN rewrite. The element is
        # named "iacl_<idx>" (no dots/underscores in the device part) so APKeep's
        # "<a>_<b>_..._{in,out}" node convention resolves it -- stanford device
        # names like in.bbra_rtr would break the 2-token split.
        device_acls: Dict[str, List[str]] = {}
        acl_rules: List[str] = []
        routers = sorted({d.split('.', 1)[1] for d in self._in_vlans})
        idx_of = {r: i for i, r in enumerate(routers)}
        acl_names: set = set()
        spliced: List[str] = []
        for edge in kept:
            s_dev, s_port, d_dev, d_port = edge.split()
            router = s_dev.split('.', 1)[1] if '.' in s_dev else None
            if (s_dev.split('.', 1)[0] == 'in' and d_dev.split('.', 1)[0] == 'mid'
                    and router in idx_of and self._in_vlans.get(s_dev)):
                idx = idx_of[router]
                node = "iacl_%d_i_in" % idx
                acl_names.add(str(idx))
                spliced.append("%s %s %s inport" % (s_dev, s_port, node))
                spliced.append("%s permit %s %s" % (node, d_dev, d_port))
                # One permit rule matching the whole admitted-VLAN SET (APKeep ORs
                # the comma-separated tags), not ~114 per-VLAN rules -- far fewer
                # atomic-predicate splits, so the faithful build stays tractable.
                vlan_set = ",".join(sorted(self._in_vlans[s_dev], key=int))
                acl_rules.append(_acl_rule_string(
                    "iacl_%d" % idx, True, None, None, 0, vlan=vlan_set))
            else:
                spliced.append(edge)
        if acl_names:
            device_acls["iacl"] = sorted(acl_names, key=int)
        return (spliced, {d: sorted(p) for d, p in device_nats.items()}, nat_rules,
                device_acls, acl_rules)

    def _collapse_out_stage(self, edges: List[str]) -> List[str]:
        """ Remove the wl_stanford out. stage, splicing its port permutation into
        the topology. The physical path is mid.X.<110n> -> out.X.<130n> (internal
        link) -> out.X.<120m> (permutation rule) -> in.Y.<p> / probe (external
        link). ForwardElements route by dst-IP and cannot honour the in-port
        permutation, so we resolve the chain statically and wire the mid. egress
        interface straight to the external neighbour(s), dropping out. entirely.
        """
        mid_to_out: Dict[Tuple[str, str], Tuple[str, str]] = {}  # (out_dev,inport)->(mid_dev,port)
        out_ext: Dict[Tuple[str, str], List[Tuple[str, str]]] = {}  # (out_dev,outport)->[(dev,port)]
        kept: List[str] = []
        for edge in edges:
            s_dev, s_port, d_dev, d_port = edge.split()
            if d_dev.split('.', 1)[0] == 'out':        # mid.X -> out.X (internal)
                mid_to_out[(d_dev, d_port)] = (s_dev, s_port)
            elif s_dev.split('.', 1)[0] == 'out':      # out.X -> in.Y / probe (external)
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
        return kept

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

    def check_compliance(self, rules: Any) -> None:
        """ rules: {probe_name: [(source_name, negated, cond), ...]}. For each
        pair, existential reachability source->probe; a violation is recorded
        when reachability disagrees with the rule's expectation. """
        self._build()
        for probe_name, src_rules in rules.items():
            pdev, pport = _split_port(self._probes[probe_name])
            for source_name, negated, cond in src_rules:
                sdev, sport = _split_port(self._generators[source_name])
                # With ACLs present, seed reachability with the source's actual
                # src-IP so source-matching ACLs bite (a 0.0.0.0/0 source -> len
                # 0 -> full space, the unconstrained case).
                src_cidr = self._gen_src.get(source_name)
                # wl_stanford probes accept only vlan=0 (traffic whose egress VLAN
                # the out-stage reset to 0); the faithful model enforces that at
                # the probe as a target-header constraint.
                tvlan = 0 if (self._stanford and self._faithful_vlan) else None
                if self._acl_device is not None and src_cidr is not None:
                    prefix, plen = _cidr_to_apkeep(src_cidr)
                    reachable = self._lib.is_reachable(
                        sdev, sport, pdev, pport, prefix, plen, target_vlan=tvlan)
                else:
                    reachable = self._lib.is_reachable(
                        sdev, sport, pdev, pport, target_vlan=tvlan)
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
