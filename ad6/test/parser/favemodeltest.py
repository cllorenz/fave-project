import unittest

import lxml.etree as et

from src.core.instantiator import Instantiator
from src.parser import favemodel
from src.solver.pycosat import PycoSATAdapter
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
