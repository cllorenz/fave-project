package apkeep.core;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;

import org.junit.jupiter.api.Test;

import apkeep.ApkeepTestBase;

/**
 * Pins APKeep's defining property (Theorem 1): it maintains the *minimum* number
 * of equivalence classes / atomic predicates after each update -- creating ECs
 * only when a new forwarding behaviour appears, and merging them when behaviours
 * coincide. This is the source of APKeep's scale advantage, and the invariant any
 * header-field extension must preserve, so it is pinned here on small networks
 * with known-minimal EC counts (via Network.getAPNum()).
 */
class APKeeperTest extends ApkeepTestBase {

    @Test
    void splitsOnlyOnDistinctForwardingBehaviour() throws Exception {
        // default -> port 1 and 10/8 -> port 2 are two distinct behaviours: 2 ECs.
        Network two = buildNetwork("ap-2", List.of(), List.of("r"), null,
                List.of("+ fwd r 0 0 1 0", "+ fwd r 167772160 8 2 8"));
        assertEquals(2, two.getAPNum(), "two forwarding classes -> 2 atomic predicates");

        // adding a disjoint 20/8 -> port 3 introduces exactly one more behaviour.
        Network three = buildNetwork("ap-3", List.of(), List.of("r"), null,
                List.of("+ fwd r 0 0 1 0", "+ fwd r 167772160 8 2 8", "+ fwd r 335544320 8 3 8"));
        assertEquals(3, three.getAPNum(), "three disjoint classes -> 3 atomic predicates");
    }

    @Test
    void mergesWhenBehavioursBecomeIdentical() throws Exception {
        // default -> 1 and 10/8 -> 2 start as 2 ECs; then route 10/8 -> 1 at a
        // higher priority, so 10/8 now behaves exactly like the default. APKeep
        // must MERGE the two classes back into one (not leave a redundant EC).
        Network net = buildNetwork("ap-merge", List.of(), List.of("r"), null,
                List.of("+ fwd r 0 0 1 0",
                        "+ fwd r 167772160 8 2 8",
                        "+ fwd r 167772160 8 1 9"));  // 10/8 -> 1, higher priority
        assertEquals(1, net.getAPNum(), "identical behaviour -> classes merge back to 1");
    }
}
