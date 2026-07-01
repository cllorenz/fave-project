package apkeep.checker;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.Map;
import java.util.Set;

import org.junit.jupiter.api.Test;

import apkeep.ApkeepTestBase;
import apkeep.core.Network;
import common.PositionTuple;

/**
 * Pins APKeep's VLAN *flood* mechanism (distinct from VLAN-as-match-field, P9a):
 * a ForwardElement route to a `vlanN` port floods to that VLAN's physical ports
 * via `vlan_ports`/`getVlanPorts`, expanded during traversal by
 * ReachabilityChecker.getPhysicalPorts.
 *
 * This is how wl_stanford's L2 spanning-tree flooding (the "multicast") will be
 * modelled compactly (P7), and the traversal branch is otherwise unexercised
 * (i2/wl_ifi used no vlan_ports). No core change -- it validates existing code.
 */
class VlanFloodTest extends ApkeepTestBase {

    private static PositionTuple pt(String dev, String port) {
        return new PositionTuple(dev, port);
    }

    @Test
    void routeToVlanPortFloodsToAllVlanMembers() throws Exception {
        // r's default route -> "vlan1", which floods to physical ports 1 and 2
        // (linked to A and B). C hangs off port 3, which vlan1 does not include.
        Network net = buildNetwork("vlan-flood",
                List.of("src 1 r 9", "r 1 A 1", "r 2 B 1", "r 3 C 1"),
                List.of("r"), null,
                Map.of("r", Map.of("vlan1", Set.of("1", "2"))),
                List.of("+ fwd r 0 0 vlan1 0"));
        ReachabilityChecker rc = new ReachabilityChecker(net);
        assertTrue(rc.isReachable(pt("src", "1"), pt("A", "1")), "flood reaches A (vlan1 member)");
        assertTrue(rc.isReachable(pt("src", "1"), pt("B", "1")), "flood reaches B (vlan1 member)");
        assertFalse(rc.isReachable(pt("src", "1"), pt("C", "1")), "port 3 is not in vlan1");
    }
}
