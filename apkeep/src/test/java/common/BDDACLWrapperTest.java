package common;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import apkeep.utils.Parameters;

/**
 * Pins the BDD encoders + header variable layout that everything else rests on.
 *
 * The "layout lock" is deliberately behavioural (prefix containment, disjointness,
 * src/dst independence) rather than asserting raw BDD node ids: it survives
 * refactors but still catches the dangerous regression -- a later header-field
 * addition (IPv6/VLAN/state, see TESTING_STRATEGY_JAVA.md) that silently shifts
 * the BDD variables of existing fields.
 */
class BDDACLWrapperTest {

    @BeforeAll
    static void shrinkBddTable() {
        Parameters.BDD_TABLE_SIZE = 100_000;
    }

    @Test
    void headerFieldWidthsAreTheExpectedContract() {
        // IPv4 5-tuple widths; IPv6 dst is present (128 bits) though unused today.
        assertEquals(8, BDDACLWrapper.protocolBits);
        assertEquals(16, BDDACLWrapper.portBits);
        assertEquals(32, BDDACLWrapper.ipBits);
        assertEquals(128, BDDACLWrapper.ip6Bits);
    }

    @Test
    void prefixEncodingSemantics() {
        BDDACLWrapper bdd = new BDDACLWrapper();
        int slash0 = bdd.encodeDstIPPrefix(0L, 0);
        assertEquals(BDDACLWrapper.BDDTrue, slash0, "0.0.0.0/0 is the full space");

        int slash8 = bdd.encodeDstIPPrefix(0x0A000000L, 8);   // 10.0.0.0/8
        int host = bdd.encodeDstIPPrefix(0x0A000005L, 32);    // 10.0.0.5/32
        // the host is contained in the /8: (host AND /8) == host.
        assertEquals(host, bdd.and(host, slash8), "10.0.0.5/32 subset of 10.0.0.0/8");

        int other8 = bdd.encodeDstIPPrefix(0x0B000000L, 8);   // 11.0.0.0/8
        assertEquals(BDDACLWrapper.BDDFalse, bdd.and(slash8, other8), "disjoint /8s do not overlap");
    }

    @Test
    void sourceAndDestinationUseIndependentVariables() {
        BDDACLWrapper bdd = new BDDACLWrapper();
        int dst10 = bdd.encodeDstIPPrefix(0x0A000000L, 8);
        int src10 = bdd.encodeSrcIPPrefix(0x0A000000L, 8);
        assertNotEquals(dst10, src10, "src and dst of the same bits must differ");
        // independent fields: dst=10/8 AND src=10/8 is a non-empty strict subset of each.
        int both = bdd.and(dst10, src10);
        assertNotEquals(BDDACLWrapper.BDDFalse, both, "src and dst are independent (intersection non-empty)");
        assertNotEquals(dst10, both);
        assertNotEquals(src10, both);
    }

    @Test
    void aclRuleEncodesProtocolAndPortTuple() {
        BDDACLWrapper bdd = new BDDACLWrapper();
        int tcp22 = bdd.ConvertACLRule(aclMatch("6 6", "22 22"));
        int tcp80 = bdd.ConvertACLRule(aclMatch("6 6", "80 80"));
        int udp22 = bdd.ConvertACLRule(aclMatch("17 17", "22 22"));
        // different dst port -> disjoint; different protocol -> disjoint.
        assertEquals(BDDACLWrapper.BDDFalse, bdd.and(tcp22, tcp80), "TCP:22 vs TCP:80 disjoint (port)");
        assertEquals(BDDACLWrapper.BDDFalse, bdd.and(tcp22, udp22), "TCP:22 vs UDP:22 disjoint (proto)");
        assertTrue(tcp22 != BDDACLWrapper.BDDFalse && tcp22 != BDDACLWrapper.BDDTrue,
                "a 5-tuple match is a proper, non-trivial predicate");
    }

    @Test
    void vlanEncodesAsAnIndependentField() {
        // P9a: VLAN is a new header match field (the reduced multi-field case).
        BDDACLWrapper bdd = new BDDACLWrapper();
        int v10 = bdd.ConvertACLRule(vlanOnly(10));
        int v20 = bdd.ConvertACLRule(vlanOnly(20));
        assertNotEquals(v10, v20, "different VLAN tags differ");
        assertEquals(BDDACLWrapper.BDDFalse, bdd.and(v10, v20), "different VLANs are disjoint");
        // independent of the IP fields: vlan=10 AND dst=10/8 is a non-empty strict
        // subset of each (and, with the P6 layout-lock still passing, adding VLAN
        // did not shift the existing fields).
        int dst = bdd.encodeDstIPPrefix(0x0A000000L, 8);
        int both = bdd.and(v10, dst);
        assertNotEquals(BDDACLWrapper.BDDFalse, both, "VLAN is independent of dst-IP");
        assertNotEquals(v10, both);
        assertNotEquals(dst, both);
    }

    @Test
    void vlanRewriteReplacesTheTagAndPreservesOtherFields() {
        // P7b: the Stanford mid-stage rewrites the egress VLAN (nat over the VLAN
        // field), keyed by the dst-IP route. Pin that primitive: nat(pkt, vlanField,
        // vlan=N) must set VLAN to N, drop the old tag, and leave dst-IP untouched.
        BDDACLWrapper bdd = new BDDACLWrapper();
        int vlanField = bdd.get_field_bdd(Fields.vlan);
        assertNotEquals(BDDACLWrapper.BDDFalse, vlanField, "VLAN field BDD must be non-trivial");

        int v10 = bdd.ConvertVLAN(10);
        int v20 = bdd.ConvertVLAN(20);
        int dst = bdd.encodeDstIPPrefix(0x0A000000L, 8);   // 10.0.0.0/8
        int pkt = bdd.and(v10, dst);                        // vlan=10 AND dst=10/8

        int rewritten = bdd.nat(pkt, vlanField, v20);       // vlan 10 -> 20

        assertEquals(rewritten, bdd.and(rewritten, v20), "result is entirely within vlan=20");
        assertEquals(BDDACLWrapper.BDDFalse, bdd.and(rewritten, v10), "no vlan=10 remains");
        assertEquals(rewritten, bdd.and(rewritten, dst), "dst-IP is preserved across the rewrite");
        assertNotEquals(BDDACLWrapper.BDDFalse, rewritten, "the rewritten packet set is non-empty");
    }

    /** A 5-tuple match (protocol range, dst-port range; any IP, any src port). */
    private static ACLRule aclMatch(String proto, String dport) {
        return new ACLRule("p 0 x " + proto + " 0.0.0.0 255.255.255.255 null null "
                + "0.0.0.0 255.255.255.255 " + dport + " 0");
    }

    /** Any 5-tuple, VLAN as the optional trailing token. */
    private static ACLRule vlanOnly(int vlan) {
        return new ACLRule("p 0 x 0 255 0.0.0.0 255.255.255.255 null null "
                + "0.0.0.0 255.255.255.255 null null 0 " + vlan);
    }

    // ---- IPv6 (FaVe fork P9b) ------------------------------------------------

    /** A rule matching an IPv6 src prefix and an IPv6 dst prefix ("addr/len" in
     *  the src/dst slots, wildcard token "null"); "any" leaves that side free. */
    private static ACLRule ip6(String src, String dst) {
        return new ACLRule("p 0 x 0 255 " + src + " null null null " + dst
                + " null null null 0");
    }

    @Test
    void ipv6PrefixContainmentAndDisjointness() {
        BDDACLWrapper bdd = new BDDACLWrapper();
        int slash0 = bdd.encodeIP6Prefix("any", null);   // full space
        assertEquals(BDDACLWrapper.BDDTrue, slash0, "any is the full space");

        // via ConvertACLRule (the real path): a /64 is contained in its covering /48.
        int p48 = bdd.ConvertACLRule(ip6("2001:db8:abc::/48", "any"));
        int p64 = bdd.ConvertACLRule(ip6("2001:db8:abc:1::/64", "any"));
        assertEquals(p64, bdd.and(p64, p48), "2001:db8:abc:1::/64 subset of 2001:db8:abc::/48");

        int other48 = bdd.ConvertACLRule(ip6("2001:db8:dead::/48", "any"));
        assertEquals(BDDACLWrapper.BDDFalse, bdd.and(p48, other48),
                "disjoint /48s do not overlap");
        // a full /128 host address is a strict, non-empty subset of its /64.
        int host = bdd.ConvertACLRule(ip6("2001:db8:abc:1::5/128", "any"));
        assertEquals(host, bdd.and(host, p64), "host /128 subset of its /64");
        assertNotEquals(BDDACLWrapper.BDDFalse, host, "host match is non-empty");
    }

    @Test
    void ipv6SrcAndDstAreIndependentFields() {
        BDDACLWrapper bdd = new BDDACLWrapper();
        int src = bdd.ConvertACLRule(ip6("2001:db8:aaaa::/48", "any"));
        int dst = bdd.ConvertACLRule(ip6("any", "2001:db8:bbbb::/48"));
        int both = bdd.ConvertACLRule(ip6("2001:db8:aaaa::/48", "2001:db8:bbbb::/48"));
        // src AND dst == the combined rule, and it is a strict non-empty subset of each.
        assertEquals(both, bdd.and(src, dst), "src6 & dst6 compose to the combined rule");
        assertNotEquals(BDDACLWrapper.BDDFalse, both, "combined match is non-empty");
        assertEquals(both, bdd.and(both, src), "combined subset of src6");
        assertEquals(both, bdd.and(both, dst), "combined subset of dst6");
        assertNotEquals(src, both, "dst6 further constrains src6 (independent fields)");
    }
}
