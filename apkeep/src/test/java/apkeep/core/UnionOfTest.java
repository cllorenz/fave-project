package apkeep.core;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

import org.junit.jupiter.api.Test;

import apkeep.ApkeepTestBase;
import jdd.bdd.BDD;

/**
 * Network.unionOf's reference accounting (FAVE_CHANGES.md §14): the union it
 * returns carries exactly the caller's one reference, and every operand keeps
 * its own. Its first version stored the first pair's OR into level[0] before
 * dereferencing level[0], so the result was left unreferenced (and the operand
 * leaked); the next JDD gc reclaimed a node a footprint still held, and the
 * D11 calibration's wl_up cells crashed in or_rec. Every set size from 1 to 9
 * covers the odd carries and each level's first pair.
 */
class UnionOfTest extends ApkeepTestBase {

    @Test
    void unionOwnsOneReferenceAndLeavesTheOperandsAlone() throws Exception {
        Network net = buildNetwork("net-union", List.of("a 1 b 2"), List.of(), null, List.of());
        net.activate();
        BDD b = net.bdd_engine.getBDD();
        for (int k = 1; k <= 9; k++) {
            Set<Integer> aps = new LinkedHashSet<>();
            for (int i = 0; i < k; i++) {
                // disjoint, as APs are: 10.i.0.0/16, each owned once by the test
                aps.add(net.bdd_engine.encodeDstIPPrefix((10L << 24) | ((long) (16 * k + i) << 16), 16));
            }
            int[] before = aps.stream().mapToInt(b::getRef).toArray();
            int u = net.unionOf(aps);
            int[] after = aps.stream().mapToInt(b::getRef).toArray();
            if (k == 1) {
                // the union of one AP is that AP: the caller's reference is added to it
                assertEquals(aps.iterator().next(), u);
                assertEquals(before[0] + 1, after[0], "the one AP gains the caller's reference");
            } else {
                for (int i = 0; i < k; i++) {
                    assertEquals(before[i], after[i], "operand " + i + " of " + k + " keeps its references");
                }
                assertEquals(1, b.getRef(u), "the union of " + k + " carries one reference");
            }
            b.gc();
            assertTrue(b.isValid(u), "the union of " + k + " survives a gc");
            net.predicateOps().deref(u);
            for (int ap : aps) net.predicateOps().deref(ap);
        }
    }
}
