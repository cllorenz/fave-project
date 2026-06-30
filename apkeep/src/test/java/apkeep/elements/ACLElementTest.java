package apkeep.elements;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.junit.jupiter.api.Test;

import apkeep.ApkeepTestBase;
import apkeep.core.Network;
import common.ACLRule;

/**
 * Pins the ACL semantics the FaVe adapter relies on: a per-port ACLElement that
 * matches the full 5-tuple (protocol + ports, not just src/dst IP -- the
 * transport-layer paths the adapter will need for wl_stanford, currently
 * exercised by NOTHING) and resolves overlapping rules first-match via
 * higher-priority-wins.
 */
class ACLElementTest extends ApkeepTestBase {

    /** Build an ACLElement "fw_acl" with the given rules (no topology needed). */
    private Network aclNetwork(String name, List<String> rules) throws Exception {
        return buildNetwork(name, List.of(), List.of(),
                Map.of("fw", Set.of("acl")), rules);
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
    void fiveTupleMatch_protocolAndPort_firstMatchPriority() throws Exception {
        // deny TCP(6) dport 22 at priority 200; permit everything else at 100.
        // Higher priority wins, so the specific deny takes precedence (cisco
        // first-match -> descending priority).
        Network net = aclNetwork("acl-5tuple", List.of(
                "+ acl fw_acl acl 0 deny 6 6 0.0.0.0 255.255.255.255 null null "
                        + "0.0.0.0 255.255.255.255 22 22 200",
                "+ acl fw_acl acl 0 permit 0 255 0.0.0.0 255.255.255.255 null null "
                        + "0.0.0.0 255.255.255.255 null null 100"));
        Element acl = net.getElement("fw_acl");
        Set<Integer> permit = acl.forwardAPs("permit", seedTrue());
        Set<Integer> deny = acl.forwardAPs("deny", seedTrue());

        // TCP:22 is denied, not permitted.
        HashSet<Integer> tcp22 = packet(net, "6 6", "22 22");
        assertTrue(Element.hasOverlap(deny, tcp22), "TCP:22 should be denied");
        assertFalse(Element.hasOverlap(permit, tcp22), "TCP:22 must not be permitted");

        // TCP:80 is permitted (the destination port distinguishes it).
        HashSet<Integer> tcp80 = packet(net, "6 6", "80 80");
        assertTrue(Element.hasOverlap(permit, tcp80), "TCP:80 should be permitted");
        assertFalse(Element.hasOverlap(deny, tcp80), "TCP:80 must not be denied");

        // UDP:22 is permitted (the protocol distinguishes it from the TCP:22 deny).
        HashSet<Integer> udp22 = packet(net, "17 17", "22 22");
        assertTrue(Element.hasOverlap(permit, udp22), "UDP:22 should be permitted");
        assertFalse(Element.hasOverlap(deny, udp22), "UDP:22 must not be denied");
    }
}
