package org.ants.jndd.diagram;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Random;

import org.ants.jndd.cache.OperationCache;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

/**
 * FaVe changes to NDD's operation caches and atom collection
 * (ndd/FAVE_CHANGES.md §14, §15).
 *
 * §14: an operation stored its cache entry at the slot of the last miss of
 * its recursion, so an entry above the leaves was never found again. Right
 * after an operation its own entry must be there.
 * §15: `collectAtoms` visiting each node once gives the atoms the authors'
 * tree walk gives.
 */
class NDDFaveCacheAndAtomsTest {

    private static final int[] FIELD_BITS = {32, 32, 8, 16};

    @BeforeEach
    void initProfile() {
        AtomizedNDD.initAtomizedNDD(1_000_000, 1_000_000, 4_000_000, 1_000_000);
        for (int bits : FIELD_BITS) {
            AtomizedNDD.declareField(bits);
        }
        NDD.generateFields();
    }

    @AfterEach
    void restore() {
        AtomizedNDD.setCollectAtomsVisited(false);
        AtomizedNDD.disableCaches();
    }

    private static int prefix(int field, Random rnd, int len) {
        int r = NDD.getTrue();
        for (int i = 0; i < len; i++) {
            r = NDD.and(r, rnd.nextBoolean() ? NDD.getVar(field, i) : NDD.getNotVar(field, i));
        }
        return r;
    }

    /** A short prefix on every field: an `and` of two recurses through all
     *  fields, and two often overlap. */
    private static List<Integer> predicates(int n, long seed) {
        Random rnd = new Random(seed);
        List<Integer> out = new ArrayList<>();
        for (int i = 0; i < n; i++) {
            int r = NDD.getTrue();
            for (int f = 0; f < FIELD_BITS.length; f++) {
                r = NDD.and(r, prefix(f, rnd, 1 + rnd.nextInt(2)));
            }
            out.add(NDD.ref(r));
        }
        return out;
    }

    private static Object field(Class<?> c, String name) throws Exception {
        Field f = c.getDeclaredField(name);
        f.setAccessible(true);
        return f.get(null);
    }

    @Test
    void anIntCoreAndFindsItsOwnEntryAgain() throws Exception {
        List<Integer> p = predicates(40, 0x5107L);
        Object cache = field(NDD.class, "andCache");
        Method get = cache.getClass().getDeclaredMethod("getEntry", int.class, int.class);
        get.setAccessible(true);
        Field result = cache.getClass().getDeclaredField("result");
        result.setAccessible(true);
        int checked = 0;
        for (int i = 0; i + 1 < p.size(); i++) {
            int a = p.get(i), b = p.get(i + 1);
            if (a == b) continue;
            int r = NDD.and(a, b);
            assertTrue((Boolean) get.invoke(cache, a, b), "the and of pair " + i + " is not cached");
            assertEquals(r, result.getInt(cache));
            checked++;
        }
        assertTrue(checked > 30);
    }

    @Test
    @SuppressWarnings("unchecked")
    void anAtomizedAndFindsItsOwnEntryAgain() throws Exception {
        List<Integer> p = predicates(40, 0xA70L);
        HashMap<Integer, HashSet<Integer>[]> perPred = new HashMap<>();
        HashMap<Integer, AtomizedNDD> mol = AtomizedNDD.atomization(new HashSet<>(p), perPred);
        AtomizedNDD.enableCaches();
        OperationCache<AtomizedNDD> cache =
                (OperationCache<AtomizedNDD>) field(AtomizedNDD.class, "andCache");
        int checked = 0;
        for (int i = 0; i < p.size(); i++) {
            for (int j = i + 1; j < p.size(); j++) {
                AtomizedNDD a = mol.get(p.get(i)), b = mol.get(p.get(j));
                if (a == b) continue;
                AtomizedNDD r = AtomizedNDD.and(a, b);
                if (r.isTerminal()) continue;   // its recursion stopped early
                assertTrue(cache.getEntry(a, b), "the and of " + i + ", " + j + " is not cached");
                assertTrue(cache.result == r);
                checked++;
            }
        }
        assertTrue(checked > 10, "too few non-terminal pairs: " + checked);
    }

    @Test
    void collectingAtomsOnceGivesTheTreeWalksAtoms() {
        List<Integer> p = predicates(200, 0xC011L);
        HashMap<Integer, HashSet<Integer>[]> perPred = new HashMap<>();
        HashMap<Integer, AtomizedNDD> mol = AtomizedNDD.atomization(new HashSet<>(p), perPred);
        for (AtomizedNDD m : mol.values()) {
            HashSet<Integer>[][] got = new HashSet[2][];
            for (int on = 0; on < 2; on++) {
                AtomizedNDD.setCollectAtomsVisited(on == 1);
                HashSet<Integer>[] none = new HashSet[NDD.getFieldNum() + 1];
                got[on] = new HashSet[NDD.getFieldNum() + 1];
                AtomizedNDD.changeAtoms(AtomizedNDD.getAtomizedFalse(), m, none, got[on]);
            }
            for (int f = 0; f <= NDD.getFieldNum(); f++) {
                assertEquals(got[0][f], got[1][f], "field " + f);
            }
        }
    }
}
