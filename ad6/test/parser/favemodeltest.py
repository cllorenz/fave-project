import unittest

from copy import deepcopy

import lxml.etree as et

from src.core.instantiator import Instantiator
from src.parser import favemodel
from src.solver.incremental import IncrementalSession
from src.solver.pycosat import PycoSATAdapter
from src.solver.solver import AbstractSolver
from src.xml.genutils import GenUtils
from src.xml.xmlutils import XMLUtils


def _dst_literals(cidr):
    """ Force the destination header to a single address/CIDR -- the
    dst-direction mirror of ad6/fave_bridge.py's `_seed_literals` (there is
    no committed dst-forcing helper yet; this reuses the exact same
    XMLUtils.CanonizeIP -> XMLUtils.ConvertCIDRToVariables path so the forced
    literals live in the same shared bit-vector space a routing rule's own
    <ip direction="dst"> condition is built over, not a bare named-alias
    variable that would only bind by coincidence -- see fave_bridge.py's
    docstring for why that distinction is load-bearing). """
    version = '6' if ':' in cidr else '4'
    elem = et.fromstring(
        '<ip xmlns="http://config" version="%s" direction="dst">'
        '<address>%s</address></ip>' % (version, cidr)
    )
    XMLUtils.deannotate(elem)
    canonical = XMLUtils.CanonizeIP(elem)
    return list(XMLUtils.ConvertCIDRToVariables(canonical, 'dst'))


def _target_table(name, key):
    """ A dedicated 1-rule/1-table accept sink, own <table> per target
    (ad6/test/core/instantiatortest.py::testMatchAllReachable's discipline --
    sharing a table would add a spurious fallthrough edge between the two
    targets under test, unrelated to the LPM question). """
    table = GenUtils.table(name)
    rule = GenUtils.rule(name, key=key)
    rule.append(GenUtils.action('accept'))
    table.append(rule)
    return table


def _build(routes):
    """ Wire `favemodel._routing_table` -- the exact production
    building block AD6_PLAN.md §5.1 built for wl_up and §5.2 earmarks for
    reuse on Stanford/i2's FIB -- into a minimal standalone firewall, plus
    one terminal target table per route's egress port. Returns
    (kripke, encoding, {port: target_key}). """
    ir = {"routing_rules": routes}
    table, entry = favemodel._routing_table('r', ir)

    firewall = GenUtils.firewall('fw_r')
    firewall.append(table)

    target_keys = {}
    for pos, r in enumerate(routes):
        port = r["port"]
        if port in target_keys:
            continue
        port_dev, port_no = favemodel._split(port)
        target_key = favemodel.iface_key(port_dev, port_no) + "_out"
        firewall.append(_target_table("t%d" % pos, target_key))
        target_keys[port] = target_key

    config = GenUtils.config()
    firewalls = GenUtils.firewalls()
    firewalls.append(firewall)
    config.append(firewalls)

    kripke, encoding = Instantiator.InstantiateBase(
        config, Inits=[entry], default_inits=False
    )
    return kripke, encoding, target_keys


def _reachable(kripke, encoding, target_key, dst_cidr):
    instance = Instantiator.InstantiateReach(kripke, encoding, target_key)
    instance[0].extend(_dst_literals(dst_cidr))
    return bool(PycoSATAdapter().Solve(instance))


def _lpm_prio(dst):
    """ Mirrors Ad6Adapter._lpm_prio (fave/ad6/adapter.py) exactly -- ad6's
    own test tree cannot import fave/ad6/adapter.py (separate PYTHONPATH
    roots/venvs, see that module's docstring), so this is duplicated to
    build realistic fixtures here; fave/test/test_ad6_adapter_lpm_prio.py
    pins the real implementation directly. """
    if dst is None:
        return 65535
    prefix_len = int(dst.rsplit('/', 1)[1])
    return 65535 - 1 - prefix_len


class RoutingTableLPMTest(unittest.TestCase):
    """ AD6_PLAN.md §5.2 feasibility spike: does `favemodel._routing_table`
    (the dst egress-selection building block AD6_PLAN.md §5.1 built for
    wl_up, and §5.2 earmarks for reuse on Stanford/i2's FIB) resolve
    OVERLAPPING-prefix routes by longest-prefix-match, or merely by
    insertion order?

    `_routing_table`'s own docstring is explicit that it does not implement
    LPM: every dst-specific route gets the SAME `prio` (0, only the dst=None
    default gets 65535 -- fave/ad6/adapter.py's `_translate_routing_rule`),
    so `sorted(..., key=lambda r: r["prio"])` is a stable sort: whether a tie
    between two dst-specific routes resolves correctly depends entirely on
    `prio` actually encoding prefix length, not just "any dst-specific route
    before the no-dst default". A prior version of `Ad6Adapter._lpm_prio`
    (fave/ad6/adapter.py) used a binary 0-vs-65535 split, which is only exact
    when a device never carries two overlapping-prefix routes -- true for
    wl_ifi/wl_up (confirmed by inspection at the time), but false in general.
    Stanford's real FIBs are exactly the counterexample: `bbra_rtr` carries
    both a `172.28.0.0/14` route and a broader `172.16.0.0/12` entry on the
    same device, and only the longer prefix is correct (see
    [[stanford-forwarding-overapprox]] -- this is precisely the shape of bug
    that made vanilla NetPlumber's own Stanford result silently wrong,
    10/165, before its own fix).

    Fixed in `Ad6Adapter._lpm_prio` (AD6_PLAN.md §5.2): `prio` is now
    `65535 - 1 - prefix_length` for a dst-specific route (65535 for the
    no-dst default), so a longer prefix always sorts first regardless of
    capture order. This module's `_lpm_prio` duplicates that formula to
    build realistic fixtures; `fave/test/test_ad6_adapter_lpm_prio.py` pins
    the real implementation directly.

    Each test feeds the SAME two overlapping routes in BOTH insertion
    orders and asserts the specific (/64) route wins for a destination
    inside it, regardless of order -- this is now expected to PASS both
    ways (a real priority, unlike a stable-sort tie, does not depend on
    capture order at all). """

    _GENERAL = {"device": "r", "dst": "2001:db8::/32", "port": "nextA.p1"}
    _SPECIFIC = {"device": "r", "dst": "2001:db8:0:1::/64", "port": "nextB.p1"}
    _GENERAL["prio"] = _lpm_prio(_GENERAL["dst"])
    _SPECIFIC["prio"] = _lpm_prio(_SPECIFIC["dst"])
    _INSIDE_BOTH = "2001:db8:0:1::5/128"

    def _assert_specific_wins(self, routes):
        kripke, encoding, keys = _build(routes)
        general_reached = _reachable(
            kripke, encoding, keys[self._GENERAL["port"]], self._INSIDE_BOTH)
        specific_reached = _reachable(
            kripke, encoding, keys[self._SPECIFIC["port"]], self._INSIDE_BOTH)
        self.assertTrue(
            specific_reached,
            "the longer-prefix (/64) route must win for a destination "
            "inside it, but it was NOT reached")
        self.assertFalse(
            general_reached,
            "the shorter-prefix (/32) route wrongly won for a destination "
            "that also matches the longer, more specific /64 route -- "
            "_lpm_prio's longest-prefix priority regressed (AD6_PLAN.md "
            "§5.2)")

    def testGeneralInsertedFirst(self):
        """ Insertion order = [general, specific] -- the order a caller
        walking a FIB least-specific-first (e.g. as-parsed route-table order)
        would produce. Must pass regardless: a real priority does not care
        about capture order. """
        self._assert_specific_wins([self._GENERAL, self._SPECIFIC])

    def testSpecificInsertedFirst(self):
        """ Insertion order = [specific, general] -- the opposite order.
        Must agree with testGeneralInsertedFirst's result -- if it didn't,
        that would prove the outcome is (still) order-dependent, not a real
        LPM decision. """
        self._assert_specific_wins([self._SPECIFIC, self._GENERAL])

    def testNonOverlappingRoutesUnaffectedByOrder(self):
        """ Positive control: two DISJOINT dst-specific routes must each be
        reachable for their own destination regardless of insertion order --
        isolates the bug to overlap tie-breaking, not the basic dst-match/
        jump mechanism itself. """
        disjoint_a = {"device": "r", "dst": "2001:db8:1::/64", "port": "nextA.p1", "prio": 0}
        disjoint_b = {"device": "r", "dst": "2001:db8:2::/64", "port": "nextB.p1", "prio": 0}
        for routes in ([disjoint_a, disjoint_b], [disjoint_b, disjoint_a]):
            kripke, encoding, keys = _build(routes)
            self.assertTrue(_reachable(
                kripke, encoding, keys["nextA.p1"], "2001:db8:1::5/128"))
            self.assertTrue(_reachable(
                kripke, encoding, keys["nextB.p1"], "2001:db8:2::5/128"))


class GenFirewallDeadPortGateTest(unittest.TestCase):
    """ AD6_PLAN.md §5.4 Stage B (B1): a generator wired to a dead
    (unadmitted) physical port must be gated exactly like a topology edge
    into that same port already is (`_gate_dead_ingress`). Found at full
    16-router wl_stanford scale: a generator's own attachment resolves via
    `_attachment`/`entry_key` directly inside `_gen_firewall`, never
    touching `ir["edges"]`/`wire_edges` at all -- so `_gate_dead_ingress`
    alone left Stanford's 5 well-known dead-port SOURCES
    (`[[stanford-forwarding-overapprox]]`) reaching every probe. B0's own
    N=2 differential slice (`bbra_rtr,rozb_rtr`) happens to contain none of
    the 5, so this was never exercised there -- only surfaced by B1's
    full-scale live differential against NetPlumber. """

    @staticmethod
    def _ir(admit):
        return {
            "devices": ["in.dev"],
            "edges": [["source.gen.1", "in.dev.99"]],
            "in_admit": {"in.dev": admit},
            "acl_devices": [],
            "acl_in": {},
            "ruleset_devices": {},
            "fwd_rules": [],
            "routing_rules": [],
        }

    @staticmethod
    def _jump_target(firewall):
        return firewall.find('.//action').attrib['target']

    def test_generator_on_dead_port_jumps_to_drop(self):
        ir = self._ir(admit={"1", "2"})   # port "99" NOT admitted
        firewall = favemodel._gen_firewall("source.gen", ir)
        self.assertEqual(self._jump_target(firewall), favemodel.DROP_KEY)

    def test_generator_on_admitted_port_uses_normal_entry(self):
        ir = self._ir(admit={"99"})
        firewall = favemodel._gen_firewall("source.gen", ir)
        self.assertEqual(
            self._jump_target(firewall), favemodel.entry_key("in.dev", "99", ir))

    def test_generator_on_admit_all_device_uses_normal_entry(self):
        ir = self._ir(admit=None)
        firewall = favemodel._gen_firewall("source.gen", ir)
        self.assertEqual(
            self._jump_target(firewall), favemodel.entry_key("in.dev", "99", ir))


class FaithfulVlanWiringTest(unittest.TestCase):
    """ AD6_PLAN.md §5.4 Stage B (B2): favemodel.py's own consumption of the
    faithful-VLAN IR fields (Ad6Adapter._build_ir's "faithful_vlan"/
    "in_vlans"/"mid_rw"/"gen_vlan") through a REAL build_config/
    instantiate_base Kripke/CNF build and solve -- one level downstream of
    Stage A2's own hand-built GenUtils/Instantiator-only synthetic fixture
    (instantiatortest.py::testFieldMatchGatesOnMutatedSSAValue, which
    proved the core mechanism but never exercised favemodel.py's own
    wiring of it into a real IR-driven build). Ad6Adapter's own capture
    methods (_capture_in_admission/_capture_mid_rewrite/_capture_out_reset/
    _fold_mid_rewrites) are separately unit-tested fave-side against fake
    Rule objects (fave/test/test_ad6_wl_stanford_faithful.py) -- this
    starts one level downstream, from an already-built IR, same discipline
    as GenFirewallDeadPortGateTest above.

    Fixture: source.gen -> in.r (admission-checked) -> mid.r -> probe.p,
    the smallest real shape wl_stanford's own in.X/mid.X staging takes
    (in.r's own egress port 5 -> mid.r's ingress port 1 is a REAL
    device-to-device topology edge, matching how a real in.X's forwarding
    rule targets its OWN egress port -- not the next hop's port -- exactly
    like Ad6Adapter._translate_fwd_rule/_out_ports build fr["ports"]). """

    @staticmethod
    def _ir(admitted, gen_vlan, mid_rw=None, faithful_vlan=True):
        return {
            "devices": ["in.r", "mid.r"],
            "edges": [
                ["source.gen.1", "in.r.1"],
                ["in.r.5", "mid.r.1"],
                ["mid.r.2", "probe.p.1"],
            ],
            "generators": {"source.gen": "source.gen.1"},
            "probes": {"probe.p": "probe.p.1"},
            "fwd_rules": [
                {"device": "in.r", "dst": None, "ports": ["in.r.5"], "prio": 65535},
                {"device": "mid.r", "dst": None, "ports": ["mid.r.2"], "prio": 65535},
            ],
            "routing_rules": [],
            "acl_devices": [],
            "acl_in": {},
            "acl_out": {},
            "in_port_vlan": {},
            "out_port_vlan": {},
            "in_admit": {},
            "ruleset_devices": {},
            "device_addr": {},
            "faithful_vlan": faithful_vlan,
            "in_vlans": {"in.r": admitted},
            "mid_rw": {"mid.r": mid_rw or []},
            "gen_vlan": {"source.gen": gen_vlan} if gen_vlan is not None else {},
        }

    @staticmethod
    def _reachable(ir):
        config = favemodel.build_config(ir)
        XMLUtils.deannotate(config)
        kripke, encoding = favemodel.instantiate_base(config, ir)
        source = favemodel.gen_entry_key("source.gen")
        dest = favemodel.query_destination_key("probe.p", ir)
        instance = Instantiator.InstantiateEndToEnd(kripke, encoding, source, dest)
        return bool(PycoSATAdapter().Solve(instance))

    def test_admitted_vlan_reaches(self):
        ir = self._ir(admitted=["5", "7"], gen_vlan="5")
        self.assertTrue(
            self._reachable(ir),
            "source.gen's own vlan (5) is in in.r's admitted set {5,7} -- "
            "must reach probe.p")

    def test_non_admitted_vlan_is_blocked(self):
        ir = self._ir(admitted=["5", "7"], gen_vlan="6")
        self.assertFalse(
            self._reachable(ir),
            "source.gen's own vlan (6) is NOT in in.r's admitted set "
            "{5,7} -- must be blocked, not vacuously admitted")

    def test_second_admitted_value_also_reaches(self):
        ir = self._ir(admitted=["5", "7"], gen_vlan="7")
        self.assertTrue(
            self._reachable(ir),
            "proves the admitted-set OR (both members), not just the "
            "first value in the list")

    @staticmethod
    def _chain_ir(r2_admitted):
        """ source.gen -> in.r1 (admits {5}) -> mid.r1 (rewrites vlan to
        9) -> in.r2 (admits `r2_admitted`) -> probe.p. Proves rewrite and
        downstream match compose through a REAL build_config/
        instantiate_base pass -- not just Stage A2's own synthetic
        Instantiator-only fixture -- by making a SECOND router's
        admission depend on mid.r1's rewritten value, not source.gen's
        original vlan (the real Stanford shape: a transit router's mid
        stage reassigns the VLAN the next router's ingress then checks). """
        return {
            "devices": ["in.r1", "mid.r1", "in.r2"],
            "edges": [
                ["source.gen.1", "in.r1.1"],
                ["in.r1.5", "mid.r1.1"],
                ["mid.r1.2", "in.r2.9"],
                ["in.r2.5", "probe.p.1"],
            ],
            "generators": {"source.gen": "source.gen.1"},
            "probes": {"probe.p": "probe.p.1"},
            "fwd_rules": [
                {"device": "in.r1", "dst": None, "ports": ["in.r1.5"], "prio": 65535},
                {"device": "mid.r1", "dst": None, "ports": ["mid.r1.2"], "prio": 65535},
                {"device": "in.r2", "dst": None, "ports": ["in.r2.5"], "prio": 65535},
            ],
            "routing_rules": [],
            "acl_devices": [], "acl_in": {}, "acl_out": {},
            "in_port_vlan": {}, "out_port_vlan": {}, "in_admit": {},
            "ruleset_devices": {}, "device_addr": {},
            "faithful_vlan": True,
            "in_vlans": {"in.r1": ["5"], "in.r2": r2_admitted},
            "mid_rw": {"mid.r1": [[None, "mid.r1.2", "9"]]},
            "gen_vlan": {"source.gen": "5"},
        }

    def test_mid_rewrite_gates_downstream_admission(self):
        ir = self._chain_ir(r2_admitted=["9"])
        self.assertTrue(
            self._reachable(ir),
            "vlan 5 admitted at r1, rewritten to 9 by mid.r1, and 9 is "
            "admitted at r2 -- must reach probe.p")

    def test_downstream_admission_rejects_stale_upstream_vlan(self):
        ir = self._chain_ir(r2_admitted=["3"])
        self.assertFalse(
            self._reachable(ir),
            "r2 admits {3}, not 9 -- mid.r1's rewritten value (9) must "
            "be what r2 checks, not source.gen's original vlan (5), and "
            "9 is not in r2's admitted set, so this must be blocked")

    def test_plain_mode_ignores_faithful_vlan_fields_entirely(self):
        """ faithful_vlan=False (the default -- every existing benchmark)
        must ignore in_vlans/gen_vlan/mid_rw completely, even if present
        in the IR -- no fieldmatch/rewrite emitted, unconditional plain
        reachability, byte-for-byte the same as before this feature
        existed. Deliberately sets a vlan that would be BLOCKED in
        faithful mode (test_non_admitted_vlan_is_blocked) to prove it is
        the faithful_vlan FLAG, not mere absence of in_vlans/gen_vlan,
        that gates the mechanism. """
        ir = self._ir(admitted=["5", "7"], gen_vlan="6", faithful_vlan=False)
        self.assertTrue(
            self._reachable(ir),
            "faithful_vlan=False must ignore in_vlans/gen_vlan entirely "
            "-- plain reachability, unconditionally admitted")


if __name__ == "__main__":
    unittest.main()


class FaithfulVlanOutRewriteWiringTest(unittest.TestCase):
    """ AD6_PLAN.md §5.5 C4: favemodel.py's consumption of `ir["out_rw"]` --
    the wl_i2-shaped OUT-stage egress-VLAN rewrite -- through a REAL
    build_config/instantiate_base Kripke/CNF build and solve.

    The wl_stanford counterpart above (FaithfulVlanWiringTest) puts the
    rewrite on a `mid.X` stage and gates the next router's admission on it.
    wl_i2 has no `mid` stage at all: its `out.X` devices ARE the dst FIB and
    each of their 77,451 real rules carries `rw=vlan:M` alongside its single
    `fd=`, so the rewrite has to ride on an `out.X` forwarding rule instead
    (and, unlike wl_stanford's, that stage is NOT collapsed by
    Ad6Adapter._build_ir, precisely because no `mid` device exists).

    What makes this more than a renamed copy of the mid test: i2's rewrite is
    keyed PER DESTINATION PREFIX, so which VLAN arrives at the next router
    depends on which dst the existential query picks. That joint (dst, VLAN)
    constraint is the thing C4 exists to model and the thing plain mode drops
    -- so the fixture below gives `out.r1` two routes with DIFFERENT rewrites
    and varies only what `in.r2` admits.

    Fixture: source.gen -> in.r1 (admits {5}) -> out.r1 (two dst routes,
    rewriting to 9 and 3 respectively) -> in.r2 (admits `r2_admitted`) ->
    out.r2 -> probe.p. The source injects VLAN-UNCONSTRAINED (no `gen_vlan`),
    which is i2's own real shape -- `sources.json` declares only
    `ipv4_dst=0.0.0.0/0` -- unlike wl_stanford's VLAN-tagged generators.

    Ad6Adapter's own capture side (`_capture_out_rewrite`, its `add_rules`
    dispatch and its `_build_ir` scoping) is unit-tested fave-side against
    fake Rule objects: fave/test/test_ad6_wl_i2_faithful.py. This starts one
    level downstream, from an already-built IR, same division of labour as
    FaithfulVlanWiringTest. """

    _DST_A = '10.0.0.0/24'
    _DST_B = '10.0.1.0/24'

    @classmethod
    def _ir(cls, r2_admitted, rewrites=None, faithful_vlan=True):
        return {
            "devices": ["in.r1", "out.r1", "in.r2", "out.r2"],
            "edges": [
                ["source.gen.1", "in.r1.1"],
                ["in.r1.5", "out.r1.1"],
                ["out.r1.2", "in.r2.9"],
                ["in.r2.5", "out.r2.1"],
                ["out.r2.2", "probe.p.1"],
            ],
            "generators": {"source.gen": "source.gen.1"},
            "probes": {"probe.p": "probe.p.1"},
            "fwd_rules": [
                {"device": "in.r1", "dst": None, "ports": ["in.r1.5"], "prio": 65535},
                {"device": "out.r1", "dst": cls._DST_A, "ports": ["out.r1.2"],
                 "prio": _lpm_prio(cls._DST_A)},
                {"device": "out.r1", "dst": cls._DST_B, "ports": ["out.r1.2"],
                 "prio": _lpm_prio(cls._DST_B)},
                {"device": "in.r2", "dst": None, "ports": ["in.r2.5"], "prio": 65535},
                {"device": "out.r2", "dst": None, "ports": ["out.r2.2"], "prio": 65535},
            ],
            "routing_rules": [],
            "acl_devices": [], "acl_in": {}, "acl_out": {},
            "in_port_vlan": {}, "out_port_vlan": {}, "in_admit": {},
            "ruleset_devices": {}, "device_addr": {},
            "faithful_vlan": faithful_vlan,
            "in_vlans": {"in.r1": ["5"], "in.r2": r2_admitted},
            "mid_rw": {},
            "out_rw": {"out.r1": rewrites if rewrites is not None else [
                [cls._DST_A, "out.r1.2", "9"],
                [cls._DST_B, "out.r1.2", "3"],
            ]},
            "gen_vlan": {},
        }

    @staticmethod
    def _reachable(ir):
        config = favemodel.build_config(ir)
        XMLUtils.deannotate(config)
        kripke, encoding = favemodel.instantiate_base(config, ir)
        source = favemodel.gen_entry_key("source.gen")
        dest = favemodel.query_destination_key("probe.p", ir)
        instance = Instantiator.InstantiateEndToEnd(kripke, encoding, source, dest)
        return bool(PycoSATAdapter().Solve(instance))

    def test_first_routes_rewrite_reaches_when_admitted(self):
        self.assertTrue(
            self._reachable(self._ir(r2_admitted=["9"])),
            "out.r1's %s route rewrites the egress VLAN to 9, which in.r2 "
            "admits -- must reach probe.p" % self._DST_A)

    def test_second_routes_rewrite_reaches_when_admitted(self):
        """ The OTHER dst prefix's rewrite must be live too, not just the
        first entry in the out_rw list -- this is what makes the model
        per-destination rather than per-device. """
        self.assertTrue(
            self._reachable(self._ir(r2_admitted=["3"])),
            "out.r1's %s route rewrites to 3, which in.r2 admits -- must "
            "reach probe.p via that destination instead" % self._DST_B)

    def test_admitting_neither_rewritten_vlan_blocks(self):
        """ The gate must still bite against the REWRITTEN value. Note this
        one also passed before `out_rw` was consumed at all (with the
        rewrite dropped the arriving tag is the source's own 5, which in.r2
        also refuses) -- it is a regression guard for the direction where a
        rewrite leaves the field FREE rather than setting it, which would
        make every pair vacuously reachable. The discriminating case is
        test_downstream_gate_sees_the_rewritten_value_not_the_source_value
        below. """
        self.assertFalse(
            self._reachable(self._ir(r2_admitted=["7"])),
            "in.r2 admits only 7; out.r1 rewrites to 9 or 3 depending on "
            "the destination, so NO destination gets through -- must be "
            "blocked, not vacuously admitted on the source's own free VLAN")

    def test_rewrite_to_vlan_zero_gates_downstream_admission(self):
        """ 41,200 of wl_i2's real out routes rewrite to vlan 0 (the
        access-port untag), so `0` must be a real rewritten value and not
        read as "no rewrite" -- the two fail in opposite directions on a
        workload whose probes accept vlan=0 only. BOTH of the fixture's
        routes rewrite here, so no destination can reach in.r2 carrying the
        source's own tag instead (see
        test_a_route_without_a_rewrite_entry_passes_the_vlan_through). """
        rewrites = [[self._DST_A, "out.r1.2", "0"],
                    [self._DST_B, "out.r1.2", "0"]]
        self.assertTrue(
            self._reachable(self._ir(r2_admitted=["0"], rewrites=rewrites)),
            "out.r1 rewrites to vlan 0 and in.r2 admits 0 -- must reach")
        self.assertFalse(
            self._reachable(self._ir(r2_admitted=["5"], rewrites=rewrites)),
            "out.r1 rewrites to vlan 0, which in.r2 does not admit -- must "
            "be blocked; a `rw=vlan:0` treated as absent would instead let "
            "the source's own free VLAN satisfy in.r2 and wrongly reach")

    def test_a_route_without_a_rewrite_entry_passes_the_vlan_through(self):
        """ The frame-axiom side of Stage A's SSA encoding, pinned because
        diagnosing it is what corrected this class's first vlan-0 fixture: a
        forwarding rule with NO `out_rw` entry must leave the field at
        whatever value arrived, NOT force it to some default. Only
        `self._DST_A` is given a rewrite, so the `self._DST_B` route stays a
        pass-through and carries in.r1's admitted 5 to in.r2 unchanged.
        Every one of wl_i2's real out routes does rewrite, so this is a
        semantics guard rather than a live i2 case -- but it is exactly the
        behaviour that makes a PARTIAL rewrite table safe. """
        rewrites = [[self._DST_A, "out.r1.2", "9"]]
        self.assertTrue(
            self._reachable(self._ir(r2_admitted=["5"], rewrites=rewrites)),
            "the %s route carries no rewrite, so the packet keeps in.r1's "
            "admitted vlan 5, which in.r2 admits -- must reach through "
            "that destination" % self._DST_B)
        self.assertTrue(
            self._reachable(self._ir(r2_admitted=["9"], rewrites=rewrites)),
            "and the %s route's own rewrite to 9 is live at the same time "
            "-- both destinations are independently available" % self._DST_A)

    def test_downstream_gate_sees_the_rewritten_value_not_the_source_value(self):
        """ The sharpest case: in.r2 admits exactly the VLAN the packet
        carried on ARRIVAL at in.r1 (5, the only value in.r1 admits), but
        NOT either value out.r1 rewrites to. If the rewrite is modelled,
        the tag reaching in.r2 is 9 or 3 and this is blocked; if the
        rewrite is dropped -- plain mode, and every recorded ad6 i2 run so
        far -- the stale 5 sails through and the pair looks reachable. This
        is the over-approximation AD6_PLAN.md §5.5's WORKLOAD-PARITY
        FINDING describes, reproduced in miniature. """
        self.assertFalse(
            self._reachable(self._ir(r2_admitted=["5"])),
            "in.r2 admits 5, which is what the packet carried INTO in.r1 "
            "-- but out.r1 rewrites it to 9 or 3, so in.r2 must see the "
            "rewritten value and block, not the stale source value")

    def test_plain_mode_ignores_the_out_rewrite_entirely(self):
        """ faithful_vlan=False must ignore in_vlans/out_rw completely, so
        every plain-mode i2 measurement already recorded
        (`bench/wl_i2/eval/ad6_i2_*.json`) stays reproducible. Uses the
        admitted set that is BLOCKED in faithful mode
        (test_admitting_neither_rewritten_vlan_blocks) to prove it is the
        FLAG doing the gating, not the absence of the fields. """
        self.assertTrue(
            self._reachable(self._ir(r2_admitted=["7"], faithful_vlan=False)),
            "plain mode must emit no fieldmatch and no rewrite at all")


class FaithfulVlanProbeUntagTest(unittest.TestCase):
    """ AD6_PLAN.md §5.5 C4 (part 2): the probe-side VLAN untag.

    wl_i2 declares every probe `existential` on `vlan=0` (its `probes.json`
    carries that in the model's `test_fields`, NOT `filter_fields`), which is
    the access-port untag: a flow only counts as delivered if the last
    `out.X` route rewrote its tag to 0. `Ad6Adapter` dropped that condition
    entirely -- `add_probe` recorded only `node + '.1'`, and
    `query_destination_key` resolves a probe to a topology node with no
    condition of its own.

    ENFORCED AT QUERY TIME, not in the model. A `GenUtils.fieldmatch` needs a
    real rule node to key its node-scoped alias on
    (`XMLUtils.FieldMatchAliasName` embeds the rule key), and a synthetic gate
    node is not an option: a node that exists only as a transition endpoint,
    with no registered `KripkeNode`, makes
    `Instantiator._CreateMutationConstraints` raise `KeyError` on its own
    `Kripke.GetNode` call. So this forces the destination node's own per-node
    SSA bits directly, via `XMLUtils.ConvertFieldToVariables` -- the
    force-side counterpart of the fieldmatch, whose docstring anticipates
    exactly this use, and the same query-time idiom `fave_bridge.py`'s
    `_seed_literals`/`_state_literals` already use for src-IP and state. It
    is also the same shape as `apkeep/adapter.py`'s own `target_vlan=` query
    parameter, which keeps the two backends comparable.

    OPT-IN, DEFAULT OFF (`ir["probe_untag"]`), deliberately -- see
    test_default_is_off and AD6_PLAN.md §5.5's PROBE-UNTAG PARITY FINDING:
    neither comparison backend enforces this condition on i2 today, so
    turning it on unconditionally would make ad6 the STRICTEST of the three
    and break like-for-like parity in the opposite direction. """

    _DST_A = '10.0.0.0/24'      # rewritten to vlan 0 (untagged)
    _DST_B = '10.0.1.0/24'      # rewritten to vlan 7 (still tagged)

    @classmethod
    def _ir(cls, rewrites, untag=True, probe_vlan="0", attachments=1,
            faithful_vlan=True):
        edges = [
            ["source.gen.1", "in.r1.1"],
            ["in.r1.5", "out.r1.1"],
            ["out.r1.2", "probe.p.1"],
        ]
        if attachments > 1:
            edges.append(["out.r1.3", "probe.p.1"])
        ir = {
            "devices": ["in.r1", "out.r1"],
            "edges": edges,
            "generators": {"source.gen": "source.gen.1"},
            "probes": {"probe.p": "probe.p.1"},
            "fwd_rules": [
                {"device": "in.r1", "dst": None, "ports": ["in.r1.5"], "prio": 65535},
                {"device": "out.r1", "dst": cls._DST_A, "ports": ["out.r1.2"],
                 "prio": _lpm_prio(cls._DST_A)},
                {"device": "out.r1", "dst": cls._DST_B, "ports": ["out.r1.3"],
                 "prio": _lpm_prio(cls._DST_B)},
            ],
            "routing_rules": [],
            "acl_devices": [], "acl_in": {}, "acl_out": {},
            "in_port_vlan": {}, "out_port_vlan": {}, "in_admit": {},
            "ruleset_devices": {}, "device_addr": {},
            "faithful_vlan": faithful_vlan,
            "in_vlans": {"in.r1": ["5"]},
            "mid_rw": {}, "out_rw": {"out.r1": rewrites},
            "gen_vlan": {},
        }
        if probe_vlan is not None:
            ir["probe_vlan"] = {"probe.p": probe_vlan}
        if untag:
            ir["probe_untag"] = True
        return ir

    # both routes present; only DST_A (via out.r1.2) untags
    @classmethod
    def _both(cls):
        return [[cls._DST_A, "out.r1.2", "0"], [cls._DST_B, "out.r1.3", "7"]]

    # only the still-tagged route reaches the probe's single attachment
    @classmethod
    def _tagged_only(cls):
        return [[cls._DST_A, "out.r1.2", "7"], [cls._DST_B, "out.r1.3", "7"]]

    @staticmethod
    def _build(ir):
        config = favemodel.build_config(ir)
        XMLUtils.deannotate(config)
        return favemodel.instantiate_base(config, ir)

    @classmethod
    def _reachable(cls, ir):
        kripke, encoding = cls._build(ir)
        source = favemodel.gen_entry_key("source.gen")
        dest = favemodel.query_destination_key("probe.p", ir)
        instance = Instantiator.InstantiateEndToEnd(kripke, encoding, source, dest)
        instance[0].extend(favemodel.probe_vlan_literals("probe.p", ir, dest))
        return bool(PycoSATAdapter().Solve(instance))

    # --- the literals themselves -------------------------------------------

    def test_default_is_off(self):
        """ Absent `ir["probe_untag"]`, no literal is produced even though
        `ir["probe_vlan"]` records the condition -- the IR always carries
        what the model SAYS, and a separate flag decides whether it is
        ENFORCED. """
        ir = self._ir(self._both(), untag=False)
        self.assertEqual(ir.get("probe_untag"), None)
        self.assertEqual(favemodel.probe_vlan_literals("probe.p", ir), [])

    def test_plain_mode_produces_no_literals(self):
        """ The SSA machinery only exists in faithful mode, so forcing a
        per-node field copy there would name variables the encoding has
        never heard of. """
        ir = self._ir(self._both(), faithful_vlan=False)
        self.assertEqual(favemodel.probe_vlan_literals("probe.p", ir), [])

    def test_no_recorded_probe_vlan_produces_no_literals(self):
        ir = self._ir(self._both(), probe_vlan=None)
        self.assertEqual(favemodel.probe_vlan_literals("probe.p", ir), [])

    def test_literals_are_flat_per_bit_variables_of_the_declared_width(self):
        """ One flat `<variable>` per bit, at `MUTABLE_FIELDS`' own width --
        appending a nested conjunction to an already-CNF'd instance is a
        silent no-op, the lesson `_state_literals` records. """
        ir = self._ir(self._both())
        lits = favemodel.probe_vlan_literals("probe.p", ir, "somenode")
        self.assertEqual(len(lits), favemodel.MUTABLE_FIELDS['vlan'])
        self.assertEqual({l.tag for l in lits}, {XMLUtils.VARIABLE})
        # vlan 0 -> every bit forced false
        self.assertEqual(
            {l.attrib.get(XMLUtils.ATTRNEGATED) for l in lits}, {'true'})
        self.assertTrue(all(
            l.attrib[XMLUtils.ATTRNAME].startswith('vlan#somenode_')
            for l in lits))

    def test_the_forced_variables_exist_in_the_base_encoding(self):
        """ THE non-vacuity guard, and the reason this class exists rather
        than trusting the solve alone: `IncrementalSession._index_for`
        silently INVENTS a fresh unconstrained index for a name it has
        never seen, so forcing a misnamed variable is satisfiable either
        way and would look like a pass. Assert the destination node's own
        SSA bit names really are in the base CNF's variable set. """
        ir = self._ir(self._both())
        _kripke, encoding = self._build(ir)
        dest = favemodel.query_destination_key("probe.p", ir)
        variables, _clauses = AbstractSolver()._ConvertToDIMACS(deepcopy(encoding))
        known = set(variables)
        for lit in favemodel.probe_vlan_literals("probe.p", ir, dest):
            self.assertIn(
                lit.attrib[XMLUtils.ATTRNAME], known,
                "the untag would be VACUOUS: %r is not a variable of the "
                "base encoding, so forcing it constrains nothing" %
                lit.attrib[XMLUtils.ATTRNAME])

    # --- the semantics, through a real build and solve ---------------------

    def test_untagged_route_still_reaches(self):
        self.assertTrue(
            self._reachable(self._ir(self._both())),
            "out.r1's %s route rewrites to vlan 0, so a flow arrives "
            "untagged and the probe must still accept it" % self._DST_A)

    def test_only_tagged_routes_are_blocked_by_the_untag(self):
        """ The discriminating case: every route reaching the probe leaves
        the tag non-zero, so an untag-enforcing probe observes nothing --
        while without the untag this is plainly reachable
        (test_same_model_reaches_when_the_untag_is_off). """
        self.assertFalse(
            self._reachable(self._ir(self._tagged_only())),
            "every route to the probe rewrites to vlan 7, so no flow "
            "arrives untagged -- must be blocked")

    def test_same_model_reaches_when_the_untag_is_off(self):
        """ The A/B partner of the test above, on the identical model: the
        block must come from the untag and nothing else. """
        self.assertTrue(
            self._reachable(self._ir(self._tagged_only(), untag=False)),
            "with the untag off, the tagged route delivers -- proving the "
            "previous test's UNSAT is the untag's doing, not a broken "
            "fixture")

    def test_a_non_zero_untag_value_is_honoured(self):
        """ Nothing here is hardcoded to 0: a probe declaring vlan=7 must
        accept exactly the route the vlan=0 probe rejects. """
        ir = self._ir(self._tagged_only(), probe_vlan="7")
        self.assertTrue(
            self._reachable(ir),
            "the probe declares vlan=7 and the arriving tag is 7 -- must "
            "reach, which also proves the value is read from the IR "
            "rather than assumed")

    def test_multi_attachment_probe_is_gated_at_the_aggregate_node(self):
        """ wl_i2's OWN shape, and the case a single-attachment fixture
        would miss entirely: every real i2 probe has 18-36 topology
        attachments, so `query_destination_key` resolves it to
        `wire_probe_fanout`'s aggregate node rather than to an interface.
        That node has no registered `KripkeNode` -- it exists only as a
        transition TARGET -- so its per-node SSA copy is written purely by
        the frame axioms of its incoming edges. Untagging there must still
        bite: here the second attachment (out.r1.3) carries the tagged
        route, so with both attachments live only the untagged one may
        deliver. """
        both = self._ir(self._both(), attachments=2)
        self.assertTrue(
            self._reachable(both),
            "the out.r1.2 attachment untags, so the aggregate sees an "
            "untagged arrival -- must reach")
        tagged = self._ir(self._tagged_only(), attachments=2)
        self.assertFalse(
            self._reachable(tagged),
            "BOTH attachments now deliver tag 7 -- the untag must be "
            "enforced on the aggregate node, not silently vacuous there")

    def test_untag_holds_through_the_production_incremental_session(self):
        """ The bridge answers every real query through
        `IncrementalSession`, not `PycoSATAdapter`, and that path is where
        a misnamed variable fails SILENTLY (`_index_for` invents one). So
        run the same discriminating A/B through it. """
        for rewrites, untag, expected, why in (
                (self._both(), True, True, "an untagged route exists"),
                (self._tagged_only(), True, False, "every route stays tagged"),
                (self._tagged_only(), False, True, "untag off -> delivers")):
            ir = self._ir(rewrites, untag=untag)
            kripke, encoding = self._build(ir)
            session = IncrementalSession(kripke, encoding)
            try:
                dest = favemodel.query_destination_key("probe.p", ir)
                got = session.Query(
                    favemodel.gen_entry_key("source.gen"), dest,
                    extra_vars=favemodel.probe_vlan_literals("probe.p", ir, dest))
            finally:
                session.Close()
            self.assertEqual(got, expected, why)
