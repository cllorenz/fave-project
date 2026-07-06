package apkeep.checker;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.File;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.junit.jupiter.api.Test;

import apkeep.ApkeepTestBase;
import apkeep.core.Network;
import apkeep.utils.Evaluator;
import apkeep.utils.Parameters;
import common.PositionTuple;

/**
 * P7b: reachability through a VLAN-rewriting NATElement -- the mechanism the
 * faithful wl_stanford model needs (mid-stage rewrites the egress VLAN keyed by
 * the dst-IP route, and that VLAN gates a downstream ACL).
 *
 * Topology: src -> r (FIB: 10/8 -> p1) -> NAT r_p1 (dst 10/8 => vlan:=20) -> two
 * downstream ACLs, one permitting only vlan 20 (-> B) and one only vlan 30 (-> C).
 * The rewrite makes B reachable and C UNREACHABLE; without it C would be reachable
 * too (wildcard VLAN overlaps vlan 30). C's unreachability is the discriminating
 * assertion that the rewrite actually happened.
 */
class NATReachabilityTest extends ApkeepTestBase {

    private static PositionTuple pt(String dev, String port) {
        return new PositionTuple(dev, port);
    }

    private static Network buildWithNAT(String name, List<String> links, List<String> devices,
            Map<String, Set<String>> acls, Map<String, Set<String>> nats, List<String> rules)
            throws Exception {
        Network net = new Network(name);
        net.initializeNetwork(new ArrayList<>(links), devices, acls, null, nats);
        Evaluator eva = new Evaluator(name, File.createTempFile("apkeep-" + name, ".out").getAbsolutePath());
        net.run(eva, rules);
        return net;
    }

    @Test
    void vlanRewriteGatesDownstreamAcl() throws Exception {
        // permit-only-vlan-N ACL rule (P9a trailing VLAN token).
        String permitVlan = "0 255 0.0.0.0 255.255.255.255 null null "
                + "0.0.0.0 255.255.255.255 null null 100 ";
        Network net = buildWithNAT("nat-vlan",
                List.of("src 1 r 2",
                        // r.1 fans to both ACLs; device_nats inserts the NAT inline
                        // on r.1, so this downstream moves to the NAT's outport.
                        "r 1 d_inACL_p1_in inport", "d_inACL_p1_in permit B 1",
                        "r 1 e_inACL_p1_in inport", "e_inACL_p1_in permit C 1"),
                List.of("r"),
                Map.of("d", Set.of("inACL"), "e", Set.of("inACL")),
                Map.of("r", Set.of("1")),
                List.of("+ fwd r 167772160 8 1 8",              // r: 10/8 -> port 1
                        "+ nat r 1 vlan 10.0.0.0 8 20",         // NAT: dst 10/8 => vlan:=20
                        "+ acl d_inACL acl 0 permit " + permitVlan + "20",   // permit vlan 20
                        "+ acl e_inACL acl 0 permit " + permitVlan + "30")); // permit vlan 30
        ReachabilityChecker rc = new ReachabilityChecker(net);
        assertTrue(rc.isReachable(pt("src", "1"), pt("B", "1")),
                "10/8 rewritten to vlan 20 is permitted by the vlan-20 ACL -> B");
        assertFalse(rc.isReachable(pt("src", "1"), pt("C", "1")),
                "after the rewrite the traffic is vlan 20, so the vlan-30 ACL drops it -> C unreachable");
    }

    @Test
    void multipleVlanRewritesOnOneNat() throws Exception {
        // Two rewrite rules on the SAME NAT (dst 10.0/9 => vlan 20, dst 10.128/9
        // => vlan 30) -- this crashed AP merging (updateMergeAP dereferenced an
        // already-merged AP -> APNotFoundException). AP merging is a size-only
        // optimization, so we disable it when NATs are present; reachability is
        // unchanged. Pin both: no crash, and each route keeps its own rewrite.
        boolean saved = Parameters.MergeAP;
        Parameters.MergeAP = false;
        try {
            String permitVlan = "0 255 0.0.0.0 255.255.255.255 null null "
                    + "0.0.0.0 255.255.255.255 null null 100 ";
            Network net = buildWithNAT("nat-multi",
                    List.of("src 1 r 2",
                            "r 1 d_inACL_p1_in inport", "d_inACL_p1_in permit X 1",
                            "r 1 e_inACL_p1_in inport", "e_inACL_p1_in permit Y 1"),
                    List.of("r"),
                    Map.of("d", Set.of("inACL"), "e", Set.of("inACL")),
                    Map.of("r", Set.of("1")),
                    List.of("+ fwd r 167772160 9 1 9",              // 10.0.0.0/9   -> port 1
                            "+ fwd r 176160768 9 1 9",              // 10.128.0.0/9 -> port 1
                            "+ nat r 1 vlan 10.0.0.0 9 20",         // 10.0/9   => vlan 20
                            "+ nat r 1 vlan 10.128.0.0 9 30",       // 10.128/9 => vlan 30
                            "+ acl d_inACL acl 0 permit " + permitVlan + "20",
                            "+ acl e_inACL acl 0 permit " + permitVlan + "30"));
            ReachabilityChecker rc = new ReachabilityChecker(net);
            assertTrue(rc.isReachable(pt("src", "1"), pt("X", "1")),
                    "10.0/9 -> vlan 20 -> permitted by the vlan-20 ACL -> X");
            assertTrue(rc.isReachable(pt("src", "1"), pt("Y", "1")),
                    "10.128/9 -> vlan 30 -> permitted by the vlan-30 ACL -> Y");
        } finally {
            Parameters.MergeAP = saved;
        }
    }

    @Test
    void ingressAdmissionComposesWithRewriteInOneUniverse() throws Exception {
        // The wl_stanford ordering: an ingress ACL (VLAN admission) UPSTREAM of the
        // mid VLAN rewrite, then a downstream ACL matching the rewritten VLAN. With
        // ACL division this collapses (fwd/acl universes disagree on the rewritten
        // VLAN). Single-universe (USE_DIVISION=false) keeps ACL+NAT in one AP set
        // so they compose: src(any vlan) -> in-ACL(permit vlan 10) -> r(FIB) ->
        // NAT(dst 10/8 => vlan 20) -> {out-ACL vlan 20 -> X, out-ACL vlan 30 -> Y}.
        // Expect X reachable (rewritten to 20) and Y not (it is 20, not 30).
        boolean savedM = Parameters.MergeAP, savedD = Parameters.USE_DIVISION;
        Parameters.MergeAP = false;
        Parameters.USE_DIVISION = false;
        try {
            String any = "0 255 0.0.0.0 255.255.255.255 null null "
                    + "0.0.0.0 255.255.255.255 null null 100 ";
            Network net = buildWithNAT("nat-1uni",
                    List.of("src 1 ia_0_p_in inport", "ia_0_p_in permit r 2",
                            "r 1 od_0_p_in inport", "od_0_p_in permit X 1",
                            "r 1 oe_0_p_in inport", "oe_0_p_in permit Y 1"),
                    List.of("r"),
                    Map.of("ia", Set.of("0"), "od", Set.of("0"), "oe", Set.of("0")),
                    Map.of("r", Set.of("1")),
                    List.of("+ fwd r 167772160 8 1 8",          // 10/8 -> port 1
                            "+ nat r 1 vlan 10.0.0.0 8 20",      // dst 10/8 => vlan 20
                            "+ acl ia_0 acl 0 permit " + any + "10",   // ingress: permit vlan 10
                            "+ acl od_0 acl 0 permit " + any + "20",   // egress X: permit vlan 20
                            "+ acl oe_0 acl 0 permit " + any + "30")); // egress Y: permit vlan 30
            ReachabilityChecker rc = new ReachabilityChecker(net);
            assertTrue(rc.isReachable(pt("src", "1"), pt("X", "1")),
                    "vlan-10 admitted, rewritten to 20, permitted by the vlan-20 ACL -> X");
            assertFalse(rc.isReachable(pt("src", "1"), pt("Y", "1")),
                    "after the rewrite the traffic is vlan 20, so the vlan-30 ACL drops it -> Y");
        } finally {
            Parameters.MergeAP = savedM;
            Parameters.USE_DIVISION = savedD;
        }
    }
}
