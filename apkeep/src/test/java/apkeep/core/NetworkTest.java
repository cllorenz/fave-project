package apkeep.core;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.Map;
import java.util.Set;

import org.junit.jupiter.api.Test;

import apkeep.ApkeepTestBase;
import apkeep.elements.ACLElement;
import apkeep.elements.ForwardElement;
import common.BDDACLWrapper;
import common.PositionTuple;

/**
 * Pins the in-memory network construction the FaVe adapter drives: element
 * creation/typing from links + devices + device_acls, the L1 topology, APKeep's
 * ACL-node naming convention (the `_in`/`_out` splice the adapter emits), and
 * the source-IP seed (Network.getACLSeedAPs) the reachability query uses.
 */
class NetworkTest extends ApkeepTestBase {

    @Test
    void buildsAndTypesElementsFromLinksDevicesAndAcls() throws Exception {
        // link introduces ForwardElement "a"; device adds "r"; device_acls makes
        // ACLElement "r_acl".
        Network net = buildNetwork("net-build",
                List.of("a 1 r 2"), List.of("r"),
                Map.of("r", Set.of("acl")), List.of());
        assertTrue(net.getElement("a") instanceof ForwardElement, "linked node -> ForwardElement");
        assertTrue(net.getElement("r") instanceof ForwardElement, "device -> ForwardElement");
        assertTrue(net.getElement("r_acl") instanceof ACLElement, "device_acl -> ACLElement");
    }

    @Test
    void l1TopologyIsDirected() throws Exception {
        Network net = buildNetwork("net-topo", List.of("a 1 b 2"), List.of(), null, List.of());
        var fwd = net.getConnectedPorts(new PositionTuple("a", "1"));
        assertEquals(1, fwd.size());
        PositionTuple dst = fwd.iterator().next();
        assertEquals("b", dst.getDeviceName());
        assertEquals("2", dst.getPortName());
        // links are one-way: the reverse direction is absent.
        assertEquals(null, net.getConnectedPorts(new PositionTuple("b", "2")));
    }

    @Test
    void aclNodeNamingConvention() throws Exception {
        Network net = buildNetwork("net-acl", List.of(), List.of(),
                Map.of("r", Set.of("acl")), List.of());
        // a topology node ending in _in/_out is an ACL node, resolving to its element.
        assertTrue(net.isACLNode("r_acl_p2_in"), "_in node is an ACL node");
        assertFalse(net.isACLNode("r"), "a plain device is not an ACL node");
        assertSame(net.getElement("r_acl"), net.getACLElement("r_acl_p2_in"),
                "ACL node resolves to its device_acl element");
    }

    @Test
    void aclSeedAPsRestrictsToSourcePrefix() throws Exception {
        // ACL that splits on source IP: deny 192.168/16, permit the rest.
        Network net = buildNetwork("net-seed", List.of(), List.of(),
                Map.of("fw", Set.of("acl")), List.of(
                        "+ acl fw_acl acl 0 deny 0 255 192.168.0.0 0.0.255.255 null null "
                                + "0.0.0.0 255.255.255.255 null null 200",
                        "+ acl fw_acl acl 0 permit 0 255 0.0.0.0 255.255.255.255 null null "
                                + "0.0.0.0 255.255.255.255 null null 100"));
        // no source constraint -> full space.
        Set<Integer> all = net.getACLSeedAPs(0L, 0);
        assertEquals(Set.of(BDDACLWrapper.BDDTrue), all);
        // a denied vs a permitted source select different (non-empty) AP classes.
        Set<Integer> denied = net.getACLSeedAPs(0xC0A80100L, 24);   // 192.168.1.0/24
        Set<Integer> permitted = net.getACLSeedAPs(0x01020300L, 24); // 1.2.3.0/24
        assertFalse(denied.isEmpty());
        assertFalse(permitted.isEmpty());
        assertNotEquals(denied, permitted, "src-IP seed distinguishes denied vs permitted source");
    }
}
