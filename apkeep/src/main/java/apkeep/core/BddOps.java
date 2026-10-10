package apkeep.core;

import common.BDDACLWrapper;
import jdd.bdd.BDD;

/** {@link PredicateOps} on one network's BDD engine: upstream's calls, unchanged. */
public final class BddOps implements PredicateOps {
	private final BDDACLWrapper bdd;

	public BddOps(BDDACLWrapper bdd) {
		this.bdd = bdd;
	}

	@Override public int ref(int p) { return bdd.ref(p); }
	@Override public void deref(int p) { bdd.deref(p); }
	@Override public int and(int a, int b) { return bdd.and(a, b); }
	@Override public int or(int a, int b) { return bdd.or(a, b); }
	@Override public int diff(int a, int b) { return bdd.diff(a, b); }
	@Override public int not(int a) { return bdd.negate(a); }
	@Override public int diffTo(int a, int b) { return bdd.diffTo(a, b); }
	@Override public int orTo(int a, int b) { return bdd.orTo(a, b); }

	/** The assignment JDD's {@code oneSat} picks, its free variables set to
	 *  0, built bottom-up (JDD orders variables by index). */
	@Override public int onePacket(int set) {
		if (set == FALSE) return FALSE;
		BDD b = bdd.getBDD();
		int[] bits = b.oneSat(set, null);
		int u = TRUE;
		for (int v = bits.length - 1; v >= 0; v--) {
			int next = b.ref(bits[v] == 1 ? b.mk(v, FALSE, u) : b.mk(v, u, FALSE));
			b.deref(u);
			u = next;
		}
		return u;
	}
}
