package apkeep.core;

import common.BDDACLWrapper;

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
}
