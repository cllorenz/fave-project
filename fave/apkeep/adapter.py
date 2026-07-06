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
        # buffered FaVe model -> APKeep input
        self._fwd_devices: set = set()       # ForwardElement device names
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
            return  # nothing to forward (e.g. an ACL drop or pure-match rule)
        dst = None
        for field in (rule.match or []):
            if field.name == _DST:
                dst = field.value
        # A forwarding rule with no dst match is the default route (FIB idx
        # 65535 / match=null): a 0.0.0.0/0 catch-all. APKeep's prefix trie does
        # the longest-prefix match, so /0 naturally loses to any specific route.
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
                    self._translate_fwd_rule(model.node, rule)
                    self._capture_vlan_port(rule)
                    if self._faithful_vlan and model.node.split('.', 1)[0] == 'mid':
                        self._capture_mid_rewrite(model.node, rule)
                    if self._faithful_vlan and model.node.split('.', 1)[0] == 'in':
                        self._capture_in_admission(model.node, rule)
            elif table == acl_in_t:
                self._acl_device = model.node
                self._capture_acl(self._acl_in, rules)
            elif table == acl_out_t:
                self._acl_device = model.node
                self._capture_acl(self._acl_out, rules)
            elif table == model.node + '.pre_routing':
                self._capture_iport_vlan(rules)

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
        # ForwardElement device names not implied by a topology edge still need
        # to exist; pass them all explicitly.
        # The faithful VLAN model builds far more BDD nodes (per-route rewrites +
        # per-VLAN ACLs); give it a larger table.
        bdd_table = 16_000_000 if (self._stanford and self._faithful_vlan) else 1_000_000
        self._lib.init_in_memory("fave", edges, sorted(self._fwd_devices),
                                 device_acls, device_nats, bdd_table_size=bdd_table)
        # Apply ACLs BEFORE the VLAN-rewrite NATs: the ACLs split atomic predicates
        # on VLAN, and the NAT rewrite table must be built over that final
        # partition (a later ACL split would leave APs the NAT never rewrites).
        self._lib.run(_dedup(fwd_rules) + acl_rules + nat_rules)
        self._built = True

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
                for i, vlan in enumerate(sorted(self._in_vlans[s_dev], key=int)):
                    acl_rules.append(_acl_rule_string(
                        "iacl_%d" % idx, True, None, None, i, vlan=vlan))
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
