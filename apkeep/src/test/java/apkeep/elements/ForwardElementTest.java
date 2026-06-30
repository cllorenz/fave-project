package apkeep.elements;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.HashSet;
import java.util.List;
import java.util.Set;

import org.junit.jupiter.api.Test;

import apkeep.ApkeepTestBase;
import apkeep.core.Network;

/**
 * Pins the forwarding semantics the FaVe adapter relies on: destination-IP
 * longest-prefix match expressed through APKeep's higher-priority-wins
 * ForwardElement. The adapter sets a rule's priority to its prefix length
 * precisely so that LPM falls out of the priority order; these tests document
 * and protect that contract (a regression here is the wl_ifi "everything routes
 * to the default port" class of bug).
 */
class ForwardElementTest extends ApkeepTestBase {

    private static final long IP_10_0_0_5 = 0x0A000005L;  // in 10.0.0.0/8
    private static final long IP_11_0_0_5 = 0x0B000005L;  // not in 10.0.0.0/8

    @Test
    void longestPrefixWins_whenPriorityEncodesPrefixLength() throws Exception {
        // default 0.0.0.0/0 -> port 1 (priority 0); 10.0.0.0/8 -> port 2 (priority 8).
        Network net = buildNetwork("fwd-lpm", List.of(), List.of("r"), null,
                List.of("+ fwd r 0 0 1 0",
                        "+ fwd r 167772160 8 2 8"));
        Element r = net.getElement("r");
        Set<Integer> port1 = r.forwardAPs("1", seedTrue());
        Set<Integer> port2 = r.forwardAPs("2", seedTrue());

        HashSet<Integer> in10 = dstPacket(net, IP_10_0_0_5);
        HashSet<Integer> in11 = dstPacket(net, IP_11_0_0_5);

        // 10/8 traffic takes the longer prefix (port 2), not the default (port 1).
        assertTrue(Element.hasOverlap(port2, in10), "10.0.0.5 should egress port 2 (/8)");
        assertFalse(Element.hasOverlap(port1, in10), "10.0.0.5 must not egress the default port 1");
        // everything else takes the default route.
        assertTrue(Element.hasOverlap(port1, in11), "11.0.0.5 should egress the default port 1");
        assertFalse(Element.hasOverlap(port2, in11), "11.0.0.5 must not egress port 2");
    }

    @Test
    void higherPriorityWins_soPriorityMustEncodePrefixLength() throws Exception {
        // Give the default route a HIGHER priority than the specific /8. Because
        // APKeep is higher-priority-wins, the default then SHADOWS the specific
        // route and 10/8 wrongly egresses the default port. This is exactly the
        // failure the adapter avoids by setting priority = prefix length.
        Network net = buildNetwork("fwd-prio", List.of(), List.of("r"), null,
                List.of("+ fwd r 0 0 1 9",          // default, priority 9 (higher)
                        "+ fwd r 167772160 8 2 0")); // specific /8, priority 0 (lower)
        Element r = net.getElement("r");
        HashSet<Integer> in10 = dstPacket(net, IP_10_0_0_5);

        assertTrue(Element.hasOverlap(r.forwardAPs("1", seedTrue()), in10),
                "higher-priority default shadows the /8");
        assertFalse(Element.hasOverlap(r.forwardAPs("2", seedTrue()), in10),
                "specific /8 is shadowed -> priority must encode prefix length");
    }
}
