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


if __name__ == "__main__":
    unittest.main()
