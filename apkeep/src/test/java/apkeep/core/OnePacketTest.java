package apkeep.core;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.File;
import java.util.ArrayList;
import java.util.Arrays;

import org.junit.jupiter.api.Test;
import org.ants.jndd.diagram.NDD;

import apkeep.ApkeepTestBase;
import apkeep.utils.Evaluator;
import jdd.bdd.BDD;

/**
 * {@link PredicateOps#onePacket} on both backends (witness footprints,
 * APKEEP_INCREMENTAL_SCOPE.md §9): the result is non-empty, inside the set,
 * a single packet -- every variable decided -- and the same on every call.
 */
class OnePacketTest extends ApkeepTestBase {

	private static Network net(String backend) throws Exception {
		Network n = new Network("one-" + backend, backend);
		n.initializeNetwork(new ArrayList<>(Arrays.asList("a x b y")), new ArrayList<>(),
				null, null, null, null);
		n.run(new Evaluator("one", File.createTempFile("apkeep-one", ".out").getAbsolutePath()),
				new ArrayList<>());
		return n;
	}

	/** 10/8 from 192.168/16, or anything to 172.16/12. */
	private static int set(Network n) {
		PredicateOps ops = n.predicateOps();
		int d10, s192, d172;
		if (n.isNdd()) {
			d10 = n.nddEncoder().dstPrefix(167772160L, 8);
			s192 = n.nddEncoder().srcPrefix(3232235520L, 16);
			d172 = n.nddEncoder().dstPrefix(2886729728L, 12);
		} else {
			d10 = n.bdd_engine.encodeDstIPPrefix(167772160L, 8);
			s192 = n.bdd_engine.encodeSrcIPPrefix(3232235520L, 16);
			d172 = n.bdd_engine.encodeDstIPPrefix(2886729728L, 12);
		}
		int both = ops.and(d10, s192);
		int s = ops.or(both, d172);
		ops.deref(both);
		return s;
	}

	private static void check(Network n) {
		PredicateOps ops = n.predicateOps();
		int s = set(n);
		int p = ops.onePacket(s);
		assertNotEquals(PredicateOps.FALSE, p, "empty");
		int inside = ops.and(p, s);
		assertEquals(p, inside, "not inside the set");
		ops.deref(inside);
		int again = ops.onePacket(s);
		assertEquals(p, again, "not deterministic");
		ops.deref(again);
		// a single packet: every variable either holds on all of it or on none
		int decided = 0;
		if (n.isNdd()) {
			for (int f = 0; f <= NDD.getFieldNum(); f++) {
				for (int i = 0; i < NDD.getBDDVars(f).length; i++) {
					int x = ops.and(p, NDD.getVar(f, i));
					assertTrue(x == p || x == PredicateOps.FALSE, "field " + f + " bit " + i + " undecided");
					ops.deref(x);
					decided++;
				}
			}
		} else {
			BDD b = n.bdd_engine.getBDD();
			for (int v = 0; v < b.numberOfVariables(); v++) {
				int lit = b.ref(b.mk(v, PredicateOps.FALSE, PredicateOps.TRUE));
				int x = ops.and(p, lit);
				assertTrue(x == p || x == PredicateOps.FALSE, "variable " + v + " undecided");
				ops.deref(x);
				b.deref(lit);
				decided++;
			}
		}
		assertTrue(decided > 64, "only " + decided + " variables checked");
		assertEquals(PredicateOps.FALSE, ops.onePacket(PredicateOps.FALSE));
		ops.deref(p);
		ops.deref(s);
	}

	@Test
	void bdd() throws Exception {
		check(net("bdd"));
	}

	@Test
	void ndd() throws Exception {
		Network n = net("ndd");
		try {
			check(n);
		} finally {
			n.close();
		}
	}
}
