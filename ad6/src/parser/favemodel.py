#/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2026 Claas Lorenz <claas_lorenz@genua.de>

# This file is part of ad6.

# ad6 is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# ad6 is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with ad6.  If not, see <https://www.gnu.org/licenses/>.

""" Build an ad6 Config tree directly from FaVe's neutral model IR
(fave/ad6/adapter.py), bypassing IP6TablesParser/Cisco-ACL text entirely
(AD6_PLAN.md §4.4 -- FaVe parses the config, this module is the "ad6-adapter"
that emits ad6's own IR from FaVe's already-parsed model).

First milestone (matches wl_ifi): IPv4 dst-IP forwarding (routers + switches)
+ ingress/egress ACLs. VLAN is structural only (which port's ACL group
applies), never a match field.

Uses GenUtils' existing element factories exactly as IP6TablesParser does --
this module is a second FRONTEND, not a change to the Kripke/Instantiator/
solver backend (which stays fully generic over whatever GenUtils-shaped
Config tree it is handed).

Design notes (see AD6_PLAN.md §4.4 for the experiment this relies on):
  * A rule's `action type="jump"` can target ANY declared node directly,
    including a specific egress interface -- not only the generic shared
    "accept" node KripkeUtils._ConnectOutputs floods to every declared
    out-interface of a firewall. Every forwarding rule here jumps straight
    to its resolved egress interface's `_out` node (or an egress-ACL
    sub-table when one applies), so _ConnectOutputs's accept/flood
    machinery is never exercised -- it is the right model for a stateless
    filter chain (ad6's native use case), not a router with a real routing
    decision.
  * Cisco ACL "permit" means "stop evaluating this ACL, continue with
    whatever processing follows it" -- NOT "fall through to the next ACL
    entry" (a later entry in the SAME acl must not re-examine a permitted
    packet). So every ACL rule here (permit or deny) is an unconditional
    jump: permit -> the first key of the next processing stage; deny -> the
    shared drop sink. Table order for the ACL device is: [ingress-ACL
    groups, one per admission-checked port, each ending in an implicit
    deny-all] -> [forwarding rules, longest-prefix first].
"""

from src.core.kripke import KripkeUtils
from src.core.instantiator import Instantiator
from src.sat.satutils import SATUtils
from src.xml.genutils import GenUtils
from src.xml.xmlutils import XMLUtils

DROP_FW = "ad6fave_drop"
DROP_KEY = DROP_FW + "_r0"
_NET = "favenet"


def _fwkey(device):
    return "fw_" + device.replace('.', '_').replace('-', '_')


def iface_key(device, port):
    """ Must match what KripkeUtils._HandleInterface will derive for the
    <node name="{device-with-dots-replaced}"><interface name="{port}"/></node>
    this module emits: NetKey + '_' + NodeName + '_' + InterfaceName. """
    return "%s_%s_%s" % (_NET, device.replace('.', '_').replace('-', '_'), _port_key(port))


def _port_key(port):
    return str(port).replace('.', '_').replace('-', '_')


def _gen_fwkey(source_name):
    return "gensrc_" + source_name.replace('.', '_').replace('-', '_')


def gen_entry_key(source_name):
    """ The dedicated injection node for a FaVe generator/source. Every real
    query Source is one of these, never a device's own forwarding/ACL entry
    directly -- KripkeUtils._ConvertNodesToImplications's INIT exemption
    ("was this node entered") only fires for a node with ZERO backward
    transitions, and every device entry point (fwd_r0, an ACL stage) DOES
    have a real predecessor once wire_edges connects the topology (its
    neighbour's egress interface) -- marking it INIT anyway does not exempt
    it, it just adds it to the "at least one of these fired" pool, so a query
    asserting "this node's own edge fires" still has to prove the SAME real
    predecessor chain. A generator's own dedicated node is the one thing nothing
    else ever points into, so it is the only node where the INIT exemption is
    actually load-bearing. (Found by tracing an admin.ifi->internal.ifi query
    that stayed UNSAT even though every individual edge along the path looked
    right -- see AD6_PLAN.md §4.4/memory for the postmortem.) """
    return _gen_fwkey(source_name) + "_r0"


def _split(devport):
    device, _, port = devport.rpartition('.')
    return device, port


def _collect_ports(ir):
    """ device -> set of physical port strings referenced anywhere. """
    ports = {d: set() for d in ir["devices"]}

    def add(devport):
        d, p = _split(devport)
        ports.setdefault(d, set()).add(p)

    for sport, dport in ir["edges"]:
        add(sport)
        add(dport)
    for rule in ir["fwd_rules"]:
        add(rule["port"])
    for port in ir.get("generators", {}).values():
        add(port)
    for port in ir.get("probes", {}).values():
        add(port)
    for port in ir.get("in_port_vlan", {}):
        add(port)
    for port in ir.get("out_port_vlan", {}):
        add(port)
    return ports


def _ingress_ports_for(device, ir):
    """ [(port, vlan)] this device's ingress-ACL-checked ports, in a stable
    order -- must match _build_device_table's own iteration order exactly,
    since entry_key/init_keys and the table-building both derive stage keys
    from this same list independently. """
    if device != ir.get("acl_device"):
        return []
    in_port_vlan = ir.get("in_port_vlan") or {}
    out = []
    for devport, vlan in sorted(in_port_vlan.items()):
        d, p = _split(devport)
        if d == device:
            out.append((p, vlan))
    return out


def entry_key(device, port, ir):
    """ The Kripke node a packet arriving at `device` via `port` starts
    processing at: that port's ingress-ACL stage if one applies (an ACL
    device, and this port is admission-checked), else straight into the
    device's own forwarding table. """
    fwkey = _fwkey(device)
    acl_in = ir.get("acl_in") or {}
    for p, vlan in _ingress_ports_for(device, ir):
        if p == port:
            entries = acl_in.get(vlan, [])
            if entries:
                return "%s_iacl%s_r0" % (fwkey, _port_key(p))
            return "%s_iacl%s_denyall" % (fwkey, _port_key(p))
    return "%s_fwd_r0" % fwkey


def init_keys(ir):
    """ Every generator's own dedicated injection node -- ad6 INIT, so
    InstantiateBase's global "at least one init transition fires" bookkeeping
    is satisfiable (an empty Inits list injects an unconditional unsat() --
    see AD6_PLAN.md §4.4/memory). Only generator nodes qualify: they are the
    only nodes nothing else ever points into, so they are the only place
    KripkeUtils._ConvertNodesToImplications's INIT exemption ("was this node
    entered") is actually satisfied for free -- a device's own forwarding/ACL
    entry point looks like a plausible init too, but wire_edges gives it a
    real predecessor (its neighbour's egress interface), so marking it INIT
    does not exempt it from needing that predecessor proven (see
    gen_entry_key's docstring for the debugging story). Each generator's own
    unconditional jump means this never over-constrains the shared header
    space -- InstantiateBase's XOR only forces "exactly one of these fired",
    and each query's own InstantiateEndToEnd(Source, ...) call asserts which
    generator is being examined. """
    return sorted(gen_entry_key(name) for name in ir.get("generators", {}))


def _drop_firewall():
    fw = GenUtils.firewall(DROP_FW)
    table = GenUtils.table('drop')
    rule = GenUtils.rule('0', key=DROP_KEY)
    rule.append(GenUtils.action('drop'))
    table.append(rule)
    fw.append(table)
    return fw


def _acl_rule(fwkey, stage, port, pos, src, dst, target):
    key = "%s_%s%s_r%d" % (fwkey, stage, _port_key(port), pos)
    rule = GenUtils.rule(str(pos), key=key)
    if _is_constrained(src):
        rule.append(GenUtils.address(src, direction='src', version='4'))
    if _is_constrained(dst):
        rule.append(GenUtils.address(dst, direction='dst', version='4'))
    rule.append(GenUtils.action('jump', target=target))
    return key, rule


_MATCH_ALL = frozenset({"0.0.0.0/0", None})


def _is_constrained(cidr):
    """ False for a match-all address (None, or the literal "0.0.0.0/0" FaVe
    emits for an explicit "any" ACL match): XMLUtils.ConvertCIDRToVariables
    truncates a /0 prefix's bit-vector to zero bits (Count*2 == 0), producing
    a Kripke node whose Gamma is an EMPTY <conjunction/> instead of a
    trivially-true condition -- silently making every rule using it (and
    everything reachable only through it) unsatisfiable. A match-all
    condition is exactly "no condition", so the fix is to omit the <ip>
    element entirely rather than assert it -- semantically identical, and
    avoids ad6's zero-bit-CIDR corner case. """
    return cidr not in _MATCH_ALL


def _build_device_table(device, ir, ports_by_device):
    """ Returns (list-of-<rule>-elements, extra-firewalls-list) for `device`'s
    single "fwd" table, plus any egress-ACL sub-tables spliced onto its own
    firewall (kept in the same firewall, as additional <table> elements). """
    fwkey = _fwkey(device)
    is_acl_device = (device == ir.get("acl_device"))
    acl_in = ir.get("acl_in") or {}
    acl_out = ir.get("acl_out") or {}
    out_port_vlan = ir.get("out_port_vlan") or {}

    fwd_rules = sorted(
        (r for r in ir["fwd_rules"] if r["device"] == device),
        key=lambda r: r["prio"],
    )

    # --- ingress-ACL groups (this device's ports only), then fwd
    ingress_ports = _ingress_ports_for(device, ir)
    forward_key = "%s_fwd_r0" % fwkey if fwd_rules else DROP_KEY

    rules = []
    tables_extra = []   # egress-ACL sub-tables (own <table> elements)

    # Per-port isolation is structural here: each port's ACL group is its own
    # dedicated query entry point (entry_key/init_keys), reached directly via
    # wire_edges from the previous hop -- NOT chained from other ports' ACL
    # groups. A permit therefore always jumps straight to the shared
    # forwarding stage (every port ultimately routes through the same dst-IP
    # table), never to "the next port's ACL group" -- there is no such
    # relationship between two different ports' admitted traffic. (An earlier
    # version of this function wrongly chained port groups sequentially by
    # list position, which meant e.g. port 3's fallthrough leaked into port
    # 4's ACL group whenever they happened to sort adjacently -- silently
    # wrong, only surfaced by tracing actual reachability, not by reading the
    # generated XML.) These rules also do NOT need an <interface> match
    # condition: nothing wires a backward transition into an interface's
    # "_in" node (bypassed entirely, see the module docstring), so an
    # <interface direction="in"> term would be rewritten to constant(False)
    # by KripkeUtils._EnhanceInterfaceRules and make every such rule
    # unconditionally unreachable.
    for port, vlan in ingress_ports:
        entries = sorted(acl_in.get(vlan, []), key=lambda t: t[0])
        for pos, (_idx, permit, src, dst) in enumerate(entries):
            target = forward_key if permit else DROP_KEY
            _key, rule = _acl_rule(fwkey, "iacl", port, pos, src, dst, target)
            rules.append(rule)
        deny_key = "%s_iacl%s_denyall" % (fwkey, _port_key(port))
        deny_rule = GenUtils.rule(str(len(entries)), key=deny_key)
        deny_rule.append(GenUtils.action('jump', target=DROP_KEY))
        rules.append(deny_rule)

    for pos, fr in enumerate(fwd_rules):
        key = "%s_fwd_r%d" % (fwkey, pos)
        rule = GenUtils.rule(str(pos), key=key)
        if _is_constrained(fr["dst"]):
            rule.append(GenUtils.address(fr["dst"], direction='dst', version='4'))
        port_dev, port_no = _split(fr["port"])
        eacl_vlan = out_port_vlan.get(fr["port"]) if is_acl_device else None
        if eacl_vlan is not None and acl_out.get(eacl_vlan):
            target = "%s_eacl%s_r0" % (fwkey, _port_key(port_no))
        else:
            target = iface_key(port_dev, port_no) + "_out"
        rule.append(GenUtils.action('jump', target=target))
        rules.append(rule)

    if is_acl_device:
        for eport, evlan in sorted(out_port_vlan.items()):
            entries = sorted(acl_out.get(evlan, []), key=lambda t: t[0])
            if not entries:
                continue
            _d, port_no = _split(eport)
            iface_target = iface_key(device, port_no) + "_out"
            table = GenUtils.table("eacl" + _port_key(port_no))
            for pos, (_idx, permit, src, dst) in enumerate(entries):
                target = iface_target if permit else DROP_KEY
                _key, rule = _acl_rule(fwkey, "eacl", port_no, pos, src, dst, target)
                table.append(rule)
            tables_extra.append(table)

    return rules, tables_extra


def wire_edges(kripke, ir):
    """ Connect one device's egress interface to the next device's processing
    entry point for every topology edge between two REAL devices (source/probe
    attachment edges are handled separately -- see fave_bridge.py, which uses
    entry_key/iface_key directly from the query's own src_port/dst_port).

    KripkeUtils._HandleInterface never gives a declared interface's "_out"
    node an outgoing transition of its own (it is built purely from the
    network XML's <routes>, unrelated to forwarding) -- so without this, a
    router's own egress interface is a dead end and no packet ever reaches a
    second device. Kripke.Put mutates the same structure ConvertToKripke
    built, so this must run AFTER it and BEFORE Instantiator.InstantiateBase
    (which reads the transition maps to build the CNF). """
    devices = set(ir["devices"])
    for sport, dport in ir["edges"]:
        s_dev, s_port = _split(sport)
        d_dev, d_port = _split(dport)
        if s_dev not in devices or d_dev not in devices:
            continue
        kripke.Put(iface_key(s_dev, s_port) + "_out",
                   (entry_key(d_dev, d_port, ir), True))


def _attachment(source_name, ir):
    """ The real "device.port" a generator/probe (identified by its OWN
    "device.port" in ir["generators"]/ir["probes"], e.g.
    "source.admin.ifi.1") is wired to in the topology -- i.e. the OTHER end
    of its one edge, NOT its own port identity (which names no real device
    at all and must never be fed to entry_key/iface_key). """
    devices = set(ir["devices"])
    for sport, dport in ir["edges"]:
        s_dev, s_port = _split(sport)
        if s_dev == source_name:
            d_dev, d_port = _split(dport)
            if d_dev in devices:
                return d_dev, d_port
        d_dev, d_port = _split(dport)
        if d_dev == source_name:
            s_dev, s_port = _split(sport)
            if s_dev in devices:
                return s_dev, s_port
    raise KeyError("no topology edge attaches %r to a real device" % source_name)


def _gen_firewall(source_name, ir):
    """ A generator's own dedicated 1-rule firewall: unconditionally jumps to
    wherever its attachment device/port starts processing (entry_key). No
    other rule ever targets this firewall's rule -- see gen_entry_key. """
    device, phys_port = _attachment(source_name, ir)
    fw = GenUtils.firewall(_gen_fwkey(source_name))
    table = GenUtils.table('gen')
    rule = GenUtils.rule('0', key=gen_entry_key(source_name))
    rule.append(GenUtils.action('jump', target=entry_key(device, phys_port, ir)))
    table.append(rule)
    fw.append(table)
    return fw


def build_config(ir):
    """ ir: the JSON-decoded IR from Ad6Adapter._build_ir(). Returns an lxml
    Element ready for KripkeUtils.ConvertToKripke (after XMLUtils.deannotate,
    same as any other ad6 config). """
    config = GenUtils.config()

    firewalls = GenUtils.firewalls()
    ports_by_device = _collect_ports(ir)
    for device in ir["devices"]:
        fw = GenUtils.firewall(_fwkey(device))
        table = GenUtils.table('fwd')
        rules, extra_tables = _build_device_table(device, ir, ports_by_device)
        for rule in rules:
            table.append(rule)
        fw.append(table)
        for extra in extra_tables:
            fw.append(extra)
        firewalls.append(fw)
    for source_name in ir.get("generators", {}):
        firewalls.append(_gen_firewall(source_name, ir))
    firewalls.append(_drop_firewall())
    config.append(firewalls)

    networks = GenUtils.networks()
    network = GenUtils.network(_NET)
    for device in ir["devices"]:
        node = GenUtils.node(device.replace('.', '_').replace('-', '_'))
        for port in sorted(ports_by_device.get(device, [])):
            node.append(GenUtils.interface(port, iface_key(device, port)))
        node.append(GenUtils.nodeFirewall(_fwkey(device)))
        network.append(node)
    networks.append(network)
    config.append(networks)

    return config


def instantiate_base(config, ir):
    """ Instantiator.InstantiateBase's own body, with wire_edges spliced in
    between KripkeUtils.ConvertToKripke and the base-implication build --
    there is no public seam for this, so this necessarily calls a couple of
    ad6-internal (underscore-prefixed) Instantiator helpers directly rather
    than duplicating their logic. Keep in sync with
    src/core/instantiator.py:InstantiateBase if that changes. """
    kripke = KripkeUtils.ConvertToKripke(config, default_inits=False)
    for init in init_keys(ir):
        node = kripke.GetNode(init)
        if XMLUtils.INIT not in node.Props:
            node.Props.append(XMLUtils.INIT)
        kripke.PutInit(init, node)
    wire_edges(kripke, ir)

    encoding = Instantiator._InstantiateBase(kripke)
    handled = {}
    for variable in encoding.iterdescendants(XMLUtils.VARIABLE):
        Instantiator._HandlePrefixes(variable, handled)
        Instantiator._HandlePorts(variable, handled)
        Instantiator._HandleVlans(variable, handled)
        Instantiator._HandleOthers(variable, handled)
    keys = list(handled)
    src_keys = [k for k in keys if k.startswith('src_')]
    dst_keys = [k for k in keys if k.startswith('dst_')]
    Instantiator._ShortenPrefixes(handled, src_keys)
    Instantiator._ShortenPrefixes(handled, dst_keys)
    encoding[0].extend(list(handled.values()))
    encoding[0].extend(Instantiator._CreateGlobalConstraints(kripke, encoding))
    SATUtils.ConvertToCNF(encoding)

    return kripke, encoding
