package apkeep.ndd;

import org.ants.jndd.diagram.NDD;

import jdd.bdd.BDD;

import apkeep.core.PredicateOps;

/** {@link PredicateOps} on NDD, with {@code BDDACLWrapper}'s reference
 *  discipline: every result is referenced for the caller. */
public final class NddOps implements PredicateOps {
	public static final NddOps INSTANCE = new NddOps();

	private NddOps() {}

	@Override public int ref(int p) { return NDD.ref(p); }
	@Override public void deref(int p) { NDD.deref(p); }
	@Override public int and(int a, int b) { return NDD.ref(NDD.and(a, b)); }
	@Override public int or(int a, int b) { return NDD.ref(NDD.or(a, b)); }
	@Override public int diff(int a, int b) { return NDD.ref(NDD.diff(a, b)); }
	@Override public int not(int a) { return NDD.ref(NDD.not(a)); }
	@Override public int diffTo(int a, int b) {
		int r = NDD.ref(NDD.diff(a, b));
		NDD.deref(a);
		return r;
	}
	@Override public int orTo(int a, int b) { return NDD.orTo(a, b); }

	/** Down one path of {@code set}: at each field node its first edge, and
	 *  the field value JDD's {@code oneSat} picks in that edge's label (free
	 *  bits 0); a field the path skips is 0. The packet is the conjunction
	 *  of the exact per-field values. Labels other than BDDs: the set itself. */
	@Override public int onePacket(int set) {
		if (NDD.isFalse(set)) return FALSE;
		if (NDD.isZddMode() || NDD.hasMixedLabelModes()) return NDD.ref(set);
		BDD labels = NDD.getBDDEngine();
		int[][] value = new int[NDD.getFieldNum() + 1][];
		for (int f = 0; f < value.length; f++) value[f] = new int[NDD.getBDDVars(f).length];
		int node = set;
		while (!NDD.isTerminal(node)) {
			int f = NDD.getField(node);
			int k = 0;
			while (NDD.isFalse(NDD.getEdgeTarget(node, k))) k++;
			int[] sat = labels.oneSat(NDD.getEdgeLabel(node, k), null);
			int[] vars = NDD.getBDDVars(f);
			for (int i = 0; i < vars.length; i++) value[f][i] = sat[labels.getVar(vars[i])] == 1 ? 1 : 0;
			node = NDD.getEdgeTarget(node, k);
		}
		int packet = NDD.getTrue();
		for (int f = 0; f < value.length; f++) {
			int exact = NDD.ref(NDD.encodePrefix(value[f], f));
			int next = NDD.ref(NDD.and(packet, exact));
			NDD.deref(exact);
			NDD.deref(packet);
			packet = next;
		}
		return packet;
	}
}
