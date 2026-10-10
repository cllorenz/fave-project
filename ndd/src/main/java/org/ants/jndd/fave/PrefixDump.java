package org.ants.jndd.fave;

import java.util.ArrayList;
import java.util.List;

import org.ants.jndd.diagram.NDD;

import jdd.bdd.BDD;

/**
 * An IPv4 destination set as its canonical list of maximal prefixes, from an
 * NDD on one 32-bit field -- independent of how the field's bits map to label
 * variables, so two engines with different layouts compare exactly. FaVe
 * harness code (the NDD-APKeep reference differential).
 */
public final class PrefixDump {
	private PrefixDump() {}

	/** `ndd` constrains at most `field`; `bit[b]` is the label variable of
	 *  bit b (0 = least significant). "a.b.c.d/len" sorted, or "-" if empty. */
	public static String prefixes(BDD bdd, int ndd, int field, int[] bit) {
		if (NDD.isFalse(ndd)) return "-";
		if (NDD.isTrue(ndd)) return "0.0.0.0/0";
		if (NDD.getField(ndd) != field || NDD.getEdgeCount(ndd) != 1
				|| !NDD.isTrue(NDD.getEdgeTarget(ndd, 0))) {
			throw new IllegalArgumentException("not a set on field " + field + " alone");
		}
		int label = NDD.getEdgeLabel(ndd, 0);
		List<String> out = new ArrayList<>();
		walk(bdd, label, bdd.ref(1), 0, 0L, bit, out);
		return String.join(",", out);
	}

	/** `cube`: the prefix fixed so far (referenced; consumed). */
	private static void walk(BDD bdd, int label, int cube, int depth, long value,
			int[] bit, List<String> out) {
		int inside = bdd.ref(bdd.and(cube, label));
		if (inside == 0) {
			bdd.deref(cube);
			return;
		}
		int outside = bdd.ref(bdd.and(cube, bdd.not(label)));
		bdd.deref(inside);
		if (outside == 0) {
			bdd.deref(cube);
			long ip = value << (32 - depth);
			if (depth == 0) ip = 0;
			out.add(((ip >> 24) & 255) + "." + ((ip >> 16) & 255) + "." + ((ip >> 8) & 255) + "."
					+ (ip & 255) + "/" + depth);
			return;
		}
		bdd.deref(outside);
		int v = bit[31 - depth];
		int zero = bdd.ref(bdd.and(cube, bdd.not(v)));
		int one = bdd.ref(bdd.and(cube, v));
		bdd.deref(cube);
		walk(bdd, label, zero, depth + 1, value << 1, bit, out);
		walk(bdd, label, one, depth + 1, (value << 1) | 1, bit, out);
	}
}
