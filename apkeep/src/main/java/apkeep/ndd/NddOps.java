package apkeep.ndd;

import org.ants.jndd.diagram.NDD;

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
}
