package org.ants.jndd.diagram;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Random;

import jdd.bdd.BDD;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

/**
 * Differential correctness test for the FaVe port of the atomization layer
 * (AtomizedNDD / AtomizedNodeTable) onto the int-node-id NDD core
 * (APKEEP_NDD_PLAN.md 2.1 atomize/update; 2.5 engine dependency).
 *
 * Profile mirrors NDDIPv6DifferentialTest: IPv6 src(128) + dst(128) + proto(8) +
 * dport(16). Atomization computes atomic predicates PER FIELD; this test proves:
 *   (1) each field's atoms PARTITION that field's space (pairwise disjoint, union
 *       == the field-universe BDD),
 *   (2) each input predicate RECOMBINES exactly from its atoms
 *       (atomizedToNDD(atomization(P)) denotes the same set as P), and
 *   (3) the atom count is the per-field sum.
 */
class NDDAtomizationTest {

    private static final int SRC = 0, DST = 1, PROTO = 2, DPORT = 3;
    private static final int[] FIELD_BITS = {128, 128, 8, 16};

    private BDD bdd;

    @BeforeEach
    void initProfile() {
        AtomizedNDD.initAtomizedNDD(1_000_000, 1_000_000, 4_000_000, 1_000_000);
        for (int bits : FIELD_BITS) {
            AtomizedNDD.declareField(bits);
        }
        NDD.generateFields();
        bdd = NDD.getBDDEngine();
    }

    /** int-NDD predicate: field's top `len` bits fixed to bits[], rest free. */
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

    private int randFieldPred(Random rnd, int field) {
        int bits = FIELD_BITS[field];
        int len = (field == SRC || field == DST)
                ? new int[]{0, 32, 48, 64, 128}[rnd.nextInt(5)]
                : rnd.nextInt(bits + 1);
        return nddPrefix(field, randBits(rnd, len), len);
    }

    private int randPredicate(Random rnd) {
        int r = NDD.getTrue();
        for (int f = 0; f < FIELD_BITS.length; f++) {
            if (rnd.nextInt(3) == 0) continue;
            r = NDD.and(r, randFieldPred(rnd, f));
        }
        return r;
    }

    /**
     * FaVe fix (ndd/FAVE_CHANGES.md §12). SRC and DST are both 128 bits, so they
     * share label variables and one prefix is one label id on either field.
     * Atomization mapped labels to atoms in ONE map, so a label on both fields
     * got the atoms of whichever field came last: the SRC molecule below held
     * DST's atoms. The sets still recombine (both fields' atoms tile the same
     * prefix), so only the atom ids show it -- and a later split, which finds
     * a molecule's atoms by field, then misses them.
     */
    @Test
    void aLabelOnTwoFieldsGetsEachFieldsOwnAtoms() {
        int[] x = new int[48];
        x[0] = 1;
        int[] y = x.clone();
        y[47] = 1;
        int pSrc = NDD.ref(nddPrefix(SRC, x, 32));     // X as a source
        int pDst = NDD.ref(nddPrefix(DST, x, 32));     // X as a destination
        int pDst2 = NDD.ref(nddPrefix(DST, y, 48));    // Y inside X, destination only
        HashSet<Integer> preds = new HashSet<>();
        preds.add(pSrc);
        preds.add(pDst);
        preds.add(pDst2);
        HashMap<Integer, HashSet<Integer>[]> perPred = new HashMap<>();
        HashMap<Integer, AtomizedNDD> mol = AtomizedNDD.atomization(preds, perPred);
        assertEquals(2, AtomizedNDD.getAllAtoms(SRC).size(), "X and not-X");
        assertEquals(3, AtomizedNDD.getAllAtoms(DST).size(), "Y, X minus Y, not-X");
        for (int p : preds) {
            HashSet<Integer>[] atoms = perPred.get(p);
            for (int f = 0; f < FIELD_BITS.length; f++) {
                assertTrue(AtomizedNDD.getAllAtoms(f).containsAll(atoms[f]),
                        "a molecule holds atoms of another field on field " + f);
            }
            assertEquals(p, AtomizedNDD.atomizedToNDD(mol.get(p)), "recombines");
        }
    }

    @Test
    void atomsPartitionEachFieldAndPredicatesRecombine() {
        Random rnd = new Random(0xA70A1DL);
        HashSet<Integer> preds = new HashSet<>();
        for (int i = 0; i < 200; i++) {
            preds.add(NDD.ref(randPredicate(rnd)));
        }

        HashMap<Integer, HashSet<Integer>[]> nddToAtoms = new HashMap<>();
        HashMap<Integer, AtomizedNDD> mol = AtomizedNDD.atomization(preds, nddToAtoms);

        // (1) per-field partition
        int total = 0;
        for (int field = 0; field <= NDD.getFieldNum(); field++) {
            ArrayList<Integer> atoms = new ArrayList<>(AtomizedNDD.getAllAtoms(field));
            total += atoms.size();
            int union = bdd.getZero();
            bdd.ref(union);
            for (int i = 0; i < atoms.size(); i++) {
                assertTrue(atoms.get(i) != bdd.getZero(), "atom is FALSE in field " + field);
                for (int j = i + 1; j < atoms.size(); j++) {
                    assertEquals(bdd.getZero(), bdd.and(atoms.get(i), atoms.get(j)),
                            "atoms overlap in field " + field);
                }
                int nu = bdd.ref(bdd.or(union, atoms.get(i)));
                bdd.deref(union);
                union = nu;
            }
            assertEquals(bdd.getOne(), union, "atoms do not cover field " + field);
            bdd.deref(union);
        }

        // (3) count == per-field sum
        assertEquals(total, AtomizedNDD.totalCountOfAtoms());

        // (2) recombination: atomizedToNDD(atomization(P)) == P (canonical node id)
        for (int p : preds) {
            AtomizedNDD ap = mol.get(p);
            int back = AtomizedNDD.atomizedToNDD(ap);
            assertEquals(p, back, "predicate does not recombine from its atoms");
        }
    }
}
