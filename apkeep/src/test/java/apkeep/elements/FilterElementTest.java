package apkeep.elements;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.HashSet;
import java.util.List;
import java.util.Set;

import org.junit.jupiter.api.Test;

import apkeep.ApkeepTestBase;
import apkeep.core.Network;
import common.ACLRule;

/**
 * Pins the FilterElement semantics the FaVe adapter relies on for packet-filter
 * forward_filter tables (APKEEP_TUM_UP_PLAN.md Phase 2): a multi-field, first-
 * match element that FORWARDS accepted traffic out a named out_port (not just
 * permit/deny) and drops the rest to a "__drop__" sink -- combining ACLElement's
 * 5-tuple/first-match match with ForwardElement's per-port hit-predicate
 * placement.
 */
class FilterElementTest extends ApkeepTestBase {

    /** Build a single FilterElement "fw" with the given rules (no topology needed). */
    private Network filterNetwork(String name, List<String> rules) throws Exception {
        return buildNetworkWithFilters(name, List.of(), List.of(), null, Set.of("fw"), rules);
    }

    /** A one-packet BDD for (protocol, dstPort), any src/dst IP, any srcPort. */
    private static HashSet<Integer> packet(Network net, String proto, String dport) {
        ACLRule r = new ACLRule("p 0 x " + proto + " 0.0.0.0 255.255.255.255 null null "
                + "0.0.0.0 255.255.255.255 " + dport + " 0");
        HashSet<Integer> s = new HashSet<>();
        s.add(net.bdd_engine.ConvertACLRule(r));
        return s;
    }

    @Test
    void firstMatchForwardsToOutPortElseDrops() throws Exception {
        // ACCEPT TCP(6) dport 80 out port "eth1" at priority 100; everything else
        // falls through to the default __drop__ sink. The action token (ACL
        // permitDeny slot) is the out_port, not permit/deny.
        Network net = filterNetwork("filter-basic", List.of(
                "+ filter fw fwd 0 eth1 6 6 0.0.0.0 255.255.255.255 null null "
                        + "0.0.0.0 255.255.255.255 80 80 100"));
        Element fw = net.getElement("fw");
        Set<Integer> eth1 = fw.forwardAPs("eth1", seedTrue());
        Set<Integer> drop = fw.forwardAPs(FilterElement.DROP_PORT, seedTrue());

        // TCP:80 is forwarded out eth1, not dropped.
        HashSet<Integer> tcp80 = packet(net, "6 6", "80 80");
        assertTrue(Element.hasOverlap(eth1, tcp80), "TCP:80 should forward out eth1");
        assertFalse(Element.hasOverlap(drop, tcp80), "TCP:80 must not be dropped");

        // TCP:22 has no accept rule -> dropped.
        HashSet<Integer> tcp22 = packet(net, "6 6", "22 22");
        assertTrue(Element.hasOverlap(drop, tcp22), "TCP:22 should be dropped");
        assertFalse(Element.hasOverlap(eth1, tcp22), "TCP:22 must not forward out eth1");
    }

    @Test
    void multipleOutPortsFirstMatchWins() throws Exception {
        // Two accept rules to DIFFERENT out_ports + first-match priority: the
        // higher-priority rule (200) claims TCP:80 for ethA even though a broader
        // lower-priority rule (100) would also match it toward ethB.
        Network net = filterNetwork("filter-multiport", List.of(
                "+ filter fw fwd 0 ethA 6 6 0.0.0.0 255.255.255.255 null null "
                        + "0.0.0.0 255.255.255.255 80 80 200",
                "+ filter fw fwd 0 ethB 6 6 0.0.0.0 255.255.255.255 null null "
                        + "0.0.0.0 255.255.255.255 0 65535 100"));
        Element fw = net.getElement("fw");
        Set<Integer> ethA = fw.forwardAPs("ethA", seedTrue());
        Set<Integer> ethB = fw.forwardAPs("ethB", seedTrue());

        HashSet<Integer> tcp80 = packet(net, "6 6", "80 80");
        assertTrue(Element.hasOverlap(ethA, tcp80), "TCP:80 should forward out ethA (higher priority)");
        assertFalse(Element.hasOverlap(ethB, tcp80), "TCP:80 must not also forward out ethB");

        HashSet<Integer> tcp443 = packet(net, "6 6", "443 443");
        assertTrue(Element.hasOverlap(ethB, tcp443), "TCP:443 should forward out ethB (broad rule)");
        assertFalse(Element.hasOverlap(ethA, tcp443), "TCP:443 must not forward out ethA");
    }
}
