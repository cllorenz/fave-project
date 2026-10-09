package apkeep.rules;

import common.BDDACLWrapper;

public abstract class Rule implements Comparable<Rule>{
	
	protected int match_bdd;
	protected int hit_bdd;

	protected int priority;
	protected String port;
	
	public Rule(int match_bdd, int priority, String port) {
		this.priority = priority;
		this.port = port;
		this.match_bdd = match_bdd;
		this.hit_bdd = BDDACLWrapper.BDDFalse;
	}
	
	protected Rule(int match_bdd, int hit_bdd, int priority, String port) {
		this.priority = priority;
		this.port = port;
		this.match_bdd = match_bdd;
		this.hit_bdd = hit_bdd;
	}

	public void setHit_bdd(int hit_bdd) {
		this.hit_bdd = hit_bdd;
	}
	
	public int getMatch_bdd() {
		return match_bdd;
	}

	public int getHit_bdd() {
		return hit_bdd;
	}
	
	public int getPriority() {
		return priority;
	}
	
	public String getPort() {
		return port;
	}
	
	/* FaVe fork (INCREMENTAL_PLAN.md O6): identity is priority, port AND
	 * match. Upstream compared priority and port only, so a removal could find
	 * and remove a DIFFERENT rule with the same action -- every NAT rule sits at
	 * one priority, and a first-match table can hold two rules with the same
	 * egress. Comparing the match BDD is exact: BDD nodes are canonical, so equal
	 * functions are equal ids while both are referenced. */
	@Override
	public boolean equals(Object o) {
		if(o instanceof Rule) {
			Rule another = (Rule) o;
			return another.priority == priority 
					&& another.port.equals(port)
					&& another.match_bdd == match_bdd;
		}
		return false;
	}

	@Override
	public int hashCode() {
		return 31 * (31 * priority + port.hashCode()) + match_bdd;
	}
	
	@Override
	public int compareTo(Rule a) {
		return a.priority - priority;
	}
}
