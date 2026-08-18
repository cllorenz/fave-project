package org.ants.jndd.diagram;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Random;

import jdd.bdd.BDD;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

/**
 * Differential-vs-BDD trust tests for the NDD library on FaVe's OWN header
 * profile: two 128-bit IPv6 address fields (src, dst) plus small transport
 * fields. This is APKEEP_NDD_PLAN.md 2.1 -- the paper's own tests use the IPv4
 * 5-tuple; ours stresses the 128-bit fields where "createVar(len) at 128 bits is
 * exactly where research code breaks", the case the FaVe/APKeep fork depends on.
 *
 * ORACLE. Every NDD boolean op is checked to commute with the toBDD homomorphism:
 *   toBDD(op_NDD(P, Q)) == op_BDD(toBDD(P), toBDD(Q))
 * i.e. the NDD computes the same boolean function as the reference BDD. JDD BDDs
 * are canonical (reduced+ordered), so equal node ids <=> equal packet sets --
 * an EXACT set-equality test that (unlike satCount over a 2^280 space, where a
 * double loses precision) never rounds. NDD's toBDD uses the same JDD engine
 * returned by getBDDEngine(), so the two live in one variable space.
 */
class NDDIPv6DifferentialTest {

    // FaVe's wl_up-like profile: IPv6 src(128) + dst(128) + proto(8) + dport(16).
    private static final int SRC = 0, DST = 1, PROTO = 2, DPORT = 3;
    private static final int[] FIELD_BITS = {128, 128, 8, 16};

    private BDD bdd;

    @BeforeEach
    void initProfile() {
        // Generous tables so JDD/NDD never auto-GC mid-test (node ids stay stable
        // for == comparison).
        NDD.initNDD(1_000_000, 4_000_000, 1_000_000);
        for (int bits : FIELD_BITS) {
            NDD.declareField(bits);
        }
        NDD.generateFields();
        bdd = NDD.getBDDEngine();
    }

    // ---- helpers ------------------------------------------------------------

    /** NDD predicate: field's top `len` bits fixed to `bits[0..len-1]`, rest free. */
    private int nddPrefix(int field, int[] bits, int len) {
        int r = NDD.getTrue();
        for (int i = 0; i < len; i++) {
            int lit = bits[i] == 1 ? NDD.getVar(field, i) : NDD.getNotVar(field, i);
            r = NDD.and(r, lit);
        }
        return r;
    }

    private int[] randBits(Random rnd, int n) {
        int[] b = new int[n];
        for (int i = 0; i < n; i++) b[i] = rnd.nextInt(2);
        return b;
    }

    /** A random single-field prefix constraint (length biased to realistic IPv6). */
    private int randFieldPred(Random rnd, int field) {
        int bits = FIELD_BITS[field];
        int len;
        if (field == SRC || field == DST) {
            int[] choices = {0, 32, 48, 64, 128};
            len = choices[rnd.nextInt(choices.length)];
        } else {
            len = rnd.nextInt(bits + 1);
        }
        return nddPrefix(field, randBits(rnd, len), len);
    }

    /** A random multi-field predicate (conjunction over a random subset of fields). */
    private int randPredicate(Random rnd) {
        int r = NDD.getTrue();
        for (int f = 0; f < FIELD_BITS.length; f++) {
            if (rnd.nextInt(3) == 0) continue;            // sometimes leave a field free
            r = NDD.and(r, randFieldPred(rnd, f));
        }
        return r;
    }

    /** toBDD, immediately ref'd (toBDD returns an un-protected node). */
    private int toBddRef(int ndd) {
        return bdd.ref(NDD.toBDD(ndd));
    }

    // ---- tests --------------------------------------------------------------

    @Test
    void declaresTwo128BitFieldsAndAddressesEveryBit() {
        // The load-bearing smoke test: a 128-bit field must expose vars 0..127
        // and a full-width literal must be exact. (The plan's "128 bits is where
        // research code breaks" risk.)
        for (int field : new int[]{SRC, DST}) {
            int hostRoute = nddPrefix(field, randBits(new Random(field), 128), 128);
            // one field fully fixed (128 bits), the other 3 free: 128+8+16 = 152 free bits
            assertEquals(Math.pow(2, 128 + 8 + 16), NDD.satCount(hostRoute), 0.0,
                    "128-bit host route in field " + field);
            // top-bit and bottom-bit literals are distinct, non-trivial functions
            assertNotEquals(NDD.getVar(field, 0), NDD.getVar(field, 127));
            assertNotEquals(NDD.getTrue(), NDD.getVar(field, 127));
            assertNotEquals(NDD.getFalse(), NDD.getVar(field, 127));
        }
    }

    @Test
    void ipv6PrefixContainmentAndDisjointness() {
        // /48 contains its /64 extension; two different /64s under it are disjoint.
        int[] p48 = randBits(new Random(1), 64);
        int pre48 = NDD.ref(nddPrefix(SRC, p48, 48));

        int[] a = p48.clone(); // /64 = /48 + 16 more bits
        int[] b = p48.clone();
        a[48] = 0; b[48] = 1;                    // differ at bit 48 -> disjoint /64s
        int ndA = NDD.ref(nddPrefix(SRC, a, 64));
        int ndB = NDD.ref(nddPrefix(SRC, b, 64));

        // containment: /64 AND /48 == /64
        assertEquals(ndA, NDD.and(ndA, pre48), "the /48 contains the /64");
        // disjointness: the two /64s meet nowhere
        assertEquals(NDD.getFalse(), NDD.and(ndA, ndB), "sibling /64s are disjoint");
        // union of the two /64s is strictly inside the /48
        int union = NDD.ref(NDD.or(ndA, ndB));
        assertEquals(union, NDD.and(union, pre48));
        assertNotEquals(pre48, union);
        NDD.deref(pre48); NDD.deref(ndA); NDD.deref(ndB); NDD.deref(union);
    }

    @Test
    void booleanOpsCommuteWithToBDD() {
        Random rnd = new Random(0xB1A5E5);
        for (int iter = 0; iter < 400; iter++) {
            int p = NDD.ref(randPredicate(rnd));
            int q = NDD.ref(randPredicate(rnd));
            int bp = toBddRef(p);
            int bq = toBddRef(q);

            // AND
            assertEquals(bdd.and(bp, bq), NDD.toBDD(NDD.and(p, q)), "AND @" + iter);
            // OR
            assertEquals(bdd.or(bp, bq), NDD.toBDD(NDD.or(p, q)), "OR @" + iter);
            // NOT
            assertEquals(bdd.not(bp), NDD.toBDD(NDD.not(p)), "NOT @" + iter);
            // DIFF (a \ b == a & !b)
            assertEquals(bdd.and(bp, bdd.not(bq)), NDD.toBDD(NDD.diff(p, q)), "DIFF @" + iter);
            // XOR via apply
            assertEquals(bdd.xor(bp, bq),
                    NDD.toBDD(NDD.apply(NDD.BinaryOperation.XOR, p, q)), "XOR @" + iter);

            bdd.deref(bp); bdd.deref(bq); NDD.deref(p); NDD.deref(q);
        }
    }

    @Test
    void existentialQuantificationHasProjectionSemantics() {
        // exist is checked with LAYOUT-INDEPENDENT algebraic identities rather than
        // a monolithic-BDD reference: NDD fields share a BDD variable template
        // (sharedVars sized to the widest field), so a getBDDVars-built cube is NOT
        // in the toBDD variable space. These identities pin projection semantics
        // using only the (already differentially-trusted) boolean ops.
        Random rnd = new Random(0xE5157);
        for (int iter = 0; iter < 200; iter++) {
            int p = NDD.ref(randPredicate(rnd));
            for (int f = 0; f < FIELD_BITS.length; f++) {
                int ex = NDD.ref(NDD.exist(p, f));
                // weakening: p implies ex  (p subset of ex)
                assertEquals(p, NDD.and(p, ex), "exist weakening (and) f" + f + " @" + iter);
                assertEquals(ex, NDD.or(p, ex), "exist weakening (or) f" + f + " @" + iter);
                // idempotence
                assertEquals(ex, NDD.exist(ex, f), "exist idempotent f" + f + " @" + iter);
                NDD.deref(ex);
            }
            // quantifying every field collapses a satisfiable predicate to TRUE
            assertNotEquals(NDD.getFalse(), p);      // randPredicate is always sat
            assertEquals(NDD.getTrue(), NDD.exist(p, 0, 1, 2, 3),
                    "quantify all fields -> TRUE @" + iter);
            NDD.deref(p);
        }
    }

    @Test
    void existOnAnUnmentionedFieldIsIdentity() {
        // If p constrains only fields {DST, PROTO}, projecting SRC leaves p unchanged.
        Random rnd = new Random(99);
        for (int iter = 0; iter < 100; iter++) {
            int p = NDD.ref(NDD.and(randFieldPred(rnd, DST), randFieldPred(rnd, PROTO)));
            assertEquals(p, NDD.exist(p, SRC), "exist of unmentioned field is identity @" + iter);
            NDD.deref(p);
        }
    }

    @Test
    void nddIsCanonicalAcrossConstructionOrder() {
        // RONDD canonicity: the same set built two different ways is the SAME node id.
        Random rnd = new Random(42);
        for (int iter = 0; iter < 200; iter++) {
            int src = NDD.ref(randFieldPred(rnd, SRC));
            int dst = NDD.ref(randFieldPred(rnd, DST));
            int proto = NDD.ref(randFieldPred(rnd, PROTO));
            int order1 = NDD.and(NDD.and(src, dst), proto);
            int order2 = NDD.and(src, NDD.and(proto, dst));
            assertEquals(order1, order2, "canonical regardless of AND order @" + iter);
            // Distributivity must yield the *same node id*, not merely an equivalent
            // set: a & (b|c) == (a&b) | (a&c). Equal ids <=> reduced+ordered canonical
            // form (RONDD), the property the whole atom-count argument rests on.
            int lhs = NDD.and(src, NDD.or(dst, proto));
            int rhs = NDD.or(NDD.and(src, dst), NDD.and(src, proto));
            assertEquals(lhs, rhs, "distributivity is canonical (same node) @" + iter);
            NDD.deref(src); NDD.deref(dst); NDD.deref(proto);
        }
    }

    @Test
    void deMorganAndAbsorptionHoldOnTheProfile() {
        Random rnd = new Random(7);
        for (int iter = 0; iter < 200; iter++) {
            int p = NDD.ref(randPredicate(rnd));
            int q = NDD.ref(randPredicate(rnd));
            // !(p & q) == !p | !q
            assertEquals(NDD.or(NDD.not(p), NDD.not(q)), NDD.not(NDD.and(p, q)),
                    "de Morgan @" + iter);
            // p | (p & q) == p (absorption)
            assertEquals(p, NDD.or(p, NDD.and(p, q)), "absorption @" + iter);
            // p & !p == false ; p | !p == true
            assertEquals(NDD.getFalse(), NDD.and(p, NDD.not(p)));
            assertEquals(NDD.getTrue(), NDD.or(p, NDD.not(p)));
            NDD.deref(p); NDD.deref(q);
        }
    }
}
