package apkeep.core;

/**
 * The packet-set operations APKeep's elements compute their change tuples
 * with, over integer handles (FaVe fork, APKEEP_INCREMENTAL_SCOPE.md §4).
 *
 * <p>Upstream computes them on BDDs through {@link common.BDDACLWrapper}. The
 * NDD paper's APKeep(NDD) is the same element logic over NDDs -- its reference
 * code ({@code FieldNode}) carries every element method twice, once per
 * representation -- so FaVe's fork routes that logic through this interface
 * instead: {@link BddOps} for BDD-APKeep, {@code apkeep.ndd.NddOps} for
 * NDD-APKeep. In both, 0 is the empty set and 1 the full one.
 *
 * <p>Reference discipline is {@code BDDACLWrapper}'s: {@code and}, {@code or},
 * {@code diff} and {@code not} return a handle the caller owns; {@code diffTo}
 * and {@code orTo} also consume their first argument.
 */
public interface PredicateOps {
	int FALSE = 0;
	int TRUE = 1;

	int ref(int p);
	void deref(int p);
	int and(int a, int b);
	int or(int a, int b);
	int diff(int a, int b);
	int not(int a);
	int diffTo(int a, int b);
	int orTo(int a, int b);
}
