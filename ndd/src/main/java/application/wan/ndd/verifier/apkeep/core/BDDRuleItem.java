package application.wan.ndd.verifier.apkeep.core;

import org.ants.jndd.diagram.NDD;

public class BDDRuleItem<T> {
	public T rule; // the OpenFlow rule
	public int rule_bdd; // the BDD encoding of rule
	public int matches; // the matched packets

	public BDDRuleItem() {
		rule = null;
		rule_bdd = NDD.getFalse();
		matches = NDD.getFalse();
	}

	public BDDRuleItem(T r, int bdd) {
		rule = r;
		rule_bdd = bdd;
		matches = NDD.getFalse();
	}

	public BDDRuleItem(T r, int bdd, int m) {
		rule = r;
		rule_bdd = bdd;
		matches = m;
	}

	public T GetRule() {
		return rule;
	}
}
