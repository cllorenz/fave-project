package apkeep.checker;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.Map;
import java.util.Set;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

import apkeep.ApkeepTestBase;
import apkeep.core.Network;
import common.PositionTuple;

/**
 * Direct coverage for the FaVe-fork ReachabilityChecker (the source->probe
 * existential reachability the APKeepAdapter reduces compliance to). Covers:
 * plain forwarding reachability, the source-IP-seeded path through an ACL
 * (denied vs permitted source), the unseeded over-approximation, and loop
 * termination.
 */
class ReachabilityCheckerTest extends ApkeepTestBase {

    private static PositionTuple pt(String dev, String port) {
        return new PositionTuple(dev, port);
    }

    @Test
    void forwardingReachableAndUnreachable() throws Exception {
        // src injects at r:2; r forwards 10/8 -> r:1 -> B. C hangs off r:3, to
        // which r never forwards.
        Network net = buildNetwork("rc-fwd",
                List.of("src 1 r 2", "r 1 B 1", "r 3 C 1"),
                List.of("r"), null,
                List.of("+ fwd r 167772160 8 1 8"));
        ReachabilityChecker rc = new ReachabilityChecker(net);
        assertTrue(rc.isReachable(pt("src", "1"), pt("B", "1")), "10/8 reaches B");
        assertFalse(rc.isReachable(pt("src", "1"), pt("C", "1")), "nothing is forwarded to C");
    }

    @Test
    void sourceIpSeedMakesAclSourceFiltersBite() throws Exception {
        // A -> [inACL on r:2] -> r forwards 10/8 -> r:1 -> B. The ACL denies
        // source 192.168/16 and permits the rest.
        Network net = buildNetwork("rc-acl",
                List.of("A 1 r_inACL_p2_in inport",
                        "r_inACL_p2_in permit r 2",
                        "r 1 B 1"),
                List.of("r"), Map.of("r", Set.of("inACL")),
                List.of("+ fwd r 167772160 8 1 8",
                        "+ acl r_inACL acl 0 deny 0 255 192.168.0.0 0.0.255.255 null null "
                                + "0.0.0.0 255.255.255.255 null null 200",
                        "+ acl r_inACL acl 0 permit 0 255 0.0.0.0 255.255.255.255 null null "
                                + "0.0.0.0 255.255.255.255 null null 100"));
        ReachabilityChecker rc = new ReachabilityChecker(net);
        // seeded with the actual source IP, the ACL filter applies:
        assertFalse(rc.isReachable(pt("A", "1"), pt("B", "1"), 0xC0A80100L, 24),
                "denied source 192.168.1.0/24 cannot reach B");
        assertTrue(rc.isReachable(pt("A", "1"), pt("B", "1"), 0x01020300L, 24),
                "permitted source 1.2.3.0/24 reaches B");
        // unseeded (full space) over-approximates: some permitted packet always exists.
        assertTrue(rc.isReachable(pt("A", "1"), pt("B", "1")),
                "without a source seed the query over-approximates");
    }

    @Test
    @Timeout(30)
    void terminatesOnAForwardingLoop() throws Exception {
        // r forwards everything to r:2, which links back to r:1 -- a self-loop.
        // The query must terminate (simple-path pruning) and report the
        // unreachable target as unreachable, not hang.
        Network net = buildNetwork("rc-loop",
                List.of("src 1 r 1", "r 2 r 1"),
                List.of("r"), null,
                List.of("+ fwd r 0 0 2 0"));
        ReachabilityChecker rc = new ReachabilityChecker(net);
        assertFalse(rc.isReachable(pt("src", "1"), pt("probe", "1")),
                "the loop never reaches probe; the traversal terminates");
    }
}
