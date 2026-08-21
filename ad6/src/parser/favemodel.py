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
from src.parser.iptables import IP6TablesParser
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


def _ip_version(addr):
    """ '6' for an IPv6-shaped address/CIDR string, else '4'. wl_ifi's router
    forwarding/ACLs are IPv4-only; wl_up's switch forwarding (this same
    fwd_rules mechanism, shared across both benchmarks -- AD6_PLAN.md §5.1)
    is IPv6. Sniffing on ':' rather than hardcoding avoids a repeat of the
    bug this fixes: _build_device_table's fwd-rule loop building an
    IPv6 dst with GenUtils.address(..., version='4') by default, which
    corrupts the condition rather than raising -- confirmed the hard way,
    traced via a chain of InstantiateEndToEnd probes down to exactly this
    one hardcoded version literal (a switch's own dst-based forward rule
    silently became unreachable, breaking every path through it). """
    return '6' if addr and ':' in addr else '4'


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
    for rule in ir.get("routing_rules", []):
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


def _is_ruleset_device(device, ir):
    """ wl_up (AD6_PLAN.md §5.1): True for a packet_filter/host device whose
    rule CONTENT comes from ad6's native IP6TablesParser on the real
    ip6tables ruleset text (Ad6Adapter.load_bench_metadata), as opposed to
    wl_ifi's router/switch devices, which stay on the original
    fwd_rules/GenUtils-per-field translation path (_build_device_table). """
    return device in (ir.get("ruleset_devices") or {})


def _is_transit(device, ir):
    """ True iff `device` has at least one real (dst-specific) routing_rules
    entry -- a forwarding router (wl_up's pgf) rather than a single-uplink
    leaf host, which only ever has the trivial dst=None default route. Purely
    data-driven (no physical-port counting needed): a leaf's own address is
    never a routing DESTINATION its own routing table discriminates on. """
    return any(
        r["dst"] is not None
        for r in ir.get("routing_rules", [])
        if r["device"] == device
    )


def _dispatch_key(device):
    return "%s_dispatch_r0" % _fwkey(device)


def entry_key(device, port, ir):
    """ The Kripke node a packet arriving at `device` via `port` starts
    processing at: that port's ingress-ACL stage if one applies (an ACL
    device, and this port is admission-checked), else straight into the
    device's own forwarding table -- or, for a wl_up-style ruleset device
    (§5.1), its dst-based to-self/in-transit dispatch (a transit router like
    pgf) or straight into its own ip6tables INPUT chain (a single-uplink leaf
    host, where every arriving packet is "to self" by construction -- see
    _is_transit). """
    fwkey = _fwkey(device)
    if _is_ruleset_device(device, ir):
        if _is_transit(device, ir):
            return _dispatch_key(device)
        return "%s_input_r0" % fwkey
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


_STATE_FOR_RELATED = {"0": "NEW", "1": "ESTABLISHED"}


def _acl_rule(fwkey, stage, port, pos, src, dst, target, related=None):
    key = "%s_%s%s_r%d" % (fwkey, stage, _port_key(port), pos)
    rule = GenUtils.rule(str(pos), key=key)
    if _is_constrained(src):
        rule.append(GenUtils.address(src, direction='src', version='4'))
    if _is_constrained(dst):
        rule.append(GenUtils.address(dst, direction='dst', version='4'))
    state = _STATE_FOR_RELATED.get(related)
    if state is not None:
        rule.append(GenUtils.state(state))
    rule.append(GenUtils.action('jump', target=target))
    return key, rule


_MATCH_ALL = frozenset({"0.0.0.0/0", "::/0", "0::0/0", None})


def _is_constrained(cidr):
    """ False for a match-all address (None, or the literal "0.0.0.0/0" FaVe
    emits for an explicit "any" ACL match). A match-all condition is exactly
    "no condition", so this omits the <ip> element entirely rather than
    asserting it -- semantically identical either way, and one fewer
    variable in the encoding.

    This used to be load-bearing, not just a simplification:
    XMLUtils.ConvertCIDRToVariables truncated a /0 prefix's bit-vector to
    zero bits (Count*2 == 0), producing a Kripke node whose Gamma was an
    EMPTY <conjunction/> instead of a trivially-true condition -- and
    Instantiator._ShortenPrefixes treats a /0 entry as a (trivial) prefix of
    every other same-direction CIDR, splicing a reference to it into their
    conjunctions too, so the corruption spread to rules that never
    mentioned 0.0.0.0/0 at all. Fixed in ad6 core 2026-08-21 --
    ConvertCIDRToVariables now returns XMLUtils.constant() for a /0 prefix;
    see ad6/FAVE_CHANGES.md §7 and
    ad6/test/core/instantiatortest.py:testMatchAllReachable for the
    regression test. Kept here anyway: omitting a redundant condition is
    good hygiene independent of whether the underlying bug is fixed. """
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
        for pos, (_idx, permit, src, dst, related) in enumerate(entries):
            target = forward_key if permit else DROP_KEY
            _key, rule = _acl_rule(fwkey, "iacl", port, pos, src, dst, target, related)
            rules.append(rule)
        deny_key = "%s_iacl%s_denyall" % (fwkey, _port_key(port))
        deny_rule = GenUtils.rule(str(len(entries)), key=deny_key)
        deny_rule.append(GenUtils.action('jump', target=DROP_KEY))
        rules.append(deny_rule)

    for pos, fr in enumerate(fwd_rules):
        key = "%s_fwd_r%d" % (fwkey, pos)
        rule = GenUtils.rule(str(pos), key=key)
        if _is_constrained(fr["dst"]):
            rule.append(GenUtils.address(
                fr["dst"], direction='dst', version=_ip_version(fr["dst"])))
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
            for pos, (_idx, permit, src, dst, related) in enumerate(entries):
                target = iface_target if permit else DROP_KEY
                _key, rule = _acl_rule(fwkey, "eacl", port_no, pos, src, dst, target, related)
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


_GEN_OUTPUT_PORT = "output_filter_in"


def _gen_firewall(source_name, ir):
    """ A generator's own dedicated 1-rule firewall: unconditionally jumps to
    wherever its attachment device/port starts processing. No other rule
    ever targets this firewall's rule -- see gen_entry_key.

    Two attachment shapes (AD6_PLAN.md §5.1): a wl_ifi-style generator wires
    to a REAL physical port (e.g. a switch port) -- topology-arrival
    semantics, entry_key. A wl_up-style ruleset-device generator instead
    wires to that device's OWN internal "<device>.output_filter_in" marker
    port (FaVe's own convention for "this device originates traffic
    locally") -- which is NOT a physical port entry_key understands, and
    means something different: enter that device's OWN ip6tables OUTPUT
    chain directly, not its to-self/in-transit dispatch. wl_up's own
    "internet" generator is the one exception that DOES wire to a real
    physical port (pgf's uplink) and correctly falls through to entry_key,
    exactly like any other topology-arriving neighbour. """
    device, phys_port = _attachment(source_name, ir)
    if phys_port == _GEN_OUTPUT_PORT and _is_ruleset_device(device, ir):
        target = "%s_output_r0" % _fwkey(device)
    else:
        target = entry_key(device, phys_port, ir)
    fw = GenUtils.firewall(_gen_fwkey(source_name))
    table = GenUtils.table('gen')
    rule = GenUtils.rule('0', key=gen_entry_key(source_name))
    rule.append(GenUtils.action('jump', target=target))
    table.append(rule)
    fw.append(table)
    return fw


_ACCEPT_JUMP = ".//table[@name='%s']//action[@type='jump']"
_INPUT_ACCEPT_PORT = "input_filter_accept"


def _routing_table(device, ir):
    """ wl_up (AD6_PLAN.md §5.1): dst-LPM egress selection for a ruleset
    device, from Ad6Adapter._translate_routing_rule's captured
    routing_rules -- the ip6tables ruleset text itself has no notion of
    routing (that's a network-layer decision, not a firewall-chain match),
    so this is built the same way _build_device_table already builds
    wl_ifi's router forwarding table: sequential first-match, dst-specific
    before the dst=None default (ad6 has no LPM; wl_up's own routing table
    never has two overlapping-prefix routes on one device, confirmed via
    the captured rules, so "specific before default" is exact here too). """
    fwkey = _fwkey(device)
    table = GenUtils.table('routing')
    rules = sorted(
        (r for r in ir.get("routing_rules", []) if r["device"] == device),
        key=lambda r: r["prio"],
    )
    for pos, r in enumerate(rules):
        key = "%s_routing_r%d" % (fwkey, pos)
        rule = GenUtils.rule(str(pos), key=key)
        if _is_constrained(r["dst"]):
            rule.append(GenUtils.address(r["dst"], direction='dst', version='6'))
        port_dev, port_no = _split(r["port"])
        rule.append(GenUtils.action('jump', target=iface_key(port_dev, port_no) + "_out"))
        table.append(rule)
    return table, "%s_routing_r0" % fwkey


def _dispatch_table(device, ir):
    """ wl_up (AD6_PLAN.md §5.1): a transit ruleset device's (pgf) to-self/
    in-transit split -- FaVe's own `pre_routing` table does exactly this
    dst-match dispatch (see the module docstring's investigation trace), but
    since its content is a plain address match + jump, it is cheaper and
    just as faithful to rebuild directly from the device's own known address
    (Ad6Adapter.load_bench_metadata's topology.json read) than to also
    capture and translate `pre_routing`'s rules. One shared entry point
    regardless of ingress port: the check itself (dst == my own address?)
    does not depend on which physical port the packet arrived on, unlike
    wl_ifi's per-port ACL groups (whose CONTENT genuinely differs port to
    port) -- confirmed against the real capture: wl_up's own pre_routing
    duplicates this same check once per ingress port, which is FaVe's
    internal pipeline shape, not a semantic requirement. """
    fwkey = _fwkey(device)
    own_addr = (ir.get("device_addr") or {}).get(device)
    table = GenUtils.table('dispatch')
    to_self = GenUtils.rule('0', key=_dispatch_key(device))
    if own_addr:
        to_self.append(GenUtils.address(own_addr, direction='dst', version='6'))
    to_self.append(GenUtils.action('jump', target="%s_input_r0" % fwkey))
    table.append(to_self)
    transit = GenUtils.rule('1', key="%s_dispatch_r1" % fwkey)
    transit.append(GenUtils.action('jump', target="%s_forward_r0" % fwkey))
    table.append(transit)
    return table


def _build_ruleset_firewall(device, ir):
    """ wl_up (AD6_PLAN.md §5.1): build a device's firewall from its real
    ip6tables ruleset text via ad6's own native IP6TablesParser (proven at
    scale on wl_tum's 3795 rules) instead of hand-translating FaVe's
    already-parsed Match/Action objects field by field -- the ruleset files
    ARE ip6tables text, confirmed byte-identical to ad6's own bundled
    bench/up rulesets (AD6_PLAN.md §3.2/§4.1), so this is the same "feed ad6
    its native format directly" principle wl_tum already established.

    IP6TablesParser resolves every chain's "-j ACCEPT" to ONE shared
    "<fwkey>_accept_r0" sink regardless of which chain (INPUT/OUTPUT/
    FORWARD) reached it -- correct for the ACCEPT/DROP decision itself
    (independently computed per chain), but wrong for what happens AFTER
    accept: INPUT-accept means "deliver locally" (this device's own
    accept_r0 stays the probe-delivery sink, unchanged), while OUTPUT/
    FORWARD-accept means "continue to this device's OWN routing decision"
    (a DIFFERENT continuation the shared sink can't express). Fixed by
    rewriting OUTPUT's and FORWARD's own accept-jump targets (scoped by
    table, via XPath -- INPUT's is left untouched) to this device's routing
    table entry point instead of the shared sink. """
    fwkey = _fwkey(device)
    ruleset_text = ir["ruleset_devices"][device]
    firewall = IP6TablesParser.parse(ruleset_text, fwkey)

    accept_key = "%s_accept_r0" % fwkey
    routing_table, routing_entry = _routing_table(device, ir)
    for chain in ('output', 'forward'):
        for action in firewall.xpath(_ACCEPT_JUMP % chain):
            if action.attrib.get('target') == accept_key:
                action.attrib['target'] = routing_entry
    firewall.append(routing_table)

    if _is_transit(device, ir):
        firewall.append(_dispatch_table(device, ir))

    return firewall


def query_destination_key(dst_dev, dst_port, ir):
    """ The Kripke node a compliance check's probe attachment resolves to.
    wl_ifi-style: a probe wires to a device's own declared physical/logical
    interface (iface_key's "_out" convention). wl_up-style (AD6_PLAN.md
    §5.1): a probe instead wires to a ruleset device's internal
    "input_filter_accept" marker port -- FaVe's own convention for "this
    device is the delivery target of its own INPUT chain" ("internet"'s
    probe is the one exception that wires to a REAL physical port, pgf's
    uplink, and correctly falls through to the iface_key case like any
    other topology attachment).

    NOT the device's shared "<fwkey>_accept_r0" sink -- ad6's own
    KripkeUtils.ConvertToKripke ALWAYS calls _RedirectInputs, which
    specifically rewrites every accept-jump reachable from a chain literally
    named "input" (any "..._input_r0"-keyed entry) away from the shared sink
    onto a dedicated "<input_entry_key>_accept" node instead (found the hard
    way: querying the shared sink directly returned UNSAT for an obviously-
    satisfiable single-rule INPUT chain, traced via
    Kripke.IterBTransitions/IterFTransitions to this redirect). This is
    exactly the mechanism that makes multi-chain accept-sharing safe in
    ad6's own native model -- FORWARD/OUTPUT chains are NOT redirected this
    way, which is why _build_ruleset_firewall must retarget their
    accept-jumps to routing itself (a plain jump target does not go through
    this INPUT-specific redirect). """
    if dst_port == _INPUT_ACCEPT_PORT and _is_ruleset_device(dst_dev, ir):
        return "%s_input_r0_accept" % _fwkey(dst_dev)
    return iface_key(dst_dev, dst_port) + "_out"


def build_config(ir):
    """ ir: the JSON-decoded IR from Ad6Adapter._build_ir(). Returns an lxml
    Element ready for KripkeUtils.ConvertToKripke (after XMLUtils.deannotate,
    same as any other ad6 config). """
    config = GenUtils.config()

    firewalls = GenUtils.firewalls()
    ports_by_device = _collect_ports(ir)
    for device in ir["devices"]:
        if _is_ruleset_device(device, ir):
            firewalls.append(_build_ruleset_firewall(device, ir))
            continue
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
